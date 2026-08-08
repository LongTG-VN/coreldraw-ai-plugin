from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from corel_bridge import CorelDrawBridgeError
from design_bridge import DesignBridge


class FakeFill:
    def __init__(self) -> None:
        self.color = None

    def ApplyUniformFill(self, color) -> None:
        self.color = color


class FakePowerClip:
    def __init__(self) -> None:
        self.ContentsLocked = False


class FakeShape:
    def __init__(
        self,
        name: str,
        *,
        x: float = 10,
        y: float = 10,
        width: float = 20,
        height: float = 10,
        text: str | None = None,
    ) -> None:
        self.Name = name
        self.LeftX = self.PositionX = x
        self.BottomY = self.PositionY = y
        self.SizeWidth = width
        self.SizeHeight = height
        self.RotationAngle = 0
        self.Fill = FakeFill()
        self.Type = 1
        self.Layer = SimpleNamespace(Name="Layer 1")
        self.Shapes = SimpleNamespace(Count=0)
        self.PowerClip = FakePowerClip()
        self.deleted = False
        self.order_action: tuple[str, str | None] | None = None
        self.powerclip_target: str | None = None
        if text is not None:
            self.Text = SimpleNamespace(
                Story=SimpleNamespace(Text=text, Size=5, Font="Arial")
            )

    def SetSize(self, width: float, height: float) -> None:
        self.SizeWidth = width
        self.SizeHeight = height

    def SetPosition(self, x: float, y: float) -> None:
        self.LeftX = self.PositionX = x
        self.BottomY = self.PositionY = y

    def Duplicate(self, offset_x: float = 0, offset_y: float = 0):
        return FakeShape(
            self.Name + "_copy",
            x=self.LeftX + offset_x,
            y=self.BottomY + offset_y,
            width=self.SizeWidth,
            height=self.SizeHeight,
        )

    def OrderToFront(self) -> None:
        self.order_action = ("front", None)

    def OrderToBack(self) -> None:
        self.order_action = ("back", None)

    def OrderFrontOf(self, other) -> None:
        self.order_action = ("front_of", other.Name)

    def OrderBackOf(self, other) -> None:
        self.order_action = ("back_of", other.Name)

    def AddToPowerClip(self, frame) -> None:
        self.powerclip_target = frame.Name

    def Delete(self) -> None:
        self.deleted = True


class FakeShapes:
    def __init__(self, items: list[FakeShape]) -> None:
        self.items = items

    @property
    def Count(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    def Item(self, key):
        for item in self.items:
            if item.Name == key:
                return item
        raise KeyError(key)


class FakeLayer:
    def __init__(self, shapes: FakeShapes) -> None:
        self.Shapes = shapes
        self.imported: FakeShape | None = None

    def Import(self, _path: str):
        self.imported = FakeShape("Imported", x=0, y=0, width=100, height=100)
        self.Shapes.items.append(self.imported)
        return self.imported


class FakePage:
    def __init__(self, layer: FakeLayer) -> None:
        self.Name = "Page 1"
        self.SizeWidth = 100
        self.SizeHeight = 50
        self.Shapes = layer.Shapes
        self.ActiveLayer = layer

    def SetSize(self, width: float, height: float) -> None:
        self.SizeWidth = width
        self.SizeHeight = height


class FakeDocument:
    def __init__(self, layer: FakeLayer) -> None:
        self.Name = "Test.cdr"
        self.Unit = 4
        self.undo_count = 0
        self.ActivePage = FakePage(layer)

    def Undo(self) -> None:
        self.undo_count += 1


class FakeApplication:
    Version = "27.0"

    def CreateCMYKColor(self, c: int, m: int, y: int, k: int):
        return c, m, y, k


class FakeBridge:
    def __init__(self) -> None:
        self.items = [
            FakeShape("title", text="HELLO"),
            FakeShape("outside", x=95, y=45, width=10, height=10),
        ]
        self.shapes = FakeShapes(self.items)
        self.layer = FakeLayer(self.shapes)
        self.doc = FakeDocument(self.layer)
        self.app = FakeApplication()

    @contextmanager
    def session(self):
        yield self.app, self.doc

    def _iter_shapes_recursive(self, shapes):
        yield from shapes

    def _find_shape_in_document(self, _doc, name: str):
        try:
            return self.shapes.Item(name)
        except KeyError as exc:
            raise CorelDrawBridgeError(f"Không tìm thấy shape '{name}'.") from exc

    @staticmethod
    def _assign_shape_name(shape, name, prefix: str):
        shape.Name = name or prefix
        return shape.Name

    @staticmethod
    def _create_cmyk_color(app, c: int, m: int, y: int, k: int):
        return app.CreateCMYKColor(c, m, y, k)

    @staticmethod
    def _imported_shape(result, _doc, _layer):
        return result


def test_snapshot_transform_duplicate_fill_and_check() -> None:
    bridge = FakeBridge()
    design = DesignBridge(bridge)

    snapshot = design.snapshot()
    assert snapshot["object_count"] == 2
    assert snapshot["page"]["width"] == 100

    moved = design.transform_shape(
        "title", x=12, y=15, width=30, height=12, rotation=15
    )
    assert (moved["x"], moved["y"], moved["width"], moved["rotation"]) == (
        12,
        15,
        30,
        15,
    )

    duplicate = design.duplicate_shape("title", offset_x=5, new_name="title_copy")
    assert duplicate["name"] == "title_copy"
    assert duplicate["x"] == 17

    filled = design.set_fill_cmyk("title", 1, 2, 3, 4)
    assert filled["name"] == "title"
    assert bridge.items[0].Fill.color == (1, 2, 3, 4)

    report = design.check_design(min_font_size=6)
    assert report["status"] == "pass"
    assert {issue["code"] for issue in report["issues"]} == {
        "small_text",
        "outside_page",
    }


def test_import_delete_undo_and_allowlist(tmp_path: Path) -> None:
    bridge = FakeBridge()
    design = DesignBridge(bridge)
    svg = tmp_path / "logo.svg"
    svg.write_text("<svg/>", encoding="utf-8")

    imported = design.import_asset(
        str(svg), name="logo", x=3, y=4, width=20, height=20
    )
    assert imported["name"] == "logo"
    assert imported["source_path"].endswith("logo.svg")

    deleted = design.delete_shape("logo")
    assert deleted == {"shape_name": "logo", "deleted": True}
    assert bridge.layer.imported is not None
    assert bridge.layer.imported.deleted is True

    assert design.undo(2)["completed_steps"] == 2

    bad = tmp_path / "payload.exe"
    bad.write_bytes(b"x")
    with pytest.raises(CorelDrawBridgeError, match="allow-list"):
        design.import_asset(str(bad))


def test_batch_typography_order_and_page_resize() -> None:
    bridge = FakeBridge()
    bridge.items.append(FakeShape("logo", x=60, y=10, width=10, height=10))
    design = DesignBridge(bridge)

    changed = design.batch_transform(
        [
            {"shape_name": "title", "x": 5, "y": 6, "rotation": 8},
            {"shape_name": "logo", "width": 15, "height": 12},
        ]
    )
    assert changed[0]["x"] == 5
    assert changed[0]["rotation"] == 8
    assert changed[1]["width"] == 15

    text = design.set_typography(
        "title", text="NEW TITLE", font_name="Inter", font_size=18
    )
    assert text["text"] == "NEW TITLE"
    assert text["font_name"] == "Inter"
    assert text["font_size"] == 18

    design.order_shape("title", "front_of", relative_to="logo")
    assert bridge.shapes.Item("title").order_action == ("front_of", "logo")
    design.order_shape("logo", "back")
    assert bridge.shapes.Item("logo").order_action == ("back", None)

    page = design.set_page_size(210, 297)
    assert page == {"width": 210.0, "height": 297.0}


def test_align_and_distribute_geometry() -> None:
    bridge = FakeBridge()
    bridge.items.clear()
    bridge.items.extend(
        [
            FakeShape("a", x=0, y=0, width=10, height=10),
            FakeShape("b", x=30, y=20, width=10, height=10),
            FakeShape("c", x=80, y=40, width=20, height=10),
        ]
    )
    design = DesignBridge(bridge)

    aligned = design.align_shapes(
        ["a", "b", "c"], horizontal="center", relative_to="page"
    )
    assert [item["x"] for item in aligned] == [45, 45, 40]

    # Reset X positions and distribute the three shapes across the original span.
    bridge.shapes.Item("a").SetPosition(0, 0)
    bridge.shapes.Item("b").SetPosition(30, 20)
    bridge.shapes.Item("c").SetPosition(80, 40)
    distributed = design.distribute_shapes(
        ["a", "b", "c"], axis="horizontal", mode="gaps"
    )
    assert distributed[0]["x"] == 0
    assert distributed[1]["x"] == 40
    assert distributed[2]["x"] == 80


def test_fit_to_frame_cover_and_powerclip() -> None:
    bridge = FakeBridge()
    bridge.items.clear()
    bridge.items.extend(
        [
            FakeShape("photo", x=0, y=0, width=200, height=100),
            FakeShape("frame", x=10, y=5, width=50, height=50),
        ]
    )
    design = DesignBridge(bridge)

    result = design.fit_shape_to_frame(
        "photo", "frame", mode="cover", powerclip=True, lock_contents=True
    )
    photo = bridge.shapes.Item("photo")
    frame = bridge.shapes.Item("frame")

    assert result["mode"] == "cover"
    assert result["powerclip"] is True
    assert photo.SizeWidth == 100
    assert photo.SizeHeight == 50
    assert photo.LeftX == -15
    assert photo.BottomY == 5
    assert photo.powerclip_target == "frame"
    assert frame.PowerClip.ContentsLocked is True
