"""Local visual artifacts for human-auditable pasteboard region selection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont

from training.company_archive.regions import DesignRegionAnalysis


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    ):
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def label_region_preview(
    preview_path: Path,
    output_path: Path,
    *,
    design_id: str,
    region_id: str,
    max_width: int = 1800,
    max_height: int = 1400,
) -> Path:
    """Add an external caption below a region preview without covering artwork."""

    source = preview_path.resolve(strict=True)
    target = output_path.resolve(strict=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        artwork = opened.convert("RGB")
    artwork.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
    caption_height = 90
    canvas = Image.new("RGB", (artwork.width, artwork.height + caption_height), "white")
    canvas.paste(artwork, (0, 0))
    draw = ImageDraw.Draw(canvas)
    label = f"{design_id}  |  {region_id}"
    font = _font(30)
    text_box = draw.textbbox((0, 0), label, font=font)
    x = max(16, (canvas.width - (text_box[2] - text_box[0])) // 2)
    y = artwork.height + (caption_height - (text_box[3] - text_box[1])) // 2
    draw.text((x, y), label, fill="#111111", font=font)
    canvas.save(target, format="PNG", optimize=True)
    return target


def build_region_contact_sheet(
    labeled_previews: Iterable[Path],
    output_path: Path,
    *,
    columns: int = 2,
    cell_width: int = 1400,
    cell_height: int = 1050,
    gap: int = 30,
) -> Path:
    paths = [path.resolve(strict=True) for path in labeled_previews]
    if not paths:
        raise ValueError("contact sheet requires at least one region preview")
    if columns < 1:
        raise ValueError("contact sheet columns must be positive")
    rows = (len(paths) + columns - 1) // columns
    sheet = Image.new(
        "RGB",
        (
            columns * cell_width + (columns + 1) * gap,
            rows * cell_height + (rows + 1) * gap,
        ),
        "#e8e8e8",
    )
    for index, path in enumerate(paths):
        with Image.open(path) as opened:
            image = opened.convert("RGB")
        image.thumbnail((cell_width, cell_height), Image.Resampling.LANCZOS)
        column = index % columns
        row = index // columns
        x = gap + column * cell_width + (cell_width - image.width) // 2
        y = gap + row * cell_height + (cell_height - image.height) // 2
        sheet.paste(image, (x, y))
    target = output_path.resolve(strict=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, format="PNG", optimize=True)
    return target


def write_region_manifest(
    analysis: DesignRegionAnalysis,
    output_path: Path,
    *,
    preview_paths: dict[str, Path] | None = None,
    errors: dict[str, str] | None = None,
) -> Path:
    """Persist a local manifest; callers sanitize it before private publication."""

    payload: dict[str, Any] = analysis.model_dump(mode="json")
    payload["preview_paths"] = {
        region_id: str(path.resolve())
        for region_id, path in sorted((preview_paths or {}).items())
    }
    payload["preview_errors"] = dict(sorted((errors or {}).items()))
    target = output_path.resolve(strict=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


__all__ = [
    "build_region_contact_sheet",
    "label_region_preview",
    "write_region_manifest",
]
