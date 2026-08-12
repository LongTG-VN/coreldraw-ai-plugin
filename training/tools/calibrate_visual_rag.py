"""Calibrate hybrid fusion on development briefs excluded from final evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean

from training.retrieval import (
    HybridReferenceRetriever,
    HybridRetrievalWeights,
    JsonlReferenceProvider,
    TransformersSiglip2Embedder,
    VisualEmbeddingIndex,
    analyze_brief,
)


DEVELOPMENT_BRIEFS = [
    ("dev_wellness_brochure", "Brochure wellness cao cấp, tối giản, nhiều khoảng thở", 297, 210),
    ("dev_artisan_coffee_card", "Thẻ giới thiệu cà phê thủ công ấm áp, editorial", 180, 180),
    ("dev_botanical_skincare", "Ra mắt skincare thực vật sạch, premium, bố cục dọc", 210, 297),
    ("dev_vietnamese_food_board", "Bảng món Việt hiện đại, dễ đọc từ xa", 400, 180),
    ("dev_opening_invitation", "Thiệp mời khai trương tối giản, sang trọng", 210, 297),
]

CANDIDATES = [
    HybridRetrievalWeights(structural=.55, visual_text=.35, visual_asset=.10),
    HybridRetrievalWeights(structural=.45, visual_text=.40, visual_asset=.15),
    HybridRetrievalWeights(structural=.35, visual_text=.50, visual_asset=.15),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-index", type=Path, required=True)
    parser.add_argument("--visual-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    args = parser.parse_args()
    provider = JsonlReferenceProvider(args.reference_index.resolve())
    visual_index = VisualEmbeddingIndex(args.visual_index.resolve())
    embedder = TransformersSiglip2Embedder(
        model_id=visual_index.manifest.embedding_model,
        revision=visual_index.manifest.embedding_revision,
        device=args.device,
    )
    rows = []
    for weights in CANDIDATES:
        retriever = HybridReferenceRetriever(
            provider,
            visual_index=visual_index,
            embedder=embedder,
            weights=weights,
            mmr_lambda=.70,
        )
        cases = []
        for prompt_id, prompt, width, height in DEVELOPMENT_BRIEFS:
            results = retriever.retrieve_references(
                analyze_brief(prompt, width=width, height=height),
                top_k=5,
            )
            cases.append(
                {
                    "prompt_id": prompt_id,
                    "reference_ids": [item.reference_id for item in results],
                    "structural_relevance": mean(item.structural_score for item in results),
                    "visual_text_similarity": mean(item.visual_text_score for item in results),
                    "diversity": mean(item.match.diversity for item in results),
                    "source_diversity": mean(item.source_diversity for item in results),
                }
            )
        metrics = {
            key: mean(case[key] for case in cases)
            for key in (
                "structural_relevance",
                "visual_text_similarity",
                "diversity",
                "source_diversity",
            )
        }
        objective = (
            .35 * metrics["structural_relevance"]
            + .35 * metrics["visual_text_similarity"]
            + .20 * metrics["diversity"]
            + .10 * metrics["source_diversity"]
        )
        rows.append(
            {
                "weights": weights.__dict__,
                "metrics": metrics,
                "objective": objective,
                "cases": cases,
            }
        )
    rows.sort(
        key=lambda row: (
            -row["objective"],
            -row["weights"]["structural"],
        )
    )
    report = {
        "schema_version": "1.0",
        "final_evaluation_queries_used": False,
        "development_case_count": len(DEVELOPMENT_BRIEFS),
        "selection_objective": (
            "0.35 structural + 0.35 visual_text + 0.20 diversity + 0.10 source_diversity"
        ),
        "selected_weights": rows[0]["weights"],
        "candidates": rows,
        "model_load_seconds": embedder.load_duration_seconds,
        "peak_memory_gib": embedder.peak_memory_gib,
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
