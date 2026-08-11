"""Run full and leakage-reduced retrieval benchmarks without model generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.evaluation.retrieval_heldout import (
    RetrievalBenchmarkCase,
    evaluate_retrieval_heldout,
)
from training.retrieval import JsonlReferenceProvider, analyze_brief


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def run(
    *,
    reference_index: Path,
    benchmark_config: Path,
    output: Path,
    top_k: int,
) -> dict:
    config = _read_json(benchmark_config.resolve())
    cases = []
    for row in config["prompts"]:
        brief = analyze_brief(
            row["prompt"],
            width=float(row["width_mm"]),
            height=float(row["height_mm"]),
        )
        cases.append(
            RetrievalBenchmarkCase(
                prompt_id=row["id"],
                prompt=row["prompt"],
                width=float(row["width_mm"]),
                height=float(row["height_mm"]),
                expected_category=brief.category,
                expected_format=brief.format,
            )
        )
    report = evaluate_retrieval_heldout(
        JsonlReferenceProvider(reference_index.resolve()),
        cases,
        top_k=top_k,
    )
    report.update(
        {
            "reference_index": str(reference_index.resolve()),
            "benchmark_config": str(benchmark_config.resolve()),
        }
    )
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-index", required=True, type=Path)
    parser.add_argument(
        "--benchmark-config",
        type=Path,
        default=Path("training/config/benchmarks/design_v0_2.json"),
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    report = run(
        reference_index=args.reference_index,
        benchmark_config=args.benchmark_config,
        output=args.output,
        top_k=args.top_k,
    )
    compact = {
        mode: {
            key: value
            for key, value in result.items()
            if key in {"category_accuracy", "format_accuracy", "relevance", "diversity", "structural_match", "fallback_rate"}
        }
        for mode, result in report["modes"].items()
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
