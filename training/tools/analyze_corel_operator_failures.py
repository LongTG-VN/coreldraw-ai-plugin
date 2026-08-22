"""Write a sanitized root-cause report for a completed operator run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.corel_operator.failure_analysis import build_failure_analysis
from training.corel_operator.state import OperatorStateDatabase


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--run-id", default="real-mutation-pilot-001")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = OperatorStateDatabase(args.state).batch_rows(args.run_id)
    report = build_failure_analysis([row["result"] for row in rows])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
