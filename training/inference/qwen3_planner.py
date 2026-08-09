"""Reload and run a trained Qwen3 structured-planner adapter."""

from __future__ import annotations

import json
import hashlib
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

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


@dataclass(frozen=True)
class RawPlannerGeneration:
    raw_output: str
    duration_seconds: float
    seed: int
    generation_config: dict[str, Any]
    peak_vram_gib: float


def _finite_positive(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) and number > 0 else fallback


def _finite_number(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


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
    recovered_payload = payload
    wrappers = ("design_document", "design", "layout")
    for wrapper in wrappers:
        nested = recovered_payload.get(wrapper)
        if isinstance(nested, dict):
            recovered_payload = nested
            break
    raw_canvas = recovered_payload.get("canvas")
    if not isinstance(raw_canvas, dict):
        raw_canvas = recovered_payload.get("canvas_size")
    if isinstance(raw_canvas, (list, tuple)) and len(raw_canvas) == 2:
        raw_canvas = {"width": raw_canvas[0], "height": raw_canvas[1]}
    if not isinstance(raw_canvas, dict) and {
        "width",
        "height",
    } <= recovered_payload.keys():
        raw_canvas = {
            "width": recovered_payload["width"],
            "height": recovered_payload["height"],
        }
    raw_elements = recovered_payload.get("elements")
    if isinstance(raw_elements, dict):
        normalized_elements = []
        for name, value in raw_elements.items():
            if not isinstance(value, dict):
                continue
            normalized = {**value, "name": value.get("name", name)}
            normalized.setdefault(
                "type",
                "text" if "text" in normalized else "rectangle",
            )
            normalized_elements.append(normalized)
        raw_elements = normalized_elements
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
        if isinstance(position, (list, tuple)) and len(position) >= 2:
            position = {"x": position[0], "y": position[1]}
        position = position if isinstance(position, dict) else {}
        x = max(
            0.0,
            min(_finite_number(position.get("x"), width * 0.1), width - 1),
        )
        y = max(
            0.0,
            min(_finite_number(position.get("y"), height * 0.1), height - 1),
        )
        size = raw_element.get("size")
        if isinstance(size, (list, tuple)) and len(size) >= 2:
            size = {"width": size[0], "height": size[1]}
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
            font_size = _finite_positive(
                raw_element.get("font_size", size),
                min(width, height) * 0.05,
            )
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
                    font_family=str(
                        raw_element.get("font_family")
                        or raw_element.get("font")
                        or "Arial"
                    ),
                    font_size=font_size,
                    alignment="left",
                ),
                visual=VisualSpec(fill=fill),
            )
        else:
            remote_source = str(
                raw_element.get("image")
                or raw_element.get("image_url")
                or raw_element.get("url")
                or ""
            )
            parsed_source = urlparse(remote_source)
            query = str(raw_element.get("query", "")).strip()
            if not query and parsed_source.query:
                query = parse_qs(parsed_source.query).get("text", [""])[0]
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
                metadata={
                    "recovered_from_type": element_type,
                    "asset_intent": {
                        "role": str(raw_element.get("role", "hero")),
                        "query": query or "design-relevant placeholder",
                        "placeholder": True,
                        "remote_source_rejected": bool(parsed_source.scheme),
                    },
                },
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
        category=str(recovered_payload.get("category") or "poster"),
        elements=elements,
        metadata={
            "schema_recovery": "qwen_shorthand_v0.1",
            "schema_wrapper": (
                next(
                    (
                        wrapper
                        for wrapper in wrappers
                        if isinstance(payload.get(wrapper), dict)
                    ),
                    None,
                )
            ),
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
    """Strictly validate unified JSON or explicitly normalize known shorthand."""

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
        raise ModelOutputError(
            "model output contains no JSON object",
            raw_output=raw_output,
        )
    if start > 0:
        recovery_steps.append("discarded_prefix_text")
    try:
        payload, end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        try:
            document = _recover_truncated_element_prefix(text[start:], raw_output)
        except ModelOutputError:
            raise ModelOutputError(
                f"invalid model JSON: {exc}",
                raw_output=raw_output,
            ) from exc
        return document, {
            "strict_schema_valid": True,
            "raw_schema_valid": False,
            "recovery_steps": ["recovered_truncated_element_prefix"],
        }
    suffix = text[start + end :].strip()
    if suffix:
        recovery_steps.append("discarded_suffix_text")
    try:
        document = DesignDocument.model_validate(payload)
        raw_schema_valid = True
    except Exception:
        try:
            document = _recover_shorthand(payload, raw_output)
        except ModelOutputError:
            raise
        except Exception as exc:
            raise ModelOutputError(
                f"schema recovery failed: {exc}",
                raw_output=raw_output,
            ) from exc
        raw_schema_valid = False
        recovery_steps.append("normalized_qwen_shorthand_to_unified_schema")
    return document, {
        "strict_schema_valid": True,
        "raw_schema_valid": raw_schema_valid,
        "recovery_steps": recovery_steps,
    }


def extract_planner_payload(raw_output: str) -> dict[str, Any]:
    """Return the first raw JSON object for candidate provenance artifacts."""

    text = re.sub(r"<think>.*?</think>", "", raw_output, flags=re.DOTALL).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, count=1)
    start = text.find("{")
    if start < 0:
        raise ModelOutputError("model output contains no JSON object", raw_output=raw_output)
    try:
        payload, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        try:
            document = _recover_truncated_element_prefix(text[start:], raw_output)
        except ModelOutputError:
            raise ModelOutputError(
                f"invalid model JSON: {exc}",
                raw_output=raw_output,
            ) from exc
        return {
            "recovery": "truncated_element_prefix",
            "complete_prefix_element_count": document.metadata[
                "complete_prefix_element_count"
            ],
            "normalized_design": document.model_dump(
                mode="json",
                exclude_none=True,
            ),
        }
    if not isinstance(payload, dict):
        raise ModelOutputError("planner JSON must be an object", raw_output=raw_output)
    return payload


def _recover_truncated_element_prefix(
    json_text: str,
    raw_output: str,
) -> DesignDocument:
    """Recover only fully decoded shorthand elements from a truncated JSON list."""

    canvas: dict[str, Any] | None = None
    canvas_object = re.search(
        r'"(?:canvas|canvas_size)"\s*:\s*\{([^{}]*)\}',
        json_text,
        flags=re.DOTALL,
    )
    if canvas_object:
        width = re.search(
            r'"width"\s*:\s*(-?\d+(?:\.\d+)?)',
            canvas_object.group(1),
        )
        height = re.search(
            r'"height"\s*:\s*(-?\d+(?:\.\d+)?)',
            canvas_object.group(1),
        )
        if width and height:
            canvas = {
                "width": float(width.group(1)),
                "height": float(height.group(1)),
            }
    if canvas is None:
        canvas_array = re.search(
            r'"canvas_size"\s*:\s*\[\s*(-?\d+(?:\.\d+)?)\s*,\s*'
            r'(-?\d+(?:\.\d+)?)\s*\]',
            json_text,
        )
        if canvas_array:
            canvas = {
                "width": float(canvas_array.group(1)),
                "height": float(canvas_array.group(2)),
            }
    if canvas is None:
        width = re.search(r'"width"\s*:\s*(-?\d+(?:\.\d+)?)', json_text)
        height = re.search(r'"height"\s*:\s*(-?\d+(?:\.\d+)?)', json_text)
        if width and height:
            canvas = {
                "width": float(width.group(1)),
                "height": float(height.group(1)),
            }
    elements_match = re.search(r'"elements"\s*:\s*\[', json_text)
    if canvas is None or elements_match is None:
        raise ModelOutputError(
            "truncated recovery requires canvas and elements",
            raw_output=raw_output,
        )

    decoder = json.JSONDecoder()
    position = elements_match.end()
    elements: list[dict[str, Any]] = []
    while position < len(json_text):
        while position < len(json_text) and json_text[position] in " \t\r\n,":
            position += 1
        if position >= len(json_text) or json_text[position] != "{":
            break
        try:
            element, consumed = decoder.raw_decode(json_text[position:])
        except json.JSONDecodeError:
            break
        if not isinstance(element, dict):
            break
        elements.append(element)
        position += consumed
    if not elements:
        raise ModelOutputError(
            "truncated recovery found no complete elements",
            raw_output=raw_output,
        )
    document = _recover_shorthand(
        {"canvas": canvas, "elements": elements, "category": "poster"},
        raw_output,
    )
    document.metadata.update(
        {
            "truncated_json_recovery": True,
            "complete_prefix_element_count": len(elements),
        }
    )
    return DesignDocument.model_validate(document.model_dump())


class Qwen3PlannerSession:
    """Load one quantized planner and generate sequential reproducible samples."""

    def __init__(
        self,
        *,
        checkpoint: Path,
        model_id: str,
        model_revision: str,
    ) -> None:
        import torch
        from peft import PeftModel
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
        )

        started = time.perf_counter()
        self.checkpoint = checkpoint.resolve()
        self.model_id = model_id
        self.model_revision = model_revision
        self.tokenizer = AutoTokenizer.from_pretrained(checkpoint)
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
        self.model = PeftModel.from_pretrained(base_model, checkpoint)
        self.model.eval()
        self.load_duration_seconds = time.perf_counter() - started

    def generate_raw(
        self,
        *,
        prompt: str,
        width_mm: float,
        height_mm: float,
        seed: int,
        max_new_tokens: int,
        do_sample: bool,
        temperature: float = 0.7,
        top_p: float = 0.8,
        top_k: int = 20,
        repetition_penalty: float = 1.05,
    ) -> RawPlannerGeneration:
        import torch
        from transformers import set_seed

        set_seed(seed, deterministic=True)
        messages = planner_messages(prompt, width_mm, height_mm)
        rendered = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        rendered += "{"
        inputs = self.tokenizer(rendered, return_tensors="pt").to("cuda")
        generation_config: dict[str, Any] = {
            "do_sample": do_sample,
            "max_new_tokens": max_new_tokens,
            "repetition_penalty": repetition_penalty,
        }
        if do_sample:
            generation_config.update(
                {
                    "temperature": temperature,
                    "top_p": top_p,
                    "top_k": top_k,
                    "min_p": 0.0,
                }
            )
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        with torch.inference_mode():
            output = self.model.generate(
                **inputs,
                **generation_config,
                eos_token_id=self.tokenizer.eos_token_id,
                pad_token_id=self.tokenizer.pad_token_id,
                use_cache=True,
            )
        duration_seconds = time.perf_counter() - started
        peak_vram_gib = torch.cuda.max_memory_allocated() / (1024**3)
        generated = self.tokenizer.decode(
            output[0, inputs["input_ids"].shape[1] :],
            skip_special_tokens=True,
        )
        return RawPlannerGeneration(
            raw_output="{" + generated,
            duration_seconds=duration_seconds,
            seed=seed,
            generation_config=generation_config,
            peak_vram_gib=peak_vram_gib,
        )


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
    session = Qwen3PlannerSession(
        checkpoint=checkpoint,
        model_id=model_id,
        model_revision=model_revision,
    )
    generation = session.generate_raw(
        prompt=prompt,
        width_mm=width_mm,
        height_mm=height_mm,
        seed=42,
        max_new_tokens=max_new_tokens,
        do_sample=False,
    )
    raw_output = generation.raw_output
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
