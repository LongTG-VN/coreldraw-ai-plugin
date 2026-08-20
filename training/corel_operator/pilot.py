"""Resumable working-copy mutation pilot over census-eligible real CDRs."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from training.company_archive.safety import assert_source_unchanged, source_stat_guard
from training.corel_operator.models import OperatorResultClass
from training.corel_operator.policy import sanitize_error, source_token
from training.corel_operator.runtime import CorelOperatorRuntime
from training.corel_operator.state import OperatorStateDatabase


def select_mutation_pilot_rows(
    census_rows: list[dict[str, Any]],
    inventory_by_file_id: dict[str, dict[str, Any]],
    *,
    limit: int = 20,
    seed: str = "corel-mutation-pilot-v1",
) -> list[dict[str, Any]]:
    eligible: list[dict[str, Any]] = []
    for state_row in census_rows:
        result = state_row["result"]
        inventory = inventory_by_file_id.get(str(state_row["file_id"]))
        if (
            inventory is not None
            and bool(result.get("operator_eligible"))
            and int(result.get("counts", {}).get("text", 0)) > 0
        ):
            eligible.append(inventory)
    eligible.sort(
        key=lambda row: hashlib.sha256(
            f"{seed}:{row['file_id']}".encode("utf-8")
        ).hexdigest()
    )
    return eligible[:limit]


class MutationPilotRunner:
    def __init__(
        self,
        *,
        archive_root: Path,
        workspace: Path,
        timeout_seconds: float = 240.0,
        max_attempts: int = 2,
    ) -> None:
        self.archive_root = archive_root.resolve()
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.state = OperatorStateDatabase(self.workspace / "mutation_pilot.sqlite")
        self.runtime = CorelOperatorRuntime()
        self.run_id = "real-mutation-pilot-001"

    def run(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        finished = {
            row["source_token"]
            for row in self.state.batch_rows(self.run_id)
            if row["status"] in {"COMPLETE", "NEEDS_REVIEW", "UNSUPPORTED", "FAILED"}
        }
        for index, row in enumerate(rows, start=1):
            source = Path(str(row["absolute_path"])).resolve()
            token = source_token(source, self.archive_root)
            if token in finished:
                print(f"[{index}/{len(rows)}] {token} RESUME_SKIP", flush=True)
                continue
            final: dict[str, Any] | None = None
            for attempt in range(1, self.max_attempts + 1):
                final = self._run_one_isolated(row, attempt=attempt)
                if final.get("result") != OperatorResultClass.FAILED.value:
                    break
            assert final is not None
            status = (
                "COMPLETE"
                if final.get("result")
                in {
                    OperatorResultClass.AUTO_SUCCESS.value,
                    OperatorResultClass.SUCCESS_WITH_WARNING.value,
                }
                else str(final.get("result", "FAILED"))
            )
            self.state.put_batch(
                self.run_id,
                token,
                status,
                final,
                attempt_count=int(final.get("attempt", self.max_attempts)),
            )
            print(f"[{index}/{len(rows)}] {token} {status}", flush=True)
        return self.write_reports(expected_count=len(rows))

    def _run_one_isolated(self, row: dict[str, Any], *, attempt: int) -> dict[str, Any]:
        source = Path(str(row["absolute_path"])).resolve()
        token = source_token(source, self.archive_root)
        guard = source_stat_guard(source)
        worker_root = self.workspace / "_worker"
        worker_root.mkdir(parents=True, exist_ok=True)
        stem = f"{token.removeprefix('source:')}.attempt_{attempt}"
        request_path = worker_root / f"{stem}.request.json"
        response_path = worker_root / f"{stem}.response.json"
        request_path.write_text(
            json.dumps({"row": row, "attempt": attempt}, ensure_ascii=False),
            encoding="utf-8",
        )
        if response_path.exists():
            response_path.unlink()
        command = [
            sys.executable,
            "-m",
            "training.tools.run_corel_operator_mutation_worker",
            "--archive-root",
            str(self.archive_root),
            "--workspace",
            str(self.workspace),
            "--request",
            str(request_path),
            "--response",
            str(response_path),
        ]
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=Path.cwd(),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            if completed.returncode != 0 or not response_path.is_file():
                error = completed.stderr.strip() or completed.stdout.strip() or (
                    f"worker exited {completed.returncode} without a result"
                )
                result = {
                    "result": OperatorResultClass.FAILED.value,
                    "source_token": token,
                    "error_code": "WORKER_FAILURE",
                    "error": sanitize_error(error, archive_root=self.archive_root),
                    "source_unchanged": False,
                }
            else:
                result = json.loads(response_path.read_text(encoding="utf-8"))
        except subprocess.TimeoutExpired:
            recovery_error = None
            try:
                self.runtime.close_active_if_under(self.workspace)
            except Exception as exc:
                try:
                    self.runtime.close_active_if_exact(source)
                except Exception as source_close_exc:
                    recovery_error = sanitize_error(
                        source_close_exc, archive_root=self.archive_root
                    )
            result = {
                "result": OperatorResultClass.FAILED.value,
                "source_token": token,
                "error_code": "TIMEOUT_EXCEEDED",
                "error": f"mutation worker exceeded {self.timeout_seconds:.1f}s",
                "recovery_error": recovery_error,
                "source_unchanged": False,
            }
        finally:
            for generated in (request_path, response_path):
                if generated.exists():
                    generated.unlink()
        assert_source_unchanged(source, guard)
        result["source_unchanged"] = True
        result["attempt"] = attempt
        result["elapsed_seconds"] = time.perf_counter() - started
        return result

    def write_reports(self, *, expected_count: int) -> dict[str, Any]:
        rows = self.state.batch_rows(self.run_id)
        payloads = [row["result"] for row in rows]
        summary = {
            "run_id": self.run_id,
            "expected_count": expected_count,
            "processed_count": len(rows),
            "auto_success": sum(
                item.get("result") == OperatorResultClass.AUTO_SUCCESS.value
                for item in payloads
            ),
            "success_with_warning": sum(
                item.get("result") == OperatorResultClass.SUCCESS_WITH_WARNING.value
                for item in payloads
            ),
            "needs_review": sum(
                item.get("result") == OperatorResultClass.NEEDS_REVIEW.value
                for item in payloads
            ),
            "unsupported": sum(
                item.get("result") == OperatorResultClass.UNSUPPORTED.value
                for item in payloads
            ),
            "failed": sum(
                item.get("result") == OperatorResultClass.FAILED.value
                for item in payloads
            ),
            "source_mutations_detected": sum(
                not bool(item.get("source_unchanged")) for item in payloads
            ),
            "editable_reopen_verified": sum(
                bool(item.get("editability_verified")) for item in payloads
            ),
        }
        (self.workspace / "mutation_pilot_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        with (self.workspace / "mutation_pilot_results.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "source_token",
                    "result",
                    "attempt",
                    "object_count_before",
                    "object_count_after",
                    "editability_verified",
                    "source_unchanged",
                    "error_code",
                ]
            )
            for item in payloads:
                writer.writerow(
                    [
                        item.get("source_token"),
                        item.get("result"),
                        item.get("attempt"),
                        item.get("object_count_before"),
                        item.get("object_count_after"),
                        item.get("editability_verified"),
                        item.get("source_unchanged"),
                        item.get("error_code") or "",
                    ]
                )
        return summary
