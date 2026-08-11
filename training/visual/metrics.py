"""Frozen v0.3.1 visual diagnostics; these do not replace the v0.3 scorer."""

from __future__ import annotations

import statistics

from training.schemas.design import ColorSpec, DesignDocument
from training.typography.fitting import infer_text_role
from training.visual.density import evaluate_density
from training.visual.models import VisualStyleProfileV1
from training.visual.palette import contrast_ratio


VISUAL_METRICS_VERSION = "visual_diagnostics_v0.3.1_frozen_1"


def _hex(color: ColorSpec | None, fallback: str) -> str:
    if color is None or color.model != "hex":
        return fallback
    return str(color.values[0]).upper()


def evaluate_visual_quality(
    document: DesignDocument,
    *,
    profile: VisualStyleProfileV1,
) -> dict[str, float | int | str]:
    density = evaluate_density(document, profile)
    texts = [element for element in document.elements if element.text is not None]
    largest = max((float(item.text.font_size or 0) for item in texts), default=0.0)
    roles = {
        element.id: infer_text_role(element, largest_font=largest) for element in texts
    }
    body_sizes = [
        float(element.text.font_size or 0)
        for element in texts
        if roles[element.id] in {"body", "menu_item"}
    ]
    headline_sizes = [
        float(element.text.font_size or 0)
        for element in texts
        if roles[element.id] == "headline"
    ]
    base = statistics.median(body_sizes or [largest or 1.0])
    dominance = min(max(headline_sizes or [base]) / max(base, 1e-6) / 3.0, 1.0)
    ctas = [element for element in texts if roles[element.id] == "cta"]
    cta_area = sum(float(item.bbox_norm.width * item.bbox_norm.height) for item in ctas)
    cta_prominence = min(cta_area / 0.08, 1.0) if ctas else 0.0
    font_sizes = {round(float(item.text.font_size or 0), 2) for item in texts}
    font_weights = {str(item.text.font_weight or 400) for item in texts}
    differentiation = min((len(font_sizes) + len(font_weights) - 2) / 5, 1.0)
    background = profile.palette_roles.background
    contrast_values = [
        contrast_ratio(_hex(item.visual.fill, profile.palette_roles.body), background)
        for item in texts
    ]
    contrast = min(contrast_values, default=4.5)
    contrast_score = min(contrast / 7.0, 1.0)
    fills = {
        _hex(item.visual.fill, profile.palette_roles.surface)
        for item in document.elements
        if item.visual.fill is not None
    }
    palette_cohesion = max(0.0, 1 - max(0, len(fills) - 6) / 8)
    requested_assets = [
        item
        for item in document.elements
        if item.metadata.get("asset_required") or item.metadata.get("asset_intent")
    ]
    preserved_assets = [
        item
        for item in requested_assets
        if item.asset_ref is not None or item.metadata.get("editable_placeholder")
    ]
    asset_preservation = (
        len(preserved_assets) / len(requested_assets) if requested_assets else 1.0
    )
    decorations = [
        item for item in document.elements if item.metadata.get("decorative_role")
    ]
    max_decor = max(profile.max_decorative_elements, 1)
    decorative_balance = (
        max(0.0, 1 - abs(len(decorations) - max_decor * .55) / max_decor)
        if profile.max_decorative_elements
        else float(not decorations)
    )
    focal_areas = [
        float(item.bbox_norm.width * item.bbox_norm.height)
        for item in document.elements
        if item.metadata.get("asset_role") in {"hero", "product"}
        or item.metadata.get("role") in {"headline", "promotion"}
    ]
    focal_strength = min(max(focal_areas, default=0.0) / 0.22, 1.0)
    return {
        "metrics_version": VISUAL_METRICS_VERSION,
        "density_fit": float(density.density_fit),
        "density_error": float(density.density_error),
        "palette_cohesion": palette_cohesion,
        "contrast": contrast_score,
        "minimum_text_contrast_ratio": contrast,
        "headline_dominance": dominance,
        "cta_prominence": cta_prominence,
        "typography_differentiation": differentiation,
        "asset_intent_preservation": asset_preservation,
        "decorative_balance": decorative_balance,
        "focal_point_strength": focal_strength,
        "decorative_element_count": len(decorations),
        "asset_intent_count": len(requested_assets),
    }


__all__ = ["VISUAL_METRICS_VERSION", "evaluate_visual_quality"]
