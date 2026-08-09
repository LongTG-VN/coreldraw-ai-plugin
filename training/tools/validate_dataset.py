"""Validate every normalized JSONL record and its materialization metadata."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.datasets.validator import validate_dataset_directory


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate normalized design dataset files and metadata."
    )
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    report = validate_dataset_directory(args.dataset_dir)
    if args.write_report:
        report_path = args.dataset_dir / "validation_report.json"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report["report_path"] = str(report_path.resolve())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
