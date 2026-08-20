from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.corel_operator.models import (
    MutationActionV1,
    MutationPlanV1,
    OperatorResultClass,
    TargetSelectorV1,
)
from training.corel_operator.policy import OperatorPolicyError, validate_working_copy_path
from training.corel_operator.service import SafeCorelOperator
from training.corel_operator.targets import resolve_target


def _object(
    object_id: str,
    name: str,
    *,
    text: str | None = None,
    object_type: str = "text",
) -> CdrObjectV1:
    return CdrObjectV1(
        object_id=object_id,
        corel_name=name,
        object_type=object_type,
        bbox={"x": 1.0, "y": 2.0, "width": 20.0, "height": 5.0},
        bbox_norm={"x": 0.01, "y": 0.02, "width": 0.2, "height": 0.05},
        text=text,
        font_family="Arial" if object_type == "text" else None,
        font_size=12.0 if object_type == "text" else None,
        metadata={"source_page": 1},
    )


def _inspection(objects: list[CdrObjectV1]) -> CdrInspectionV1:
    return CdrInspectionV1(
        source_path="working.cdr",
        source_size_bytes=10,
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
        bitmap_count=0,
        vector_count=sum(item.object_type != "text" for item in objects),
        group_count=0,
        objects=objects,
    )


class FakeRuntime:
    def __init__(self, inspection: CdrInspectionV1) -> None:
        self.current = inspection.model_copy(deep=True)
        self.before_transaction = inspection.model_copy(deep=True)
        self.is_open = False
        self.fail_transaction = False
        self.change_untargeted = False
        self.closed = 0

    def create_working_copy(self, source: Path, target: Path) -> None:
        target.write_bytes(b"COREL-FAKE-FIXTURE")

    def open(self, path: Path) -> None:
        self.is_open = True

    def snapshot(self, path: Path) -> CdrInspectionV1:
        return self.current.model_copy(deep=True)

    def execute_transaction(
        self, operations: list[dict[str, Any]], *, name: str
    ) -> dict[str, Any]:
        if self.fail_transaction:
            raise RuntimeError("disconnected")
        self.before_transaction = self.current.model_copy(deep=True)
        by_id = {item.object_id: item for item in self.current.objects}
        for operation in operations:
            item = by_id[operation["operator_object_id"]]
            if operation["op"] == "typography":
                if "text" in operation:
                    item.text = operation["text"]
                if "font_name" in operation:
                    item.font_family = operation["font_name"]
                if "font_size" in operation:
                    item.font_size = operation["font_size"]
            elif operation["op"] == "transform":
                if "x" in operation:
                    item.bbox["x"] = float(operation["x"])
                if "y" in operation:
                    item.bbox["y"] = float(operation["y"])
                if "width" in operation:
                    item.bbox["width"] = float(operation["width"])
                if "height" in operation:
                    item.bbox["height"] = float(operation["height"])
                if "rotation" in operation:
                    item.rotation = float(operation["rotation"])
        if self.change_untargeted:
            self.current.objects[-1].fill = {"unexpected": True}
        return {"status": "committed"}

    def undo(self) -> None:
        self.current = self.before_transaction.model_copy(deep=True)

    def save(self) -> None:
        return None

    def close(self) -> None:
        self.is_open = False
        self.closed += 1

    def export_png(self, path: Path, *, max_dimension: int, max_pixels: int) -> Path:
        path.write_bytes(b"PNG")
        return path

    def export_pdf(self, path: Path) -> Path:
        path.write_bytes(b"PDF")
        return path


def _plan(selector: TargetSelectorV1, value: str = "New text") -> MutationPlanV1:
    return MutationPlanV1(
        plan_id="test-plan",
        intent="replace one exact text object",
        source="fixture",
        actions=[
            MutationActionV1(
                operation="replace_text",
                target=selector,
                value=value,
                precondition_object_type="text",
            )
        ],
    )


def _paths(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    archive = tmp_path / "archive"
    workspace = tmp_path / "workspace"
    archive.mkdir()
    workspace.mkdir()
    source = archive / "source.cdr"
    source.write_bytes(b"SOURCE")
    target = workspace / "run" / "working.cdr"
    return archive, workspace, source, target


def test_operator_replaces_unique_text_on_copy_and_reopens(tmp_path: Path) -> None:
    archive, workspace, source, target = _paths(tmp_path)
    runtime = FakeRuntime(
        _inspection([_object("one", "headline", text="Old"), _object("two", "body", text="Body")])
    )
    result = SafeCorelOperator(runtime).execute(
        source_path=source,
        archive_root=archive,
        workspace=workspace,
        working_copy_path=target,
        plan=_plan(TargetSelectorV1(kind="exact_text", value="Old")),
    )
    assert result.result == OperatorResultClass.AUTO_SUCCESS
    assert result.source_unchanged is True
    assert result.editability_verified is True
    assert result.object_count_before == result.object_count_after == 2
    assert runtime.current.objects[0].text == "New text"
    assert source.read_bytes() == b"SOURCE"


def test_ambiguous_text_needs_review_without_mutation(tmp_path: Path) -> None:
    archive, workspace, source, target = _paths(tmp_path)
    runtime = FakeRuntime(
        _inspection([_object("one", "a", text="Same"), _object("two", "b", text="Same")])
    )
    result = SafeCorelOperator(runtime).execute(
        source_path=source,
        archive_root=archive,
        workspace=workspace,
        working_copy_path=target,
        plan=_plan(TargetSelectorV1(kind="exact_text", value="Same")),
    )
    assert result.result == OperatorResultClass.NEEDS_REVIEW
    assert result.operation_count == 0
    assert result.source_unchanged is True


def test_duplicate_corel_names_resolve_by_stable_operator_id() -> None:
    objects = [_object("one", "duplicate", text="A"), _object("two", "duplicate", text="B")]
    resolved = resolve_target(objects, TargetSelectorV1(kind="object_id", value="one"))
    assert resolved.object_id == "one"
    assert resolved.corel_name == "duplicate"


def test_unexpected_untargeted_change_triggers_verified_rollback(tmp_path: Path) -> None:
    archive, workspace, source, target = _paths(tmp_path)
    original = _inspection([_object("one", "headline", text="Old"), _object("two", "body", text="Body")])
    runtime = FakeRuntime(original)
    runtime.change_untargeted = True
    result = SafeCorelOperator(runtime).execute(
        source_path=source,
        archive_root=archive,
        workspace=workspace,
        working_copy_path=target,
        plan=_plan(TargetSelectorV1(kind="object_id", value="one")),
    )
    assert result.result == OperatorResultClass.FAILED
    assert result.rollback_verified is True
    assert runtime.current == original


def test_runtime_failure_isolated_and_document_closed(tmp_path: Path) -> None:
    archive, workspace, source, target = _paths(tmp_path)
    runtime = FakeRuntime(_inspection([_object("one", "headline", text="Old")]))
    runtime.fail_transaction = True
    result = SafeCorelOperator(runtime).execute(
        source_path=source,
        archive_root=archive,
        workspace=workspace,
        working_copy_path=target,
        plan=_plan(TargetSelectorV1(kind="object_id", value="one")),
    )
    assert result.result == OperatorResultClass.FAILED
    assert result.error_code == "COREL_RUNTIME_FAILURE"
    assert runtime.is_open is False
    assert source.read_bytes() == b"SOURCE"


def test_working_copy_policy_rejects_source_and_escape(tmp_path: Path) -> None:
    archive, workspace, source, _target = _paths(tmp_path)
    with pytest.raises(OperatorPolicyError):
        validate_working_copy_path(source, workspace, source)
    with pytest.raises(OperatorPolicyError):
        validate_working_copy_path(tmp_path / "outside.cdr", workspace, source)


def test_phone_and_price_selectors() -> None:
    objects = [
        _object("phone", "phone", text="0901 234 567"),
        _object("price", "price", text="45K"),
    ]
    assert resolve_target(objects, TargetSelectorV1(kind="phone", value="*")).object_id == "phone"
    assert resolve_target(objects, TargetSelectorV1(kind="price", value="*")).object_id == "price"


def test_plan_rejects_unbounded_resize() -> None:
    with pytest.raises(ValueError):
        MutationActionV1(
            operation="resize",
            target=TargetSelectorV1(kind="object_id", value="one"),
            value={"width": -1, "height": 2},
        )
