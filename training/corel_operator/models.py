"""Strict contracts for bounded, model-agnostic Corel operator plans."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OperatorResultClass(str, Enum):
    AUTO_SUCCESS = "AUTO_SUCCESS"
    SUCCESS_WITH_WARNING = "SUCCESS_WITH_WARNING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"


class SelectorKind(str, Enum):
    OBJECT_ID = "object_id"
    COREL_NAME = "corel_name"
    EXACT_TEXT = "exact_text"
    CASEFOLD_TEXT = "casefold_text"
    REGEX_TEXT = "regex_text"
    PHONE = "phone"
    PRICE = "price"


class OperationKind(str, Enum):
    REPLACE_TEXT = "replace_text"
    MOVE = "move"
    RESIZE = "resize"
    ROTATE = "rotate"
    SET_FONT = "set_font"
    SET_FONT_SIZE = "set_font_size"


class MutationDependencyKind(str, Enum):
    DEPENDENT_CONTAINER = "DEPENDENT_CONTAINER"
    DEPENDENT_TEXT_FRAME = "DEPENDENT_TEXT_FRAME"


class MutationDependencyV1(StrictModel):
    object_id: str = Field(min_length=1, max_length=160)
    kind: MutationDependencyKind
    allowed_properties: list[Literal["bbox"]] = Field(
        default_factory=lambda: ["bbox"], min_length=1, max_length=1
    )


class TargetSelectorV1(StrictModel):
    kind: SelectorKind
    value: str = Field(min_length=1, max_length=500)
    object_type: str | None = Field(default=None, max_length=40)
    page: int = Field(default=1, ge=1)
    require_unique: bool = True


class MutationActionV1(StrictModel):
    operation: OperationKind
    target: TargetSelectorV1
    value: str | float | dict[str, float]
    allowed_properties: list[str] = Field(default_factory=list, max_length=10)
    maximum_scope: Literal["one_object"] = "one_object"
    precondition_object_type: str | None = Field(default=None, max_length=40)
    dependencies: list[MutationDependencyV1] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_value(self) -> "MutationActionV1":
        if self.operation in {OperationKind.REPLACE_TEXT, OperationKind.SET_FONT}:
            if not isinstance(self.value, str) or not self.value:
                raise ValueError(f"{self.operation.value} requires a non-empty string")
        elif self.operation in {OperationKind.SET_FONT_SIZE, OperationKind.ROTATE}:
            if not isinstance(self.value, (int, float)):
                raise ValueError(f"{self.operation.value} requires a number")
        elif self.operation == OperationKind.MOVE:
            if not isinstance(self.value, dict) or set(self.value) != {"x", "y"}:
                raise ValueError("move requires exactly x and y")
        elif self.operation == OperationKind.RESIZE:
            if not isinstance(self.value, dict) or set(self.value) != {"width", "height"}:
                raise ValueError("resize requires exactly width and height")
            if float(self.value["width"]) <= 0 or float(self.value["height"]) <= 0:
                raise ValueError("resize dimensions must be positive")
        return self


class MutationPlanV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    plan_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    intent: str = Field(min_length=1, max_length=1000)
    source: Literal["human", "fixture", "deterministic", "llm"]
    actions: list[MutationActionV1] = Field(min_length=1, max_length=50)
    expected_object_count_change: Literal[0] = 0
    rollback_on_error: Literal[True] = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResolvedTargetV1(StrictModel):
    object_id: str
    corel_name: str
    object_type: str
    page: int = Field(ge=1)


class OperatorExecutionResultV1(StrictModel):
    result: OperatorResultClass
    plan_id: str
    source_token: str
    working_copy: str | None = None
    preview_before: str | None = None
    preview_after: str | None = None
    pdf_after: str | None = None
    resolved_targets: list[ResolvedTargetV1] = Field(default_factory=list)
    operation_count: int = Field(default=0, ge=0)
    object_count_before: int | None = Field(default=None, ge=0)
    object_count_after: int | None = Field(default=None, ge=0)
    reopened_object_count: int | None = Field(default=None, ge=0)
    source_unchanged: bool
    transaction_committed: bool = False
    rollback_verified: bool = False
    editability_verified: bool = False
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error: str | None = None
    timings_ms: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
