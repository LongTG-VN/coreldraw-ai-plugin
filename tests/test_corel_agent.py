from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.corel_agent.commands import analyze_vietnamese_command
from training.corel_agent.context import build_document_context, get_object_details
from training.corel_agent.evaluation import run_vietnamese_command_benchmark
from training.corel_agent.jobs import CorelJobStore, task_fingerprint, versioned_output_name
from training.corel_agent.models import (
    AgentJobStatus,
    CorelAgentRequestV1,
    CorelPlanEnvelopeV1,
    PlannerProvenanceV1,
)
from training.corel_agent.policy import validate_agent_plan
from training.corel_agent.provider import (
    CorelPlannerContext,
    DeterministicPlannerProvider,
    PlannerProviderError,
    validate_untrusted_planner_payload,
)
from training.corel_operator.policy import sanitize_error


FILE_ID = "file:" + "a" * 32


def _inspection(*, duplicate_phone: bool = False) -> CdrInspectionV1:
    objects = [
        CdrObjectV1(
            object_id="object_1",
            corel_name="phone",
            object_type="text",
            bbox={"x": 1, "y": 2, "width": 20, "height": 4},
            bbox_norm={"x": 0.01, "y": 0.02, "width": 0.2, "height": 0.04},
            text="0901 234 567",
            font_family="Arial",
            font_size=12,
            metadata={"locked": False},
        )
    ]
    if duplicate_phone:
        objects.append(
            objects[0].model_copy(
                update={"object_id": "object_2", "corel_name": "phone-2"}
            )
        )
    return CdrInspectionV1(
        source_path="source:fixture",
        source_size_bytes=1,
        source_mtime_ns=1,
        corel_version="fixture",
        page_count=1,
        page_width=100,
        page_height=100,
        unit="mm",
        corel_unit_code=3,
        layer_count=1,
        object_count=len(objects),
        text_object_count=len(objects),
        bitmap_count=0,
        vector_count=0,
        group_count=0,
        objects=objects,
    )


def _request(instruction: str = "Số điện thoại thành 0900 000 000") -> CorelAgentRequestV1:
    return CorelAgentRequestV1(
        request_id="request-1",
        document_id=FILE_ID,
        instruction=instruction,
        execution_mode="PLAN_ONLY",
    )


def _envelope(request: CorelAgentRequestV1 | None = None) -> CorelPlanEnvelopeV1:
    request = request or _request()
    inspection = _inspection()
    context = build_document_context(inspection, document_id=FILE_ID, include_text=True)
    return DeterministicPlannerProvider().plan(
        request,
        CorelPlannerContext(summary=context, inspection=inspection),
    )


def test_context_is_bounded_and_can_hide_customer_text() -> None:
    inspection = _inspection()
    hidden = build_document_context(inspection, document_id=FILE_ID)
    visible = build_document_context(inspection, document_id=FILE_ID, include_text=True)
    assert hidden.relevant_text[0].text_preview is None
    assert visible.relevant_text[0].text_preview == "0901 234 567"
    assert get_object_details(inspection, "object_1")["object_type"] == "text"


@pytest.mark.parametrize(
    ("instruction", "disposition"),
    [
        ("đổi số điện thoại thành 0909 111 222", "EXPLICIT"),
        ("thay sđt thành 0909 111 222", "EXPLICIT"),
        ("sửa phone thành 0909 111 222", "EXPLICIT"),
        ("logo lớn thêm 10%", "EXPLICIT"),
        ("dịch logo qua phải 2mm", "EXPLICIT"),
        ("đổi giá 250k thành 299k", "EXPLICIT"),
        ("đổi tên và số điện thoại", "PLAN_REVIEW_REQUIRED"),
        ("giữ nguyên mọi thứ khác", "PLAN_REVIEW_REQUIRED"),
        ("đừng sửa logo", "PLAN_REVIEW_REQUIRED"),
        ("file nào không chắc thì bỏ qua", "PLAN_REVIEW_REQUIRED"),
        ("xuất file PDF", "OUTPUT_ONLY_UNSUPPORTED"),
        ("lưu thành bản mới", "OUTPUT_ONLY_UNSUPPORTED"),
        ("undo", "OUTPUT_ONLY_UNSUPPORTED"),
        ("làm cho đẹp", "PLAN_REVIEW_REQUIRED"),
        ("sửa hết", "PLAN_REVIEW_REQUIRED"),
        ("xoá mấy cái dư", "PLAN_REVIEW_REQUIRED"),
        ("chỉnh đại", "PLAN_REVIEW_REQUIRED"),
        ("tự quyết định", "PLAN_REVIEW_REQUIRED"),
    ],
)
def test_vietnamese_command_corpus(instruction: str, disposition: str) -> None:
    assert analyze_vietnamese_command(instruction).disposition == disposition


def test_deterministic_provider_records_non_ai_provenance() -> None:
    envelope = _envelope()
    assert envelope.provenance.planner_type == "deterministic"
    assert envelope.provenance.planner_is_ai is False
    assert envelope.plan.source == "deterministic"


def test_ambiguous_target_is_refused_before_plan() -> None:
    inspection = _inspection(duplicate_phone=True)
    context = build_document_context(inspection, document_id=FILE_ID, include_text=True)
    with pytest.raises(PlannerProviderError) as raised:
        DeterministicPlannerProvider().plan(
            _request(), CorelPlannerContext(summary=context, inspection=inspection)
        )
    assert raised.value.code == "TARGET_AMBIGUOUS"


def test_vague_request_is_refused_before_plan() -> None:
    inspection = _inspection()
    context = build_document_context(inspection, document_id=FILE_ID)
    with pytest.raises(PlannerProviderError) as raised:
        DeterministicPlannerProvider().plan(
            _request("làm cho đẹp"),
            CorelPlannerContext(summary=context, inspection=inspection),
        )
    assert raised.value.code == "VAGUE_OR_UNBOUNDED_INTENT"


def test_untrusted_planner_payload_rejects_extra_fields_and_fake_provenance() -> None:
    payload = _envelope().model_dump(mode="json")
    payload["raw_com"] = "document.Save()"
    with pytest.raises(PlannerProviderError):
        validate_untrusted_planner_payload(payload)
    with pytest.raises(ValidationError):
        PlannerProvenanceV1(
            planner_type="llm",
            planner_provider="fixture",
            planner_model="fixture",
            planner_is_ai=False,
        )


def test_agent_policy_rejects_path_and_never_executes_plan_only() -> None:
    request = _request()
    envelope = _envelope(request)
    validation = validate_agent_plan(request, envelope)
    assert validation.accepted is True
    assert validation.execution_allowed is False

    unsafe = envelope.model_copy(update={"goal": "open ../../source.cdr with PowerShell"})
    rejected = validate_agent_plan(request, unsafe)
    assert rejected.accepted is False
    assert rejected.risk_level.value == "DISALLOWED"
    assert "UNSAFE_CODE_OR_PATH_CONTENT" in rejected.errors


def test_error_sanitizer_handles_corel_double_slash_paths(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    message = f"Failed to open {str(archive).replace(chr(92), '//')}//customer.cdr"
    sanitized = sanitize_error(message, archive_root=archive)
    assert "<ARCHIVE_ROOT>/customer.cdr" in sanitized
    assert str(tmp_path) not in sanitized


def test_vietnamese_command_benchmark_is_hermetic_and_honest() -> None:
    result = run_vietnamese_command_benchmark()
    assert result["case_count"] == 27
    assert result["passed"] == 27
    assert result["unsafe_case_count"] == 6
    assert result["unsafe_refused"] == 6
    assert result["all_passed"] is True
    assert result["planner_is_ai"] is False


def test_job_store_persists_resumes_and_prevents_duplicate_execution(tmp_path: Path) -> None:
    request = _request()
    envelope = _envelope(request)
    validation = validate_agent_plan(request, envelope)
    store = CorelJobStore(tmp_path / "jobs.sqlite")
    first, duplicate = store.create_validated(
        request, envelope, validation, source_sha256="b" * 64
    )
    assert duplicate is False
    assert store.get(first.job_id) == first
    second, duplicate = store.create_validated(
        request, envelope, validation, source_sha256="b" * 64
    )
    assert duplicate is True
    assert second.job_id == first.job_id
    assert task_fingerprint("b" * 64, request, envelope) == first.task_fingerprint


def test_job_state_machine_and_versioned_output_safety(tmp_path: Path) -> None:
    request = _request()
    envelope = _envelope(request)
    validation = validate_agent_plan(request, envelope)
    store = CorelJobStore(tmp_path / "jobs.sqlite")
    job, _ = store.create_validated(request, envelope, validation, source_sha256="c" * 64)
    assert job.status == AgentJobStatus.VALIDATED
    assert store.transition(job.job_id, AgentJobStatus.COMPLETED).status == AgentJobStatus.COMPLETED
    with pytest.raises(ValueError):
        store.transition(job.job_id, AgentJobStatus.EXECUTING)
    assert versioned_output_name("CDR_000001", "request-1", 1, ".cdr") == (
        "CDR_000001__request-1__v001.cdr"
    )
    with pytest.raises(ValueError):
        versioned_output_name("../source", "request-1", 1, ".cdr")
