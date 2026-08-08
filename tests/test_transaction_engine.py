from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from corel_bridge import CorelDrawBridgeError
from transaction_engine import DesignTransactionEngine, DesignTransactionError


class FakeDocument:
    def __init__(self) -> None:
        self.begin_names: list[str] = []
        self.end_count = 0
        self.undo_count = 0

    def BeginCommandGroup(self, name: str) -> None:
        self.begin_names.append(name)

    def EndCommandGroup(self) -> None:
        self.end_count += 1

    def Undo(self) -> None:
        self.undo_count += 1


class FakeBridge:
    def __init__(self) -> None:
        self.doc = FakeDocument()
        self.created: list[str] = []

    @contextmanager
    def session(self):
        yield SimpleNamespace(), self.doc

    def create_rectangle_cmyk(self, *args, shape_name=None):
        name = shape_name or "rectangle"
        self.created.append(name)
        return name

    def create_ellipse_cmyk(self, *args, shape_name=None):
        name = shape_name or "ellipse"
        self.created.append(name)
        return name

    def create_artistic_text_cmyk(self, *args, shape_name=None):
        name = shape_name or "text"
        self.created.append(name)
        return name


class FakeDesign:
    def __init__(self) -> None:
        self.transforms: list[str] = []
        self.fail_on: str | None = None

    def transform_shape(self, shape_name: str, **kwargs):
        if shape_name == self.fail_on:
            raise CorelDrawBridgeError(f"boom:{shape_name}")
        self.transforms.append(shape_name)
        return {"name": shape_name, **kwargs}

    def set_fill_cmyk(self, shape_name: str, *color):
        return {"name": shape_name, "color": color}

    def snapshot(self):
        return {
            "document_name": "Mock.cdr",
            "object_count": len(self.transforms),
            "page": {"width": 100, "height": 50},
            "objects": [{"name": name} for name in self.transforms],
        }

    def check_design(self, **_kwargs):
        return {"status": "pass", "errors": 0, "warnings": 0, "issues": []}


class FakeAdvanced:
    def __init__(self) -> None:
        self.exports: list[tuple[str, str, int]] = []

    def export_document(self, path: str, fmt: str, dpi: int = 300) -> str:
        self.exports.append((path, fmt, dpi))
        return path

    def set_shape_outline_cmyk(self, shape_name: str, *_args):
        return shape_name

    def group_shapes_by_names(self, _names, group_name=None):
        return group_name or "group"


def test_transaction_commits_once_and_returns_feedback() -> None:
    bridge = FakeBridge()
    design = FakeDesign()
    advanced = FakeAdvanced()
    engine = DesignTransactionEngine(bridge, design, advanced)

    result = engine.execute(
        [
            {"op": "transform", "shape_name": "title", "x": 10},
            {
                "op": "fill",
                "shape_name": "title",
                "color": {"cyan": 0, "magenta": 0, "yellow": 0, "black": 100},
            },
            {
                "op": "create_rectangle",
                "x": 0,
                "y": 50,
                "width": 100,
                "height": 50,
                "name": "background",
                "color": {"cyan": 5, "magenta": 5, "yellow": 5, "black": 0},
            },
        ],
        name="Antigravity pass 1",
        preview_path="preview.png",
        preview_dpi=120,
    )

    assert result["status"] == "committed"
    assert result["operation_count"] == 3
    assert bridge.doc.begin_names == ["Antigravity pass 1"]
    assert bridge.doc.end_count == 1
    assert bridge.doc.undo_count == 0
    assert bridge.created == ["background"]
    assert result["feedback"]["check"]["status"] == "pass"
    assert result["feedback"]["preview"]["file_path"] == "preview.png"
    assert advanced.exports == [("preview.png", "png", 120)]


def test_transaction_rolls_back_one_group_on_middle_failure() -> None:
    bridge = FakeBridge()
    design = FakeDesign()
    design.fail_on = "bad"
    engine = DesignTransactionEngine(bridge, design, FakeAdvanced())

    with pytest.raises(DesignTransactionError) as caught:
        engine.execute(
            [
                {"op": "transform", "shape_name": "good", "x": 10},
                {"op": "transform", "shape_name": "bad", "x": 20},
                {"op": "transform", "shape_name": "never", "x": 30},
            ],
            include_feedback=False,
        )

    report = caught.value.report
    assert report["status"] == "rolled_back"
    assert report["completed_operations"] == 1
    assert report["failed_index"] == 1
    assert report["failed_operation"]["shape_name"] == "bad"
    assert report["rolled_back"] is True
    assert bridge.doc.end_count == 1
    assert bridge.doc.undo_count == 1
    assert design.transforms == ["good"]


def test_unknown_operation_is_rolled_back() -> None:
    bridge = FakeBridge()
    engine = DesignTransactionEngine(bridge, FakeDesign(), FakeAdvanced())

    with pytest.raises(DesignTransactionError, match="không được hỗ trợ") as caught:
        engine.execute([{"op": "teleport"}], include_feedback=False)

    assert caught.value.report["failed_index"] == 0
    assert bridge.doc.end_count == 1
    assert bridge.doc.undo_count == 1
