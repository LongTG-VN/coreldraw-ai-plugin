"""Model-agnostic planner providers; no provider receives execution authority."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from training.company_archive.models import CdrInspectionV1
from training.corel_agent.commands import analyze_vietnamese_command
from training.corel_agent.models import (
    CorelAgentRequestV1,
    CorelPlanEnvelopeV1,
    DocumentContextV1,
    OutputRequestV1,
    PlannerProvenanceV1,
)
from training.corel_operator.agent import (
    ControlledInstructionPlanner,
    OperatorTaskRequestV1,
    TaskPlanningError,
)


@dataclass(frozen=True)
class CorelPlannerContext:
    summary: DocumentContextV1
    inspection: CdrInspectionV1


class CorelPlannerProvider(Protocol):
    def plan(
        self,
        request: CorelAgentRequestV1,
        context: CorelPlannerContext,
    ) -> CorelPlanEnvelopeV1: ...


class PlannerProviderError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DeterministicPlannerProvider:
    """Adapter for the existing bounded grammar; explicitly not AI."""

    def __init__(self) -> None:
        self.planner = ControlledInstructionPlanner()

    def plan(
        self,
        request: CorelAgentRequestV1,
        context: CorelPlannerContext,
    ) -> CorelPlanEnvelopeV1:
        analysis = analyze_vietnamese_command(request.instruction)
        if analysis.disposition != "EXPLICIT":
            raise PlannerProviderError(
                analysis.reasons[0] if analysis.reasons else analysis.disposition,
                "command requires review or unsupported output authority",
            )
        try:
            plan = self.planner.plan(
                OperatorTaskRequestV1(
                    file_id=request.document_id,
                    task_id=request.request_id,
                    instruction=analysis.normalized_instruction,
                    execution_confirmed=False,
                ),
                context.inspection,
            )
        except TaskPlanningError as exc:
            code = "TARGET_AMBIGUOUS" if exc.code == "TARGET_AMBIGUOUS_OR_MISSING" else exc.code
            raise PlannerProviderError(code, str(exc)) from exc
        return CorelPlanEnvelopeV1(
            request_id=request.request_id,
            goal=request.instruction,
            document_id=request.document_id,
            plan=plan,
            constraints=analysis.constraints,
            output_requests=[OutputRequestV1(format=value) for value in analysis.output_formats],
            confidence=1.0,
            requires_review=False,
            provenance=PlannerProvenanceV1(
                planner_type="deterministic",
                planner_provider="local",
                planner_model=self.planner.name,
                planner_is_ai=False,
            ),
        )


def validate_untrusted_planner_payload(payload: Any) -> CorelPlanEnvelopeV1:
    """Strict parser for future remote/local LLM JSON."""

    try:
        return CorelPlanEnvelopeV1.model_validate(payload)
    except Exception as exc:
        raise PlannerProviderError("PLANNER_INVALID_OUTPUT", str(exc)) from exc


def detect_authorized_provider_configuration() -> dict[str, bool]:
    """Report configuration presence without reading or returning secret values."""

    return {
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


__all__ = [
    "CorelPlannerContext",
    "CorelPlannerProvider",
    "DeterministicPlannerProvider",
    "PlannerProviderError",
    "detect_authorized_provider_configuration",
    "validate_untrusted_planner_payload",
]
