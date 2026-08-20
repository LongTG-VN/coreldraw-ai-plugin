from __future__ import annotations

import pytest

from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.corel_operator.inspection import OperatorDocumentView


def _inspection() -> CdrInspectionV1:
    objects = [
        CdrObjectV1(
            object_id="a",
            corel_name="A",
            object_type="text",
            bbox={"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0},
            bbox_norm={"x": 0.0, "y": 0.0, "width": 0.1, "height": 0.1},
            text="Hello Việt Nam",
            metadata={"source_page": 1, "bbox_clipped_to_page": False},
        ),
        CdrObjectV1(
            object_id="b",
            corel_name="B",
            object_type="vector",
            bbox={"x": 5.0, "y": 5.0, "width": 10.0, "height": 10.0},
            bbox_norm={"x": 0.05, "y": 0.05, "width": 0.1, "height": 0.1},
            metadata={"source_page": 1, "bbox_clipped_to_page": True},
        ),
    ]
    return CdrInspectionV1(
        source_path="fixture.cdr",
        source_size_bytes=1,
        source_mtime_ns=1,
        corel_version="fake",
        page_count=2,
        page_width=100,
        page_height=100,
        unit="mm",
        corel_unit_code=3,
        layer_count=1,
        object_count=2,
        text_object_count=1,
        bitmap_count=0,
        vector_count=1,
        group_count=0,
        objects=objects,
    )


def test_document_view_queries_objects_and_pages() -> None:
    view = OperatorDocumentView(_inspection())
    assert len(view.list_pages()) == 2
    assert view.list_pages()[1]["objects_inspected"] is False
    assert view.get_object("a").corel_name == "A"
    assert [item.object_id for item in view.list_objects(object_type="text")] == ["a"]


def test_document_view_text_search_is_explicit() -> None:
    view = OperatorDocumentView(_inspection())
    assert view.find_text("Việt")
    assert view.find_text("hello", case_sensitive=False)
    assert view.find_text(r"Vi.t", regex=True)
    with pytest.raises(ValueError):
        view.find_text("(", regex=True)


def test_document_view_geometry_checks() -> None:
    view = OperatorDocumentView(_inspection())
    collisions = view.collisions()
    assert len(collisions) == 1
    assert collisions[0].overlap_area == 25.0
    assert view.outside_canvas() == ["b"]
