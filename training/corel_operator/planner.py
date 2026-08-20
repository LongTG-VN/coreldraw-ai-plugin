"""Model-agnostic planner boundary; no planner can emit raw COM instructions."""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.corel_operator.models import (
    MutationActionV1,
    MutationPlanV1,
    TargetSelectorV1,
)


class StructuredOperatorPlanner(Protocol):
    def plan(self, inspection: CdrInspectionV1, *, source_token: str) -> MutationPlanV1 | None: ...


def _unique_named(objects: list[CdrObjectV1]) -> list[CdrObjectV1]:
    counts: dict[str, int] = {}
    for item in objects:
        counts[item.corel_name] = counts.get(item.corel_name, 0) + 1
    return [item for item in objects if counts[item.corel_name] == 1]


class DeterministicSafePilotPlanner:
    """Create one bounded typography edit for real working-copy validation.

    This is explicitly a fixture planner, not AI and not aesthetic judgment.
    It preserves all customer/business text and changes only font size by a
    bounded percentage on one uniquely addressable editable text object.
    """

    def __init__(self, *, scale: float = 1.05, min_size: float = 6.0, max_size: float = 72.0) -> None:
        if not 0.9 <= scale <= 1.1:
            raise ValueError("pilot font scale must stay in 0.9..1.1")
        self.scale = scale
        self.min_size = min_size
        self.max_size = max_size

    def plan(
        self, inspection: CdrInspectionV1, *, source_token: str
    ) -> MutationPlanV1 | None:
        candidates = [
            item
            for item in _unique_named(inspection.objects)
            if item.object_type == "text"
            and item.text
            and item.font_size is not None
            and self.min_size <= item.font_size <= self.max_size
            and not bool(item.metadata.get("locked", False))
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: hashlib.sha256(
                f"{source_token}:{item.object_id}".encode("utf-8")
            ).hexdigest()
        )
        chosen = candidates[0]
        new_size = round(
            max(self.min_size, min(self.max_size, float(chosen.font_size) * self.scale)),
            3,
        )
        if new_size == chosen.font_size:
            return None
        return MutationPlanV1(
            plan_id="pilot-" + source_token.removeprefix("source:")[:24],
            intent="verify one bounded editable-text typography mutation on a working copy",
            source="deterministic",
            actions=[
                MutationActionV1(
                    operation="set_font_size",
                    target=TargetSelectorV1(
                        kind="object_id",
                        value=chosen.object_id,
                        object_type="text",
                    ),
                    value=new_size,
                    precondition_object_type="text",
                )
            ],
            metadata={
                "planner": "DeterministicSafePilotPlanner",
                "planner_is_ai": False,
                "customer_content_changed": False,
                "font_scale": self.scale,
            },
        )


_PHONE = re.compile(r"(?<!\d)(?:\+?84|0)(?:[ .-]?\d){8,10}(?!\d)")
_PRICE = re.compile(r"(?i)(?<!\w)\d+(?:[., ]\d{3})*(?:\s?)(?:k|đ|₫|vnd)(?!\w)")


class DeterministicMutationPilotPlanner:
    """Diversify safe mechanical edits without making aesthetic decisions."""

    def __init__(
        self,
        *,
        preferred_mode: str = "auto",
    ) -> None:
        if preferred_mode not in {"auto", "font", "replace", "move", "resize"}:
            raise ValueError("unsupported pilot operation mode")
        self.font_planner = DeterministicSafePilotPlanner()
        self.preferred_mode = preferred_mode

    @staticmethod
    def _base_candidates(inspection: CdrInspectionV1) -> list[CdrObjectV1]:
        return [
            item
            for item in _unique_named(inspection.objects)
            if not bool(item.metadata.get("locked", False))
            and not bool(item.metadata.get("bbox_clipped_to_page", False))
        ]

    def plan(
        self, inspection: CdrInspectionV1, *, source_token: str
    ) -> MutationPlanV1 | None:
        candidates = self._base_candidates(inspection)
        if not candidates:
            if self.preferred_mode not in {"auto", "font"}:
                return None
            fallback = self.font_planner.plan(inspection, source_token=source_token)
            if fallback is not None:
                fallback.metadata["operation_mode"] = "font_size_plus_5_percent"
            return fallback
        mode = (
            int(hashlib.sha256(source_token.encode("utf-8")).hexdigest()[:2], 16) % 4
            if self.preferred_mode == "auto"
            else {"font": 0, "replace": 1, "move": 2, "resize": 3}[
                self.preferred_mode
            ]
        )
        plan_id = "pilot-" + source_token.removeprefix("source:")[:24]

        if mode == 1:
            replaceable = [
                item
                for item in candidates
                if item.object_type == "text"
                and item.text
                and (_PHONE.search(item.text) or _PRICE.search(item.text))
            ]
            if replaceable:
                chosen = sorted(replaceable, key=lambda item: item.object_id)[0]
                is_phone = bool(_PHONE.search(chosen.text or ""))
                replacement = "0900 000 000" if is_phone else "99K"
                return MutationPlanV1(
                    plan_id=plan_id,
                    intent="verify explicit benchmark text replacement on a working copy",
                    source="deterministic",
                    actions=[
                        MutationActionV1(
                            operation="replace_text",
                            target=TargetSelectorV1(
                                kind="object_id",
                                value=chosen.object_id,
                                object_type="text",
                            ),
                            value=replacement,
                            precondition_object_type="text",
                        )
                    ],
                    metadata={
                        "planner": "DeterministicMutationPilotPlanner",
                        "planner_is_ai": False,
                        "operation_mode": "replace_phone" if is_phone else "replace_price",
                        "benchmark_sample_data": True,
                        "customer_content_changed_on_working_copy": True,
                    },
                )
            if self.preferred_mode == "replace":
                return None

        if mode == 2:
            movable = [
                item
                for item in candidates
                if item.parent_id is None
                and item.object_type != "group"
                and item.bbox["x"] + item.bbox["width"] + 1 <= inspection.page_width
                and item.bbox["y"] + item.bbox["height"] + 1 <= inspection.page_height
            ]
            if movable:
                chosen = sorted(movable, key=lambda item: item.object_id)[0]
                return MutationPlanV1(
                    plan_id=plan_id,
                    intent="verify a one-millimetre bounded position change on a working copy",
                    source="deterministic",
                    actions=[
                        MutationActionV1(
                            operation="move",
                            target=TargetSelectorV1(
                                kind="object_id",
                                value=chosen.object_id,
                                object_type=chosen.object_type,
                            ),
                            value={"x": chosen.bbox["x"] + 1, "y": chosen.bbox["y"] + 1},
                            precondition_object_type=chosen.object_type,
                        )
                    ],
                    metadata={
                        "planner": "DeterministicMutationPilotPlanner",
                        "planner_is_ai": False,
                        "operation_mode": "move_1mm",
                        "customer_content_changed_on_working_copy": False,
                    },
                )
            if self.preferred_mode == "move":
                return None

        if mode == 3:
            resizable = [
                item
                for item in candidates
                if item.parent_id is None
                and item.object_type not in {"group", "text"}
                and item.bbox["width"] > 0
                and item.bbox["height"] > 0
                and item.bbox["x"] + item.bbox["width"] * 1.01 <= inspection.page_width
                and item.bbox["y"] + item.bbox["height"] * 1.01 <= inspection.page_height
            ]
            if resizable:
                chosen = sorted(resizable, key=lambda item: item.object_id)[0]
                return MutationPlanV1(
                    plan_id=plan_id,
                    intent="verify a one-percent bounded resize on a working copy",
                    source="deterministic",
                    actions=[
                        MutationActionV1(
                            operation="resize",
                            target=TargetSelectorV1(
                                kind="object_id",
                                value=chosen.object_id,
                                object_type=chosen.object_type,
                            ),
                            value={
                                "width": round(chosen.bbox["width"] * 1.01, 6),
                                "height": round(chosen.bbox["height"] * 1.01, 6),
                            },
                            precondition_object_type=chosen.object_type,
                        )
                    ],
                    metadata={
                        "planner": "DeterministicMutationPilotPlanner",
                        "planner_is_ai": False,
                        "operation_mode": "resize_1_percent",
                        "customer_content_changed_on_working_copy": False,
                    },
                )
            if self.preferred_mode == "resize":
                return None

        fallback = self.font_planner.plan(inspection, source_token=source_token)
        if fallback is not None:
            fallback.metadata["operation_mode"] = "font_size_plus_5_percent"
        return fallback


class PlannerOutputError(ValueError):
    pass


def validate_planner_output(payload: object) -> MutationPlanV1:
    """Strict trust boundary for future local/remote planner JSON."""

    try:
        return MutationPlanV1.model_validate(payload)
    except Exception as exc:
        raise PlannerOutputError(f"planner output is not MutationPlanV1: {exc}") from exc
