"""Strict, provider-neutral contracts for Corel agent planning and jobs."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from training.corel_operator.models import MutationPlanV1, StrictModel


class ExecutionMode(str, Enum):
    PLAN_ONLY = "PLAN_ONLY"
    DRY_RUN = "DRY_RUN"
    EXECUTE_CONFIRMED = "EXECUTE_CONFIRMED"


class AgentRiskLevel(str, Enum):
    LOW_RISK = "LOW_RISK"
    MEDIUM_RISK = "MEDIUM_RISK"
    DISALLOWED = "DISALLOWED"


class AgentJobStatus(str, Enum):
    CREATED = "CREATED"
    INSPECTED = "INSPECTED"
    PLANNED = "PLANNED"
    VALIDATED = "VALIDATED"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    EXECUTING = "EXECUTING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"


class AgentErrorCode(str, Enum):
    PLANNER_INVALID_OUTPUT = "PLANNER_INVALID_OUTPUT"
    PLANNER_UNSAFE_ACTION = "PLANNER_UNSAFE_ACTION"
    TARGET_AMBIGUOUS = "TARGET_AMBIGUOUS"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    POLICY_REJECTED = "POLICY_REJECTED"
    COREL_EXECUTION_FAILED = "COREL_EXECUTION_FAILED"
    POSTCONDITION_FAILED = "POSTCONDITION_FAILED"
    VISUAL_QA_REVIEW = "VISUAL_QA_REVIEW"
    SAVE_FAILED = "SAVE_FAILED"
    REOPEN_FAILED = "REOPEN_FAILED"
    EXPORT_FAILED = "EXPORT_FAILED"


class PlannerProvenanceV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    planner_type: Literal["deterministic", "fixture", "llm"]
    planner_provider: str = Field(min_length=1, max_length=100)
    planner_model: str = Field(min_length=1, max_length=160)
    planner_is_ai: bool

    @model_validator(mode="after")
    def enforce_ai_provenance(self) -> "PlannerProvenanceV1":
        if (self.planner_type == "llm") != self.planner_is_ai:
            raise ValueError("planner_is_ai must match planner_type=llm")
        return self


class OutputRequestV1(StrictModel):
    format: Literal["CDR", "PDF", "PNG"]
    destination: Literal["job_workspace"] = "job_workspace"
    overwrite: Literal[False] = False


class CorelAgentRequestV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
    document_id: str = Field(pattern=r"^file:[a-f0-9]{32}$")
    instruction: str = Field(min_length=1, max_length=2000)
    execution_mode: ExecutionMode = ExecutionMode.PLAN_ONLY
    max_planning_steps: int = Field(default=6, ge=1, le=10)


class CorelPlanEnvelopeV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
    goal: str = Field(min_length=1, max_length=1000)
    document_id: str = Field(pattern=r"^file:[a-f0-9]{32}$")
    plan: MutationPlanV1
    constraints: list[str] = Field(default_factory=list, max_length=20)
    output_requests: list[OutputRequestV1] = Field(default_factory=list, max_length=3)
    confidence: float = Field(ge=0, le=1)
    requires_review: bool = False
    provenance: PlannerProvenanceV1

    @model_validator(mode="after")
    def bind_plan_to_request(self) -> "CorelPlanEnvelopeV1":
        if self.plan.plan_id != self.request_id:
            raise ValueError("plan_id must equal request_id")
        if self.plan.source == "llm" and not self.provenance.planner_is_ai:
            raise ValueError("LLM plan source requires AI provenance")
        if self.plan.source != "llm" and self.provenance.planner_is_ai:
            raise ValueError("non-LLM plan source cannot claim AI provenance")
        return self


class TextCandidateSummaryV1(StrictModel):
    object_id: str = Field(min_length=1, max_length=160)
    text_preview: str | None = Field(default=None, max_length=160)
    font_family: str | None = Field(default=None, max_length=160)
    font_size: float | None = None
    bbox_norm: dict[str, float]


class DocumentContextV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    document_id: str = Field(pattern=r"^file:[a-f0-9]{32}$")
    pages: int = Field(ge=1)
    page_width: float = Field(gt=0)
    page_height: float = Field(gt=0)
    unit: str
    object_count: int = Field(ge=0)
    text_count: int = Field(ge=0)
    bitmap_count: int = Field(ge=0)
    vector_count: int = Field(ge=0)
    group_count: int = Field(ge=0)
    operation_candidate_counts: dict[str, int]
    relevant_text: list[TextCandidateSummaryV1] = Field(default_factory=list, max_length=25)
    text_included: bool
    truncated: bool


class PlanValidationV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    accepted: bool
    risk_level: AgentRiskLevel
    execution_allowed: bool
    review_required: bool
    errors: list[str] = Field(default_factory=list)
    normalized_action_count: int = Field(ge=0)


class CorelOperatorJobV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    job_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
    document_id: str = Field(pattern=r"^file:[a-f0-9]{32}$")
    request: str = Field(min_length=1, max_length=2000)
    planner: PlannerProvenanceV1
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    task_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    risk: AgentRiskLevel
    status: AgentJobStatus
    dry_run: bool
    execution_confirmed: bool
    validation: PlanValidationV1
    output_files: list[str] = Field(default_factory=list, max_length=10)
    audit: list[dict[str, str]] = Field(default_factory=list, max_length=100)


__all__ = [
    "AgentErrorCode",
    "AgentJobStatus",
    "AgentRiskLevel",
    "CorelAgentRequestV1",
    "CorelOperatorJobV1",
    "CorelPlanEnvelopeV1",
    "DocumentContextV1",
    "ExecutionMode",
    "OutputRequestV1",
    "PlannerProvenanceV1",
    "PlanValidationV1",
    "TextCandidateSummaryV1",
]
