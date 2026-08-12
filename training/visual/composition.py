"""Bounded editable visual composition layered on recovered RAG documents."""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from training.retrieval.models import StructuredBriefV1
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
from training.visual.assets import preserve_asset_intent
from training.visual.density import evaluate_density
from training.visual.models import VisualCompositionReportV1
from training.visual.palette import contrast_ratio, resolve_palette
from training.visual.profiles import get_visual_profile, normalize_visual_category
from training.visual.typography import apply_semantic_typography


VISUAL_ENGINE_VERSION = "visual_composition_v0.3.1"
_PLACEHOLDER_RE = re.compile(
    r"^\[(?:ITEM|DESCRIPTION|PRICE|DISCOUNT|OFFER|DATE)_?\d*\]$",
    re.I,
)
_PERCENT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[.,]\d+)?)\s*%")
_MONEY_RE = re.compile(r"(?<!\w)(\d+(?:[.,]\d+)?)\s*(k|vnd|đ|₫)(?!\w)", re.I)
_DATE_RE = re.compile(r"(?<!\d)(\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?)(?!\d)")
_BOGO_RE = re.compile(r"\bmua\s*(\d+)\D{0,12}tang\s*(\d+)\b", re.I)


def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(
        character for character in normalized if not unicodedata.combining(character)
    )


def _ungrounded_business_placeholder(
    content: str,
    *,
    brief: StructuredBriefV1,
) -> str | None:
    """Replace concrete campaign values that are absent from the user brief."""

    if normalize_visual_category(brief.category) not in {"sale", "grand_opening"}:
        return None
    prompt = _plain(brief.prompt)
    candidate = _plain(content)
    for match in _PERCENT_RE.finditer(candidate):
        if not any(item.group(1) == match.group(1) for item in _PERCENT_RE.finditer(prompt)):
            return "[DISCOUNT]"
    for match in _MONEY_RE.finditer(candidate):
        datum = (match.group(1), match.group(2).casefold())
        if not any(
            (item.group(1), item.group(2).casefold()) == datum
            for item in _MONEY_RE.finditer(prompt)
        ):
            return "[DISCOUNT]"
    for match in _BOGO_RE.finditer(candidate):
        datum = (match.group(1), match.group(2))
        if not any(
            (item.group(1), item.group(2)) == datum
            for item in _BOGO_RE.finditer(prompt)
        ):
            return "[OFFER]"
    for match in _DATE_RE.finditer(candidate):
        if not any(item.group(1) == match.group(1) for item in _DATE_RE.finditer(prompt)):
            return "[DATE]"
    return None


def _color(value: str) -> ColorSpec:
    return ColorSpec(model="hex", values=[value])


def _box(document: DesignDocument, values: tuple[float, float, float, float]) -> BoundingBox:
    x, y, width, height = values
    return BoundingBox(
        x=x * float(document.canvas.width),
        y=y * float(document.canvas.height),
        width=width * float(document.canvas.width),
        height=height * float(document.canvas.height),
    )


def _unique_id(document: DesignDocument, preferred: str) -> str:
    identifiers = {item.id for item in document.elements}
    if preferred not in identifiers:
        return preferred
    suffix = 2
    while f"{preferred}_{suffix}" in identifiers:
        suffix += 1
    return f"{preferred}_{suffix}"


def _shape(
    document: DesignDocument,
    *,
    element_id: str,
    kind: str,
    values: tuple[float, float, float, float],
    fill: str,
    role: str,
    z_index: int,
    opacity: float = 1.0,
) -> DesignElement:
    absolute = _box(document, values)
    return DesignElement(
        id=_unique_id(document, element_id),
        name=role.replace("_", " ").title(),
        type=kind,
        bbox=absolute,
        bbox_norm=normalize_bbox(absolute, document.canvas),
        z_index=z_index,
        layer="background",
        visual=VisualSpec(fill=_color(fill), opacity=opacity),
        metadata={
            "decorative_role": role,
            "visual_engine": VISUAL_ENGINE_VERSION,
            "editable": True,
        },
    )


def _ensure_background(document: DesignDocument, background: str) -> None:
    existing = next(
        (
            element
            for element in document.elements
            if element.id == "background" or element.layer.casefold() == "background"
            if float(element.bbox_norm.width) >= .98 and float(element.bbox_norm.height) >= .98
        ),
        None,
    )
    document.canvas.background = VisualSpec(fill=_color(background))
    if existing is not None:
        existing.visual.fill = _color(background)
        existing.layer = "background"
        existing.z_index = min(existing.z_index, -100)
        return
    absolute = _box(document, (0.0, 0.0, 1.0, 1.0))
    document.elements.append(
        DesignElement(
            id=_unique_id(document, "visual_background"),
            name="Visual Background",
            type="rectangle",
            bbox=absolute,
            bbox_norm=normalize_bbox(absolute, document.canvas),
            z_index=-100,
            layer="background",
            visual=VisualSpec(fill=_color(background)),
            metadata={
                "decorative_role": "canvas_background",
                "visual_engine": VISUAL_ENGINE_VERSION,
                "editable": True,
            },
        )
    )


def _mark_content_provenance(
    document: DesignDocument,
    *,
    brief: StructuredBriefV1,
    benchmark_mode: bool,
) -> int:
    placeholders = 0
    menu_requested = brief.format == "menu" and any(
        value.endswith("_items") for value in brief.requested_elements
    )
    menu_role_counts = {"menu_item": 0, "price": 0}
    largest = max(
        (float(item.text.font_size or 0) for item in document.elements if item.text),
        default=0.0,
    )
    for element in document.elements:
        if element.text is None:
            continue
        metadata = element.metadata
        role = infer_text_role(element, largest_font=largest)
        business_placeholder = _ungrounded_business_placeholder(
            element.text.content,
            brief=brief,
        )
        if business_placeholder is not None:
            element.text.content = business_placeholder
            metadata.update(
                {
                    "role": "promotion" if business_placeholder != "[DATE]" else "date",
                    "synthetic_brief_completion": True,
                    "placeholder_only": True,
                    "requires_user_data": True,
                    "sanitized_ungrounded_business_value": True,
                }
            )
        if menu_requested and role in menu_role_counts and not metadata.get("brief_text_recovery"):
            menu_role_counts[role] += 1
            index = menu_role_counts[role]
            element.text.content = (
                f"[ITEM_{index:02d}]\n[DESCRIPTION_{index:02d}]"
                if role == "menu_item"
                else f"[PRICE_{index:02d}]"
            )
            metadata.update(
                {
                    "role": role,
                    "synthetic_brief_completion": True,
                    "placeholder_only": True,
                    "requires_user_data": True,
                }
            )
        content = element.text.content.strip()
        explicit_placeholder = bool(metadata.get("placeholder_only")) or bool(
            _PLACEHOLDER_RE.fullmatch(content)
        )
        if explicit_placeholder:
            placeholders += 1
            metadata.update(
                {
                    "placeholder_only": True,
                    "requires_user_data": True,
                    "content_provenance": (
                        "benchmark_placeholder" if benchmark_mode else "system_placeholder"
                    ),
                    "benchmark_placeholder": benchmark_mode,
                }
            )
        elif metadata.get("brief_text_recovery"):
            metadata.setdefault("content_provenance", "user_provided")
        else:
            metadata.setdefault("content_provenance", "model_generated_copy")
    return placeholders


def _ensure_campaign_placeholder(
    document: DesignDocument,
    *,
    brief: StructuredBriefV1,
    benchmark_mode: bool,
    fill: str,
) -> int:
    category = normalize_visual_category(brief.category)
    if category not in {"sale", "grand_opening"}:
        return 0
    text_elements = [element for element in document.elements if element.text is not None]
    largest = max((float(item.text.font_size or 0) for item in text_elements), default=12.0)
    if any(
        infer_text_role(item, largest_font=largest) in {"price", "promotion"}
        or "%" in item.text.content
        or re.search(r"\b(?:giảm|sale|offer|ưu đãi)\b", item.text.content, re.I)
        for item in text_elements
    ):
        return 0
    placeholder = "[DISCOUNT]" if category == "sale" else "[OFFER]"
    absolute = _box(document, (0.08, 0.69, 0.34, 0.10))
    next_z = max((element.z_index for element in document.elements), default=0) + 1
    document.elements.append(
        DesignElement(
            id=_unique_id(document, "campaign_offer_placeholder"),
            name="Campaign Offer Placeholder",
            type="text",
            bbox=absolute,
            bbox_norm=normalize_bbox(absolute, document.canvas),
            z_index=next_z,
            layer="content",
            text=TextSpec(
                content=placeholder,
                font_family="DejaVuSans.ttf",
                font_size=max(8.0, min(float(document.canvas.width), float(document.canvas.height)) * .05),
                font_weight=800,
                alignment="center",
            ),
            visual=VisualSpec(fill=_color(fill)),
            metadata={
                "role": "promotion",
                "placeholder_only": True,
                "requires_user_data": True,
                "synthetic_brief_completion": True,
                "content_provenance": (
                    "benchmark_placeholder" if benchmark_mode else "system_placeholder"
                ),
                "benchmark_placeholder": benchmark_mode,
            },
        )
    )
    return 1


def _apply_role_colors(document: DesignDocument, palette: object) -> None:
    text_elements = [element for element in document.elements if element.text is not None]
    largest = max((float(item.text.font_size or 0) for item in text_elements), default=0.0)
    emphasized_text = (
        palette.primary
        if contrast_ratio(palette.primary, palette.background) >= 4.5
        else palette.headline
    )
    for element in document.elements:
        if element.text is not None:
            role = infer_text_role(element, largest_font=largest)
            element.metadata["role"] = role
            if role == "headline":
                element.visual.fill = _color(palette.headline)
            elif role == "cta":
                element.visual.fill = _color(palette.cta_text)
            elif role in {"subtitle", "price"}:
                element.visual.fill = _color(emphasized_text)
            else:
                element.visual.fill = _color(palette.body)
        elif element.layer.casefold() != "background" and not element.metadata.get("asset_required"):
            element.visual.fill = element.visual.fill or _color(palette.surface)


def _set_norm_box(
    document: DesignDocument,
    element: DesignElement,
    values: tuple[float, float, float, float],
) -> None:
    absolute = _box(document, values)
    element.bbox = absolute
    element.bbox_norm = normalize_bbox(absolute, document.canvas)


def _refine_category_geometry(document: DesignDocument, *, category: str) -> int:
    if category not in {"business_card", "salon"}:
        return 0
    text = [element for element in document.elements if element.text is not None]
    ordered = sorted(text, key=lambda item: (float(item.bbox_norm.y), item.z_index))
    if category == "salon" and len(ordered) == 2:
        _set_norm_box(document, ordered[0], (.06, .07, .52, .17))
        _set_norm_box(document, ordered[1], (.06, .30, .52, .24))
        return 2
    boxes = (
        (.05, .07, .65, .20),
        (.05, .34, .66, .14),
        (.05, .49, .66, .26),
        (.05, .78, .66, .16),
    )
    for element, values in zip(ordered, boxes):
        _set_norm_box(document, element, values)
    return min(len(ordered), len(boxes))


def _add_decorations(document: DesignDocument, *, profile: object, palette: object) -> int:
    created: list[DesignElement] = []
    low_z = min((item.z_index for item in document.elements), default=0) - 1
    if profile.surface_strategy == "single_panel":
        created.append(_shape(document, element_id="visual_surface", kind="rectangle", values=(.035, .045, .93, .91), fill=palette.surface, role="surface_panel", z_index=low_z, opacity=.72))
    elif profile.surface_strategy == "section_panels":
        created.append(_shape(document, element_id="visual_menu_surface", kind="rectangle", values=(.04, .17, .92, .77), fill=palette.surface, role="menu_surface", z_index=low_z, opacity=.78))
    if profile.accent_strategy == "line":
        created.append(_shape(document, element_id="visual_accent_line", kind="rectangle", values=(.025, .08, .012, .48), fill=palette.accent, role="accent_line", z_index=low_z + 1))
    elif profile.accent_strategy == "corner":
        created.append(_shape(document, element_id="visual_corner", kind="rectangle", values=(.80, .025, .17, .018), fill=palette.accent, role="corner_accent", z_index=low_z + 1))
    elif profile.accent_strategy == "orb":
        created.append(_shape(document, element_id="visual_orb", kind="ellipse", values=(.78, .77, .18, .18), fill=palette.accent, role="soft_orb", z_index=low_z + 1, opacity=.32))
    elif profile.accent_strategy == "burst":
        created.extend(
            [
                _shape(document, element_id="visual_campaign_bar", kind="rectangle", values=(0, 0, 1, .022), fill=palette.accent, role="campaign_bar", z_index=low_z + 1, opacity=.95),
                _shape(document, element_id="visual_burst_echo", kind="ellipse", values=(.035, .82, .10, .10), fill=palette.secondary, role="campaign_echo", z_index=low_z + 1, opacity=.65),
            ]
        )
    if profile.badge_strategy != "none":
        badge_box = (
            (.78, .78, .14, .14)
            if profile.badge_strategy in {"circle", "campaign"}
            else (.72, .08, .18, .10)
        )
        created.append(_shape(document, element_id="visual_badge", kind="ellipse" if profile.badge_strategy in {"circle", "campaign"} else "rectangle", values=badge_box, fill=palette.accent, role="badge_container", z_index=low_z + 2, opacity=.82))
    menu_rows = [
        item
        for item in document.elements
        if item.text is not None and item.metadata.get("role") == "menu_item"
    ]
    if profile.divider_strategy == "menu_rows":
        for index, item in enumerate(menu_rows[: max(0, profile.max_decorative_elements - len(created))], start=1):
            y = min(float(item.bbox_norm.y + item.bbox_norm.height) + .004, .97)
            created.append(_shape(document, element_id=f"visual_menu_divider_{index:02d}", kind="rectangle", values=(.07, y, .86, .002), fill=palette.secondary, role="menu_divider", z_index=low_z + 2, opacity=.45))
    for element in created[: profile.max_decorative_elements]:
        document.elements.append(element)
    return min(len(created), profile.max_decorative_elements)


def _add_cta_containers(document: DesignDocument, *, palette: object, maximum: int) -> int:
    ctas = [
        item
        for item in document.elements
        if item.text is not None and item.metadata.get("role") == "cta"
    ]
    created = 0
    for index, cta in enumerate(ctas[:maximum], start=1):
        box = cta.bbox_norm
        pad_x = min(.018, float(box.x))
        pad_y = min(.010, float(box.y))
        values = (
            float(box.x) - pad_x,
            float(box.y) - pad_y,
            min(float(box.width) + pad_x * 2, 1 - float(box.x) + pad_x),
            min(float(box.height) + pad_y * 2, 1 - float(box.y) + pad_y),
        )
        document.elements.append(
            _shape(
                document,
                element_id=f"visual_cta_container_{index:02d}",
                kind="rectangle",
                values=values,
                fill=palette.cta_background,
                role="cta_container",
                z_index=cta.z_index - 1,
            )
        )
        created += 1
    return created


def apply_visual_composition(
    document: DesignDocument,
    *,
    brief: StructuredBriefV1,
    reference_palette: Iterable[str] | None = None,
    benchmark_mode: bool = False,
) -> tuple[DesignDocument, VisualCompositionReportV1]:
    """Apply deterministic visual personality without copying reference artwork."""

    original_contents = [item.text.content for item in document.elements if item.text]
    profile = get_visual_profile(brief.category, format_name=brief.format)
    palette = resolve_palette(
        profile,
        brief=brief,
        reference_palette=list(reference_palette or []),
    )
    output = document.model_copy(deep=True)
    density_before = evaluate_density(output, profile)
    _ensure_background(output, palette.background)
    output, asset_report = preserve_asset_intent(output, profile=profile, palette=palette)
    geometry_refinement_count = _refine_category_geometry(
        output,
        category=profile.category,
    )
    campaign_count = _ensure_campaign_placeholder(
        output,
        brief=brief,
        benchmark_mode=benchmark_mode,
        fill=palette.accent,
    )
    output, type_report = apply_semantic_typography(output, profile)
    _apply_role_colors(output, palette)
    decoration_count = _add_decorations(output, profile=profile, palette=palette)
    decoration_count += _add_cta_containers(
        output,
        palette=palette,
        maximum=max(0, profile.max_decorative_elements - decoration_count),
    )
    business_placeholder_count = _mark_content_provenance(
        output,
        brief=brief,
        benchmark_mode=benchmark_mode,
    )
    output.metadata = {
        **output.metadata,
        "visual_composition": {
            "engine": VISUAL_ENGINE_VERSION,
            "profile_id": profile.profile_id,
            "source_category": brief.category,
            "normalized_category": profile.category,
            "reference_coordinates_copied": False,
            "palette": palette.model_dump(mode="json"),
            "business_placeholder_mode": "benchmark" if benchmark_mode else "system",
            "geometry_refinement_count": geometry_refinement_count,
            "asset_avoidance_reflow_count": asset_report["reflowed_text"],
        },
    }
    output = DesignDocument.model_validate(output.model_dump())
    density_after = evaluate_density(output, profile)
    final_contents = [item.text.content for item in output.elements if item.text]
    report = VisualCompositionReportV1(
        profile_id=profile.profile_id,
        source_category=brief.category,
        palette=palette,
        density_before=density_before,
        density_after=density_after,
        semantic_typography_count=int(type_report["changed_count"]),
        asset_placeholder_count=asset_report["preserved"],
        asset_placeholders_created=asset_report["created"],
        decorative_element_count=decoration_count,
        business_placeholder_count=business_placeholder_count,
        content_mutated=original_contents != final_contents or campaign_count > 0,
    )
    return output, report


__all__ = ["VISUAL_ENGINE_VERSION", "apply_visual_composition"]
