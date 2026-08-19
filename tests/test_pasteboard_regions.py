from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from training.company_archive.extractor import inspection_to_design_document
from training.company_archive.inspector import CompanyCdrInspector
from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.company_archive.region_artifacts import (
    build_region_contact_sheet,
    label_region_preview,
)
from training.company_archive.regions import (
    analyze_design_regions,
    enumerate_object_space,
)


SOURCE_SHA = "b" * 64


def _object(
    index: int,
    *,
    left: float,
    bottom: float,
    width: float = 20,
    height: float = 10,
    parent_id: str | None = None,
) -> CdrObjectV1:
    object_id = f"object_{index:03d}"
    return CdrObjectV1(
        object_id=object_id,
        corel_name=object_id,
        object_type="rectangle",
        bbox={"x": 0, "y": 0, "width": 1, "height": 1},
        bbox_norm={"x": 0, "y": 0, "width": 0.01, "height": 0.01},
        parent_id=parent_id,
        metadata={
            "source_raw_bbox": {
                "left": left,
                "bottom": bottom,
                "width": width,
                "height": height,
            },
            "bbox_clipped_to_page": not (
                left >= 0
                and bottom >= 0
                and left + width <= 100
                and bottom + height <= 100
            ),
            "source_page": 1,
        },
    )


def _inspection(objects: list[CdrObjectV1]) -> CdrInspectionV1:
    return CdrInspectionV1(
        source_path="C:/private/source.cdr",
        source_size_bytes=123,
        source_mtime_ns=456,
        corel_version="fixture",
        page_count=1,
        page_width=100,
        page_height=100,
        unit="mm",
        corel_unit_code=3,
        layer_count=1,
        object_count=len(objects),
        text_object_count=0,
        bitmap_count=0,
        vector_count=len(objects),
        group_count=0,
        objects=objects,
    )


def test_off_page_cluster_is_selected_without_moving_source_geometry() -> None:
    inspection = _inspection(
        [
            _object(1, left=-220, bottom=160, width=100, height=60),
            _object(2, left=-205, bottom=175, width=35, height=12),
        ]
    )
    before = deepcopy(inspection.model_dump(mode="json"))

    analysis = analyze_design_regions(inspection, design_id="CDR_000159")

    assert analysis.status == "REGION_SELECTED"
    assert analysis.selected_region_id == "cluster_001"
    assert analysis.spatial_cluster_count == 1
    assert all(item.outside_page for item in analysis.objects)
    assert inspection.model_dump(mode="json") == before


def test_virtual_canvas_preserves_negative_source_coordinates() -> None:
    source = _object(1, left=-220, bottom=-40, width=100, height=60)
    inspection = _inspection([source])
    analysis = analyze_design_regions(
        inspection,
        design_id="CDR_000159",
        padding_ratio=0,
    )
    region = analysis.selected_region()
    assert region is not None

    document = inspection_to_design_document(
        inspection,
        source_sha256=SOURCE_SHA,
        category="OTHER",
        region=region,
    )

    assert document.canvas.source_type == "ARTWORK_REGION"
    assert document.canvas.normalization_origin.x == -220
    assert document.canvas.normalization_origin.y == -40
    assert document.elements[0].bbox_norm.model_dump() == {
        "x": 0.0,
        "y": 0.0,
        "width": 1.0,
        "height": 1.0,
    }
    assert document.elements[0].metadata["source_absolute_bbox"] == {
        "left": -220,
        "bottom": -40,
        "width": 100,
        "height": 60,
    }
    assert document.elements[0].metadata["source_absolute_bbox_unit"] == "mm"
    assert document.elements[0].metadata["virtual_bbox_bottom_left_norm"] == {
        "x": 0.0,
        "y": 0.0,
        "width": 1.0,
        "height": 1.0,
    }

    inch_document = inspection_to_design_document(
        inspection.model_copy(update={"unit": "in", "corel_unit_code": 1}),
        source_sha256=SOURCE_SHA,
        category="OTHER",
        region=region,
    )
    assert inch_document.canvas.unit == "mm"
    assert inch_document.canvas.normalization_origin.x == pytest.approx(-220 * 25.4)
    assert inch_document.canvas.artwork_region_bounds.right == pytest.approx(-120 * 25.4)
    assert inch_document.elements[0].metadata["source_absolute_bbox_unit"] == "in"


def test_partially_intersecting_page_is_not_silently_inside() -> None:
    inspection = _inspection([_object(1, left=90, bottom=20, width=20, height=10)])
    record = enumerate_object_space(inspection)[0]

    assert record.inside_page is False
    assert record.intersects_page is True
    assert record.outside_page is True


def test_multiple_spatial_regions_require_human_selection() -> None:
    inspection = _inspection(
        [
            _object(1, left=-300, bottom=0, width=80, height=50),
            _object(2, left=300, bottom=0, width=80, height=50),
        ]
    )

    analysis = analyze_design_regions(inspection, design_id="CDR_000401", gap=10)

    assert analysis.status == "REGION_SELECTION_REQUIRED"
    assert analysis.selected_region_id is None
    assert analysis.spatial_cluster_count == 2
    assert {region.region_id for region in analysis.candidate_regions} >= {
        "all_artwork",
        "cluster_001",
        "cluster_002",
    }


def test_group_children_remain_with_parent_cluster() -> None:
    parent = _object(1, left=-100, bottom=10, width=80, height=60)
    child = _object(
        2,
        left=-90,
        bottom=20,
        width=20,
        height=10,
        parent_id=parent.object_id,
    )
    inspection = _inspection([parent, child])

    analysis = analyze_design_regions(inspection, design_id="CDR_GROUP")
    region = analysis.selected_region()

    assert region is not None
    assert region.included_object_ids == ["object_001", "object_002"]


@pytest.mark.parametrize(
    ("total", "outside"),
    [(24, 24), (30, 30), (311, 137), (50, 50), (88, 88)],
)
def test_real_pilot_object_space_count_fixtures(total: int, outside: int) -> None:
    objects = []
    for index in range(total):
        if index < outside:
            objects.append(_object(index + 1, left=-50, bottom=10))
        else:
            objects.append(_object(index + 1, left=10, bottom=10))
    records = enumerate_object_space(_inspection(objects))

    assert len(records) == total
    assert sum(item.outside_page for item in records) == outside


def test_region_extraction_rejects_object_outside_selected_bounds() -> None:
    inspection = _inspection(
        [
            _object(1, left=-100, bottom=0, width=40, height=30),
            _object(2, left=100, bottom=0, width=40, height=30),
        ]
    )
    analysis = analyze_design_regions(inspection, design_id="CDR_AMBIGUOUS", gap=1)
    region = next(
        item for item in analysis.candidate_regions if item.region_id == "cluster_001"
    )
    invalid = region.model_copy(
        update={"included_object_ids": ["object_001", "object_002"]}
    )

    with pytest.raises(ValueError, match="exceeds selected design region"):
        inspection_to_design_document(
            inspection,
            source_sha256=SOURCE_SHA,
            category="OTHER",
            region=invalid,
        )


class _Collection:
    def __init__(self, values):
        self.values = values
        self.Count = len(values)

    def __iter__(self):
        return iter(self.values)

    def Item(self, index):
        return self.values[index - 1]


class _RegionShape:
    def __init__(self, name: str):
        self.Name = name
        self.Shapes = _Collection([])


class _ShapeRange:
    def __init__(self):
        self.added = []
        self.selection_created = False

    def Add(self, shape):
        self.added.append(shape)

    def CreateSelection(self):
        self.selection_created = True


class _RegionDocument:
    def __init__(self, source: Path, output_holder: dict[str, object]):
        shapes = _Collection([_RegionShape("object_001"), _RegionShape("object_002")])
        self.ActivePage = SimpleNamespace(
            Shapes=shapes,
            ActiveLayer=SimpleNamespace(Shapes=shapes),
        )
        self.FullFileName = str(source)
        self.Unit = 3
        self.closed = False
        self.output_holder = output_holder

    def ClearSelection(self):
        return None

    def ExportEx(self, output, *_args):
        self.output_holder["output"] = output

        class _Export:
            def Finish(self_inner):
                Path(output).write_bytes(b"png-fixture")

        return _Export()

    def Close(self):
        self.closed = True


class _RegionBridge:
    def __init__(self, source: Path):
        self.output_holder: dict[str, object] = {}
        self.document = _RegionDocument(source, self.output_holder)
        self.shape_range = _ShapeRange()
        self.application = SimpleNamespace(
            ActiveDocument=None,
            OpenDocument=self._open,
            CreateShapeRange=lambda: self.shape_range,
            CreateStructExportOptions=lambda: SimpleNamespace(),
            CreateStructPaletteOptions=lambda: SimpleNamespace(),
        )
        self.active = SimpleNamespace(FullFileName=str(source.parent / "other.cdr"))

    def _open(self, _path):
        self.application.ActiveDocument = self.document

    @contextmanager
    def session(self):
        yield self.application, self.active


def test_region_preview_selects_objects_and_closes_without_source_save(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    source = root / "source.cdr"
    source.write_bytes(b"real-source-fixture")
    inspection = _inspection(
        [
            _object(1, left=-100, bottom=0),
            _object(2, left=-80, bottom=0),
        ]
    )
    region = analyze_design_regions(
        inspection,
        design_id="CDR_000001",
        padding_ratio=0,
    ).selected_region()
    assert region is not None
    bridge = _RegionBridge(source)
    before = (source.stat().st_size, source.stat().st_mtime_ns)

    target = CompanyCdrInspector(bridge).render_region_preview(
        source,
        tmp_path / "region.png",
        archive_root=root,
        region=region,
    )

    assert target.read_bytes() == b"png-fixture"
    assert bridge.shape_range.selection_created is True
    assert [shape.Name for shape in bridge.shape_range.added] == [
        "object_001",
        "object_002",
    ]
    assert bridge.document.closed is True
    assert before == (source.stat().st_size, source.stat().st_mtime_ns)


def test_region_labels_are_below_artwork_and_contact_sheet_is_created(tmp_path: Path) -> None:
    raw = tmp_path / "raw.png"
    Image.new("RGB", (400, 200), "#336699").save(raw)

    labeled = label_region_preview(
        raw,
        tmp_path / "labeled.png",
        design_id="CDR_000159",
        region_id="cluster_001",
    )
    with Image.open(labeled) as image:
        assert image.size == (400, 290)
        assert image.getpixel((10, 10)) == (51, 102, 153)
        assert image.getpixel((10, 250)) == (255, 255, 255)

    sheet = build_region_contact_sheet([labeled], tmp_path / "sheet.png")
    with Image.open(sheet) as image:
        assert image.width > 400
        assert image.height > 290
