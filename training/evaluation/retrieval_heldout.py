"""Honest retrieval evaluation without exact-category project-template leakage."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any, Literal

from training.retrieval import ReferenceRetriever, analyze_brief
from training.retrieval.models import ReferenceRecordV1
from training.retrieval.providers import ReferenceProvider


HeldOutMode = Literal[
    "full_corpus",
    "exclude_exact_category_owned_templates",
    "genposter_only",
]


class _MemoryProvider:
    provider_name = "held_out_memory"

    def __init__(self, records: list[ReferenceRecordV1]) -> None:
        self.records = records

    def load_references(self) -> list[ReferenceRecordV1]:
        return list(self.records)


@dataclass(frozen=True)
class RetrievalBenchmarkCase:
    prompt_id: str
    prompt: str
    width: float
    height: float
    expected_category: str
    expected_format: str | None = None


def _pool(
    records: list[ReferenceRecordV1],
    *,
    mode: HeldOutMode,
    category: str,
) -> list[ReferenceRecordV1]:
    if mode == "full_corpus":
        return list(records)
    if mode == "genposter_only":
        return [record for record in records if record.metadata.source == "genposter100k"]
    return [
        record
        for record in records
        if not (
            record.metadata.source == "synthetic_owned"
            and record.metadata.category == category
        )
    ]


def evaluate_retrieval_mode(
    provider: ReferenceProvider,
    cases: list[RetrievalBenchmarkCase],
    *,
    mode: HeldOutMode,
    top_k: int = 5,
) -> dict[str, Any]:
    if not cases:
        raise ValueError("retrieval benchmark requires at least one case")
    records = provider.load_references()
    if not records:
        raise ValueError("reference corpus is empty")
    rows: list[dict[str, Any]] = []
    for case in cases:
        brief = analyze_brief(case.prompt, width=case.width, height=case.height)
        pool = _pool(records, mode=mode, category=brief.category)
        if not pool:
            raise ValueError(f"held-out pool is empty for {case.prompt_id} in {mode}")
        results = ReferenceRetriever(_MemoryProvider(pool)).retrieve_references(
            brief,
            top_k=min(top_k, len(pool)),
        )
        first = results[0]
        expected_format = case.expected_format or brief.format
        rows.append(
            {
                "prompt_id": case.prompt_id,
                "expected_category": case.expected_category,
                "analyzed_category": brief.category,
                "expected_format": expected_format,
                "pool_size": len(pool),
                "reference_ids": [item.reference_id for item in results],
                "top1_category": first.metadata.category,
                "top1_format": first.metadata.format,
                "top1_category_match": float(first.metadata.category == case.expected_category),
                "top1_format_match": float(first.metadata.format == expected_format),
                "average_relevance": mean(float(item.match.relevance) for item in results),
                "average_diversity": mean(float(item.match.diversity) for item in results),
                "average_structural_match": mean(
                    mean(
                        (
                            float(item.match.style),
                            float(item.match.aspect_ratio),
                            float(item.match.density),
                        )
                    )
                    for item in results
                ),
                "fallback_used": any(item.fallback_reason is not None for item in results),
                "sources": sorted({item.metadata.source for item in results}),
            }
        )
    return {
        "schema_version": "1.0",
        "mode": mode,
        "case_count": len(rows),
        "top_k": top_k,
        "category_accuracy": mean(row["top1_category_match"] for row in rows),
        "format_accuracy": mean(row["top1_format_match"] for row in rows),
        "relevance": mean(row["average_relevance"] for row in rows),
        "diversity": mean(row["average_diversity"] for row in rows),
        "structural_match": mean(row["average_structural_match"] for row in rows),
        "fallback_rate": mean(float(row["fallback_used"]) for row in rows),
        "interpretation": (
            "Full-corpus routing includes benchmark-aligned project templates."
            if mode == "full_corpus"
            else "Held-out result; exact-category project templates are not available."
        ),
        "rows": rows,
    }


def evaluate_retrieval_heldout(
    provider: ReferenceProvider,
    cases: list[RetrievalBenchmarkCase],
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "benchmark": "reference_retrieval_heldout_v1",
        "human_aesthetic_judgment": False,
        "modes": {
            mode: evaluate_retrieval_mode(provider, cases, mode=mode, top_k=top_k)
            for mode in (
                "full_corpus",
                "exclude_exact_category_owned_templates",
                "genposter_only",
            )
        },
    }


__all__ = [
    "RetrievalBenchmarkCase",
    "evaluate_retrieval_heldout",
    "evaluate_retrieval_mode",
]
