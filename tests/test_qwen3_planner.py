from __future__ import annotations

import json

import pytest

from training.adapters.qwen3_sft import Qwen3SFTAdapter
from training.experiments.qwen3_local import chat_token_ids, prepare_examples
from training.inference.qwen3_planner import ModelOutputError, parse_design_output
from training.schemas.design import (
    AssetSpec,
    BoundingBox,
    CanvasSpec,
    DesignDocument,
    DesignElement,
    SourceSpec,
    TextSpec,
    VisualSpec,
    normalize_bbox,
)


def _document() -> DesignDocument:
    canvas = CanvasSpec(width=1000, height=500, unit="px")
    text_bbox = BoundingBox(x=100, y=50, width=800, height=100)
    image_bbox = BoundingBox(x=200, y=200, width=600, height=250)
    return DesignDocument(
        sample_id="genposter100k:test",
        source=SourceSpec(
            name="genposter100k",
            split="train",
            license_class="research_only",
            upstream_id="test",
            commercial_allowed=False,
        ),
        canvas=canvas,
        category="poster",
        elements=[
            DesignElement(
                id="title",
                name="Title",
                type="text",
                bbox=text_bbox,
                bbox_norm=normalize_bbox(text_bbox, canvas),
                text=TextSpec(content="SUMMER SALE", font_size=48),
                visual=VisualSpec(),
            ),
            DesignElement(
                id="photo",
                name="Photo",
                type="image",
                bbox=image_bbox,
                bbox_norm=normalize_bbox(image_bbox, canvas),
                asset_ref="photo_asset",
                visual=VisualSpec(),
            ),
        ],
        assets=[
            AssetSpec(
                id="photo_asset",
                source="dataset://photo",
                type="bitmap",
            )
        ],
    )


def test_qwen3_adapter_produces_compact_corel_safe_target() -> None:
    record = Qwen3SFTAdapter(max_elements=4).convert(_document())

    payload = json.loads(record.completion[0]["content"])
    projected = DesignDocument.model_validate(payload)

    assert record.commercial_allowed is False
    assert len(projected.elements) == 3
    assert projected.assets == []
    assert {element.type for element in projected.elements} == {"rectangle", "text"}
    assert record.prompt[0]["role"] == "system"
    assert "SUMMER SALE" in record.prompt[1]["content"]


def test_parse_design_output_validates_and_reports_fence_recovery() -> None:
    target = Qwen3SFTAdapter().convert(_document()).completion[0]["content"]

    document, metadata = parse_design_output(f"```json\n{target}\n```")

    assert document.sample_id == "genposter100k:test"
    assert metadata["strict_schema_valid"] is True
    assert metadata["recovery_steps"] == ["removed_markdown_fence"]


def test_parse_design_output_rejects_invalid_schema() -> None:
    with pytest.raises(ModelOutputError, match="schema recovery requires"):
        parse_design_output('{"schema_version":"0.1"}')


def test_parse_design_output_recovers_observed_shorthand_explicitly() -> None:
    raw = json.dumps(
        {
            "schema_version": 0.1,
            "canvas": {"width": 1000, "height": 500, "unit": "px"},
            "elements": [
                {
                    "type": "text",
                    "text": "SPA",
                    "position": {"x": 100, "y": 50},
                    "size": 48,
                    "color": "gold",
                },
                {
                    "type": "image",
                    "image": "https://invalid.example/image.png",
                    "position": {"x": 200, "y": 200},
                    "size": {"width": 600, "height": 200},
                },
            ],
        }
    )

    document, metadata = parse_design_output(raw)

    assert metadata["raw_schema_valid"] is False
    assert metadata["strict_schema_valid"] is True
    assert metadata["recovery_steps"] == [
        "normalized_qwen_shorthand_to_unified_schema"
    ]
    assert document.source.commercial_allowed is False
    assert [element.type for element in document.elements] == [
        "rectangle",
        "text",
        "rectangle",
    ]


class _FakeTokenizer:
    def apply_chat_template(self, messages, **kwargs):  # type: ignore[no-untyped-def]
        if kwargs["add_generation_prompt"]:
            return [1, 2, 3]
        return [1, 2, 3, 4, 5]


def test_sft_labels_mask_prompt_and_length_filter_is_explicit() -> None:
    record = Qwen3SFTAdapter().convert(_document()).to_dict()
    input_ids, labels = chat_token_ids(_FakeTokenizer(), record)
    examples, rejected = prepare_examples(
        _FakeTokenizer(), [record], max_sequence_length=4
    )

    assert input_ids == [1, 2, 3, 4, 5]
    assert labels == [-100, -100, -100, 4, 5]
    assert examples == []
    assert rejected == [
        {
            "sample_id": "genposter100k:test",
            "tokens": 5,
            "reason": "over_max_sequence_length",
        }
    ]
