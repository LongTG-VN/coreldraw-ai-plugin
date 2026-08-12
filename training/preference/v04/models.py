"""Strict contracts for blinded, explicit human preference collection."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$"
SHA256_PATTERN = r"^[a-f0-9]{64}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OptionalReviewScoresV1(StrictModel):
    composition: int | None = Field(default=None, ge=1, le=10)
    hierarchy: int | None = Field(default=None, ge=1, le=10)
    typography: int | None = Field(default=None, ge=1, le=10)
    brand_feeling: int | None = Field(default=None, ge=1, le=10)
    overall: int | None = Field(default=None, ge=1, le=10)


class CandidateArtifactV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    design_id: str = Field(pattern=ID_PATTERN)
    brief_id: str = Field(pattern=ID_PATTERN)
    design_path: str = Field(min_length=1, max_length=4096)
    preview_path: str = Field(min_length=1, max_length=4096)
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    generation_source: str = Field(min_length=1, max_length=200)
    technically_eligible: Literal[True]
    provenance: dict[str, Any]
    license_class: str = Field(min_length=1, max_length=100)
    commercial_allowed: bool


class ReviewQueueItemV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    pair_id: str = Field(pattern=r"^pair:[a-f0-9]{24}$")
    brief_id: str = Field(pattern=ID_PATTERN)
    prompt: str = Field(min_length=1, max_length=4000)
    category: str = Field(min_length=1, max_length=100)
    candidate_1: CandidateArtifactV1
    candidate_2: CandidateArtifactV1
    pairing_stage: Literal["opening", "cross", "historical"] = "opening"
    benchmark_sample_data: bool = False
    customer_provided: bool = False
    provenance: dict[str, Any]
    license_class: str = Field(min_length=1, max_length=100)
    commercial_allowed: bool

    @model_validator(mode="after")
    def validate_pair(self) -> "ReviewQueueItemV1":
        if self.candidate_1.design_id == self.candidate_2.design_id:
            raise ValueError("a review pair requires two different designs")
        if self.candidate_1.content_sha256 == self.candidate_2.content_sha256:
            raise ValueError("a review pair cannot compare identical content")
        if self.candidate_1.brief_id != self.brief_id or self.candidate_2.brief_id != self.brief_id:
            raise ValueError("candidate brief identity does not match queue item")
        if self.commercial_allowed and not (
            self.candidate_1.commercial_allowed and self.candidate_2.commercial_allowed
        ):
            raise ValueError("pair cannot upgrade candidate commercial permission")
        return self


class BlindMappingV1(StrictModel):
    design_a_id: str = Field(pattern=ID_PATTERN)
    design_b_id: str = Field(pattern=ID_PATTERN)

    @model_validator(mode="after")
    def distinct(self) -> "BlindMappingV1":
        if self.design_a_id == self.design_b_id:
            raise ValueError("blind mapping sides must differ")
        return self


class ReviewSessionV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    session_id: str = Field(pattern=r"^session:[a-f0-9]{24}$")
    reviewer: str = Field(min_length=1, max_length=100)
    queue_sha256: str = Field(pattern=SHA256_PATTERN)
    seed: int = Field(ge=0)
    ordered_pair_ids: list[str]
    blind_mappings: dict[str, BlindMappingV1]
    skipped_pair_ids: list[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime | None = None

    @field_validator("reviewer")
    @classmethod
    def clean_reviewer(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or any(char in cleaned for char in "/\\\0"):
            raise ValueError("reviewer name is invalid")
        return cleaned

    @model_validator(mode="after")
    def validate_mappings(self) -> "ReviewSessionV1":
        if set(self.ordered_pair_ids) != set(self.blind_mappings):
            raise ValueError("every queued pair must have one persisted blind mapping")
        if not set(self.skipped_pair_ids).issubset(set(self.ordered_pair_ids)):
            raise ValueError("skipped pair is not in the session queue")
        return self


class ReviewSubmissionV1(StrictModel):
    choice: Literal["a", "b", "tie", "both_bad"]
    scores: OptionalReviewScoresV1 | None = None
    notes: str | None = Field(default=None, max_length=2000)
    confidence: int | None = Field(default=None, ge=1, le=5)


class HumanReviewV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    review_id: str = Field(pattern=r"^review:[a-f0-9]{24}$")
    pair_id: str = Field(pattern=r"^pair:[a-f0-9]{24}$")
    brief_id: str = Field(pattern=ID_PATTERN)
    prompt: str = Field(min_length=1, max_length=4000)
    category: str = Field(min_length=1, max_length=100)
    design_a_id: str = Field(pattern=ID_PATTERN)
    design_b_id: str = Field(pattern=ID_PATTERN)
    choice: Literal["a", "b", "tie", "both_bad"]
    scores: OptionalReviewScoresV1 | None = None
    notes: str | None = Field(default=None, max_length=2000)
    confidence: int | None = Field(default=None, ge=1, le=5)
    reviewer: str = Field(min_length=1, max_length=100)
    session_id: str = Field(pattern=r"^session:[a-f0-9]{24}$")
    created_at: datetime
    source: Literal["human"]
    human_verified: Literal[True]
    provenance: dict[str, Any]
    license_class: str = Field(min_length=1, max_length=100)
    commercial_allowed: bool

    @model_validator(mode="after")
    def validate_human_origin(self) -> "HumanReviewV1":
        forbidden = {"heuristic", "critic", "vision_critic", "automatic", "synthetic"}
        origin = str(self.provenance.get("selection_source", "")).casefold()
        if origin in forbidden or origin != "human_ui_action":
            raise ValueError("review provenance must be an explicit human UI action")
        if self.design_a_id == self.design_b_id:
            raise ValueError("review sides must differ")
        return self


class PreferencePairV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    pair_id: str = Field(pattern=r"^preference:[a-f0-9]{24}$")
    review_id: str = Field(pattern=r"^review:[a-f0-9]{24}$")
    brief_id: str = Field(pattern=ID_PATTERN)
    prompt: str = Field(min_length=1, max_length=4000)
    category: str = Field(min_length=1, max_length=100)
    chosen_design_id: str = Field(pattern=ID_PATTERN)
    rejected_design_id: str = Field(pattern=ID_PATTERN)
    chosen_design_path: str = Field(min_length=1, max_length=4096)
    rejected_design_path: str = Field(min_length=1, max_length=4096)
    chosen_preview: str = Field(min_length=1, max_length=4096)
    rejected_preview: str = Field(min_length=1, max_length=4096)
    scores: OptionalReviewScoresV1 | None = None
    notes: str | None = Field(default=None, max_length=2000)
    confidence: int | None = Field(default=None, ge=1, le=5)
    reviewer: str = Field(min_length=1, max_length=100)
    created_at: datetime
    source: Literal["human"]
    human_verified: Literal[True]
    provenance: dict[str, Any]
    license_class: str = Field(min_length=1, max_length=100)
    commercial_allowed: bool

    @model_validator(mode="after")
    def validate_distinct(self) -> "PreferencePairV1":
        if self.chosen_design_id == self.rejected_design_id:
            raise ValueError("chosen and rejected designs must differ")
        return self


class PreferenceSplitV1(StrictModel):
    train_brief_ids: list[str]
    validation_brief_ids: list[str]
    test_brief_ids: list[str]
    seed: int

    @model_validator(mode="after")
    def no_leakage(self) -> "PreferenceSplitV1":
        groups = [set(self.train_brief_ids), set(self.validation_brief_ids), set(self.test_brief_ids)]
        if any(groups[index] & groups[other] for index in range(3) for other in range(index + 1, 3)):
            raise ValueError("brief IDs leak across preference splits")
        return self
