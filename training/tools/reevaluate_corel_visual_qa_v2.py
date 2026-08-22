"""Replay prior review-held mutations through page-anchored Visual QA V2."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from training.company_archive.database import ArchiveDatabase
from training.company_archive.hashing import sha256_file
from training.company_archive.safety import assert_source_unchanged, source_stat_guard
from training.corel_operator.models import OperatorResultClass
from training.corel_operator.policy import sanitize_error, source_token
from training.corel_operator.reliability import classify_visual_qa_reevaluation
from training.corel_operator.runtime import CorelOperatorRuntime
from training.corel_operator.state import OperatorStateDatabase


RUN_ID = "visual-qa-v2-reevaluation-001"


def execute_previous_result_replay(
    *,
    row: dict,
    previous_result: dict,
    archive_root: Path,
    workspace: Path,
    attempt: int,
    timeout_seconds: float,
) -> dict:
    source = Path(str(row["absolute_path"])).resolve()
    token = source_token(source, archive_root)
    guard = source_stat_guard(source)
    sha_before = sha256_file(source)
    worker_root = workspace / "_worker"
    worker_root.mkdir(parents=True, exist_ok=True)
    request_path = worker_root / f"{token.removeprefix('source:')}.attempt_{attempt}.json"
    response_path = worker_root / f"{token.removeprefix('source:')}.attempt_{attempt}.response.json"
    request_path.write_text(
        json.dumps(
            {
                "row": row,
                "attempt": attempt,
                "replay_result": previous_result,
            }
        ),
        encoding="utf-8",
    )
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "training.tools.run_corel_operator_mutation_worker",
                "--archive-root",
                str(archive_root),
                "--workspace",
                str(workspace),
                "--request",
                str(request_path),
                "--response",
                str(response_path),
            ],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode or not response_path.is_file():
            result = {
                "result": OperatorResultClass.FAILED.value,
                "source_token": token,
                "error_code": "WORKER_FAILURE",
                "error": sanitize_error(
                    completed.stderr or completed.stdout or "worker produced no response",
                    archive_root=archive_root,
                ),
            }
        else:
            result = json.loads(response_path.read_text(encoding="utf-8"))
    except subprocess.TimeoutExpired:
        recovery_error = None
        runtime = CorelOperatorRuntime()
        try:
            runtime.close_active_if_under(workspace)
        except Exception:
            try:
                runtime.close_active_if_exact(source)
            except Exception as exc:
                recovery_error = sanitize_error(exc, archive_root=archive_root)
        result = {
            "result": OperatorResultClass.FAILED.value,
            "source_token": token,
            "error_code": "WORKER_TIMEOUT",
            "error": f"worker exceeded {timeout_seconds:.0f}s",
            "recovery_error": recovery_error,
        }
    finally:
        request_path.unlink(missing_ok=True)
        response_path.unlink(missing_ok=True)
    assert_source_unchanged(source, guard)
    sha_after = sha256_file(source)
    if sha_before != sha_after:
        raise RuntimeError(f"source mutation detected for {token}")
    result.update(
        {
            "attempt": attempt,
            "elapsed_seconds": time.perf_counter() - started,
            "source_size_before": guard[0],
            "source_mtime_ns_before": guard[1],
            "source_sha256_before": sha_before,
            "source_sha256_after": sha_after,
            "source_unchanged": True,
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--previous-state", type=Path, required=True)
    parser.add_argument("--previous-run-id", default="real-mutation-pilot-001")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=240)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--read-only-source", action="store_true", required=True)
    args = parser.parse_args()
    archive_root = args.archive_root.resolve()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    state = OperatorStateDatabase(workspace / "reevaluation.sqlite")
    previous = OperatorStateDatabase(args.previous_state)
    review_rows = [
        item["result"]
        for item in previous.batch_rows(args.previous_run_id)
        if item["result"].get("result") == OperatorResultClass.NEEDS_REVIEW.value
    ]
    by_token = {item["source_token"]: item for item in review_rows}
    inventory = ArchiveDatabase(args.inventory)
    source_rows = {
        source_token(Path(str(row["absolute_path"])), archive_root): row
        for row in inventory.rows("cdr_candidate=1")
    }
    completed = {row["source_token"] for row in state.batch_rows(RUN_ID)}
    for index, token in enumerate(sorted(by_token), start=1):
        if token in completed:
            print(f"[{index}/{len(by_token)}] {token} RESUME_SKIP", flush=True)
            continue
        row = source_rows.get(token)
        if row is None:
            result = {
                "result": OperatorResultClass.UNSUPPORTED.value,
                "source_token": token,
                "source_unchanged": True,
                "error_code": "SOURCE_MAPPING_MISSING",
                "attempt": 0,
            }
        else:
            result = {}
            for attempt in range(1, args.max_attempts + 1):
                result = execute_previous_result_replay(
                    row=row,
                    previous_result=by_token[token],
                    archive_root=archive_root,
                    workspace=workspace,
                    attempt=attempt,
                    timeout_seconds=args.timeout_seconds,
                )
                if result.get("result") != OperatorResultClass.FAILED.value:
                    break
        result["reevaluation_class"] = classify_visual_qa_reevaluation(result)
        state.put_batch(
            RUN_ID,
            token,
            str(result["reevaluation_class"]),
            result,
            attempt_count=int(result.get("attempt", 0)),
        )
        print(
            f"[{index}/{len(by_token)}] {token} {result['reevaluation_class']}",
            flush=True,
        )

    output_rows = state.batch_rows(RUN_ID)
    classifications = Counter(row["result"]["reevaluation_class"] for row in output_rows)
    summary = {
        "run_id": RUN_ID,
        "expected_count": len(review_rows),
        "processed_count": len(output_rows),
        "upgraded_to_auto_success": classifications["UPGRADED_TO_AUTO_SUCCESS"],
        "still_needs_review": classifications["STILL_NEEDS_REVIEW"],
        "confirmed_regression": classifications["CONFIRMED_REGRESSION"],
        "qa_evidence_insufficient": classifications["QA_EVIDENCE_INSUFFICIENT"],
        "source_mutations": sum(
            not bool(row["result"].get("source_unchanged")) for row in output_rows
        ),
    }
    (workspace / "reevaluation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["processed_count"] == summary["expected_count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
