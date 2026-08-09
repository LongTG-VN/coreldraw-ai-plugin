"""Reload and run a trained Qwen3 structured-planner adapter."""

from __future__ import annotations

import json
import hashlib
import math
import re
from pathlib import Path
from typing import Any

from training.adapters.qwen3_sft import SYSTEM_PROMPT
from training.schemas.design import (
    BoundingBox,
    CanvasSpec,
    ColorSpec,
    DesignDocument,
    DesignElement,
    SourceSpec,
    TextSpec,
    VisualSpec,
    normalize_bbox,
)


class ModelOutputError(ValueError):
    """Raised when raw model text cannot produce a valid unified design."""

    def __init__(self, message: str, *, raw_output: str | None = None) -> None:
        super().__init__(message)
        self.raw_output = raw_output


_NAMED_COLORS = {
    "black": "#000000",
    "white": "#FFFFFF",
    "gold": "#C49A2C",
    "cream": "#FFF4D6",
    "yellow": "#FFD700",
}


def _finite_positive(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) and number > 0 else fallback


def _color(value: Any) -> ColorSpec:
    text = str(value or "black").strip()
    resolved = _NAMED_COLORS.get(text.casefold(), text)
    if not resolved.startswith("#"):
        resolved = "#000000"
    try:
        return ColorSpec(model="hex", values=[resolved])
    except ValueError:
        return ColorSpec(model="hex", values=["#000000"])


def _recover_shorthand(payload: Any, raw_output: str) -> DesignDocument:
    """Normalize the observed Qwen shorthand without trusting remote assets."""

    if not isinstance(payload, dict):
        raise ModelOutputError("model JSON root must be an object", raw_output=raw_output)
    raw_canvas = payload.get("canvas")
    raw_elements = payload.get("elements")
    if not isinstance(raw_canvas, dict) or not isinstance(raw_elements, list):
        raise ModelOutputError(
            "schema recovery requires canvas and elements",
            raw_output=raw_output,
        )
    width = _finite_positive(raw_canvas.get("width"), 1000.0)
    height = _finite_positive(raw_canvas.get("height"), 1000.0)
    unit = raw_canvas.get("unit", "px")
    if unit not in {"px", "mm", "in", "pt"}:
        unit = "px"
    canvas = CanvasSpec(width=width, height=height, unit=unit)
    background_bbox = BoundingBox(x=0, y=0, width=width, height=height)
    elements = [
        DesignElement(
            id="background",
            name="Background",
            type="rectangle",
            bbox=background_bbox,
            bbox_norm=normalize_bbox(background_bbox, canvas),
            z_index=0,
            layer="background",
            visual=VisualSpec(fill=ColorSpec(model="hex", values=["#FFF4D6"])),
        )
    ]
    for index, raw_element in enumerate(raw_elements[:20], start=1):
        if not isinstance(raw_element, dict):
            continue
        element_type = str(raw_element.get("type", "rectangle")).casefold()
        position = raw_element.get("position")
        position = position if isinstance(position, dict) else {}
        x = max(0.0, min(float(position.get("x", width * 0.1)), width - 1))
        y = max(0.0, min(float(position.get("y", height * 0.1)), height - 1))
        size = raw_element.get("size")
        if isinstance(size, dict):
            box_width = _finite_positive(size.get("width"), width * 0.5)
            box_height = _finite_positive(size.get("height"), height * 0.2)
        else:
            box_width = width * 0.8
            box_height = max(_finite_positive(size, height * 0.08) * 1.8, height * 0.08)
        box_width = max(1.0, min(box_width, width - x))
        box_height = max(1.0, min(box_height, height - y))
        bbox = BoundingBox(x=x, y=y, width=box_width, height=box_height)
        fill = _color(raw_element.get("color"))
        identifier = f"content_{index}"
        if element_type == "text":
            content = str(raw_element.get("text", "")).strip() or f"Text {index}"
            font_size = _finite_positive(size, min(width, height) * 0.05)
            element = DesignElement(
                id=identifier,
                name=f"Text {index}",
                type="text",
                bbox=bbox,
                bbox_norm=normalize_bbox(bbox, canvas),
                rotation=float(raw_element.get("rotation", 0) or 0),
                z_index=index,
                layer="content",
                text=TextSpec(
                    content=content,
                    font_family=str(raw_element.get("font", "Arial")),
                    font_size=font_size,
                    alignment="left",
                ),
                visual=VisualSpec(fill=fill),
            )
        else:
            element = DesignElement(
                id=identifier,
                name=f"Placeholder {index}",
                type="rectangle",
                bbox=bbox,
                bbox_norm=normalize_bbox(bbox, canvas),
                rotation=float(raw_element.get("rotation", 0) or 0),
                z_index=index,
                layer="content",
                visual=VisualSpec(fill=fill),
                metadata={"recovered_from_type": element_type},
            )
        elements.append(element)
    if len(elements) == 1:
        raise ModelOutputError(
            "schema recovery found no usable elements",
            raw_output=raw_output,
        )
    digest = hashlib.sha256(raw_output.encode("utf-8")).hexdigest()[:16]
    return DesignDocument(
        sample_id=f"qwen3-inference:{digest}",
        source=SourceSpec(
            name="qwen3_1_7b_genposter_research",
            split="inference",
            license_class="research_only",
            upstream_id=digest,
            commercial_allowed=False,
        ),
        canvas=canvas,
        category=str(payload.get("category") or "poster"),
        elements=elements,
        metadata={
            "schema_recovery": "qwen_shorthand_v0.1",
            "raw_schema_valid": False,
        },
    )


def planner_messages(
    prompt: str,
    width_mm: float,
    height_mm: float,
) -> list[dict[str, str]]:
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("prompt cannot be empty")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Create an editable poster layout at {width_mm:g} x "
                f"{height_mm:g} mm. User request: {prompt}"
            ),
        },
    ]


def parse_design_output(raw_output: str) -> tuple[DesignDocument, dict[str, Any]]:
    """Extract one JSON object and strictly validate it; never repair fields."""

    text = raw_output.strip()
    recovery_steps: list[str] = []
    without_thinking = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if without_thinking != text:
        text = without_thinking
        recovery_steps.append("removed_thinking_block")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1)
        text = re.sub(r"\s*```$", "", text, count=1)
        recovery_steps.append("removed_markdown_fence")
    start = text.find("{")
    if start < 0:
        raise ModelOutputError("model output contains no JSON object")
    if start > 0:
        recovery_steps.append("discarded_prefix_text")
    try:
        payload, end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise ModelOutputError(f"invalid model JSON: {exc}") from exc
    suffix = text[start + end :].strip()
    if suffix:
        recovery_steps.append("discarded_suffix_text")
    try:
        document = DesignDocument.model_validate(payload)
        raw_schema_valid = True
    except Exception:
        document = _recover_shorthand(payload, raw_output)
        raw_schema_valid = False
        recovery_steps.append("normalized_qwen_shorthand_to_unified_schema")
    return document, {
        "strict_schema_valid": True,
        "raw_schema_valid": raw_schema_valid,
        "recovery_steps": recovery_steps,
    }


def generate_with_checkpoint(
    *,
    checkpoint: Path,
    model_id: str,
    model_revision: str,
    prompt: str,
    width_mm: float,
    height_mm: float,
    max_new_tokens: int,
) -> tuple[DesignDocument, str, dict[str, Any]]:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    )
    base_model = AutoModelForCausalLM.from_pretrained(
        model_id,
        revision=model_revision,
        quantization_config=quantization_config,
        device_map={"": 0},
        dtype=torch.float16,
        attn_implementation="sdpa",
    )
    model = PeftModel.from_pretrained(base_model, checkpoint)
    model.eval()
    messages = planner_messages(prompt, width_mm, height_mm)
    rendered = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    rendered += "{"
    inputs = tokenizer(rendered, return_tensors="pt").to("cuda")
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.pad_token_id,
            use_cache=True,
        )
    generated = tokenizer.decode(
        output[0, inputs["input_ids"].shape[1] :],
        skip_special_tokens=True,
    )
    raw_output = "{" + generated
    document, parse_metadata = parse_design_output(raw_output)
    document.metadata.update(
        {
            "trained_model": True,
            "generator": "qwen3_1_7b_local_qlora_v0.1",
            "base_model": model_id,
            "base_model_revision": model_revision,
            "adapter_checkpoint": str(checkpoint.resolve()),
            "inference_prompt": prompt,
        }
    )
    document = DesignDocument.model_validate(document.model_dump())
    return document, raw_output, parse_metadata
