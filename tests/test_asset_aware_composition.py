from __future__ import annotations

import copy
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from training.inference.corel_compiler import compile_corel_operations
from training.inference.preview import render_preview
from training.retrieval import analyze_brief
from training.schemas.design import (
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
from training.tools.source_v033_assets import CASE_CONTENT
from training.typography.fitting import fit_design_typography
from training.visual.asset_analysis import analyze_asset
from training.visual.asset_aware import (
    apply_asset_aware_composition,
    calculate_fit,
    evaluate_asset_aware_composition,
)
from training.visual.asset_contracts import (
    AssetContractError,
    AssetInputV1,
    AssetManifestV1,
    inspect_asset_file,
    sha256_file,
    validate_asset_input,
)
from training.visual.palette import contrast_ratio


def _text(
    canvas: CanvasSpec,
    element_id: str,
    role: str,
    content: str,
    values: tuple[float, float, float, float],
) -> DesignElement:
    x, y, width, height = values
    bbox = BoundingBox(
        x=x * float(canvas.width),
        y=y * float(canvas.height),
        width=width * float(canvas.width),
        height=height * float(canvas.height),
    )
    return DesignElement(
        id=element_id,
        name=role,
        type="text",
        bbox=bbox,
        bbox_norm=normalize_bbox(bbox, canvas),
        z_index=10,
        layer="content",
        text=TextSpec(content=content, font_family="Arial", font_size=14),
        visual=VisualSpec(fill=ColorSpec(model="hex", values=["#222222"])),
        metadata={"role": role},
    )


def _document() -> DesignDocument:
    canvas = CanvasSpec(
        width=210,
        height=297,
        unit="mm",
        background=VisualSpec(fill=ColorSpec(model="hex", values=["#F7F0E6"])),
    )
    hero_bbox = BoundingBox(x=126, y=65, width=72, height=170)
    logo_bbox = BoundingBox(x=10.5, y=10, width=65, height=25)
    return DesignDocument(
        sample_id="asset-aware:test",
        source=SourceSpec(
            name="synthetic_owned",
            split="test",
            license_class="production_safe",
            upstream_id="asset-aware:test",
            commercial_allowed=True,
        ),
        canvas=canvas,
        category="spa",
        elements=[
            _text(canvas, "headline", "headline", "CHĂM SÓC DA", (.05, .17, .43, .15)),
            _text(canvas, "body", "body", "Không gian thư giãn", (.05, .42, .43, .13)),
            _text(canvas, "cta", "cta", "ĐẶT LỊCH", (.05, .79, .34, .09)),
            DesignElement(
                id="hero_placeholder",
                name="Hero placeholder",
                type="rectangle",
                bbox=hero_bbox,
                bbox_norm=normalize_bbox(hero_bbox, canvas),
                z_index=6,
                layer="assets",
                metadata={
                    "asset_role": "hero",
                    "placeholder": True,
                    "editable_placeholder": True,
                },
            ),
            DesignElement(
                id="logo_placeholder",
                name="Logo placeholder",
                type="rectangle",
                bbox=logo_bbox,
                bbox_norm=normalize_bbox(logo_bbox, canvas),
                z_index=7,
                layer="assets",
                metadata={
                    "asset_role": "logo",
                    "placeholder": True,
                    "editable_placeholder": True,
                },
            ),
        ],
    )


def _asset(
    path: Path,
    *,
    asset_id: str,
    role: str,
    fit_mode: str,
    preview_path: str | None = None,
    palette: list[str] | None = None,
) -> AssetInputV1:
    mime, width, height, alpha = inspect_asset_file(path)
    return AssetInputV1(
        asset_id=asset_id,
        role=role,
        path=path.name,
        preview_path=preview_path,
        mime_type=mime,
        sha256=sha256_file(path),
        width_px=width,
        height_px=height,
        aspect_ratio=width / height,
        has_alpha=alpha,
        source_type="project_owned",
        license_name="Project-owned fixture",
        commercial_allowed=True,
        modification_allowed=True,
        research_only=False,
        project_owned=True,
        fit_mode=fit_mode,
        focal_x=.7 if role == "hero" else None,
        focal_y=.5 if role == "hero" else None,
        palette_hint=palette or [],
    )


def _manifest(tmp_path: Path) -> AssetManifestV1:
    hero_path = tmp_path / "hero.png"
    Image.new("RGB", (800, 400), "#3E7254").save(hero_path)
    logo_path = tmp_path / "logo.svg"
    logo_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="100">'
        '<rect width="400" height="100" fill="#3D2B24"/></svg>',
        encoding="utf-8",
    )
    logo_preview = tmp_path / "logo.png"
    Image.new("RGBA", (400, 100), "#3D2B24").save(logo_preview)
    return AssetManifestV1(
        case_id="spa",
        benchmark_sample_data=False,
        assets=[
            _asset(hero_path, asset_id="hero_01", role="hero", fit_mode="cover"),
            _asset(
                logo_path,
                asset_id="logo_01",
                role="logo",
                fit_mode="contain",
                preview_path=logo_preview.name,
                palette=["#3D2B24", "#C49A52"],
            ),
        ],
    )


def test_manifest_validates_file_hash_dimensions_and_provenance(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    paths = {
        asset.asset_id: validate_asset_input(asset, base_dir=tmp_path)
        for asset in manifest.assets
    }
    assert paths["hero_01"].is_file()
    assert all(asset.commercial_allowed for asset in manifest.assets)
    assert all(asset.modification_allowed for asset in manifest.assets)

    bad = manifest.assets[0].model_copy(update={"sha256": "0" * 64})
    with pytest.raises(AssetContractError, match="SHA-256"):
        validate_asset_input(bad, base_dir=tmp_path)


def test_manifest_rejects_missing_unsupported_and_bad_aspect(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    missing = manifest.assets[0].model_copy(update={"path": "missing.png"})
    with pytest.raises(AssetContractError, match="does not exist"):
        validate_asset_input(missing, base_dir=tmp_path)

    bad_file = tmp_path / "asset.gif"
    bad_file.write_bytes(b"GIF89a")
    with pytest.raises(AssetContractError, match="invalid image|unsupported"):
        inspect_asset_file(bad_file)

    payload = manifest.assets[0].model_dump()
    payload["aspect_ratio"] = 9.0
    with pytest.raises(ValidationError, match="aspect_ratio"):
        AssetInputV1.model_validate(payload)


def test_raster_dimensions_follow_exif_orientation(tmp_path: Path) -> None:
    path = tmp_path / "portrait.jpg"
    image = Image.new("RGB", (40, 20), "#446655")
    exif = image.getexif()
    exif[274] = 6
    image.save(path, format="JPEG", exif=exif)

    mime, width, height, has_alpha = inspect_asset_file(path)

    assert mime == "image/jpeg"
    assert (width, height) == (20, 40)
    assert has_alpha is False


def test_logo_requires_containment() -> None:
    with pytest.raises(ValidationError, match="logos must use contain"):
        AssetInputV1(
            asset_id="logo",
            role="logo",
            path="logo.svg",
            mime_type="image/svg+xml",
            sha256="0" * 64,
            width_px=400,
            height_px=100,
            aspect_ratio=4,
            has_alpha=True,
            source_type="project_owned",
            license_name="owned",
            commercial_allowed=True,
            modification_allowed=True,
            research_only=False,
            project_owned=True,
            fit_mode="cover",
        )


def test_cover_contain_width_height_and_focal_fit_are_deterministic() -> None:
    cover = calculate_fit(
        source_aspect=2,
        frame_aspect=1,
        mode="cover",
        focal_x=.8,
        focal_y=.5,
    )
    assert cover["crop_norm"] == {"x": .5, "y": 0, "width": .5, "height": 1}
    assert cover["crop_ratio"] == .5
    assert cover["focal_point_preserved"] is True
    assert calculate_fit(source_aspect=2, frame_aspect=1, mode="contain")["crop_ratio"] == 0
    assert calculate_fit(source_aspect=.5, frame_aspect=1, mode="fit_width")["runtime_mode"] == "cover"
    assert calculate_fit(source_aspect=2, frame_aspect=1, mode="fit_height")["runtime_mode"] == "cover"


def test_analysis_palette_is_deterministic_without_semantic_claims(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    first = analyze_asset(manifest.assets[0], base_dir=tmp_path)
    second = analyze_asset(manifest.assets[0], base_dir=tmp_path)

    assert first == second
    assert first["semantic_analysis_used"] is False
    assert first["brightness"] is not None
    assert first["palette_candidates"]


def test_asset_composition_binds_assets_preserves_copy_and_compiles(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    document = _document()
    original_copy = [item.text.content for item in document.elements if item.text]
    brief = analyze_brief("Poster spa cao cấp có ảnh và logo", width=210, height=297)
    first, report = apply_asset_aware_composition(
        document,
        brief=brief,
        manifest=manifest,
        base_dir=tmp_path,
    )
    second, _ = apply_asset_aware_composition(
        copy.deepcopy(document),
        brief=brief,
        manifest=manifest,
        base_dir=tmp_path,
    )
    fitted, typography = fit_design_typography(first, allow_expand=False)
    operations = compile_corel_operations(fitted)
    metrics = evaluate_asset_aware_composition(fitted, manifest=manifest)

    assert first == second
    assert [item.text.content for item in first.elements if item.text] == original_copy
    assert report["semantic_vision_used"] is False
    assert metrics["asset_use_rate"] == 1
    assert metrics["logo_aspect_preservation"] == 1
    assert metrics["placeholder_remaining_count"] == 0
    assert typography["truncated_count"] == 0
    assert sum(operation["op"] == "import_asset" for operation in operations) == 2
    assert sum(operation["op"] == "fit_to_frame" for operation in operations) == 2
    assert any(operation.get("powerclip") is True for operation in operations)


def test_asset_preview_renders_real_pixels_and_text_contrast_is_safe(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    document, _ = apply_asset_aware_composition(
        _document(),
        brief=analyze_brief("Poster spa cao cấp có ảnh", width=210, height=297),
        manifest=manifest,
        base_dir=tmp_path,
    )
    preview = render_preview(document, tmp_path / "preview.png", max_dimension=800, allow_upscale=True)
    with Image.open(preview) as image:
        assert image.getbbox() is not None
    headline = next(item for item in document.elements if item.metadata.get("role") == "headline")
    color = str(headline.visual.fill.values[0])
    assert contrast_ratio(color, "#F7F0E6") >= 4.5


def test_benchmark_sale_and_menu_data_are_explicitly_not_customer_data() -> None:
    assert CASE_CONTENT["sale"]["benchmark_sample_data"] is True
    assert CASE_CONTENT["sale"]["customer_provided"] is False
    assert CASE_CONTENT["sale"]["offer"] == "GIẢM 30%"
    assert CASE_CONTENT["menu"]["benchmark_sample_data"] is True
    assert CASE_CONTENT["menu"]["customer_provided"] is False
    assert [item["price"] for item in CASE_CONTENT["menu"]["items"]] == [
        "45K", "55K", "49K", "50K", "52K"
    ]
