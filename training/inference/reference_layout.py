"""Deterministic structural grounding from compact reference summaries."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from training.evaluation.layout_metrics import evaluate_layout
from training.retrieval.models import ReferenceContextV1, StructuredBriefV1
from training.schemas.design import (
    BoundingBox,
    ColorSpec,
    DesignDocument,
    DesignElement,
    TextSpec,
    VisualSpec,
    normalize_bbox,
)
from training.typography.fitting import infer_text_role


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(float(value), high))


def _content_key(document: DesignDocument) -> int:
    text = "|".join(
        element.text.content for element in document.elements if element.text is not None
    )
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def _set_norm_box(
    document: DesignDocument,
    element_index: int,
    box: tuple[float, float, float, float],
) -> None:
    x, y, width, height = box
    normalized = BoundingBox(x=x, y=y, width=width, height=height)
    canvas = document.canvas
    absolute = BoundingBox(
        x=x * float(canvas.width),
        y=y * float(canvas.height),
        width=width * float(canvas.width),
        height=height * float(canvas.height),
    )
    element = document.elements[element_index]
    element.bbox = absolute
    element.bbox_norm = normalize_bbox(absolute, canvas)


def _capture(prompt: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" .,:;-")
    return None


def _brief_copy(brief: StructuredBriefV1) -> dict[str, str]:
    prompt = brief.prompt
    headline = _capture(
        prompt,
        (
            r"(?:headline|tiêu đề|tên)\s+([^,]+)",
            r"(?:cho|for)\s+([A-ZÀ-Ỹ][A-ZÀ-Ỹ\s]{3,})(?:,|$)",
            r"\b((?:MEGA SALE|GRAND OPENING|GROWTH)\s*[^,]*)",
        ),
    )
    cta = _capture(prompt, (r"CTA\s+([^,]+)", r"(Inbox đặt lịch|Mua ngay|Order Now|Đăng ký)"))
    promotion = _capture(
        prompt,
        (
            r"((?:ưu đãi|giảm|combo|mua\s*1\s*tặng\s*1)[^,]*)",
            r"(quà tặng[^,]*)",
        ),
    )
    body = _capture(
        prompt,
        (
            r"liệt kê\s+([^,]+)",
            r"gồm\s+([^,]+)",
            r"(?:dịch vụ|services?)\s+([^,]+)",
        ),
    )
    result = {}
    if headline:
        result["headline"] = headline
    if cta:
        result["cta"] = cta
    if promotion:
        result["promotion"] = promotion
        result["body"] = promotion
    elif body:
        result["body"] = body
    return result


def _recover_brief_text_elements(
    document: DesignDocument, brief: StructuredBriefV1
) -> int:
    copy = _brief_copy(brief)
    recovered = 0
    used_roles: set[str] = set()
    for element in document.elements:
        if element.text is None:
            continue
        role = str(element.metadata.get("role") or element.name).casefold()
        content = element.text.content.strip()
        looks_serialized = content.startswith(("{'", '{"', "[{'", '[{"'))
        target_role = next(
            (name for name in ("headline", "cta", "promotion", "body") if name in role),
            "headline" if not used_roles else "body",
        )
        if looks_serialized and target_role in copy:
            element.text.content = copy[target_role]
            element.metadata["role"] = target_role
            used_roles.add(target_role)
            recovered += 1
    for element in document.elements:
        if element.text is not None or element.type != "rectangle":
            continue
        intent = element.metadata.get("asset_intent")
        if not isinstance(intent, dict) or not intent.get("placeholder"):
            continue
        role = str(intent.get("role") or "body").casefold()
        target_role = next(
            (name for name in ("headline", "cta", "promotion", "body") if name in role),
            "body",
        )
        content = copy.get(target_role)
        if content is None or target_role in used_roles:
            continue
        element.type = "text"
        element.name = target_role.replace("_", " ").title()
        element.text = TextSpec(
            content=content,
            font_family="Arial",
            font_size=12,
            alignment="left",
        )
        element.metadata = {
            "role": target_role,
            "brief_text_recovery": True,
            "source_placeholder_role": role,
        }
        used_roles.add(target_role)
        recovered += 1
    return recovered


def _synthesize_requested_menu_items(
    document: DesignDocument,
    brief: StructuredBriefV1,
    *,
    benchmark_mode: bool,
) -> int:
    requested = next(
        (
            int(value.removesuffix("_items"))
            for value in brief.requested_elements
            if value.endswith("_items") and value.removesuffix("_items").isdigit()
        ),
        0,
    )
    if requested < 1 or brief.format != "menu":
        return 0
    largest = max(
        (float(element.text.font_size or 0) for element in document.elements if element.text),
        default=0,
    )
    existing_items = [
        element
        for element in document.elements
        if element.text and infer_text_role(element, largest_font=largest) == "menu_item"
    ]
    existing_prices = [
        element
        for element in document.elements
        if element.text and infer_text_role(element, largest_font=largest) == "price"
    ]
    if len(existing_items) >= requested and len(existing_prices) >= requested:
        return 0
    aggregate = re.compile(r"^(?:\d+\s*món(?:\s*chính)?|giá\s*dễ\s*đọc)$", re.IGNORECASE)
    document.elements = [
        element
        for element in document.elements
        if not (element.text and aggregate.fullmatch(element.text.content.strip()))
    ]
    existing_ids = {element.id for element in document.elements}
    canvas = document.canvas
    seed_box = BoundingBox(
        x=float(canvas.width) * 0.08,
        y=float(canvas.height) * 0.25,
        width=float(canvas.width) * 0.65,
        height=float(canvas.height) * 0.06,
    )
    next_z = max((element.z_index for element in document.elements), default=0) + 1
    created = 0
    for index in range(1, requested + 1):
        item_id = f"menu_item_{index:02d}"
        price_id = f"menu_price_{index:02d}"
        if index > len(existing_items) and item_id not in existing_ids:
            document.elements.append(
                DesignElement(
                    id=item_id,
                    name=f"Menu Item {index:02d}",
                    type="text",
                    bbox=seed_box,
                    bbox_norm=normalize_bbox(seed_box, canvas),
                    z_index=next_z,
                    layer="content",
                    text=TextSpec(
                        content=f"[ITEM_{index:02d}]\n[DESCRIPTION_{index:02d}]",
                        font_family="Arial",
                        font_size=11,
                    ),
                    visual=VisualSpec(
                        fill=ColorSpec(model="hex", values=["#181818"])
                    ),
                    metadata={
                        "role": "menu_item",
                        "synthetic_brief_completion": True,
                        "placeholder_only": True,
                        "requires_user_data": True,
                        "content_provenance": (
                            "benchmark_placeholder"
                            if benchmark_mode
                            else "system_placeholder"
                        ),
                        "benchmark_placeholder": benchmark_mode,
                    },
                )
            )
            next_z += 1
            created += 1
        if index > len(existing_prices) and price_id not in existing_ids:
            document.elements.append(
                DesignElement(
                    id=price_id,
                    name=f"Price {index:02d}",
                    type="text",
                    bbox=seed_box,
                    bbox_norm=normalize_bbox(seed_box, canvas),
                    z_index=next_z,
                    layer="content",
                    text=TextSpec(
                        content=f"[PRICE_{index:02d}]",
                        font_family="Arial",
                        font_size=11,
                        alignment="right",
                    ),
                    visual=VisualSpec(
                        fill=ColorSpec(model="hex", values=["#181818"])
                    ),
                    metadata={
                        "role": "price",
                        "synthetic_brief_completion": True,
                        "placeholder_only": True,
                        "requires_user_data": True,
                        "content_provenance": (
                            "benchmark_placeholder"
                            if benchmark_mode
                            else "system_placeholder"
                        ),
                        "benchmark_placeholder": benchmark_mode,
                    },
                )
            )
            next_z += 1
            created += 1
    return created


def _stack_boxes(
    count: int,
    *,
    x: float,
    y_start: float,
    width: float,
    y_end: float,
    gap: float,
) -> list[tuple[float, float, float, float]]:
    if count <= 0:
        return []
    span = max(1e-6, y_end - y_start)
    effective_gap = min(gap, span / max(2 * count - 1, 1))
    available = max(1e-6, span - effective_gap * (count - 1))
    height = min(available / count, 0.13)
    return [
        (x, y_start + index * (height + effective_gap), width, height)
        for index in range(count)
    ]


def apply_reference_layout_guidance(
    document: DesignDocument,
    *,
    brief: StructuredBriefV1,
    context: ReferenceContextV1,
    benchmark_mode: bool = False,
) -> tuple[DesignDocument, dict[str, object]]:
    """Synthesize non-overlapping role regions from reference abstractions.

    Exact source boxes are never consumed. The selected summary contributes
    only composition, alignment, margins, density, and semantic regions.
    """

    if not context.references:
        return document, {"engine": "reference_layout_guidance_v1", "applied": False}
    output = document.model_copy(deep=True)
    brief_text_recovery_count = _recover_brief_text_elements(output, brief)
    placeholder_count_before = sum(
        element.type == "rectangle"
        and isinstance(element.metadata.get("asset_intent"), dict)
        and bool(element.metadata["asset_intent"].get("placeholder"))
        for element in output.elements
    )
    visual_asset_roles = {
        "hero",
        "product",
        "logo",
        "icon",
        "illustration",
        "background_image",
    }
    output.elements = [
        element
        for element in output.elements
        if not (
            element.type == "rectangle"
            and isinstance(element.metadata.get("asset_intent"), dict)
            and bool(element.metadata["asset_intent"].get("placeholder"))
            and str(element.metadata["asset_intent"].get("role") or "").casefold()
            not in visual_asset_roles
        )
    ]
    placeholder_count_after = sum(
        element.type == "rectangle"
        and isinstance(element.metadata.get("asset_intent"), dict)
        and bool(element.metadata["asset_intent"].get("placeholder"))
        for element in output.elements
    )
    placeholder_drop_count = placeholder_count_before - placeholder_count_after
    menu_element_synthesis_count = _synthesize_requested_menu_items(
        output,
        brief,
        benchmark_mode=benchmark_mode,
    )
    before = evaluate_layout(output)
    reference = context.references[_content_key(output) % len(context.references)]
    margin = _clamp(float(reference.spacing.outer_margin), 0.045, 0.085)
    gap = _clamp(float(reference.spacing.section_gap) * 0.22, 0.018, 0.04)
    text_indices = [
        index for index, element in enumerate(output.elements) if element.text is not None
    ]
    shape_indices = [
        index
        for index, element in enumerate(output.elements)
        if element.text is None
        and element.id != "background"
        and element.layer.casefold() != "background"
        and element.type != "group"
    ]
    if not text_indices:
        return output, {"engine": "reference_layout_guidance_v1", "applied": False}

    largest = max(float(output.elements[index].text.font_size or 0) for index in text_indices)
    by_role: dict[str, list[int]] = defaultdict(list)
    for index in text_indices:
        by_role[infer_text_role(output.elements[index], largest_font=largest)].append(index)
    headline_candidates = by_role.pop("headline", []) or [text_indices[0]]
    headline = headline_candidates[:1]
    extra_headlines = headline_candidates[1:]
    for index in headline:
        for values in by_role.values():
            if index in values:
                values.remove(index)
    ctas = by_role.pop("cta", [])
    prices = by_role.pop("price", [])
    subtitles = by_role.pop("subtitle", [])
    menu_items = by_role.pop("menu_item", [])
    bodies = extra_headlines + [index for values in by_role.values() for index in values]
    assigned_roles = {
        **{index: "headline" for index in headline},
        **{index: "subtitle" for index in subtitles},
        **{index: "menu_item" for index in menu_items},
        **{index: "body" for index in bodies},
        **{index: "price" for index in prices},
        **{index: "cta" for index in ctas},
    }

    aspect = float(output.canvas.width) / float(output.canvas.height)
    high_density = brief.text_density == "high" or brief.format == "menu"
    composition = reference.composition
    centered = reference.alignment == "center" or "center" in composition

    if aspect >= 1.65:
        _set_norm_box(output, headline[0], (margin, 0.10, 0.52, 0.22))
        cursor = 0.37
        for index, box in zip(
            subtitles + bodies + menu_items,
            _stack_boxes(
                len(subtitles + bodies + menu_items),
                x=margin,
                y_start=cursor,
                width=0.48,
                y_end=0.78,
                gap=gap,
            ),
        ):
            _set_norm_box(output, index, box)
        for index, box in zip(
            ctas,
            _stack_boxes(
                len(ctas), x=margin, y_start=0.82, width=0.32, y_end=0.94, gap=gap
            ),
        ):
            _set_norm_box(output, index, box)
        for offset, index in enumerate(shape_indices):
            _set_norm_box(output, index, (0.62, 0.10 + offset * 0.04, 0.32, 0.76))
    elif high_density:
        _set_norm_box(output, headline[0], (margin, margin, 1 - margin * 2, 0.11))
        preamble = subtitles + bodies
        available_end = 0.86 if ctas else 0.94
        menu_start = 0.21
        for index, box in zip(
            preamble,
            _stack_boxes(
                len(preamble),
                x=margin,
                y_start=0.18,
                width=1 - 2 * margin,
                y_end=0.30,
                gap=gap,
            ),
        ):
            _set_norm_box(output, index, box)
        if preamble:
            menu_start = 0.32
        rows = max(len(menu_items), len(prices), 1)
        menu_span = max(1e-6, available_end - menu_start)
        menu_line_count = max(
            (
                output.elements[index].text.content.count("\n") + 1
                for index in menu_items
                if output.elements[index].text is not None
            ),
            default=1,
        )
        short_side = min(float(output.canvas.width), float(output.canvas.height))
        minimum_font_size = max(6.0, short_side * 0.025)
        readable_row_height = (
            minimum_font_size
            * 1.15
            * menu_line_count
            / float(output.canvas.height)
        )
        minimum_row_height = min(
            max(0.035, readable_row_height),
            menu_span / rows,
        )
        if rows > 1:
            row_gap = min(
                gap,
                max(0.0, (menu_span - minimum_row_height * rows) / (rows - 1)),
            )
        else:
            row_gap = 0.0
        row_height = min(
            (menu_span - row_gap * (rows - 1)) / rows,
            0.085,
        )
        for row, index in enumerate(menu_items):
            _set_norm_box(
                output,
                index,
                (margin, menu_start + row * (row_height + row_gap), 0.66, row_height),
            )
        for row, index in enumerate(prices):
            _set_norm_box(
                output,
                index,
                (0.77, menu_start + row * (row_height + row_gap), 0.17, row_height),
            )
        for index, box in zip(
            ctas,
            _stack_boxes(
                len(ctas), x=margin, y_start=0.88, width=1 - 2 * margin, y_end=0.96, gap=gap
            ),
        ):
            _set_norm_box(output, index, box)
    else:
        hero_left = reference.hero is not None and "left" in reference.hero.region
        has_visual_column = bool(shape_indices)
        headline_x = 0.42 if has_visual_column and hero_left else margin
        headline_width = (
            0.52
            if has_visual_column
            else (1 - 2 * margin if centered else 0.62)
        )
        _set_norm_box(
            output,
            headline[0],
            (headline_x, margin, headline_width, 0.17 if has_visual_column else 0.15),
        )
        content = subtitles + bodies + menu_items + prices
        content_x = (
            0.42
            if has_visual_column and hero_left
            else (margin if has_visual_column or not centered else 0.12)
        )
        content_width = 0.52 if has_visual_column else (0.54 if not centered else 0.76)
        for index, box in zip(
            content,
            _stack_boxes(
                len(content),
                x=content_x,
                y_start=0.27,
                width=content_width,
                y_end=0.78,
                gap=gap,
            ),
        ):
            _set_norm_box(output, index, box)
        for index, box in zip(
            ctas,
            _stack_boxes(
                len(ctas), x=margin, y_start=0.84, width=0.38, y_end=0.95, gap=gap
            ),
        ):
            _set_norm_box(output, index, box)
        hero_box = (margin, 0.30, 0.33, 0.45) if hero_left else (0.63, 0.24, 0.31, 0.52)
        for offset, index in enumerate(shape_indices):
            x, y, width, height = hero_box
            _set_norm_box(output, index, (x, y + offset * 0.025, width, height))

    for index in text_indices:
        text = output.elements[index].text
        if text is not None:
            text.alignment = reference.alignment
            role = assigned_roles.get(index, "body")
            output.elements[index].metadata["role"] = role
            output.elements[index].metadata["reference_layout_role"] = role
    after = evaluate_layout(output)
    return output, {
        "engine": "reference_layout_guidance_v1",
        "applied": True,
        "reference_id": reference.reference_id,
        "source_coordinates_copied": False,
        "composition": composition,
        "before_overlap": before["overlap_ratio"],
        "after_overlap": after["overlap_ratio"],
        "before_coverage": before["coverage"],
        "after_coverage": after["coverage"],
        "brief_text_recovery_count": brief_text_recovery_count,
        "unresolved_placeholder_drop_count": placeholder_drop_count,
        "preserved_visual_asset_placeholder_count": placeholder_count_after,
        "synthetic_menu_element_count": menu_element_synthesis_count,
        "business_placeholder_mode": "benchmark" if benchmark_mode else "system",
    }


__all__ = ["apply_reference_layout_guidance"]
