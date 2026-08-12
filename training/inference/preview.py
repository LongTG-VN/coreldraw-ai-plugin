"""Lightweight deterministic preview renderer for structured smoke outputs."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

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
    allow_upscale: bool = False,
) -> Path:
    width = float(document.canvas.width)
    height = float(document.canvas.height)
    requested_scale = max_dimension / max(width, height)
    scale = requested_scale if allow_upscale else min(requested_scale, 1.0)
    pixel_width = max(1, int(round(width * scale)))
    pixel_height = max(1, int(round(height * scale)))
    image = Image.new("RGB", (pixel_width, pixel_height), "white")
    draw = ImageDraw.Draw(image)

    assets = {asset.id: asset for asset in document.assets}

    for element in sorted(document.elements, key=lambda item: item.z_index):
        if element.type == "group":
            continue
        bbox = element.bbox_norm
        left = int(round(float(bbox.x) * pixel_width))
        top = int(round(float(bbox.y) * pixel_height))
        right = int(round(float(bbox.x + bbox.width) * pixel_width))
        bottom = int(round(float(bbox.y + bbox.height) * pixel_height))
        fill = _rgb(element.visual.fill, (230, 230, 230))
        stroke = (
            _rgb(element.visual.stroke, (80, 80, 80))
            if element.visual.stroke is not None
            else None
        )
        stroke_width = (
            max(1, int(round(float(element.visual.stroke_width or 0) * scale)))
            if stroke is not None
            else 0
        )

        if element.type == "rectangle":
            draw.rectangle((left, top, right, bottom), fill=fill, outline=stroke, width=stroke_width)
            is_placeholder = bool(
                element.metadata.get("editable_placeholder")
                or element.metadata.get("placeholder")
            )
            if is_placeholder and element.metadata.get("placeholder_presentation") == "soft_frame_v1":
                # A presentation-safe missing-asset frame: visibly a placeholder,
                # but deliberately quieter than the legacy full-frame debug X.
                placeholder_stroke = stroke or (110, 110, 110)
                diagonal = tuple(
                    int(round(channel * .65 + 255 * .35)) for channel in placeholder_stroke
                )
                inset_x = max(4, int((right - left) * .16))
                inset_y = max(4, int((bottom - top) * .18))
                icon_left = left + inset_x
                icon_top = top + inset_y
                icon_right = min(right - inset_x, icon_left + max(12, (right - left) // 4))
                icon_bottom = min(bottom - inset_y, icon_top + max(10, (bottom - top) // 6))
                draw.rounded_rectangle(
                    (icon_left, icon_top, icon_right, icon_bottom),
                    radius=max(2, stroke_width * 2),
                    outline=diagonal,
                    width=max(1, stroke_width),
                )
                draw.line(
                    (icon_left, icon_bottom, (icon_left + icon_right) // 2, icon_top, icon_right, icon_bottom),
                    fill=diagonal,
                    width=max(1, stroke_width),
                )
                draw.line(
                    (left + inset_x, bottom - inset_y, right - inset_x, top + inset_y),
                    fill=diagonal,
                    width=max(1, stroke_width // 2),
                )
            elif is_placeholder:
                # Keep missing visual intent obvious in review artifacts without
                # introducing a fake logo/product asset into the document.
                placeholder_stroke = stroke or (80, 80, 80)
                draw.line((left, top, right, bottom), fill=placeholder_stroke, width=max(1, stroke_width))
                draw.line((right, top, left, bottom), fill=placeholder_stroke, width=max(1, stroke_width))
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
        elif element.type in {"image", "svg"} and element.asset_ref in assets:
            asset = assets[element.asset_ref]
            source_path = Path(
                str(asset.metadata.get("preview_path") or asset.source)
            ).expanduser()
            if source_path.is_file():
                with Image.open(source_path) as source:
                    asset_image = ImageOps.exif_transpose(source).convert("RGBA")
                    fit = element.metadata.get("asset_fit", {})
                    crop = fit.get("crop_norm", {}) if isinstance(fit, dict) else {}
                    crop_box = (
                        int(round(float(crop.get("x", 0)) * asset_image.width)),
                        int(round(float(crop.get("y", 0)) * asset_image.height)),
                        int(round(float(crop.get("x", 0) + crop.get("width", 1)) * asset_image.width)),
                        int(round(float(crop.get("y", 0) + crop.get("height", 1)) * asset_image.height)),
                    )
                    asset_image = asset_image.crop(crop_box)
                    target_size = (max(1, right - left), max(1, bottom - top))
                    if fit.get("runtime_mode") == "cover":
                        rendered = ImageOps.fit(asset_image, target_size, method=Image.Resampling.LANCZOS)
                    else:
                        rendered = ImageOps.contain(asset_image, target_size, method=Image.Resampling.LANCZOS)
                    paste_x = left + (target_size[0] - rendered.width) // 2
                    paste_y = top + (target_size[1] - rendered.height) // 2
                    image.paste(rendered, (paste_x, paste_y), rendered)
            else:
                draw.rectangle((left, top, right, bottom), fill=fill, outline=stroke, width=stroke_width)
        elif element.type in {"image", "svg", "other"}:
            placeholder_stroke = stroke or (80, 80, 80)
            draw.rectangle((left, top, right, bottom), fill=fill, outline=placeholder_stroke, width=2)
            draw.line((left, top, right, bottom), fill=placeholder_stroke, width=1)
            draw.line((right, top, left, bottom), fill=placeholder_stroke, width=1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG", optimize=True)
    return output_path.resolve()
