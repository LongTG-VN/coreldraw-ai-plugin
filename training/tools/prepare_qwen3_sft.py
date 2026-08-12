"""Convert validated unified designs into compact Qwen3 SFT JSONL."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.adapters.qwen3_sft import Qwen3SFTAdapter
from training.experiments.qwen3_local import chat_token_ids, read_jsonl
from training.schemas.design import DesignDocument


def _percentile(values: list[int], percentile: float) -> int:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * percentile))
    return ordered[index]


def _token_stats(tokenizer: Any, records: list[dict[str, Any]]) -> dict[str, Any]:
    lengths = [len(chat_token_ids(tokenizer, record)[0]) for record in records]
    return {
        "min": min(lengths),
        "p50": _percentile(lengths, 0.50),
        "p90": _percentile(lengths, 0.90),
        "p95": _percentile(lengths, 0.95),
        "p99": _percentile(lengths, 0.99),
        "max": max(lengths),
        "mean": statistics.mean(lengths),
        "over_1024": sum(length > 1024 for length in lengths),
        "over_1536": sum(length > 1536 for length in lengths),
        "over_2048": sum(length > 2048 for length in lengths),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-elements", type=int, default=4)
    parser.add_argument("--model-id", default="Qwen/Qwen3-1.7B")
    parser.add_argument(
        "--revision",
        default="70d244cc86ccca08cf5af4e1e306ecf908b1ad5e",
    )
    args = parser.parse_args()

    adapter = Qwen3SFTAdapter(max_elements=args.max_elements)
    args.output.mkdir(parents=True, exist_ok=True)
    all_records: list[dict[str, Any]] = []
    split_counts: dict[str, int] = {}
    for split in ("train", "validation", "test"):
        documents = [
            DesignDocument.model_validate(record)
            for record in read_jsonl(args.input / f"{split}.jsonl")
        ]
        records = [adapter.convert(document).to_dict() for document in documents]
        split_counts[split] = len(records)
        all_records.extend(records)
        with (args.output / f"{split}.jsonl").open(
            "w", encoding="utf-8", newline="\n"
        ) as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        args.model_id,
        revision=args.revision,
    )
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(args.input.resolve()),
        "model_id": args.model_id,
        "model_revision": args.revision,
        "max_elements": args.max_elements,
        "splits": split_counts,
        "total": len(all_records),
        "license_class": "research_only",
        "commercial_allowed": False,
        "token_lengths": _token_stats(tokenizer, all_records),
    }
    (args.output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
