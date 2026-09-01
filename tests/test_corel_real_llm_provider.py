from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.corel_agent.context import build_document_context
from training.corel_agent.models import (
    CorelAgentRequestV1,
    PlannerProvenanceV1,
)
from training.corel_agent.provider import (
    CorelPlannerContext,
    LLMCorelPlanEnvelopeV1,
    LLMPlannerActionV1,
    LLMPlannerPlanV1,
    OpenAIPlannerProvider,
    PlannerProviderError,
    create_authorized_planner_provider,
)
from training.corel_operator.models import TargetSelectorV1


FILE_ID = "file:" + "d" * 32
MODEL = "gpt-5.6-sol"


class _FakeResponses:
    def __init__(self, parsed: LLMCorelPlanEnvelopeV1 | None) -> None:
        self.parsed = parsed
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(id="response_fixture", output_parsed=self.parsed)


class _FakeClient:
    def __init__(self, parsed: LLMCorelPlanEnvelopeV1 | None) -> None:
        self.responses = _FakeResponses(parsed)


def _request(instruction: str = "Đổi số điện thoại 0292 123 456 thành 0909 111 222") -> CorelAgentRequestV1:
    return CorelAgentRequestV1(
        request_id="real-llm-test-1",
        document_id=FILE_ID,
        instruction=instruction,
        execution_mode="PLAN_ONLY",
    )


def _context() -> CorelPlannerContext:
    inspection = CdrInspectionV1(
        source_path="source:fixture",
        source_size_bytes=1,
        source_mtime_ns=1,
        corel_version="fixture",
        page_count=1,
        page_width=100,
        page_height=50,
        unit="mm",
        corel_unit_code=3,
        layer_count=1,
        object_count=2,
        text_object_count=1,
        bitmap_count=0,
        vector_count=1,
        group_count=0,
        objects=[
            CdrObjectV1(
                object_id="object_12",
                corel_name="phone",
                object_type="text",
                bbox={"x": 5, "y": 5, "width": 30, "height": 5},
                bbox_norm={"x": 0.05, "y": 0.1, "width": 0.3, "height": 0.1},
                text="0292 123 456",
                font_family="Arial",
                font_size=12,
                metadata={"locked": False},
            )
        ],
    )
    summary = build_document_context(inspection, document_id=FILE_ID, include_text=True)
    return CorelPlannerContext(summary=summary, inspection=inspection)


def _valid_llm_envelope(request: CorelAgentRequestV1) -> LLMCorelPlanEnvelopeV1:
    return LLMCorelPlanEnvelopeV1(
        request_id=request.request_id,
        document_id=request.document_id,
        goal=request.instruction,
        plan=LLMPlannerPlanV1(
            plan_id=request.request_id,
            intent=request.instruction,
            source="llm",
            actions=[
                LLMPlannerActionV1(
                    operation="replace_text",
                    target=TargetSelectorV1(
                        kind="exact_text",
                        value="0292 123 456",
                        object_type="text",
                    ),
                    text_value="0909 111 222",
                    allowed_properties=["text"],
                    precondition_object_type="text",
                )
            ],
        ),
        confidence=0.95,
        provenance=PlannerProvenanceV1(
            planner_type="llm",
            planner_provider="openai",
            planner_model=MODEL,
            planner_is_ai=True,
        ),
    )


def test_openai_provider_requires_configuration_without_injected_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(PlannerProviderError) as raised:
        OpenAIPlannerProvider(model=MODEL)
    assert raised.value.code == "PROVIDER_NOT_CONFIGURED"


def test_authorized_provider_factory_fails_closed_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(PlannerProviderError) as raised:
        create_authorized_planner_provider()
    assert raised.value.code == "PROVIDER_NOT_CONFIGURED"


def test_openai_provider_returns_only_strict_host_bound_plan() -> None:
    request = _request()
    client = _FakeClient(_valid_llm_envelope(request))
    provider = OpenAIPlannerProvider(model=MODEL, client=client)

    envelope = provider.plan(request, _context())

    assert envelope.plan.source == "llm"
    assert envelope.provenance.planner_is_ai is True
    assert provider.last_call_metadata is not None
    assert provider.last_call_metadata.response_id == "response_fixture"
    call = client.responses.calls[0]
    assert call["text_format"] is LLMCorelPlanEnvelopeV1
    assert call["store"] is False
    assert "tools" not in call
    sent = json.loads(str(call["input"]))
    assert sent["document_context"]["document_id"] == FILE_ID
    assert "source_path" not in sent["document_context"]
    assert sent["host_locked_fields"]["provenance"]["planner_provider"] == "openai"


def test_openai_provider_refuses_vague_request_before_network_call() -> None:
    request = _request("Đổi tất cả cho đẹp hơn")
    client = _FakeClient(None)
    provider = OpenAIPlannerProvider(model=MODEL, client=client)

    with pytest.raises(PlannerProviderError) as raised:
        provider.plan(request, _context())

    assert raised.value.code == "VAGUE_OR_UNBOUNDED_INTENT"
    assert client.responses.calls == []


def test_openai_provider_rejects_host_binding_changes() -> None:
    request = _request()
    invalid = _valid_llm_envelope(request).model_copy(update={"goal": "different goal"})
    provider = OpenAIPlannerProvider(model=MODEL, client=_FakeClient(invalid))

    with pytest.raises(PlannerProviderError) as raised:
        provider.plan(request, _context())

    assert raised.value.code == "PLANNER_HOST_BINDING_MISMATCH"
    assert "goal" in str(raised.value)


def test_openai_provider_rejects_empty_or_refused_response() -> None:
    provider = OpenAIPlannerProvider(model=MODEL, client=_FakeClient(None))
    with pytest.raises(PlannerProviderError) as raised:
        provider.plan(_request(), _context())
    assert raised.value.code == "PLANNER_REFUSED_OR_EMPTY"
