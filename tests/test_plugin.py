from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import main
from corel_bridge import CorelDrawBridge, CorelDrawBridgeError
from extended_bridge import ExtendedCorelDrawBridge


class FakeFill:
    def __init__(self) -> None:
        self.color = None

    def ApplyUniformFill(self, color) -> None:
        self.color = color


class FakeShape:
    def __init__(self, name: str) -> None:
        self.Name = name
        self.Fill = FakeFill()
        self.Outline = SimpleNamespace(Width=None, Color=None)
        self.Text = SimpleNamespace(Story=SimpleNamespace(Font=None, Size=None))


class FakeShapes:
    def __init__(self) -> None:
        self.items: list[FakeShape] = []

    @property
    def Count(self) -> int:
        return len(self.items)

    def Item(self, key):
        if isinstance(key, str):
            for shape in self.items:
                if shape.Name == key:
                    return shape
            raise KeyError(key)
        return self.items[key - 1]


class FakeLayer:
    def __init__(self) -> None:
        self.Shapes = FakeShapes()
        self.last_rectangle = None
        self.last_ellipse = None

    def _add(self, name: str) -> FakeShape:
        shape = FakeShape(name)
        self.Shapes.items.append(shape)
        return shape

    def CreateRectangle(self, left, top, right, bottom):
        self.last_rectangle = (left, top, right, bottom)
        return self._add("Rectangle")

    def CreateEllipse(self, left, top, right, bottom):
        self.last_ellipse = (left, top, right, bottom)
        return self._add("Ellipse")

    def CreateArtisticText(self, _x, _y, _text):
        return self._add("Text")


class FakeShapeRange:
    def __init__(self, layer: FakeLayer) -> None:
        self.layer = layer
        self.shapes: list[FakeShape] = []

    def Add(self, shape: FakeShape) -> None:
        self.shapes.append(shape)

    def Group(self) -> FakeShape:
        group = FakeShape("Group")
        self.layer.Shapes.items.append(group)
        return group


class FakeExportFilter:
    def __init__(self) -> None:
        self.finished = False

    def Finish(self) -> None:
        self.finished = True


class FakeDocument:
    def __init__(self, layer: FakeLayer) -> None:
        self.Name = "Mock.cdr"
        self.ActivePage = SimpleNamespace(ActiveLayer=layer)
        self.published_pdf = None
        self.export_args = None
        self.export_filter = FakeExportFilter()

    def PublishToPDF(self, path: str) -> None:
        self.published_pdf = path

    def ExportEx(self, *args):
        self.export_args = args
        return self.export_filter


class FakeApplication:
    def __init__(self) -> None:
        self.Visible = False
        self.Version = "24.5"
        self.layer = FakeLayer()
        self.ActiveDocument = FakeDocument(self.layer)
        self.Documents = SimpleNamespace(Count=1)
        self.last_export_options = None

    def CreateDocument(self):
        return self.ActiveDocument

    def CreateCMYKColor(self, c, m, y, k):
        return c, m, y, k

    def CreateShapeRange(self):
        return FakeShapeRange(self.layer)

    def CreateStructExportOptions(self):
        self.last_export_options = SimpleNamespace()
        return self.last_export_options


@pytest.fixture
def bridges():
    app = FakeApplication()
    bridge = CorelDrawBridge(dispatcher=lambda _prog_id: app)
    return app, bridge, ExtendedCorelDrawBridge(bridge)


def test_create_rectangle_uses_expected_bounds_and_color(bridges):
    app, bridge, _ = bridges
    name = bridge.create_rectangle_cmyk(
        10, 20, 30, 5, 1, 2, 3, 4, shape_name="background"
    )
    assert name == "background"
    assert app.layer.last_rectangle == (10, 20, 40, 15)
    assert app.layer.Shapes.Item(name).Fill.color == (1, 2, 3, 4)


def test_text_applies_font_size_and_fill(bridges):
    app, bridge, _ = bridges
    name = bridge.create_artistic_text_cmyk(
        "Xin chào", 1, 2, "Arial", 36, 0, 0, 0, 100, "title"
    )
    shape = app.layer.Shapes.Item(name)
    assert shape.Text.Story.Font == "Arial"
    assert shape.Text.Story.Size == 36
    assert shape.Fill.color == (0, 0, 0, 100)


def test_outline_group_and_missing_shape(bridges):
    app, bridge, extended = bridges
    first = bridge.create_rectangle_cmyk(0, 10, 5, 5, 0, 0, 0, 0, "one")
    second = bridge.create_ellipse_cmyk(5, 10, 5, 5, 0, 0, 0, 0, "two")
    extended.set_shape_outline_cmyk(first, 0.2, 10, 20, 30, 40)
    assert app.layer.Shapes.Item(first).Outline.Color == (10, 20, 30, 40)
    assert extended.group_shapes_by_names([first, second], "pair") == "pair"
    with pytest.raises(CorelDrawBridgeError, match="missing"):
        extended.group_shapes_by_names([first, "missing"])


def test_export_pdf_and_png(tmp_path: Path, bridges):
    app, _, extended = bridges
    pdf_path = extended.export_document(str(tmp_path / "print"), "pdf")
    png_path = extended.export_document(str(tmp_path / "preview"), "png", 150)
    assert pdf_path.endswith("print.pdf")
    assert app.ActiveDocument.published_pdf == pdf_path
    assert png_path.endswith("preview.png")
    assert app.ActiveDocument.export_args[1:3] == (802, 1)
    assert app.last_export_options.ResolutionX == 150
    assert app.ActiveDocument.export_filter.finished is True


def test_api_workflow_and_validation(monkeypatch):
    app = FakeApplication()
    bridge = CorelDrawBridge(dispatcher=lambda _prog_id: app)
    monkeypatch.setattr(main, "corel_bridge", bridge)
    monkeypatch.setattr(main, "extended_bridge", ExtendedCorelDrawBridge(bridge))
    client = TestClient(main.app)

    assert client.get("/health").status_code == 200
    rectangle = client.post(
        "/api/v1/corel/shape/rectangle",
        json={"x": 0, "y": 20, "width": 10, "height": 5, "name": "bg"},
    )
    ellipse = client.post(
        "/api/v1/corel/shape/ellipse",
        json={"x": 2, "y": 18, "width": 3, "height": 3, "name": "logo"},
    )
    grouped = client.post(
        "/api/v1/corel/shape/group",
        json={"shape_names": ["bg", "logo"], "group_name": "header"},
    )
    invalid = client.post(
        "/api/v1/corel/shape/rectangle",
        json={"x": 0, "y": 0, "width": 0, "height": 5},
    )

    assert rectangle.status_code == 200
    assert ellipse.status_code == 200
    assert grouped.json()["shape_name"] == "header"
    assert invalid.status_code == 422
