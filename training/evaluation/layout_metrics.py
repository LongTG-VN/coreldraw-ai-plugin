"""Metrics that do not depend on a learned visual critic."""

from __future__ import annotations

from itertools import combinations

from training.evaluation.hierarchy import evaluate_hierarchy
from training.typography.fitting import measure_text
from training.schemas.design import BoundingBox, DesignDocument, DesignElement


def _area(bbox: BoundingBox) -> float:
    return float(bbox.width) * float(bbox.height)


def _intersection(first: BoundingBox, second: BoundingBox) -> float:
    left = max(float(first.x), float(second.x))
    top = max(float(first.y), float(second.y))
    right = min(
        float(first.x + first.width),
        float(second.x + second.width),
    )
    bottom = min(
        float(first.y + first.height),
        float(second.y + second.height),
    )
    return max(0.0, right - left) * max(0.0, bottom - top)


def _alignment_consistency(elements: list[DesignElement]) -> float:
    pairs = list(combinations(elements, 2))
    if not pairs:
        return 1.0
    tolerance = 0.01
    aligned = 0
    for first, second in pairs:
        first_points = (
            float(first.bbox_norm.x),
            float(first.bbox_norm.x + first.bbox_norm.width / 2),
            float(first.bbox_norm.x + first.bbox_norm.width),
        )
        second_points = (
            float(second.bbox_norm.x),
            float(second.bbox_norm.x + second.bbox_norm.width / 2),
            float(second.bbox_norm.x + second.bbox_norm.width),
        )
        if any(abs(left - right) <= tolerance for left, right in zip(first_points, second_points)):
            aligned += 1
    return aligned / len(pairs)


def evaluate_layout(document: DesignDocument) -> dict[str, float | int]:
    elements = [element for element in document.elements if element.type != "group"]
    content_elements = [
        element
        for element in elements
        if element.id != "background" and element.layer.casefold() != "background"
    ]
    canvas_area = float(document.canvas.width) * float(document.canvas.height)
    total_element_area = sum(_area(element.bbox) for element in content_elements)
    overlap_area = sum(
        _intersection(first.bbox, second.bbox)
        for first, second in combinations(content_elements, 2)
    )
    text_sizes = [
        float(element.text.font_size)
        for element in content_elements
        if element.text is not None and element.text.font_size is not None
    ]
    hierarchy_ratio = (
        max(text_sizes) / min(text_sizes)
        if len(text_sizes) >= 2 and min(text_sizes) > 0
        else 1.0
    )
    tiny_text_count = sum(
        float(element.bbox_norm.height) < 0.025
        for element in content_elements
        if element.text is not None
    )
    text_element_count = len(text_sizes)
    text_overflow_amounts: list[float] = []
    for element in content_elements:
        if element.text is None:
            continue
        font_size = float(element.text.font_size or 24)
        box_width = float(element.bbox.width)
        box_height = float(element.bbox.height)
        measured = measure_text(
            element.text.content,
            box_width=box_width,
            font_size=font_size,
            family=element.text.font_family,
            line_height=element.text.line_height,
        )
        overflow = max(0.0, measured.height - box_height) / max(box_height, 1e-6)
        text_overflow_amounts.append(min(overflow, 1.0))
    signatures = [
        (
            element.type,
            round(float(element.bbox_norm.x), 4),
            round(float(element.bbox_norm.y), 4),
            round(float(element.bbox_norm.width), 4),
            round(float(element.bbox_norm.height), 4),
            element.text.content.casefold() if element.text is not None else None,
        )
        for element in content_elements
    ]
    duplicate_element_count = len(signatures) - len(set(signatures))
    element_ids = [element.id for element in document.elements]
    duplicate_id_count = len(element_ids) - len(set(element_ids))
    invalid_dimension_count = sum(
        float(element.bbox.width) <= 0 or float(element.bbox.height) <= 0
        for element in elements
    )
    outside_count = sum(
        float(element.bbox_norm.x) < 0
        or float(element.bbox_norm.y) < 0
        or float(element.bbox_norm.x + element.bbox_norm.width) > 1
        or float(element.bbox_norm.y + element.bbox_norm.height) > 1
        for element in elements
    )
    bbox_validity = 1.0 if invalid_dimension_count == 0 else 0.0
    normalized_validity = 1.0 if outside_count == 0 else 0.0
    coverage = min(total_element_area / canvas_area, 1.0) if canvas_area else 0.0
    return {
        "bbox_validity": bbox_validity,
        "normalized_coordinate_validity": normalized_validity,
        "outside_canvas_rate": outside_count / len(elements) if elements else 0.0,
        "overlap_ratio": overlap_area / canvas_area if canvas_area else 0.0,
        "alignment_consistency": _alignment_consistency(content_elements),
        "coverage": coverage,
        "whitespace": 1.0 - coverage,
        "text_hierarchy_ratio": hierarchy_ratio,
        "element_count": len(elements),
        "content_element_count": len(content_elements),
        "background_element_count": len(elements) - len(content_elements),
        "text_element_count": text_element_count,
        "tiny_text_count": tiny_text_count,
        "tiny_text_rate": (
            tiny_text_count / text_element_count if text_element_count else 0.0
        ),
        "text_fit_rate": (
            sum(amount == 0 for amount in text_overflow_amounts)
            / len(text_overflow_amounts)
            if text_overflow_amounts
            else 1.0
        ),
        "text_overflow_rate": (
            sum(text_overflow_amounts) / len(text_overflow_amounts)
            if text_overflow_amounts
            else 0.0
        ),
        "text_overflow_count": sum(amount > 0 for amount in text_overflow_amounts),
        "invalid_dimension_count": invalid_dimension_count,
        "duplicate_id_count": duplicate_id_count,
        "duplicate_element_count": duplicate_element_count,
        "duplicate_element_rate": (
            duplicate_element_count / len(content_elements)
            if content_elements
            else 0.0
        ),
        "excessive_element_count": max(0, len(content_elements) - 16),
        **evaluate_hierarchy(document),
    }
