"""Deterministic structural diversity metrics for best-of-N candidates."""

from __future__ import annotations

from itertools import combinations

from training.schemas.design import DesignDocument, DesignElement


def _features(element: DesignElement) -> tuple[float, ...]:
    bbox = element.bbox_norm
    type_code = {
        "text": 0.0,
        "rectangle": 0.2,
        "ellipse": 0.4,
        "image": 0.6,
        "svg": 0.8,
        "other": 1.0,
        "group": 1.0,
    }[element.type]
    return (
        float(bbox.x),
        float(bbox.y),
        float(bbox.width),
        float(bbox.height),
        type_code,
    )


def layout_distance(first: DesignDocument, second: DesignDocument) -> float:
    first_elements = sorted(
        (item for item in first.elements if item.layer.casefold() != "background"),
        key=lambda item: item.z_index,
    )
    second_elements = sorted(
        (item for item in second.elements if item.layer.casefold() != "background"),
        key=lambda item: item.z_index,
    )
    shared = min(len(first_elements), len(second_elements))
    distances: list[float] = []
    for index in range(shared):
        left = _features(first_elements[index])
        right = _features(second_elements[index])
        distances.append(sum(abs(a - b) for a, b in zip(left, right)) / len(left))
    geometry_distance = sum(distances) / len(distances) if distances else 0.0
    count_distance = abs(len(first_elements) - len(second_elements)) / max(
        len(first_elements), len(second_elements), 1
    )
    first_text = [
        item.text.content.casefold()
        for item in first_elements
        if item.text is not None
    ]
    second_text = [
        item.text.content.casefold()
        for item in second_elements
        if item.text is not None
    ]
    text_distance = 0.0 if first_text == second_text else 0.25
    return max(
        0.0,
        min(0.65 * geometry_distance + 0.25 * count_distance + text_distance, 1.0),
    )


def candidate_diversity(documents: dict[str, DesignDocument]) -> dict[str, object]:
    pairs = []
    for (first_id, first), (second_id, second) in combinations(documents.items(), 2):
        distance = layout_distance(first, second)
        pairs.append(
            {
                "first": first_id,
                "second": second_id,
                "layout_distance": distance,
                "similarity": 1 - distance,
            }
        )
    average = (
        sum(float(pair["layout_distance"]) for pair in pairs) / len(pairs)
        if pairs
        else 0.0
    )
    if not documents:
        meaningful = False
        warning = "No valid candidates are available for diversity measurement."
    elif len(documents) == 1:
        meaningful = False
        warning = "Only one valid candidate; diversity cannot be established."
    else:
        meaningful = average >= 0.08
        warning = (
            None
            if meaningful
            else "Candidates are too structurally similar for useful best-of-N."
        )
    return {
        "scale": "0..1",
        "average_layout_distance": average,
        "meaningful_diversity": meaningful,
        "warning": warning,
        "pairs": pairs,
    }
