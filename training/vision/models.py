"""Strict versioned contracts for vision critique and safe refinement."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


IssueType = Literal[
    "weak_focal_point", "hero_too_small", "hero_too_large",
    "weak_headline", "headline_too_large", "headline_too_small",
    "weak_cta", "cta_too_large", "cta_too_small",
    "poor_visual_balance", "excessive_whitespace", "insufficient_whitespace",
    "uneven_spacing", "weak_hierarchy", "flat_typography",
    "poor_text_grouping", "poor_image_text_balance", "low_contrast",
    "palette_incoherence", "too_much_decoration", "too_little_decoration",
    "menu_spreadsheet_feel", "menu_grouping_weak", "campaign_energy_low",
    "logo_too_small", "logo_too_large", "logo_competes_with_headline",
    "asset_crop_awkward",
]
Severity = Literal["low", "medium", "high"]
Magnitude = Literal["small", "medium"]
TargetRole = Literal[
    "hero", "headline", "cta", "layout", "typography", "palette",
    "decoration", "menu", "logo",
]
RecommendedAction = Literal[
    "increase_area", "decrease_area", "increase_emphasis", "decrease_emphasis",
    "rebalance", "increase_contrast", "harmonize_palette",
    "add_bounded_decoration", "reduce_decoration", "improve_grouping",
]
OperationType = Literal[
    "scale_role", "shift_role", "emphasize_text", "emphasize_cta",
    "adjust_contrast", "adjust_decoration", "improve_menu_grouping",
]


class StrictVisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class VisionCriticConfig(StrictVisionModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: str = "Qwen/Qwen3-VL-2B-Instruct"
    revision: str = "89644892e4d85e24eaac8bacfd4f463576704203"
    license: str = "Apache-2.0"
    quantization: Literal["nf4_4bit", "none"] = "nf4_4bit"
    device: Literal["auto", "cuda", "cpu"] = "auto"
    max_image_dimension: int = Field(default=768, ge=224, le=1536)
    max_new_tokens: int = Field(default=256, ge=64, le=1024)
    max_issues: int = Field(default=2, ge=1, le=5)
    temperature: FiniteFloat = Field(default=0, ge=0, le=1)


class CritiqueOverallV1(StrictVisionModel):
    quality_score: FiniteFloat = Field(ge=0, le=1)
    confidence: FiniteFloat = Field(ge=0, le=1)


class DesignIssueV1(StrictVisionModel):
    issue_type: IssueType
    severity: Severity
    confidence: FiniteFloat = Field(ge=0, le=1)
    target_role: TargetRole
    reason: str = Field(min_length=1, max_length=240)
    recommended_action: RecommendedAction
    magnitude: Magnitude


class VisionCritiqueV1(StrictVisionModel):
    schema_version: Literal["1.0"] = "1.0"
    overall: CritiqueOverallV1
    issues: list[DesignIssueV1] = Field(default_factory=list, max_length=5)
    critic_model: str = Field(min_length=1)
    critic_revision: str = Field(min_length=1)
    raw_recovered: bool = False
    latency_seconds: FiniteFloat = Field(ge=0)


class PairwiseVisionJudgmentV1(StrictVisionModel):
    schema_version: Literal["1.0"] = "1.0"
    preferred: Literal["A", "B", "tie"]
    confidence: FiniteFloat = Field(ge=0, le=1)
    reasons: list[str] = Field(min_length=1, max_length=3)
    critic_model: str = Field(min_length=1)
    critic_revision: str = Field(min_length=1)
    latency_seconds: FiniteFloat = Field(ge=0)


class RefinementOperationV1(StrictVisionModel):
    operation_id: str = Field(pattern=r"^op_[0-9]{2}$")
    operation_type: OperationType
    target_role: TargetRole
    source_issue: IssueType
    magnitude: Magnitude
    parameters: dict[str, FiniteFloat | str]
    constraint_applied: str = Field(min_length=1, max_length=300)


class RefinementPlanV1(StrictVisionModel):
    schema_version: Literal["1.0"] = "1.0"
    operations: list[RefinementOperationV1] = Field(default_factory=list, max_length=5)
    stalled_issues: list[IssueType] = Field(default_factory=list)


class RefinementOperationReportV1(StrictVisionModel):
    operation_id: str
    source_issue: IssueType
    accepted: bool
    reason: str
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    constraint_applied: str


class TechnicalValidationV1(StrictVisionModel):
    schema_valid: bool
    hard_failure: bool
    outside_canvas_rate: FiniteFloat = Field(ge=0, le=1)
    overlap_ratio: FiniteFloat = Field(ge=0, le=1)
    text_fit_rate: FiniteFloat = Field(ge=0, le=1)
    truncation_count: int = Field(ge=0)
    corel_compile_valid: bool
    asset_aspect_preserved: bool
    logo_aspect_preserved: bool
    business_content_immutable: bool
    violations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def safe_if_no_violations(self) -> "TechnicalValidationV1":
        if self.hard_failure and not self.violations:
            raise ValueError("hard failures require at least one violation")
        return self


class SelfRefineIterationV1(StrictVisionModel):
    iteration: int = Field(ge=0, le=3)
    critic_score: FiniteFloat = Field(ge=0, le=1)
    frozen_design_score: FiniteFloat = Field(ge=0, le=1)
    selection_score: FiniteFloat = Field(ge=0, le=1)
    technical_safe: bool
    accepted_operations: int = Field(ge=0)
    rejected_operations: int = Field(ge=0)


__all__ = [
    "DesignIssueV1", "PairwiseVisionJudgmentV1", "RefinementOperationReportV1",
    "RefinementOperationV1", "RefinementPlanV1", "SelfRefineIterationV1",
    "TechnicalValidationV1", "VisionCriticConfig", "VisionCritiqueV1",
]
