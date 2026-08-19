"""Unified editable design representation for datasets and model outputs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    field_validator,
    model_validator,
)


ElementType = Literal[
    "text",
    "image",
    "rectangle",
    "ellipse",
    "svg",
    "group",
    "other",
]
AssetType = Literal["bitmap", "svg", "logo", "font", "other"]
DocumentUnit = Literal["px", "mm", "in", "pt"]
CanvasSourceType = Literal["ACTIVE_PAGE", "ARTWORK_REGION"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BoundingBox(StrictModel):
    """Absolute top-left bounding box in the document unit."""

    x: FiniteFloat = Field(ge=0)
    y: FiniteFloat = Field(ge=0)
    width: FiniteFloat = Field(gt=0)
    height: FiniteFloat = Field(gt=0)


class NormalizedBoundingBox(StrictModel):
    """Top-left bounding box normalized to the inclusive [0, 1] canvas."""

    x: FiniteFloat = Field(ge=0, le=1)
    y: FiniteFloat = Field(ge=0, le=1)
    width: FiniteFloat = Field(gt=0, le=1)
    height: FiniteFloat = Field(gt=0, le=1)

    @model_validator(mode="after")
    def validate_canvas_bounds(self) -> "NormalizedBoundingBox":
        tolerance = 1e-9
        if self.x + self.width > 1 + tolerance:
            raise ValueError("normalized bbox exceeds canvas width")
        if self.y + self.height > 1 + tolerance:
            raise ValueError("normalized bbox exceeds canvas height")
        return self


class ColorSpec(StrictModel):
    model: Literal["rgb", "rgba", "cmyk", "hex"]
    values: list[FiniteFloat | str] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_channels(self) -> "ColorSpec":
        if self.model == "hex":
            if len(self.values) != 1 or not isinstance(self.values[0], str):
                raise ValueError("hex color requires one string value")
            value = self.values[0]
            if len(value) not in {4, 7, 9} or not value.startswith("#"):
                raise ValueError("hex color must use #RGB, #RRGGBB, or #RRGGBBAA")
            try:
                int(value[1:], 16)
            except ValueError as exc:
                raise ValueError("hex color contains invalid digits") from exc
            return self

        if any(isinstance(value, str) for value in self.values):
            raise ValueError(f"{self.model} color channels must be numeric")
        expected = {"rgb": 3, "rgba": 4, "cmyk": 4}[self.model]
        if len(self.values) != expected:
            raise ValueError(f"{self.model} color requires {expected} channels")
        numeric = [float(value) for value in self.values]
        maximum = 100 if self.model == "cmyk" else 255
        if any(value < 0 or value > maximum for value in numeric[:3]):
            raise ValueError(f"{self.model} color channel is outside range")
        if self.model == "cmyk" and (numeric[3] < 0 or numeric[3] > 100):
            raise ValueError("cmyk black channel is outside range")
        if self.model == "rgba" and (numeric[3] < 0 or numeric[3] > 1):
            raise ValueError("rgba alpha must be between 0 and 1")
        return self


class VisualSpec(StrictModel):
    fill: ColorSpec | None = None
    stroke: ColorSpec | None = None
    stroke_width: FiniteFloat | None = Field(default=None, ge=0)
    opacity: FiniteFloat = Field(default=1, ge=0, le=1)


class TextSpec(StrictModel):
    content: str
    font_family: str | None = Field(default=None, min_length=1, max_length=300)
    font_size: FiniteFloat | None = Field(default=None, gt=0)
    font_weight: int | str | None = None
    style: Literal["normal", "italic", "oblique"] | None = None
    alignment: Literal["left", "center", "right", "justify"] | None = None
    line_height: FiniteFloat | None = Field(default=None, gt=0)
    tracking: FiniteFloat | None = None

    @field_validator("font_weight")
    @classmethod
    def validate_font_weight(cls, value: int | str | None) -> int | str | None:
        if isinstance(value, int) and not 1 <= value <= 1000:
            raise ValueError("numeric font weight must be between 1 and 1000")
        if isinstance(value, str) and not value.strip():
            raise ValueError("font weight cannot be empty")
        return value


class AssetSpec(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=4096)
    type: AssetType
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceSpec(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    split: str = Field(min_length=1, max_length=100)
    license_class: str = Field(min_length=1, max_length=100)
    upstream_id: str = Field(min_length=1, max_length=500)
    commercial_allowed: bool


class SourceCanvasBounds(StrictModel):
    """Original Corel bottom-left bounds retained as extraction evidence."""

    left: FiniteFloat
    bottom: FiniteFloat
    right: FiniteFloat
    top: FiniteFloat

    @model_validator(mode="after")
    def validate_extent(self) -> "SourceCanvasBounds":
        if self.right <= self.left or self.top <= self.bottom:
            raise ValueError("source canvas bounds must have positive extent")
        return self


class SourceCanvasOrigin(StrictModel):
    x: FiniteFloat
    y: FiniteFloat


class CanvasSpec(StrictModel):
    width: FiniteFloat = Field(gt=0)
    height: FiniteFloat = Field(gt=0)
    unit: DocumentUnit = "px"
    background: VisualSpec | None = None
    source_type: CanvasSourceType = "ACTIVE_PAGE"
    source_page_bounds: SourceCanvasBounds | None = None
    artwork_region_bounds: SourceCanvasBounds | None = None
    normalization_origin: SourceCanvasOrigin | None = None

    @model_validator(mode="after")
    def validate_source_context(self) -> "CanvasSpec":
        if self.source_type == "ARTWORK_REGION":
            if self.source_page_bounds is None:
                raise ValueError("artwork-region canvas requires source page bounds")
            if self.artwork_region_bounds is None:
                raise ValueError("artwork-region canvas requires artwork region bounds")
            if self.normalization_origin is None:
                raise ValueError("artwork-region canvas requires normalization origin")
        return self


class DesignElement(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
    name: str = Field(min_length=1, max_length=300)
    type: ElementType
    bbox: BoundingBox
    bbox_norm: NormalizedBoundingBox
    rotation: FiniteFloat = 0
    z_index: int = 0
    layer: str = Field(default="default", min_length=1, max_length=300)
    parent_id: str | None = Field(default=None, min_length=1, max_length=200)
    text: TextSpec | None = None
    visual: VisualSpec = Field(default_factory=VisualSpec)
    asset_ref: str | None = Field(default=None, min_length=1, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_type_metadata(self) -> "DesignElement":
        if self.type == "text" and self.text is None:
            raise ValueError("text elements require text metadata")
        if self.type != "text" and self.text is not None:
            raise ValueError("text metadata is only valid for text elements")
        if self.type in {"image", "svg"} and self.asset_ref is None:
            raise ValueError(f"{self.type} elements require asset_ref")
        return self


class DesignDocument(StrictModel):
    schema_version: Literal["0.1"] = "0.1"
    sample_id: str = Field(min_length=1, max_length=500)
    source: SourceSpec
    canvas: CanvasSpec
    category: str = Field(min_length=1, max_length=200)
    elements: list[DesignElement] = Field(default_factory=list, max_length=10_000)
    assets: list[AssetSpec] = Field(default_factory=list, max_length=10_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_document_graph(self) -> "DesignDocument":
        element_ids = [element.id for element in self.elements]
        if len(element_ids) != len(set(element_ids)):
            raise ValueError("duplicate element IDs")

        asset_ids = [asset.id for asset in self.assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("duplicate asset IDs")
        known_assets = set(asset_ids)
        known_elements = set(element_ids)

        parents: dict[str, str] = {}
        for element in self.elements:
            if element.parent_id is not None:
                if element.parent_id not in known_elements:
                    raise ValueError(
                        f"element '{element.id}' references missing parent "
                        f"'{element.parent_id}'"
                    )
                if element.parent_id == element.id:
                    raise ValueError(f"element '{element.id}' cannot parent itself")
                parents[element.id] = element.parent_id
            if element.asset_ref and element.asset_ref not in known_assets:
                raise ValueError(
                    f"element '{element.id}' references missing asset "
                    f"'{element.asset_ref}'"
                )
            self._validate_element_bounds(element)

        for element_id in parents:
            visited: set[str] = set()
            current = element_id
            while current in parents:
                if current in visited:
                    raise ValueError(f"broken hierarchy cycle at '{element_id}'")
                visited.add(current)
                current = parents[current]
        return self

    def _validate_element_bounds(self, element: DesignElement) -> None:
        tolerance = 1e-6
        if element.bbox.x + element.bbox.width > self.canvas.width + tolerance:
            raise ValueError(f"element '{element.id}' exceeds canvas width")
        if element.bbox.y + element.bbox.height > self.canvas.height + tolerance:
            raise ValueError(f"element '{element.id}' exceeds canvas height")

        expected = normalize_bbox(element.bbox, self.canvas)
        actual = element.bbox_norm
        for key in ("x", "y", "width", "height"):
            if abs(getattr(expected, key) - getattr(actual, key)) > tolerance:
                raise ValueError(
                    f"element '{element.id}' absolute and normalized bbox disagree"
                )


def normalize_bbox(
    bbox: BoundingBox,
    canvas: CanvasSpec,
) -> NormalizedBoundingBox:
    return NormalizedBoundingBox(
        x=float(bbox.x) / float(canvas.width),
        y=float(bbox.y) / float(canvas.height),
        width=float(bbox.width) / float(canvas.width),
        height=float(bbox.height) / float(canvas.height),
    )
