"""Deterministic content locks and composition diversity for v0.4 Phase 1.1."""

from __future__ import annotations

import hashlib
import json
import re
from itertools import combinations
from typing import Any, Literal

from pydantic import Field, model_validator

from training.schemas.design import (
    BoundingBox,
    ColorSpec,
    DesignDocument,
    DesignElement,
    VisualSpec,
    normalize_bbox,
)
from training.typography.fitting import infer_text_role
from training.preference.v04.models import ID_PATTERN, SHA256_PATTERN, StrictModel


LayoutFamily = Literal[
    "editorial",
    "split_left",
    "split_right",
    "centered",
    "asymmetric",
    "image_dominant",
    "type_dominant",
    "modular",
    "stacked",
    "framed",
    "edge_aligned",
]

_MONEY_RE = re.compile(r"(?<!\w)\d[\d.,]*\s*(?:k|vnd|đ|₫|usd|\$)(?!\w)", re.I)
_PERCENT_RE = re.compile(r"(?<!\d)\d{1,3}(?:[.,]\d+)?\s*%")
_DATE_RE = re.compile(r"(?<!\d)\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?(?!\d)")


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _clean_text(value: str) -> str:
    return " ".join(value.split()).strip()


class CandidateInvariantV1(StrictModel):
    """Facts that are forbidden from changing inside one candidate group."""

    schema_version: Literal["1.0"] = "1.0"
    brief_id: str = Field(pattern=ID_PATTERN)
    category: str = Field(min_length=1, max_length=100)
    canvas_width: float = Field(gt=0)
    canvas_height: float = Field(gt=0)
    canvas_unit: str = Field(min_length=1, max_length=20)
    business_name: str | None = None
    headline: str | None = None
    subheadline: str | None = None
    body: str | None = None
    cta: str | None = None
    prices: list[str] = Field(default_factory=list)
    discounts: list[str] = Field(default_factory=list)
    offers: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    menu_items: list[dict[str, str]] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)
    asset_hashes: dict[str, str] = Field(default_factory=dict)
    brand_colors: list[str] = Field(default_factory=list)
    content_lock_hash: str = Field(pattern=SHA256_PATTERN)
    asset_lock_hash: str = Field(pattern=SHA256_PATTERN)
    business_value_hash: str = Field(pattern=SHA256_PATTERN)
    canvas_hash: str = Field(pattern=SHA256_PATTERN)


class CandidateStyleVariantV1(StrictModel):
    """Bounded design-only choices; factual content is deliberately absent."""

    schema_version: Literal["1.0"] = "1.0"
    variant_id: str = Field(pattern=ID_PATTERN)
    layout_family: LayoutFamily
    hero_position: Literal["left", "right", "top", "bottom", "center", "background"]
    hero_scale: float = Field(ge=0.05, le=0.95)
    text_group_position: Literal["left", "right", "top", "bottom", "center"]
    headline_scale: float = Field(ge=0.75, le=2.0)
    headline_alignment: Literal["left", "center", "right"]
    body_alignment: Literal["left", "center", "right"]
    cta_treatment: Literal["solid", "outline", "pill", "text"]
    cta_position: Literal["left", "right", "bottom", "center"]
    whitespace_distribution: Literal["balanced", "editorial", "compact", "dramatic"]
    surface_treatment: Literal["none", "panel", "frame", "band"]
    decorative_system: Literal["rule", "orb", "campaign", "grid", "frame", "minimal"]
    typography_pairing: Literal[
        "refined_serif_sans",
        "editorial_serif_sans",
        "bold_condensed_sans",
        "scanable_sans",
        "distance_sans",
    ]
    palette_treatment: Literal["brand", "light", "dark", "accent", "tonal"]


class QualityFloorResultV1(StrictModel):
    passed: bool
    reasons: list[str]
    metrics: dict[str, float | int | str | bool]
    regeneration_count: int = Field(ge=0, le=5)

    @model_validator(mode="after")
    def reasons_match_state(self) -> "QualityFloorResultV1":
        if self.passed == bool(self.reasons):
            raise ValueError("quality-floor pass state and reasons disagree")
        return self


def invariant_from_document(
    document: DesignDocument,
    *,
    brief_id: str,
    brief_payload: dict[str, Any] | None = None,
) -> CandidateInvariantV1:
    """Build stable factual hashes from explicit brief data and bound assets."""

    brief = dict(brief_payload or {})
    texts = [
        _clean_text(
            str(item.metadata.get("typography_fit", {}).get("original_content") or item.text.content)
        )
        for item in document.elements
        if item.text is not None
    ]
    prices = [str(value) for value in brief.get("prices", [])]
    items = [
        {
            "name": _clean_text(str(item.get("name", ""))),
            "description": _clean_text(str(item.get("description", ""))),
            "price": _clean_text(str(item.get("price", ""))),
        }
        for item in brief.get("items", [])
    ]
    prices.extend(item["price"] for item in items if item["price"])
    discounts = [str(value) for value in brief.get("discounts", [])]
    offers = [str(value) for value in brief.get("offers", [])]
    dates = [str(value) for value in brief.get("dates", [])]
    for text in texts:
        prices.extend(_MONEY_RE.findall(text))
        discounts.extend(_PERCENT_RE.findall(text))
        dates.extend(_DATE_RE.findall(text))
    asset_ids = sorted(asset.id for asset in document.assets)
    asset_hashes = {
        asset.id: str(asset.metadata.get("sha256", ""))
        for asset in sorted(document.assets, key=lambda value: value.id)
    }
    if any(not re.fullmatch(SHA256_PATTERN, value) for value in asset_hashes.values()):
        raise ValueError("every locked asset requires an explicit sha256")
    content = {
        "business_name": brief.get("business_name") or brief.get("headline"),
        "headline": brief.get("headline"),
        "subheadline": brief.get("subheadline"),
        "body": brief.get("body"),
        "cta": brief.get("cta"),
        "texts": texts,
        "menu_items": items,
    }
    business_values = {
        "prices": sorted(set(prices)),
        "discounts": sorted(set(discounts)),
        "offers": sorted(set(offers)),
        "dates": sorted(set(dates)),
        "menu_items": items,
    }
    canvas = {
        "width": float(document.canvas.width),
        "height": float(document.canvas.height),
        "unit": document.canvas.unit,
    }
    assets = {"asset_ids": asset_ids, "asset_hashes": asset_hashes}
    return CandidateInvariantV1(
        brief_id=brief_id,
        category=document.category,
        canvas_width=float(document.canvas.width),
        canvas_height=float(document.canvas.height),
        canvas_unit=document.canvas.unit,
        business_name=content["business_name"],
        headline=content["headline"],
        subheadline=content["subheadline"],
        body=content["body"],
        cta=content["cta"],
        prices=business_values["prices"],
        discounts=business_values["discounts"],
        offers=business_values["offers"],
        dates=business_values["dates"],
        menu_items=items,
        asset_ids=asset_ids,
        asset_hashes=asset_hashes,
        brand_colors=[str(value) for value in brief.get("brand_colors", [])],
        content_lock_hash=_canonical_hash(content),
        asset_lock_hash=_canonical_hash(assets),
        business_value_hash=_canonical_hash(business_values),
        canvas_hash=_canonical_hash(canvas),
    )


def assert_candidate_group_locked(invariants: list[CandidateInvariantV1]) -> None:
    if len(invariants) != 4:
        raise ValueError("a hardened candidate group requires exactly four invariants")
    for field in (
        "brief_id",
        "category",
        "content_lock_hash",
        "asset_lock_hash",
        "business_value_hash",
        "canvas_hash",
    ):
        if len({getattr(item, field) for item in invariants}) != 1:
            raise ValueError(f"candidate group violates {field}")


_CATEGORY_VARIANTS: dict[str, tuple[CandidateStyleVariantV1, ...]] = {
    "spa": (
        CandidateStyleVariantV1(variant_id="spa_editorial", layout_family="editorial", hero_position="right", hero_scale=.42, text_group_position="left", headline_scale=1.25, headline_alignment="left", body_alignment="left", cta_treatment="outline", cta_position="left", whitespace_distribution="editorial", surface_treatment="none", decorative_system="rule", typography_pairing="refined_serif_sans", palette_treatment="light"),
        CandidateStyleVariantV1(variant_id="spa_split_left", layout_family="split_left", hero_position="left", hero_scale=.44, text_group_position="right", headline_scale=1.1, headline_alignment="left", body_alignment="left", cta_treatment="solid", cta_position="right", whitespace_distribution="balanced", surface_treatment="panel", decorative_system="minimal", typography_pairing="refined_serif_sans", palette_treatment="tonal"),
        CandidateStyleVariantV1(variant_id="spa_asymmetric", layout_family="asymmetric", hero_position="right", hero_scale=.49, text_group_position="left", headline_scale=1.4, headline_alignment="left", body_alignment="left", cta_treatment="pill", cta_position="left", whitespace_distribution="dramatic", surface_treatment="none", decorative_system="orb", typography_pairing="editorial_serif_sans", palette_treatment="accent"),
        CandidateStyleVariantV1(variant_id="spa_image_dominant", layout_family="image_dominant", hero_position="background", hero_scale=.65, text_group_position="left", headline_scale=1.2, headline_alignment="left", body_alignment="left", cta_treatment="solid", cta_position="left", whitespace_distribution="dramatic", surface_treatment="panel", decorative_system="minimal", typography_pairing="refined_serif_sans", palette_treatment="dark"),
    ),
    "cafe": (
        CandidateStyleVariantV1(variant_id="cafe_editorial", layout_family="editorial", hero_position="top", hero_scale=.36, text_group_position="bottom", headline_scale=1.2, headline_alignment="left", body_alignment="left", cta_treatment="outline", cta_position="bottom", whitespace_distribution="editorial", surface_treatment="none", decorative_system="rule", typography_pairing="editorial_serif_sans", palette_treatment="light"),
        CandidateStyleVariantV1(variant_id="cafe_split_right", layout_family="split_right", hero_position="right", hero_scale=.46, text_group_position="left", headline_scale=1.1, headline_alignment="left", body_alignment="left", cta_treatment="solid", cta_position="left", whitespace_distribution="balanced", surface_treatment="panel", decorative_system="minimal", typography_pairing="editorial_serif_sans", palette_treatment="brand"),
        CandidateStyleVariantV1(variant_id="cafe_asymmetric", layout_family="asymmetric", hero_position="top", hero_scale=.46, text_group_position="bottom", headline_scale=1.35, headline_alignment="left", body_alignment="left", cta_treatment="pill", cta_position="bottom", whitespace_distribution="dramatic", surface_treatment="none", decorative_system="orb", typography_pairing="refined_serif_sans", palette_treatment="accent"),
        CandidateStyleVariantV1(variant_id="cafe_image_dominant", layout_family="image_dominant", hero_position="top", hero_scale=.58, text_group_position="bottom", headline_scale=1.05, headline_alignment="center", body_alignment="center", cta_treatment="solid", cta_position="center", whitespace_distribution="compact", surface_treatment="band", decorative_system="minimal", typography_pairing="editorial_serif_sans", palette_treatment="dark"),
    ),
    "sale": (
        CandidateStyleVariantV1(variant_id="sale_image_dominant", layout_family="image_dominant", hero_position="left", hero_scale=.52, text_group_position="right", headline_scale=1.35, headline_alignment="left", body_alignment="left", cta_treatment="solid", cta_position="right", whitespace_distribution="compact", surface_treatment="none", decorative_system="campaign", typography_pairing="bold_condensed_sans", palette_treatment="brand"),
        CandidateStyleVariantV1(variant_id="sale_type_dominant", layout_family="type_dominant", hero_position="bottom", hero_scale=.34, text_group_position="top", headline_scale=1.65, headline_alignment="center", body_alignment="center", cta_treatment="pill", cta_position="center", whitespace_distribution="dramatic", surface_treatment="band", decorative_system="campaign", typography_pairing="bold_condensed_sans", palette_treatment="dark"),
        CandidateStyleVariantV1(variant_id="sale_asymmetric", layout_family="asymmetric", hero_position="right", hero_scale=.46, text_group_position="left", headline_scale=1.45, headline_alignment="left", body_alignment="left", cta_treatment="solid", cta_position="left", whitespace_distribution="balanced", surface_treatment="panel", decorative_system="campaign", typography_pairing="bold_condensed_sans", palette_treatment="accent"),
        CandidateStyleVariantV1(variant_id="sale_split", layout_family="split_left", hero_position="left", hero_scale=.44, text_group_position="right", headline_scale=1.25, headline_alignment="right", body_alignment="right", cta_treatment="outline", cta_position="right", whitespace_distribution="editorial", surface_treatment="frame", decorative_system="frame", typography_pairing="bold_condensed_sans", palette_treatment="light"),
    ),
    "menu": (
        CandidateStyleVariantV1(variant_id="menu_editorial", layout_family="editorial", hero_position="top", hero_scale=.15, text_group_position="left", headline_scale=1.15, headline_alignment="left", body_alignment="left", cta_treatment="text", cta_position="bottom", whitespace_distribution="editorial", surface_treatment="none", decorative_system="rule", typography_pairing="scanable_sans", palette_treatment="light"),
        CandidateStyleVariantV1(variant_id="menu_sectioned", layout_family="modular", hero_position="top", hero_scale=.18, text_group_position="left", headline_scale=1.05, headline_alignment="left", body_alignment="left", cta_treatment="solid", cta_position="bottom", whitespace_distribution="balanced", surface_treatment="panel", decorative_system="grid", typography_pairing="scanable_sans", palette_treatment="tonal"),
        CandidateStyleVariantV1(variant_id="menu_image_supported", layout_family="split_right", hero_position="right", hero_scale=.25, text_group_position="left", headline_scale=1.2, headline_alignment="left", body_alignment="left", cta_treatment="outline", cta_position="bottom", whitespace_distribution="editorial", surface_treatment="none", decorative_system="rule", typography_pairing="editorial_serif_sans", palette_treatment="accent"),
        CandidateStyleVariantV1(variant_id="menu_compact_grid", layout_family="centered", hero_position="top", hero_scale=.12, text_group_position="center", headline_scale=1.0, headline_alignment="center", body_alignment="left", cta_treatment="solid", cta_position="bottom", whitespace_distribution="compact", surface_treatment="frame", decorative_system="grid", typography_pairing="scanable_sans", palette_treatment="dark"),
    ),
    "signage": (
        CandidateStyleVariantV1(variant_id="signage_logo_left", layout_family="split_left", hero_position="left", hero_scale=.30, text_group_position="right", headline_scale=1.2, headline_alignment="left", body_alignment="left", cta_treatment="text", cta_position="right", whitespace_distribution="balanced", surface_treatment="none", decorative_system="rule", typography_pairing="distance_sans", palette_treatment="dark"),
        CandidateStyleVariantV1(variant_id="signage_logo_center", layout_family="centered", hero_position="top", hero_scale=.26, text_group_position="center", headline_scale=1.0, headline_alignment="center", body_alignment="center", cta_treatment="text", cta_position="center", whitespace_distribution="dramatic", surface_treatment="frame", decorative_system="frame", typography_pairing="distance_sans", palette_treatment="brand"),
        CandidateStyleVariantV1(variant_id="signage_name_dominant", layout_family="type_dominant", hero_position="right", hero_scale=.20, text_group_position="left", headline_scale=1.5, headline_alignment="left", body_alignment="left", cta_treatment="text", cta_position="left", whitespace_distribution="compact", surface_treatment="band", decorative_system="minimal", typography_pairing="distance_sans", palette_treatment="accent"),
        CandidateStyleVariantV1(variant_id="signage_balanced", layout_family="edge_aligned", hero_position="left", hero_scale=.40, text_group_position="right", headline_scale=1.1, headline_alignment="right", body_alignment="right", cta_treatment="text", cta_position="right", whitespace_distribution="editorial", surface_treatment="none", decorative_system="rule", typography_pairing="distance_sans", palette_treatment="light"),
    ),
}


def variants_for_category(category: str) -> tuple[CandidateStyleVariantV1, ...]:
    normalized = "menu" if category in {"food_menu", "restaurant_menu"} else category
    if normalized not in _CATEGORY_VARIANTS:
        raise ValueError(f"no Phase 1.1 variants registered for {category}")
    return _CATEGORY_VARIANTS[normalized]


def _set_box(
    document: DesignDocument,
    element: DesignElement,
    values: tuple[float, float, float, float],
) -> None:
    x, y, width, height = values
    bbox = BoundingBox(
        x=x * float(document.canvas.width),
        y=y * float(document.canvas.height),
        width=width * float(document.canvas.width),
        height=height * float(document.canvas.height),
    )
    element.bbox = bbox
    element.bbox_norm = normalize_bbox(bbox, document.canvas)


def _color(value: str) -> ColorSpec:
    return ColorSpec(model="hex", values=[value])


def _background_color(document: DesignDocument) -> str:
    fill = document.canvas.background.fill if document.canvas.background else None
    if fill and fill.model == "hex":
        return str(fill.values[0])
    return "#F5F1E8"


def _shape(
    document: DesignDocument,
    *,
    element_id: str,
    values: tuple[float, float, float, float],
    fill: str,
    opacity: float = 1.0,
    kind: Literal["rectangle", "ellipse"] = "rectangle",
) -> DesignElement:
    bbox = BoundingBox(
        x=values[0] * float(document.canvas.width),
        y=values[1] * float(document.canvas.height),
        width=values[2] * float(document.canvas.width),
        height=values[3] * float(document.canvas.height),
    )
    return DesignElement(
        id=element_id,
        name="Phase 1.1 decorative surface",
        type=kind,
        bbox=bbox,
        bbox_norm=normalize_bbox(bbox, document.canvas),
        z_index=-20,
        layer="background",
        visual=VisualSpec(fill=_color(fill), opacity=opacity),
        metadata={
            "decorative_role": "phase1_1_surface",
            "generation_version": "candidate_generation_v2_pilot",
            "editable": True,
        },
    )


def _role_map(document: DesignDocument) -> dict[str, list[DesignElement]]:
    texts = [item for item in document.elements if item.text is not None]
    largest = max((float(item.text.font_size or 0) for item in texts), default=0.0)
    roles: dict[str, list[DesignElement]] = {}
    for element in texts:
        role = str(element.metadata.get("role") or infer_text_role(element, largest_font=largest))
        content = element.text.content.casefold() if element.text else ""
        if (
            "offer" in element.id.casefold()
            or "discount" in element.id.casefold()
            or "%" in content
            or "giảm" in content
        ):
            role = "promotion"
            element.metadata["role"] = role
        roles.setdefault(role, []).append(element)
    return roles


def _asset(document: DesignDocument, *roles: str) -> DesignElement | None:
    for role in roles:
        match = next(
            (
                item
                for item in document.elements
                if item.asset_ref
                and str(item.metadata.get("asset_role") or item.metadata.get("role")) == role
            ),
            None,
        )
        if match is not None:
            return match
    return None


def _set_text_style(
    document: DesignDocument,
    variant: CandidateStyleVariantV1,
) -> None:
    roles = _role_map(document)
    short = min(float(document.canvas.width), float(document.canvas.height))
    family = {
        "refined_serif_sans": "DejaVuSerif.ttf",
        "editorial_serif_sans": "DejaVuSerif.ttf",
        "bold_condensed_sans": "DejaVuSansCondensed.ttf",
        "scanable_sans": "DejaVuSans.ttf",
        "distance_sans": "DejaVuSansCondensed.ttf",
    }[variant.typography_pairing]
    for role, elements in roles.items():
        for element in elements:
            assert element.text is not None
            original = element.metadata.get("typography_fit", {}).get("original_content")
            if isinstance(original, str):
                element.text.content = original
            element.text.alignment = (
                variant.headline_alignment if role == "headline" else variant.body_alignment
            )
            element.text.font_family = family if role in {"headline", "price"} else "DejaVuSans.ttf"
            if role == "headline":
                element.text.font_size = max(short * .075, float(element.text.font_size or 8) * variant.headline_scale)
                element.text.font_weight = 800 if "bold" in variant.typography_pairing else 700
                element.text.tracking = 0.5 if variant.layout_family == "editorial" else 0.0
            elif role == "price":
                element.text.font_weight = 800
            elif role == "cta":
                element.text.font_weight = 750
            else:
                element.text.font_weight = 450


def _place_common(
    document: DesignDocument,
    *,
    boxes: dict[str, tuple[float, float, float, float]],
) -> None:
    roles = _role_map(document)
    for role, values in boxes.items():
        for element in roles.get(role, []):
            _set_box(document, element, values)


def _place_menu(document: DesignDocument, variant: CandidateStyleVariantV1) -> None:
    roles = _role_map(document)
    items = sorted(roles.get("menu_item", []), key=lambda item: item.id)
    prices = sorted(roles.get("price", []), key=lambda item: item.id)
    hero = _asset(document, "hero")
    logo = _asset(document, "logo")
    _place_common(
        document,
        boxes={
            "headline": (.06, .10, .55, .075),
            "body": (.06, .185, .55, .05),
            "cta": (.06, .875, .88, .07),
        },
    )
    if variant.variant_id == "menu_compact_grid":
        if hero:
            _set_box(document, hero, (.72, .035, .22, .16))
        if logo:
            _set_box(document, logo, (.06, .035, .24, .06))
        for index, (item, price) in enumerate(zip(items, prices)):
            column, row = index % 2, index // 2
            x = .06 + column * .47
            y = .30 + row * .16
            _set_box(document, item, (x, y, .34, .105))
            _set_box(document, price, (x + .35, y, .08, .055))
    else:
        if variant.variant_id == "menu_image_supported":
            if hero:
                _set_box(document, hero, (.69, .035, .27, .23))
            if logo:
                _set_box(document, logo, (.06, .035, .25, .065))
            start, gap = .31, .102
        elif variant.variant_id == "menu_sectioned":
            if hero:
                _set_box(document, hero, (.74, .045, .20, .17))
            if logo:
                _set_box(document, logo, (.06, .035, .25, .065))
            start, gap = .29, .105
        else:
            if hero:
                _set_box(document, hero, (.68, .035, .28, .21))
            if logo:
                _set_box(document, logo, (.06, .035, .25, .065))
            start, gap = .30, .102
        for index, (item, price) in enumerate(zip(items, prices)):
            y = start + index * gap
            _set_box(document, item, (.07, y, .67, .075))
            _set_box(document, price, (.79, y, .14, .055))


def _place_variant(document: DesignDocument, variant: CandidateStyleVariantV1) -> None:
    source_category = str(document.metadata.get("phase1_1_case_id") or document.category)
    category = "menu" if source_category in {"food_menu", "menu"} else source_category
    hero = _asset(document, "hero", "product")
    logo = _asset(document, "logo")
    if category == "menu":
        _place_menu(document, variant)
        return
    if category == "spa":
        geometry = {
            "spa_editorial": ((.58, .04, .40, .92), (.04, .04, .27, .10), {"headline": (.05, .22, .45, .20), "body": (.05, .50, .43, .14), "cta": (.05, .76, .30, .12)}),
            "spa_split_left": ((.02, .05, .44, .90), (.56, .05, .28, .10), {"headline": (.54, .24, .40, .18), "body": (.54, .48, .40, .14), "cta": (.54, .75, .30, .12)}),
            "spa_asymmetric": ((.47, .08, .49, .82), (.05, .04, .27, .09), {"headline": (.05, .20, .38, .22), "body": (.05, .51, .35, .14), "cta": (.05, .76, .29, .12)}),
            "spa_image_dominant": ((.35, 0, .65, 1), (.04, .06, .25, .09), {"headline": (.04, .22, .34, .20), "body": (.04, .49, .32, .16), "cta": (.04, .78, .27, .12)}),
        }[variant.variant_id]
    elif category == "cafe":
        geometry = {
            "cafe_editorial": ((.08, .08, .84, .36), (.08, .025, .30, .065), {"headline": (.08, .48, .84, .19), "body": (.08, .70, .78, .10), "cta": (.08, .85, .54, .10)}),
            "cafe_split_right": ((.52, .08, .44, .65), (.06, .025, .34, .07), {"headline": (.06, .18, .40, .25), "body": (.06, .49, .39, .17), "cta": (.06, .80, .38, .11)}),
            "cafe_asymmetric": ((.28, .05, .68, .47), (.06, .025, .31, .065), {"headline": (.06, .53, .78, .20), "body": (.12, .74, .74, .12), "cta": (.42, .87, .50, .12)}),
            "cafe_image_dominant": ((.04, .035, .92, .56), (.08, .055, .31, .07), {"headline": (.08, .61, .84, .15), "body": (.10, .77, .80, .11), "cta": (.24, .89, .52, .10)}),
        }[variant.variant_id]
    elif category == "sale":
        geometry = {
            "sale_image_dominant": ((.03, .18, .50, .70), (.05, .035, .27, .07), {"headline": (.55, .15, .40, .20), "promotion": (.55, .41, .36, .13), "cta": (.55, .72, .33, .10)}),
            "sale_type_dominant": ((.35, .51, .30, .29), (.06, .035, .27, .07), {"headline": (.09, .13, .82, .19), "promotion": (.21, .34, .58, .13), "cta": (.28, .84, .44, .09)}),
            "sale_asymmetric": ((.54, .20, .42, .63), (.06, .035, .27, .07), {"headline": (.06, .16, .42, .21), "promotion": (.06, .43, .37, .13), "cta": (.06, .73, .32, .10)}),
            "sale_split": ((.04, .16, .42, .68), (.69, .035, .26, .07), {"headline": (.51, .16, .43, .19), "promotion": (.56, .41, .37, .13), "cta": (.61, .72, .33, .10)}),
        }[variant.variant_id]
    elif category == "signage":
        geometry = {
            "signage_logo_left": ((.03, .12, .29, .76), None, {"headline": (.37, .25, .58, .43)}),
            "signage_logo_center": ((.36, .06, .28, .55), None, {"headline": (.18, .68, .64, .22)}),
            "signage_name_dominant": ((.76, .17, .19, .66), None, {"headline": (.04, .22, .67, .48)}),
            "signage_balanced": ((.05, .14, .39, .72), None, {"headline": (.50, .26, .45, .40)}),
        }[variant.variant_id]
        hero = logo
        logo = None
    else:
        raise ValueError(f"unsupported Phase 1.1 category: {category}")
    hero_box, logo_box, text_boxes = geometry
    if hero:
        _set_box(document, hero, hero_box)
    if logo and logo_box:
        _set_box(document, logo, logo_box)
    _place_common(document, boxes=text_boxes)


def _add_variant_surfaces(document: DesignDocument, variant: CandidateStyleVariantV1) -> None:
    background = _background_color(document)
    dark = variant.palette_treatment == "dark"
    if dark:
        background = "#171A1D"
    elif variant.palette_treatment == "light":
        background = "#F5F1E8"
    digits = background.removeprefix("#")
    if len(digits) == 3:
        digits = "".join(value * 2 for value in digits)
    red, green, blue = (int(digits[index : index + 2], 16) for index in (0, 2, 4))
    dark_surface = (0.2126 * red + 0.7152 * green + 0.0722 * blue) < 128
    document.canvas.background = VisualSpec(fill=_color(background))
    for element in document.elements:
        if (
            element.id == "background"
            or (
                element.layer.casefold() == "background"
                and float(element.bbox_norm.width) >= .98
                and float(element.bbox_norm.height) >= .98
            )
        ):
            element.visual.fill = _color(background)
        if element.text is not None:
            element.visual.fill = _color("#F5F1E8" if dark_surface else "#292421")
    accent = "#DDBB78" if dark_surface else "#C79B55"
    surfaces: list[DesignElement] = []
    if variant.surface_treatment == "panel":
        side = (.02, .06, .43, .88) if variant.text_group_position == "left" else (.52, .06, .46, .88)
        surfaces.append(_shape(document, element_id="v0411_surface_panel", values=side, fill="#FFFFFF" if not dark else "#252A2E", opacity=.92))
    elif variant.surface_treatment == "band":
        surfaces.append(_shape(document, element_id="v0411_surface_band", values=(0, .62, 1, .38), fill="#F2E7D5" if not dark else "#24282C", opacity=.96))
    elif variant.surface_treatment == "frame":
        surfaces.extend([
            _shape(document, element_id="v0411_frame_top", values=(.02, .025, .96, .012), fill=accent),
            _shape(document, element_id="v0411_frame_bottom", values=(.02, .963, .96, .012), fill=accent),
        ])
    if variant.decorative_system == "rule":
        surfaces.append(_shape(document, element_id="v0411_accent_rule", values=(.04, .91, .20, .012), fill=accent))
    elif variant.decorative_system == "orb":
        surfaces.append(_shape(document, element_id="v0411_accent_orb", values=(.82, .77, .13, .13), fill=accent, opacity=.35, kind="ellipse"))
    elif variant.decorative_system == "campaign":
        surfaces.extend([
            _shape(document, element_id="v0411_campaign_top", values=(0, 0, 1, .018), fill=accent),
            _shape(document, element_id="v0411_campaign_orb", values=(.03, .83, .12, .10), fill=accent, opacity=.55, kind="ellipse"),
        ])
    if (
        str(document.metadata.get("phase1_1_case_id")) == "signage"
        and variant.palette_treatment == "light"
        and (signage_logo := _asset(document, "logo")) is not None
    ):
        logo_box = signage_logo.bbox_norm
        surfaces.append(
            _shape(
                document,
                element_id="v0411_signage_logo_contrast_panel",
                values=(
                    max(0.0, float(logo_box.x) - .015),
                    max(0.0, float(logo_box.y) - .05),
                    min(1.0 - max(0.0, float(logo_box.x) - .015), float(logo_box.width) + .03),
                    min(1.0 - max(0.0, float(logo_box.y) - .05), float(logo_box.height) + .10),
                ),
                fill="#171A1D",
            )
        )
    roles = _role_map(document)
    for cta in roles.get("cta", []):
        box = cta.bbox_norm
        if variant.cta_treatment in {"solid", "pill"}:
            surfaces.append(
                _shape(
                    document,
                    element_id=f"v0411_cta_{variant.variant_id}",
                    values=(
                        max(0.0, float(box.x) - .012),
                        max(0.0, float(box.y) - .008),
                        min(1.0 - max(0.0, float(box.x) - .012), float(box.width) + .024),
                        min(1.0 - max(0.0, float(box.y) - .008), float(box.height) + .016),
                    ),
                    fill=accent,
                )
            )
            cta.visual.fill = _color("#171819")
        elif variant.cta_treatment == "outline":
            cta.visual.fill = _color(accent if dark_surface else "#72521D")
        else:
            cta.visual.fill = _color(accent)
    for promotion in roles.get("promotion", []):
        promotion.visual.fill = _color(accent if dark_surface else "#A32C4D")
    document.elements.extend(surfaces)


def apply_candidate_style_variant(
    document: DesignDocument,
    variant: CandidateStyleVariantV1,
) -> DesignDocument:
    """Recompose a safe asset-aware document while preserving every locked fact."""

    output = document.model_copy(deep=True)
    original = invariant_from_document(
        output,
        brief_id=str(output.metadata.get("brief_id") or output.sample_id),
        brief_payload=output.metadata.get("candidate_invariant_brief", {}),
    )
    output.elements = [
        item
        for item in output.elements
        if not item.metadata.get("decorative_role")
        or item.metadata.get("decorative_role") == "canvas_background"
    ]
    _set_text_style(output, variant)
    _place_variant(output, variant)
    _add_variant_surfaces(output, variant)
    output.metadata = {
        **output.metadata,
        "candidate_generation": {
            "generation_version": "candidate_generation_v2_pilot",
            "layout_family": variant.layout_family,
            "variant_id": variant.variant_id,
            "content_diversity_used": False,
            "visual_rag_enabled": False,
            "vision_critic_enabled": False,
        },
    }
    output = DesignDocument.model_validate(output.model_dump())
    after = invariant_from_document(
        output,
        brief_id=original.brief_id,
        brief_payload=output.metadata.get("candidate_invariant_brief", {}),
    )
    for field in ("content_lock_hash", "asset_lock_hash", "business_value_hash", "canvas_hash"):
        if getattr(original, field) != getattr(after, field):
            raise RuntimeError(f"style variant mutated locked field: {field}")
    return output


def _region(element: DesignElement | None) -> tuple[float, float, float]:
    if element is None:
        return (.5, .5, 0.0)
    box = element.bbox_norm
    return (
        float(box.x + box.width / 2),
        float(box.y + box.height / 2),
        float(box.width * box.height),
    )


def structural_diversity(
    documents: dict[str, DesignDocument],
) -> dict[str, Any]:
    """Explainable geometry-only diversity; no visual embeddings are used."""

    features: dict[str, dict[str, Any]] = {}
    for candidate_id, document in documents.items():
        roles = _role_map(document)
        headline = next(iter(roles.get("headline", [])), None)
        cta = next(iter(roles.get("cta", [])), None)
        hero = _asset(document, "hero", "product", "logo")
        family = str(document.metadata.get("candidate_generation", {}).get("layout_family") or infer_layout_family(document))
        features[candidate_id] = {
            "family": family,
            "hero": _region(hero),
            "headline": _region(headline),
            "cta": _region(cta),
        }
    pairs = []
    for left_id, right_id in combinations(features, 2):
        left, right = features[left_id], features[right_id]
        family = float(left["family"] != right["family"])
        hero = min(1.0, sum(abs(a - b) for a, b in zip(left["hero"], right["hero"])))
        headline = min(1.0, sum(abs(a - b) for a, b in zip(left["headline"], right["headline"])))
        cta = min(1.0, sum(abs(a - b) for a, b in zip(left["cta"], right["cta"])))
        score = .35 * family + .30 * hero + .20 * headline + .15 * cta
        pairs.append({
            "first": left_id,
            "second": right_id,
            "layout_family_difference": family,
            "hero_geometry_difference": hero,
            "headline_geometry_difference": headline,
            "cta_geometry_difference": cta,
            "structural_diversity": score,
        })
    values = [float(item["structural_diversity"]) for item in pairs]
    return {
        "metric_version": "structural_candidate_diversity_v0.4_phase1.1",
        "generic_visual_embedding_used": False,
        "mean_pairwise_candidate_diversity": sum(values) / len(values) if values else 0.0,
        "minimum_pairwise_candidate_diversity": min(values, default=0.0),
        "distinct_layout_family_count": len({value["family"] for value in features.values()}),
        "passes": bool(values) and min(values) >= .16 and len({value["family"] for value in features.values()}) >= 3,
        "pairs": pairs,
    }


def infer_layout_family(document: DesignDocument) -> str:
    roles = _role_map(document)
    headline = next(iter(roles.get("headline", [])), None)
    hero = _asset(document, "hero", "product", "logo")
    if hero is None or headline is None:
        return "modular"
    hx, hy, ha = _region(hero)
    tx, ty, _ = _region(headline)
    if ha >= .45:
        return "image_dominant"
    if abs(hx - tx) < .12 and abs(hy - ty) > .25:
        return "stacked"
    if hx < .45 and tx > .55:
        return "split_left"
    if hx > .55 and tx < .45:
        return "split_right"
    if abs(hx - .5) < .12 and abs(tx - .5) < .12:
        return "centered"
    return "asymmetric"


def placeholder_metrics(document: DesignDocument) -> dict[str, float | int]:
    placeholders = [
        item
        for item in document.elements
        if item.metadata.get("placeholder") is True
        or item.metadata.get("editable_placeholder") is True
        or item.metadata.get("placeholder_only") is True
    ]
    return {
        "placeholder_count": len(placeholders),
        "placeholder_area_ratio": sum(
            float(item.bbox_norm.width * item.bbox_norm.height) for item in placeholders
        ),
    }


def evaluate_quality_floor(
    document: DesignDocument,
    metrics: dict[str, Any],
    *,
    regeneration_count: int = 0,
) -> QualityFloorResultV1:
    reasons: list[str] = []
    placeholders = placeholder_metrics(document)
    hero = _asset(document, "hero", "product")
    hero_area = _region(hero)[2]
    roles = _role_map(document)
    headline = next(iter(roles.get("headline", [])), None)
    coverage = float(metrics.get("coverage", 0.0))
    if float(metrics.get("outside_canvas_rate", 1.0)) > 0 or float(metrics.get("overlap_ratio", 1.0)) > .10 or float(metrics.get("text_fit_rate", 0.0)) < .95 or int(metrics.get("text_overflow_count", 1)) > 0:
        reasons.append("TECHNICAL_FAILURE")
    if coverage < .14:
        reasons.append("EXCESSIVE_WHITESPACE")
    category = str(document.metadata.get("phase1_1_case_id") or document.category)
    minimum_hero_area = .03 if category == "menu" else .08
    if category not in {"signage", "bang_hieu"} and hero is not None and hero_area < minimum_hero_area:
        reasons.append("WEAK_HERO")
    if float(placeholders["placeholder_area_ratio"]) > .30:
        reasons.append("PLACEHOLDER_DOMINANT")
    if headline is None or float(headline.bbox_norm.width * headline.bbox_norm.height) < .018:
        reasons.append("BROKEN_TEXT_RHYTHM")
    payload: dict[str, float | int | str | bool] = {
        "coverage": coverage,
        "overlap_ratio": float(metrics.get("overlap_ratio", 1.0)),
        "outside_canvas_rate": float(metrics.get("outside_canvas_rate", 1.0)),
        "text_fit_rate": float(metrics.get("text_fit_rate", 0.0)),
        "text_overflow_count": int(metrics.get("text_overflow_count", 0)),
        "hero_area_ratio": hero_area,
        **placeholders,
    }
    return QualityFloorResultV1(
        passed=not reasons,
        reasons=reasons,
        metrics=payload,
        regeneration_count=regeneration_count,
    )


__all__ = [
    "CandidateInvariantV1",
    "CandidateStyleVariantV1",
    "QualityFloorResultV1",
    "apply_candidate_style_variant",
    "assert_candidate_group_locked",
    "evaluate_quality_floor",
    "infer_layout_family",
    "invariant_from_document",
    "placeholder_metrics",
    "structural_diversity",
    "variants_for_category",
]
