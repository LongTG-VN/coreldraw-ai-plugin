"""Strict contracts for reference-grounded design retrieval."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


TextDensity = Literal["low", "medium", "high"]


class StrictRetrievalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class StructuredBriefV1(StrictRetrievalModel):
    schema_version: Literal["1.0"] = "1.0"
    prompt: str = Field(min_length=1, max_length=8_000)
    category: str = Field(min_length=1, max_length=100)
    format: str = Field(min_length=1, max_length=100)
    style: list[str] = Field(default_factory=list, max_length=12)
    colors: list[str] = Field(default_factory=list, max_length=12)
    text_density: TextDensity
    requested_elements: list[str] = Field(default_factory=list, max_length=30)
    aspect_ratio: FiniteFloat = Field(gt=0, le=100)
    analyzer: Literal["deterministic_rules", "fallback"]
    fallback_used: bool


class NormalizedElementFeatureV1(StrictRetrievalModel):
    element_id: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=100)
    element_type: str = Field(min_length=1, max_length=50)
    x: FiniteFloat = Field(ge=0, le=1)
    y: FiniteFloat = Field(ge=0, le=1)
    width: FiniteFloat = Field(gt=0, le=1)
    height: FiniteFloat = Field(gt=0, le=1)
    relative_size: FiniteFloat = Field(ge=0, le=1)
    region: str = Field(min_length=1, max_length=50)


class ReferenceFeaturesV1(StrictRetrievalModel):
    schema_version: Literal["1.0"] = "1.0"
    normalized_element_boxes: list[NormalizedElementFeatureV1] = Field(
        default_factory=list,
        max_length=10_000,
    )
    element_roles: list[str] = Field(default_factory=list)
    element_types: list[str] = Field(default_factory=list)
    element_count: int = Field(ge=0)
    text_count: int = Field(ge=0)
    image_count: int = Field(ge=0)
    dominant_alignment: Literal["left", "center", "right", "mixed"]
    margins: dict[str, FiniteFloat]
    vertical_rhythm: FiniteFloat = Field(ge=0, le=1)
    whitespace: FiniteFloat = Field(ge=0, le=1)
    overlap: FiniteFloat = Field(ge=0)
    size_hierarchy: FiniteFloat = Field(ge=1)
    headline_body_ratio: FiniteFloat = Field(ge=1)
    cta_position: str | None = None
    hero_position: str | None = None
    hero_coverage: FiniteFloat = Field(default=0, ge=0, le=1)
    composition: str = Field(min_length=1, max_length=100)
    composition_regions: dict[str, int]
    dominant_colors: list[str] = Field(default_factory=list, max_length=12)
    aspect_ratio: FiniteFloat = Field(gt=0, le=100)
    text_density: TextDensity
    text_area_ratio: FiniteFloat = Field(default=0, ge=0, le=1)
    decorative_area_ratio: FiniteFloat = Field(default=0, ge=0, le=1)
    background_luminance: FiniteFloat | None = Field(default=None, ge=0, le=1)
    visual_hierarchy: Literal["headline_dominant", "image_dominant", "balanced"] = (
        "balanced"
    )
    typography_intent: Literal[
        "display_heavy", "editorial", "minimal", "condensed", "premium", "balanced"
    ] = "balanced"
    visual_rhythm: Literal[
        "large_small_large", "stacked", "two_column", "grid", "balanced"
    ] = "balanced"


class ReferenceMetadataV1(StrictRetrievalModel):
    schema_version: Literal["1.0"] = "1.0"
    reference_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
    category: str = Field(min_length=1, max_length=100)
    format: str = Field(min_length=1, max_length=100)
    aspect_ratio: FiniteFloat = Field(gt=0, le=100)
    style_tags: list[str] = Field(default_factory=list, max_length=20)
    color_tags: list[str] = Field(default_factory=list, max_length=20)
    text_density: TextDensity
    element_count: int = Field(ge=0)
    layout_features: dict[str, Any] = Field(default_factory=dict)
    design_document_path: str = Field(min_length=1, max_length=4096)
    preview_path: str = Field(min_length=1, max_length=4096)
    source: str = Field(min_length=1, max_length=200)
    license: str = Field(min_length=1, max_length=200)
    license_class: str = Field(min_length=1, max_length=100)
    research_only: bool
    commercial_allowed: bool
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_license_flags(self) -> "ReferenceMetadataV1":
        if self.research_only and self.commercial_allowed:
            raise ValueError("research-only references cannot be commercial_allowed")
        return self


class HierarchySummaryItemV1(StrictRetrievalModel):
    role: str = Field(min_length=1, max_length=100)
    relative_size: FiniteFloat = Field(ge=0, le=1)
    region: str = Field(min_length=1, max_length=50)


class SpacingSummaryV1(StrictRetrievalModel):
    outer_margin: FiniteFloat = Field(ge=0, le=1)
    section_gap: FiniteFloat = Field(ge=0, le=1)


class PlacementSummaryV1(StrictRetrievalModel):
    region: str = Field(min_length=1, max_length=50)
    coverage: FiniteFloat | None = Field(default=None, ge=0, le=1)


class ReferenceDesignSummaryV1(StrictRetrievalModel):
    schema_version: Literal["1.0"] = "1.0"
    reference_id: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    format: str = Field(min_length=1, max_length=100)
    style: list[str] = Field(default_factory=list, max_length=12)
    palette: list[str] = Field(default_factory=list, max_length=8)
    composition: str = Field(min_length=1, max_length=100)
    alignment: Literal["left", "center", "right", "mixed"]
    hierarchy: list[HierarchySummaryItemV1] = Field(default_factory=list, max_length=8)
    spacing: SpacingSummaryV1
    hero: PlacementSummaryV1 | None = None
    cta: PlacementSummaryV1 | None = None
    text_density: TextDensity
    element_count: int = Field(ge=0)
    visual_hierarchy: Literal["headline_dominant", "image_dominant", "balanced"] = (
        "balanced"
    )
    hero_area_ratio: FiniteFloat = Field(default=0, ge=0, le=1)
    whitespace_ratio: FiniteFloat = Field(default=0, ge=0, le=1)
    text_area_ratio: FiniteFloat = Field(default=0, ge=0, le=1)
    decorative_area_ratio: FiniteFloat = Field(default=0, ge=0, le=1)
    typography_intent: Literal[
        "display_heavy", "editorial", "minimal", "condensed", "premium", "balanced"
    ] = "balanced"
    visual_rhythm: Literal[
        "large_small_large", "stacked", "two_column", "grid", "balanced"
    ] = "balanced"
    background_luminance: FiniteFloat | None = Field(default=None, ge=0, le=1)


class ReferenceRecordV1(StrictRetrievalModel):
    metadata: ReferenceMetadataV1
    features: ReferenceFeaturesV1
    summary: ReferenceDesignSummaryV1

    @model_validator(mode="after")
    def validate_record_identity(self) -> "ReferenceRecordV1":
        if self.metadata.reference_id != self.summary.reference_id:
            raise ValueError("metadata and summary reference_id disagree")
        return self


class RetrievalMatchV1(StrictRetrievalModel):
    category: FiniteFloat = Field(ge=0, le=1)
    format: FiniteFloat = Field(ge=0, le=1)
    style: FiniteFloat = Field(ge=0, le=1)
    aspect_ratio: FiniteFloat = Field(ge=0, le=1)
    density: FiniteFloat = Field(ge=0, le=1)
    colors: FiniteFloat = Field(ge=0, le=1)
    relevance: FiniteFloat = Field(ge=0, le=1)
    diversity: FiniteFloat = Field(ge=0, le=1)


class ReferenceRetrievalResultV1(StrictRetrievalModel):
    reference_id: str = Field(min_length=1, max_length=200)
    score: FiniteFloat = Field(ge=0, le=1)
    match: RetrievalMatchV1
    summary: ReferenceDesignSummaryV1
    metadata: ReferenceMetadataV1
    fallback_reason: str | None = None


class ReferenceContextV1(StrictRetrievalModel):
    schema_version: Literal["1.0"] = "1.0"
    instruction: str = Field(min_length=1, max_length=2_000)
    references: list[ReferenceDesignSummaryV1]
    estimated_tokens: int = Field(ge=0)
    truncated: bool


class HybridReferenceRetrievalResultV1(ReferenceRetrievalResultV1):
    structural_score: FiniteFloat = Field(ge=0, le=1)
    visual_text_score: FiniteFloat = Field(ge=0, le=1)
    visual_asset_score: FiniteFloat | None = Field(default=None, ge=0, le=1)
    hybrid_score: FiniteFloat = Field(ge=0, le=1)
    mmr_score: FiniteFloat = Field(ge=-1, le=1)
    visual_diversity: FiniteFloat = Field(ge=0, le=1)
    structural_diversity: FiniteFloat = Field(ge=0, le=1)
    source_diversity: FiniteFloat = Field(ge=0, le=1)
    embedding_model: str = Field(min_length=1, max_length=300)
    embedding_revision: str = Field(min_length=1, max_length=200)
    visual_index_id: str = Field(min_length=1, max_length=200)
    template_family: str = Field(min_length=1, max_length=300)
    excluded_leakage_candidates: list[dict[str, Any]] = Field(default_factory=list)
