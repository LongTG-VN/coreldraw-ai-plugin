"""Convert normalized JSONL splits into elem2design JSON arrays."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.adapters.elem2design import (
    to_elem2design_sample,
    validate_elem2design_sample,
)
from training.schemas.design import DesignDocument


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a layout-only elem2design adapter dry run."
    )
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for split in ("train", "validation", "test"):
        records: list[dict] = []
        input_path = args.dataset_dir / f"{split}.jsonl"
        with input_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                document = DesignDocument.model_validate_json(line)
                sample = to_elem2design_sample(document)
                validate_elem2design_sample(sample)
                records.append(sample)
        (args.output_dir / f"{split}.json").write_text(
            json.dumps(records, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        counts[split] = len(records)

    metadata = {
        "status": "layout_only_dry_run",
        "training_ready": False,
        "reason": "Four intermediate rendered images per sample are not generated yet.",
        "source": str(args.dataset_dir.resolve()),
        "counts": counts,
        "format": "elem2design ten-message layered conversation",
    }
    metadata_path = args.output_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({**metadata, "output": str(args.output_dir.resolve())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
