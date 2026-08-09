"""Deterministic structured baseline used before a trained model is available."""

from __future__ import annotations

import hashlib

from training.schemas.design import (
    BoundingBox,
    CanvasSpec,
    ColorSpec,
    DesignDocument,
    DesignElement,
    SourceSpec,
    TextSpec,
    VisualSpec,
    normalize_bbox,
)


def _palette(prompt: str) -> tuple[ColorSpec, ColorSpec]:
    normalized = prompt.casefold()
    if "kem" in normalized and "vàng" in normalized:
        return (
            ColorSpec(model="cmyk", values=[0, 5, 20, 0]),
            ColorSpec(model="cmyk", values=[0, 20, 70, 20]),
        )
    if "đen" in normalized or "sang trọng" in normalized:
        return (
            ColorSpec(model="cmyk", values=[60, 40, 40, 100]),
            ColorSpec(model="cmyk", values=[0, 0, 0, 0]),
        )
    return (
        ColorSpec(model="cmyk", values=[0, 0, 0, 0]),
        ColorSpec(model="cmyk", values=[0, 0, 0, 100]),
    )


def generate_baseline_design(
    prompt: str,
    width_mm: float,
    height_mm: float,
) -> DesignDocument:
    """Create a valid editable baseline; this is not a trained-model result."""

    prompt = prompt.strip()
    if not prompt:
        raise ValueError("prompt cannot be empty")
    canvas = CanvasSpec(width=width_mm, height=height_mm, unit="mm")
    background_color, text_color = _palette(prompt)
    background_bbox = BoundingBox(x=0, y=0, width=width_mm, height=height_mm)
    headline_bbox = BoundingBox(
        x=width_mm * 0.1,
        y=height_mm * 0.12,
        width=width_mm * 0.8,
        height=height_mm * 0.24,
    )
    subtitle_bbox = BoundingBox(
        x=width_mm * 0.15,
        y=height_mm * 0.72,
        width=width_mm * 0.7,
        height=height_mm * 0.12,
    )
    digest = hashlib.sha256(
        f"{prompt}|{width_mm}|{height_mm}".encode("utf-8")
    ).hexdigest()[:16]
    headline = prompt[:160]

    return DesignDocument(
        sample_id=f"synthetic-baseline:{digest}",
        source=SourceSpec(
            name="synthetic_owned",
            split="inference",
            license_class="production_safe",
            upstream_id=digest,
            commercial_allowed=True,
        ),
        canvas=canvas,
        category="poster",
        elements=[
            DesignElement(
                id="background",
                name="Background",
                type="rectangle",
                bbox=background_bbox,
                bbox_norm=normalize_bbox(background_bbox, canvas),
                z_index=0,
                layer="background",
                visual=VisualSpec(fill=background_color),
            ),
            DesignElement(
                id="headline",
                name="Headline",
                type="text",
                bbox=headline_bbox,
                bbox_norm=normalize_bbox(headline_bbox, canvas),
                z_index=10,
                layer="typography",
                text=TextSpec(
                    content=headline,
                    font_family="Arial",
                    font_size=max(24.0, min(width_mm, height_mm) * 0.08),
                    font_weight=700,
                    alignment="center",
                    line_height=1.1,
                    tracking=0,
                ),
                visual=VisualSpec(fill=text_color),
            ),
            DesignElement(
                id="subtitle",
                name="Subtitle",
                type="text",
                bbox=subtitle_bbox,
                bbox_norm=normalize_bbox(subtitle_bbox, canvas),
                z_index=11,
                layer="typography",
                text=TextSpec(
                    content="DESIGN AI STRUCTURED BASELINE",
                    font_family="Arial",
                    font_size=max(12.0, min(width_mm, height_mm) * 0.035),
                    font_weight=400,
                    alignment="center",
                    line_height=1.1,
                    tracking=0,
                ),
                visual=VisualSpec(fill=text_color),
            ),
        ],
        metadata={
            "prompt": prompt,
            "generator": "deterministic_structured_baseline_v0",
            "trained_model": False,
            "warning": "Baseline output proves the contract, not model quality.",
        },
    )
