"""Deterministic, editable aesthetic hardening for Design AI v0.3.2."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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
from training.visual.profiles import get_visual_profile


HARDENING_ENGINE_VERSION = "aesthetic_hardening_v0.3.2"
_PREMIUM = frozenset({"spa", "cosmetics", "nail"})
_CAMPAIGN = frozenset({"sale", "grand_opening"})
_FRIENDLY = frozenset({"cafe", "milk_tea", "social_banner"})
_DARK = frozenset({"signage", "salon", "business_card"})


def _color(value: str) -> ColorSpec:
    return ColorSpec(model="hex", values=[value.upper()])


def _palette(document: DesignDocument, brief: StructuredBriefV1) -> dict[str, str]:
    visual = document.metadata.get("visual_composition", {})
    values = visual.get("palette", {}) if isinstance(visual, Mapping) else {}
    defaults = get_visual_profile(brief.category, format_name=brief.format).palette_roles
    return {
        key: str(values.get(key) or getattr(defaults, key)).upper()
        for key in (
            "background", "surface", "primary", "secondary", "accent",
            "headline", "body", "muted", "cta_background", "cta_text",
        )
    }


def _box(document: DesignDocument, values: tuple[float, float, float, float]) -> BoundingBox:
    x, y, width, height = values
    return BoundingBox(
        x=x * float(document.canvas.width),
        y=y * float(document.canvas.height),
        width=width * float(document.canvas.width),
        height=height * float(document.canvas.height),
    )


def _set_box(
    document: DesignDocument,
    element: DesignElement,
    values: tuple[float, float, float, float],
) -> None:
    absolute = _box(document, values)
    element.bbox = absolute
    element.bbox_norm = normalize_bbox(absolute, document.canvas)


def _unique_id(document: DesignDocument, preferred: str) -> str:
    ids = {element.id for element in document.elements}
    if preferred not in ids:
        return preferred
    suffix = 2
    while f"{preferred}_{suffix}" in ids:
        suffix += 1
    return f"{preferred}_{suffix}"


def _foreground_background_z(document: DesignDocument) -> int:
    """Place editable decoration above surfaces but behind real content."""

    content_z = [
        item.z_index for item in document.elements
        if item.layer.casefold() != "background"
    ]
    return min(content_z, default=10) - 3


def _shape(
    document: DesignDocument,
    *,
    element_id: str,
    values: tuple[float, float, float, float],
    fill: str,
    role: str,
    z_index: int,
    kind: str = "rectangle",
    stroke: str | None = None,
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
        visual=VisualSpec(
            fill=_color(fill),
            stroke=_color(stroke) if stroke else None,
            stroke_width=(min(float(document.canvas.width), float(document.canvas.height)) * .002 if stroke else None),
            opacity=opacity,
        ),
        metadata={
            "decorative_role": role,
            "visual_engine": HARDENING_ENGINE_VERSION,
            "editable": True,
        },
    )


def _placeholder_caption(
    document: DesignDocument,
    placeholder: DesignElement,
    *,
    label: str,
    palette: Mapping[str, str],
) -> DesignElement:
    box = placeholder.bbox_norm
    x = float(box.x) + float(box.width) * .05
    y = float(box.y) + float(box.height) * .72
    width = float(box.width) * .90
    height = max(.035, float(box.height) * .12)
    if y + height > float(box.y + box.height) - .02:
        y = float(box.y + box.height) - height - .02
    absolute = _box(document, (x, y, width, height))
    return DesignElement(
        id=_unique_id(document, f"{placeholder.id}_label"),
        name=f"{label.title()} Placeholder Label",
        type="text",
        bbox=absolute,
        bbox_norm=normalize_bbox(absolute, document.canvas),
        z_index=placeholder.z_index + 1,
        layer="background",
        text=TextSpec(
            content=label,
            font_family="DejaVuSans.ttf",
            font_size=max(4.0, min(6.0, min(float(document.canvas.width), float(document.canvas.height)) * .020)),
            font_weight=700,
            alignment="center",
            tracking=2.0,
        ),
        visual=VisualSpec(fill=_color(palette["muted"])),
        metadata={
            "decorative_role": "placeholder_label",
            "placeholder_label": True,
            "placeholder_for": placeholder.id,
            "requires_real_asset": True,
            "visual_engine": HARDENING_ENGINE_VERSION,
            "editable": True,
        },
    )


def _harden_placeholders(
    document: DesignDocument,
    *,
    palette: Mapping[str, str],
    category: str,
) -> int:
    changed = 0
    additions: list[DesignElement] = []
    labels = {"hero": "PHOTO", "product": "PHOTO", "logo": "LOGO"}
    for element in document.elements:
        if not (element.metadata.get("editable_placeholder") or element.metadata.get("placeholder")):
            continue
        role = str(element.metadata.get("asset_role") or "image").casefold()
        element.visual.fill = _color(palette["surface"])
        element.visual.stroke = _color(palette["accent"] if category in _CAMPAIGN else palette["secondary"])
        element.visual.stroke_width = max(
            .35,
            min(float(document.canvas.width), float(document.canvas.height)) * .0022,
        )
        element.visual.opacity = .78
        element.metadata.update(
            {
                "placeholder_presentation": "soft_frame_v1",
                "placeholder_label": labels.get(role, "IMAGE"),
                "requires_real_asset": True,
                "visual_engine": HARDENING_ENGINE_VERSION,
            }
        )
        additions.append(
            _placeholder_caption(
                document,
                element,
                label=labels.get(role, "IMAGE"),
                palette=palette,
            )
        )
        changed += 1
    document.elements.extend(additions)
    return changed


def _harden_typography(document: DesignDocument, *, category: str) -> int:
    texts = [element for element in document.elements if element.text is not None]
    largest = max((float(item.text.font_size or 0) for item in texts), default=0.0)
    changed = 0
    for element in texts:
        assert element.text is not None
        role = infer_text_role(element, largest_font=largest)
        if role == "headline":
            element.text.font_family = (
                "DejaVuSerif.ttf" if category in _PREMIUM | {"cafe", "restaurant", "food_menu"}
                else "DejaVuSansCondensed.ttf"
            )
            element.text.font_weight = 800 if category in _CAMPAIGN | _DARK else 700
            element.text.tracking = 1.2 if category in _PREMIUM else .2
        elif role == "cta":
            element.text.font_family = "DejaVuSans.ttf"
            element.text.font_weight = 800
            element.text.tracking = .6
        elif role == "price":
            element.text.font_family = "DejaVuSansCondensed.ttf"
            element.text.font_weight = 700
            element.text.alignment = "right"
        else:
            element.text.font_family = "DejaVuSans.ttf"
            element.text.font_weight = 400 if category in _PREMIUM else 500
            element.text.tracking = .15
        element.metadata["typography_personality"] = f"{category}_v0.3.2"
        changed += 1
    return changed


def _harden_cta(
    document: DesignDocument,
    *,
    palette: Mapping[str, str],
    category: str,
) -> int:
    ctas = [
        item for item in document.elements
        if item.text is not None and item.metadata.get("role") == "cta"
    ]
    changed = 0
    for index, cta in enumerate(ctas, start=1):
        box = cta.bbox_norm
        width = max(float(box.width), .34)
        height = max(float(box.height), .085)
        x = min(max(float(box.x), .05), 1 - width - .05)
        y = min(max(float(box.y), .05), 1 - height - .05)
        _set_box(document, cta, (x, y, width, height))
        is_menu_footer = category == "food_menu"
        cta.text.alignment = "left" if is_menu_footer else "center"
        cta.visual.fill = _color(palette["headline"] if is_menu_footer else palette["cta_text"])
        if not is_menu_footer:
            document.elements.append(
                _shape(
                    document,
                    element_id=f"hardening_cta_shadow_{index:02d}",
                    values=(
                        min(x + .010, 1 - width - .024),
                        min(y + .010, 1 - height - .022),
                        width + .024,
                        height + .016,
                    ),
                    fill=palette["accent"],
                    role="cta_shadow",
                    z_index=cta.z_index - 2,
                    opacity=.72,
                )
            )
        for element in document.elements:
            if element.metadata.get("decorative_role") == "cta_container" and (
                abs(float(element.bbox_norm.x) - float(box.x)) < .05
                or len(ctas) == 1
            ):
                _set_box(document, element, (x - .012, y - .008, width + .024, height + .016))
                element.visual.fill = _color(
                    palette["surface"] if is_menu_footer else palette["cta_background"]
                )
                element.visual.stroke = _color(palette["accent"])
                element.visual.stroke_width = max(.3, min(float(document.canvas.width), float(document.canvas.height)) * .0016)
                element.metadata["cta_hardened"] = True
                break
        else:
            document.elements.append(
                _shape(
                    document,
                    element_id=f"hardening_cta_{index:02d}",
                    values=(x - .012, y - .008, width + .024, height + .016),
                    fill=palette["surface"] if is_menu_footer else palette["cta_background"],
                    stroke=palette["accent"],
                    role="cta_container",
                    z_index=cta.z_index - 1,
                )
            )
        cta.metadata["cta_hardened"] = True
        changed += 1
    return changed


def _harden_menu(document: DesignDocument, *, palette: Mapping[str, str]) -> int:
    menu_items = sorted(
        (
            item for item in document.elements
            if item.text is not None and item.metadata.get("role") == "menu_item"
        ),
        key=lambda item: float(item.bbox_norm.y),
    )
    if not menu_items:
        return 0
    low_z = _foreground_background_z(document)
    created: list[DesignElement] = [
        _shape(
            document,
            element_id="hardening_price_rail",
            values=(.735, .305, .215, min(.65, max(.08, float(menu_items[-1].bbox_norm.y + menu_items[-1].bbox_norm.height) - .305 + .012))),
            fill=palette["background"],
            role="menu_price_rail",
            z_index=low_z,
            opacity=.68,
        )
    ]
    for index, item in enumerate(menu_items, start=1):
        box = item.bbox_norm
        if index % 2 == 1:
            created.append(
                _shape(
                    document,
                    element_id=f"hardening_menu_row_{index:02d}",
                    values=(.045, max(.0, float(box.y) - .005), .91, min(float(box.height) + .010, 1 - float(box.y))),
                    fill=palette["surface"],
                    role="menu_row_band",
                    z_index=low_z + 1,
                    opacity=.62,
                )
            )
        item.metadata["menu_refinement"] = "row_rhythm_v1"
    document.elements.extend(created)
    return len(created)


def _harden_campaign(
    document: DesignDocument,
    *,
    category: str,
    palette: Mapping[str, str],
) -> int:
    if category not in _CAMPAIGN:
        return 0
    low_z = _foreground_background_z(document)
    panel = (.385, .035, .575, .265) if category == "sale" else (.045, .035, .91, .18)
    additions = [
        _shape(document, element_id="hardening_campaign_panel", values=panel, fill=palette["surface"], stroke=palette["accent"], role="campaign_headline_panel", z_index=low_z),
        _shape(document, element_id="hardening_campaign_edge", values=(.015, .04, .025, .62), fill=palette["accent"], role="campaign_edge", z_index=low_z),
        _shape(document, element_id="hardening_campaign_ribbon", values=(.58, .76, .38, .035), fill=palette["secondary"], role="campaign_ribbon", z_index=low_z + 1),
    ]
    headlines = [
        item for item in document.elements
        if item.text is not None and item.metadata.get("role") == "headline"
    ]
    for headline in headlines:
        box = headline.bbox_norm
        if category == "sale":
            _set_box(document, headline, (max(.38, float(box.x)), .045, min(.57, 1 - max(.38, float(box.x)) - .04), .245))
        else:
            _set_box(document, headline, (.05, .045, .90, .16))
        headline.metadata["campaign_hierarchy_hardened"] = True
    document.elements.extend(additions)
    return len(additions)


def _harden_category_surfaces(
    document: DesignDocument,
    *,
    category: str,
    palette: Mapping[str, str],
) -> int:
    low_z = _foreground_background_z(document)
    additions: list[DesignElement] = []
    if category in _PREMIUM:
        additions.extend(
            [
                _shape(document, element_id="hardening_premium_rule", values=(.05, .285, .18, .006), fill=palette["accent"], role="premium_rule", z_index=low_z),
                _shape(document, element_id="hardening_premium_corner", values=(.82, .055, .13, .012), fill=palette["secondary"], role="premium_corner", z_index=low_z),
            ]
        )
    elif category in _FRIENDLY:
        additions.extend(
            [
                _shape(document, element_id="hardening_friendly_chip", values=(.045, .055, .075, .024), fill=palette["accent"], role="friendly_chip", z_index=low_z, opacity=.85),
                _shape(document, element_id="hardening_friendly_orb", values=(.84, .04, .10, .10), fill=palette["secondary"], role="friendly_orb", z_index=low_z, kind="ellipse", opacity=.55),
            ]
        )
    elif category in _DARK:
        additions.extend(
            [
                _shape(document, element_id="hardening_dark_frame_top", values=(.025, .025, .95, .008), fill=palette["accent"], role="dark_frame", z_index=low_z),
                _shape(document, element_id="hardening_dark_frame_bottom", values=(.025, .967, .95, .008), fill=palette["accent"], role="dark_frame", z_index=low_z),
            ]
        )
    document.elements.extend(additions)
    return len(additions)


def evaluate_aesthetic_hardening(document: DesignDocument) -> dict[str, float | int | str]:
    placeholders = [
        item for item in document.elements
        if item.metadata.get("editable_placeholder") or item.metadata.get("placeholder")
    ]
    ctas = [item for item in document.elements if item.metadata.get("role") == "cta"]
    menu_items = [item for item in document.elements if item.metadata.get("role") == "menu_item"]
    row_bands = [item for item in document.elements if item.metadata.get("decorative_role") == "menu_row_band"]
    hardened_placeholders = sum(
        item.metadata.get("placeholder_presentation") == "soft_frame_v1"
        for item in placeholders
    )
    hardened_ctas = sum(bool(item.metadata.get("cta_hardened")) for item in ctas)
    decoration_count = sum(
        item.metadata.get("visual_engine") == HARDENING_ENGINE_VERSION
        for item in document.elements
    )
    return {
        "metrics_version": "aesthetic_hardening_diagnostics_v0.3.2",
        "placeholder_quality": hardened_placeholders / len(placeholders) if placeholders else 1.0,
        "cta_prominence": hardened_ctas / len(ctas) if ctas else 1.0,
        "menu_readability": min(len(row_bands) / max((len(menu_items) + 1) // 2, 1), 1.0) if menu_items else 1.0,
        "decorative_balance": max(0.0, 1.0 - abs(decoration_count - 6) / 12),
        "editable_placeholder_count": len(placeholders),
        "menu_row_band_count": len(row_bands),
        "hardening_decoration_count": decoration_count,
    }


def apply_aesthetic_hardening(
    document: DesignDocument,
    *,
    brief: StructuredBriefV1,
) -> tuple[DesignDocument, dict[str, Any]]:
    """Apply bounded category polish without generating or replacing content."""

    current = document.metadata.get("aesthetic_hardening", {})
    if isinstance(current, Mapping) and current.get("engine") == HARDENING_ENGINE_VERSION:
        raise ValueError("document already has v0.3.2 aesthetic hardening")
    output = document.model_copy(deep=True)
    profile = get_visual_profile(brief.category, format_name=brief.format)
    category = profile.category
    palette = _palette(output, brief)
    original_content = [item.text.content for item in output.elements if item.text]
    counts = {
        "placeholder_count": _harden_placeholders(output, palette=palette, category=category),
        "typography_count": _harden_typography(output, category=category),
        "cta_count": _harden_cta(output, palette=palette, category=category),
        "menu_decoration_count": _harden_menu(output, palette=palette),
        "campaign_decoration_count": _harden_campaign(output, category=category, palette=palette),
        "category_decoration_count": _harden_category_surfaces(output, category=category, palette=palette),
    }
    final_content = [item.text.content for item in output.elements if item.text and not item.metadata.get("placeholder_label")]
    if original_content != final_content:
        raise RuntimeError("aesthetic hardening must not mutate customer or placeholder copy")
    output.metadata = {
        **output.metadata,
        "aesthetic_hardening": {
            "engine": HARDENING_ENGINE_VERSION,
            "category": category,
            "content_mutated": False,
            "fake_customer_data_added": False,
            "all_elements_editable": True,
            **counts,
        },
    }
    validated = DesignDocument.model_validate(output.model_dump())
    return validated, validated.metadata["aesthetic_hardening"]


__all__ = [
    "HARDENING_ENGINE_VERSION",
    "apply_aesthetic_hardening",
    "evaluate_aesthetic_hardening",
]
