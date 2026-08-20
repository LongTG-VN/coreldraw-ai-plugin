"""Bounded structured refinement policy; never interprets free-form COM advice."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from training.corel_operator.models import MutationActionV1, MutationPlanV1, OperationKind


class ReviewIssueCode(str, Enum):
    TEXT_OVERFLOW = "TEXT_OVERFLOW"
    OUTSIDE_CANVAS = "OUTSIDE_CANVAS"
    COLLISION = "COLLISION"
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
    UNKNOWN = "UNKNOWN"


class StructuredReviewIssueV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: ReviewIssueCode
    object_id: str | None = None
    severity: Literal["warning", "error"] = "error"


class StructuredOperatorReviewV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    source: Literal["human", "deterministic", "llm"]
    iteration: int = Field(ge=0, le=3)
    issues: list[StructuredReviewIssueV1] = Field(max_length=50)


class BoundedRefinementPlanner:
    """Allow only one evidence-backed correction family for at most three rounds."""

    def __init__(self, *, max_iterations: int = 3, min_font_size: float = 6.0) -> None:
        if not 1 <= max_iterations <= 3:
            raise ValueError("max_iterations must be in 1..3")
        self.max_iterations = max_iterations
        self.min_font_size = min_font_size

    def refine(
        self,
        plan: MutationPlanV1,
        review: StructuredOperatorReviewV1,
    ) -> MutationPlanV1 | None:
        if review.iteration >= self.max_iterations or not review.issues:
            return None
        if any(issue.code != ReviewIssueCode.TEXT_OVERFLOW for issue in review.issues):
            return None
        overflow_ids = {issue.object_id for issue in review.issues if issue.object_id}
        refined_actions: list[MutationActionV1] = []
        changed = False
        for action in plan.actions:
            if (
                action.operation == OperationKind.SET_FONT_SIZE
                and action.target.value in overflow_ids
                and isinstance(action.value, (int, float))
            ):
                new_size = round(max(self.min_font_size, float(action.value) * 0.95), 3)
                if new_size < float(action.value):
                    action = action.model_copy(update={"value": new_size})
                    changed = True
            refined_actions.append(action)
        if not changed:
            return None
        return plan.model_copy(
            update={
                "plan_id": f"{plan.plan_id}-r{review.iteration + 1}",
                "actions": refined_actions,
                "metadata": {
                    **plan.metadata,
                    "refinement_iteration": review.iteration + 1,
                    "refinement_source": review.source,
                    "refinement_policy": "font_size_minus_5_percent",
                },
            }
        )
