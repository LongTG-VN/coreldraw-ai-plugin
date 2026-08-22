"""Semantic safety validation for untrusted planner envelopes."""

from __future__ import annotations

import re
from typing import Any

from training.corel_agent.models import (
    AgentRiskLevel,
    CorelAgentRequestV1,
    CorelPlanEnvelopeV1,
    ExecutionMode,
    PlanValidationV1,
)
from training.corel_operator.models import OperationKind, SelectorKind


_UNSAFE_TEXT = re.compile(
    r"(?:[A-Za-z]:[\\/]|\.\.[\\/]|file://|powershell|cmd\.exe|subprocess|"
    r"shell\b|vba\b|createobject|raw\s*com|document\.save|delete\s+all)",
    re.IGNORECASE,
)


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def validate_agent_plan(
    request: CorelAgentRequestV1,
    envelope: CorelPlanEnvelopeV1,
) -> PlanValidationV1:
    errors: list[str] = []
    if envelope.request_id != request.request_id:
        errors.append("REQUEST_ID_MISMATCH")
    if envelope.document_id != request.document_id:
        errors.append("DOCUMENT_ID_MISMATCH")
    if len(envelope.plan.actions) > 10:
        errors.append("MAXIMUM_ACTION_SCOPE_EXCEEDED")
    scan_values = [envelope.goal, envelope.plan.intent, envelope.constraints]
    scan_values.extend(action.value for action in envelope.plan.actions)
    if any(_UNSAFE_TEXT.search(text) for value in scan_values for text in _strings(value)):
        errors.append("UNSAFE_CODE_OR_PATH_CONTENT")

    risk = AgentRiskLevel.LOW_RISK
    for action in envelope.plan.actions:
        if action.operation == OperationKind.REPLACE_TEXT and action.target.kind in {
            SelectorKind.OBJECT_ID,
            SelectorKind.EXACT_TEXT,
            SelectorKind.PHONE,
            SelectorKind.PRICE,
        }:
            continue
        if action.operation in {
            OperationKind.MOVE,
            OperationKind.RESIZE,
            OperationKind.ROTATE,
            OperationKind.SET_FONT,
            OperationKind.SET_FONT_SIZE,
        }:
            risk = AgentRiskLevel.MEDIUM_RISK
            continue
        errors.append("PLANNER_UNSAFE_ACTION")
        risk = AgentRiskLevel.DISALLOWED

    if errors:
        risk = AgentRiskLevel.DISALLOWED
    review_required = envelope.requires_review or risk == AgentRiskLevel.MEDIUM_RISK
    execution_allowed = (
        not errors
        and request.execution_mode == ExecutionMode.EXECUTE_CONFIRMED
        and not review_required
    )
    return PlanValidationV1(
        accepted=not errors,
        risk_level=risk,
        execution_allowed=execution_allowed,
        review_required=review_required,
        errors=errors,
        normalized_action_count=len(envelope.plan.actions),
    )


__all__ = ["validate_agent_plan"]
