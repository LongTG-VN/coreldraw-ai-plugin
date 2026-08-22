from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest
from PIL import Image

from training.corel_operator.runtime import CanonicalExportError, CorelOperatorRuntime
from transaction_engine import DesignTransactionError


class Story:
    def __init__(self) -> None:
        self.Text = "old"
        self.Font = "Arial"
        self.Size = 10.0
        self.replace_wide_args = None

    def ReplaceWide(self, value: str, language_id=0, charset=-1, font=None):
        self.replace_wide_args = (value, language_id, charset, font)
        self.Text = value
        return self


class Text:
    def __init__(self) -> None:
        self.Story = Story()


class Shape:
    def __init__(self) -> None:
        self.Name = ""
        self.Text = Text()
        self.SizeWidth = 10.0
        self.SizeHeight = 2.0
        self.PositionX = 1.0
        self.PositionY = 1.0
        self.RotationAngle = 0.0

    def Move(self, delta_x: float, delta_y: float) -> None:
        self.PositionX += delta_x
        self.PositionY += delta_y


class Document:
    def __init__(self, shape: Shape) -> None:
        self.shape = shape
        self.started = 0
        self.ended = 0
        self.undo_count = 0
        self._before = shape.Text.Story.Size

    def BeginCommandGroup(self, name: str) -> None:
        self.started += 1
        self._before = self.shape.Text.Story.Size

    def EndCommandGroup(self) -> None:
        self.ended += 1

    def Undo(self) -> None:
        self.undo_count += 1
        self.shape.Text.Story.Size = self._before


class Bridge:
    def __init__(self, document: Document) -> None:
        self.document = document

    @contextmanager
    def session(self):
        yield object(), self.document


class Inspector:
    def __init__(self, shape: Shape) -> None:
        self.shape = shape

    def _shape_map(self, document):
        return {"object_1": self.shape}, {"object_1": None}


class TextRangeComError(RuntimeError):
    hresult = -2147467259


class FlakyStory:
    def __init__(self, *, fail_size: bool) -> None:
        self.Text = "old"
        self.Font = "Arial"
        self._size = 10.0
        self.fail_size = fail_size

    @property
    def Size(self) -> float:
        return self._size

    @Size.setter
    def Size(self, value: float) -> None:
        if self.fail_size:
            raise TextRangeComError("TextRange unexpected error")
        self._size = value


class SequencedInspector:
    def __init__(self, shapes: list[Shape]) -> None:
        self.shapes = shapes
        self.calls = 0

    def _shape_map(self, document):
        index = min(self.calls, len(self.shapes) - 1)
        self.calls += 1
        return {"object_1": self.shapes[index]}, {"object_1": None}


def _runtime() -> tuple[CorelOperatorRuntime, Shape, Document]:
    shape = Shape()
    document = Document(shape)
    runtime = CorelOperatorRuntime(bridge=Bridge(document))  # type: ignore[arg-type]
    runtime.inspector = Inspector(shape)  # type: ignore[assignment]
    return runtime, shape, document


def test_object_transaction_targets_unnamed_shape_by_stable_id() -> None:
    runtime, shape, document = _runtime()
    result = runtime.execute_transaction(
        [
            {
                "op": "typography",
                "shape_name": "synthetic_name_not_used",
                "operator_object_id": "object_1",
                "font_size": 11.0,
            }
        ],
        name="test",
    )
    assert result["status"] == "committed"
    assert shape.Text.Story.Size == 11.0
    assert document.started == document.ended == 1


def test_text_replacement_prefers_object_local_replacewide_and_preserves_font() -> None:
    runtime, shape, document = _runtime()
    shape.Text.Story.Font = "Fixture Font"

    result = runtime.execute_transaction(
        [
            {
                "op": "typography",
                "shape_name": "unused",
                "operator_object_id": "object_1",
                "text": "new",
            }
        ],
        name="replacewide-test",
    )

    assert result["status"] == "committed"
    assert shape.Text.Story.Text == "new"
    assert shape.Text.Story.Font == "Fixture Font"
    assert shape.Text.Story.replace_wide_args == ("new", 0, -1, "Fixture Font")
    assert document.undo_count == 0


def test_object_transaction_rolls_back_when_later_id_is_missing() -> None:
    runtime, shape, document = _runtime()
    with pytest.raises(DesignTransactionError) as raised:
        runtime.execute_transaction(
            [
                {
                    "op": "typography",
                    "shape_name": "unused",
                    "operator_object_id": "object_1",
                    "font_size": 11.0,
                },
                {
                    "op": "typography",
                    "shape_name": "unused",
                    "operator_object_id": "missing",
                    "font_size": 12.0,
                },
            ],
            name="test",
        )
    assert raised.value.report["rolled_back"] is True
    assert shape.Text.Story.Size == 10.0
    assert document.undo_count == 1


def test_textrange_retry_reacquires_live_shape_once() -> None:
    stale = Shape()
    stale.Text.Story = FlakyStory(fail_size=True)
    live = Shape()
    live.Text.Story = FlakyStory(fail_size=False)
    document = Document(live)
    runtime = CorelOperatorRuntime(bridge=Bridge(document))  # type: ignore[arg-type]
    # First map is the transaction lookup, second is attempt 1, third is the
    # bounded retry that must reacquire a fresh COM shape.
    runtime.inspector = SequencedInspector([stale, stale, live])  # type: ignore[assignment]

    result = runtime.execute_transaction(
        [
            {
                "op": "typography",
                "shape_name": "unused",
                "operator_object_id": "object_1",
                "font_size": 11.0,
            }
        ],
        name="retry-test",
    )

    assert result["results"][0]["retry_count"] == 1
    assert live.Text.Story.Size == 11.0
    assert document.undo_count == 0


def test_non_retryable_typography_error_rolls_back_without_second_attempt() -> None:
    shape = Shape()

    class BrokenText:
        @property
        def Story(self):
            raise ValueError("not a text object")

    shape.Text = BrokenText()
    document = Document(Shape())
    runtime = CorelOperatorRuntime(bridge=Bridge(document))  # type: ignore[arg-type]
    inspector = SequencedInspector([shape, shape])
    runtime.inspector = inspector  # type: ignore[assignment]
    with pytest.raises(DesignTransactionError):
        runtime.execute_transaction(
            [
                {
                    "op": "typography",
                    "shape_name": "unused",
                    "operator_object_id": "object_1",
                    "font_size": 11.0,
                }
            ],
            name="no-retry-test",
        )
    assert inspector.calls == 2
    assert document.undo_count == 1


def test_ambiguous_working_copy_shapes_receive_stable_unique_names() -> None:
    one = Shape()
    two = Shape()
    one.Name = two.Name = "duplicate"
    document = Document(one)
    runtime = CorelOperatorRuntime(bridge=Bridge(document))  # type: ignore[arg-type]

    class DuplicateInspector:
        def _shape_map(self, document):
            return {"duplicate": one, "duplicate_2": two}, {
                "duplicate": None,
                "duplicate_2": None,
            }

    runtime.inspector = DuplicateInspector()  # type: ignore[assignment]
    aliases = runtime.ensure_stable_object_ids(["duplicate", "duplicate_2"])
    assert aliases == {
        "duplicate": "codex_operator_000001",
        "duplicate_2": "codex_operator_000002",
    }
    assert one.Name != two.Name


def test_stable_naming_does_not_touch_unrequested_ambiguous_shapes() -> None:
    requested = Shape()
    unrelated = Shape()
    requested.Name = unrelated.Name = "duplicate"
    document = Document(requested)
    runtime = CorelOperatorRuntime(bridge=Bridge(document))  # type: ignore[arg-type]

    class DuplicateInspector:
        def _shape_map(self, document):
            return {"duplicate": requested, "duplicate_2": unrelated}, {
                "duplicate": None,
                "duplicate_2": None,
            }

    runtime.inspector = DuplicateInspector()  # type: ignore[assignment]
    aliases = runtime.ensure_stable_object_ids(["duplicate"])
    assert aliases == {"duplicate": "codex_operator_000001"}
    assert unrelated.Name == "duplicate"


class _FakeColor:
    def __init__(self) -> None:
        self.rgb = (10, 20, 30)

    def RGBAssign(self, red: int, green: int, blue: int) -> None:
        self.rgb = (red, green, blue)


class _FakePage:
    def __init__(self) -> None:
        self.SizeWidth = 100.0
        self.SizeHeight = 50.0
        self.LeftX = 0.0
        self.BottomY = 0.0
        self.BoundingBox = object()
        self.Background = 0
        self.PrintExportBackground = False
        self.Color = _FakeColor()


class _FakeExportOptions:
    pass


class _FakeExportFilter:
    def Finish(self) -> None:
        return None


class _CanonicalApplication:
    def CreateStructExportOptions(self):
        return _FakeExportOptions()

    def CreateStructPaletteOptions(self):
        return object()


class _CanonicalDocument:
    Unit = 3

    def __init__(self, *, reject_explicit_area: bool) -> None:
        self.ActivePage = _FakePage()
        self.reject_explicit_area = reject_explicit_area
        self.export_calls = 0
        self.undo_count = 0
        self._page_before: tuple[int, bool, tuple[int, int, int]] | None = None

    def ExportEx(self, path, _format, _range, options, _palette):
        self.export_calls += 1
        if self.reject_explicit_area and hasattr(options, "ExportArea"):
            raise RuntimeError("legacy CDR rejects explicit ExportArea")
        Image.new("RGB", (options.SizeX, options.SizeY), "white").save(path)
        return _FakeExportFilter()

    def BeginCommandGroup(self, _name: str) -> None:
        page = self.ActivePage
        self._page_before = (
            page.Background,
            page.PrintExportBackground,
            page.Color.rgb,
        )

    def EndCommandGroup(self) -> None:
        return None

    def Undo(self) -> None:
        assert self._page_before is not None
        page = self.ActivePage
        page.Background, page.PrintExportBackground, page.Color.rgb = self._page_before
        self.undo_count += 1


class _CanonicalBridge:
    def __init__(self, document: _CanonicalDocument) -> None:
        self.application = _CanonicalApplication()
        self.document = document

    @contextmanager
    def session(self):
        yield self.application, self.document


def test_canonical_export_prefers_explicit_page_bounding_box(tmp_path: Path) -> None:
    document = _CanonicalDocument(reject_explicit_area=False)
    runtime = CorelOperatorRuntime(bridge=_CanonicalBridge(document))  # type: ignore[arg-type]

    evidence = runtime.export_canonical_png(
        tmp_path / "canonical.png",
        dpi=100,
        max_dimension=1000,
        max_pixels=1_000_000,
    )

    assert evidence.export_area == "page_bounding_box"
    assert document.export_calls == 1
    assert document.undo_count == 0


def test_canonical_export_rejects_content_bound_legacy_fallback(tmp_path: Path) -> None:
    document = _CanonicalDocument(reject_explicit_area=True)
    original = (
        document.ActivePage.Background,
        document.ActivePage.PrintExportBackground,
        document.ActivePage.Color.rgb,
    )
    runtime = CorelOperatorRuntime(bridge=_CanonicalBridge(document))  # type: ignore[arg-type]

    with pytest.raises(CanonicalExportError):
        runtime.export_canonical_png(
            tmp_path / "canonical.png",
            dpi=100,
            max_dimension=1000,
            max_pixels=1_000_000,
        )

    assert document.export_calls == 1
    assert document.undo_count == 0
    assert (
        document.ActivePage.Background,
        document.ActivePage.PrintExportBackground,
        document.ActivePage.Color.rgb,
    ) == original
