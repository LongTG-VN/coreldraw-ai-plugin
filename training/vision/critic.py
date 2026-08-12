"""Lazy local Qwen3-VL critic with strict JSON recovery."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import ValidationError

from training.schemas.design import DesignDocument
from training.vision.models import (
    PairwiseVisionJudgmentV1,
    VisionCriticConfig,
    VisionCritiqueV1,
)
from training.vision.prompts import critique_prompt, pairwise_prompt


class VisionCriticError(RuntimeError):
    pass


@runtime_checkable
class VisionCritic(Protocol):
    config: VisionCriticConfig
    loaded: bool
    load_duration_seconds: float | None
    peak_memory_gib: float

    def critique(
        self, *, preview_path: Path, brief: str, category: str,
        business_content: dict[str, object], asset_roles: list[str],
        document: DesignDocument,
    ) -> VisionCritiqueV1: ...

    def compare(
        self, *, image_a: Path, image_b: Path, brief: str, category: str,
    ) -> PairwiseVisionJudgmentV1: ...


def recover_json_object(raw: str) -> tuple[dict[str, Any], bool]:
    """Recover one complete JSON object; never accept a truncated prefix."""

    text = raw.strip()
    recovered = not (text.startswith("{") and text.endswith("}"))
    decoder = json.JSONDecoder()
    start = text.find("{")
    if start >= 0:
        try:
            payload, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return payload, recovered or start != 0
    raise VisionCriticError("critic returned no complete JSON object")


def _normalize_critique_payload(payload: dict[str, Any], *, max_issues: int) -> tuple[dict[str, Any], bool]:
    """Apply only bounded schema aliases/defaults; unknown commands still fail."""

    changed = False
    normalized = dict(payload)
    if "overall" not in normalized and "quality_score" in normalized:
        normalized = {
            "overall": {
                "quality_score": normalized.pop("quality_score"),
                "confidence": normalized.pop("confidence", 0.5),
            },
            "issues": normalized.get("issues", []),
        }
        changed = True
    role_aliases = {"product": "hero", "image": "hero", "composition": "layout"}
    action_aliases = {
        "increase_size": "increase_area", "decrease_size": "decrease_area",
        "enhance_contrast": "increase_contrast", "strengthen_hierarchy": "increase_emphasis",
    }
    issues = normalized.get("issues", [])
    if not isinstance(issues, list):
        raise VisionCriticError("critic issues must be a list")
    cleaned = []
    for issue in issues[:max_issues]:
        if not isinstance(issue, dict):
            raise VisionCriticError("critic issue must be an object")
        item = dict(issue)
        role = item.get("target_role")
        if role in role_aliases:
            item["target_role"] = role_aliases[role]
            changed = True
        action = item.get("recommended_action")
        if action in action_aliases:
            item["recommended_action"] = action_aliases[action]
            changed = True
        severity = item.get("severity")
        if isinstance(severity, (int, float)) and not isinstance(severity, bool):
            score = max(0.0, min(float(severity), 1.0))
            item["confidence"] = item.get("confidence", score)
            item["severity"] = "high" if score >= .8 else "medium" if score >= .55 else "low"
            changed = True
        if "confidence" not in item:
            overall = normalized.get("overall", {})
            item["confidence"] = (
                overall.get("confidence", .5) if isinstance(overall, dict) else .5
            )
            changed = True
        magnitude_aliases = {"moderate": "medium", "low": "small", "high": "medium"}
        magnitude = item.get("magnitude")
        if magnitude in magnitude_aliases:
            item["magnitude"] = magnitude_aliases[magnitude]
            changed = True
        if "magnitude" not in item:
            item["magnitude"] = "small"
            changed = True
        cleaned.append(item)
    if len(issues) > max_issues:
        changed = True
    normalized["issues"] = cleaned
    return normalized, changed


class TransformersQwenVisionCritic:
    """Qwen3-VL adapter; torch/model weights are loaded only on first call."""

    def __init__(
        self,
        config: VisionCriticConfig | None = None,
        *,
        local_model_path: Path | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.config = config or VisionCriticConfig()
        self.local_model_path = local_model_path.resolve() if local_model_path else None
        self.cache_dir = cache_dir.resolve() if cache_dir else None
        self.loaded = False
        self.load_duration_seconds: float | None = None
        self.peak_memory_gib = 0.0
        self._model: Any | None = None
        self._processor: Any | None = None
        self._torch: Any | None = None
        self._device = "not_loaded"

    @property
    def device(self) -> str:
        return self._device

    def _ensure_loaded(self) -> None:
        if self.loaded:
            return
        started = time.perf_counter()
        try:
            import torch
            from transformers import (
                AutoModelForMultimodalLM,
                AutoProcessor,
                BitsAndBytesConfig,
            )
        except ImportError as exc:
            raise VisionCriticError(
                "vision critic requires optional torch, torchvision, transformers, "
                "accelerate, and bitsandbytes dependencies"
            ) from exc
        if self.config.device == "cuda" and not torch.cuda.is_available():
            raise VisionCriticError("vision critic configured for CUDA but CUDA is unavailable")
        device = "cuda" if self.config.device == "auto" and torch.cuda.is_available() else self.config.device
        if device == "auto":
            device = "cpu"
        source: str | Path = self.local_model_path or self.config.model_id
        kwargs: dict[str, Any] = {
            "revision": None if self.local_model_path else self.config.revision,
            "cache_dir": self.cache_dir,
            "low_cpu_mem_usage": True,
            "dtype": torch.float16 if device == "cuda" else torch.float32,
        }
        if self.config.quantization == "nf4_4bit":
            if device != "cuda":
                raise VisionCriticError("NF4 vision critic requires CUDA; use quantization=none for CPU")
            kwargs.update(
                {
                    "device_map": "auto",
                    "quantization_config": BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_compute_dtype=torch.float16,
                        bnb_4bit_use_double_quant=True,
                    ),
                }
            )
        else:
            kwargs["device_map"] = device
        kwargs = {key: value for key, value in kwargs.items() if value is not None}
        try:
            if device == "cuda":
                torch.cuda.empty_cache()
                torch.cuda.reset_peak_memory_stats()
            self._model = AutoModelForMultimodalLM.from_pretrained(source, **kwargs).eval()
            self._processor = AutoProcessor.from_pretrained(
                source,
                revision=None if self.local_model_path else self.config.revision,
                cache_dir=self.cache_dir,
            )
        except Exception as exc:
            raise VisionCriticError(
                f"failed to load {self.config.model_id}@{self.config.revision}: {exc}"
            ) from exc
        self._torch = torch
        self._device = str(next(self._model.parameters()).device)
        self.loaded = True
        self.load_duration_seconds = time.perf_counter() - started
        self._update_peak()

    def _update_peak(self) -> None:
        if self._torch is not None and str(self._device).startswith("cuda"):
            self.peak_memory_gib = max(
                self.peak_memory_gib,
                self._torch.cuda.max_memory_allocated() / 1024**3,
            )

    def _image(self, path: Path) -> Image.Image:
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"critic preview missing: {resolved}")
        try:
            with Image.open(resolved) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
        except (UnidentifiedImageError, OSError) as exc:
            raise VisionCriticError(f"invalid critic preview: {resolved}") from exc
        image.thumbnail(
            (self.config.max_image_dimension, self.config.max_image_dimension),
            Image.Resampling.LANCZOS,
        )
        return image

    def _generate(self, images: list[Image.Image], prompt: str, *, max_tokens: int) -> tuple[str, float]:
        self._ensure_loaded()
        assert self._processor is not None and self._model is not None and self._torch is not None
        content = [{"type": "image", "image": image} for image in images]
        content.append({"type": "text", "text": prompt})
        messages = [{"role": "user", "content": content}]
        inputs = self._processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
        inputs = {
            key: value.to(self._device) if hasattr(value, "to") else value
            for key, value in inputs.items()
        }
        started = time.perf_counter()
        self._torch.manual_seed(0)
        with self._torch.inference_mode():
            generated = self._model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=False,
                use_cache=True,
            )
        elapsed = time.perf_counter() - started
        output = self._processor.batch_decode(
            generated[:, inputs["input_ids"].shape[1] :],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]
        self._update_peak()
        return output, elapsed

    def critique(
        self, *, preview_path: Path, brief: str, category: str,
        business_content: dict[str, object], asset_roles: list[str],
        document: DesignDocument,
    ) -> VisionCritiqueV1:
        prompt = critique_prompt(
            brief=brief,
            category=category,
            business_content=business_content,
            asset_roles=asset_roles,
            document=document,
        )
        raw, latency = self._generate(
            [self._image(preview_path)], prompt, max_tokens=self.config.max_new_tokens
        )
        try:
            payload, recovered = recover_json_object(raw)
            payload, normalized = _normalize_critique_payload(
                payload, max_issues=self.config.max_issues
            )
            return VisionCritiqueV1.model_validate(
                {
                    **payload,
                    "schema_version": "1.0",
                    "critic_model": self.config.model_id,
                    "critic_revision": self.config.revision,
                    "raw_recovered": recovered or normalized,
                    "latency_seconds": latency,
                },
                strict=False,
            )
        except (VisionCriticError, ValidationError, TypeError) as first_error:
            retry_prompt = prompt + "\nYour previous response was invalid. Return one compact complete JSON object, at most 2 issues and no markdown."
            retry_raw, retry_latency = self._generate(
                [self._image(preview_path)], retry_prompt, max_tokens=min(320, self.config.max_new_tokens + 64)
            )
            try:
                payload, _ = recover_json_object(retry_raw)
                payload, _ = _normalize_critique_payload(
                    payload, max_issues=self.config.max_issues
                )
                return VisionCritiqueV1.model_validate(
                    {
                        **payload,
                        "schema_version": "1.0",
                        "critic_model": self.config.model_id,
                        "critic_revision": self.config.revision,
                        "raw_recovered": True,
                        "latency_seconds": latency + retry_latency,
                    },
                    strict=False,
                )
            except (VisionCriticError, ValidationError, TypeError) as exc:
                raise VisionCriticError(
                    f"critic JSON invalid after one retry: {exc}; first error: {first_error}"
                ) from exc

    def compare(
        self, *, image_a: Path, image_b: Path, brief: str, category: str,
    ) -> PairwiseVisionJudgmentV1:
        raw, latency = self._generate(
            [self._image(image_a), self._image(image_b)],
            pairwise_prompt(brief=brief, category=category),
            max_tokens=160,
        )
        try:
            payload, _ = recover_json_object(raw)
            preferred = str(payload.get("preferred", "")).strip().upper().replace("IMAGE ", "")
            if preferred in {"A", "B", "TIE"}:
                payload["preferred"] = preferred.lower() if preferred == "TIE" else preferred
            return PairwiseVisionJudgmentV1.model_validate(
                {
                    **payload,
                    "schema_version": "1.0",
                    "critic_model": self.config.model_id,
                    "critic_revision": self.config.revision,
                    "latency_seconds": latency,
                },
                strict=False,
            )
        except (ValidationError, VisionCriticError) as first_error:
            retry_raw, retry_latency = self._generate(
                [self._image(image_a), self._image(image_b)],
                pairwise_prompt(brief=brief, category=category)
                + "\nPrevious output was invalid. Return one compact complete JSON object with all keys and no markdown.",
                max_tokens=192,
            )
            try:
                payload, _ = recover_json_object(retry_raw)
                preferred = str(payload.get("preferred", "")).strip().upper().replace("IMAGE ", "")
                if preferred in {"A", "B", "TIE"}:
                    payload["preferred"] = preferred.lower() if preferred == "TIE" else preferred
                return PairwiseVisionJudgmentV1.model_validate(
                    {
                        **payload,
                        "schema_version": "1.0",
                        "critic_model": self.config.model_id,
                        "critic_revision": self.config.revision,
                        "latency_seconds": latency + retry_latency,
                    },
                    strict=False,
                )
            except (ValidationError, VisionCriticError) as exc:
                raise VisionCriticError(
                    f"pairwise critic JSON invalid after retry: {exc}; first error: {first_error}"
                ) from exc

    def unload(self) -> None:
        if self._model is None:
            return
        del self._model
        self._model = None
        self._processor = None
        if self._torch is not None and self._torch.cuda.is_available():
            self._torch.cuda.empty_cache()
        self.loaded = False
        self._device = "not_loaded"


__all__ = [
    "TransformersQwenVisionCritic", "VisionCritic", "VisionCriticError",
    "recover_json_object",
]
