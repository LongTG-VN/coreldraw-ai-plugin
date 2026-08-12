"""Explainable weighted retrieval with deterministic MMR diversity."""

from __future__ import annotations

import math
from dataclasses import dataclass

from training.retrieval.models import (
    ReferenceRecordV1,
    ReferenceRetrievalResultV1,
    RetrievalMatchV1,
    StructuredBriefV1,
)
from training.retrieval.providers import ReferenceProvider


class EmptyReferenceCorpusError(ValueError):
    pass


@dataclass(frozen=True)
class RetrievalWeights:
    category: float = 0.28
    format: float = 0.18
    style: float = 0.18
    aspect_ratio: float = 0.15
    density: float = 0.11
    colors: float = 0.10

    def __post_init__(self) -> None:
        if not math.isclose(sum(self.__dict__.values()), 1.0, abs_tol=1e-9):
            raise ValueError("retrieval weights must sum to 1")


def _jaccard(first: list[str], second: list[str]) -> float:
    left = {item.casefold() for item in first}
    right = {item.casefold() for item in second}
    if not left and not right:
        return 0.5
    return len(left & right) / len(left | right) if left | right else 0.0


def _aspect_similarity(first: float, second: float) -> float:
    return max(0.0, 1.0 - abs(math.log(max(first, 1e-9) / max(second, 1e-9))) / 1.5)


def _density_similarity(first: str, second: str) -> float:
    ranks = {"low": 0, "medium": 1, "high": 2}
    return max(0.0, 1.0 - abs(ranks[first] - ranks[second]) * 0.5)


def _matches(
    brief: StructuredBriefV1,
    record: ReferenceRecordV1,
    weights: RetrievalWeights,
) -> tuple[dict[str, float], float]:
    metadata = record.metadata
    values = {
        "category": 1.0 if metadata.category == brief.category else 0.0,
        "format": 1.0 if metadata.format == brief.format else 0.0,
        "style": _jaccard(brief.style, metadata.style_tags),
        "aspect_ratio": _aspect_similarity(float(brief.aspect_ratio), float(metadata.aspect_ratio)),
        "density": _density_similarity(brief.text_density, metadata.text_density),
        "colors": _jaccard(brief.colors, metadata.color_tags),
    }
    relevance = sum(values[key] * getattr(weights, key) for key in values)
    return values, relevance


def _record_similarity(first: ReferenceRecordV1, second: ReferenceRecordV1) -> float:
    a, b = first.features, second.features
    return (
        0.30 * (1.0 if a.composition == b.composition else 0.0)
        + 0.18 * (1.0 if a.dominant_alignment == b.dominant_alignment else 0.0)
        + 0.18 * _jaccard(first.metadata.style_tags, second.metadata.style_tags)
        + 0.14 * _aspect_similarity(float(a.aspect_ratio), float(b.aspect_ratio))
        + 0.10 * _density_similarity(a.text_density, b.text_density)
        + 0.10 * _jaccard(a.element_roles, b.element_roles)
    )


def score_reference(
    brief: StructuredBriefV1,
    record: ReferenceRecordV1,
    *,
    weights: RetrievalWeights | None = None,
) -> tuple[dict[str, float], float]:
    """Return explainable structural components without candidate hard-filtering."""

    return _matches(brief, record, weights or RetrievalWeights())


def reference_structural_similarity(
    first: ReferenceRecordV1,
    second: ReferenceRecordV1,
) -> float:
    return _record_similarity(first, second)


class ReferenceRetriever:
    def __init__(
        self,
        provider: ReferenceProvider,
        *,
        weights: RetrievalWeights | None = None,
        mmr_relevance: float = 0.72,
    ) -> None:
        if not 0 <= mmr_relevance <= 1:
            raise ValueError("mmr_relevance must be within [0, 1]")
        self.provider = provider
        self.weights = weights or RetrievalWeights()
        self.mmr_relevance = mmr_relevance

    def retrieve_references(
        self,
        brief: StructuredBriefV1,
        *,
        top_k: int = 5,
    ) -> list[ReferenceRetrievalResultV1]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        records = self.provider.load_references()
        if not records:
            raise EmptyReferenceCorpusError("reference corpus is empty")
        exact_category = [record for record in records if record.metadata.category == brief.category]
        exact_format = [record for record in records if record.metadata.format == brief.format]
        if exact_category:
            pool = exact_category
            fallback_reason = None
        elif exact_format:
            pool = exact_format
            fallback_reason = "no_matching_category_used_format"
        else:
            pool = records
            fallback_reason = "no_matching_category_or_format_used_global"

        scored: list[tuple[ReferenceRecordV1, dict[str, float], float]] = []
        for record in pool:
            match, relevance = _matches(brief, record, self.weights)
            scored.append((record, match, relevance))
        scored.sort(key=lambda item: (-item[2], item[0].metadata.reference_id))

        selected: list[tuple[ReferenceRecordV1, dict[str, float], float, float, float]] = []
        remaining = list(scored)
        while remaining and len(selected) < min(top_k, len(pool)):
            ranked: list[tuple[float, str, ReferenceRecordV1, dict[str, float], float, float]] = []
            for record, match, relevance in remaining:
                diversity = (
                    min(1.0 - _record_similarity(record, chosen[0]) for chosen in selected)
                    if selected
                    else 1.0
                )
                mmr_score = self.mmr_relevance * relevance + (1 - self.mmr_relevance) * diversity
                ranked.append((mmr_score, record.metadata.reference_id, record, match, relevance, diversity))
            ranked.sort(key=lambda item: (-item[0], item[1]))
            mmr_score, _, record, match, relevance, diversity = ranked[0]
            selected.append((record, match, relevance, diversity, mmr_score))
            remaining = [item for item in remaining if item[0].metadata.reference_id != record.metadata.reference_id]

        return [
            ReferenceRetrievalResultV1(
                reference_id=record.metadata.reference_id,
                score=max(0.0, min(1.0, mmr_score)),
                match=RetrievalMatchV1(
                    **match,
                    relevance=max(0.0, min(1.0, relevance)),
                    diversity=max(0.0, min(1.0, diversity)),
                ),
                summary=record.summary,
                metadata=record.metadata,
                fallback_reason=fallback_reason,
            )
            for record, match, relevance, diversity, mmr_score in selected
        ]


def retrieve_references(
    brief: StructuredBriefV1,
    *,
    provider: ReferenceProvider,
    top_k: int = 5,
) -> list[ReferenceRetrievalResultV1]:
    return ReferenceRetriever(provider).retrieve_references(brief, top_k=top_k)
