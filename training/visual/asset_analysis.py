"""Deterministic geometry and color statistics for local visual assets."""

from __future__ import annotations

import colorsys
import statistics
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, ImageStat

from training.visual.asset_contracts import AssetInputV1, validate_asset_input


ASSET_ANALYSIS_VERSION = "asset_statistics_v0.3.3"


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{channel:02X}" for channel in rgb)


def _usable_palette(colors: list[tuple[int, int, int]]) -> list[str]:
    result: list[str] = []
    for red, green, blue in colors:
        _, saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
        if value < .10 or value > .97 or saturation < .06:
            continue
        value_hex = _hex((red, green, blue))
        if value_hex not in result:
            result.append(value_hex)
    return result[:5]


def analyze_asset(asset: AssetInputV1, *, base_dir: Path) -> dict[str, Any]:
    path = validate_asset_input(asset, base_dir=base_dir)
    if asset.mime_type == "image/svg+xml":
        return {
            "analysis_version": ASSET_ANALYSIS_VERSION,
            "asset_id": asset.asset_id,
            "geometry_only": True,
            "semantic_analysis_used": False,
            "width_px": asset.width_px,
            "height_px": asset.height_px,
            "aspect_ratio": asset.aspect_ratio,
            "has_alpha": asset.has_alpha,
            "brightness": None,
            "contrast": None,
            "dominant_colors": list(asset.palette_hint),
            "palette_candidates": list(asset.palette_hint),
        }
    with Image.open(path) as source:
        rgb = ImageOps.exif_transpose(source).convert("RGB")
        rgb.thumbnail((128, 128), Image.Resampling.LANCZOS)
        pixels = list(rgb.getdata())
        luminance = [(.2126 * red + .7152 * green + .0722 * blue) / 255 for red, green, blue in pixels]
        quantized = rgb.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
        palette = quantized.getpalette() or []
        ranked = sorted(quantized.getcolors() or [], reverse=True)
        colors = [
            tuple(palette[index * 3 : index * 3 + 3])
            for _, index in ranked
            if len(palette[index * 3 : index * 3 + 3]) == 3
        ]
        stat = ImageStat.Stat(rgb)
    return {
        "analysis_version": ASSET_ANALYSIS_VERSION,
        "asset_id": asset.asset_id,
        "geometry_only": False,
        "semantic_analysis_used": False,
        "width_px": asset.width_px,
        "height_px": asset.height_px,
        "aspect_ratio": asset.aspect_ratio,
        "has_alpha": asset.has_alpha,
        "brightness": statistics.fmean(luminance),
        "contrast": statistics.pstdev(luminance),
        "channel_mean": [value / 255 for value in stat.mean],
        "dominant_colors": [_hex(color) for color in colors[:5]],
        "palette_candidates": _usable_palette(colors) or list(asset.palette_hint),
    }


def analyze_manifest_assets(
    assets: list[AssetInputV1],
    *,
    base_dir: Path,
) -> dict[str, dict[str, Any]]:
    return {asset.asset_id: analyze_asset(asset, base_dir=base_dir) for asset in assets}


__all__ = ["ASSET_ANALYSIS_VERSION", "analyze_asset", "analyze_manifest_assets"]
