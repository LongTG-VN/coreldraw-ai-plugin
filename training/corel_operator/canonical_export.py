"""Deterministic page-anchored raster geometry for Corel integrity QA."""

from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import Field

from training.corel_operator.models import StrictModel


_INCHES_PER_UNIT: dict[str, Decimal] = {
    "tenth_micron": Decimal("0.000003937007874015748"),
    "in": Decimal("1"),
    "ft": Decimal("12"),
    "mm": Decimal("0.03937007874015748"),
    "cm": Decimal("0.3937007874015748"),
    "mile": Decimal("63360"),
    "m": Decimal("39.37007874015748"),
    "km": Decimal("39370.07874015748"),
    "yard": Decimal("36"),
    "pica": Decimal("0.1666666666666667"),
    "pt": Decimal("0.01388888888888889"),
    "q": Decimal("0.00984251968503937"),
}


class CanonicalPageGeometryV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    page_width: float = Field(gt=0)
    page_height: float = Field(gt=0)
    unit: str
    dpi: int = Field(ge=1)
    unbounded_width_px: int = Field(ge=1)
    unbounded_height_px: int = Field(ge=1)
    width_px: int = Field(ge=1)
    height_px: int = Field(ge=1)
    scale: float = Field(gt=0, le=1)
    max_dimension: int = Field(ge=1)
    max_pixels: int = Field(ge=1)


class CanonicalExportEvidenceV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    path: str
    geometry: CanonicalPageGeometryV1
    actual_width_px: int = Field(ge=1)
    actual_height_px: int = Field(ge=1)
    range: Literal["current_page"] = "current_page"
    maintain_aspect: Literal[False] = False
    image_type: Literal["rgb"] = "rgb"
    file_size_bytes: int = Field(ge=1)
    dimensions_verified: bool


def _rounded_pixel_count(value: Decimal) -> int:
    return max(1, int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def canonical_page_dimensions(
    page_width: float,
    page_height: float,
    *,
    unit: str,
    dpi: int = 200,
    max_dimension: int = 2400,
    max_pixels: int = 8_000_000,
) -> CanonicalPageGeometryV1:
    """Map verified page-space dimensions to one bounded canonical pixel frame."""

    width = float(page_width)
    height = float(page_height)
    normalized_unit = unit.casefold().strip()
    if not math.isfinite(width) or not math.isfinite(height) or width <= 0 or height <= 0:
        raise ValueError("page dimensions must be finite and positive")
    if dpi < 1 or max_dimension < 1 or max_pixels < 1:
        raise ValueError("canonical export bounds must be positive")
    if normalized_unit == "px":
        # Corel pixels are interpreted at the configured document/export DPI.
        width_pixels = _rounded_pixel_count(Decimal(str(width)))
        height_pixels = _rounded_pixel_count(Decimal(str(height)))
    else:
        inches = _INCHES_PER_UNIT.get(normalized_unit)
        if inches is None:
            raise ValueError(f"unsupported Corel page unit for canonical export: {unit}")
        width_pixels = _rounded_pixel_count(Decimal(str(width)) * inches * dpi)
        height_pixels = _rounded_pixel_count(Decimal(str(height)) * inches * dpi)

    scale = min(
        1.0,
        max_dimension / width_pixels,
        max_dimension / height_pixels,
        math.sqrt(max_pixels / (width_pixels * height_pixels)),
    )
    bounded_width = max(
        1,
        int((Decimal(width_pixels) * Decimal(str(scale))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
    )
    bounded_height = max(
        1,
        int((Decimal(height_pixels) * Decimal(str(scale))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
    )
    return CanonicalPageGeometryV1(
        page_width=width,
        page_height=height,
        unit=normalized_unit,
        dpi=dpi,
        unbounded_width_px=width_pixels,
        unbounded_height_px=height_pixels,
        width_px=bounded_width,
        height_px=bounded_height,
        scale=scale,
        max_dimension=max_dimension,
        max_pixels=max_pixels,
    )


def canonical_export_evidence(
    path: Path,
    geometry: CanonicalPageGeometryV1,
) -> CanonicalExportEvidenceV1:
    resolved = path.expanduser().resolve(strict=True)
    with Image.open(resolved) as image:
        actual_width, actual_height = image.size
    verified = (actual_width, actual_height) == (geometry.width_px, geometry.height_px)
    return CanonicalExportEvidenceV1(
        path=str(resolved),
        geometry=geometry,
        actual_width_px=actual_width,
        actual_height_px=actual_height,
        file_size_bytes=resolved.stat().st_size,
        dimensions_verified=verified,
    )


__all__ = [
    "CanonicalExportEvidenceV1",
    "CanonicalPageGeometryV1",
    "canonical_export_evidence",
    "canonical_page_dimensions",
]
