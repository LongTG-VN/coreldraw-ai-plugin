"""Model-agnostic planner boundary; no planner can emit raw COM instructions."""

from __future__ import annotations

import hashlib
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


class PlannerOutputError(ValueError):
    pass


def validate_planner_output(payload: object) -> MutationPlanV1:
    """Strict trust boundary for future local/remote planner JSON."""

    try:
        return MutationPlanV1.model_validate(payload)
    except Exception as exc:
        raise PlannerOutputError(f"planner output is not MutationPlanV1: {exc}") from exc
