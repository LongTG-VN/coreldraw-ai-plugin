"""Token-bounded document summaries for deterministic or external planners."""

from __future__ import annotations

from typing import Any

from training.company_archive.models import CdrInspectionV1
from training.corel_agent.models import DocumentContextV1, TextCandidateSummaryV1
from training.corel_operator.capabilities import inspect_operator_capabilities


def _preview(value: str, limit: int = 140) -> str:
    collapsed = " ".join(value.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


def build_document_context(
    inspection: CdrInspectionV1,
    *,
    document_id: str,
    include_text: bool = False,
    max_text_candidates: int = 25,
) -> DocumentContextV1:
    if not 0 <= max_text_candidates <= 25:
        raise ValueError("max_text_candidates must be in 0..25")
    capabilities = inspect_operator_capabilities(inspection)
    text_objects = [
        item
        for item in inspection.objects
        if item.object_type == "text" and item.text is not None
    ]
    text_objects.sort(key=lambda item: (item.z_index, item.object_id))
    relevant = [
        TextCandidateSummaryV1(
            object_id=item.object_id,
            text_preview=_preview(item.text or "") if include_text else None,
            font_family=item.font_family,
            font_size=item.font_size,
            bbox_norm=item.bbox_norm,
        )
        for item in text_objects[:max_text_candidates]
    ]
    return DocumentContextV1(
        document_id=document_id,
        pages=inspection.page_count,
        page_width=inspection.page_width,
        page_height=inspection.page_height,
        unit=inspection.unit,
        object_count=inspection.object_count,
        text_count=inspection.text_object_count,
        bitmap_count=inspection.bitmap_count,
        vector_count=inspection.vector_count,
        group_count=inspection.group_count,
        operation_candidate_counts={
            name: len(ids)
            for name, ids in capabilities.operation_candidates.items()
        },
        relevant_text=relevant,
        text_included=include_text,
        truncated=len(text_objects) > max_text_candidates,
    )


def get_object_details(inspection: CdrInspectionV1, object_id: str) -> dict[str, Any]:
    matches = [item for item in inspection.objects if item.object_id == object_id]
    if len(matches) != 1:
        raise KeyError("object ID is missing or ambiguous")
    item = matches[0]
    return {
        "object_id": item.object_id,
        "object_type": item.object_type,
        "bbox": item.bbox,
        "bbox_norm": item.bbox_norm,
        "rotation": item.rotation,
        "parent_id": item.parent_id,
        "text": item.text,
        "font_family": item.font_family,
        "font_size": item.font_size,
        "locked": bool(item.metadata.get("locked", False)),
    }


__all__ = ["build_document_context", "get_object_details"]
