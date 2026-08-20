"""Deterministic capability census for one inspected Corel document."""

from __future__ import annotations

import re
from collections import Counter
from typing import Literal

from pydantic import Field

from training.company_archive.models import CdrInspectionV1
from training.corel_operator.models import StrictModel


_PHONE_RE = re.compile(r"(?<!\d)(?:\+?84|0)(?:[ .-]?\d){8,10}(?!\d)")
_PRICE_RE = re.compile(
    r"(?i)(?<!\w)(?:\d{1,3}(?:[., ]\d{3})+|\d+)(?:\s?)(?:k|đ|₫|vnd)(?!\w)"
)


class OperatorCapabilityReportV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    object_count: int = Field(ge=0)
    stable_target_count: int = Field(ge=0)
    unnamed_corel_name_count: int = Field(ge=0)
    duplicate_corel_name_count: int = Field(ge=0)
    editable_text_target_count: int = Field(ge=0)
    phone_target_count: int = Field(ge=0)
    price_target_count: int = Field(ge=0)
    movable_target_count: int = Field(ge=0)
    resizable_target_count: int = Field(ge=0)
    operation_candidates: dict[str, list[str]]


def inspect_operator_capabilities(
    inspection: CdrInspectionV1,
) -> OperatorCapabilityReportV1:
    id_counts = Counter(item.object_id for item in inspection.objects)
    name_counts = Counter(item.corel_name for item in inspection.objects if item.corel_name)
    stable = [
        item
        for item in inspection.objects
        if item.object_id and id_counts[item.object_id] == 1
    ]
    editable_text = [
        item
        for item in stable
        if item.object_type == "text"
        and item.text is not None
        and not bool(item.metadata.get("locked", False))
    ]
    phones = [item for item in editable_text if _PHONE_RE.search(item.text or "")]
    prices = [item for item in editable_text if _PRICE_RE.search(item.text or "")]
    movable = [
        item
        for item in stable
        if item.parent_id is None
        and item.object_type != "group"
        and not bool(item.metadata.get("locked", False))
        and not bool(item.metadata.get("bbox_clipped_to_page", False))
    ]
    resizable = [
        item
        for item in movable
        if item.object_type != "group"
        and item.bbox["width"] > 0
        and item.bbox["height"] > 0
    ]
    duplicate_name_objects = sum(
        1
        for item in inspection.objects
        if item.corel_name and name_counts[item.corel_name] > 1
    )
    return OperatorCapabilityReportV1(
        object_count=inspection.object_count,
        stable_target_count=len(stable),
        unnamed_corel_name_count=sum(not item.corel_name for item in inspection.objects),
        duplicate_corel_name_count=duplicate_name_objects,
        editable_text_target_count=len(editable_text),
        phone_target_count=len(phones),
        price_target_count=len(prices),
        movable_target_count=len(movable),
        resizable_target_count=len(resizable),
        operation_candidates={
            "replace_text": [item.object_id for item in editable_text],
            "replace_phone": [item.object_id for item in phones],
            "replace_price": [item.object_id for item in prices],
            "move": [item.object_id for item in movable],
            "resize": [item.object_id for item in resizable],
            "set_font_size": [
                item.object_id for item in editable_text if item.font_size is not None
            ],
        },
    )


__all__ = ["OperatorCapabilityReportV1", "inspect_operator_capabilities"]
