"""Run one preselected real-CDR operation cohort without hiding outcomes."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from training.company_archive.database import ArchiveDatabase
from training.corel_operator.balanced import (
    BALANCED_OPERATION_MODES,
    select_targeted_rows,
)
from training.corel_operator.pilot import MutationPilotRunner
from training.corel_operator.state import OperatorStateDatabase


def summarize_targeted(payloads: list[dict[str, Any]], *, mode: str, seed: str) -> dict[str, Any]:
    counts = Counter(str(item.get("result")) for item in payloads)
    elapsed = sorted(
        float(item["elapsed_seconds"])
        for item in payloads
        if item.get("elapsed_seconds") is not None
    )
    return {
        "schema_version": "1.0",
        "operation_mode": mode,
        "selection_seed": seed,
        "planner_is_ai": False,
        "attempted": len(payloads),
        "auto_success": counts["AUTO_SUCCESS"],
        "success_with_warning": counts["SUCCESS_WITH_WARNING"],
        "needs_review": counts["NEEDS_REVIEW"],
        "unsupported": counts["UNSUPPORTED"],
        "failed": counts["FAILED"],
        "save_reopen_pass": sum(
            bool(item.get("editability_verified"))
            for item in payloads
            if item.get("result") in {"AUTO_SUCCESS", "SUCCESS_WITH_WARNING", "NEEDS_REVIEW"}
        ),
        "source_mutations": sum(
            not bool(item.get("source_unchanged")) for item in payloads
        ),
        "median_seconds": median(elapsed) if elapsed else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--census-state", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--operation-mode", choices=BALANCED_OPERATION_MODES, required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    parser.add_argument("--selection-seed", required=True)
    parser.add_argument("--read-only-source", action="store_true", required=True)
    args = parser.parse_args()

    inventory_rows = ArchiveDatabase(args.inventory).rows("cdr_candidate=1")
    inventory_by_id = {str(row["file_id"]): row for row in inventory_rows}
    selected = select_targeted_rows(
        OperatorStateDatabase(args.census_state).census_rows(),
        inventory_by_id,
        operation_mode=args.operation_mode,
        limit=args.limit,
        seed=args.selection_seed,
    )
    runner = MutationPilotRunner(
        archive_root=args.archive_root,
        workspace=args.workspace,
        timeout_seconds=args.timeout_seconds,
        planner_mode=args.operation_mode,
    )
    runner.run(selected)
    payloads = [
        row["result"]
        for row in OperatorStateDatabase(
            args.workspace / "mutation_pilot.sqlite"
        ).batch_rows("real-mutation-pilot-001")
    ]
    summary = summarize_targeted(
        payloads,
        mode=args.operation_mode,
        seed=args.selection_seed,
    )
    (args.workspace / "targeted_pilot_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["source_mutations"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
