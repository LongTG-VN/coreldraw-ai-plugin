from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from training.adapters.genposter import GenPosterAdapter
from training.datasets.builder import materialize_dataset
from training.datasets.splitter import deterministic_split
from training.datasets.validator import validate_dataset_directory, validate_record
from training.schemas.design import DesignDocument


def _valid_payload() -> dict[str, Any]:
    return {
        "sample_id": "synthetic:1",
        "source": {
            "name": "synthetic_owned",
            "split": "train",
            "license_class": "production_safe",
            "upstream_id": "1",
            "commercial_allowed": True,
        },
        "canvas": {"width": 1000, "height": 500, "unit": "px"},
        "category": "poster",
        "assets": [
            {
                "id": "hero_asset",
                "source": "assets/hero.png",
                "type": "bitmap",
            }
        ],
        "elements": [
            {
                "id": "group_1",
                "name": "Header",
                "type": "group",
                "bbox": {"x": 100, "y": 50, "width": 800, "height": 200},
                "bbox_norm": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.4},
                "z_index": 1,
            },
            {
                "id": "headline",
                "name": "Headline",
                "type": "text",
                "bbox": {"x": 200, "y": 100, "width": 600, "height": 100},
                "bbox_norm": {"x": 0.2, "y": 0.2, "width": 0.6, "height": 0.2},
                "parent_id": "group_1",
                "z_index": 2,
                "text": {
                    "content": "OPENING SOON",
                    "font_family": "Arial",
                    "font_size": 72,
                    "font_weight": 700,
                    "alignment": "center",
                    "line_height": 1.2,
                    "tracking": 0,
                },
                "visual": {
                    "fill": {"model": "cmyk", "values": [0, 0, 0, 100]},
                    "opacity": 1,
                },
            },
            {
                "id": "hero",
                "name": "Hero image",
                "type": "image",
                "bbox": {"x": 0, "y": 300, "width": 1000, "height": 200},
                "bbox_norm": {"x": 0, "y": 0.6, "width": 1, "height": 0.4},
                "asset_ref": "hero_asset",
            },
        ],
    }


def test_unified_schema_accepts_structured_editable_design() -> None:
    document = DesignDocument.model_validate(_valid_payload())

    assert document.canvas.width == 1000
    assert document.elements[1].text is not None
    assert document.elements[1].text.font_weight == 700
    assert document.elements[2].asset_ref == "hero_asset"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: value["elements"][0]["bbox"].update({"width": -1}),
            "greater than 0",
        ),
        (
            lambda value: value["elements"][0]["bbox"].update({"x": math.nan}),
            "finite number",
        ),
        (
            lambda value: value["elements"][1].update({"id": "group_1"}),
            "duplicate element IDs",
        ),
        (
            lambda value: value["elements"][1].update({"parent_id": "missing"}),
            "references missing parent",
        ),
        (
            lambda value: value["elements"][2].update({"asset_ref": "missing"}),
            "references missing asset",
        ),
        (
            lambda value: value["elements"][2]["bbox_norm"].update({"width": 0.5}),
            "absolute and normalized bbox disagree",
        ),
    ],
)
def test_unified_schema_rejects_invalid_designs(mutate, message: str) -> None:
    payload = copy.deepcopy(_valid_payload())
    mutate(payload)

    with pytest.raises(ValidationError, match=message):
        DesignDocument.model_validate(payload)


def test_validator_returns_stable_issue_locations() -> None:
    payload = _valid_payload()
    payload["elements"][1]["text"]["font_size"] = 0

    document, issues = validate_record(payload)

    assert document is None
    assert issues[0].location == "elements.1.text.font_size"


def test_deterministic_split_is_reproducible_and_seeded() -> None:
    first = [deterministic_split(f"sample:{index}", seed=42) for index in range(100)]
    reordered = {
        sample_id: deterministic_split(sample_id, seed=42)
        for sample_id in reversed([f"sample:{index}" for index in range(100)])
    }
    second_seed = [
        deterministic_split(f"sample:{index}", seed=43) for index in range(100)
    ]

    assert first == [reordered[f"sample:{index}"] for index in range(100)]
    assert first != second_seed
    assert {"train", "validation", "test"}.issubset(set(first))


def test_genposter_adapter_maps_parallel_columns_and_xyxy_bbox() -> None:
    row = {
        "id": 7,
        "psd_path": "meta_psd/7.psd",
        "regions": [],
        "layers": {
            "layer_name": ["Headline", "Logo"],
            "text": ["OPENING SOON", ""],
            "bbox": [[100, 50, 900, 150], [20, 300, 220, 480]],
            "angle": [0, 5],
            "psd_size": [[1000, 500], [1000, 500]],
            "stroke_width": [0.0, 1.0],
            "font": ["Montserrat", ""],
            "font_size": [72.0, 0.0],
            "tracking": [1.5, 0.0],
            "justification": [2, 0],
            "fill_color": [[0, 0, 0, 255], [255, 0, 0, 128]],
            "layer_image": [object(), object()],
            "layer_image_relpath": ["", "layers/logo.png"],
            "label": [11, 7],
        },
    }

    document = GenPosterAdapter().convert(row, 0)

    headline, logo = document.elements
    assert headline.type == "text"
    assert headline.bbox.width == 800
    assert headline.bbox_norm.width == pytest.approx(0.8)
    assert headline.metadata["label_name"] == "Title"
    assert headline.visual.fill is not None
    assert headline.visual.fill.values[3] == pytest.approx(1)
    assert logo.type == "image"
    assert logo.asset_ref == "asset_0001"
    assert document.assets[0].source == "layers/logo.png"


def test_genposter_adapter_records_and_drops_zero_area_layers() -> None:
    row = {
        "id": 17,
        "layers": {
            "layer_name": ["Valid", "Zero"],
            "text": ["TITLE", ""],
            "bbox": [[0, 0, 100, 50], [0, 0, 0, 0]],
            "angle": [0, 0],
            "psd_size": [[200, 100], [200, 100]],
            "fill_color": [[0.1, 0.2, 0.3, 1], [0, 0, 0, 1]],
        },
    }

    document = GenPosterAdapter().convert(row, 17)

    assert len(document.elements) == 1
    assert document.elements[0].visual.fill is not None
    assert document.elements[0].visual.fill.values[:3] == pytest.approx(
        [25.5, 51, 76.5]
    )
    assert document.metadata["normalization_warnings"] == [
        {
            "layer_index": 1,
            "reason": "zero_area_bbox",
            "bbox": [0, 0, 0, 0],
            "layer_name": "Zero",
        }
    ]


def test_materialize_dataset_writes_reproducible_splits_and_metadata(
    tmp_path: Path,
) -> None:
    class SyntheticAdapter:
        def convert(self, row: dict[str, Any], index: int) -> DesignDocument:
            payload = _valid_payload()
            payload["sample_id"] = f"synthetic:{row['id']}"
            payload["source"]["upstream_id"] = str(row["id"])
            return DesignDocument.model_validate(payload)

    output = tmp_path / "smoke"
    result = materialize_dataset(
        ({"id": index} for index in range(30)),
        SyntheticAdapter(),
        output,
        limit=30,
        seed=123,
    )

    assert result.total == 30
    assert sum(result.split_counts.values()) == 30
    assert all((output / f"{split}.jsonl").is_file() for split in result.split_counts)
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["seed"] == 123
    assert metadata["license_class"] == "production_safe"
    validation = validate_dataset_directory(output)
    assert validation["status"] == "valid"
    assert validation["total"] == 30
