"""Deterministic visual-integrity checks; never an aesthetic judge."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from PIL import Image, ImageChops, ImageStat
from pydantic import Field

from training.corel_operator.models import StrictModel


class VisualQaReportV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["PASS", "NEEDS_REVIEW"]
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    changed_pixel_ratio: float = Field(ge=0.0, le=1.0)
    mean_absolute_difference: float = Field(ge=0.0, le=255.0)
    before_nonempty: bool
    after_nonempty: bool
    issues: list[str] = Field(default_factory=list)
    aesthetic_judgment: Literal[False] = False


def _approved_image(path: Path, workspace: Path) -> Path:
    candidate = path.expanduser().resolve(strict=True)
    root = workspace.expanduser().resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("visual QA path escaped the operator workspace") from exc
    if candidate.suffix.casefold() not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("visual QA supports PNG/JPEG only")
    return candidate


def compare_operator_previews(
    before_path: Path,
    after_path: Path,
    *,
    workspace: Path,
    minimum_change_ratio: float = 0.000001,
    maximum_change_ratio: float = 0.85,
) -> VisualQaReportV1:
    if not 0 <= minimum_change_ratio < maximum_change_ratio <= 1:
        raise ValueError("invalid visual QA change bounds")
    before_file = _approved_image(before_path, workspace)
    after_file = _approved_image(after_path, workspace)
    with Image.open(before_file) as source_before, Image.open(after_file) as source_after:
        before = source_before.convert("RGB")
        after = source_after.convert("RGB")
        if before.size != after.size:
            return VisualQaReportV1(
                status="NEEDS_REVIEW",
                width=max(before.width, after.width),
                height=max(before.height, after.height),
                changed_pixel_ratio=1.0,
                mean_absolute_difference=255.0,
                before_nonempty=before.width > 0 and before.height > 0,
                after_nonempty=after.width > 0 and after.height > 0,
                issues=["PREVIEW_DIMENSION_CHANGED"],
            )
        difference = ImageChops.difference(before, after)
        mask = difference.convert("L").point(lambda value: 255 if value else 0)
        changed_pixels = int(sum(mask.histogram()[1:]))
        pixel_count = before.width * before.height
        ratio = changed_pixels / pixel_count
        mean_difference = sum(ImageStat.Stat(difference).mean) / 3
        issues: list[str] = []
        if ratio < minimum_change_ratio:
            issues.append("NO_VISIBLE_CHANGE")
        if ratio > maximum_change_ratio:
            issues.append("EXCESSIVE_FRAME_CHANGE")
        return VisualQaReportV1(
            status="NEEDS_REVIEW" if issues else "PASS",
            width=before.width,
            height=before.height,
            changed_pixel_ratio=ratio,
            mean_absolute_difference=mean_difference,
            before_nonempty=before.width > 0 and before.height > 0,
            after_nonempty=after.width > 0 and after.height > 0,
            issues=issues,
        )


__all__ = ["VisualQaReportV1", "compare_operator_previews"]
