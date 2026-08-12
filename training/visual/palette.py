"""Deterministic prompt-aware palette resolution and contrast safeguards."""

from __future__ import annotations

from training.retrieval.models import StructuredBriefV1
from training.visual.models import PaletteRolesV1, VisualStyleProfileV1


NAMED_COLORS: dict[str, str] = {
    "cream": "#F5EBDD",
    "gold": "#C49A52",
    "red": "#B42332",
    "black": "#171717",
    "white": "#FFFFFF",
    "green": "#2F6B55",
    "blue": "#245B91",
    "purple": "#6847A8",
    "pink": "#D87898",
    "orange": "#E66A2C",
    "brown": "#604536",
    "silver": "#B8BDC4",
}


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def relative_luminance(hex_color: str) -> float:
    channels = []
    for value in _rgb(hex_color):
        normalized = value / 255
        channels.append(
            normalized / 12.92
            if normalized <= 0.04045
            else ((normalized + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted(
        (relative_luminance(first), relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def _safe_text(preferred: str, background: str, *, minimum: float = 4.5) -> str:
    if contrast_ratio(preferred, background) >= minimum:
        return preferred
    black = "#171717"
    white = "#FFFFFF"
    return max((black, white), key=lambda color: contrast_ratio(color, background))


def resolve_palette(
    profile: VisualStyleProfileV1,
    *,
    brief: StructuredBriefV1,
    reference_palette: list[str] | None = None,
) -> PaletteRolesV1:
    """Resolve a limited role palette: user colors, then profile, then RAG intent."""

    base = profile.palette_roles.model_dump()
    requested = [NAMED_COLORS[name] for name in brief.colors if name in NAMED_COLORS]
    reference = [
        NAMED_COLORS[name]
        for name in (reference_palette or [])
        if name in NAMED_COLORS
    ]
    influences = requested or reference
    if influences:
        base["primary"] = influences[0]
        base["cta_background"] = influences[0]
        if len(influences) >= 2:
            base["accent"] = influences[1]
            base["secondary"] = influences[1]
        elif requested:
            # Preserve a requested single color without replacing every role.
            base["accent"] = influences[0]
    base["headline"] = _safe_text(base["headline"], base["background"])
    base["body"] = _safe_text(base["body"], base["background"])
    base["muted"] = _safe_text(base["muted"], base["background"], minimum=3.0)
    base["cta_text"] = _safe_text(base["cta_text"], base["cta_background"])
    return PaletteRolesV1.model_validate(base)


__all__ = ["NAMED_COLORS", "contrast_ratio", "relative_luminance", "resolve_palette"]
