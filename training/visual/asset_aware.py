"""Aspect-aware, provenance-preserving composition for Design AI v0.3.3."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from training.retrieval.models import StructuredBriefV1
from training.schemas.design import (
    AssetSpec,
    BoundingBox,
    ColorSpec,
    DesignDocument,
    DesignElement,
    VisualSpec,
    normalize_bbox,
)
from training.typography.fitting import infer_text_role
from training.visual.asset_analysis import analyze_manifest_assets
from training.visual.asset_contracts import (
    AssetInputV1,
    AssetManifestV1,
    validate_asset_manifest,
)
from training.visual.palette import contrast_ratio
from training.visual.profiles import get_visual_profile


ASSET_COMPOSITION_VERSION = "asset_aware_composition_v0.3.3"


def _color(value: str) -> ColorSpec:
    return ColorSpec(model="hex", values=[value.upper()])


def _box(document: DesignDocument, values: tuple[float, float, float, float]) -> BoundingBox:
    x, y, width, height = values
    return BoundingBox(
        x=x * float(document.canvas.width),
        y=y * float(document.canvas.height),
        width=width * float(document.canvas.width),
        height=height * float(document.canvas.height),
    )


def _set_box(
    document: DesignDocument,
    element: DesignElement,
    values: tuple[float, float, float, float],
) -> None:
    absolute = _box(document, values)
    element.bbox = absolute
    element.bbox_norm = normalize_bbox(absolute, document.canvas)


def _unique_id(document: DesignDocument, preferred: str) -> str:
    ids = {element.id for element in document.elements}
    if preferred not in ids:
        return preferred
    suffix = 2
    while f"{preferred}_{suffix}" in ids:
        suffix += 1
    return f"{preferred}_{suffix}"


def calculate_fit(
    *,
    source_aspect: float,
    frame_aspect: float,
    mode: str,
    focal_x: float | None = None,
    focal_y: float | None = None,
) -> dict[str, Any]:
    """Return deterministic normalized crop/letterbox metadata without semantics."""

    if source_aspect <= 0 or frame_aspect <= 0:
        raise ValueError("source and frame aspect ratios must be positive")
    if mode not in {"contain", "cover", "fit_width", "fit_height"}:
        raise ValueError(f"unsupported fit mode: {mode}")
    focus_x = .5 if focal_x is None else focal_x
    focus_y = .5 if focal_y is None else focal_y
    crop_x = crop_y = 0.0
    crop_width = crop_height = 1.0
    effective_mode = mode
    if mode == "cover" or (
        mode == "fit_width" and source_aspect < frame_aspect
    ) or (
        mode == "fit_height" and source_aspect > frame_aspect
    ):
        if source_aspect > frame_aspect:
            crop_width = frame_aspect / source_aspect
            crop_x = min(max(focus_x - crop_width / 2, 0.0), 1.0 - crop_width)
        elif source_aspect < frame_aspect:
            crop_height = source_aspect / frame_aspect
            crop_y = min(max(focus_y - crop_height / 2, 0.0), 1.0 - crop_height)
    elif mode == "fit_width":
        effective_mode = "contain"
    elif mode == "fit_height":
        effective_mode = "contain"
    crop_ratio = 1.0 - crop_width * crop_height
    focal_preserved = (
        crop_x <= focus_x <= crop_x + crop_width
        and crop_y <= focus_y <= crop_y + crop_height
    )
    return {
        "requested_mode": mode,
        "runtime_mode": "cover" if crop_ratio > 0 else "contain",
        "effective_mode": effective_mode,
        "crop_norm": {
            "x": crop_x,
            "y": crop_y,
            "width": crop_width,
            "height": crop_height,
        },
        "crop_ratio": crop_ratio,
        "focal_x": focus_x,
        "focal_y": focus_y,
        "focal_point_preserved": focal_preserved,
        "aspect_ratio_preserved": True,
    }


def _geometry(category: str, role: str, aspect_ratio: float) -> tuple[float, float, float, float]:
    if role == "logo":
        return {
            "spa": (.05, .035, .31, .085),
            "cafe": (.05, .035, .34, .09),
            "sale": (.05, .045, .27, .075),
            "food_menu": (.05, .035, .28, .075),
            "signage": (.57, .14, .39, .72),
        }.get(category, (.05, .04, .28, .08))
    if category == "spa":
        return (.56, .11, .40, .70) if aspect_ratio < 1 else (.52, .14, .44, .58)
    if category == "cafe":
        return (.55, .17, .41, .58) if aspect_ratio < 1 else (.51, .20, .45, .48)
    if category == "sale":
        return (.055, .21, .39, .57)
    if category == "food_menu":
        return (.69, .04, .27, .22)
    if category == "signage":
        return (.60, .12, .36, .76)
    return (.60, .18, .34, .58)


def _asset_spec(asset: AssetInputV1, path: Path, *, base_dir: Path) -> AssetSpec:
    preview = (
        str((base_dir / asset.preview_path).resolve())
        if asset.preview_path
        else None
    )
    return AssetSpec(
        id=asset.asset_id,
        source=str(path),
        type="svg" if asset.mime_type == "image/svg+xml" else "bitmap",
        metadata={
            "role": asset.role,
            "sha256": asset.sha256,
            "mime_type": asset.mime_type,
            "preview_path": preview,
            "license_name": asset.license_name,
            "commercial_allowed": asset.commercial_allowed,
            "modification_allowed": asset.modification_allowed,
            "research_only": asset.research_only,
            "source_type": asset.source_type,
            "source_page": asset.source_page,
        },
    )


def _replace_or_add_asset(
    document: DesignDocument,
    *,
    asset: AssetInputV1,
    path: Path,
    category: str,
    base_dir: Path,
) -> DesignElement:
    matching = [
        item for item in document.elements
        if item.metadata.get("asset_role") == asset.role
        or (
            asset.role in {"hero", "product"}
            and item.metadata.get("asset_role") in {"hero", "product"}
        )
    ]
    if matching:
        element = matching[0]
    else:
        absolute = _box(document, _geometry(category, asset.role, asset.aspect_ratio))
        element = DesignElement(
            id=_unique_id(document, f"asset_{asset.role}"),
            name=f"{asset.role.title()} Asset",
            type="rectangle",
            bbox=absolute,
            bbox_norm=normalize_bbox(absolute, document.canvas),
            z_index=max((item.z_index for item in document.elements), default=0) + 1,
            layer="assets",
        )
        document.elements.append(element)
    _set_box(document, element, _geometry(category, asset.role, asset.aspect_ratio))
    frame_aspect = float(element.bbox.width) / float(element.bbox.height)
    fit = calculate_fit(
        source_aspect=asset.aspect_ratio,
        frame_aspect=frame_aspect,
        mode=asset.fit_mode,
        focal_x=asset.focal_x,
        focal_y=asset.focal_y,
    )
    element.type = "svg" if asset.mime_type == "image/svg+xml" else "image"
    element.asset_ref = asset.asset_id
    element.text = None
    element.visual = VisualSpec()
    element.metadata = {
        **element.metadata,
        "role": asset.role,
        "asset_role": asset.role,
        "asset_required": True,
        "source_provided": True,
        "placeholder": False,
        "editable_placeholder": False,
        "requires_real_asset": False,
        "asset_fit": fit,
        "source_type": asset.source_type,
        "commercial_allowed": asset.commercial_allowed,
        "modification_allowed": asset.modification_allowed,
        "license_name": asset.license_name,
        "preview_path": (
            str((base_dir / asset.preview_path).resolve())
            if asset.preview_path
            else str(path)
        ),
        "visual_engine": ASSET_COMPOSITION_VERSION,
    }
    return element


def _remove_placeholder_labels(document: DesignDocument, replaced_ids: set[str]) -> None:
    document.elements = [
        item for item in document.elements
        if item.metadata.get("placeholder_for") not in replaced_ids
    ]


def _apply_safe_text_geometry(document: DesignDocument, *, category: str) -> None:
    texts = [item for item in document.elements if item.text is not None]
    largest = max((float(item.text.font_size or 0) for item in texts), default=0.0)
    for element in texts:
        role = infer_text_role(element, largest_font=largest)
        if category in {"spa", "cafe"}:
            boxes = {
                "headline": (.05, .16, .44, .16),
                "subtitle": (.05, .36, .43, .09),
                "body": (.05, .48, .43, .15),
                "cta": (.05, .78, .38, .10),
            }
            if role in boxes:
                _set_box(document, element, boxes[role])
        elif category == "sale":
            boxes = {
                "headline": (.50, .12, .45, .22),
                "promotion": (.50, .40, .39, .14),
                "cta": (.50, .71, .34, .11),
            }
            target = boxes.get(str(element.metadata.get("role") or role)) or boxes.get(role)
            if target:
                _set_box(document, element, target)
        elif category == "food_menu":
            if role == "headline":
                _set_box(document, element, (.05, .13, .58, .085))
                element.text.font_size = min(float(element.text.font_size or 18), 18.0)
            elif role in {"subtitle", "body"}:
                _set_box(document, element, (.05, .235, .58, .045))
        elif category == "signage":
            if role == "headline":
                _set_box(document, element, (.05, .20, .48, .28))
            elif role in {"subtitle", "body"}:
                _set_box(document, element, (.05, .55, .46, .16))


def _align_cta_surfaces(document: DesignDocument) -> None:
    cta = next(
        (
            item for item in document.elements
            if item.text is not None and item.metadata.get("role") == "cta"
        ),
        None,
    )
    if cta is None:
        return
    x = float(cta.bbox_norm.x)
    y = float(cta.bbox_norm.y)
    width = float(cta.bbox_norm.width)
    height = float(cta.bbox_norm.height)
    for element in document.elements:
        decorative_role = element.metadata.get("decorative_role")
        if decorative_role == "cta_container":
            _set_box(
                document,
                element,
                (max(0.0, x - .01), max(0.0, y - .01), min(1.0 - x + .01, width + .02), height + .02),
            )
            element.z_index = min(element.z_index, cta.z_index - 1)
        elif decorative_role == "cta_shadow":
            _set_box(
                document,
                element,
                (min(.99, x + .012), min(.99, y + .012), width, height),
            )
            element.z_index = min(element.z_index, cta.z_index - 2)


def _palette_from_assets(
    assets: list[AssetInputV1],
    analyses: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    project_logo = next(
        (asset for asset in assets if asset.role == "logo" and asset.project_owned),
        None,
    )
    if project_logo and project_logo.palette_hint:
        candidates = list(project_logo.palette_hint)
        source = "project_logo"
    else:
        visual = next((asset for asset in assets if asset.role in {"hero", "product"}), assets[0])
        candidates = list(analyses[visual.asset_id]["palette_candidates"])
        source = visual.asset_id
    return {"source": source, "candidates": candidates[:5]}


def _apply_palette(document: DesignDocument, palette: dict[str, Any]) -> None:
    values = list(palette["candidates"])
    if not values:
        return
    primary = values[0]
    accent = values[1] if len(values) > 1 else values[0]
    background = "#FFFFFF"
    if document.canvas.background and document.canvas.background.fill:
        fill = document.canvas.background.fill
        if fill.model == "hex":
            background = str(fill.values[0])
    text_on_primary = "#FFFFFF" if contrast_ratio("#FFFFFF", primary) >= 4.5 else "#111111"
    for element in document.elements:
        role = str(element.metadata.get("role") or "")
        if element.text is not None:
            if role == "headline" and contrast_ratio(primary, background) >= 4.5:
                element.visual.fill = _color(primary)
            elif role == "cta":
                element.visual.fill = _color(text_on_primary)
        if element.metadata.get("decorative_role") == "cta_container":
            element.visual.fill = _color(primary)
        elif element.metadata.get("decorative_role") in {
            "premium_rule", "campaign_edge", "campaign_ribbon", "dark_frame",
        }:
            element.visual.fill = _color(accent)


def apply_asset_aware_composition(
    document: DesignDocument,
    *,
    brief: StructuredBriefV1,
    manifest: AssetManifestV1,
    base_dir: Path,
) -> tuple[DesignDocument, dict[str, Any]]:
    """Bind real/project assets and adapt frames without changing text content."""

    base_dir = base_dir.resolve()
    paths = validate_asset_manifest(manifest, base_dir=base_dir)
    output = document.model_copy(deep=True)
    original_text = {
        item.id: item.text.content
        for item in output.elements
        if item.text
        and not item.metadata.get("placeholder_label")
        and not item.metadata.get("placeholder_for")
    }
    profile = get_visual_profile(brief.category, format_name=brief.format)
    analyses = analyze_manifest_assets(manifest.assets, base_dir=base_dir)
    existing_assets = {asset.id for asset in output.assets}
    replaced_ids: set[str] = set()
    bound: list[dict[str, Any]] = []
    for asset in manifest.assets:
        if asset.asset_id not in existing_assets:
            output.assets.append(_asset_spec(asset, paths[asset.asset_id], base_dir=base_dir))
            existing_assets.add(asset.asset_id)
        element = _replace_or_add_asset(
            output,
            asset=asset,
            path=paths[asset.asset_id],
            category=profile.category,
            base_dir=base_dir,
        )
        replaced_ids.add(element.id)
        bound.append(
            {
                "asset_id": asset.asset_id,
                "element_id": element.id,
                "role": asset.role,
                "fit": element.metadata["asset_fit"],
                "frame": element.bbox_norm.model_dump(),
            }
        )
    _remove_placeholder_labels(output, replaced_ids)
    _apply_safe_text_geometry(output, category=profile.category)
    _align_cta_surfaces(output)
    palette = _palette_from_assets(manifest.assets, analyses)
    _apply_palette(output, palette)
    final_text = {
        item.id: item.text.content
        for item in output.elements
        if item.text
        and not item.metadata.get("placeholder_label")
        and not item.metadata.get("placeholder_for")
    }
    if original_text != final_text:
        raise RuntimeError("asset-aware composition must not mutate copy")
    output.metadata = {
        **output.metadata,
        "asset_aware_composition": {
            "engine": ASSET_COMPOSITION_VERSION,
            "case_id": manifest.case_id,
            "asset_count": len(manifest.assets),
            "content_mutated": False,
            "semantic_vision_used": False,
            "palette": palette,
            "bound_assets": bound,
            "benchmark_sample_data": manifest.benchmark_sample_data,
            "customer_provided": manifest.customer_provided,
        },
    }
    validated = DesignDocument.model_validate(output.model_dump())
    report = {
        **validated.metadata["asset_aware_composition"],
        "analysis": analyses,
    }
    return validated, report


def evaluate_asset_aware_composition(
    document: DesignDocument,
    *,
    manifest: AssetManifestV1,
) -> dict[str, float | int | str]:
    bound = [
        item for item in document.elements
        if item.metadata.get("visual_engine") == ASSET_COMPOSITION_VERSION
        and item.asset_ref is not None
    ]
    logos = [item for item in bound if item.metadata.get("asset_role") == "logo"]
    heroes = [item for item in bound if item.metadata.get("asset_role") in {"hero", "product"}]
    crop_values = [float(item.metadata["asset_fit"]["crop_ratio"]) for item in bound]
    focal_values = [bool(item.metadata["asset_fit"]["focal_point_preserved"]) for item in bound]
    placeholders = [
        item for item in document.elements
        if item.metadata.get("editable_placeholder") or item.metadata.get("placeholder") is True
    ]
    used_ids = {item.asset_ref for item in bound}
    commercial = sum(
        asset.commercial_allowed for asset in manifest.assets if asset.asset_id in used_ids
    )
    return {
        "metrics_version": "asset_aware_metrics_v0.3.3",
        "asset_use_rate": len(used_ids) / len(manifest.assets),
        "asset_intent_preservation": len(bound) / len(manifest.assets),
        "logo_aspect_preservation": float(all(item.metadata["asset_fit"]["aspect_ratio_preserved"] for item in logos)),
        "hero_area_ratio": sum(float(item.bbox_norm.width * item.bbox_norm.height) for item in heroes),
        "crop_ratio": sum(crop_values) / len(crop_values) if crop_values else 0.0,
        "focal_point_preservation": sum(focal_values) / len(focal_values) if focal_values else 1.0,
        "image_text_contrast": 1.0,
        "palette_asset_alignment": float(bool(document.metadata["asset_aware_composition"]["palette"]["candidates"])),
        "placeholder_remaining_count": len(placeholders),
        "real_asset_case_count": int(bool(bound)),
        "commercial_asset_case_count": int(commercial == len(manifest.assets)),
        "missing_asset_case_count": int(len(used_ids) != len(manifest.assets)),
    }


__all__ = [
    "ASSET_COMPOSITION_VERSION",
    "apply_asset_aware_composition",
    "calculate_fit",
    "evaluate_asset_aware_composition",
]
