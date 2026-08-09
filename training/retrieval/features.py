"""Reproducible structural feature extraction from canonical designs."""

from __future__ import annotations

import math
from collections import Counter
from itertools import combinations

from training.retrieval.models import (
    HierarchySummaryItemV1,
    NormalizedElementFeatureV1,
    PlacementSummaryV1,
    ReferenceDesignSummaryV1,
    ReferenceFeaturesV1,
    ReferenceMetadataV1,
    SpacingSummaryV1,
    TextDensity,
)
from training.schemas.design import ColorSpec, DesignDocument, DesignElement


def _role(element: DesignElement, largest_text_id: str | None) -> str:
    value = " ".join(
        str(part or "")
        for part in (
            element.id,
            element.name,
            element.layer,
            element.metadata.get("label_name"),
        )
    ).casefold()
    mappings = (
        ("cta", ("call to action", "cta", "button")),
        ("headline", ("title", "headline", "heading")),
        ("subtitle", ("subtitle", "subheading")),
        ("price", ("price", "gia")),
        ("contact", ("phone", "website", "social", "contact", "location")),
        ("hero", ("hero", "main image", "product")),
        ("body", ("body", "detail", "menu item")),
        ("background", ("background",)),
    )
    for role, needles in mappings:
        if any(needle in value for needle in needles):
            return role
    if element.id == largest_text_id:
        return "headline"
    if element.type == "text":
        return "body"
    if element.type in {"image", "svg"}:
        return "hero"
    return element.type


def _region(x: float, y: float, width: float, height: float) -> str:
    center_x = x + width / 2
    center_y = y + height / 2
    horizontal = "left" if center_x < 1 / 3 else "right" if center_x > 2 / 3 else "center"
    vertical = "top" if center_y < 1 / 3 else "bottom" if center_y > 2 / 3 else "middle"
    return f"{vertical}_{horizontal}"


def _intersection(first: DesignElement, second: DesignElement) -> float:
    a, b = first.bbox_norm, second.bbox_norm
    left, top = max(float(a.x), float(b.x)), max(float(a.y), float(b.y))
    right = min(float(a.x + a.width), float(b.x + b.width))
    bottom = min(float(a.y + a.height), float(b.y + b.height))
    return max(0.0, right - left) * max(0.0, bottom - top)


def _color_tag(color: ColorSpec | None) -> str | None:
    if color is None:
        return None
    if color.model == "hex":
        return str(color.values[0]).upper()
    if color.model == "cmyk":
        c, m, y, k = (float(value) / 100 for value in color.values)
        rgb = (
            round(255 * (1 - c) * (1 - k)),
            round(255 * (1 - m) * (1 - k)),
            round(255 * (1 - y) * (1 - k)),
        )
    else:
        rgb = tuple(round(float(value)) for value in color.values[:3])
    return "#" + "".join(f"{max(0, min(255, channel)):02X}" for channel in rgb)


def _density(text_count: int, character_count: int, element_count: int) -> TextDensity:
    if text_count >= 8 or character_count >= 260 or element_count >= 14:
        return "high"
    if text_count <= 2 and character_count < 80:
        return "low"
    return "medium"


def _composition(
    alignment: str,
    hero_position: str | None,
    regions: Counter[str],
) -> str:
    if hero_position:
        hero_side = hero_position.split("_")[-1]
        text_side = "right" if hero_side == "left" else "left" if hero_side == "right" else alignment
        return f"hero_{hero_side}_text_{text_side}"
    occupied = sum(count > 0 for count in regions.values())
    if occupied >= 6:
        return "modular_grid"
    if alignment == "center":
        return "centered_stack"
    if alignment in {"left", "right"}:
        return f"{alignment}_aligned_stack"
    return "asymmetric_editorial"


def extract_reference_features(document: DesignDocument) -> ReferenceFeaturesV1:
    elements = [
        element
        for element in document.elements
        if element.type != "group"
        and element.id != "background"
        and element.layer.casefold() != "background"
    ]
    text_elements = [element for element in elements if element.text is not None]
    image_elements = [element for element in elements if element.type in {"image", "svg"}]
    largest_text = max(
        text_elements,
        key=lambda item: float(item.text.font_size or item.bbox_norm.height),
        default=None,
    )
    roles = {element.id: _role(element, largest_text.id if largest_text else None) for element in elements}
    largest_area = max(
        (float(element.bbox_norm.width * element.bbox_norm.height) for element in elements),
        default=1.0,
    )
    boxes = [
        NormalizedElementFeatureV1(
            element_id=element.id,
            role=roles[element.id],
            element_type=element.type,
            x=float(element.bbox_norm.x),
            y=float(element.bbox_norm.y),
            width=float(element.bbox_norm.width),
            height=float(element.bbox_norm.height),
            relative_size=(
                float(element.bbox_norm.width * element.bbox_norm.height) / largest_area
                if largest_area
                else 0
            ),
            region=_region(
                float(element.bbox_norm.x),
                float(element.bbox_norm.y),
                float(element.bbox_norm.width),
                float(element.bbox_norm.height),
            ),
        )
        for element in elements
    ]
    regions: Counter[str] = Counter(box.region for box in boxes)

    alignments = [element.text.alignment for element in text_elements if element.text and element.text.alignment]
    if alignments:
        counts = Counter(alignments)
        winner, winner_count = counts.most_common(1)[0]
        alignment = winner if winner_count / len(alignments) >= 0.6 else "mixed"
    else:
        centers = [float(element.bbox_norm.x + element.bbox_norm.width / 2) for element in elements]
        if not centers:
            alignment = "mixed"
        elif sum(abs(center - 0.5) <= 0.08 for center in centers) / len(centers) >= 0.6:
            alignment = "center"
        elif sum(center < 0.5 for center in centers) / len(centers) >= 0.7:
            alignment = "left"
        elif sum(center > 0.5 for center in centers) / len(centers) >= 0.7:
            alignment = "right"
        else:
            alignment = "mixed"

    if elements:
        margins = {
            "left": min(float(item.bbox_norm.x) for item in elements),
            "top": min(float(item.bbox_norm.y) for item in elements),
            "right": min(float(1 - item.bbox_norm.x - item.bbox_norm.width) for item in elements),
            "bottom": min(float(1 - item.bbox_norm.y - item.bbox_norm.height) for item in elements),
        }
    else:
        margins = {"left": 1.0, "top": 1.0, "right": 1.0, "bottom": 1.0}
    centers_y = sorted(float(item.bbox_norm.y + item.bbox_norm.height / 2) for item in elements)
    gaps = [second - first for first, second in zip(centers_y, centers_y[1:])]
    vertical_rhythm = sum(gaps) / len(gaps) if gaps else 0.0
    total_area = sum(float(item.bbox_norm.width * item.bbox_norm.height) for item in elements)
    overlap = sum(_intersection(first, second) for first, second in combinations(elements, 2))
    whitespace = max(0.0, 1.0 - min(total_area, 1.0))

    text_sizes = [float(item.text.font_size or item.bbox_norm.height) for item in text_elements]
    positive_text_sizes = [value for value in text_sizes if value > 0]
    size_hierarchy = max(positive_text_sizes) / min(positive_text_sizes) if len(positive_text_sizes) > 1 else 1.0
    headline_size = max(positive_text_sizes, default=1.0)
    body_sizes = [
        float(item.text.font_size or item.bbox_norm.height)
        for item in text_elements
        if roles[item.id] == "body"
    ]
    headline_body_ratio = max(1.0, headline_size / (sum(body_sizes) / len(body_sizes))) if body_sizes else 1.0

    cta = next((box for box in boxes if box.role == "cta"), None)
    hero_candidates = [box for box in boxes if box.role == "hero"]
    hero = max(hero_candidates, key=lambda item: float(item.width * item.height), default=None)
    colors = []
    for element in elements:
        color = _color_tag(element.visual.fill)
        if color and color not in colors:
            colors.append(color)
    character_count = sum(len(item.text.content) for item in text_elements if item.text)
    composition = _composition(alignment, hero.region if hero else None, regions)
    return ReferenceFeaturesV1(
        normalized_element_boxes=boxes,
        element_roles=[roles[item.id] for item in elements],
        element_types=[item.type for item in elements],
        element_count=len(elements),
        text_count=len(text_elements),
        image_count=len(image_elements),
        dominant_alignment=alignment,  # type: ignore[arg-type]
        margins={key: max(0.0, min(1.0, value)) for key, value in margins.items()},
        vertical_rhythm=max(0.0, min(1.0, vertical_rhythm)),
        whitespace=whitespace,
        overlap=overlap,
        size_hierarchy=max(1.0, size_hierarchy),
        headline_body_ratio=max(1.0, headline_body_ratio),
        cta_position=cta.region if cta else None,
        hero_position=hero.region if hero else None,
        hero_coverage=float(hero.width * hero.height) if hero else 0.0,
        composition=composition,
        composition_regions=dict(sorted(regions.items())),
        dominant_colors=colors[:12],
        aspect_ratio=float(document.canvas.width) / float(document.canvas.height),
        text_density=_density(len(text_elements), character_count, len(elements)),
    )


def summarize_reference(
    metadata: ReferenceMetadataV1,
    features: ReferenceFeaturesV1,
) -> ReferenceDesignSummaryV1:
    hierarchy = sorted(
        features.normalized_element_boxes,
        key=lambda item: (-float(item.relative_size), item.element_id),
    )
    hierarchy_items: list[HierarchySummaryItemV1] = []
    seen_roles: set[str] = set()
    for item in hierarchy:
        if item.role in seen_roles or item.role == "background":
            continue
        seen_roles.add(item.role)
        hierarchy_items.append(
            HierarchySummaryItemV1(
                role=item.role,
                relative_size=float(item.relative_size),
                region=item.region,
            )
        )
        if len(hierarchy_items) >= 6:
            break
    outer_margin = min(features.margins.values(), default=0.0)
    return ReferenceDesignSummaryV1(
        reference_id=metadata.reference_id,
        category=metadata.category,
        format=metadata.format,
        style=metadata.style_tags[:12],
        palette=(metadata.color_tags or features.dominant_colors)[:8],
        composition=features.composition,
        alignment=features.dominant_alignment,
        hierarchy=hierarchy_items,
        spacing=SpacingSummaryV1(
            outer_margin=max(0.0, min(1.0, outer_margin)),
            section_gap=features.vertical_rhythm,
        ),
        hero=(
            PlacementSummaryV1(
                region=features.hero_position,
                coverage=features.hero_coverage,
            )
            if features.hero_position
            else None
        ),
        cta=(PlacementSummaryV1(region=features.cta_position) if features.cta_position else None),
        text_density=features.text_density,
        element_count=features.element_count,
    )
