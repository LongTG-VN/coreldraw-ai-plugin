from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import main
from corel_bridge import CorelDrawBridge, CorelDrawBridgeError
from extended_bridge import ExtendedCorelDrawBridge
from image_providers import DisabledImageProvider
from template_engine import TemplateEngine, TemplateRegistry
from template_models import MenuRenderRequest


class FakeFill:
    def __init__(self) -> None:
        self.color = None

    def ApplyUniformFill(self, color) -> None:
        self.color = color


class FakeStory:
    def __init__(self, text: str = "", size: float = 24) -> None:
        self.Text = text
        self.Size = size
        self.Font = None


class FakeShape:
    def __init__(
        self,
        name: str,
        *,
        text: str | None = None,
        x: float = 0,
        y: float = 0,
        width: float = 20,
        height: float = 10,
    ) -> None:
        self.Name = name
        self.Fill = FakeFill()
        self.Outline = SimpleNamespace(Width=None, Color=None)
        self.Text = SimpleNamespace(Story=FakeStory(text or ""))
        self.LeftX = x
        self.BottomY = y
        self.PositionX = x
        self.PositionY = y
        self.SizeWidth = width
        self.SizeHeight = height
        self.deleted = False

    def SetSize(self, width: float, height: float) -> None:
        self.SizeWidth = width
        self.SizeHeight = height

    def SetPosition(self, x: float, y: float) -> None:
        self.LeftX = self.PositionX = x
        self.BottomY = self.PositionY = y

    def Delete(self) -> None:
        self.deleted = True


class FakeShapes:
    def __init__(self) -> None:
        self.items: list[FakeShape] = []

    @property
    def Count(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    def Item(self, key):
        if isinstance(key, str):
            for shape in self.items:
                if shape.Name == key:
                    return shape
            raise KeyError(key)
        return self.items[key - 1]

    def __call__(self, key):
        return self.Item(key)


class FakeLayer:
    def __init__(self) -> None:
        self.Shapes = FakeShapes()
        self.last_rectangle = None
        self.last_ellipse = None
        self.imported_paths: list[str] = []

    def _add(self, name: str, **kwargs) -> FakeShape:
        shape = FakeShape(name, **kwargs)
        self.Shapes.items.append(shape)
        return shape

    def CreateRectangle(self, left, top, right, bottom):
        self.last_rectangle = (left, top, right, bottom)
        return self._add("Rectangle")

    def CreateEllipse(self, left, top, right, bottom):
        self.last_ellipse = (left, top, right, bottom)
        return self._add("Ellipse")

    def CreateArtisticText(self, _x, _y, text):
        return self._add("Text", text=text)

    def Import(self, path: str):
        self.imported_paths.append(path)
        return self._add("Imported", width=100, height=100)


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
        self.FileName = "Mock.cdr"
        self.ActivePage = SimpleNamespace(
            ActiveLayer=layer,
            Shapes=layer.Shapes,
            Layers=[layer],
        )
        self.ActiveSelectionRange = SimpleNamespace(Shapes=FakeShapes())
        self.published_pdf = None
        self.export_args = None
        self.export_filter = FakeExportFilter()
        self.saved_as = None

    def PublishToPDF(self, path: str) -> None:
        self.published_pdf = path

    def ExportEx(self, *args):
        self.export_args = args
        return self.export_filter

    def SaveAs(self, path: str) -> None:
        self.saved_as = path


class FakeApplication:
    def __init__(self) -> None:
        self.Visible = False
        self.Version = "24.5"
        self.layer = FakeLayer()
        self.ActiveDocument = FakeDocument(self.layer)
        self.Documents = SimpleNamespace(Count=1)
        self.last_export_options = None
        self.last_palette_options = None
        self.opened_path = None

    def CreateDocument(self):
        return self.ActiveDocument

    def OpenDocument(self, path: str):
        self.opened_path = path
        return self.ActiveDocument

    def CreateCMYKColor(self, c, m, y, k):
        return c, m, y, k

    def CreateShapeRange(self):
        return FakeShapeRange(self.layer)

    def CreateStructExportOptions(self):
        self.last_export_options = SimpleNamespace()
        return self.last_export_options

    def CreateStructPaletteOptions(self):
        self.last_palette_options = SimpleNamespace()
        return self.last_palette_options


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


def test_template_text_image_and_save(tmp_path: Path, bridges):
    app, bridge, _ = bridges
    title = app.layer._add("placeholder_title", text="OLD", width=80)
    slot = app.layer._add(
        "placeholder_item_1_image", x=10, y=20, width=40, height=30
    )
    image = tmp_path / "food.png"
    image.write_bytes(b"fake-image")

    result = bridge.set_text_content("placeholder_title", "NEW MENU")
    placed = bridge.import_image_into_slot(
        str(image), "placeholder_item_1_image", imported_shape_name="dish_1"
    )
    saved = bridge.save_document(str(tmp_path / "editable"))

    assert result["text"] == "NEW MENU"
    assert title.Text.Story.Text == "NEW MENU"
    imported = app.layer.Shapes.Item("dish_1")
    assert imported.SizeWidth == slot.SizeWidth
    assert imported.SizeHeight == slot.SizeHeight
    assert imported.LeftX == slot.LeftX
    assert imported.BottomY == slot.BottomY
    assert placed["slot_shape_name"] == "placeholder_item_1_image"
    assert saved.endswith("editable.cdr")


def _write_manifest(root: Path, cdr_path: Path) -> None:
    manifest = {
        "schema_version": "1.0",
        "template_id": "menu_test",
        "name": "Test menu",
        "category": "menu",
        "cdr_path": str(cdr_path),
        "placeholders": [
            {"key": "title", "shape_name": "placeholder_title", "required": True},
            {"key": "subtitle", "shape_name": "placeholder_subtitle", "required": False},
            {"key": "address", "shape_name": "placeholder_address", "required": False},
            {"key": "phone", "shape_name": "placeholder_phone", "required": False}
        ],
        "repeaters": [{
            "source": "items",
            "start_index": 1,
            "max_items": 2,
            "fields": {
                "section": "placeholder_item_{index}_section",
                "name": "placeholder_item_{index}_name",
                "price": "placeholder_item_{index}_price",
                "description": "placeholder_item_{index}_description",
                "image": "placeholder_item_{index}_image"
            }
        }]
    }
    root.mkdir(parents=True)
    (root / "menu.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_render_menu_from_manifest(tmp_path: Path, bridges):
    app, bridge, extended = bridges
    cdr = tmp_path / "template.cdr"
    cdr.write_bytes(b"fake-cdr")
    manifests = tmp_path / "manifests"
    _write_manifest(manifests, cdr)

    for name in [
        "placeholder_title", "placeholder_subtitle", "placeholder_address",
        "placeholder_phone", "placeholder_item_1_section",
        "placeholder_item_1_name", "placeholder_item_1_price",
        "placeholder_item_1_description", "placeholder_item_1_image",
        "placeholder_item_2_section", "placeholder_item_2_name",
        "placeholder_item_2_price", "placeholder_item_2_description",
        "placeholder_item_2_image",
    ]:
        app.layer._add(name, text="OLD", width=30, height=15)

    image = tmp_path / "dish.png"
    image.write_bytes(b"fake-image")
    engine = TemplateEngine(
        TemplateRegistry(manifests), bridge, extended, DisabledImageProvider()
    )
    request = MenuRenderRequest.model_validate({
        "title": "QUÁN NHÀ LONG",
        "subtitle": "Ngon mỗi ngày",
        "address": "Cần Thơ",
        "phone": "0900",
        "sections": [{
            "name": "Món chính",
            "items": [
                {"name": "Cơm tấm", "price": "35.000", "image_path": str(image)},
                {"name": "Bún bò", "price": "40.000", "image_prompt": "food photo"}
            ]
        }],
        "output_dir": str(tmp_path / "out"),
        "file_stem": "menu-final",
        "export_pdf": True,
        "export_png": True
    })

    report = engine.render_menu("menu_test", request)

    assert report["status"] == "completed_with_pending_images"
    assert report["outputs"]["cdr"].endswith("menu-final.cdr")
    assert report["outputs"]["pdf"].endswith("menu-final.pdf")
    assert report["outputs"]["png"].endswith("menu-final-preview.png")
    assert app.layer.Shapes.Item("placeholder_title").Text.Story.Text == "QUÁN NHÀ LONG"
    assert app.layer.Shapes.Item("placeholder_item_1_name").Text.Story.Text == "Cơm tấm"
    assert app.layer.Shapes.Item("placeholder_item_2_price").Text.Story.Text == "40.000"
    assert report["pending_image_prompts"][0]["item"] == "Bún bò"


def test_api_workflow_and_validation(monkeypatch):
    app = FakeApplication()
    bridge = CorelDrawBridge(dispatcher=lambda _prog_id: app)
    advanced = ExtendedCorelDrawBridge(bridge)
    monkeypatch.setattr(main, "corel_bridge", bridge)
    monkeypatch.setattr(main, "extended_bridge", advanced)
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
