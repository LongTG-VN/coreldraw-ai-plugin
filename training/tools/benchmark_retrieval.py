"""Benchmark deterministic reference retrieval without loading the planner."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.retrieval import JsonlReferenceProvider, ReferenceRetriever, analyze_brief


def benchmark_retrieval(
    *, benchmark_path: Path, reference_index: Path, top_k: int
) -> dict[str, object]:
    config = json.loads(benchmark_path.read_text(encoding="utf-8"))
    retriever = ReferenceRetriever(JsonlReferenceProvider(reference_index))
    rows: list[dict[str, object]] = []
    for item in config["prompts"]:
        brief = analyze_brief(
            item["prompt"], width=item["width_mm"], height=item["height_mm"]
        )
        started = time.perf_counter()
        results = retriever.retrieve_references(brief, top_k=top_k)
        latency = time.perf_counter() - started
        categories = [result.summary.category for result in results]
        formats = [result.summary.format for result in results]
        compositions = [result.summary.composition for result in results]
        rows.append(
            {
                "prompt_id": item["id"],
                "expected_category": item["category"],
                "analyzed_category": brief.category,
                "analyzed_format": brief.format,
                "retrieved_ids": [result.reference_id for result in results],
                "top1_category_match": float(categories[0] == brief.category),
                "topk_category_match": float(brief.category in categories),
                "top1_format_match": float(formats[0] == brief.format),
                "topk_format_match": float(brief.format in formats),
                "average_relevance": statistics.mean(
                    float(result.match.relevance) for result in results
                ),
                "average_style_match": statistics.mean(
                    float(result.match.style) for result in results
                ),
                "average_aspect_match": statistics.mean(
                    float(result.match.aspect_ratio) for result in results
                ),
                "average_diversity": statistics.mean(
                    float(result.match.diversity) for result in results
                ),
                "composition_diversity": len(set(compositions)) / len(compositions),
                "latency_seconds": latency,
            }
        )
    average_keys = (
        "top1_category_match",
        "topk_category_match",
        "top1_format_match",
        "topk_format_match",
        "average_relevance",
        "average_style_match",
        "average_aspect_match",
        "average_diversity",
        "composition_diversity",
        "latency_seconds",
    )
    summary = {
        "benchmark_id": config["benchmark_id"],
        "prompt_count": len(rows),
        "top_k": top_k,
        **{
            key: statistics.mean(float(row[key]) for row in rows)
            for key in average_keys
        },
        "deterministic_retrieval": True,
        "rows": rows,
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--benchmark-config",
        type=Path,
        default=Path("training/config/benchmarks/design_v0_2.json"),
    )
    parser.add_argument("--reference-index", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"retrieval benchmark output exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = benchmark_retrieval(
        benchmark_path=args.benchmark_config,
        reference_index=args.reference_index,
        top_k=args.top_k,
    )
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
