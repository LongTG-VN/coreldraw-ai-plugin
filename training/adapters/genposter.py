"""GenPoster100K research adapter.

The upstream ``layers`` field is a dict of parallel columns. Bboxes use
``[x1, y1, x2, y2]`` pixel coordinates and are converted to the unified
top-left ``x/y/width/height`` contract.
"""

from __future__ import annotations

import math
import re
from typing import Any

from training.adapters.base import AdapterError
from training.schemas.design import (
    AssetSpec,
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


GENPOSTER_LABELS = (
    "Bodytext",
    "Calls to Action",
    "Date",
    "Detailed items",
    "Location",
    "Menu Items",
    "Name",
    "Others",
    "Phone number",
    "Social Media",
    "Subtitle",
    "Title",
    "Website",
)


def _column(layers: dict[str, Any], key: str) -> list[Any]:
    value = layers.get(key)
    return value if isinstance(value, list) else []


def _at(values: list[Any], index: int, default: Any = None) -> Any:
    return values[index] if index < len(values) else default


def _optional_finite_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _safe_identifier(value: Any, fallback: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._:-]+", "_", str(value or "").strip())
    normalized = normalized.strip("_.:-")
    return (normalized or fallback)[:120]


def _image_size(value: Any) -> tuple[float, float] | None:
    size = getattr(value, "size", None)
    if isinstance(size, (list, tuple)) and len(size) == 2:
        width, height = float(size[0]), float(size[1])
        if width > 0 and height > 0:
            return width, height
    return None


class GenPosterAdapter:
    """Normalize GenPoster rows without persisting decoded image objects."""

    def __init__(
        self,
        *,
        split: str = "train",
        label_names: tuple[str, ...] = GENPOSTER_LABELS,
    ) -> None:
        self.split = split
        self.label_names = label_names

    def convert(self, row: dict[str, Any], index: int) -> DesignDocument:
        layers = row.get("layers")
        if not isinstance(layers, dict):
            raise AdapterError(f"GenPoster row {index} has no layers mapping")

        upstream_id = str(row.get("id", index))
        canvas = self._canvas(layers, row, index)
        layer_count = max(
            (len(value) for value in layers.values() if isinstance(value, list)),
            default=0,
        )
        if layer_count == 0:
            raise AdapterError(f"GenPoster row {index} has no layer records")

        elements: list[DesignElement] = []
        assets: list[AssetSpec] = []
        normalization_warnings: list[dict[str, Any]] = []
        for layer_index in range(layer_count):
            converted = self._convert_layer(
                layers,
                layer_index,
                upstream_id=upstream_id,
                canvas=canvas,
            )
            if converted is None:
                normalization_warnings.append(
                    {
                        "layer_index": layer_index,
                        "reason": "zero_area_bbox",
                        "bbox": _at(_column(layers, "bbox"), layer_index),
                        "layer_name": _at(
                            _column(layers, "layer_name"), layer_index
                        ),
                    }
                )
                continue
            element, asset = converted
            elements.append(element)
            if asset is not None:
                assets.append(asset)
        if not elements:
            raise AdapterError(f"GenPoster row {index} has no valid positioned layers")

        return DesignDocument(
            sample_id=f"genposter100k:{upstream_id}",
            source=SourceSpec(
                name="genposter100k",
                split=self.split,
                license_class="research_only",
                upstream_id=upstream_id,
                commercial_allowed=False,
            ),
            canvas=canvas,
            category="poster",
            elements=elements,
            assets=assets,
            metadata={
                "dataset_id": "creative-graphic-design/GenPoster100K",
                "license": "CC-BY-NC-4.0",
                "psd_path": row.get("psd_path"),
                "background_image_relpath": row.get("background_image_relpath"),
                "region_count": len(row.get("regions") or []),
                "normalization_warnings": normalization_warnings,
            },
        )

    @staticmethod
    def _canvas(
        layers: dict[str, Any],
        row: dict[str, Any],
        row_index: int,
    ) -> CanvasSpec:
        psd_sizes = _column(layers, "psd_size")
        for value in psd_sizes:
            if isinstance(value, (list, tuple)) and len(value) == 2:
                width, height = float(value[0]), float(value[1])
                if width > 0 and height > 0:
                    return CanvasSpec(width=width, height=height, unit="px")
        for key in ("background_image", "merged_image"):
            size = _image_size(row.get(key))
            if size is not None:
                return CanvasSpec(width=size[0], height=size[1], unit="px")
        raise AdapterError(f"GenPoster row {row_index} has no valid canvas size")

    def _convert_layer(
        self,
        layers: dict[str, Any],
        layer_index: int,
        *,
        upstream_id: str,
        canvas: CanvasSpec,
    ) -> tuple[DesignElement, AssetSpec | None] | None:
        bbox_values = _at(_column(layers, "bbox"), layer_index)
        if not isinstance(bbox_values, (list, tuple)) or len(bbox_values) != 4:
            raise AdapterError(
                f"GenPoster {upstream_id} layer {layer_index} has invalid bbox"
            )
        x1, y1, x2, y2 = (float(value) for value in bbox_values)
        x1 = max(0.0, min(x1, float(canvas.width)))
        y1 = max(0.0, min(y1, float(canvas.height)))
        x2 = max(x1, min(x2, float(canvas.width)))
        y2 = max(y1, min(y2, float(canvas.height)))
        if x2 <= x1 or y2 <= y1:
            return None
        bbox = BoundingBox(x=x1, y=y1, width=x2 - x1, height=y2 - y1)

        raw_name = _at(_column(layers, "layer_name"), layer_index)
        element_id = _safe_identifier(raw_name, f"layer_{layer_index}")
        element_id = f"layer_{layer_index:04d}_{element_id}"
        text_content = str(_at(_column(layers, "text"), layer_index, "") or "")
        label_value = _at(_column(layers, "label"), layer_index)
        label_name = self._label_name(label_value)
        fill = self._fill_color(_at(_column(layers, "fill_color"), layer_index))
        stroke_width = _optional_finite_float(
            _at(_column(layers, "stroke_width"), layer_index)
        )
        rotation = _optional_finite_float(
            _at(_column(layers, "angle"), layer_index)
        ) or 0.0

        asset: AssetSpec | None = None
        asset_ref: str | None = None
        text: TextSpec | None = None
        element_type = "text" if text_content else "image"
        if text_content:
            text = TextSpec(
                content=text_content,
                font_family=self._optional_string(
                    _at(_column(layers, "font"), layer_index)
                ),
                font_size=_optional_finite_float(
                    _at(_column(layers, "font_size"), layer_index)
                ),
                tracking=_optional_finite_float(
                    _at(_column(layers, "tracking"), layer_index)
                ),
            )
        else:
            asset_ref = f"asset_{layer_index:04d}"
            relpath = self._optional_string(
                _at(_column(layers, "layer_image_relpath"), layer_index)
            )
            source = relpath or (
                f"dataset://genposter100k/{upstream_id}/layer/{layer_index}"
            )
            asset = AssetSpec(
                id=asset_ref,
                source=source,
                type="bitmap",
                metadata={"embedded_upstream_image": relpath is None},
            )

        element = DesignElement(
            id=element_id,
            name=str(raw_name or f"Layer {layer_index}"),
            type=element_type,
            bbox=bbox,
            bbox_norm=normalize_bbox(bbox, canvas),
            rotation=rotation,
            z_index=layer_index,
            layer="genposter",
            text=text,
            visual=VisualSpec(fill=fill, stroke_width=stroke_width),
            asset_ref=asset_ref,
            metadata={
                "upstream_label": label_value,
                "label_name": label_name,
                "justification": _at(
                    _column(layers, "justification"), layer_index
                ),
            },
        )
        return element, asset

    def _label_name(self, value: Any) -> str | None:
        try:
            index = int(value)
        except (TypeError, ValueError):
            return None
        if 0 <= index < len(self.label_names):
            return self.label_names[index]
        return None

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None

    @staticmethod
    def _fill_color(value: Any) -> ColorSpec | None:
        if not isinstance(value, (list, tuple)) or len(value) not in {3, 4}:
            return None
        try:
            channels = [float(channel) for channel in value]
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(channel) for channel in channels):
            return None
        if len(channels) == 3:
            if max(channels, default=0) <= 1:
                channels = [channel * 255 for channel in channels]
            return ColorSpec(model="rgb", values=channels)
        if max(channels[:3], default=0) <= 1:
            channels[:3] = [channel * 255 for channel in channels[:3]]
        if channels[3] > 1:
            channels[3] /= 255
        return ColorSpec(model="rgba", values=channels)
