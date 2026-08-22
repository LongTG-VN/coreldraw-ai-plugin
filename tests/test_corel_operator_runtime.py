from __future__ import annotations

from contextlib import contextmanager

import pytest

from training.corel_operator.runtime import CorelOperatorRuntime
from transaction_engine import DesignTransactionError


class Story:
    def __init__(self) -> None:
        self.Text = "old"
        self.Font = "Arial"
        self.Size = 10.0


class Text:
    def __init__(self) -> None:
        self.Story = Story()


class Shape:
    def __init__(self) -> None:
        self.Text = Text()
        self.SizeWidth = 10.0
        self.SizeHeight = 2.0
        self.PositionX = 1.0
        self.PositionY = 1.0
        self.RotationAngle = 0.0


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
