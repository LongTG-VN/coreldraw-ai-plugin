"""Preserve editable asset intent when a real local asset is unavailable."""

from __future__ import annotations

from training.schemas.design import (
    BoundingBox,
    ColorSpec,
    DesignDocument,
    DesignElement,
    VisualSpec,
    normalize_bbox,
)
from training.visual.models import PaletteRolesV1, VisualStyleProfileV1


VISUAL_ASSET_ROLES = frozenset(
    {"hero", "product", "logo", "icon", "illustration", "background_image"}
)


def _color(value: str) -> ColorSpec:
    return ColorSpec(model="hex", values=[value])


def _unique_id(document: DesignDocument, preferred: str) -> str:
    identifiers = {element.id for element in document.elements}
    if preferred not in identifiers:
        return preferred
    suffix = 2
    while f"{preferred}_{suffix}" in identifiers:
        suffix += 1
    return f"{preferred}_{suffix}"


def _box(document: DesignDocument, values: tuple[float, float, float, float]) -> BoundingBox:
    x, y, width, height = values
    return BoundingBox(
        x=x * float(document.canvas.width),
        y=y * float(document.canvas.height),
        width=width * float(document.canvas.width),
        height=height * float(document.canvas.height),
    )


def _intersection_area(
    values: tuple[float, float, float, float],
    other: DesignElement,
) -> float:
    x, y, width, height = values
    box = other.bbox_norm
    return max(0.0, min(x + width, float(box.x + box.width)) - max(x, float(box.x))) * max(
        0.0, min(y + height, float(box.y + box.height)) - max(y, float(box.y))
    )


def _best_asset_box(document: DesignDocument, strategy: str) -> tuple[float, float, float, float]:
    aspect = float(document.canvas.width) / float(document.canvas.height)
    if strategy == "logo_frame":
        candidates = (
            (0.06, 0.18, 0.20, 0.28 if aspect < 1.5 else 0.60),
            (0.74, 0.18, 0.20, 0.28 if aspect < 1.5 else 0.60),
        )
    elif strategy == "left_frame":
        candidates = ((0.06, 0.24, 0.31, 0.50), (0.63, 0.24, 0.31, 0.50))
    else:
        height = 0.46 if strategy == "product_card" else 0.52
        candidates = ((0.63, 0.24, 0.31, height), (0.06, 0.24, 0.31, height))
    text = [element for element in document.elements if element.text is not None]
    return min(candidates, key=lambda candidate: sum(_intersection_area(candidate, item) for item in text))


def _make_room_for_asset(document: DesignDocument, placeholder: DesignElement) -> int:
    """Narrow only intersecting text columns; never move or delete copy."""

    changed = 0
    asset = placeholder.bbox_norm
    gap = 0.035
    asset_on_right = float(asset.x) >= 0.5
    for element in document.elements:
        if element.text is None or _intersection_area(
            (
                float(asset.x),
                float(asset.y),
                float(asset.width),
                float(asset.height),
            ),
            element,
        ) <= 1e-9:
            continue
        box = element.bbox_norm
        if asset_on_right and float(box.x) < float(asset.x):
            width = float(asset.x) - gap - float(box.x)
            if width < .28:
                continue
            absolute = BoundingBox(
                x=float(box.x) * float(document.canvas.width),
                y=float(box.y) * float(document.canvas.height),
                width=width * float(document.canvas.width),
                height=float(box.height) * float(document.canvas.height),
            )
        elif not asset_on_right and float(box.x + box.width) > float(asset.x + asset.width):
            x = float(asset.x + asset.width) + gap
            width = 1 - x - .05
            if width < .28:
                continue
            absolute = BoundingBox(
                x=x * float(document.canvas.width),
                y=float(box.y) * float(document.canvas.height),
                width=width * float(document.canvas.width),
                height=float(box.height) * float(document.canvas.height),
            )
        else:
            continue
        element.bbox = absolute
        element.bbox_norm = normalize_bbox(absolute, document.canvas)
        element.metadata["asset_avoidance_reflow"] = placeholder.id
        changed += 1
    return changed


def preserve_asset_intent(
    document: DesignDocument,
    *,
    profile: VisualStyleProfileV1,
    palette: PaletteRolesV1,
) -> tuple[DesignDocument, dict[str, int]]:
    output = document.model_copy(deep=True)
    preserved = 0
    visual_roles: set[str] = set()
    for element in output.elements:
        intent = element.metadata.get("asset_intent")
        role = ""
        if isinstance(intent, dict):
            role = str(intent.get("role") or intent.get("asset_role") or "").casefold()
        role = str(element.metadata.get("asset_role") or role).casefold()
        if role not in VISUAL_ASSET_ROLES:
            continue
        element.metadata = {
            **element.metadata,
            "asset_required": True,
            "asset_role": role,
            "placeholder": True,
            "source_provided": bool(element.asset_ref),
            "editable_placeholder": element.asset_ref is None,
        }
        if element.asset_ref is None:
            element.type = "rectangle"
            element.text = None
            element.visual = VisualSpec(
                fill=_color(palette.surface),
                stroke=_color(palette.secondary),
                stroke_width=max(0.5, min(float(output.canvas.width), float(output.canvas.height)) * 0.004),
                opacity=0.88,
            )
        visual_roles.add(role)
        preserved += 1

    created = 0
    strategy = profile.hero_strategy
    if strategy != "none" and not visual_roles:
        role = "logo" if strategy == "logo_frame" else (
            "product" if strategy == "product_card" else "hero"
        )
        absolute = _box(output, _best_asset_box(output, strategy))
        element = DesignElement(
            id=_unique_id(output, f"asset_placeholder_{role}"),
            name=f"{role.title()} Asset Placeholder",
            type="rectangle",
            bbox=absolute,
            bbox_norm=normalize_bbox(absolute, output.canvas),
            z_index=max((item.z_index for item in output.elements), default=0) + 1,
            layer="assets",
            visual=VisualSpec(
                fill=_color(palette.surface),
                stroke=_color(palette.secondary),
                stroke_width=max(0.5, min(float(output.canvas.width), float(output.canvas.height)) * 0.004),
                opacity=0.88,
            ),
            metadata={
                "role": role,
                "asset_required": True,
                "asset_role": role,
                "placeholder": True,
                "source_provided": False,
                "editable_placeholder": True,
                "created_by_visual_profile": profile.profile_id,
            },
        )
        output.elements.append(element)
        preserved += 1
        created = 1
    placeholders = [
        element
        for element in output.elements
        if element.metadata.get("asset_required")
        and element.metadata.get("editable_placeholder")
        and element.metadata.get("asset_role") != "background_image"
    ]
    reflowed = sum(_make_room_for_asset(output, element) for element in placeholders)
    return output, {"preserved": preserved, "created": created, "reflowed_text": reflowed}


__all__ = ["VISUAL_ASSET_ROLES", "preserve_asset_intent"]
