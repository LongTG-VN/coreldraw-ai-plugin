from __future__ import annotations

import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from training.adapters.base import AdapterError
from training.adapters.elem2design import (
    to_elem2design_sample,
    validate_elem2design_sample,
)
from training.evaluation.layout_metrics import evaluate_layout
from training.experiments.elem2design import assess_launch, build_train_command
from training.inference.baseline import generate_baseline_design
from training.inference.contract import DesignGenerateRequest, DesignGenerateResponse
from training.inference.corel_compiler import (
    CorelCompileError,
    compile_corel_operations,
)
from training.inference.preview import render_preview
from training.schemas.design import DesignDocument


def test_baseline_generates_valid_structured_design_contract() -> None:
    request = DesignGenerateRequest(
        prompt="Thiết kế poster spa cao cấp màu kem và vàng",
        width_mm=4000,
        height_mm=1200,
    )
    document = generate_baseline_design(
        request.prompt,
        request.width_mm,
        request.height_mm,
    )
    response = DesignGenerateResponse(
        design=document,
        assets=document.assets,
        metadata={
            "generator": document.metadata["generator"],
            "trained_model": False,
        },
    )

    assert response.design.canvas.unit == "mm"
    assert response.design.source.commercial_allowed is True
    assert response.design.metadata["trained_model"] is False
    assert {element.id for element in response.design.elements} == {
        "background",
        "headline",
        "subtitle",
    }


def test_corel_compiler_converts_top_left_norm_to_corel_top_y() -> None:
    document = generate_baseline_design("Poster spa màu kem và vàng", 4000, 1200)

    operations = compile_corel_operations(document)

    assert operations[0] == {"op": "page_resize", "width": 4000, "height": 1200}
    background = operations[1]
    headline = operations[2]
    assert background["op"] == "create_rectangle"
    assert background["y"] == 1200
    assert background["height"] == 1200
    assert headline["op"] == "create_text"
    assert headline["name"] == "headline"
    assert headline["x"] == pytest.approx(400)
    assert headline["y"] == pytest.approx(1056)
    assert headline["color"] == {
        "cyan": 0,
        "magenta": 20,
        "yellow": 70,
        "black": 20,
    }


def test_corel_compiler_requires_explicit_mm_size_for_pixel_documents() -> None:
    baseline = generate_baseline_design("Poster", 1000, 500)
    payload = baseline.model_dump()
    payload["canvas"]["unit"] = "px"
    document = DesignDocument.model_validate(payload)

    with pytest.raises(CorelCompileError, match="explicit width_mm"):
        compile_corel_operations(document)

    operations = compile_corel_operations(document, width_mm=100, height_mm=50)
    assert operations[0]["width"] == 100
    assert operations[1]["width"] == 100


def test_corel_compiler_rejects_nonlocal_assets() -> None:
    baseline = generate_baseline_design("Poster", 1000, 500)
    payload = baseline.model_dump()
    payload["assets"] = [
        {
            "id": "hero_asset",
            "source": "dataset://research/hero.png",
            "type": "bitmap",
        }
    ]
    payload["elements"].append(
        {
            "id": "hero",
            "name": "Hero",
            "type": "image",
            "bbox": {"x": 100, "y": 200, "width": 800, "height": 200},
            "bbox_norm": {"x": 0.1, "y": 0.4, "width": 0.8, "height": 0.4},
            "asset_ref": "hero_asset",
            "z_index": 5,
        }
    )
    document = DesignDocument.model_validate(payload)

    with pytest.raises(CorelCompileError, match="existing local file"):
        compile_corel_operations(document)


def test_layout_metrics_are_machine_readable_and_deterministic() -> None:
    document = generate_baseline_design("Poster", 1000, 500)

    first = evaluate_layout(document)
    second = evaluate_layout(copy.deepcopy(document))

    assert first == second
    assert first["bbox_validity"] == 1
    assert first["outside_canvas_rate"] == 0
    assert first["element_count"] == 3
    assert first["content_element_count"] == 2
    assert first["background_element_count"] == 1
    assert first["coverage"] < 1
    assert first["text_hierarchy_ratio"] > 1


def test_elem2design_adapter_builds_exact_five_round_contract() -> None:
    baseline = generate_baseline_design("Poster", 1000, 500)
    payload = baseline.model_dump()
    payload["canvas"]["unit"] = "px"
    document = DesignDocument.model_validate(payload)

    sample = to_elem2design_sample(
        document,
        render_images=["layer_0.png", "layer_1.png", "layer_2.png", "layer_3.png"],
    )
    validate_elem2design_sample(sample)

    assert len(sample["conversations"]) == 10
    assert len(sample["image"]) == 4
    assert sum(
        message["value"].count("<image>")
        for message in sample["conversations"]
    ) == 4
    assert sample["metadata"]["adapter_mode"] == "rendered_multimodal"


def test_elem2design_adapter_marks_layout_only_dry_run() -> None:
    baseline = generate_baseline_design("Poster", 1000, 500)
    payload = baseline.model_dump()
    payload["canvas"]["unit"] = "px"
    document = DesignDocument.model_validate(payload)

    sample = to_elem2design_sample(document)
    validate_elem2design_sample(sample)

    assert sample["image"] == []
    assert sample["metadata"]["adapter_mode"] == "layout_only_dry_run"
    with pytest.raises(AdapterError, match="exactly four"):
        to_elem2design_sample(document, render_images=["only-one.png"])


def test_preview_renderer_writes_png(tmp_path: Path) -> None:
    document = generate_baseline_design("Poster", 1000, 500)

    output = render_preview(document, tmp_path / "preview.png", max_dimension=500)

    assert output.is_file()
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_elem2design_launch_plan_is_guarded_by_data_and_hardware(
    tmp_path: Path,
) -> None:
    vendor_train = tmp_path / "vendor" / "llava" / "train" / "train_mem.py"
    vendor_train.parent.mkdir(parents=True)
    vendor_train.write_text("# fixture\n", encoding="utf-8")
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "train.json").write_text("[]\n", encoding="utf-8")
    (adapter / "metadata.json").write_text(
        '{"training_ready": false, "reason": "missing renders"}\n',
        encoding="utf-8",
    )
    config = {
        "experiment_id": "smoke",
        "upstream": {"local_path": "vendor"},
        "model": {
            "base_model": "base",
            "vision_tower": "vision",
            "quantization_bits": 4,
            "quantization_type": "nf4",
            "double_quant": True,
        },
        "lora": {"rank": 16, "alpha": 32, "dropout": 0.05},
        "training": {
            "max_steps": 10,
            "batch_size": 1,
            "gradient_accumulation_steps": 16,
            "learning_rate": 0.0002,
            "max_sequence_length": 2048,
            "gradient_checkpointing": True,
        },
        "data_gate": {"elem2design_adapter": "adapter"},
        "hardware_gate": {
            "local_execution_supported": False,
            "reason": "6GB VRAM",
        },
    }

    report = assess_launch(config, repo_root=tmp_path)
    command = build_train_command(config, repo_root=tmp_path)

    assert report["status"] == "blocked"
    assert report["executable"] is False
    assert report["blockers"] == ["missing renders", "6GB VRAM"]
    assert "--bits" in command
    assert command[command.index("--bits") + 1] == "4"
    assert command[command.index("--model_max_length") + 1] == "2048"


@pytest.mark.parametrize(
    "endpoint",
    ["/design/generate", "/api/v1/design/generate"],
)
def test_design_generate_endpoint_returns_explicit_baseline_contract(
    endpoint: str,
) -> None:
    response = TestClient(main.app).post(
        endpoint,
        json={
            "prompt": "Thiết kế poster spa cao cấp màu kem và vàng",
            "width_mm": 4000,
            "height_mm": 1200,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["design"]["schema_version"] == "0.1"
    assert payload["design"]["canvas"]["unit"] == "mm"
    assert payload["metadata"]["trained_model"] is False
    assert payload["metadata"]["corel_transaction_endpoint"] == (
        "/api/v1/design/transaction"
    )
