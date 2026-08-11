"""Lightweight deterministic preview renderer for structured smoke outputs."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from training.schemas.design import ColorSpec, DesignDocument
from training.typography.fitting import load_font, measure_text


def _rgb(color: ColorSpec | None, default: tuple[int, int, int]) -> tuple[int, int, int]:
    if color is None:
        return default
    if color.model in {"rgb", "rgba"}:
        return tuple(int(round(float(value))) for value in color.values[:3])
    if color.model == "hex":
        value = str(color.values[0]).lstrip("#")
        if len(value) in {3, 4}:
            value = "".join(character * 2 for character in value[:3])
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))
    cyan, magenta, yellow, black = (
        float(value) / 100 for value in color.values
    )
    return (
        int(round(255 * (1 - cyan) * (1 - black))),
        int(round(255 * (1 - magenta) * (1 - black))),
        int(round(255 * (1 - yellow) * (1 - black))),
    )


def render_preview(
    document: DesignDocument,
    output_path: Path,
    *,
    max_dimension: int = 1600,
) -> Path:
    width = float(document.canvas.width)
    height = float(document.canvas.height)
    scale = min(max_dimension / max(width, height), 1.0)
    pixel_width = max(1, int(round(width * scale)))
    pixel_height = max(1, int(round(height * scale)))
    image = Image.new("RGB", (pixel_width, pixel_height), "white")
    draw = ImageDraw.Draw(image)

    for element in sorted(document.elements, key=lambda item: item.z_index):
        if element.type == "group":
            continue
        bbox = element.bbox_norm
        left = int(round(float(bbox.x) * pixel_width))
        top = int(round(float(bbox.y) * pixel_height))
        right = int(round(float(bbox.x + bbox.width) * pixel_width))
        bottom = int(round(float(bbox.y + bbox.height) * pixel_height))
        fill = _rgb(element.visual.fill, (230, 230, 230))
        stroke = _rgb(element.visual.stroke, (80, 80, 80))
        stroke_width = max(1, int(round(float(element.visual.stroke_width or 0))))

        if element.type == "rectangle":
            draw.rectangle((left, top, right, bottom), fill=fill, outline=stroke, width=stroke_width)
            if element.metadata.get("editable_placeholder") or element.metadata.get("placeholder"):
                # Keep missing visual intent obvious in review artifacts without
                # introducing a fake logo/product asset into the document.
                draw.line((left, top, right, bottom), fill=stroke, width=max(1, stroke_width))
                draw.line((right, top, left, bottom), fill=stroke, width=max(1, stroke_width))
        elif element.type == "ellipse":
            draw.ellipse((left, top, right, bottom), fill=fill, outline=stroke, width=stroke_width)
        elif element.type == "text" and element.text is not None:
            font_size = int(round(float(element.text.font_size or 24) * scale))
            font = load_font(font_size, element.text.font_family)
            measured = measure_text(
                element.text.content,
                box_width=max(1, right - left),
                font_size=font_size,
                family=element.text.font_family,
                line_height=(
                    float(element.text.line_height) * scale
                    if element.text.line_height is not None
                    and float(element.text.line_height) > 3
                    else element.text.line_height
                ),
            )
            wrapped = "\n".join(measured.lines)
            draw.multiline_text(
                (left, top),
                wrapped,
                fill=fill,
                font=font,
                spacing=max(0, int(measured.line_height - font_size)),
                align=element.text.alignment or "left",
            )
        elif element.type in {"image", "svg", "other"}:
            draw.rectangle((left, top, right, bottom), fill=fill, outline=stroke, width=2)
            draw.line((left, top, right, bottom), fill=stroke, width=1)
            draw.line((right, top, left, bottom), fill=stroke, width=1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG", optimize=True)
    return output_path.resolve()
