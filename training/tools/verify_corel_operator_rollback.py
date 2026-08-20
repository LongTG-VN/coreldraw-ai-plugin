"""Verify one real Corel transaction rollback on a generated CDR copy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.corel_operator.rollback import (
    verify_real_transaction_rollback,
    write_rollback_report,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--read-only-source", action="store_true", required=True)
    args = parser.parse_args()
    report = verify_real_transaction_rollback(
        source_path=args.source,
        archive_root=args.archive_root,
        workspace=args.workspace,
    )
    write_rollback_report(args.report, report)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
