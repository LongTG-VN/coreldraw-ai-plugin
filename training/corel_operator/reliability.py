"""Deterministic reliability plans and result classifications."""

from __future__ import annotations

from typing import Any

from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.corel_operator.models import (
    MutationActionV1,
    MutationDependencyV1,
    MutationPlanV1,
    TargetSelectorV1,
)


def _target_from_previous_result(
    inspection: CdrInspectionV1,
    previous_result: dict[str, Any],
) -> CdrObjectV1 | None:
    targets = previous_result.get("resolved_targets") or []
    if len(targets) != 1:
        return None
    object_id = str(targets[0].get("object_id", ""))
    return next(
        (
            item
            for item in inspection.objects
            if item.object_id == object_id
            or item.metadata.get("legacy_object_id") == object_id
        ),
        None,
    )


def replay_plan_from_previous_result(
    inspection: CdrInspectionV1,
    previous_result: dict[str, Any],
    *,
    source_token: str,
) -> MutationPlanV1 | None:
    """Reconstruct the bounded deterministic Run2 action without customer invention."""

    target = _target_from_previous_result(inspection, previous_result)
    if target is None or bool(target.metadata.get("locked", False)):
        return None
    operation_mode = str(
        previous_result.get("metadata", {}).get("planner", {}).get("operation_mode", "")
    )
    dependencies = (
        [
            MutationDependencyV1(
                object_id=target.parent_id,
                kind="DEPENDENT_CONTAINER",
            )
        ]
        if target.parent_id
        else []
    )
    selector = TargetSelectorV1(
        kind="object_id",
        value=target.object_id,
        object_type=target.object_type,
    )
    common = {
        "target": selector,
        "precondition_object_type": target.object_type,
        "dependencies": dependencies,
    }
    if operation_mode == "font_size_plus_5_percent":
        if target.object_type != "text" or target.font_size is None:
            return None
        action = MutationActionV1(
            operation="set_font_size",
            value=round(float(target.font_size) * 1.05, 3),
            **common,
        )
    elif operation_mode in {"replace_phone", "replace_price"}:
        if target.object_type != "text" or not target.text:
            return None
        action = MutationActionV1(
            operation="replace_text",
            value="0900 000 000" if operation_mode == "replace_phone" else "99K",
            **common,
        )
    elif operation_mode == "move_1mm":
        action = MutationActionV1(
            operation="move",
            value={"x": target.bbox["x"] + 1, "y": target.bbox["y"] + 1},
            **common,
        )
    elif operation_mode == "resize_1_percent":
        action = MutationActionV1(
            operation="resize",
            value={
                "width": round(target.bbox["width"] * 1.01, 6),
                "height": round(target.bbox["height"] * 1.01, 6),
            },
            **common,
        )
    else:
        return None
    return MutationPlanV1(
        plan_id="qa-v2-replay-" + source_token.removeprefix("source:")[:24],
        intent="replay one previous bounded Run2 action for Visual QA V2",
        source="deterministic",
        actions=[action],
        metadata={
            "planner": "VisualQaV2ReplayPlanner",
            "planner_is_ai": False,
            "operation_mode": operation_mode,
            "customer_content_changed_on_working_copy": operation_mode.startswith("replace_"),
            "replay_of_previous_run": True,
        },
    )


def classify_visual_qa_reevaluation(result: dict[str, Any]) -> str:
    result_class = str(result.get("result", ""))
    if result.get("error_code") in {
        "CANONICAL_EXPORT_FAILED",
        "TARGET_OUTSIDE_CANONICAL_PAGE",
        "SOURCE_MAPPING_MISSING",
    }:
        return "QA_EVIDENCE_INSUFFICIENT"
    if result_class in {"AUTO_SUCCESS", "SUCCESS_WITH_WARNING"}:
        return "UPGRADED_TO_AUTO_SUCCESS"
    if result_class == "NEEDS_REVIEW":
        return "STILL_NEEDS_REVIEW"
    if result_class == "FAILED":
        return "CONFIRMED_REGRESSION"
    return "QA_EVIDENCE_INSUFFICIENT"


__all__ = [
    "classify_visual_qa_reevaluation",
    "replay_plan_from_previous_result",
]
