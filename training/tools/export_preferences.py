"""Export only explicit human A/B decisions from the local v0.4 review store."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.preference.v04.exporter import export_preferences
from training.preference.v04.store import ReviewStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("training/data/human_preferences/v0_4"))
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("training/data/human_preferences/v0_4/exports/latest"))
    parser.add_argument("--artifact-root", type=Path, action="append", required=True)
    args = parser.parse_args()
    store = ReviewStore(data_root=args.data_root, queue_path=args.queue, approved_roots=args.artifact_root)
    print(json.dumps(export_preferences(store, args.output), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
