"""Deterministic text measurement, wrapping, and hierarchy-aware fitting."""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass
from typing import Any, Iterable

from PIL import ImageFont

from training.schemas.design import (
    BoundingBox,
    DesignDocument,
    DesignElement,
    TextSpec,
    normalize_bbox,
)


_CTA_WORDS = (
    "đặt lịch",
    "mua ngay",
    "đăng ký",
    "inbox",
    "order",
    "khám phá",
    "liên hệ",
    "call",
    "book",
)
_PRICE_RE = re.compile(r"(?:\d[\d.,]*\s*(?:k|đ|vnd|usd|\$|€))", re.IGNORECASE)


@dataclass(frozen=True)
class MeasuredText:
    lines: tuple[str, ...]
    width: float
    height: float
    line_height: float


def load_font(size: float, family: str | None = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load the same deterministic fallback family used by the preview renderer."""

    pixel_size = max(1, int(round(size)))
    for candidate in (family, "arial.ttf", "DejaVuSans.ttf"):
        if not candidate:
            continue
        try:
            return ImageFont.truetype(candidate, size=pixel_size)
        except OSError:
            continue
    return ImageFont.load_default()


def resolved_line_height(font_size: float, line_height: float | None) -> float:
    """Treat small line-height values as CSS-like multipliers, else as absolute."""

    if line_height is None:
        return font_size * 1.15
    value = float(line_height)
    return font_size * value if value <= 3 else value


def _text_width(font: ImageFont.FreeTypeFont | ImageFont.ImageFont, text: str) -> float:
    left, _, right, _ = font.getbbox(text or " ")
    return float(max(0, right - left))


def _break_word(
    word: str,
    *,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: float,
) -> list[str]:
    chunks: list[str] = []
    current = ""
    for character in word:
        candidate = current + character
        if current and _text_width(font, candidate) > max_width:
            chunks.append(current)
            current = character
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [word]


def wrap_text(
    content: str,
    *,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: float,
) -> tuple[str, ...]:
    """Greedy word wrap using actual local glyph measurements."""

    max_width = max(float(max_width), 1.0)
    output: list[str] = []
    paragraphs = content.splitlines() or [content]
    for paragraph in paragraphs:
        words: list[str] = []
        for word in paragraph.split():
            if _text_width(font, word) <= max_width:
                words.append(word)
            else:
                words.extend(_break_word(word, font=font, max_width=max_width))
        if not words:
            output.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if _text_width(font, candidate) <= max_width:
                current = candidate
            else:
                output.append(current)
                current = word
        output.append(current)
    return tuple(output or [""])


def measure_text(
    content: str,
    *,
    box_width: float,
    font_size: float,
    family: str | None = None,
    line_height: float | None = None,
) -> MeasuredText:
    font = load_font(font_size, family)
    lines = wrap_text(content, font=font, max_width=box_width)
    resolved_height = resolved_line_height(font_size, line_height)
    return MeasuredText(
        lines=lines,
        width=max((_text_width(font, line) for line in lines), default=0.0),
        height=max(resolved_height, len(lines) * resolved_height),
        line_height=resolved_height,
    )


def infer_text_role(element: DesignElement, *, largest_font: float | None = None) -> str:
    """Infer a structural role without using copyrighted reference content."""

    metadata_role = str(
        element.metadata.get("role")
        or element.metadata.get("label_name")
        or element.name
        or ""
    ).casefold()
    content = element.text.content.casefold() if element.text else ""
    if "title" in metadata_role or "headline" in metadata_role:
        return "headline"
    if "subtitle" in metadata_role:
        return "subtitle"
    if "call" in metadata_role or "cta" in metadata_role:
        return "cta"
    if "menu" in metadata_role or "detail" in metadata_role:
        return "menu_item"
    if "price" in metadata_role or _PRICE_RE.search(content):
        return "price"
    if any(
        value in metadata_role
        for value in ("body", "paragraph", "subtle", "description", "support")
    ):
        return "body"
    if any(word in content for word in _CTA_WORDS):
        return "cta"
    if largest_font and element.text and float(element.text.font_size or 0) >= largest_font * 0.98:
        return "headline"
    return "body"


def _horizontal_intersection(first: DesignElement, second: DesignElement) -> bool:
    return not (
        float(first.bbox.x + first.bbox.width) <= float(second.bbox.x)
        or float(second.bbox.x + second.bbox.width) <= float(first.bbox.x)
    )


def _available_height(
    element: DesignElement,
    elements: Iterable[DesignElement],
    *,
    canvas_height: float,
    gap: float,
) -> float:
    bottom_limit = canvas_height
    for other in elements:
        if other.id == element.id or not _horizontal_intersection(element, other):
            continue
        other_top = float(other.bbox.y)
        if other_top > float(element.bbox.y):
            bottom_limit = min(bottom_limit, other_top - gap)
    return max(float(element.bbox.height), bottom_limit - float(element.bbox.y))


def _target_sizes(text_elements: list[DesignElement]) -> dict[str, float]:
    sizes = [float(item.text.font_size or 12) for item in text_elements if item.text]
    largest = max(sizes, default=12.0)
    roles = {item.id: infer_text_role(item, largest_font=largest) for item in text_elements}
    body_sizes = [
        float(item.text.font_size or 12)
        for item in text_elements
        if item.text and roles[item.id] in {"body", "menu_item", "subtitle"}
    ]
    base = statistics.median(body_sizes or sizes or [12.0])
    targets: dict[str, float] = {}
    for element in text_elements:
        assert element.text is not None
        current = float(element.text.font_size or base)
        role = roles[element.id]
        if role == "headline":
            targets[element.id] = max(current, base * 2.35)
        elif role == "subtitle":
            targets[element.id] = max(current, base * 1.25)
        elif role in {"cta", "price"}:
            targets[element.id] = max(current, base * 1.15)
        else:
            targets[element.id] = current
    return targets


def fit_design_typography(
    document: DesignDocument,
    *,
    minimum_font_ratio: float = 0.025,
    allow_expand: bool = True,
) -> tuple[DesignDocument, dict[str, Any]]:
    """Fit all text deterministically and return a validated transformed copy.

    Content is never silently truncated. Explicit line breaks are inserted so
    the existing Corel artistic-text operation receives the measured wrapping.
    """

    payload = document.model_dump()
    source_elements = [item for item in document.elements if item.type != "group"]
    text_elements = [item for item in source_elements if item.text is not None]
    targets = _target_sizes(text_elements)
    short_side = min(float(document.canvas.width), float(document.canvas.height))
    minimum_font_size = max(6.0, short_side * minimum_font_ratio)
    gap = max(1.0, short_side * 0.012)
    adjustments: list[dict[str, Any]] = []

    by_id = {item["id"]: item for item in payload["elements"]}
    largest = max(
        (float(item.text.font_size or 0) for item in text_elements if item.text),
        default=0.0,
    )
    for element in sorted(text_elements, key=lambda item: (float(item.bbox.y), item.z_index)):
        assert element.text is not None
        target_size = targets[element.id]
        original_size = float(element.text.font_size or target_size)
        available_height = (
            _available_height(
                element,
                source_elements,
                canvas_height=float(document.canvas.height),
                gap=gap,
            )
            if allow_expand
            else float(element.bbox.height)
        )
        size = target_size
        measured = measure_text(
            element.text.content,
            box_width=float(element.bbox.width),
            font_size=size,
            family=element.text.font_family,
            line_height=None,
        )
        while (
            measured.height > available_height + 1e-6
            or measured.width > float(element.bbox.width) + 1e-6
        ) and size > minimum_font_size:
            size = max(minimum_font_size, size - 0.5)
            measured = measure_text(
                element.text.content,
                box_width=float(element.bbox.width),
                font_size=size,
                family=element.text.font_family,
                line_height=None,
            )
        fitted = (
            measured.height <= available_height + 1e-6
            and measured.width <= float(element.bbox.width) + 1e-6
        )
        final_height = float(element.bbox.height)
        expanded = False
        if fitted and measured.height > final_height and allow_expand:
            final_height = min(measured.height, available_height)
            expanded = final_height > float(element.bbox.height) + 1e-6

        target = by_id[element.id]
        target["bbox"]["height"] = final_height
        target["bbox_norm"] = normalize_bbox(
            BoundingBox.model_validate(target["bbox"]),
            document.canvas,
        ).model_dump()
        target["text"]["content"] = "\n".join(measured.lines)
        target["text"]["font_size"] = size
        target["text"]["line_height"] = measured.line_height
        target["metadata"] = {
            **target.get("metadata", {}),
            "role": infer_text_role(element, largest_font=largest),
            "typography_fit": {
                "original_content": element.text.content,
                "inserted_line_breaks": len(measured.lines) > 1,
                "truncated": False,
                "fit": fitted,
            },
        }
        adjustments.append(
            {
                "element_id": element.id,
                "role": target["metadata"]["role"],
                "original_font_size": original_size,
                "target_font_size": target_size,
                "final_font_size": size,
                "line_count": len(measured.lines),
                "expanded_box": expanded,
                "fit": fitted,
                "truncated": False,
            }
        )

    payload["metadata"] = {
        **payload.get("metadata", {}),
        "typography_fitting": {
            "engine": "deterministic_typography_fit_v0.3",
            "minimum_font_size": minimum_font_size,
            "adjusted_count": sum(
                abs(item["original_font_size"] - item["final_font_size"]) > 1e-6
                or item["line_count"] > 1
                or item["expanded_box"]
                for item in adjustments
            ),
            "unresolved_overflow_count": sum(not item["fit"] for item in adjustments),
            "truncated_count": 0,
            "adjustments": adjustments,
        },
    }
    fitted_document = DesignDocument.model_validate(payload)
    return fitted_document, fitted_document.metadata["typography_fitting"]
