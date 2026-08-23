from training.company_archive.models import CdrInspectionV1, CdrObjectV1
from training.tools.diagnose_corel_final_gate_targets import (
    classify_text_target_refusal,
)


def _inspection(*objects: CdrObjectV1) -> CdrInspectionV1:
    return CdrInspectionV1(
        source_path="fixture.cdr",
        source_size_bytes=1,
        source_mtime_ns=1,
        corel_version="fixture",
        page_count=1,
        page_width=100,
        page_height=100,
        unit="mm",
        corel_unit_code=3,
        layer_count=1,
        object_count=len(objects),
        text_object_count=sum(item.object_type == "text" for item in objects),
        bitmap_count=0,
        vector_count=0,
        group_count=0,
        objects=list(objects),
    )


def _text(*, size: float = 12.0, family: str | None = "Arial") -> CdrObjectV1:
    return CdrObjectV1(
        object_id="text_1",
        corel_name="Text",
        object_type="text",
        bbox={"x": 1.0, "y": 1.0, "width": 20.0, "height": 5.0},
        bbox_norm={"x": 0.01, "y": 0.01, "width": 0.2, "height": 0.05},
        text="Benchmark headline",
        font_family=family,
        font_size=size,
        metadata={"locked": False, "bbox_clipped_to_page": False},
    )


def test_text_target_diagnosis_separates_missing_and_strict_size() -> None:
    missing_reason, missing_metrics = classify_text_target_refusal(_inspection())
    strict_reason, strict_metrics = classify_text_target_refusal(
        _inspection(_text(size=56.74))
    )

    assert missing_reason == "TARGET_NOT_FOUND"
    assert missing_metrics["stable_text"] == 0
    assert strict_reason == "SELECTOR_TOO_STRICT"
    assert strict_metrics["font_size_above_36"] == 1
    assert strict_metrics["font_size_max"] == 56.74


def test_text_target_diagnosis_preserves_mixed_font_refusal() -> None:
    reason, metrics = classify_text_target_refusal(_inspection(_text(family=None)))

    assert reason == "MIXED_FONT"
    assert metrics["stable_font_text"] == 0
