from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.corel_operator.batch import OperatorBatchRunner
from training.corel_operator.models import OperatorExecutionResultV1, OperatorResultClass
from training.corel_operator.planner import (
    DeterministicMutationPilotPlanner,
    DeterministicSafePilotPlanner,
    PlannerOutputError,
    validate_planner_output,
)
from training.corel_operator.state import OperatorStateDatabase


def _inspection() -> CdrInspectionV1:
    item = CdrObjectV1(
        object_id="headline",
        corel_name="Headline",
        object_type="text",
        bbox={"x": 0.0, "y": 0.0, "width": 10.0, "height": 2.0},
        bbox_norm={"x": 0.0, "y": 0.0, "width": 0.1, "height": 0.02},
        text="Customer text",
        font_family="Arial",
        font_size=20.0,
        metadata={"source_page": 1, "locked": False},
    )
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
        object_count=1,
        text_object_count=1,
        bitmap_count=0,
        vector_count=0,
        group_count=0,
        objects=[item],
    )


class FakeOperator:
    def __init__(self) -> None:
        self.calls: list[Path] = []

    def execute(self, **kwargs: Any) -> OperatorExecutionResultV1:
        source = Path(kwargs["source_path"])
        self.calls.append(source)
        if source.name == "bad.cdr":
            return OperatorExecutionResultV1(
                result=OperatorResultClass.FAILED,
                plan_id=kwargs["plan"].plan_id,
                source_token="source:bad",
                source_unchanged=True,
                error_code="COREL_RUNTIME_FAILURE",
            )
        return OperatorExecutionResultV1(
            result=OperatorResultClass.AUTO_SUCCESS,
            plan_id=kwargs["plan"].plan_id,
            source_token="source:ok",
            source_unchanged=True,
            editability_verified=True,
        )


def test_fixture_planner_preserves_customer_content() -> None:
    plan = DeterministicSafePilotPlanner(scale=1.05).plan(
        _inspection(), source_token="source:abcdef"
    )
    assert plan is not None
    assert plan.source == "deterministic"
    assert plan.metadata["planner_is_ai"] is False
    assert plan.metadata["customer_content_changed"] is False
    assert plan.actions[0].operation.value == "set_font_size"
    assert plan.actions[0].value == 21.0


def test_planner_boundary_rejects_raw_com_payload() -> None:
    with pytest.raises(PlannerOutputError):
        validate_planner_output({"plan_id": "bad", "raw_com": "document.Save()"})


def test_mutation_pilot_planner_marks_benchmark_phone_replacement() -> None:
    inspection = _inspection()
    inspection.objects[0].text = "0901 234 567"
    plan = DeterministicMutationPilotPlanner(preferred_mode="replace").plan(
        inspection, source_token="source:fixture"
    )
    assert plan is not None
    assert plan.metadata["benchmark_sample_data"] is True
    assert plan.metadata["customer_content_changed_on_working_copy"] is True
    assert plan.actions[0].value == "0900 000 000"


def test_targeted_resize_refuses_text_object() -> None:
    assert (
        DeterministicMutationPilotPlanner(preferred_mode="resize").plan(
            _inspection(), source_token="source:fixture"
        )
        is None
    )


def test_batch_isolates_failure_and_resumes(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    workspace = tmp_path / "workspace"
    archive.mkdir()
    workspace.mkdir()
    good = archive / "good.cdr"
    bad = archive / "bad.cdr"
    good.write_bytes(b"good")
    bad.write_bytes(b"bad")
    rows = [{"absolute_path": str(good)}, {"absolute_path": str(bad)}]
    operator = FakeOperator()
    state = OperatorStateDatabase(workspace / "state.sqlite")
    planner = DeterministicSafePilotPlanner()
    plan = planner.plan(_inspection(), source_token="source:fixture")
    assert plan is not None
    runner = OperatorBatchRunner(
        run_id="pilot",
        archive_root=archive,
        workspace=workspace,
        operator=operator,  # type: ignore[arg-type]
        state=state,
        max_attempts=1,
    )
    first = runner.run(rows, lambda _row, _token: plan)
    assert {row["status"] for row in first} == {"COMPLETE", "FAILED"}
    assert len(operator.calls) == 2
    second = runner.run(rows, lambda _row, _token: plan)
    assert len(second) == 2
    assert len(operator.calls) == 2


def test_batch_records_unsupported_without_calling_operator(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    workspace = tmp_path / "workspace"
    archive.mkdir()
    workspace.mkdir()
    source = archive / "one.cdr"
    source.write_bytes(b"one")
    operator = FakeOperator()
    runner = OperatorBatchRunner(
        run_id="pilot",
        archive_root=archive,
        workspace=workspace,
        operator=operator,  # type: ignore[arg-type]
        state=OperatorStateDatabase(workspace / "state.sqlite"),
    )
    rows = runner.run([{"absolute_path": str(source)}], lambda _row, _token: None)
    assert rows[0]["status"] == "UNSUPPORTED"
    assert operator.calls == []
