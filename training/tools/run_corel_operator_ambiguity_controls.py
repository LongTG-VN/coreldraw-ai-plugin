"""Run bounded real-CDR ambiguity controls without mutating source documents."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from training.company_archive.database import ArchiveDatabase
from training.company_archive.inspector import CompanyCdrInspector
from training.corel_operator.ambiguity import (
    build_ambiguous_text_control_plan,
    summarize_ambiguity_controls,
)
from training.corel_operator.policy import source_token
from training.corel_operator.service import SafeCorelOperator
from training.corel_operator.state import OperatorStateDatabase


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--census-state", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--selection-seed", default="corel-ambiguity-controls-v1")
    parser.add_argument("--read-only-source", action="store_true", required=True)
    args = parser.parse_args()

    archive_root = args.archive_root.resolve()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    inventory_rows = ArchiveDatabase(args.inventory).rows("cdr_candidate=1")
    inventory_by_id = {str(row["file_id"]): row for row in inventory_rows}
    candidates: list[dict[str, object]] = []
    for state_row in OperatorStateDatabase(args.census_state).census_rows():
        result = state_row["result"]
        row = inventory_by_id.get(str(state_row["file_id"]))
        if (
            row is not None
            and bool(result.get("operator_eligible"))
            and int(result.get("counts", {}).get("text", 0)) >= 2
        ):
            candidates.append(row)
    candidates.sort(
        key=lambda row: hashlib.sha256(
            f"{args.selection_seed}:{row['file_id']}".encode("utf-8")
        ).hexdigest()
    )

    inspector = CompanyCdrInspector()
    operator = SafeCorelOperator()
    payloads: list[dict[str, object]] = []
    for row in candidates:
        if len(payloads) >= args.limit:
            break
        source = Path(str(row["absolute_path"])).resolve()
        inspection = inspector.inspect(source, archive_root=archive_root)
        page_one_text = [
            item
            for item in inspection.objects
            if item.object_type == "text"
            and int(item.metadata.get("source_page", 1)) == 1
        ]
        if len(page_one_text) < 2:
            continue
        token = source_token(source, archive_root)
        control_id = f"{len(payloads) + 1:03d}"
        result = operator.execute(
            source_path=source,
            archive_root=archive_root,
            workspace=workspace,
            working_copy_path=workspace / "artifacts" / control_id / "working_copy.cdr",
            plan=build_ambiguous_text_control_plan(control_id=control_id),
            export_pdf=False,
        )
        payload = result.model_dump(mode="json")
        payloads.append(payload)
        print(f"[{len(payloads)}/{args.limit}] {token} {payload['result']}", flush=True)

    summary = summarize_ambiguity_controls(payloads)
    summary["expected_count"] = args.limit
    summary["selection_seed"] = args.selection_seed
    (workspace / "ambiguity_control_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["safely_refused"] == args.limit else 2


if __name__ == "__main__":
    raise SystemExit(main())
