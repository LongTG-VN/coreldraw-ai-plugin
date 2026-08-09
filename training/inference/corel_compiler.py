"""Compile normalized design documents into the existing Corel transaction API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from training.schemas.design import ColorSpec, DesignDocument, DesignElement


class CorelCompileError(ValueError):
    """Raised when a structured element cannot be represented by Corel runtime."""


def _color_to_cmyk(color: ColorSpec | None) -> dict[str, int]:
    if color is None:
        return {"cyan": 0, "magenta": 0, "yellow": 0, "black": 0}
    if color.model == "cmyk":
        values = [int(round(float(value))) for value in color.values]
        return dict(zip(("cyan", "magenta", "yellow", "black"), values))

    if color.model == "hex":
        value = str(color.values[0]).lstrip("#")
        if len(value) in {3, 4}:
            value = "".join(character * 2 for character in value[:3])
        else:
            value = value[:6]
        rgb = tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))
    else:
        rgb = tuple(float(value) for value in color.values[:3])
    red, green, blue = (max(0, min(channel / 255, 1)) for channel in rgb)
    black = 1 - max(red, green, blue)
    if black >= 1 - 1e-9:
        c_value = m_value = y_value = 0.0
    else:
        denominator = 1 - black
        c_value = (1 - red - black) / denominator
        m_value = (1 - green - black) / denominator
        y_value = (1 - blue - black) / denominator
    return {
        "cyan": int(round(c_value * 100)),
        "magenta": int(round(m_value * 100)),
        "yellow": int(round(y_value * 100)),
        "black": int(round(black * 100)),
    }


def _corel_geometry(
    element: DesignElement,
    *,
    width_mm: float,
    height_mm: float,
) -> dict[str, float]:
    bbox = element.bbox_norm
    return {
        "x": float(bbox.x) * width_mm,
        "y": height_mm - float(bbox.y) * height_mm,
        "width": float(bbox.width) * width_mm,
        "height": float(bbox.height) * height_mm,
    }


def _asset_path(document: DesignDocument, asset_ref: str) -> str:
    asset = next((item for item in document.assets if item.id == asset_ref), None)
    if asset is None:
        raise CorelCompileError(f"missing asset '{asset_ref}'")
    source = Path(asset.source).expanduser()
    if "://" in asset.source or not source.is_file():
        raise CorelCompileError(
            f"asset '{asset_ref}' must resolve to an existing local file"
        )
    return str(source.resolve())


def compile_corel_operations(
    document: DesignDocument,
    *,
    width_mm: float | None = None,
    height_mm: float | None = None,
) -> list[dict[str, Any]]:
    if document.canvas.unit == "mm":
        target_width = float(document.canvas.width)
        target_height = float(document.canvas.height)
    else:
        if width_mm is None or height_mm is None:
            raise CorelCompileError(
                "non-mm designs require explicit width_mm and height_mm"
            )
        target_width = width_mm
        target_height = height_mm

    operations: list[dict[str, Any]] = [
        {"op": "page_resize", "width": target_width, "height": target_height}
    ]
    groups: list[DesignElement] = []
    scale = min(
        target_width / float(document.canvas.width),
        target_height / float(document.canvas.height),
    )
    for element in sorted(document.elements, key=lambda item: item.z_index):
        if element.type == "group":
            groups.append(element)
            continue
        geometry = _corel_geometry(
            element,
            width_mm=target_width,
            height_mm=target_height,
        )
        color = _color_to_cmyk(element.visual.fill)
        if element.type in {"rectangle", "ellipse"}:
            operation = {
                "op": f"create_{element.type}",
                "name": element.id,
                **geometry,
                "color": color,
            }
        elif element.type == "text":
            if element.text is None:
                raise CorelCompileError(f"text element '{element.id}' has no text")
            operation = {
                "op": "create_text",
                "name": element.id,
                "text": element.text.content,
                "font_name": element.text.font_family or "Arial",
                "font_size": element.text.font_size or 24,
                "x": geometry["x"],
                "y": geometry["y"],
                "color": color,
            }
        elif element.type in {"image", "svg"}:
            if element.asset_ref is None:
                raise CorelCompileError(f"element '{element.id}' has no asset")
            operation = {
                "op": "import_asset",
                "name": element.id,
                "file_path": _asset_path(document, element.asset_ref),
                **geometry,
            }
        else:
            raise CorelCompileError(
                f"element type '{element.type}' is not supported by Corel compiler"
            )
        operations.append(operation)

        if abs(float(element.rotation)) > 1e-9:
            operations.append(
                {
                    "op": "transform",
                    "shape_name": element.id,
                    "rotation": float(element.rotation),
                }
            )
        if element.visual.stroke is not None and element.visual.stroke_width:
            operations.append(
                {
                    "op": "outline",
                    "shape_name": element.id,
                    "width": float(element.visual.stroke_width) * scale,
                    "color": _color_to_cmyk(element.visual.stroke),
                }
            )

    for group in groups:
        children = [
            element.id
            for element in document.elements
            if element.parent_id == group.id
        ]
        if len(children) < 2:
            raise CorelCompileError(
                f"group '{group.id}' needs at least two direct children"
            )
        operations.append(
            {
                "op": "group",
                "shape_names": children,
                "group_name": group.id,
            }
        )

    if len(operations) > 200:
        raise CorelCompileError(
            f"compiled transaction has {len(operations)} operations; maximum is 200"
        )
    return operations
