"""Stream and materialize a bounded normalized research dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.adapters.genposter import GenPosterAdapter
from training.datasets.builder import materialize_dataset
from training.tools.bootstrap import CONFIG_PATH, REPO_ROOT, load_registry


def stream_rows(source_config: dict[str, Any]) -> Iterable[dict[str, Any]]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError(
            "Missing bootstrap dependency. Install training/requirements.txt"
        ) from exc
    return load_dataset(
        source_config["dataset_id"],
        split=source_config.get("split", "train"),
        streaming=True,
    ).decode(False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a validated <=500-sample normalized research dataset."
    )
    parser.add_argument("--source", choices=("genposter100k",), required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 500:
        parser.error("--limit must be between 1 and 500")

    registry = load_registry(CONFIG_PATH)
    source_config = registry["sources"][args.source]
    if source_config.get("commercial_allowed"):
        raise RuntimeError("GenPoster build must remain research-only")
    output = args.output or (
        REPO_ROOT / "training" / "data" / "research" / "genposter_smoke"
    )
    result = materialize_dataset(
        stream_rows(source_config),
        GenPosterAdapter(split=str(source_config.get("split", "train"))),
        output,
        limit=args.limit,
        seed=args.seed,
    )
    print(
        json.dumps(
            {
                "source": args.source,
                "license_class": source_config["license_class"],
                "commercial_allowed": False,
                "total": result.total,
                "splits": result.split_counts,
                "output": str(result.output_dir),
                "metadata": str(result.metadata_path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
