"""Model-agnostic planner providers; no provider receives execution authority."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import Field, model_validator

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
from training.corel_operator.models import (
    MutationActionV1,
    MutationPlanV1,
    OperationKind,
    StrictModel,
    TargetSelectorV1,
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


@dataclass(frozen=True)
class PlannerCallMetadata:
    provider: str
    model: str
    latency_ms: float
    response_id: str | None


DEFAULT_OPENAI_PLANNER_MODEL = "gpt-5.6-sol"


_OPENAI_PLANNER_INSTRUCTIONS = """You are a planning-only CorelDRAW assistant.
Return exactly one LLMCorelPlanEnvelopeV1 using the supplied structured-output schema.
You have no execution authority and no tools. Never emit or request COM, VBA,
shell commands, arbitrary file paths, save/open/export operations, source overwrite,
or unbounded mutations. Use only the bounded mutation operations and selectors in
the schema. Keep request_id, document_id, goal, constraints, output_requests, and
planner provenance exactly equal to the values supplied by the host. Set plan.source
to llm and plan.plan_id to request_id. Use text_value for replace_text/set_font,
number_value for set_font_size/rotate, move_x/move_y for move, and
resize_width/resize_height for resize. Move values are absolute page-space target
coordinates, not deltas; compute relative movement from the supplied bbox. Resize
values are absolute target dimensions. Leave all other value slots null. When the
target is not uniquely defensible, set requires_review=true; do not guess an object
identifier.
"""


class LLMPlannerActionV1(StrictModel):
    """Strict-output action DTO without arbitrary JSON maps."""

    operation: OperationKind
    target: TargetSelectorV1
    text_value: str | None = Field(default=None, max_length=500)
    number_value: float | None = None
    move_x: float | None = None
    move_y: float | None = None
    resize_width: float | None = None
    resize_height: float | None = None
    allowed_properties: list[str] = Field(default_factory=list, max_length=10)
    maximum_scope: Literal["one_object"] = "one_object"
    precondition_object_type: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def validate_value_slots(self) -> "LLMPlannerActionV1":
        slots = {
            "text": self.text_value,
            "number": self.number_value,
            "move_x": self.move_x,
            "move_y": self.move_y,
            "resize_width": self.resize_width,
            "resize_height": self.resize_height,
        }
        required: set[str]
        if self.operation in {OperationKind.REPLACE_TEXT, OperationKind.SET_FONT}:
            required = {"text"}
        elif self.operation in {OperationKind.SET_FONT_SIZE, OperationKind.ROTATE}:
            required = {"number"}
        elif self.operation == OperationKind.MOVE:
            required = {"move_x", "move_y"}
        else:
            required = {"resize_width", "resize_height"}
        if any(slots[name] is None for name in required):
            raise ValueError(f"{self.operation.value} is missing required value slots")
        if any(value is not None for name, value in slots.items() if name not in required):
            raise ValueError(f"{self.operation.value} contains unrelated value slots")
        if self.operation == OperationKind.RESIZE and (
            float(self.resize_width or 0) <= 0 or float(self.resize_height or 0) <= 0
        ):
            raise ValueError("resize dimensions must be positive")
        return self

    def to_canonical(self) -> MutationActionV1:
        if self.operation in {OperationKind.REPLACE_TEXT, OperationKind.SET_FONT}:
            value: str | float | dict[str, float] = str(self.text_value)
        elif self.operation in {OperationKind.SET_FONT_SIZE, OperationKind.ROTATE}:
            value = float(self.number_value)  # type: ignore[arg-type]
        elif self.operation == OperationKind.MOVE:
            value = {"x": float(self.move_x), "y": float(self.move_y)}  # type: ignore[arg-type]
        else:
            value = {
                "width": float(self.resize_width),  # type: ignore[arg-type]
                "height": float(self.resize_height),  # type: ignore[arg-type]
            }
        return MutationActionV1(
            operation=self.operation,
            target=self.target,
            value=value,
            allowed_properties=self.allowed_properties,
            maximum_scope=self.maximum_scope,
            precondition_object_type=self.precondition_object_type,
        )


class LLMPlannerPlanV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    plan_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    intent: str = Field(min_length=1, max_length=1000)
    source: Literal["llm"] = "llm"
    actions: list[LLMPlannerActionV1] = Field(min_length=1, max_length=10)
    expected_object_count_change: Literal[0] = 0
    rollback_on_error: Literal[True] = True


class LLMCorelPlanEnvelopeV1(StrictModel):
    """Provider-facing response schema converted into the canonical envelope."""

    schema_version: Literal["1.0"] = "1.0"
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
    goal: str = Field(min_length=1, max_length=1000)
    document_id: str = Field(pattern=r"^file:[a-f0-9]{32}$")
    plan: LLMPlannerPlanV1
    constraints: list[str] = Field(default_factory=list, max_length=20)
    output_requests: list[OutputRequestV1] = Field(default_factory=list, max_length=3)
    confidence: float = Field(ge=0, le=1)
    requires_review: bool = False
    provenance: PlannerProvenanceV1

    def to_canonical(self) -> CorelPlanEnvelopeV1:
        return CorelPlanEnvelopeV1(
            request_id=self.request_id,
            goal=self.goal,
            document_id=self.document_id,
            plan=MutationPlanV1(
                plan_id=self.plan.plan_id,
                intent=self.plan.intent,
                source="llm",
                actions=[action.to_canonical() for action in self.plan.actions],
                expected_object_count_change=0,
                rollback_on_error=True,
                metadata={},
            ),
            constraints=self.constraints,
            output_requests=self.output_requests,
            confidence=self.confidence,
            requires_review=self.requires_review,
            provenance=self.provenance,
        )


class OpenAIPlannerProvider:
    """Planning-only OpenAI adapter with no tool or mutation authority."""

    provider_name = "openai"

    def __init__(
        self,
        *,
        model: str = DEFAULT_OPENAI_PLANNER_MODEL,
        client: Any | None = None,
        max_output_tokens: int = 4000,
    ) -> None:
        if not model.strip():
            raise PlannerProviderError("PLANNER_MODEL_REQUIRED", "model is required")
        if not 256 <= max_output_tokens <= 8000:
            raise PlannerProviderError(
                "PLANNER_TOKEN_BUDGET_INVALID",
                "max_output_tokens must be between 256 and 8000",
            )
        if client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise PlannerProviderError(
                    "PROVIDER_NOT_CONFIGURED",
                    "OPENAI_API_KEY is not configured",
                )
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise PlannerProviderError(
                    "PROVIDER_SDK_UNAVAILABLE",
                    "OpenAI SDK is not installed",
                ) from exc
            client = OpenAI()
        self.client = client
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.last_call_metadata: PlannerCallMetadata | None = None

    def plan(
        self,
        request: CorelAgentRequestV1,
        context: CorelPlannerContext,
    ) -> CorelPlanEnvelopeV1:
        analysis = analyze_vietnamese_command(request.instruction)
        if analysis.disposition != "EXPLICIT":
            raise PlannerProviderError(
                analysis.reasons[0] if analysis.reasons else analysis.disposition,
                "command requires review or is outside mutation authority",
            )
        if context.summary.document_id != request.document_id:
            raise PlannerProviderError(
                "DOCUMENT_ID_MISMATCH",
                "planner context does not match the request document",
            )

        expected_outputs = [
            OutputRequestV1(format=value) for value in analysis.output_formats
        ]
        planner_input = {
            "request": request.model_dump(mode="json"),
            "document_context": context.summary.model_dump(mode="json"),
            "host_locked_fields": {
                "request_id": request.request_id,
                "document_id": request.document_id,
                "goal": request.instruction,
                "constraints": analysis.constraints,
                "output_requests": [
                    value.model_dump(mode="json") for value in expected_outputs
                ],
                "provenance": {
                    "schema_version": "1.0",
                    "planner_type": "llm",
                    "planner_provider": self.provider_name,
                    "planner_model": self.model,
                    "planner_is_ai": True,
                },
            },
        }
        started = time.perf_counter()
        try:
            response = self.client.responses.parse(
                model=self.model,
                instructions=_OPENAI_PLANNER_INSTRUCTIONS,
                input=json.dumps(planner_input, ensure_ascii=False),
                text_format=LLMCorelPlanEnvelopeV1,
                max_output_tokens=self.max_output_tokens,
                store=False,
            )
        except Exception as exc:
            raise PlannerProviderError(
                "PLANNER_PROVIDER_ERROR",
                f"OpenAI planner request failed: {type(exc).__name__}",
            ) from exc
        latency_ms = (time.perf_counter() - started) * 1000
        response_id = getattr(response, "id", None)
        self.last_call_metadata = PlannerCallMetadata(
            provider=self.provider_name,
            model=self.model,
            latency_ms=latency_ms,
            response_id=response_id if isinstance(response_id, str) else None,
        )
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise PlannerProviderError(
                "PLANNER_REFUSED_OR_EMPTY",
                "OpenAI planner returned no parsed plan",
            )
        payload = parsed.model_dump(mode="json") if hasattr(parsed, "model_dump") else parsed
        try:
            structured = LLMCorelPlanEnvelopeV1.model_validate(payload)
            envelope = validate_untrusted_planner_payload(
                structured.to_canonical().model_dump(mode="json")
            )
        except PlannerProviderError:
            raise
        except Exception as exc:
            raise PlannerProviderError("PLANNER_INVALID_OUTPUT", str(exc)) from exc
        self._validate_host_locked_fields(
            request=request,
            envelope=envelope,
            expected_constraints=analysis.constraints,
            expected_outputs=expected_outputs,
        )
        return envelope

    def _validate_host_locked_fields(
        self,
        *,
        request: CorelAgentRequestV1,
        envelope: CorelPlanEnvelopeV1,
        expected_constraints: list[str],
        expected_outputs: list[OutputRequestV1],
    ) -> None:
        mismatches: list[str] = []
        if envelope.request_id != request.request_id:
            mismatches.append("request_id")
        if envelope.document_id != request.document_id:
            mismatches.append("document_id")
        if envelope.goal != request.instruction:
            mismatches.append("goal")
        if envelope.constraints != expected_constraints:
            mismatches.append("constraints")
        if envelope.output_requests != expected_outputs:
            mismatches.append("output_requests")
        provenance = envelope.provenance
        if (
            provenance.planner_type != "llm"
            or provenance.planner_provider != self.provider_name
            or provenance.planner_model != self.model
            or not provenance.planner_is_ai
            or envelope.plan.source != "llm"
        ):
            mismatches.append("provenance")
        if len(envelope.plan.actions) > request.max_planning_steps:
            mismatches.append("max_planning_steps")
        if mismatches:
            raise PlannerProviderError(
                "PLANNER_HOST_BINDING_MISMATCH",
                "planner changed host-locked fields: " + ", ".join(mismatches),
            )


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


def create_authorized_planner_provider() -> CorelPlannerProvider:
    """Select one configured provider without exposing credential values."""

    configured = detect_authorized_provider_configuration()
    if configured["openai"]:
        return OpenAIPlannerProvider(
            model=os.environ.get(
                "COREL_AGENT_OPENAI_MODEL", DEFAULT_OPENAI_PLANNER_MODEL
            )
        )
    if configured["anthropic"]:
        raise PlannerProviderError(
            "PROVIDER_ADAPTER_UNAVAILABLE",
            "Anthropic is configured but no supervised planner adapter is installed",
        )
    raise PlannerProviderError(
        "PROVIDER_NOT_CONFIGURED",
        "no authorized OpenAI or Anthropic provider is configured",
    )


__all__ = [
    "DEFAULT_OPENAI_PLANNER_MODEL",
    "CorelPlannerContext",
    "CorelPlannerProvider",
    "DeterministicPlannerProvider",
    "LLMCorelPlanEnvelopeV1",
    "LLMPlannerActionV1",
    "LLMPlannerPlanV1",
    "OpenAIPlannerProvider",
    "PlannerCallMetadata",
    "PlannerProviderError",
    "create_authorized_planner_provider",
    "detect_authorized_provider_configuration",
    "validate_untrusted_planner_payload",
]
