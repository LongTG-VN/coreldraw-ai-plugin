"""Role-aware hierarchy and dense-layout metrics."""

from __future__ import annotations

import math
import statistics
from collections import Counter

from training.typography.fitting import infer_text_role
from training.schemas.design import DesignDocument, DesignElement


def _clamp(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def _alignment_consistency(elements: list[DesignElement]) -> float:
    if len(elements) < 2:
        return 1.0
    right_edges = [float(item.bbox_norm.x + item.bbox_norm.width) for item in elements]
    spread = statistics.pstdev(right_edges)
    return _clamp(1 - spread / 0.08)


def evaluate_hierarchy(document: DesignDocument) -> dict[str, float | int]:
    texts = [item for item in document.elements if item.text is not None]
    if not texts:
        return {
            "headline_dominance": 0.0,
            "primary_secondary_ratio": 1.0,
            "cta_emphasis": 0.0,
            "price_emphasis": 0.0,
            "focal_point_score": 0.0,
            "section_hierarchy_score": 0.0,
            "equal_size_text_rate": 0.0,
            "price_alignment_consistency": 1.0,
            "price_element_count": 0,
        }
    sizes = [float(item.text.font_size or 0) for item in texts]
    largest = max(sizes)
    roles = {item.id: infer_text_role(item, largest_font=largest) for item in texts}
    body_sizes = [
        float(item.text.font_size or 0)
        for item in texts
        if roles[item.id] in {"body", "menu_item", "subtitle"}
    ]
    body = statistics.median(body_sizes or sizes)
    headlines = [item for item in texts if roles[item.id] == "headline"]
    ctas = [item for item in texts if roles[item.id] == "cta"]
    prices = [item for item in texts if roles[item.id] == "price"]
    headline_size = max(
        (float(item.text.font_size or 0) for item in headlines),
        default=largest,
    )
    ratio = headline_size / max(body, 1e-6)
    headline_dominance = _clamp(1 - abs(math.log(max(ratio, 1e-6) / 2.4)) / 1.5)
    cta_ratio = statistics.mean(
        [float(item.text.font_size or 0) / max(body, 1e-6) for item in ctas]
    ) if ctas else 0.0
    price_ratio = statistics.mean(
        [float(item.text.font_size or 0) / max(body, 1e-6) for item in prices]
    ) if prices else 0.0
    buckets = Counter(round(size / max(body, 1e-6), 1) for size in sizes)
    equal_size_rate = max(buckets.values()) / len(sizes)
    distinct_levels = len(buckets)
    focal = max(
        (
            float(item.bbox_norm.width * item.bbox_norm.height)
            * (float(item.text.font_size or 0) / max(largest, 1e-6))
            for item in texts
        ),
        default=0.0,
    )
    return {
        "headline_dominance": headline_dominance,
        "primary_secondary_ratio": ratio,
        "cta_emphasis": _clamp(cta_ratio / 1.25) if ctas else 0.5,
        "price_emphasis": _clamp(price_ratio / 1.15) if prices else 0.5,
        "focal_point_score": _clamp(focal / 0.12),
        "section_hierarchy_score": _clamp(distinct_levels / min(len(texts), 4)),
        "equal_size_text_rate": equal_size_rate,
        "price_alignment_consistency": _alignment_consistency(prices),
        "price_element_count": len(prices),
    }
