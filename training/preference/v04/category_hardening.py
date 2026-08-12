"""Category-scoped art direction for the v0.4 Phase 1.2 mini pilot."""

from __future__ import annotations

from itertools import combinations
from typing import Any, Literal

from pydantic import Field, model_validator

from training.preference.v04.hardening import (
    CandidateInvariantV1,
    LayoutFamily,
    QualityFloorResultV1,
    invariant_from_document,
    placeholder_metrics,
)
from training.preference.v04.models import StrictModel
from training.schemas.design import (
    BoundingBox,
    ColorSpec,
    DesignDocument,
    DesignElement,
    VisualSpec,
    normalize_bbox,
)
from training.typography.fitting import infer_text_role


SelectedCategory = Literal["sale", "signage", "spa"]


class CategoryArtDirectionProfileV2(StrictModel):
    category: SelectedCategory
    eligible_layout_families: list[LayoutFamily] = Field(min_length=3, max_length=6)
    preferred_hero_area_range: tuple[float, float]
    preferred_whitespace_range: tuple[float, float]
    headline_scale_range: tuple[float, float]
    headline_width_range: tuple[float, float]
    cta_prominence_range: tuple[float, float]
    typography_profiles: list[str] = Field(min_length=1, max_length=5)
    alignment_preferences: list[Literal["left", "center", "right"]]
    image_text_ratio: tuple[float, float]
    decoration_density: float = Field(ge=0, le=0.35)
    surface_strategy: list[str] = Field(min_length=1, max_length=5)
    minimum_candidate_diversity: float = Field(ge=0.16, le=1)

    @model_validator(mode="after")
    def bounded_ranges(self) -> "CategoryArtDirectionProfileV2":
        for name in (
            "preferred_hero_area_range",
            "preferred_whitespace_range",
            "headline_scale_range",
            "headline_width_range",
            "cta_prominence_range",
            "image_text_ratio",
        ):
            low, high = getattr(self, name)
            if low < 0 or high > 2 or low > high:
                raise ValueError(f"invalid bounded range: {name}")
        if len(set(self.eligible_layout_families)) < 3:
            raise ValueError("category profile requires at least three layout families")
        return self


class CategoryArtDirectionVariantV2(StrictModel):
    variant_id: str
    category: SelectedCategory
    layout_family: LayoutFamily
    hero_box: tuple[float, float, float, float]
    logo_box: tuple[float, float, float, float] | None = None
    headline_box: tuple[float, float, float, float]
    body_box: tuple[float, float, float, float] | None = None
    promotion_box: tuple[float, float, float, float] | None = None
    cta_box: tuple[float, float, float, float] | None = None
    palette: Literal["light", "dark", "warm", "campaign"]
    surface_strategy: Literal[
        "editorial_panel",
        "readability_panel",
        "campaign_cluster",
        "campaign_split",
        "identity_band",
        "monument_frame",
        "edge_balance",
    ]
    headline_scale: float = Field(ge=0.9, le=1.8)
    headline_alignment: Literal["left", "center", "right"]
    accent_side: Literal["left", "right", "top", "bottom"]

    @model_validator(mode="after")
    def boxes_stay_on_canvas(self) -> "CategoryArtDirectionVariantV2":
        for name in (
            "hero_box",
            "logo_box",
            "headline_box",
            "body_box",
            "promotion_box",
            "cta_box",
        ):
            box = getattr(self, name)
            if box is None:
                continue
            x, y, width, height = box
            if min(box) < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
                raise ValueError(f"{name} is outside normalized canvas")
        return self


_PROFILES: dict[SelectedCategory, CategoryArtDirectionProfileV2] = {
    "sale": CategoryArtDirectionProfileV2(
        category="sale",
        eligible_layout_families=["image_dominant", "type_dominant", "asymmetric", "split_left"],
        preferred_hero_area_range=(.15, .40),
        preferred_whitespace_range=(.12, .42),
        headline_scale_range=(1.20, 1.75),
        headline_width_range=(.36, .84),
        cta_prominence_range=(.035, .075),
        typography_profiles=["bold_condensed_sans", "campaign_sans"],
        alignment_preferences=["left", "center"],
        image_text_ratio=(.42, .58),
        decoration_density=.16,
        surface_strategy=["campaign_cluster", "campaign_split"],
        minimum_candidate_diversity=.18,
    ),
    "signage": CategoryArtDirectionProfileV2(
        category="signage",
        eligible_layout_families=["split_left", "centered", "type_dominant", "edge_aligned"],
        preferred_hero_area_range=(.16, .50),
        preferred_whitespace_range=(.18, .50),
        headline_scale_range=(1.05, 1.55),
        headline_width_range=(.34, .62),
        cta_prominence_range=(0, 0),
        typography_profiles=["distance_sans", "identity_sans"],
        alignment_preferences=["left", "center", "right"],
        image_text_ratio=(.45, .55),
        decoration_density=.08,
        surface_strategy=["identity_band", "monument_frame", "edge_balance"],
        minimum_candidate_diversity=.18,
    ),
    "spa": CategoryArtDirectionProfileV2(
        category="spa",
        eligible_layout_families=["editorial", "image_dominant", "asymmetric", "stacked"],
        preferred_hero_area_range=(.35, 1.0),
        preferred_whitespace_range=(.22, .58),
        headline_scale_range=(1.05, 1.40),
        headline_width_range=(.32, .48),
        cta_prominence_range=(.025, .055),
        typography_profiles=["refined_serif_sans", "editorial_serif_sans"],
        alignment_preferences=["left", "center"],
        image_text_ratio=(.48, .72),
        decoration_density=.07,
        surface_strategy=["editorial_panel", "readability_panel"],
        minimum_candidate_diversity=.18,
    ),
}


_VARIANTS: dict[SelectedCategory, tuple[CategoryArtDirectionVariantV2, ...]] = {
    "sale": (
        CategoryArtDirectionVariantV2(variant_id="sale_v3_product_focal", category="sale", layout_family="image_dominant", hero_box=(.45, .19, .51, .61), logo_box=(.05, .035, .28, .065), headline_box=(.06, .16, .36, .18), promotion_box=(.06, .39, .35, .15), cta_box=(.06, .72, .34, .11), palette="campaign", surface_strategy="campaign_cluster", headline_scale=1.45, headline_alignment="left", accent_side="left"),
        CategoryArtDirectionVariantV2(variant_id="sale_v3_type_focal", category="sale", layout_family="type_dominant", hero_box=(.28, .49, .44, .36), logo_box=(.05, .035, .28, .065), headline_box=(.08, .13, .84, .17), promotion_box=(.18, .33, .64, .14), cta_box=(.25, .86, .50, .09), palette="dark", surface_strategy="campaign_cluster", headline_scale=1.70, headline_alignment="center", accent_side="top"),
        CategoryArtDirectionVariantV2(variant_id="sale_v3_asymmetric_tension", category="sale", layout_family="asymmetric", hero_box=(.48, .23, .48, .57), logo_box=(.06, .035, .28, .065), headline_box=(.06, .14, .41, .19), promotion_box=(.08, .39, .35, .14), cta_box=(.09, .72, .34, .11), palette="campaign", surface_strategy="campaign_cluster", headline_scale=1.52, headline_alignment="left", accent_side="right"),
        CategoryArtDirectionVariantV2(variant_id="sale_v3_split_campaign", category="sale", layout_family="split_left", hero_box=(.05, .24, .43, .57), logo_box=(.66, .035, .29, .065), headline_box=(.53, .15, .41, .18), promotion_box=(.55, .39, .37, .14), cta_box=(.56, .72, .35, .11), palette="light", surface_strategy="campaign_split", headline_scale=1.35, headline_alignment="right", accent_side="bottom"),
    ),
    "signage": (
        CategoryArtDirectionVariantV2(variant_id="signage_v3_distance_identity", category="signage", layout_family="split_left", hero_box=(.035, .14, .48, .72), headline_box=(.57, .27, .37, .36), palette="dark", surface_strategy="identity_band", headline_scale=1.22, headline_alignment="left", accent_side="bottom"),
        CategoryArtDirectionVariantV2(variant_id="signage_v3_monument_center", category="signage", layout_family="centered", hero_box=(.20, .12, .60, .47), headline_box=(.29, .67, .42, .20), palette="dark", surface_strategy="monument_frame", headline_scale=1.08, headline_alignment="center", accent_side="top"),
        CategoryArtDirectionVariantV2(variant_id="signage_v3_name_bar", category="signage", layout_family="type_dominant", hero_box=(.57, .15, .39, .70), headline_box=(.05, .24, .45, .43), palette="light", surface_strategy="identity_band", headline_scale=1.48, headline_alignment="left", accent_side="left"),
        CategoryArtDirectionVariantV2(variant_id="signage_v3_edge_signature", category="signage", layout_family="edge_aligned", hero_box=(.08, .17, .40, .66), headline_box=(.56, .31, .34, .30), palette="warm", surface_strategy="edge_balance", headline_scale=1.18, headline_alignment="right", accent_side="right"),
    ),
    "spa": (
        CategoryArtDirectionVariantV2(variant_id="spa_v3_editorial_image_led", category="spa", layout_family="editorial", hero_box=(0, 0, .46, 1), logo_box=(.52, .08, .21, .14), headline_box=(.52, .30, .42, .16), body_box=(.52, .49, .40, .13), cta_box=(.52, .73, .30, .13), palette="light", surface_strategy="editorial_panel", headline_scale=1.18, headline_alignment="left", accent_side="right"),
        CategoryArtDirectionVariantV2(variant_id="spa_v3_full_bleed_restrained", category="spa", layout_family="image_dominant", hero_box=(0, 0, 1, 1), logo_box=(.05, .08, .20, .14), headline_box=(.05, .31, .36, .17), body_box=(.05, .53, .34, .13), cta_box=(.05, .75, .26, .13), palette="dark", surface_strategy="readability_panel", headline_scale=1.12, headline_alignment="left", accent_side="left"),
        CategoryArtDirectionVariantV2(variant_id="spa_v3_asymmetric_luxury", category="spa", layout_family="asymmetric", hero_box=(.52, .07, .44, .86), logo_box=(.05, .08, .21, .14), headline_box=(.05, .30, .41, .17), body_box=(.14, .52, .32, .12), cta_box=(.21, .73, .25, .12), palette="warm", surface_strategy="editorial_panel", headline_scale=1.28, headline_alignment="left", accent_side="bottom"),
        CategoryArtDirectionVariantV2(variant_id="spa_v3_panoramic_signature", category="spa", layout_family="stacked", hero_box=(.18, 0, .64, 1), logo_box=(.04, .07, .18, .13), headline_box=(.05, .65, .36, .15), body_box=(.44, .66, .31, .12), cta_box=(.76, .67, .20, .13), palette="dark", surface_strategy="readability_panel", headline_scale=1.08, headline_alignment="left", accent_side="bottom"),
    ),
}


def profile_for_category(category: str) -> CategoryArtDirectionProfileV2:
    if category not in _PROFILES:
        raise ValueError(f"Phase 1.2 is scoped only to {sorted(_PROFILES)}")
    return _PROFILES[category]  # type: ignore[index]


def variants_for_category_v2(category: str) -> tuple[CategoryArtDirectionVariantV2, ...]:
    profile = profile_for_category(category)
    variants = _VARIANTS[profile.category]
    if len({item.layout_family for item in variants}) < 3:
        raise RuntimeError("category profile produced insufficient composition families")
    return variants


def _color(value: str) -> ColorSpec:
    return ColorSpec(model="hex", values=[value])


def _set_box(document: DesignDocument, element: DesignElement, box: tuple[float, float, float, float]) -> None:
    x, y, width, height = box
    absolute = BoundingBox(
        x=x * float(document.canvas.width),
        y=y * float(document.canvas.height),
        width=width * float(document.canvas.width),
        height=height * float(document.canvas.height),
    )
    element.bbox = absolute
    element.bbox_norm = normalize_bbox(absolute, document.canvas)


def _roles(document: DesignDocument) -> dict[str, list[DesignElement]]:
    text = [item for item in document.elements if item.text is not None]
    largest = max((float(item.text.font_size or 0) for item in text), default=0)
    result: dict[str, list[DesignElement]] = {}
    for element in text:
        role = str(element.metadata.get("role") or infer_text_role(element, largest_font=largest))
        content = element.text.content.casefold() if element.text else ""
        if (
            "offer" in element.id.casefold()
            or "discount" in element.id.casefold()
            or "%" in content
            or "giảm" in content
        ):
            role = "promotion"
        result.setdefault(role, []).append(element)
    return result


def _asset(document: DesignDocument, *roles: str) -> DesignElement | None:
    for role in roles:
        for element in document.elements:
            if element.asset_ref and str(element.metadata.get("asset_role") or element.metadata.get("role")) == role:
                return element
    return None


def _shape(
    document: DesignDocument,
    *,
    element_id: str,
    box: tuple[float, float, float, float],
    fill: str,
    opacity: float = 1,
    kind: Literal["rectangle", "ellipse"] = "rectangle",
    rotation: float = 0,
) -> DesignElement:
    absolute = BoundingBox(
        x=box[0] * float(document.canvas.width),
        y=box[1] * float(document.canvas.height),
        width=box[2] * float(document.canvas.width),
        height=box[3] * float(document.canvas.height),
    )
    return DesignElement(
        id=element_id,
        name="Phase 1.2 category art-direction surface",
        type=kind,
        bbox=absolute,
        bbox_norm=normalize_bbox(absolute, document.canvas),
        rotation=rotation,
        z_index=-18,
        layer="background",
        visual=VisualSpec(fill=_color(fill), opacity=opacity),
        metadata={
            "decorative_role": "phase1_2_surface",
            "generation_version": "candidate_generation_v3_category_hardened",
            "editable": True,
        },
    )


def _apply_typography(document: DesignDocument, variant: CategoryArtDirectionVariantV2) -> None:
    roles = _roles(document)
    short = min(float(document.canvas.width), float(document.canvas.height))
    for role, elements in roles.items():
        for element in elements:
            assert element.text is not None
            original = element.metadata.get("typography_fit", {}).get("original_content")
            if isinstance(original, str):
                element.text.content = original
            if variant.category == "spa" and role == "headline":
                element.text.font_family = "DejaVuSerif.ttf"
                element.text.font_weight = 650
                element.text.tracking = .7
            elif variant.category in {"sale", "signage"} and role in {"headline", "promotion"}:
                element.text.font_family = "DejaVuSansCondensed.ttf"
                element.text.font_weight = 800
                element.text.tracking = 1.0 if variant.category == "signage" else -.2
            else:
                element.text.font_family = "DejaVuSans.ttf"
                element.text.font_weight = 500
                element.text.tracking = 0
            element.text.alignment = variant.headline_alignment if role == "headline" else "left"
            if role == "headline":
                element.text.font_size = max(
                    short * .075,
                    float(element.text.font_size or 8) * variant.headline_scale,
                )
            elif role == "promotion":
                element.text.font_weight = 850
            elif role == "cta":
                element.text.font_weight = 750


def _place(document: DesignDocument, variant: CategoryArtDirectionVariantV2) -> None:
    hero = _asset(document, "hero", "product", "logo")
    logo = _asset(document, "logo")
    if variant.category == "signage":
        logo = None
    if hero is not None:
        _set_box(document, hero, variant.hero_box)
        if variant.category == "spa" and variant.surface_strategy == "readability_panel":
            # Full-bleed photography is an editable background asset.  Keeping
            # it in the content overlap graph would falsely classify every
            # intentional text overlay as a structural collision.
            hero.layer = "background"
            hero.z_index = -30
    if logo is not None and variant.logo_box is not None:
        _set_box(document, logo, variant.logo_box)
    boxes = {
        "headline": variant.headline_box,
        "body": variant.body_box,
        "promotion": variant.promotion_box,
        "cta": variant.cta_box,
    }
    for role, box in boxes.items():
        if box is None:
            continue
        for element in _roles(document).get(role, []):
            _set_box(document, element, box)


def _apply_surfaces(document: DesignDocument, variant: CategoryArtDirectionVariantV2) -> None:
    colors = {
        "light": ("#F7F2E9", "#29221E", "#B98942"),
        "warm": ("#EDE1D0", "#2C2420", "#9A6B37"),
        "dark": ("#171A1D", "#F7F1E7", "#D6B15E"),
        "campaign": ("#FAF0E5", "#2B1F2A", "#B23963"),
    }
    background, text_color, accent = colors[variant.palette]
    document.canvas.background = VisualSpec(fill=_color(background))
    for element in document.elements:
        if element.id == "background":
            element.visual.fill = _color(background)
        if element.text is not None:
            element.visual.fill = _color(text_color)
    surfaces: list[DesignElement] = []
    if variant.surface_strategy == "readability_panel":
        if variant.category == "spa" and variant.layout_family == "stacked":
            panel = (0, .59, 1, .41)
        else:
            panel = (.025, .045, .42, .91)
        surfaces.append(_shape(document, element_id=f"v0412_{variant.variant_id}_panel", box=panel, fill="#171A1D" if variant.palette == "dark" else "#FFFDF8", opacity=.91))
    elif variant.surface_strategy == "editorial_panel":
        side = (.48, .04, .50, .92) if variant.hero_box[0] == 0 else (.025, .045, .45, .91)
        surfaces.append(_shape(document, element_id=f"v0412_{variant.variant_id}_editorial", box=side, fill="#FFFDF8", opacity=.94))
    elif variant.surface_strategy == "campaign_cluster":
        surfaces.extend(
            [
                _shape(document, element_id=f"v0412_{variant.variant_id}_campaign_rule", box=(.04, .025, .92, .015), fill=accent),
                _shape(document, element_id=f"v0412_{variant.variant_id}_campaign_orb", box=(.72, .75, .20, .16), fill=accent, opacity=.24, kind="ellipse"),
                _shape(document, element_id=f"v0412_{variant.variant_id}_campaign_slash", box=(.65, .08, .35, .055), fill=accent, opacity=.35, rotation=-8),
            ]
        )
    elif variant.surface_strategy == "campaign_split":
        surfaces.extend(
            [
                _shape(document, element_id=f"v0412_{variant.variant_id}_split", box=(.50, 0, .50, 1), fill="#FFF9F0", opacity=.94),
                _shape(document, element_id=f"v0412_{variant.variant_id}_split_rule", box=(.49, .05, .012, .90), fill=accent),
            ]
        )
    elif variant.surface_strategy == "identity_band":
        side = (0, 0, .53, 1) if variant.layout_family == "type_dominant" else (0, 0, 1, 1)
        surfaces.append(_shape(document, element_id=f"v0412_{variant.variant_id}_identity", box=side, fill=background))
        if variant.category == "signage" and variant.layout_family == "type_dominant":
            surfaces.append(
                _shape(
                    document,
                    element_id=f"v0412_{variant.variant_id}_logo_contrast",
                    box=(.53, .08, .45, .84),
                    fill="#171A1D",
                )
            )
        rule = (.035, .88, .22, .025) if variant.accent_side != "left" else (.02, .12, .012, .76)
        surfaces.append(_shape(document, element_id=f"v0412_{variant.variant_id}_rule", box=rule, fill=accent))
    elif variant.surface_strategy == "monument_frame":
        surfaces.extend(
            [
                _shape(document, element_id=f"v0412_{variant.variant_id}_top", box=(.02, .04, .96, .025), fill=accent),
                _shape(document, element_id=f"v0412_{variant.variant_id}_bottom", box=(.02, .935, .96, .025), fill=accent),
            ]
        )
    elif variant.surface_strategy == "edge_balance":
        if variant.category == "signage":
            x, y, width, height = variant.hero_box
            surfaces.append(
                _shape(
                    document,
                    element_id=f"v0412_{variant.variant_id}_logo_contrast",
                    box=(max(0, x - .025), max(0, y - .08), min(.96 - x, width + .05), min(1 - max(0, y - .08), height + .16)),
                    fill="#171A1D",
                )
            )
        surfaces.append(_shape(document, element_id=f"v0412_{variant.variant_id}_edge", box=(.965, .10, .015, .80), fill=accent))
    roles = _roles(document)
    for cta in roles.get("cta", []):
        box = cta.bbox_norm
        surfaces.append(
            _shape(
                document,
                element_id=f"v0412_{variant.variant_id}_cta",
                box=(
                    max(0, float(box.x) - .012),
                    max(0, float(box.y) - .008),
                    min(1 - max(0, float(box.x) - .012), float(box.width) + .024),
                    min(1 - max(0, float(box.y) - .008), float(box.height) + .016),
                ),
                fill=accent,
            )
        )
        cta.visual.fill = _color("#171819" if variant.palette != "dark" else "#111315")
    for promotion in roles.get("promotion", []):
        promotion.visual.fill = _color(accent)
    document.elements.extend(surfaces)


def apply_category_hardening_v2(
    document: DesignDocument,
    variant: CategoryArtDirectionVariantV2,
) -> DesignDocument:
    """Apply one bounded category profile while preserving all locked facts."""

    profile_for_category(variant.category)
    output = document.model_copy(deep=True)
    brief_id = str(output.metadata.get("brief_id") or output.sample_id)
    brief = output.metadata.get("candidate_invariant_brief", {})
    before = invariant_from_document(output, brief_id=brief_id, brief_payload=brief)
    output.elements = [
        item
        for item in output.elements
        if not item.metadata.get("decorative_role")
        or item.metadata.get("decorative_role") == "canvas_background"
    ]
    _apply_typography(output, variant)
    _place(output, variant)
    _apply_surfaces(output, variant)
    output.metadata = {
        **output.metadata,
        "candidate_generation": {
            "generation_version": "candidate_generation_v3_category_hardened",
            "quality_floor_version": "category_quality_floor_v2",
            "layout_family": variant.layout_family,
            "variant_id": variant.variant_id,
            "category_profile": variant.category,
            "content_diversity_used": False,
            "visual_rag_enabled": False,
            "vision_critic_enabled": False,
        },
    }
    output = DesignDocument.model_validate(output.model_dump())
    after = invariant_from_document(output, brief_id=before.brief_id, brief_payload=brief)
    for field in ("content_lock_hash", "asset_lock_hash", "business_value_hash", "canvas_hash"):
        if getattr(before, field) != getattr(after, field):
            raise RuntimeError(f"category hardening mutated locked field: {field}")
    return output


def _center(element: DesignElement | None) -> tuple[float, float, float]:
    if element is None:
        return (.5, .5, 0)
    box = element.bbox_norm
    return (
        float(box.x + box.width / 2),
        float(box.y + box.height / 2),
        float(box.width * box.height),
    )


def evaluate_category_quality_floor_v2(
    document: DesignDocument,
    metrics: dict[str, Any],
    *,
    regeneration_count: int = 0,
) -> QualityFloorResultV1:
    category = str(document.metadata.get("candidate_generation", {}).get("category_profile"))
    profile = profile_for_category(category)
    roles = _roles(document)
    headline = next(iter(roles.get("headline", [])), None)
    cta = next(iter(roles.get("cta", [])), None)
    focal_asset = _asset(document, "hero", "product", "logo")
    hero_x, hero_y, hero_area = _center(focal_asset)
    headline_x, headline_y, headline_area = _center(headline)
    cta_x, cta_y, cta_area = _center(cta)
    reasons: list[str] = []
    outside = float(metrics.get("outside_canvas_rate", 1))
    overlap = float(metrics.get("overlap_ratio", 1))
    fit = float(metrics.get("text_fit_rate", 0))
    overflow = int(metrics.get("text_overflow_count", 1))
    coverage = float(metrics.get("coverage", 0))
    effective_coverage = max(coverage, hero_area)
    placeholders = placeholder_metrics(document)
    if outside > 0 or overlap > .10 or fit < .95 or overflow > 0:
        reasons.append("TECHNICAL_FAILURE")
    if effective_coverage < .16:
        reasons.append("EXCESSIVE_UNUSED_SPACE")
    if headline is None or headline_area < .025:
        reasons.append("HEADLINE_TOO_WEAK")
    if focal_asset is None or hero_area < profile.preferred_hero_area_range[0]:
        reasons.append("ASSET_TOO_SMALL")
    if max(hero_area, headline_area) < .07:
        reasons.append("WEAK_FOCAL_POINT")
    if cta is not None:
        if cta_area < profile.cta_prominence_range[0]:
            reasons.append("DISCONNECTED_CTA")
        if abs(cta_x - headline_x) + abs(cta_y - headline_y) > .82:
            reasons.append("DISCONNECTED_CTA")
    for element in (item for items in roles.values() for item in items):
        assert element.text is not None
        lines = [line.strip() for line in element.text.content.splitlines() if line.strip()]
        if len(lines) >= 3 and sum(len(line.split()) == 1 for line in lines) >= 3:
            reasons.append("UNINTENTIONAL_TEXT_FRAGMENTATION")
            break
    mass_x = (hero_x * hero_area + headline_x * headline_area + cta_x * cta_area) / max(
        hero_area + headline_area + cta_area, .0001
    )
    mass_y = (hero_y * hero_area + headline_y * headline_area + cta_y * cta_area) / max(
        hero_area + headline_area + cta_area, .0001
    )
    if abs(mass_x - .5) > .35 or abs(mass_y - .5) > .35:
        reasons.append("POOR_VISUAL_MASS_BALANCE")
    if float(placeholders["placeholder_area_ratio"]) > .20:
        reasons.append("PLACEHOLDER_DOMINANT")
    reasons = list(dict.fromkeys(reasons))
    return QualityFloorResultV1(
        passed=not reasons,
        reasons=reasons,
        metrics={
            "quality_floor_version": "category_quality_floor_v2",
            "category": category,
            "coverage": coverage,
            "effective_coverage": effective_coverage,
            "overlap_ratio": overlap,
            "outside_canvas_rate": outside,
            "text_fit_rate": fit,
            "text_overflow_count": overflow,
            "hero_area_ratio": hero_area,
            "headline_area_ratio": headline_area,
            "cta_area_ratio": cta_area,
            "visual_mass_x": mass_x,
            "visual_mass_y": mass_y,
            **placeholders,
        },
        regeneration_count=regeneration_count,
    )


def category_group_diversity(
    documents: dict[str, DesignDocument],
) -> dict[str, Any]:
    features = {}
    for candidate_id, document in documents.items():
        roles = _roles(document)
        features[candidate_id] = {
            "family": str(document.metadata["candidate_generation"]["layout_family"]),
            "hero": _center(_asset(document, "hero", "product", "logo")),
            "headline": _center(next(iter(roles.get("headline", [])), None)),
            "cta": _center(next(iter(roles.get("cta", [])), None)),
        }
    pairs = []
    for left_id, right_id in combinations(features, 2):
        left, right = features[left_id], features[right_id]
        family = float(left["family"] != right["family"])
        hero = min(1.0, sum(abs(a - b) for a, b in zip(left["hero"], right["hero"])))
        headline = min(1.0, sum(abs(a - b) for a, b in zip(left["headline"], right["headline"])))
        cta = min(1.0, sum(abs(a - b) for a, b in zip(left["cta"], right["cta"])))
        score = .35 * family + .32 * hero + .21 * headline + .12 * cta
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
    categories = {
        str(document.metadata["candidate_generation"]["category_profile"])
        for document in documents.values()
    }
    if len(categories) != 1:
        raise ValueError("category diversity requires one category group")
    profile = profile_for_category(next(iter(categories)))
    family_count = len({item["family"] for item in features.values()})
    minimum = min(values, default=0)
    return {
        "metric_version": "category_candidate_diversity_v0.4_phase1.2",
        "generic_visual_embedding_used": False,
        "mean_pairwise_candidate_diversity": sum(values) / len(values) if values else 0,
        "minimum_pairwise_candidate_diversity": minimum,
        "distinct_layout_family_count": family_count,
        "minimum_required": profile.minimum_candidate_diversity,
        "passes": bool(values) and minimum >= profile.minimum_candidate_diversity and family_count >= 3,
        "pairs": pairs,
    }


__all__ = [
    "CategoryArtDirectionProfileV2",
    "CategoryArtDirectionVariantV2",
    "apply_category_hardening_v2",
    "category_group_diversity",
    "evaluate_category_quality_floor_v2",
    "profile_for_category",
    "variants_for_category_v2",
]
