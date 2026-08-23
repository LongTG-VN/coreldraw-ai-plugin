"""Model-agnostic planner boundary; no planner can emit raw COM instructions."""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.corel_operator.models import (
    MutationActionV1,
    MutationDependencyV1,
    MutationPlanV1,
    TargetSelectorV1,
)


def _container_dependency(item: CdrObjectV1) -> list[MutationDependencyV1]:
    if not item.parent_id:
        return []
    return [
        MutationDependencyV1(
            object_id=item.parent_id,
            kind="DEPENDENT_CONTAINER",
        )
    ]


class StructuredOperatorPlanner(Protocol):
    def plan(self, inspection: CdrInspectionV1, *, source_token: str) -> MutationPlanV1 | None: ...


def _stable_targetable(objects: list[CdrObjectV1]) -> list[CdrObjectV1]:
    """Return objects addressable by a unique stable inspector ID.

    Corel object names are not identifiers: real documents commonly contain
    blank and duplicate names.  Runtime mutation uses ``operator_object_id``.
    """

    counts: dict[str, int] = {}
    for item in objects:
        counts[item.object_id] = counts.get(item.object_id, 0) + 1
    return [item for item in objects if item.object_id and counts[item.object_id] == 1]


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
            for item in _stable_targetable(inspection.objects)
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
                    dependencies=_container_dependency(chosen),
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


def _replace_digits_in_match(text: str, match: re.Match[str]) -> str:
    """Create explicit benchmark copy without changing length or separators."""

    output = list(text)
    for index in range(match.start(), match.end()):
        if output[index].isdigit():
            output[index] = str((int(output[index]) + 1) % 10)
    return "".join(output)


def _same_length_benchmark_text(text: str) -> str:
    """Replace letters only, preserving layout-significant whitespace/punctuation."""

    return "".join(
        ("Y" if character.casefold() == "x" else "X")
        if character.isalpha()
        else character
        for character in text
    )


class DeterministicMutationPilotPlanner:
    """Diversify safe mechanical edits without making aesthetic decisions."""

    def __init__(
        self,
        *,
        preferred_mode: str = "auto",
    ) -> None:
        if preferred_mode not in {
            "auto",
            "font",
            "replace",
            "move",
            "resize",
            "multi",
        }:
            raise ValueError("unsupported pilot operation mode")
        self.font_planner = DeterministicSafePilotPlanner()
        self.preferred_mode = preferred_mode

    @staticmethod
    def _base_candidates(inspection: CdrInspectionV1) -> list[CdrObjectV1]:
        return [
            item
            for item in _stable_targetable(inspection.objects)
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
            else {"font": 0, "replace": 1, "move": 2, "resize": 3, "multi": 4}[
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
                and item.font_family
                and (_PHONE.search(item.text) or _PRICE.search(item.text))
            ]
            if replaceable:
                chosen = sorted(replaceable, key=lambda item: item.object_id)[0]
                source_text = chosen.text or ""
                phone_match = _PHONE.search(source_text)
                price_match = _PRICE.search(source_text)
                matched = phone_match or price_match
                assert matched is not None
                is_phone = phone_match is not None
                replacement = _replace_digits_in_match(source_text, matched)
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
                            dependencies=_container_dependency(chosen),
                        )
                    ],
                    metadata={
                        "planner": "DeterministicMutationPilotPlanner",
                        "planner_is_ai": False,
                        "operation_mode": "replace_phone" if is_phone else "replace_price",
                        "benchmark_sample_data": True,
                        "customer_content_changed_on_working_copy": True,
                        "replacement_scope": "matched_substring",
                        "replacement_length_preserved": True,
                    },
                )
            if self.preferred_mode == "replace":
                text_counts: dict[str, int] = {}
                for item in candidates:
                    normalized = (item.text or "").strip().casefold()
                    if item.object_type == "text" and normalized:
                        text_counts[normalized] = text_counts.get(normalized, 0) + 1
                benchmarkable = [
                    item
                    for item in candidates
                    if item.object_type == "text"
                    and (item.text or "").strip()
                    # Some legacy numeric display objects report themselves as
                    # cdrTextShape but silently ignore every supported
                    # TextRange replacement.  Keep the benchmark fallback on a
                    # conventional editable-text profile; exact postconditions
                    # still fail closed and roll back any silent no-op.
                    and any(character.isalpha() for character in item.text or "")
                    and item.font_family
                    and item.font_size is not None
                    # Display headlines are ordinary editable text too.  Keep
                    # the established 72 pt upper bound used by the bounded
                    # typography planner instead of excluding safe, stable
                    # headline objects solely for being larger than body copy.
                    and 3.0 <= float(item.font_size) <= 72.0
                    and text_counts[(item.text or "").strip().casefold()] == 1
                ]
                if not benchmarkable:
                    return None
                chosen = sorted(
                    benchmarkable,
                    key=lambda item: (len((item.text or "").strip()), item.object_id),
                )[0]
                return MutationPlanV1(
                    plan_id=plan_id,
                    intent="verify one unique text replacement with explicit benchmark copy",
                    source="deterministic",
                    actions=[
                        MutationActionV1(
                            operation="replace_text",
                            target=TargetSelectorV1(
                                kind="object_id",
                                value=chosen.object_id,
                                object_type="text",
                            ),
                            value=_same_length_benchmark_text(chosen.text or ""),
                            precondition_object_type="text",
                            dependencies=_container_dependency(chosen),
                        )
                    ],
                    metadata={
                        "planner": "DeterministicMutationPilotPlanner",
                        "planner_is_ai": False,
                        "operation_mode": "replace_benchmark_text",
                        "benchmark_sample_data": True,
                        "customer_content_changed_on_working_copy": True,
                        "replacement_scope": "alphabetic_characters",
                        "replacement_length_preserved": True,
                    },
                )

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
                # Real evidence showed both terminal MOVE failures on text
                # targets while every non-text MOVE succeeded.  Prefer simple
                # vector/rectangle objects when the same document offers one;
                # text remains a bounded fallback rather than being disabled.
                chosen = sorted(
                    movable,
                    key=lambda item: (item.object_type == "text", item.object_id),
                )[0]
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

        if mode == 4:
            multi_targets = [
                item
                for item in candidates
                if item.parent_id is None
                and item.object_type not in {"group", "text"}
                and item.bbox["width"] > 0
                and item.bbox["height"] > 0
                and item.bbox["x"] + item.bbox["width"] * 1.01 + 1
                <= inspection.page_width
                and item.bbox["y"] + item.bbox["height"] * 1.01 + 1
                <= inspection.page_height
            ]
            if multi_targets:
                chosen = sorted(multi_targets, key=lambda item: item.object_id)[0]
                selector = TargetSelectorV1(
                    kind="object_id",
                    value=chosen.object_id,
                    object_type=chosen.object_type,
                )
                return MutationPlanV1(
                    plan_id=plan_id,
                    intent="verify one bounded move and resize in one transaction",
                    source="deterministic",
                    actions=[
                        MutationActionV1(
                            # Resize first because Corel sizes around the active
                            # reference point.  The final relative Move then
                            # establishes the exact page-coordinate postcondition.
                            operation="resize",
                            target=selector,
                            value={
                                "width": round(chosen.bbox["width"] * 1.01, 6),
                                "height": round(chosen.bbox["height"] * 1.01, 6),
                            },
                            precondition_object_type=chosen.object_type,
                        ),
                        MutationActionV1(
                            operation="move",
                            target=selector,
                            value={
                                "x": chosen.bbox["x"] + 1,
                                "y": chosen.bbox["y"] + 1,
                            },
                            precondition_object_type=chosen.object_type,
                        ),
                    ],
                    metadata={
                        "planner": "DeterministicMutationPilotPlanner",
                        "planner_is_ai": False,
                        "operation_mode": "multi_move_resize",
                        "customer_content_changed_on_working_copy": False,
                        "single_transaction_required": True,
                    },
                )
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
