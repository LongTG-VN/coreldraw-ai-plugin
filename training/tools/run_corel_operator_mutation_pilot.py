"""Select and execute the 20-file safe mutation pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.company_archive.database import ArchiveDatabase
from training.corel_operator.pilot import MutationPilotRunner, select_mutation_pilot_rows
from training.corel_operator.state import OperatorStateDatabase


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--census-state", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    parser.add_argument("--selection-seed", default="corel-mutation-pilot-v1")
    parser.add_argument(
        "--planner-mode",
        choices=("auto", "font", "replace", "move", "resize"),
        default="auto",
    )
    parser.add_argument("--read-only-source", action="store_true", required=True)
    args = parser.parse_args()
    inventory = ArchiveDatabase(args.inventory)
    inventory_rows = inventory.rows("cdr_candidate=1")
    inventory_by_id = {str(row["file_id"]): row for row in inventory_rows}
    census = OperatorStateDatabase(args.census_state)
    selected = select_mutation_pilot_rows(
        census.census_rows(),
        inventory_by_id,
        limit=args.limit,
        seed=args.selection_seed,
    )
    runner = MutationPilotRunner(
        archive_root=args.archive_root,
        workspace=args.workspace,
        timeout_seconds=args.timeout_seconds,
        planner_mode=args.planner_mode,
    )
    summary = runner.run(selected)
    print(json.dumps(summary, indent=2))
    return 0 if summary["processed_count"] == len(selected) else 2


if __name__ == "__main__":
    raise SystemExit(main())
