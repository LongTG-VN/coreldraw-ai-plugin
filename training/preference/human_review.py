"""Validate real human reviews and export v0.4-ready preference pairs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from training.schemas.design import DesignDocument


class StrictPreferenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReviewDimensionScoresV1(StrictPreferenceModel):
    overall: int = Field(ge=1, le=10)
    hierarchy: int = Field(ge=1, le=10)
    typography: int = Field(ge=1, le=10)
    composition: int = Field(ge=1, le=10)


class HumanReviewProvenanceV1(StrictPreferenceModel):
    human_reviewed: Literal[True]
    selection_source: Literal["human"]
    heuristic_metrics_are_human_scores: Literal[False] = False


class CompletedHumanReviewV1(StrictPreferenceModel):
    schema_version: Literal["1.0"] = "1.0"
    artifact_type: Literal["manual_design_review_template"]
    prompt_id: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=4_000)
    review_status: Literal["completed"]
    preferred: str = Field(min_length=1, max_length=100)
    scores: dict[str, ReviewDimensionScoresV1]
    reviewer: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=4_000)
    provenance: HumanReviewProvenanceV1

    @model_validator(mode="after")
    def validate_variants(self) -> "CompletedHumanReviewV1":
        if len(self.scores) != 2:
            raise ValueError("human comparison must score exactly two variants")
        if self.preferred not in self.scores:
            raise ValueError("preferred variant is missing from scores")
        return self


class HumanPreferenceSourceV1(StrictPreferenceModel):
    reviewer: str
    notes: str | None = None
    review_dimensions: list[str] = Field(
        default_factory=lambda: ["overall", "hierarchy", "typography", "composition"]
    )
    source_review: str
    source_comparison: str


class PreferencePairV1(StrictPreferenceModel):
    schema_version: Literal["1.0"] = "1.0"
    pair_id: str = Field(pattern=r"^human:[a-f0-9]{24}$")
    prompt_id: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=4_000)
    context_reference_ids: list[str] = Field(default_factory=list, max_length=20)
    chosen_variant: str
    rejected_variant: str
    chosen_design: DesignDocument
    rejected_design: DesignDocument
    chosen_preview: str = Field(min_length=1, max_length=4096)
    rejected_preview: str = Field(min_length=1, max_length=4096)
    scores: dict[str, ReviewDimensionScoresV1]
    human_source: HumanPreferenceSourceV1
    provenance: dict[str, Any]
    license_class: str = Field(min_length=1, max_length=100)
    research_only: bool
    commercial_allowed: bool

    @model_validator(mode="after")
    def validate_pair(self) -> "PreferencePairV1":
        if self.chosen_variant == self.rejected_variant:
            raise ValueError("chosen and rejected variants must differ")
        if {self.chosen_variant, self.rejected_variant} != set(self.scores):
            raise ValueError("pair variants must match review score variants")
        if self.research_only and self.commercial_allowed:
            raise ValueError("research-only preference pairs cannot be commercial")
        return self


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _required_path(value: Any, *, field: str, suffix: str | None = None) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{field} does not exist: {path}")
    if suffix is not None and path.suffix.casefold() != suffix:
        raise ValueError(f"{field} must be a {suffix} file")
    return path


def build_preference_pair(
    *,
    review_path: Path,
    comparison_path: Path,
) -> PreferencePairV1:
    """Build a pair only from explicit completed human input."""

    review_path = review_path.resolve()
    comparison_path = comparison_path.resolve()
    review = CompletedHumanReviewV1.model_validate(_read_json(review_path))
    comparison = _read_json(comparison_path)
    if not isinstance(comparison, dict):
        raise ValueError("comparison JSON root must be an object")
    if comparison.get("prompt_id") != review.prompt_id or comparison.get("prompt") != review.prompt:
        raise ValueError("review prompt identity does not match comparison")
    variants = comparison.get("variants")
    if not isinstance(variants, dict) or set(variants) != set(review.scores):
        raise ValueError("review variants do not match comparison variants")
    chosen_key = review.preferred
    rejected_key = next(key for key in review.scores if key != chosen_key)

    def load_variant(key: str) -> tuple[DesignDocument, Path]:
        payload = variants[key]
        if not isinstance(payload, dict):
            raise ValueError(f"comparison variant {key} must be an object")
        design_path = _required_path(payload.get("design_path"), field=f"{key}.design_path", suffix=".json")
        preview_path = _required_path(payload.get("preview_path"), field=f"{key}.preview_path", suffix=".png")
        return DesignDocument.model_validate(_read_json(design_path)), preview_path

    chosen_design, chosen_preview = load_variant(chosen_key)
    rejected_design, rejected_preview = load_variant(rejected_key)
    commercial_allowed = bool(
        chosen_design.source.commercial_allowed and rejected_design.source.commercial_allowed
    )
    research_only = not commercial_allowed
    license_classes = {
        chosen_design.source.license_class,
        rejected_design.source.license_class,
    }
    license_class = (
        next(iter(license_classes)) if len(license_classes) == 1 else "mixed_research_only"
    )
    reference_ids = [
        str(item["reference_id"])
        for item in comparison.get("retrieved_references", [])
        if isinstance(item, dict) and item.get("reference_id")
    ]
    identity = "|".join(
        (
            review.prompt_id,
            review.reviewer,
            chosen_key,
            rejected_key,
            chosen_design.sample_id,
            rejected_design.sample_id,
        )
    )
    pair_id = "human:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return PreferencePairV1(
        pair_id=pair_id,
        prompt_id=review.prompt_id,
        prompt=review.prompt,
        context_reference_ids=reference_ids,
        chosen_variant=chosen_key,
        rejected_variant=rejected_key,
        chosen_design=chosen_design,
        rejected_design=rejected_design,
        chosen_preview=str(chosen_preview),
        rejected_preview=str(rejected_preview),
        scores=review.scores,
        human_source=HumanPreferenceSourceV1(
            reviewer=review.reviewer,
            notes=review.notes,
            source_review=str(review_path),
            source_comparison=str(comparison_path),
        ),
        provenance={
            "preference_type": "human_preference",
            "human_approved": True,
            "heuristic_selection_used_as_human_preference": False,
            "comparison_artifact_type": comparison.get("artifact_type"),
        },
        license_class=license_class,
        research_only=research_only,
        commercial_allowed=commercial_allowed,
    )


def export_preference_pair(
    *,
    review_path: Path,
    comparison_path: Path,
    output_path: Path,
) -> Path:
    pair = build_preference_pair(
        review_path=review_path,
        comparison_path=comparison_path,
    )
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        pair.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


__all__ = [
    "CompletedHumanReviewV1",
    "PreferencePairV1",
    "ReviewDimensionScoresV1",
    "build_preference_pair",
    "export_preference_pair",
]
