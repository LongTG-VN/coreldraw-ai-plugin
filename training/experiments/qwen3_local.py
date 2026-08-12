"""Minimal QLoRA training primitives for Design AI v0.1."""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def chat_token_ids(
    tokenizer: Any,
    record: dict[str, Any],
) -> tuple[list[int], list[int]]:
    def extract_ids(value: Any) -> list[int]:
        if isinstance(value, dict) or hasattr(value, "keys"):
            value = value["input_ids"]
        if value and isinstance(value[0], list):
            value = value[0]
        return list(value)

    prompt = record["prompt"]
    completion = record["completion"]
    prompt_ids = tokenizer.apply_chat_template(
        prompt,
        tokenize=True,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    full_ids = tokenizer.apply_chat_template(
        [*prompt, *completion],
        tokenize=True,
        add_generation_prompt=False,
        enable_thinking=False,
    )
    prompt_ids = extract_ids(prompt_ids)
    full_ids = extract_ids(full_ids)
    common_prefix = 0
    for prompt_token, full_token in zip(prompt_ids, full_ids):
        if prompt_token != full_token:
            break
        common_prefix += 1
    if common_prefix < max(1, len(prompt_ids) - 2):
        raise ValueError("Qwen chat prompt is not a prefix of the full SFT sample")
    return list(full_ids), [-100] * common_prefix + list(full_ids[common_prefix:])


@dataclass(frozen=True)
class PreparedExample:
    sample_id: str
    input_ids: list[int]
    labels: list[int]


def prepare_examples(
    tokenizer: Any,
    records: list[dict[str, Any]],
    *,
    max_sequence_length: int,
) -> tuple[list[PreparedExample], list[dict[str, Any]]]:
    examples: list[PreparedExample] = []
    rejected: list[dict[str, Any]] = []
    for record in records:
        input_ids, labels = chat_token_ids(tokenizer, record)
        if len(input_ids) > max_sequence_length:
            rejected.append(
                {
                    "sample_id": record["sample_id"],
                    "tokens": len(input_ids),
                    "reason": "over_max_sequence_length",
                }
            )
            continue
        examples.append(
            PreparedExample(
                sample_id=record["sample_id"],
                input_ids=input_ids,
                labels=labels,
            )
        )
    return examples, rejected


def collate_one(example: PreparedExample, *, pad_token_id: int) -> dict[str, Any]:
    import torch

    return {
        "input_ids": torch.tensor([example.input_ids], dtype=torch.long),
        "attention_mask": torch.ones((1, len(example.input_ids)), dtype=torch.long),
        "labels": torch.tensor([example.labels], dtype=torch.long),
    }


def train_qlora(
    *,
    config: dict[str, Any],
    records: list[dict[str, Any]],
    output_dir: Path,
) -> dict[str, Any]:
    """Run real optimizer steps and save a reloadable PEFT checkpoint."""

    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available to PyTorch")
    training = config["training"]
    lora = config["lora"]
    quantization = config["quantization"]
    seed = int(config["seed"])
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cuda.matmul.allow_tf32 = True

    tokenizer = AutoTokenizer.from_pretrained(
        config["model_id"],
        revision=config["model_revision"],
    )
    examples, rejected = prepare_examples(
        tokenizer,
        records,
        max_sequence_length=int(training["max_sequence_length"]),
    )
    if not examples:
        raise RuntimeError("no SFT examples fit the configured sequence length")

    compute_dtype = torch.float16
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=bool(quantization["load_in_4bit"]),
        bnb_4bit_quant_type=quantization["quant_type"],
        bnb_4bit_use_double_quant=bool(quantization["double_quant"]),
        bnb_4bit_compute_dtype=compute_dtype,
    )
    model = AutoModelForCausalLM.from_pretrained(
        config["model_id"],
        revision=config["model_revision"],
        quantization_config=bnb_config,
        device_map={"": 0},
        dtype=compute_dtype,
        attn_implementation="sdpa",
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=bool(training["gradient_checkpointing"]),
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )
    model = get_peft_model(
        model,
        LoraConfig(
            r=int(lora["rank"]),
            lora_alpha=int(lora["alpha"]),
            lora_dropout=float(lora["dropout"]),
            target_modules=list(lora["target_modules"]),
            bias="none",
            task_type="CAUSAL_LM",
        ),
    )
    trainable_parameters, total_parameters = model.get_nb_trainable_parameters()
    parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(
        parameters,
        lr=float(training["learning_rate"]),
    )
    scaler = torch.amp.GradScaler("cuda")
    gradient_accumulation = int(training["gradient_accumulation_steps"])
    max_steps = int(training["max_steps"])
    order = list(range(len(examples)))
    random.Random(seed).shuffle(order)
    cursor = 0
    losses: list[float] = []
    model.train()
    optimizer.zero_grad(set_to_none=True)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    for step in range(max_steps):
        accumulated_loss = 0.0
        for _ in range(gradient_accumulation):
            example = examples[order[cursor % len(order)]]
            cursor += 1
            batch = collate_one(example, pad_token_id=tokenizer.pad_token_id)
            batch = {key: value.to("cuda") for key, value in batch.items()}
            with torch.autocast(device_type="cuda", dtype=compute_dtype):
                loss = model(**batch).loss
                scaled_loss = loss / gradient_accumulation
            scaler.scale(scaled_loss).backward()
            accumulated_loss += float(loss.detach().cpu())
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(parameters, 1.0)
        scaler.step(optimizer)
        scaler.update()
        optimizer.zero_grad(set_to_none=True)
        step_loss = accumulated_loss / gradient_accumulation
        if not math.isfinite(step_loss):
            raise RuntimeError(f"non-finite loss at optimizer step {step + 1}")
        losses.append(step_loss)
        print(json.dumps({"optimizer_step": step + 1, "loss": step_loss}))

    duration_seconds = time.perf_counter() - started
    peak_vram_bytes = int(torch.cuda.max_memory_allocated())
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = output_dir / f"checkpoint-{max_steps}"
    model.save_pretrained(checkpoint_dir, safe_serialization=True)
    tokenizer.save_pretrained(checkpoint_dir)
    metrics = {
        "trained_model": True,
        "optimizer_steps": max_steps,
        "micro_batches": max_steps * gradient_accumulation,
        "batch_size": 1,
        "gradient_accumulation_steps": gradient_accumulation,
        "effective_batch_size": gradient_accumulation,
        "train_loss": losses[-1],
        "mean_train_loss": sum(losses) / len(losses),
        "losses": losses,
        "duration_seconds": duration_seconds,
        "peak_vram_bytes": peak_vram_bytes,
        "peak_vram_gib": peak_vram_bytes / (1024**3),
        "trainable_parameters": trainable_parameters,
        "total_parameters": total_parameters,
        "trainable_parameter_percent": 100 * trainable_parameters / total_parameters,
        "input_records": len(records),
        "training_records": len(examples),
        "rejected_records": rejected,
        "checkpoint": str(checkpoint_dir.resolve()),
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return metrics
