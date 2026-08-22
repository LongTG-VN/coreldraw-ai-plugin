from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.corel_operator.canonical_export import (
    canonical_export_evidence,
    canonical_page_dimensions,
)
from training.corel_operator.visual_qa_v2 import (
    compare_visual_integrity_v2,
    expected_change_region,
)


def _object(
    object_id: str,
    *,
    x: float = 0.1,
    y: float = 0.1,
    width: float = 0.2,
    height: float = 0.1,
    parent_id: str | None = None,
) -> CdrObjectV1:
    return CdrObjectV1(
        object_id=object_id,
        corel_name=object_id,
        object_type="text",
        bbox={"x": x * 100, "y": y * 100, "width": width * 100, "height": height * 100},
        bbox_norm={"x": x, "y": y, "width": width, "height": height},
        text="fixture",
        parent_id=parent_id,
        metadata={"source_page": 1},
    )


def _inspection(
    objects: list[CdrObjectV1],
    *,
    width: float = 100,
    height: float = 100,
) -> CdrInspectionV1:
    return CdrInspectionV1(
        source_path="fixture.cdr",
        source_size_bytes=1,
        source_mtime_ns=1,
        corel_version="fixture",
        page_count=1,
        page_width=width,
        page_height=height,
        unit="mm",
        corel_unit_code=3,
        layer_count=1,
        object_count=len(objects),
        text_object_count=len(objects),
        bitmap_count=0,
        vector_count=0,
        group_count=0,
        objects=objects,
    )


def _exports(tmp_path: Path, before: Image.Image, after: Image.Image):
    before_path = tmp_path / "before.png"
    after_path = tmp_path / "after.png"
    before.save(before_path)
    after.save(after_path)
    geometry = canonical_page_dimensions(100, 100, unit="mm", dpi=25)
    assert before.size == after.size == (geometry.width_px, geometry.height_px)
    return (
        canonical_export_evidence(before_path, geometry),
        canonical_export_evidence(after_path, geometry),
    )


def test_canonical_dimensions_round_half_up_for_portrait_mm() -> None:
    geometry = canonical_page_dimensions(210, 297, unit="mm", dpi=200)
    assert (geometry.width_px, geometry.height_px) == (1654, 2339)


def test_canonical_dimensions_landscape_is_orientation_preserving() -> None:
    geometry = canonical_page_dimensions(297, 210, unit="mm", dpi=200)
    assert (geometry.width_px, geometry.height_px) == (2339, 1654)


def test_canonical_dimensions_respect_dimension_and_pixel_budget() -> None:
    geometry = canonical_page_dimensions(
        1000,
        1000,
        unit="mm",
        dpi=300,
        max_dimension=1000,
        max_pixels=500_000,
    )
    assert geometry.width_px * geometry.height_px <= 501_264
    assert geometry.width_px <= 1000


def test_canonical_dimensions_support_inches_and_pixels() -> None:
    assert canonical_page_dimensions(2, 1, unit="in", dpi=100).width_px == 200
    assert canonical_page_dimensions(200, 100, unit="px", dpi=300).width_px == 200


def test_expected_region_unions_before_and_after_target_boxes() -> None:
    before = _inspection([_object("target", x=0.1)])
    after = _inspection([_object("target", x=0.3)])
    region = expected_change_region(
        before,
        after,
        target_ids=["target"],
        width_px=100,
        height_px=100,
        padding_ratio=0,
    )
    assert region is not None
    assert (region.left_px, region.right_px) == (10, 50)


def test_target_only_visual_change_passes(tmp_path: Path) -> None:
    before_image = Image.new("RGB", (98, 98), "white")
    after_image = before_image.copy()
    ImageDraw.Draw(after_image).rectangle((12, 12, 25, 18), fill="black")
    exports = _exports(tmp_path, before_image, after_image)
    inspection = _inspection([_object("target")])
    report = compare_visual_integrity_v2(
        inspection,
        inspection,
        *exports,
        target_ids=["target"],
    )
    assert report.status == "PASS"
    assert report.metrics is not None


def test_outside_scope_visual_change_needs_review(tmp_path: Path) -> None:
    before_image = Image.new("RGB", (98, 98), "white")
    after_image = before_image.copy()
    ImageDraw.Draw(after_image).rectangle((70, 70, 85, 85), fill="black")
    exports = _exports(tmp_path, before_image, after_image)
    inspection = _inspection([_object("target")])
    report = compare_visual_integrity_v2(
        inspection,
        inspection,
        *exports,
        target_ids=["target"],
    )
    assert report.status == "NEEDS_REVIEW"
    assert "VISUAL_CHANGE_OUT_OF_SCOPE" in report.reasons


def test_no_visible_change_requires_review(tmp_path: Path) -> None:
    image = Image.new("RGB", (98, 98), "white")
    exports = _exports(tmp_path, image, image.copy())
    inspection = _inspection([_object("target")])
    report = compare_visual_integrity_v2(
        inspection,
        inspection,
        *exports,
        target_ids=["target"],
    )
    assert report.status == "NEEDS_REVIEW"
    assert report.reasons == ["NO_VISIBLE_TARGET_CHANGE"]


def test_page_geometry_change_fails_even_with_equal_rasters(tmp_path: Path) -> None:
    before_image = Image.new("RGB", (98, 98), "white")
    after_image = before_image.copy()
    ImageDraw.Draw(after_image).rectangle((12, 12, 20, 20), fill="black")
    exports = _exports(tmp_path, before_image, after_image)
    report = compare_visual_integrity_v2(
        _inspection([_object("target")]),
        _inspection([_object("target")], width=101),
        *exports,
        target_ids=["target"],
    )
    assert report.status == "FAIL"
    assert "PAGE_GEOMETRY_CHANGED" in report.reasons


def test_missing_target_fails(tmp_path: Path) -> None:
    image = Image.new("RGB", (98, 98), "white")
    exports = _exports(tmp_path, image, image.copy())
    report = compare_visual_integrity_v2(
        _inspection([_object("other")]),
        _inspection([_object("other")]),
        *exports,
        target_ids=["missing"],
    )
    assert report.status == "FAIL"
    assert "TARGET_MISSING" in report.reasons


def test_non_target_structural_change_fails(tmp_path: Path) -> None:
    image = Image.new("RGB", (98, 98), "white")
    exports = _exports(tmp_path, image, image.copy())
    inspection = _inspection([_object("target")])
    report = compare_visual_integrity_v2(
        inspection,
        inspection,
        *exports,
        target_ids=["target"],
        structural_errors=["object other changed outside policy: bbox"],
    )
    assert report.status == "FAIL"
    assert "NON_TARGET_STRUCTURAL_CHANGE" in report.reasons


def test_canonical_export_evidence_detects_unresolved_dimension_variance(
    tmp_path: Path,
) -> None:
    geometry = canonical_page_dimensions(100, 100, unit="mm", dpi=25)
    before_path = tmp_path / "before.png"
    after_path = tmp_path / "after.png"
    Image.new("RGB", (geometry.width_px, geometry.height_px), "white").save(before_path)
    Image.new("RGB", (90, 98), "white").save(after_path)
    before = canonical_export_evidence(before_path, geometry)
    after = canonical_export_evidence(after_path, geometry)
    inspection = _inspection([_object("target")])
    report = compare_visual_integrity_v2(
        inspection,
        inspection,
        before,
        after,
        target_ids=["target"],
    )
    assert report.status == "FAIL"
    assert "PREVIEW_DIMENSION_MISMATCH_UNRESOLVED" in report.reasons
