from __future__ import annotations

from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.corel_operator.reliability import (
    classify_failure_replay,
    classify_visual_qa_reevaluation,
    replay_plan_from_previous_result,
)


def _inspection(*, parent: bool = False) -> CdrInspectionV1:
    objects = [
        CdrObjectV1(
            object_id="text",
            corel_name="text",
            object_type="text",
            bbox={"x": 10, "y": 10, "width": 20, "height": 5},
            bbox_norm={"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.05},
            parent_id="group" if parent else None,
            text="45K",
            font_family="Arial",
            font_size=10,
            metadata={"source_page": 1, "locked": False},
        )
    ]
    if parent:
        objects.append(
            CdrObjectV1(
                object_id="group",
                corel_name="group",
                object_type="group",
                bbox={"x": 9, "y": 9, "width": 22, "height": 7},
                bbox_norm={"x": 0.09, "y": 0.09, "width": 0.22, "height": 0.07},
                metadata={"source_page": 1, "locked": False},
            )
        )
    return CdrInspectionV1(
        source_path="fixture.cdr",
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
        text_object_count=1,
        bitmap_count=0,
        vector_count=0,
        group_count=int(parent),
        objects=objects,
    )


def _previous(mode: str) -> dict:
    return {
        "resolved_targets": [{"object_id": "text"}],
        "metadata": {"planner": {"operation_mode": mode}},
    }


def test_replay_font_plan_preserves_bounded_operation_and_parent_dependency() -> None:
    plan = replay_plan_from_previous_result(
        _inspection(parent=True),
        _previous("font_size_plus_5_percent"),
        source_token="source:" + "a" * 24,
    )
    assert plan is not None
    assert plan.actions[0].value == 10.5
    assert plan.actions[0].dependencies[0].object_id == "group"
    assert plan.metadata["planner_is_ai"] is False


def test_replay_replacement_uses_explicit_benchmark_value() -> None:
    plan = replay_plan_from_previous_result(
        _inspection(),
        _previous("replace_price"),
        source_token="source:" + "b" * 24,
    )
    assert plan is not None
    assert plan.actions[0].value == "99K"
    assert plan.metadata["customer_content_changed_on_working_copy"] is True


def test_replay_move_and_resize_are_bounded() -> None:
    move = replay_plan_from_previous_result(
        _inspection(),
        _previous("move_1mm"),
        source_token="source:" + "c" * 24,
    )
    resize = replay_plan_from_previous_result(
        _inspection(),
        _previous("resize_1_percent"),
        source_token="source:" + "d" * 24,
    )
    assert move is not None and move.actions[0].value == {"x": 11.0, "y": 11.0}
    assert resize is not None and resize.actions[0].value == {
        "width": 20.2,
        "height": 5.05,
    }


def test_replay_rejects_missing_or_unknown_previous_evidence() -> None:
    assert (
        replay_plan_from_previous_result(
            _inspection(),
            _previous("unknown"),
            source_token="source:" + "e" * 24,
        )
        is None
    )
    missing = _previous("move_1mm")
    missing["resolved_targets"] = [{"object_id": "missing"}]
    assert (
        replay_plan_from_previous_result(
            _inspection(),
            missing,
            source_token="source:" + "f" * 24,
        )
        is None
    )


def test_reevaluation_classification_never_upgrades_review_or_failure() -> None:
    assert classify_visual_qa_reevaluation({"result": "AUTO_SUCCESS"}) == (
        "UPGRADED_TO_AUTO_SUCCESS"
    )
    assert classify_visual_qa_reevaluation({"result": "NEEDS_REVIEW"}) == (
        "STILL_NEEDS_REVIEW"
    )
    assert classify_visual_qa_reevaluation({"result": "FAILED"}) == (
        "CONFIRMED_REGRESSION"
    )
    assert classify_visual_qa_reevaluation({"result": "UNSUPPORTED"}) == (
        "QA_EVIDENCE_INSUFFICIENT"
    )
    assert classify_visual_qa_reevaluation(
        {
            "result": "NEEDS_REVIEW",
            "error_code": "TARGET_OUTSIDE_CANONICAL_PAGE",
        }
    ) == "QA_EVIDENCE_INSUFFICIENT"
    assert classify_visual_qa_reevaluation(
        {"result": "NEEDS_REVIEW", "error_code": "CANONICAL_EXPORT_FAILED"}
    ) == "QA_EVIDENCE_INSUFFICIENT"


def test_failure_replay_classification_keeps_uncertain_results_separate() -> None:
    assert classify_failure_replay({"result": "AUTO_SUCCESS"}) == "FIXED"
    assert classify_failure_replay({"result": "SUCCESS_WITH_WARNING"}) == "FIXED"
    assert classify_failure_replay({"result": "NEEDS_REVIEW"}) == "NEEDS_REVIEW"
    assert classify_failure_replay({"result": "UNSUPPORTED"}) == "NOT_REPLAYABLE"
    assert classify_failure_replay({"result": "FAILED"}) == "FAILED"
