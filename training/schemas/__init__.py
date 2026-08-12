"""Stable structured-design schemas shared by training and inference."""

from training.schemas.design import (
    AssetSpec,
    BoundingBox,
    CanvasSpec,
    ColorSpec,
    DesignDocument,
    DesignElement,
    NormalizedBoundingBox,
    SourceSpec,
    TextSpec,
    VisualSpec,
    normalize_bbox,
)

__all__ = [
    "AssetSpec",
    "BoundingBox",
    "CanvasSpec",
    "ColorSpec",
    "DesignDocument",
    "DesignElement",
    "NormalizedBoundingBox",
    "SourceSpec",
    "TextSpec",
    "VisualSpec",
    "normalize_bbox",
]
