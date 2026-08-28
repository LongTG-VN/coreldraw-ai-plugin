"""Exact-plan approval binding for local supervised medium-risk operations."""

from __future__ import annotations

import hmac

from training.corel_agent.jobs import plan_hash
from training.corel_agent.models import (
    AgentRiskLevel,
    CorelPlanEnvelopeV1,
    MediumRiskApprovalV1,
    MediumRiskPlanBindingV1,
    PlanValidationV1,
)
from training.corel_operator.models import OperationKind, SelectorKind


_APPROVABLE_OPERATIONS = {OperationKind.MOVE, OperationKind.RESIZE}


def build_medium_risk_binding(
    *,
    job_id: str,
    envelope: CorelPlanEnvelopeV1,
    validation: PlanValidationV1,
) -> MediumRiskPlanBindingV1:
    """Build the complete immutable approval challenge for one validated plan."""

    if not validation.accepted or validation.errors:
        raise ValueError("medium-risk plan was not accepted")
    if validation.risk_level != AgentRiskLevel.MEDIUM_RISK:
        raise ValueError("approval is only available for medium-risk plans")
    if envelope.requires_review:
        raise ValueError("planner-requested review cannot be elevated by this approval")
    if envelope.request_id != job_id or envelope.plan.plan_id != job_id:
        raise ValueError("medium-risk plan is not bound to this job")
    if any(action.operation not in _APPROVABLE_OPERATIONS for action in envelope.plan.actions):
        raise ValueError("only move and resize are explicitly approvable")
    if any(action.target.kind != SelectorKind.OBJECT_ID for action in envelope.plan.actions):
        raise ValueError("medium-risk approval requires stable object IDs")

    return MediumRiskPlanBindingV1(
        job_id=job_id,
        plan_hash=plan_hash(envelope),
        target_object_ids=[action.target.value for action in envelope.plan.actions],
        operations=[action.operation.value for action in envelope.plan.actions],
        operation_arguments=[action.value for action in envelope.plan.actions],
    )


def approval_matches_binding(
    approval: MediumRiskApprovalV1,
    binding: MediumRiskPlanBindingV1,
) -> bool:
    """Return true only when every approval-bound field still matches."""

    return bool(
        approval.job_id == binding.job_id
        and hmac.compare_digest(approval.plan_hash, binding.plan_hash)
        and approval.target_object_ids == binding.target_object_ids
        and approval.operations == binding.operations
        and approval.operation_arguments == binding.operation_arguments
        and approval.risk_level == binding.risk_level
    )


__all__ = ["approval_matches_binding", "build_medium_risk_binding"]
