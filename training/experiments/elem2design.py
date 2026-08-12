"""Build a guarded elem2design QLoRA smoke command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_experiment_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_train_command(
    config: dict[str, Any],
    *,
    repo_root: Path,
) -> list[str]:
    model = config["model"]
    lora = config["lora"]
    training = config["training"]
    data = config["data_gate"]
    vendor = repo_root / config["upstream"]["local_path"]
    data_root = repo_root / data["elem2design_adapter"]
    output_dir = repo_root / "training" / "artifacts" / "runs" / config[
        "experiment_id"
    ] / "checkpoints"
    return [
        "python",
        str(vendor / "llava" / "train" / "train_mem.py"),
        "--lora_enable",
        "True",
        "--lora_r",
        str(lora["rank"]),
        "--lora_alpha",
        str(lora["alpha"]),
        "--lora_dropout",
        str(lora["dropout"]),
        "--bits",
        str(model["quantization_bits"]),
        "--double_quant",
        str(model["double_quant"]),
        "--quant_type",
        str(model["quantization_type"]),
        "--model_name_or_path",
        str(model["base_model"]),
        "--version",
        "v1",
        "--data_path",
        str(data_root / "train.json"),
        "--image_folder",
        str(data_root / "images"),
        "--vision_tower",
        str(model["vision_tower"]),
        "--mm_projector_type",
        "mlp2x_gelu",
        "--mm_vision_select_layer",
        "-2",
        "--mm_use_im_start_end",
        "False",
        "--mm_use_im_patch_token",
        "False",
        "--image_aspect_ratio",
        "pad",
        "--bf16",
        "True",
        "--output_dir",
        str(output_dir),
        "--max_steps",
        str(training["max_steps"]),
        "--per_device_train_batch_size",
        str(training["batch_size"]),
        "--gradient_accumulation_steps",
        str(training["gradient_accumulation_steps"]),
        "--learning_rate",
        str(training["learning_rate"]),
        "--model_max_length",
        str(training["max_sequence_length"]),
        "--gradient_checkpointing",
        str(training["gradient_checkpointing"]),
        "--evaluation_strategy",
        "no",
        "--save_strategy",
        "steps",
        "--save_steps",
        str(training["max_steps"]),
        "--logging_steps",
        "1",
        "--dataloader_num_workers",
        "2",
        "--lazy_preprocess",
        "True",
        "--report_to",
        "none",
    ]


def assess_launch(
    config: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    blockers: list[str] = []
    vendor = repo_root / config["upstream"]["local_path"]
    data_root = repo_root / config["data_gate"]["elem2design_adapter"]
    if not (vendor / "llava" / "train" / "train_mem.py").is_file():
        blockers.append("elem2design train entrypoint is missing")
    if not (data_root / "train.json").is_file():
        blockers.append("adapted train.json is missing")
    metadata_path = data_root / "metadata.json"
    if not metadata_path.is_file():
        blockers.append("adapter metadata is missing")
    else:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not metadata.get("training_ready", False):
            blockers.append(str(metadata.get("reason") or "dataset is not training-ready"))
    hardware = config["hardware_gate"]
    if not hardware.get("local_execution_supported", False):
        blockers.append(str(hardware.get("reason") or "hardware gate failed"))
    return {
        "status": "ready" if not blockers else "blocked",
        "executable": not blockers,
        "blockers": blockers,
        "command": build_train_command(config, repo_root=repo_root),
    }
