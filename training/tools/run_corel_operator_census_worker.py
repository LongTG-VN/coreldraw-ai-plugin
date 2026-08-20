"""Single-file subprocess worker for the Corel operator census."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.corel_operator.census import OperatorCensusRunner


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    row = json.loads(args.request.read_text(encoding="utf-8"))
    runner = OperatorCensusRunner(
        archive_root=args.archive_root,
        workspace=args.workspace,
    )
    result = runner.run_one(row)
    args.response.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
