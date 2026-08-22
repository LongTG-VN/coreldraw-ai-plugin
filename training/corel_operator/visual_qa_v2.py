"""Page-anchored, target-scoped visual integrity validation."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Literal

from PIL import Image, ImageChops, ImageStat
from pydantic import Field

from training.company_archive.models import CdrInspectionV1
from training.corel_operator.canonical_export import CanonicalExportEvidenceV1
from training.corel_operator.models import StrictModel


VisualQaV2Reason = Literal[
    "PAGE_GEOMETRY_CHANGED",
    "OBJECT_COUNT_CHANGED",
    "TARGET_MISSING",
    "NON_TARGET_STRUCTURAL_CHANGE",
    "CANONICAL_EXPORT_FAILED",
    "VISUAL_CHANGE_OUT_OF_SCOPE",
    "NO_VISIBLE_TARGET_CHANGE",
    "EXCESSIVE_TARGET_CHANGE",
    "PREVIEW_REGISTRATION_FAILED",
    "PREVIEW_DIMENSION_MISMATCH_UNRESOLVED",
]


class ExpectedChangeRegionV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    left_px: int = Field(ge=0)
    top_px: int = Field(ge=0)
    right_px: int = Field(ge=1)
    bottom_px: int = Field(ge=1)
    target_ids: list[str]
    padding_ratio: float = Field(ge=0, le=0.1)


class VisualQaV2Metrics(StrictModel):
    changed_pixel_ratio: float = Field(ge=0, le=1)
    inside_changed_pixel_ratio: float = Field(ge=0, le=1)
    outside_changed_pixel_ratio: float = Field(ge=0, le=1)
    outside_fraction_of_changed: float = Field(ge=0, le=1)
    mean_absolute_difference: float = Field(ge=0, le=255)
    largest_changed_component_ratio: float = Field(ge=0, le=1)


class VisualIntegrityQaV2Report(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    status: Literal["PASS", "NEEDS_REVIEW", "FAIL"]
    reasons: list[VisualQaV2Reason] = Field(default_factory=list)
    page_geometry_before: dict[str, float | str | int]
    page_geometry_after: dict[str, float | str | int]
    expected_dimensions: tuple[int, int]
    actual_before_dimensions: tuple[int, int]
    actual_after_dimensions: tuple[int, int]
    expected_change_region: ExpectedChangeRegionV1 | None = None
    metrics: VisualQaV2Metrics | None = None
    structural_errors: list[str] = Field(default_factory=list)
    thresholds: dict[str, float] = Field(default_factory=dict)
    aesthetic_judgment: Literal[False] = False


def _page_geometry(inspection: CdrInspectionV1) -> dict[str, float | str | int]:
    return {
        "width": inspection.page_width,
        "height": inspection.page_height,
        "unit": inspection.unit,
        "unit_code": inspection.corel_unit_code,
        "page_count": inspection.page_count,
    }


def expected_change_region(
    before: CdrInspectionV1,
    after: CdrInspectionV1,
    *,
    target_ids: list[str],
    width_px: int,
    height_px: int,
    padding_ratio: float = 0.01,
) -> ExpectedChangeRegionV1 | None:
    before_map = {item.object_id: item for item in before.objects}
    after_map = {item.object_id: item for item in after.objects}
    boxes: list[dict[str, float]] = []
    for object_id in target_ids:
        for collection in (before_map, after_map):
            item = collection.get(object_id)
            if item is not None:
                boxes.append(item.bbox_norm)
    if not boxes:
        return None
    padding_x = padding_ratio * width_px
    padding_y = padding_ratio * height_px
    left = max(0, int(min(box["x"] * width_px for box in boxes) - padding_x))
    top = max(0, int(min(box["y"] * height_px for box in boxes) - padding_y))
    right = min(
        width_px,
        int(max((box["x"] + box["width"]) * width_px for box in boxes) + padding_x + 0.9999),
    )
    bottom = min(
        height_px,
        int(max((box["y"] + box["height"]) * height_px for box in boxes) + padding_y + 0.9999),
    )
    if right <= left or bottom <= top:
        return None
    return ExpectedChangeRegionV1(
        left_px=left,
        top_px=top,
        right_px=right,
        bottom_px=bottom,
        target_ids=target_ids,
        padding_ratio=padding_ratio,
    )


def _largest_component_ratio(mask: Image.Image) -> float:
    width, height = mask.size
    scale = min(1.0, 512 / max(width, height))
    reduced = mask if scale == 1 else mask.resize(
        (max(1, round(width * scale)), max(1, round(height * scale))),
        Image.Resampling.NEAREST,
    )
    pixels = reduced.load()
    rw, rh = reduced.size
    visited: set[tuple[int, int]] = set()
    largest = 0
    for y in range(rh):
        for x in range(rw):
            if not pixels[x, y] or (x, y) in visited:
                continue
            queue = deque([(x, y)])
            visited.add((x, y))
            size = 0
            while queue:
                cx, cy = queue.popleft()
                size += 1
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if (
                        0 <= nx < rw
                        and 0 <= ny < rh
                        and (nx, ny) not in visited
                        and pixels[nx, ny]
                    ):
                        visited.add((nx, ny))
                        queue.append((nx, ny))
            largest = max(largest, size)
    return largest / (rw * rh)


def compare_visual_integrity_v2(
    before: CdrInspectionV1,
    after: CdrInspectionV1,
    before_export: CanonicalExportEvidenceV1,
    after_export: CanonicalExportEvidenceV1,
    *,
    target_ids: list[str],
    structural_errors: list[str] | None = None,
    pixel_threshold: int = 8,
    minimum_change_ratio: float = 0.000001,
    maximum_change_ratio: float = 0.45,
    maximum_outside_page_ratio: float = 0.0025,
    maximum_outside_fraction: float = 0.35,
    fail_outside_page_ratio: float = 0.05,
) -> VisualIntegrityQaV2Report:
    errors = list(structural_errors or [])
    reasons: list[VisualQaV2Reason] = []
    before_geometry = _page_geometry(before)
    after_geometry = _page_geometry(after)
    expected = (before_export.geometry.width_px, before_export.geometry.height_px)
    actual_before = (before_export.actual_width_px, before_export.actual_height_px)
    actual_after = (after_export.actual_width_px, after_export.actual_height_px)
    if before_geometry != after_geometry:
        reasons.append("PAGE_GEOMETRY_CHANGED")
    if before.object_count != after.object_count:
        reasons.append("OBJECT_COUNT_CHANGED")
    before_ids = {item.object_id for item in before.objects}
    after_ids = {item.object_id for item in after.objects}
    if any(object_id not in before_ids or object_id not in after_ids for object_id in target_ids):
        reasons.append("TARGET_MISSING")
    if errors:
        reasons.append("NON_TARGET_STRUCTURAL_CHANGE")
    if not before_export.dimensions_verified or not after_export.dimensions_verified:
        reasons.append("CANONICAL_EXPORT_FAILED")
    if actual_before != actual_after or actual_before != expected:
        reasons.append("PREVIEW_DIMENSION_MISMATCH_UNRESOLVED")
    region = expected_change_region(
        before,
        after,
        target_ids=target_ids,
        width_px=expected[0],
        height_px=expected[1],
    )
    if region is None:
        reasons.append("PREVIEW_REGISTRATION_FAILED")
    structural_failures = {
        "PAGE_GEOMETRY_CHANGED",
        "OBJECT_COUNT_CHANGED",
        "TARGET_MISSING",
        "NON_TARGET_STRUCTURAL_CHANGE",
        "CANONICAL_EXPORT_FAILED",
        "PREVIEW_DIMENSION_MISMATCH_UNRESOLVED",
        "PREVIEW_REGISTRATION_FAILED",
    }
    metrics: VisualQaV2Metrics | None = None
    if not any(reason in structural_failures for reason in reasons) and region is not None:
        with Image.open(before_export.path) as left_source, Image.open(after_export.path) as right_source:
            left = left_source.convert("RGB")
            right = right_source.convert("RGB")
            difference = ImageChops.difference(left, right)
            maximum_channel = difference.getchannel("R")
            maximum_channel = ImageChops.lighter(maximum_channel, difference.getchannel("G"))
            maximum_channel = ImageChops.lighter(maximum_channel, difference.getchannel("B"))
            mask = maximum_channel.point(lambda value: 255 if value >= pixel_threshold else 0, "1")
            total_pixels = left.width * left.height
            changed = sum(mask.histogram()[1:])
            inside_mask = Image.new("1", left.size, 0)
            inside_mask.paste(
                1,
                (region.left_px, region.top_px, region.right_px, region.bottom_px),
            )
            inside_changed = sum(ImageChops.logical_and(mask, inside_mask).histogram()[1:])
            outside_changed = changed - inside_changed
            total_ratio = changed / total_pixels
            inside_ratio = inside_changed / total_pixels
            outside_ratio = outside_changed / total_pixels
            outside_fraction = outside_changed / changed if changed else 0.0
            mean_difference = sum(ImageStat.Stat(difference).mean) / 3
            metrics = VisualQaV2Metrics(
                changed_pixel_ratio=total_ratio,
                inside_changed_pixel_ratio=inside_ratio,
                outside_changed_pixel_ratio=outside_ratio,
                outside_fraction_of_changed=outside_fraction,
                mean_absolute_difference=mean_difference,
                largest_changed_component_ratio=_largest_component_ratio(mask),
            )
            if total_ratio < minimum_change_ratio:
                reasons.append("NO_VISIBLE_TARGET_CHANGE")
            if total_ratio > maximum_change_ratio:
                reasons.append("EXCESSIVE_TARGET_CHANGE")
            if (
                outside_ratio > maximum_outside_page_ratio
                and outside_fraction > maximum_outside_fraction
            ):
                reasons.append("VISUAL_CHANGE_OUT_OF_SCOPE")

    status: Literal["PASS", "NEEDS_REVIEW", "FAIL"] = "PASS"
    if any(reason in structural_failures for reason in reasons):
        status = "FAIL"
    elif "VISUAL_CHANGE_OUT_OF_SCOPE" in reasons and metrics is not None:
        status = "FAIL" if metrics.outside_changed_pixel_ratio > fail_outside_page_ratio else "NEEDS_REVIEW"
    elif reasons:
        status = "NEEDS_REVIEW"
    return VisualIntegrityQaV2Report(
        status=status,
        reasons=reasons,
        page_geometry_before=before_geometry,
        page_geometry_after=after_geometry,
        expected_dimensions=expected,
        actual_before_dimensions=actual_before,
        actual_after_dimensions=actual_after,
        expected_change_region=region,
        metrics=metrics,
        structural_errors=errors,
        thresholds={
            "pixel_threshold": float(pixel_threshold),
            "minimum_change_ratio": minimum_change_ratio,
            "maximum_change_ratio": maximum_change_ratio,
            "maximum_outside_page_ratio": maximum_outside_page_ratio,
            "maximum_outside_fraction": maximum_outside_fraction,
            "fail_outside_page_ratio": fail_outside_page_ratio,
        },
    )


__all__ = [
    "ExpectedChangeRegionV1",
    "VisualIntegrityQaV2Report",
    "VisualQaV2Metrics",
    "compare_visual_integrity_v2",
    "expected_change_region",
]
