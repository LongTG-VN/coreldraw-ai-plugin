from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageDraw

from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.corel_operator.agent import (
    AutonomousOperatorAgent,
    ControlledInstructionPlanner,
    OperatorTaskRequestV1,
    OperatorTaskStatus,
    TaskPlanningError,
)
from training.corel_operator.capabilities import inspect_operator_capabilities
from training.corel_operator.mcp_server import create_mcp_server
from training.corel_operator.models import OperatorExecutionResultV1, OperatorResultClass
from training.corel_operator.tools import OperatorToolError, OperatorToolService
from training.corel_operator.visual_qa import compare_operator_previews


FILE_ID = "file:" + "a" * 32


def _object(
    object_id: str,
    *,
    name: str = "",
    object_type: str = "text",
    text: str | None = "Text",
    x: float = 1.0,
) -> CdrObjectV1:
    return CdrObjectV1(
        object_id=object_id,
        corel_name=name,
        object_type=object_type,
        bbox={"x": x, "y": 2.0, "width": 20.0, "height": 5.0},
        bbox_norm={"x": x / 100, "y": 0.02, "width": 0.2, "height": 0.05},
        text=text if object_type == "text" else None,
        font_family="Arial" if object_type == "text" else None,
        font_size=12.0 if object_type == "text" else None,
        metadata={"source_page": 1, "locked": False, "bbox_clipped_to_page": False},
    )


def _inspection(objects: list[CdrObjectV1]) -> CdrInspectionV1:
    return CdrInspectionV1(
        source_path="fixture.cdr",
        source_size_bytes=1,
        source_mtime_ns=1,
        corel_version="fake",
        page_count=1,
        page_width=100,
        page_height=100,
        unit="mm",
        corel_unit_code=3,
        layer_count=1,
        object_count=len(objects),
        text_object_count=sum(item.object_type == "text" for item in objects),
        bitmap_count=sum(item.object_type == "image" for item in objects),
        vector_count=sum(item.object_type not in {"text", "image", "group"} for item in objects),
        group_count=sum(item.object_type == "group" for item in objects),
        objects=objects,
    )


def test_capability_report_uses_stable_ids_not_corel_names() -> None:
    inspection = _inspection(
        [
            _object("one", name="", text="0901 234 567"),
            _object("two", name="duplicate", text="45K"),
            _object("three", name="duplicate", object_type="rectangle", text=None),
        ]
    )
    report = inspect_operator_capabilities(inspection)
    assert report.stable_target_count == 3
    assert report.unnamed_corel_name_count == 1
    assert report.duplicate_corel_name_count == 2
    assert report.phone_target_count == 1
    assert report.price_target_count == 1
    assert report.operation_candidates["resize"] == ["one", "two", "three"]


def test_visual_qa_detects_bounded_change_and_identical_output(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    before = workspace / "before.png"
    after = workspace / "after.png"
    image = Image.new("RGB", (100, 100), "white")
    image.save(before)
    changed = image.copy()
    ImageDraw.Draw(changed).rectangle((10, 10, 20, 20), fill="black")
    changed.save(after)
    report = compare_operator_previews(before, after, workspace=workspace)
    assert report.status == "PASS"
    assert 0 < report.changed_pixel_ratio < 0.85

    same = workspace / "same.png"
    image.save(same)
    no_change = compare_operator_previews(before, same, workspace=workspace)
    assert no_change.status == "NEEDS_REVIEW"
    assert no_change.issues == ["NO_VISIBLE_CHANGE"]


def test_visual_qa_rejects_path_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.png"
    Image.new("RGB", (10, 10), "white").save(outside)
    with pytest.raises(ValueError, match="escaped"):
        compare_operator_previews(outside, outside, workspace=workspace)


def test_controlled_planner_builds_explicit_phone_and_scale_actions() -> None:
    inspection = _inspection(
        [
            _object("phone", text="0901 234 567"),
            _object("logo", object_type="rectangle", text=None, x=30),
        ]
    )
    request = OperatorTaskRequestV1(
        file_id=FILE_ID,
        task_id="task-1",
        instruction="Đổi số điện thoại thành 0909 123 456; tăng logo 10%",
    )
    plan = ControlledInstructionPlanner().plan(request, inspection)
    assert [item.operation.value for item in plan.actions] == ["replace_text", "resize"]
    assert plan.actions[0].value == "0909 123 456"
    assert plan.actions[1].value == {"width": 22.0, "height": 5.5}
    assert plan.metadata["business_values_source"] == "explicit_instruction"


def test_controlled_planner_fails_closed_on_ambiguous_phone() -> None:
    inspection = _inspection(
        [_object("one", text="0901 234 567"), _object("two", text="0902 345 678")]
    )
    request = OperatorTaskRequestV1(
        file_id=FILE_ID,
        task_id="task-2",
        instruction="Đổi số điện thoại thành 0909 123 456",
    )
    with pytest.raises(TaskPlanningError) as captured:
        ControlledInstructionPlanner().plan(request, inspection)
    assert captured.value.code == "TARGET_AMBIGUOUS_OR_MISSING"


class _FakeInventory:
    def __init__(self, source: Path) -> None:
        self.source = source

    def get_file(self, file_id: str) -> dict[str, Any]:
        if file_id != FILE_ID:
            raise KeyError(file_id)
        return {"absolute_path": str(self.source), "cdr_candidate": True}


class _FakeInspector:
    def __init__(self, inspection: CdrInspectionV1) -> None:
        self.inspection = inspection

    def inspect(self, path: Path, *, archive_root: Path) -> CdrInspectionV1:
        return self.inspection.model_copy(deep=True)


class _FakeOperator:
    def execute(self, **kwargs: Any) -> OperatorExecutionResultV1:
        target = Path(kwargs["working_copy_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"FAKE-COREL-WORKING-COPY")
        before = target.with_name("working_copy_before.png")
        after = target.with_name("working_copy_after.png")
        image = Image.new("RGB", (100, 100), "white")
        image.save(before)
        changed = image.copy()
        ImageDraw.Draw(changed).rectangle((10, 10, 20, 20), fill="black")
        changed.save(after)
        pdf = target.with_suffix(".pdf")
        pdf.write_bytes(b"PDF")
        return OperatorExecutionResultV1(
            result=OperatorResultClass.AUTO_SUCCESS,
            plan_id=kwargs["plan"].plan_id,
            source_token="source:fixture",
            working_copy=str(target),
            preview_before=str(before),
            preview_after=str(after),
            pdf_after=str(pdf),
            source_unchanged=True,
            transaction_committed=True,
            editability_verified=True,
        )


def _tool_service(tmp_path: Path) -> OperatorToolService:
    archive = tmp_path / "archive"
    workspace = tmp_path / "workspace"
    archive.mkdir()
    source = archive / "source.cdr"
    source.write_bytes(b"SOURCE")
    inspection = _inspection([_object("phone", text="0901 234 567")])
    return OperatorToolService(
        archive_root=archive,
        workspace=workspace,
        inventory=_FakeInventory(source),
        inspector=_FakeInspector(inspection),  # type: ignore[arg-type]
        operator=_FakeOperator(),  # type: ignore[arg-type]
    )


def test_tool_service_resolves_opaque_id_and_sanitizes_output_paths(tmp_path: Path) -> None:
    service = _tool_service(tmp_path)
    document = service.get_document(FILE_ID)
    assert document["source_token"].startswith("source:")
    assert document["capabilities"]["phone_target_count"] == 1
    with pytest.raises(OperatorToolError):
        service.get_document("../source.cdr")

    request = OperatorTaskRequestV1(
        file_id=FILE_ID,
        task_id="safe-task",
        instruction="Đổi số điện thoại thành 0909 123 456",
    )
    plan = ControlledInstructionPlanner().plan(request, service.inspect_model(FILE_ID))
    result = service.execute_plan(FILE_ID, task_id="safe-task", plan=plan)
    assert result["result"] == "AUTO_SUCCESS"
    assert not Path(result["working_copy"]).is_absolute()
    assert service.visual_qa(task_id="safe-task")["status"] == "PASS"


def test_autonomous_agent_is_plan_only_by_default_and_runs_after_confirmation(
    tmp_path: Path,
) -> None:
    service = _tool_service(tmp_path)
    agent = AutonomousOperatorAgent(service)
    plan_only = agent.run(
        OperatorTaskRequestV1(
            file_id=FILE_ID,
            task_id="plan-only",
            instruction="Đổi số điện thoại thành 0909 123 456",
        )
    )
    assert plan_only.status == OperatorTaskStatus.PLANNED
    assert plan_only.execution is None

    executed = agent.run(
        OperatorTaskRequestV1(
            file_id=FILE_ID,
            task_id="confirmed",
            instruction="Đổi số điện thoại thành 0909 123 456",
            execution_confirmed=True,
        )
    )
    assert executed.status == OperatorTaskStatus.AUTO_SUCCESS
    assert executed.visual_qa is not None
    assert executed.visual_qa["aesthetic_judgment"] is False


def test_mcp_exposes_only_bounded_tools_and_requires_confirmation(tmp_path: Path) -> None:
    server = create_mcp_server(_tool_service(tmp_path))

    async def verify() -> None:
        tools = await server.list_tools()
        names = {tool.name for tool in tools}
        assert names == {
            "corel_get_document",
            "corel_list_objects",
            "corel_find_text",
            "corel_plan_task",
            "corel_run_task",
            "corel_execute_plan",
            "corel_visual_qa",
        }
        response = await server.call_tool(
            "corel_execute_plan",
            {
                "file_id": FILE_ID,
                "task_id": "mcp-plan",
                "plan": {},
                "execution_confirmed": False,
            },
        )
        assert isinstance(response, tuple)
        structured = response[1]
        assert isinstance(structured, dict)
        assert structured["result"] == "CONFIRMATION_REQUIRED"

    asyncio.run(verify())


def test_mcp_rejects_non_loopback_binding(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="loopback"):
        create_mcp_server(_tool_service(tmp_path), host="0.0.0.0")
