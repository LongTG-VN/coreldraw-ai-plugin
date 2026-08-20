"""Conservative autonomous task loop over the policy-gated operator tools."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Protocol

from pydantic import Field

from training.company_archive.models import CdrInspectionV1
from training.corel_operator.models import (
    MutationActionV1,
    MutationPlanV1,
    OperatorResultClass,
    StrictModel,
    TargetSelectorV1,
)
from training.corel_operator.targets import TargetResolutionError, resolve_target


class OperatorTaskStatus(str, Enum):
    PLANNED = "PLANNED"
    AUTO_SUCCESS = "AUTO_SUCCESS"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"


class OperatorTaskRequestV1(StrictModel):
    schema_version: str = "1.0"
    file_id: str = Field(pattern=r"^file:[a-f0-9]{32}$")
    task_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
    instruction: str = Field(min_length=1, max_length=2000)
    execution_confirmed: bool = False


class OperatorTaskRunV1(StrictModel):
    schema_version: str = "1.0"
    task_id: str
    file_id: str
    status: OperatorTaskStatus
    planner: str
    planner_is_ai: bool = False
    plan: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
    visual_qa: dict[str, Any] | None = None
    issues: list[str] = Field(default_factory=list)
    refinement_attempts: int = Field(default=0, ge=0, le=3)


class OperatorAgentBackend(Protocol):
    def inspect_model(self, file_id: str) -> CdrInspectionV1: ...

    def execute_plan(
        self, file_id: str, *, task_id: str, plan: MutationPlanV1 | dict[str, Any]
    ) -> dict[str, Any]: ...

    def visual_qa(self, *, task_id: str) -> dict[str, Any]: ...


class TaskPlanningError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


_QUOTED_REPLACE_RE = re.compile(
    r"(?:đổi|thay|replace)\s+[\"“](?P<old>[^\"”]{1,500})[\"”]"
    r"\s+(?:thành|bằng|with|to)\s+[\"“](?P<new>[^\"”]{1,500})[\"”]",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(
    r"(?:số\s*điện\s*thoại|phone)(?:\s+mới)?\s*(?:thành|bằng|to|=)\s*"
    r"(?P<value>\+?\d[\d .-]{7,20}\d)",
    re.IGNORECASE,
)
_PRICE_RE = re.compile(
    r"(?:giá|price)(?:\s+mới)?\s*(?:thành|bằng|to|=)\s*"
    r"(?P<value>\d[\d., ]{0,12}\s*(?:k|đ|₫|vnd))",
    re.IGNORECASE,
)
_FONT_RE = re.compile(
    r"(?:cỡ\s*chữ|font\s*size)\s+(?P<object_id>[A-Za-z0-9_.:-]+)"
    r"\s*(?:thành|to|=)\s*(?P<value>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_MOVE_RE = re.compile(
    r"(?:di\s*chuyển|move)\s+(?P<object_id>[A-Za-z0-9_.:-]+)"
    r"\s*(?:đến|to)\s*x\s*=\s*(?P<x>-?\d+(?:\.\d+)?)"
    r"\s*[,;]?\s*y\s*=\s*(?P<y>-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_RESIZE_RE = re.compile(
    r"(?:đổi\s*kích\s*thước|resize)\s+(?P<object_id>[A-Za-z0-9_.:-]+)"
    r"\s*(?:thành|to)?\s*width\s*=\s*(?P<width>\d+(?:\.\d+)?)"
    r"\s*[,;]?\s*height\s*=\s*(?P<height>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_SCALE_RE = re.compile(
    r"(?:tăng|scale\s*up)\s+(?P<object_id>[A-Za-z0-9_.:-]+)"
    r"\s+(?P<percent>\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)


class ControlledInstructionPlanner:
    """Parse a small explicit grammar; unsupported language fails closed."""

    name = "ControlledInstructionPlanner"

    @staticmethod
    def _resolve(inspection: CdrInspectionV1, selector: TargetSelectorV1):
        try:
            return resolve_target(inspection.objects, selector)
        except TargetResolutionError as exc:
            raise TaskPlanningError("TARGET_AMBIGUOUS_OR_MISSING", str(exc)) from exc

    def plan(
        self,
        request: OperatorTaskRequestV1,
        inspection: CdrInspectionV1,
    ) -> MutationPlanV1:
        actions: list[MutationActionV1] = []
        instruction = request.instruction

        for match in _QUOTED_REPLACE_RE.finditer(instruction):
            selector = TargetSelectorV1(kind="exact_text", value=match.group("old"))
            target = self._resolve(inspection, selector)
            actions.append(
                MutationActionV1(
                    operation="replace_text",
                    target=selector,
                    value=match.group("new"),
                    precondition_object_type=target.object_type,
                )
            )

        phone_match = _PHONE_RE.search(instruction)
        if phone_match:
            selector = TargetSelectorV1(kind="phone", value="*", object_type="text")
            self._resolve(inspection, selector)
            actions.append(
                MutationActionV1(
                    operation="replace_text",
                    target=selector,
                    value=phone_match.group("value").strip(),
                    precondition_object_type="text",
                )
            )

        price_match = _PRICE_RE.search(instruction)
        if price_match:
            selector = TargetSelectorV1(kind="price", value="*", object_type="text")
            self._resolve(inspection, selector)
            actions.append(
                MutationActionV1(
                    operation="replace_text",
                    target=selector,
                    value=price_match.group("value").strip(),
                    precondition_object_type="text",
                )
            )

        for match in _FONT_RE.finditer(instruction):
            selector = TargetSelectorV1(kind="object_id", value=match.group("object_id"))
            target = self._resolve(inspection, selector)
            if target.object_type != "text":
                raise TaskPlanningError("TARGET_TYPE_MISMATCH", "font-size target is not text")
            size = float(match.group("value"))
            if not 4 <= size <= 300:
                raise TaskPlanningError("VALUE_OUT_OF_BOUNDS", "font size must be in 4..300")
            actions.append(
                MutationActionV1(
                    operation="set_font_size",
                    target=selector,
                    value=size,
                    precondition_object_type="text",
                )
            )

        for match in _MOVE_RE.finditer(instruction):
            selector = TargetSelectorV1(kind="object_id", value=match.group("object_id"))
            target = self._resolve(inspection, selector)
            actions.append(
                MutationActionV1(
                    operation="move",
                    target=selector,
                    value={"x": float(match.group("x")), "y": float(match.group("y"))},
                    precondition_object_type=target.object_type,
                )
            )

        for match in _RESIZE_RE.finditer(instruction):
            selector = TargetSelectorV1(kind="object_id", value=match.group("object_id"))
            target = self._resolve(inspection, selector)
            actions.append(
                MutationActionV1(
                    operation="resize",
                    target=selector,
                    value={
                        "width": float(match.group("width")),
                        "height": float(match.group("height")),
                    },
                    precondition_object_type=target.object_type,
                )
            )

        for match in _SCALE_RE.finditer(instruction):
            selector = TargetSelectorV1(kind="object_id", value=match.group("object_id"))
            target = self._resolve(inspection, selector)
            item = next(obj for obj in inspection.objects if obj.object_id == target.object_id)
            percent = float(match.group("percent"))
            if not 0 < percent <= 20:
                raise TaskPlanningError("VALUE_OUT_OF_BOUNDS", "scale increase must be in 0..20%")
            scale = 1 + percent / 100
            actions.append(
                MutationActionV1(
                    operation="resize",
                    target=selector,
                    value={
                        "width": round(item.bbox["width"] * scale, 6),
                        "height": round(item.bbox["height"] * scale, 6),
                    },
                    precondition_object_type=target.object_type,
                )
            )

        if not actions:
            raise TaskPlanningError(
                "UNSUPPORTED_INSTRUCTION",
                "instruction did not match the bounded operator grammar",
            )
        if len(actions) > 10:
            raise TaskPlanningError("MAXIMUM_SCOPE_EXCEEDED", "task exceeds 10 actions")
        return MutationPlanV1(
            plan_id=request.task_id,
            intent=request.instruction,
            source="deterministic",
            actions=actions,
            metadata={
                "planner": self.name,
                "planner_is_ai": False,
                "business_values_source": "explicit_instruction",
                "maximum_task_actions": 10,
            },
        )


class AutonomousOperatorAgent:
    """Inspect, plan, execute, validate, and stop on uncertainty."""

    def __init__(
        self,
        backend: OperatorAgentBackend,
        planner: ControlledInstructionPlanner | None = None,
    ) -> None:
        self.backend = backend
        self.planner = planner or ControlledInstructionPlanner()

    def run(self, request: OperatorTaskRequestV1) -> OperatorTaskRunV1:
        try:
            inspection = self.backend.inspect_model(request.file_id)
            plan = self.planner.plan(request, inspection)
        except TaskPlanningError as exc:
            status = (
                OperatorTaskStatus.NEEDS_REVIEW
                if exc.code == "TARGET_AMBIGUOUS_OR_MISSING"
                else OperatorTaskStatus.UNSUPPORTED
            )
            return OperatorTaskRunV1(
                task_id=request.task_id,
                file_id=request.file_id,
                status=status,
                planner=self.planner.name,
                issues=[f"{exc.code}: {exc}"],
            )
        plan_payload = plan.model_dump(mode="json")
        if not request.execution_confirmed:
            return OperatorTaskRunV1(
                task_id=request.task_id,
                file_id=request.file_id,
                status=OperatorTaskStatus.PLANNED,
                planner=self.planner.name,
                plan=plan_payload,
            )

        try:
            execution = self.backend.execute_plan(
                request.file_id,
                task_id=request.task_id,
                plan=plan,
            )
        except Exception as exc:
            return OperatorTaskRunV1(
                task_id=request.task_id,
                file_id=request.file_id,
                status=OperatorTaskStatus.FAILED,
                planner=self.planner.name,
                plan=plan_payload,
                issues=[f"EXECUTION_FAILURE: {exc}"],
            )
        result = str(execution.get("result", "FAILED"))
        if result != OperatorResultClass.AUTO_SUCCESS.value:
            status = {
                OperatorResultClass.NEEDS_REVIEW.value: OperatorTaskStatus.NEEDS_REVIEW,
                OperatorResultClass.UNSUPPORTED.value: OperatorTaskStatus.UNSUPPORTED,
            }.get(result, OperatorTaskStatus.FAILED)
            return OperatorTaskRunV1(
                task_id=request.task_id,
                file_id=request.file_id,
                status=status,
                planner=self.planner.name,
                plan=plan_payload,
                execution=execution,
                issues=[str(execution.get("error_code") or result)],
            )
        visual = self.backend.visual_qa(task_id=request.task_id)
        status = (
            OperatorTaskStatus.AUTO_SUCCESS
            if visual.get("status") == "PASS"
            else OperatorTaskStatus.NEEDS_REVIEW
        )
        return OperatorTaskRunV1(
            task_id=request.task_id,
            file_id=request.file_id,
            status=status,
            planner=self.planner.name,
            plan=plan_payload,
            execution=execution,
            visual_qa=visual,
            issues=list(visual.get("issues", [])),
        )


__all__ = [
    "AutonomousOperatorAgent",
    "ControlledInstructionPlanner",
    "OperatorTaskRequestV1",
    "OperatorTaskRunV1",
    "OperatorTaskStatus",
    "TaskPlanningError",
]
