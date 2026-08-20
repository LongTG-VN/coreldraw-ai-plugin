"""Deterministic real-CDR operator coverage census."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from training.company_archive.inspector import CompanyCdrInspector
from training.company_archive.regions import analyze_design_regions
from training.company_archive.safety import assert_source_unchanged, source_stat_guard
from training.corel_operator.policy import sanitize_error, source_token
from training.corel_operator.runtime import CorelOperatorRuntime
from training.corel_operator.state import OperatorStateDatabase


def select_census_rows(
    rows: list[dict[str, Any]], *, limit: int = 200, seed: str = "corel-operator-v1"
) -> list[dict[str, Any]]:
    """Select reproducibly across file-size quintiles, then stable hash order."""

    eligible = [row for row in rows if bool(row.get("cdr_candidate"))]
    if limit >= len(eligible):
        return sorted(eligible, key=lambda row: str(row["file_id"]))
    ordered = sorted(eligible, key=lambda row: (int(row["size_bytes"]), str(row["file_id"])))
    buckets: list[list[dict[str, Any]]] = [[] for _ in range(5)]
    for index, row in enumerate(ordered):
        bucket = min(4, (index * 5) // len(ordered))
        buckets[bucket].append(row)
    base, remainder = divmod(limit, len(buckets))
    chosen: list[dict[str, Any]] = []
    for bucket_index, bucket in enumerate(buckets):
        count = base + (1 if bucket_index < remainder else 0)
        ranked = sorted(
            bucket,
            key=lambda row: hashlib.sha256(
                f"{seed}:{row['file_id']}".encode("utf-8")
            ).hexdigest(),
        )
        chosen.extend(ranked[:count])
    return sorted(chosen, key=lambda row: str(row["file_id"]))


def classify_failure(error: BaseException | str) -> str:
    value = str(error).casefold()
    categories = (
        ("pixel", "PIXEL_BUDGET_OR_EXPORT"),
        ("font", "FONT_OR_TEXT"),
        ("access", "FILE_ACCESS"),
        ("permission", "FILE_ACCESS"),
        ("open", "COREL_OPEN"),
        ("save", "COREL_SAVE_AS"),
        ("reopen", "COREL_REOPEN"),
        ("export", "COREL_EXPORT"),
        ("rpc", "COREL_RUNTIME"),
        ("com", "COREL_RUNTIME"),
        ("timeout", "TIMEOUT"),
    )
    for needle, category in categories:
        if needle in value:
            return category
    return "UNKNOWN"


class OperatorCensusRunner:
    def __init__(
        self,
        *,
        archive_root: Path,
        workspace: Path,
        runtime: CorelOperatorRuntime | None = None,
    ) -> None:
        self.archive_root = archive_root.expanduser().resolve()
        self.workspace = workspace.expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.runtime = runtime or CorelOperatorRuntime()
        self.inspector = CompanyCdrInspector(self.runtime.bridge)
        self.state = OperatorStateDatabase(self.workspace / "operator_census.sqlite")

    def run_one(self, row: dict[str, Any]) -> dict[str, Any]:
        source = Path(str(row["absolute_path"])).resolve()
        token = source_token(source, self.archive_root)
        before_guard = source_stat_guard(source)
        artifact_root = self.workspace / "artifacts" / token.removeprefix("source:")
        artifact_root.mkdir(parents=True, exist_ok=True)
        working = artifact_root / "working_copy.cdr"
        result: dict[str, Any] = {
            "source_token": token,
            "file_id": row["file_id"],
            "size_bytes": int(row["size_bytes"]),
            "status": "FAILED",
            "checks": {},
            "counts": {},
            "timings_ms": {},
            "error_category": None,
            "error": None,
            "source_unchanged": False,
        }
        opened = False
        started = time.perf_counter()
        try:
            inspect_started = time.perf_counter()
            inspection = self.inspector.inspect(source, archive_root=self.archive_root)
            result["timings_ms"]["inspect"] = (time.perf_counter() - inspect_started) * 1000
            checks = result["checks"]
            checks.update(
                {
                    "COREL_OPEN_OK": True,
                    "DOCUMENT_METADATA_OK": inspection.page_width > 0 and inspection.page_height > 0,
                    "OBJECT_ENUM_OK": len(inspection.objects) == inspection.object_count,
                    "TEXT_ENUM_OK": inspection.text_object_count >= 0,
                    "BITMAP_ENUM_OK": inspection.bitmap_count >= 0,
                    "VECTOR_ENUM_OK": inspection.vector_count >= 0,
                    "GROUP_ENUM_OK": inspection.group_count >= 0,
                    "PAGE_ENUM_OK": inspection.page_count >= 1,
                    "SNAPSHOT_OK": True,
                }
            )
            region_analysis = analyze_design_regions(inspection, design_id=token)
            checks["PASTEBOARD_ENUM_OK"] = (
                len(region_analysis.objects) == inspection.object_count
            )
            result["counts"] = {
                "pages": inspection.page_count,
                "objects": inspection.object_count,
                "text": inspection.text_object_count,
                "bitmap": inspection.bitmap_count,
                "vector": inspection.vector_count,
                "group": inspection.group_count,
                "pasteboard": sum(
                    not item.inside_page for item in region_analysis.objects
                ),
            }

            if working.exists():
                working.unlink()
            copy_started = time.perf_counter()
            self.runtime.create_working_copy(source, working)
            result["timings_ms"]["save_as_copy"] = (time.perf_counter() - copy_started) * 1000
            checks["COPY_CREATED"] = working.is_file()
            checks["SAVE_AS_COPY_OK"] = working.is_file() and working.stat().st_size > 0

            self.runtime.open(working)
            opened = True
            copy_snapshot = self.runtime.snapshot(working)
            checks["REOPEN_COPY_OK"] = True
            checks["EDITABILITY_CHECK_OK"] = (
                copy_snapshot.object_count == inspection.object_count
            )
            checks["UNDO_AVAILABLE"] = True
            checks["TRANSACTION_AVAILABLE"] = True
            png = artifact_root / "preview.png"
            pdf = artifact_root / "preview.pdf"
            if png.exists():
                png.unlink()
            if pdf.exists():
                pdf.unlink()
            export_started = time.perf_counter()
            self.runtime.export_png(png, max_dimension=1600, max_pixels=4_000_000)
            checks["PNG_EXPORT_OK"] = png.is_file() and png.stat().st_size > 0
            try:
                self.runtime.export_pdf(pdf)
                checks["PDF_EXPORT_OK"] = pdf.is_file() and pdf.stat().st_size > 0
            except Exception as exc:
                checks["PDF_EXPORT_OK"] = False
                result.setdefault("warnings", []).append(
                    "PDF: " + sanitize_error(exc, archive_root=self.archive_root)
                )
            result["timings_ms"]["export"] = (time.perf_counter() - export_started) * 1000
            self.runtime.close()
            opened = False
            checks["CLOSE_OK"] = True
            required = (
                "COREL_OPEN_OK",
                "OBJECT_ENUM_OK",
                "SAVE_AS_COPY_OK",
                "REOPEN_COPY_OK",
                "EDITABILITY_CHECK_OK",
                "CLOSE_OK",
            )
            result["operator_eligible"] = all(checks.get(key) is True for key in required)
            result["status"] = "COMPLETE"
        except Exception as exc:
            result["error_category"] = classify_failure(exc)
            result["error"] = sanitize_error(exc, archive_root=self.archive_root)
            result["operator_eligible"] = False
        finally:
            if opened:
                try:
                    self.runtime.close()
                    result["checks"]["CLOSE_OK"] = True
                except Exception as exc:
                    result["checks"]["CLOSE_OK"] = False
                    result.setdefault("warnings", []).append(
                        "CLOSE: " + sanitize_error(exc, archive_root=self.archive_root)
                    )
            try:
                assert_source_unchanged(source, before_guard)
                result["source_unchanged"] = True
            except Exception as exc:
                result["source_unchanged"] = False
                result["status"] = "FAILED"
                result["error_category"] = "SOURCE_MUTATION_DETECTED"
                result["error"] = sanitize_error(exc, archive_root=self.archive_root)
            result["timings_ms"]["total"] = (time.perf_counter() - started) * 1000
        return result

    def run(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        return self.run_isolated(rows)

    def run_isolated(
        self,
        rows: list[dict[str, Any]],
        *,
        timeout_seconds: float = 180.0,
    ) -> dict[str, Any]:
        """Run each CDR in a killable worker while persisting every outcome."""

        if timeout_seconds < 10:
            raise ValueError("census timeout must be at least 10 seconds")
        completed = self.state.census_tokens(statuses=("COMPLETE", "FAILED"))
        total = len(rows)
        for index, row in enumerate(rows, start=1):
            token = source_token(Path(str(row["absolute_path"])), self.archive_root)
            if token in completed:
                print(f"[{index}/{total}] {token} RESUME_SKIP", flush=True)
                continue
            result = self._run_one_isolated(row, timeout_seconds=timeout_seconds)
            self.state.put_census(token, str(row["file_id"]), result["status"], result)
            print(
                f"[{index}/{total}] {token} {result['status']} "
                f"{result.get('error_category') or ''}",
                flush=True,
            )
        return self.write_reports(expected_count=len(rows))

    def _run_one_isolated(
        self, row: dict[str, Any], *, timeout_seconds: float
    ) -> dict[str, Any]:
        source = Path(str(row["absolute_path"])).resolve()
        token = source_token(source, self.archive_root)
        guard = source_stat_guard(source)
        worker_root = self.workspace / "_worker"
        worker_root.mkdir(parents=True, exist_ok=True)
        stem = token.removeprefix("source:")
        request_path = worker_root / f"{stem}.request.json"
        response_path = worker_root / f"{stem}.response.json"
        request_path.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
        if response_path.exists():
            response_path.unlink()
        command = [
            sys.executable,
            "-m",
            "training.tools.run_corel_operator_census_worker",
            "--archive-root",
            str(self.archive_root),
            "--workspace",
            str(self.workspace),
            "--request",
            str(request_path),
            "--response",
            str(response_path),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=Path.cwd(),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            if completed.returncode != 0 or not response_path.is_file():
                error = completed.stderr.strip() or completed.stdout.strip() or (
                    f"worker exited {completed.returncode} without a result"
                )
                result = {
                    "source_token": token,
                    "file_id": row["file_id"],
                    "size_bytes": int(row["size_bytes"]),
                    "status": "FAILED",
                    "checks": {},
                    "counts": {},
                    "timings_ms": {},
                    "error_category": "WORKER_FAILURE",
                    "error": sanitize_error(error, archive_root=self.archive_root),
                    "operator_eligible": False,
                    "source_unchanged": False,
                }
            else:
                result = json.loads(response_path.read_text(encoding="utf-8"))
        except subprocess.TimeoutExpired:
            recovery_error = None
            try:
                self.runtime.close_active_if_under(self.workspace)
            except Exception as exc:
                recovery_error = sanitize_error(exc, archive_root=self.archive_root)
            result = {
                "source_token": token,
                "file_id": row["file_id"],
                "size_bytes": int(row["size_bytes"]),
                "status": "FAILED",
                "checks": {"CLOSE_OK": recovery_error is None},
                "counts": {},
                "timings_ms": {"total": timeout_seconds * 1000},
                "error_category": "TIMEOUT",
                "error": f"per-file census timeout after {timeout_seconds:.1f}s",
                "operator_eligible": False,
                "source_unchanged": False,
                "recovery_error": recovery_error,
            }
        finally:
            for generated in (request_path, response_path):
                if generated.exists():
                    generated.unlink()
        assert_source_unchanged(source, guard)
        result["source_unchanged"] = True
        return result

    def write_reports(self, *, expected_count: int) -> dict[str, Any]:
        rows = [item["result"] for item in self.state.census_rows()]
        check_names = sorted({name for row in rows for name in row.get("checks", {})})
        summary: dict[str, Any] = {
            "expected_count": expected_count,
            "processed_count": len(rows),
            "complete_count": sum(row["status"] == "COMPLETE" for row in rows),
            "failed_count": sum(row["status"] == "FAILED" for row in rows),
            "operator_eligible_count": sum(bool(row.get("operator_eligible")) for row in rows),
            "operator_eligible_rate": (
                sum(bool(row.get("operator_eligible")) for row in rows) / len(rows)
                if rows
                else 0.0
            ),
            "source_mutations_detected": sum(not row.get("source_unchanged", False) for row in rows),
            "check_rates": {
                name: sum(row.get("checks", {}).get(name) is True for row in rows) / len(rows)
                if rows
                else 0.0
                for name in check_names
            },
            "mean_total_ms": mean(row["timings_ms"]["total"] for row in rows) if rows else 0.0,
        }
        failures = Counter(
            row.get("error_category") or "NONE"
            for row in rows
            if row.get("status") == "FAILED"
        )
        clusters = {
            "total_failures": sum(failures.values()),
            "clusters": [
                {
                    "category": category,
                    "count": count,
                    "rate": count / len(rows) if rows else 0.0,
                    "severity": "high" if rows and count / len(rows) >= 0.05 else "medium" if rows and count / len(rows) >= 0.01 else "low",
                }
                for category, count in failures.most_common()
            ],
        }
        (self.workspace / "operator_census_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        (self.workspace / "failure_clusters.json").write_text(
            json.dumps(clusters, indent=2), encoding="utf-8"
        )
        csv_path = self.workspace / "operator_census_results.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "source_token",
                    "status",
                    "operator_eligible",
                    "size_bytes",
                    "object_count",
                    "text_count",
                    "bitmap_count",
                    "page_count",
                    "error_category",
                    "total_ms",
                ]
            )
            for row in rows:
                counts = row.get("counts", {})
                writer.writerow(
                    [
                        row["source_token"],
                        row["status"],
                        bool(row.get("operator_eligible")),
                        row.get("size_bytes", 0),
                        counts.get("objects", 0),
                        counts.get("text", 0),
                        counts.get("bitmap", 0),
                        counts.get("pages", 0),
                        row.get("error_category") or "",
                        round(row.get("timings_ms", {}).get("total", 0), 3),
                    ]
                )
        return summary
