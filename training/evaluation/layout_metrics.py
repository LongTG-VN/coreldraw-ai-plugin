"""Metrics that do not depend on a learned visual critic."""

from __future__ import annotations

from itertools import combinations

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
    coverage = min(total_element_area / canvas_area, 1.0) if canvas_area else 0.0
    return {
        "bbox_validity": 1.0,
        "normalized_coordinate_validity": 1.0,
        "outside_canvas_rate": 0.0,
        "overlap_ratio": overlap_area / canvas_area if canvas_area else 0.0,
        "alignment_consistency": _alignment_consistency(content_elements),
        "coverage": coverage,
        "whitespace": 1.0 - coverage,
        "text_hierarchy_ratio": hierarchy_ratio,
        "element_count": len(elements),
        "content_element_count": len(content_elements),
        "background_element_count": len(elements) - len(content_elements),
        "text_element_count": len(text_sizes),
    }
