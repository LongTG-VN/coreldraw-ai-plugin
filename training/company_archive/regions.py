"""Deterministic pasteboard design-region analysis for Corel inspections.

The analysis operates only on source geometry already captured by the read-only
inspector.  It never moves shapes, resizes pages, or chooses between multiple
plausible artwork clusters.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from training.company_archive.models import CdrInspectionV1, CdrObjectV1


RegionMethod = Literal["ACTIVE_PAGE", "ALL_ARTWORK", "SPATIAL_CLUSTER"]
RegionAnalysisStatus = Literal[
    "REGION_SELECTED",
    "REGION_SELECTION_REQUIRED",
    "EXTRACTION_BLOCKED",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegionBounds(StrictModel):
    """Axis-aligned bounds in the original Corel bottom-left coordinate space."""

    left: FiniteFloat
    bottom: FiniteFloat
    right: FiniteFloat
    top: FiniteFloat

    @model_validator(mode="after")
    def validate_extent(self) -> "RegionBounds":
        if self.right <= self.left or self.top <= self.bottom:
            raise ValueError("region bounds must have positive width and height")
        return self

    @property
    def width(self) -> float:
        return float(self.right - self.left)

    @property
    def height(self) -> float:
        return float(self.top - self.bottom)

    @property
    def area(self) -> float:
        return self.width * self.height

    def as_dict(self) -> dict[str, float]:
        return {
            "left": float(self.left),
            "bottom": float(self.bottom),
            "right": float(self.right),
            "top": float(self.top),
            "width": self.width,
            "height": self.height,
        }


class ObjectSpaceRecord(StrictModel):
    object_id: str
    parent_id: str | None = None
    layer: str
    page: int = Field(ge=1)
    object_type: str
    bbox: RegionBounds
    inside_page: bool
    intersects_page: bool
    outside_page: bool


class DesignRegion(StrictModel):
    region_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_:-]{0,99}$")
    method: RegionMethod
    bounds: RegionBounds
    content_bounds: RegionBounds
    padding: FiniteFloat = Field(default=0.0, ge=0)
    included_object_ids: list[str]
    excluded_object_ids: list[str]
    source_page: int = Field(default=1, ge=1)
    source_layers: list[str]
    selection_method: str
    confidence: FiniteFloat = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_object_partition(self) -> "DesignRegion":
        included = set(self.included_object_ids)
        excluded = set(self.excluded_object_ids)
        if len(included) != len(self.included_object_ids):
            raise ValueError("included object IDs must be unique")
        if len(excluded) != len(self.excluded_object_ids):
            raise ValueError("excluded object IDs must be unique")
        if included & excluded:
            raise ValueError("included and excluded object IDs must be disjoint")
        return self


class DesignRegionAnalysis(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    design_id: str
    source_page: int = Field(default=1, ge=1)
    page_bounds: RegionBounds
    objects: list[ObjectSpaceRecord]
    candidate_regions: list[DesignRegion]
    spatial_cluster_count: int = Field(ge=0)
    cluster_gap: FiniteFloat = Field(gt=0)
    status: RegionAnalysisStatus
    selected_region_id: str | None = None
    selection_method: str
    selection_confidence: FiniteFloat = Field(ge=0, le=1)
    reason: str

    @model_validator(mode="after")
    def validate_selection(self) -> "DesignRegionAnalysis":
        known = {region.region_id for region in self.candidate_regions}
        if self.status == "REGION_SELECTED":
            if not self.selected_region_id or self.selected_region_id not in known:
                raise ValueError("selected region must identify a candidate region")
        elif self.selected_region_id is not None:
            raise ValueError("unresolved analysis cannot contain a selected region")
        return self

    def selected_region(self) -> DesignRegion | None:
        if self.selected_region_id is None:
            return None
        return next(
            region
            for region in self.candidate_regions
            if region.region_id == self.selected_region_id
        )


def _raw_bounds(item: CdrObjectV1) -> RegionBounds:
    payload = item.metadata.get("source_raw_bbox")
    if not isinstance(payload, dict):
        raise ValueError(f"object '{item.object_id}' lacks source_raw_bbox evidence")
    left = float(payload["left"])
    bottom = float(payload["bottom"])
    width = float(payload["width"])
    height = float(payload["height"])
    values = (left, bottom, width, height)
    if not all(math.isfinite(value) for value in values) or width <= 0 or height <= 0:
        raise ValueError(f"object '{item.object_id}' has invalid source geometry")
    return RegionBounds(
        left=left,
        bottom=bottom,
        right=left + width,
        top=bottom + height,
    )


def _relation(bounds: RegionBounds, page: RegionBounds) -> tuple[bool, bool, bool]:
    tolerance = 1e-9
    inside = (
        bounds.left >= page.left - tolerance
        and bounds.bottom >= page.bottom - tolerance
        and bounds.right <= page.right + tolerance
        and bounds.top <= page.top + tolerance
    )
    intersects = not (
        bounds.right <= page.left + tolerance
        or bounds.left >= page.right - tolerance
        or bounds.top <= page.bottom + tolerance
        or bounds.bottom >= page.top - tolerance
    )
    # A partially intersecting object is both ``intersects_page`` and
    # ``outside_page`` because some source geometry is outside the page.
    return inside, intersects, not inside


def enumerate_object_space(inspection: CdrInspectionV1) -> list[ObjectSpaceRecord]:
    """Classify every inspected object without discarding off-page geometry."""

    page = RegionBounds(
        left=0.0,
        bottom=0.0,
        right=float(inspection.page_width),
        top=float(inspection.page_height),
    )
    records: list[ObjectSpaceRecord] = []
    for item in inspection.objects:
        bounds = _raw_bounds(item)
        inside, intersects, outside = _relation(bounds, page)
        records.append(
            ObjectSpaceRecord(
                object_id=item.object_id,
                parent_id=item.parent_id,
                layer=item.layer or "default",
                page=int(item.metadata.get("source_page") or 1),
                object_type=item.object_type,
                bbox=bounds,
                inside_page=inside,
                intersects_page=intersects,
                outside_page=outside,
            )
        )
    return records


def _union(bounds: list[RegionBounds]) -> RegionBounds:
    if not bounds:
        raise ValueError("cannot build a region from no bounds")
    return RegionBounds(
        left=min(item.left for item in bounds),
        bottom=min(item.bottom for item in bounds),
        right=max(item.right for item in bounds),
        top=max(item.top for item in bounds),
    )


def _padded(bounds: RegionBounds, padding: float) -> RegionBounds:
    return RegionBounds(
        left=float(bounds.left) - padding,
        bottom=float(bounds.bottom) - padding,
        right=float(bounds.right) + padding,
        top=float(bounds.top) + padding,
    )


def _axis_gap(a_min: float, a_max: float, b_min: float, b_max: float) -> float:
    return max(0.0, max(a_min, b_min) - min(a_max, b_max))


def _box_distance(a: RegionBounds, b: RegionBounds) -> float:
    dx = _axis_gap(float(a.left), float(a.right), float(b.left), float(b.right))
    dy = _axis_gap(float(a.bottom), float(a.top), float(b.bottom), float(b.top))
    return math.hypot(dx, dy)


def _descendant_ids(
    root_id: str,
    children_by_parent: dict[str, list[str]],
) -> list[str]:
    result: list[str] = []
    stack = list(reversed(children_by_parent.get(root_id, [])))
    while stack:
        object_id = stack.pop()
        result.append(object_id)
        stack.extend(reversed(children_by_parent.get(object_id, [])))
    return result


def spatial_clusters(
    inspection: CdrInspectionV1,
    *,
    gap: float | None = None,
) -> tuple[list[list[str]], float]:
    """Return deterministic root-object connected components and the gap used."""

    records = enumerate_object_space(inspection)
    by_id = {record.object_id: record for record in records}
    root_ids = sorted(record.object_id for record in records if record.parent_id is None)
    if not root_ids:
        root_ids = sorted(by_id)
    page_diagonal = math.hypot(inspection.page_width, inspection.page_height)
    cluster_gap = float(gap) if gap is not None else max(1.0, page_diagonal * 0.05)
    if not math.isfinite(cluster_gap) or cluster_gap <= 0:
        raise ValueError("cluster gap must be finite and positive")

    parent = {object_id: object_id for object_id in root_ids}

    def find(object_id: str) -> str:
        while parent[object_id] != object_id:
            parent[object_id] = parent[parent[object_id]]
            object_id = parent[object_id]
        return object_id

    def union(a: str, b: str) -> None:
        root_a = find(a)
        root_b = find(b)
        if root_a == root_b:
            return
        first, second = sorted((root_a, root_b))
        parent[second] = first

    for index, object_id in enumerate(root_ids):
        for other_id in root_ids[index + 1 :]:
            if _box_distance(by_id[object_id].bbox, by_id[other_id].bbox) <= cluster_gap:
                union(object_id, other_id)

    roots_by_cluster: dict[str, list[str]] = defaultdict(list)
    for object_id in root_ids:
        roots_by_cluster[find(object_id)].append(object_id)

    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for record in records:
        if record.parent_id:
            children_by_parent[record.parent_id].append(record.object_id)
    for values in children_by_parent.values():
        values.sort()

    clusters: list[list[str]] = []
    for cluster_roots in roots_by_cluster.values():
        members: list[str] = []
        for root_id in sorted(cluster_roots):
            members.append(root_id)
            members.extend(_descendant_ids(root_id, children_by_parent))
        clusters.append(sorted(set(members)))
    clusters.sort(key=lambda values: values[0])
    return clusters, cluster_gap


def analyze_design_regions(
    inspection: CdrInspectionV1,
    *,
    design_id: str,
    gap: float | None = None,
    padding_ratio: float = 0.02,
) -> DesignRegionAnalysis:
    """Construct page, artwork-union, and cluster regions with a strict gate."""

    if not 0 <= padding_ratio <= 0.25:
        raise ValueError("padding_ratio must be between 0 and 0.25")
    records = enumerate_object_space(inspection)
    page = RegionBounds(
        left=0.0,
        bottom=0.0,
        right=float(inspection.page_width),
        top=float(inspection.page_height),
    )
    all_ids = [record.object_id for record in records]
    all_id_set = set(all_ids)
    layers_by_id = {record.object_id: record.layer for record in records}
    bounds_by_id = {record.object_id: record.bbox for record in records}
    candidates: list[DesignRegion] = []

    page_ids = sorted(
        record.object_id for record in records if record.intersects_page
    )
    if page_ids:
        candidates.append(
            DesignRegion(
                region_id="active_page",
                method="ACTIVE_PAGE",
                bounds=page,
                content_bounds=_union([bounds_by_id[item] for item in page_ids]),
                padding=0,
                included_object_ids=page_ids,
                excluded_object_ids=sorted(all_id_set - set(page_ids)),
                source_layers=sorted({layers_by_id[item] for item in page_ids}),
                selection_method="exact_active_page_bounds",
                confidence=1.0,
            )
        )

    if not records:
        return DesignRegionAnalysis(
            design_id=design_id,
            page_bounds=page,
            objects=[],
            candidate_regions=candidates,
            spatial_cluster_count=0,
            cluster_gap=max(1.0, math.hypot(inspection.page_width, inspection.page_height) * 0.05),
            status="EXTRACTION_BLOCKED",
            selection_method="no_artwork",
            selection_confidence=0.0,
            reason="inspection contains no artwork objects",
        )

    all_bounds = _union([record.bbox for record in records])
    candidates.append(
        DesignRegion(
            region_id="all_artwork",
            method="ALL_ARTWORK",
            bounds=all_bounds,
            content_bounds=all_bounds,
            padding=0,
            included_object_ids=sorted(all_ids),
            excluded_object_ids=[],
            source_layers=sorted({record.layer for record in records}),
            selection_method="union_of_all_inspected_artwork",
            confidence=0.25,
        )
    )

    clusters, cluster_gap = spatial_clusters(inspection, gap=gap)
    cluster_regions: list[DesignRegion] = []
    for index, object_ids in enumerate(clusters, start=1):
        content = _union([bounds_by_id[object_id] for object_id in object_ids])
        padding = max(content.width, content.height) * padding_ratio
        cluster_regions.append(
            DesignRegion(
                region_id=f"cluster_{index:03d}",
                method="SPATIAL_CLUSTER",
                bounds=_padded(content, padding) if padding else content,
                content_bounds=content,
                padding=padding,
                included_object_ids=object_ids,
                excluded_object_ids=sorted(all_id_set - set(object_ids)),
                source_layers=sorted({layers_by_id[item] for item in object_ids}),
                selection_method="deterministic_bbox_connected_component",
                confidence=0.75 if len(clusters) == 1 else 0.5,
            )
        )
    candidates.extend(cluster_regions)

    if len(cluster_regions) == 1:
        selected = cluster_regions[0]
        return DesignRegionAnalysis(
            design_id=design_id,
            page_bounds=page,
            objects=records,
            candidate_regions=candidates,
            spatial_cluster_count=1,
            cluster_gap=cluster_gap,
            status="REGION_SELECTED",
            selected_region_id=selected.region_id,
            selection_method="single_spatial_cluster",
            selection_confidence=0.95,
            reason="all inspected top-level artwork belongs to one spatial cluster",
        )

    return DesignRegionAnalysis(
        design_id=design_id,
        page_bounds=page,
        objects=records,
        candidate_regions=candidates,
        spatial_cluster_count=len(cluster_regions),
        cluster_gap=cluster_gap,
        status="REGION_SELECTION_REQUIRED",
        selected_region_id=None,
        selection_method="human_region_selection_required",
        selection_confidence=0.0,
        reason=f"{len(cluster_regions)} spatially separated artwork clusters are plausible",
    )


__all__ = [
    "DesignRegion",
    "DesignRegionAnalysis",
    "ObjectSpaceRecord",
    "RegionBounds",
    "analyze_design_regions",
    "enumerate_object_space",
    "spatial_clusters",
]
