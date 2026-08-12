"""Hybrid structural + image/text retrieval with visual MMR and leakage gates."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any

from training.retrieval.engine import (
    RetrievalWeights,
    reference_structural_similarity,
    score_reference,
)
from training.retrieval.models import (
    HybridReferenceRetrievalResultV1,
    ReferenceRecordV1,
    RetrievalMatchV1,
    StructuredBriefV1,
)
from training.retrieval.providers import ReferenceProvider
from training.retrieval.visual_embeddings import (
    VisualEmbedder,
    cosine_similarity,
    normalize_embedding,
    sha256_file,
)
from training.retrieval.visual_index import VisualEmbeddingIndex


@dataclass(frozen=True)
class HybridRetrievalWeights:
    structural: float = .45
    visual_text: float = .40
    visual_asset: float = .15

    def __post_init__(self) -> None:
        if any(value < 0 for value in self.__dict__.values()):
            raise ValueError("hybrid retrieval weights cannot be negative")
        if not math.isclose(sum(self.__dict__.values()), 1.0, abs_tol=1e-9):
            raise ValueError("hybrid retrieval weights must sum to one")

    def effective(self, *, has_asset: bool) -> dict[str, float]:
        values = {
            "structural": self.structural,
            "visual_text": self.visual_text,
            "visual_asset": self.visual_asset if has_asset else 0.0,
        }
        total = sum(values.values())
        return {key: value / total for key, value in values.items()}


@dataclass(frozen=True)
class RetrievalLeakageExclusions:
    reference_ids: frozenset[str] = frozenset()
    source_ids: frozenset[str] = frozenset()
    template_families: frozenset[str] = frozenset()
    preview_sha256s: frozenset[str] = frozenset()
    near_duplicate_threshold: float = .985

    def __post_init__(self) -> None:
        if not -1 <= self.near_duplicate_threshold <= 1:
            raise ValueError("near duplicate threshold must be within [-1, 1]")


@dataclass(frozen=True)
class HybridRetrievalDiagnostics:
    query_mode: str
    embedding_latency_seconds: float
    retrieval_latency_seconds: float
    candidate_count: int
    excluded: tuple[dict[str, Any], ...]
    near_duplicate_rejection_count: int
    effective_weights: dict[str, float]
    visual_index_id: str


def _mapped_cosine(value: float) -> float:
    return max(0.0, min(1.0, (value + 1.0) / 2.0))


def _mean_vector(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        raise ValueError("cannot average an empty embedding list")
    dimension = len(vectors[0])
    if any(len(vector) != dimension for vector in vectors):
        raise ValueError("asset embedding dimensions disagree")
    return normalize_embedding(
        [mean(vector[index] for vector in vectors) for index in range(dimension)]
    )


def visual_query_text(brief: StructuredBriefV1) -> str:
    style = ", ".join(brief.style) or "balanced"
    colors = ", ".join(brief.colors) or "category appropriate"
    return (
        f"{brief.prompt}. Design reference for {brief.format}; category {brief.category}; "
        f"style {style}; colors {colors}; text density {brief.text_density}; "
        f"aspect ratio {float(brief.aspect_ratio):.3f}."
    )


class HybridReferenceRetriever:
    """Rank the global corpus; category is a score feature, never a pool gate."""

    def __init__(
        self,
        provider: ReferenceProvider,
        *,
        visual_index: VisualEmbeddingIndex,
        embedder: VisualEmbedder,
        weights: HybridRetrievalWeights | None = None,
        structural_weights: RetrievalWeights | None = None,
        mmr_lambda: float = .70,
    ) -> None:
        if not 0 <= mmr_lambda <= 1:
            raise ValueError("mmr_lambda must be within [0, 1]")
        if embedder.model_id != visual_index.manifest.embedding_model:
            raise ValueError("embedder model does not match visual index")
        if embedder.revision != visual_index.manifest.embedding_revision:
            raise ValueError("embedder revision does not match visual index")
        if embedder.dimension != visual_index.manifest.dimension:
            raise ValueError("embedder dimension does not match visual index")
        self.provider = provider
        self.visual_index = visual_index
        self.embedder = embedder
        self.weights = weights or HybridRetrievalWeights()
        self.structural_weights = structural_weights or RetrievalWeights()
        self.mmr_lambda = mmr_lambda
        self.last_diagnostics: HybridRetrievalDiagnostics | None = None

    def retrieve_references(
        self,
        brief: StructuredBriefV1,
        *,
        top_k: int = 5,
        asset_paths: list[Path] | None = None,
        exclusions: RetrievalLeakageExclusions | None = None,
    ) -> list[HybridReferenceRetrievalResultV1]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        started = time.perf_counter()
        records = self.provider.load_references()
        if not records:
            raise ValueError("reference corpus is empty")
        by_id = {record.metadata.reference_id: record for record in records}
        if len(by_id) != len(records):
            raise ValueError("structural corpus contains duplicate reference IDs")
        embedding_started = time.perf_counter()
        text_vector = normalize_embedding(self.embedder.embed_text(visual_query_text(brief)))
        resolved_assets = [path.resolve() for path in (asset_paths or [])]
        for path in resolved_assets:
            if not path.is_file():
                raise FileNotFoundError(f"hybrid query asset missing: {path}")
        asset_vector = (
            _mean_vector(self.embedder.embed_images(resolved_assets))
            if resolved_assets
            else None
        )
        embedding_latency = time.perf_counter() - embedding_started
        exclusion = exclusions or RetrievalLeakageExclusions()
        excluded: list[dict[str, Any]] = []
        near_duplicate_count = 0
        scored: list[dict[str, Any]] = []
        effective = self.weights.effective(has_asset=asset_vector is not None)
        for visual_record, visual_vector in zip(
            self.visual_index.records,
            self.visual_index.vectors,
        ):
            record = by_id.get(visual_record.reference_id)
            if record is None:
                continue
            reasons = []
            if visual_record.reference_id in exclusion.reference_ids:
                reasons.append("reference_id")
            if visual_record.source_id in exclusion.source_ids:
                reasons.append("source_id")
            if visual_record.template_family in exclusion.template_families:
                reasons.append("template_family")
            if visual_record.preview_sha256 in exclusion.preview_sha256s:
                reasons.append("preview_sha256")
            asset_cosine = (
                cosine_similarity(asset_vector, visual_vector)
                if asset_vector is not None
                else None
            )
            if (
                asset_cosine is not None
                and asset_cosine >= exclusion.near_duplicate_threshold
            ):
                reasons.append("near_duplicate_embedding")
                near_duplicate_count += 1
            if reasons:
                excluded.append(
                    {"reference_id": visual_record.reference_id, "reasons": reasons}
                )
                continue
            match, structural = score_reference(
                brief,
                record,
                weights=self.structural_weights,
            )
            visual_text = _mapped_cosine(cosine_similarity(text_vector, visual_vector))
            visual_asset = _mapped_cosine(asset_cosine) if asset_cosine is not None else None
            hybrid = (
                effective["structural"] * structural
                + effective["visual_text"] * visual_text
                + effective["visual_asset"] * (visual_asset or 0.0)
            )
            scored.append(
                {
                    "record": record,
                    "visual_record": visual_record,
                    "vector": visual_vector,
                    "match": match,
                    "structural": structural,
                    "visual_text": visual_text,
                    "visual_asset": visual_asset,
                    "hybrid": hybrid,
                }
            )
        if not scored:
            raise ValueError("all hybrid retrieval candidates were excluded")
        selected: list[dict[str, Any]] = []
        remaining = list(scored)
        while remaining and len(selected) < min(top_k, len(remaining) + len(selected)):
            ranked = []
            for candidate in remaining:
                if selected:
                    similarities = []
                    for chosen in selected:
                        visual_similarity = _mapped_cosine(
                            cosine_similarity(candidate["vector"], chosen["vector"])
                        )
                        structural_similarity = reference_structural_similarity(
                            candidate["record"], chosen["record"]
                        )
                        same_family = float(
                            candidate["visual_record"].template_family
                            == chosen["visual_record"].template_family
                        )
                        same_source = float(
                            candidate["visual_record"].source
                            == chosen["visual_record"].source
                        )
                        similarities.append(
                            .55 * visual_similarity
                            + .30 * structural_similarity
                            + .10 * same_family
                            + .05 * same_source
                        )
                    max_similarity = max(similarities)
                    visual_diversity = min(
                        1.0 - _mapped_cosine(
                            cosine_similarity(candidate["vector"], chosen["vector"])
                        )
                        for chosen in selected
                    )
                    structural_diversity = min(
                        1.0
                        - reference_structural_similarity(
                            candidate["record"], chosen["record"]
                        )
                        for chosen in selected
                    )
                    source_diversity = min(
                        float(
                            candidate["visual_record"].source
                            != chosen["visual_record"].source
                        )
                        for chosen in selected
                    )
                else:
                    max_similarity = 0.0
                    visual_diversity = structural_diversity = source_diversity = 1.0
                mmr = self.mmr_lambda * candidate["hybrid"] - (
                    1.0 - self.mmr_lambda
                ) * max_similarity
                ranked.append(
                    (
                        mmr,
                        candidate["visual_record"].reference_id,
                        candidate,
                        visual_diversity,
                        structural_diversity,
                        source_diversity,
                    )
                )
            ranked.sort(key=lambda item: (-item[0], item[1]))
            mmr, _, winner, visual_diversity, structural_diversity, source_diversity = ranked[0]
            winner.update(
                {
                    "mmr": mmr,
                    "visual_diversity": visual_diversity,
                    "structural_diversity": structural_diversity,
                    "source_diversity": source_diversity,
                }
            )
            selected.append(winner)
            remaining = [
                item
                for item in remaining
                if item["visual_record"].reference_id
                != winner["visual_record"].reference_id
            ]
        elapsed = time.perf_counter() - started
        self.last_diagnostics = HybridRetrievalDiagnostics(
            query_mode="brief_plus_asset" if asset_vector is not None else "brief_only",
            embedding_latency_seconds=embedding_latency,
            retrieval_latency_seconds=elapsed,
            candidate_count=len(scored),
            excluded=tuple(excluded),
            near_duplicate_rejection_count=near_duplicate_count,
            effective_weights=effective,
            visual_index_id=self.visual_index.manifest.visual_index_id,
        )
        return [
            HybridReferenceRetrievalResultV1(
                reference_id=item["record"].metadata.reference_id,
                score=max(0.0, min(1.0, item["hybrid"])),
                match=RetrievalMatchV1(
                    **item["match"],
                    relevance=max(0.0, min(1.0, item["structural"])),
                    diversity=max(
                        0.0,
                        min(
                            1.0,
                            mean(
                                (
                                    item["visual_diversity"],
                                    item["structural_diversity"],
                                    item["source_diversity"],
                                )
                            ),
                        ),
                    ),
                ),
                summary=item["visual_record"].summary,
                metadata=item["record"].metadata,
                structural_score=max(0.0, min(1.0, item["structural"])),
                visual_text_score=item["visual_text"],
                visual_asset_score=item["visual_asset"],
                hybrid_score=max(0.0, min(1.0, item["hybrid"])),
                mmr_score=max(-1.0, min(1.0, item["mmr"])),
                visual_diversity=item["visual_diversity"],
                structural_diversity=item["structural_diversity"],
                source_diversity=item["source_diversity"],
                embedding_model=self.embedder.model_id,
                embedding_revision=self.embedder.revision,
                visual_index_id=self.visual_index.manifest.visual_index_id,
                template_family=item["visual_record"].template_family,
                excluded_leakage_candidates=excluded,
            )
            for item in selected
        ]


@dataclass
class BoundHybridReferenceRetriever:
    """Bind one runtime request's assets/exclusions to the pipeline interface."""

    retriever: HybridReferenceRetriever
    asset_paths: list[Path] = field(default_factory=list)
    exclusions: RetrievalLeakageExclusions = field(default_factory=RetrievalLeakageExclusions)

    def retrieve_references(
        self,
        brief: StructuredBriefV1,
        *,
        top_k: int = 5,
    ) -> list[HybridReferenceRetrievalResultV1]:
        return self.retriever.retrieve_references(
            brief,
            top_k=top_k,
            asset_paths=self.asset_paths,
            exclusions=self.exclusions,
        )


__all__ = [
    "BoundHybridReferenceRetriever",
    "HybridReferenceRetriever",
    "HybridRetrievalDiagnostics",
    "HybridRetrievalWeights",
    "RetrievalLeakageExclusions",
    "visual_query_text",
]
