"""Run/resume the deterministic real-CDR operator coverage census."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.company_archive.database import ArchiveDatabase
from training.corel_operator.census import OperatorCensusRunner, select_census_rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--seed", default="corel-operator-v1")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument("--read-only", action="store_true", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.limit < 1 or args.limit > 1000:
        raise SystemExit("--limit must be in 1..1000")
    inventory = ArchiveDatabase(args.inventory)
    selected = select_census_rows(
        inventory.rows("cdr_candidate=1"), limit=args.limit, seed=args.seed
    )
    runner = OperatorCensusRunner(
        archive_root=args.archive_root,
        workspace=args.workspace,
    )
    summary = runner.run_isolated(
        selected,
        timeout_seconds=args.timeout_seconds,
        retry_failures=args.retry_failures,
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["processed_count"] == len(selected) else 2


if __name__ == "__main__":
    raise SystemExit(main())
