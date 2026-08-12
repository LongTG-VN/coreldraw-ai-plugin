"""Run the real local Qwen3 QLoRA smoke experiment."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.experiments.qwen3_local import read_jsonl, train_qlora


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    records = read_jsonl(args.dataset / "train.jsonl")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    dataset_metadata = json.loads(
        (args.dataset / "metadata.json").read_text(encoding="utf-8")
    )
    (args.output / "dataset.json").write_text(
        json.dumps(dataset_metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    packages = {}
    for name in ("torch", "transformers", "peft", "accelerate", "bitsandbytes"):
        packages[name] = importlib.metadata.version(name)
    environment = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "packages": packages,
    }
    (args.output / "environment.json").write_text(
        json.dumps(environment, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    metrics = train_qlora(config=config, records=records, output_dir=args.output)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
