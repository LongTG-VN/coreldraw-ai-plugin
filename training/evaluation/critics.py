"""Offline technical and aesthetic critics for structured designs."""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from training.evaluation.layout_metrics import evaluate_layout
from training.schemas.design import ColorSpec, DesignDocument, DesignElement


class CriticModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TechnicalViolation(CriticModel):
    code: str
    severity: Literal["hard", "soft"]
    penalty: float = Field(ge=0, le=1)
    explanation: str


class TechnicalCriticResult(CriticModel):
    scale: Literal["0..1"] = "0..1"
    overall: float = Field(ge=0, le=1)
    hard_failure: bool
    violations: list[TechnicalViolation]
    metrics: dict[str, float | int]
    critic_name: str = "deterministic_technical_critic"
    critic_version: str = "0.2.0"


class AestheticCriticResult(CriticModel):
    scale: Literal["0..1"] = "0..1"
    overall: float = Field(ge=0, le=1)
    composition: float = Field(ge=0, le=1)
    visual_hierarchy: float = Field(ge=0, le=1)
    typography: float = Field(ge=0, le=1)
    spacing: float = Field(ge=0, le=1)
    color_harmony: float = Field(ge=0, le=1)
    balance: float = Field(ge=0, le=1)
    readability: float = Field(ge=0, le=1)
    style_match: float = Field(ge=0, le=1)
    explanation: str
    critic_name: str
    critic_version: str
    model_based: bool


class AestheticCritic(ABC):
    """Pluggable preview critic contract; all scores use the 0..1 scale."""

    critic_name = "aesthetic_critic"
    critic_version = "unknown"
    model_based = False

    @abstractmethod
    def score(
        self,
        *,
        prompt: str,
        document: DesignDocument,
        preview_path: Path,
        metrics: dict[str, float | int],
    ) -> AestheticCriticResult:
        raise NotImplementedError


class VisionAestheticCritic(AestheticCritic, ABC):
    """Extension point for PosterReward, a VLM, or an evaluation service."""

    model_based = True


def _clamp(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def _content_elements(document: DesignDocument) -> list[DesignElement]:
    return [
        element
        for element in document.elements
        if element.type != "group"
        and element.id != "background"
        and element.layer.casefold() != "background"
    ]


class TechnicalCritic:
    """Deterministic eligibility gate plus print/layout-oriented penalties."""

    critic_name = "deterministic_technical_critic"
    critic_version = "0.2.3"

    def score(
        self,
        document: DesignDocument | None,
        *,
        validation: dict[str, Any] | None = None,
    ) -> TechnicalCriticResult:
        if document is None:
            return TechnicalCriticResult(
                overall=0,
                hard_failure=True,
                violations=[
                    TechnicalViolation(
                        code="invalid_schema",
                        severity="hard",
                        penalty=1,
                        explanation="Candidate did not produce a validated design.",
                    )
                ],
                metrics={
                    "schema_validity": 0,
                    "bbox_validity": 0,
                    "normalized_coordinate_validity": 0,
                    "outside_canvas_rate": 1,
                },
                critic_name=self.critic_name,
                critic_version=self.critic_version,
            )

        metrics = evaluate_layout(document)
        metrics["schema_validity"] = 1.0
        violations: list[TechnicalViolation] = []
        hard_failure = False

        def add(
            code: str,
            severity: Literal["hard", "soft"],
            penalty: float,
            explanation: str,
        ) -> None:
            nonlocal hard_failure
            violations.append(
                TechnicalViolation(
                    code=code,
                    severity=severity,
                    penalty=_clamp(penalty),
                    explanation=explanation,
                )
            )
            hard_failure = hard_failure or severity == "hard"

        if float(metrics.get("bbox_validity", 0)) < 1:
            add("invalid_bbox", "hard", 1, "At least one bbox is invalid.")
        if float(metrics.get("normalized_coordinate_validity", 0)) < 1:
            add(
                "invalid_normalized_coordinates",
                "hard",
                1,
                "Normalized coordinates are invalid.",
            )
        outside = float(metrics.get("outside_canvas_rate", 0))
        if outside > 0:
            add("outside_canvas", "hard", 1, "Objects extend outside the canvas.")
        if int(metrics.get("invalid_dimension_count", 0)):
            add("invalid_dimensions", "hard", 1, "Invalid element dimensions found.")
        if int(metrics.get("duplicate_id_count", 0)):
            add("duplicate_ids", "hard", 1, "Duplicate element IDs found.")

        overlap = float(metrics.get("overlap_ratio", 0))
        if overlap > 0.02:
            add(
                "content_overlap",
                "soft",
                min(overlap * 1.4, 0.70),
                f"Content overlap ratio is {overlap:.3f}.",
            )
        tiny_text = float(metrics.get("tiny_text_rate", 0))
        if tiny_text > 0:
            add(
                "tiny_text",
                "soft",
                min(tiny_text * 0.35, 0.35),
                f"Tiny-text rate is {tiny_text:.3f}.",
            )
        text_overflow = float(metrics.get("text_overflow_rate", 0))
        if text_overflow > 0:
            add(
                "text_box_overflow",
                "soft",
                min(text_overflow * 0.55, 0.55),
                f"Estimated rendered-text overflow rate is {text_overflow:.3f}.",
            )
        duplicate_rate = float(metrics.get("duplicate_element_rate", 0))
        if duplicate_rate > 0:
            add(
                "duplicated_elements",
                "soft",
                min(duplicate_rate * 0.35, 0.35),
                "Semantically duplicated elements reduce quality.",
            )
        element_count = int(metrics.get("content_element_count", 0))
        if element_count > 16:
            add(
                "excessive_element_count",
                "soft",
                min((element_count - 16) / 30, 0.35),
                f"Content element count {element_count} is excessive.",
            )
        coverage = float(metrics.get("coverage", 0))
        if coverage < 0.12 or coverage > 0.82:
            add(
                "unbalanced_coverage",
                "soft",
                min(abs(coverage - 0.45), 0.3),
                f"Coverage {coverage:.3f} is outside the useful range.",
            )
        if validation and not bool(validation.get("raw_schema_valid", True)):
            add(
                "schema_recovery_required",
                "soft",
                0.08,
                "Raw model output required explicit schema recovery.",
            )
        if bool(document.metadata.get("truncated_json_recovery", False)):
            add(
                "truncated_model_output",
                "soft",
                0.18,
                "Only the complete prefix of a truncated model output was usable.",
            )

        overall = 0.0 if hard_failure else _clamp(
            1.0 - sum(violation.penalty for violation in violations)
        )
        return TechnicalCriticResult(
            overall=overall,
            hard_failure=hard_failure,
            violations=violations,
            metrics=metrics,
            critic_name=self.critic_name,
            critic_version=self.critic_version,
        )


def _balance_score(elements: list[DesignElement]) -> float:
    if not elements:
        return 0.0
    areas = [float(item.bbox_norm.width * item.bbox_norm.height) for item in elements]
    total_area = sum(areas)
    if total_area <= 0:
        return 0.0
    center_x = sum(
        area * float(item.bbox_norm.x + item.bbox_norm.width / 2)
        for item, area in zip(elements, areas)
    ) / total_area
    center_y = sum(
        area * float(item.bbox_norm.y + item.bbox_norm.height / 2)
        for item, area in zip(elements, areas)
    ) / total_area
    distance = math.dist((center_x, center_y), (0.5, 0.5)) / math.sqrt(0.5)
    return _clamp(1 - distance)


def _color_harmony_score(elements: list[DesignElement]) -> float:
    colors = {
        element.visual.fill.model_dump_json()
        for element in elements
        if element.visual.fill is not None
    }
    if not colors:
        return 0.45
    count = len(colors)
    if 2 <= count <= 5:
        return 1.0
    if count == 1:
        return 0.7
    return _clamp(1 - (count - 5) * 0.12)


def _rgb(color: ColorSpec | None) -> tuple[float, float, float]:
    if color is None:
        return (0.0, 0.0, 0.0)
    if color.model == "hex":
        value = str(color.values[0]).lstrip("#")
        if len(value) in {3, 4}:
            value = "".join(channel * 2 for channel in value[:3])
        return tuple(int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))
    channels = [float(value) for value in color.values]
    if color.model in {"rgb", "rgba"}:
        return tuple(channel / 255 for channel in channels[:3])
    cyan, magenta, yellow, black = (channel / 100 for channel in channels)
    return (
        (1 - cyan) * (1 - black),
        (1 - magenta) * (1 - black),
        (1 - yellow) * (1 - black),
    )


def _relative_luminance(color: ColorSpec | None) -> float:
    def linearize(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = _rgb(color)
    return 0.2126 * linearize(red) + 0.7152 * linearize(green) + 0.0722 * linearize(blue)


def _contrast_score(document: DesignDocument, elements: list[DesignElement]) -> float:
    background = next(
        (
            element.visual.fill
            for element in document.elements
            if element.id == "background" or element.layer.casefold() == "background"
        ),
        document.canvas.background.fill if document.canvas.background else None,
    )
    background_luminance = _relative_luminance(background)
    scores = []
    for element in elements:
        if element.text is None:
            continue
        text_luminance = _relative_luminance(element.visual.fill)
        lighter = max(background_luminance, text_luminance)
        darker = min(background_luminance, text_luminance)
        contrast_ratio = (lighter + 0.05) / (darker + 0.05)
        scores.append(_clamp((contrast_ratio - 1) / 6))
    return sum(scores) / len(scores) if scores else 0.5


def _prompt_match(prompt: str, elements: list[DesignElement]) -> float:
    prompt_tokens = {
        token
        for token in re.findall(r"\w+", prompt.casefold(), flags=re.UNICODE)
        if len(token) >= 3
    }
    text = " ".join(
        element.text.content
        for element in elements
        if element.text is not None
    ).casefold()
    if not prompt_tokens:
        return 0.5
    matched = sum(token in text for token in prompt_tokens)
    return _clamp(matched / min(len(prompt_tokens), 6))


class HeuristicAestheticCritic(AestheticCritic):
    """Offline fallback based only on validated structure and preview metadata."""

    critic_name = "heuristic_aesthetic_critic"
    critic_version = "0.2.3"
    model_based = False

    def score(
        self,
        *,
        prompt: str,
        document: DesignDocument,
        preview_path: Path,
        metrics: dict[str, float | int],
    ) -> AestheticCriticResult:
        if not preview_path.is_file():
            raise FileNotFoundError(f"preview not found: {preview_path}")
        elements = _content_elements(document)
        overlap = _clamp(float(metrics.get("overlap_ratio", 0)))
        coverage = _clamp(float(metrics.get("coverage", 0)))
        whitespace = _clamp(float(metrics.get("whitespace", 0)))
        alignment = _clamp(float(metrics.get("alignment_consistency", 0)))
        tiny_text = _clamp(float(metrics.get("tiny_text_rate", 0)))
        text_fit = _clamp(float(metrics.get("text_fit_rate", 1)))
        hierarchy_ratio = max(float(metrics.get("text_hierarchy_ratio", 1)), 1e-6)

        coverage_fit = _clamp(1 - abs(coverage - 0.42) / 0.42)
        composition = _clamp(
            0.45 * coverage_fit + 0.35 * (1 - overlap) + 0.20 * alignment
        )
        hierarchy = _clamp(1 - abs(math.log(hierarchy_ratio / 2.4)) / 1.5)
        typography = _clamp(
            0.35 * (1 - tiny_text) + 0.35 * hierarchy + 0.30 * text_fit
        )
        whitespace_fit = _clamp(1 - abs(whitespace - 0.55) / 0.55)
        spacing = _clamp(
            0.65 * (1 - min(overlap * 4, 1)) + 0.35 * whitespace_fit
        )
        color_harmony = _color_harmony_score(elements)
        balance = _balance_score(elements)
        contrast = _contrast_score(document, elements)
        readability = _clamp(
            0.20 * (1 - tiny_text)
            + 0.25 * (1 - min(overlap * 5, 1))
            + 0.30 * contrast
            + 0.25 * text_fit
        )
        style_match = _prompt_match(prompt, elements)
        dimensions = [
            composition,
            hierarchy,
            typography,
            spacing,
            color_harmony,
            balance,
            readability,
            style_match,
        ]
        overall = sum(dimensions) / len(dimensions)
        return AestheticCriticResult(
            overall=overall,
            composition=composition,
            visual_hierarchy=hierarchy,
            typography=typography,
            spacing=spacing,
            color_harmony=color_harmony,
            balance=balance,
            readability=readability,
            style_match=style_match,
            explanation=(
                "Offline heuristic critic; no learned vision/reward model was used. "
                f"Mean normalized text/background contrast={contrast:.3f}; "
                f"estimated text-fit rate={text_fit:.3f}."
            ),
            critic_name=self.critic_name,
            critic_version=self.critic_version,
            model_based=self.model_based,
        )
