"""Resumable read-only Corel inspection and deterministic plan-only scale test."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from training.company_archive.database import ArchiveDatabase
from training.company_archive.safety import assert_source_unchanged, source_stat_guard
from training.corel_agent.context import build_document_context
from training.corel_agent.jobs import CorelJobStore
from training.corel_agent.models import CorelAgentRequestV1
from training.corel_agent.policy import validate_agent_plan
from training.corel_agent.provider import (
    CorelPlannerContext,
    DeterministicPlannerProvider,
    PlannerProviderError,
)
from training.corel_operator.capabilities import inspect_operator_capabilities
from training.corel_operator.policy import sanitize_error
from training.corel_operator.tools import OperatorToolService


def _request_for(inspection) -> str | None:
    capability = inspect_operator_capabilities(inspection)
    if capability.phone_target_count:
        return "Số điện thoại thành 0900 000 000; giữ nguyên mọi thứ khác"
    if capability.price_target_count:
        return "Giá thành 99K; giữ nguyên mọi thứ khác"
    candidates = capability.operation_candidates.get("set_font_size", [])
    for object_id in candidates:
        item = next(value for value in inspection.objects if value.object_id == object_id)
        if item.font_size is not None and 4 <= item.font_size < 299:
            return f"Cỡ chữ {object_id} thành {round(item.font_size + 1, 3)}; giữ nguyên mọi thứ khác"
    return None


def _atomic_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--selection-seed", required=True)
    parser.add_argument("--read-only-source", action="store_true", required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 300:
        raise SystemExit("--limit must be in 1..300")

    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    inventory = ArchiveDatabase(args.inventory)
    rows = sorted(
        inventory.rows("cdr_candidate=1"),
        key=lambda row: hashlib.sha256(
            f"{args.selection_seed}:{row['file_id']}".encode("utf-8")
        ).hexdigest(),
    )[: args.limit]
    service = OperatorToolService(
        archive_root=args.archive_root,
        workspace=workspace / "operator",
        inventory=inventory,
    )
    provider = DeterministicPlannerProvider()
    jobs = CorelJobStore(workspace / "jobs.sqlite")
    state_path = workspace / "dry_run_state.json"
    state = (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.is_file()
        else {"schema_version": "1.0", "records": {}}
    )
    records: dict[str, dict[str, Any]] = state["records"]

    for index, row in enumerate(rows, start=1):
        file_id = str(row["file_id"])
        if file_id in records:
            print(f"[{index}/{len(rows)}] RESUME_SKIP", flush=True)
            continue
        source = Path(str(row["absolute_path"])).resolve()
        guard = source_stat_guard(source)
        started = time.perf_counter()
        try:
            inspection = service.inspect_model(file_id)
            assert_source_unchanged(source, guard)
            instruction = _request_for(inspection)
            if instruction is None:
                record = {"document_id": file_id, "status": "UNSUPPORTED"}
            else:
                request = CorelAgentRequestV1(
                    request_id=f"dryrun-{index:04d}",
                    document_id=file_id,
                    instruction=instruction,
                    execution_mode="DRY_RUN",
                )
                context = build_document_context(
                    inspection,
                    document_id=file_id,
                    include_text=True,
                )
                envelope = provider.plan(
                    request,
                    CorelPlannerContext(summary=context, inspection=inspection),
                )
                validation = validate_agent_plan(request, envelope)
                source_sha = str(row.get("sha256") or "")
                if len(source_sha) != 64:
                    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
                job, duplicate = jobs.create_validated(
                    request,
                    envelope,
                    validation,
                    source_sha256=source_sha,
                )
                record = {
                    "document_id": file_id,
                    "status": "PLANNABLE" if validation.accepted else "UNSUPPORTED",
                    "action_count": len(envelope.plan.actions),
                    "risk": validation.risk_level.value,
                    "review_required": validation.review_required,
                    "planner_is_ai": envelope.provenance.planner_is_ai,
                    "job_status": job.status.value,
                    "duplicate": duplicate,
                    "context_text_candidates": len(context.relevant_text),
                }
        except PlannerProviderError as exc:
            record = {
                "document_id": file_id,
                "status": "AMBIGUOUS" if exc.code == "TARGET_AMBIGUOUS" else "UNSUPPORTED",
                "error_code": exc.code,
            }
        except Exception as exc:
            record = {
                "document_id": file_id,
                "status": "FAILED",
                "error": sanitize_error(exc, archive_root=args.archive_root),
            }
        try:
            assert_source_unchanged(source, guard)
            record["source_unchanged"] = True
        except Exception:
            record["source_unchanged"] = False
            records[file_id] = record
            _atomic_json(state_path, state)
            raise RuntimeError("source mutation detected; dry-run stopped")
        record["elapsed_seconds"] = time.perf_counter() - started
        records[file_id] = record
        _atomic_json(state_path, state)
        print(f"[{index}/{len(rows)}] {record['status']}", flush=True)

    selected_records = [records[str(row["file_id"])] for row in rows]
    counts = Counter(record["status"] for record in selected_records)
    elapsed = [float(record["elapsed_seconds"]) for record in selected_records]
    summary = {
        "schema_version": "1.0",
        "selection_seed": args.selection_seed,
        "planner_type": "deterministic",
        "planner_is_ai": False,
        "execution_mode": "DRY_RUN",
        "files": len(selected_records),
        "plannable": counts["PLANNABLE"],
        "ambiguous": counts["AMBIGUOUS"],
        "unsupported": counts["UNSUPPORTED"],
        "failed": counts["FAILED"],
        "source_mutations": sum(not record["source_unchanged"] for record in selected_records),
        "median_seconds": median(elapsed) if elapsed else None,
        "total_seconds": sum(elapsed),
    }
    _atomic_json(workspace / "dry_run_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["source_mutations"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
