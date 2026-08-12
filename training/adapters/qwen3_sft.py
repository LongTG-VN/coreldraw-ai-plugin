"""Compact, Corel-safe SFT projection for the local Qwen3 planner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from training.schemas.design import (
    BoundingBox,
    ColorSpec,
    DesignDocument,
    DesignElement,
    VisualSpec,
    normalize_bbox,
)


SYSTEM_PROMPT = (
    "You are Design AI, a structured layout planner. Return only one compact "
    "JSON object that validates as DesignDocument schema_version 0.1. Use "
    "top-left coordinates, keep every bbox inside the canvas, and do not use "
    "Markdown or reasoning text."
)


@dataclass(frozen=True)
class Qwen3SFTRecord:
    sample_id: str
    prompt: list[dict[str, str]]
    completion: list[dict[str, str]]
    license_class: str
    commercial_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "prompt": self.prompt,
            "completion": self.completion,
            "license_class": self.license_class,
            "commercial_allowed": self.commercial_allowed,
        }


class Qwen3SFTAdapter:
    """Project unified designs into short conversational SFT examples.

    GenPoster image layers reference research-dataset assets that are not local
    Corel files. They are represented as editable rectangle placeholders. This
    keeps every target valid and compilable while retaining layout geometry.
    """

    def __init__(self, *, max_elements: int = 4) -> None:
        if max_elements < 2:
            raise ValueError("max_elements must allow a background and content")
        self.max_elements = max_elements

    def convert(self, document: DesignDocument) -> Qwen3SFTRecord:
        projected = self.project(document)
        visible_text = [
            element.text.content.strip()
            for element in projected.elements
            if element.text is not None and element.text.content.strip()
        ]
        text_instruction = (
            "; ".join(visible_text[:3]) if visible_text else "no supplied copy"
        )
        user_prompt = (
            f"Create an editable {projected.category} layout at "
            f"{float(projected.canvas.width):g} x "
            f"{float(projected.canvas.height):g} {projected.canvas.unit}. "
            f"Required text: {text_instruction}."
        )
        target = projected.model_dump_json(
            exclude_none=True,
            exclude_defaults=True,
        )
        DesignDocument.model_validate(json.loads(target))
        return Qwen3SFTRecord(
            sample_id=projected.sample_id,
            prompt=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            completion=[{"role": "assistant", "content": target}],
            license_class=projected.source.license_class,
            commercial_allowed=projected.source.commercial_allowed,
        )

    def project(self, document: DesignDocument) -> DesignDocument:
        canvas = document.canvas.model_copy(deep=True)
        background_bbox = BoundingBox(
            x=0,
            y=0,
            width=float(canvas.width),
            height=float(canvas.height),
        )
        elements = [
            DesignElement(
                id="background",
                name="Background",
                type="rectangle",
                bbox=background_bbox,
                bbox_norm=normalize_bbox(background_bbox, canvas),
                z_index=0,
                layer="background",
                visual=VisualSpec(
                    fill=(
                        canvas.background.fill
                        if canvas.background and canvas.background.fill
                        else ColorSpec(model="rgb", values=[255, 255, 255])
                    )
                ),
            )
        ]
        candidates = sorted(
            document.elements,
            key=lambda item: (
                item.type != "text",
                -(float(item.bbox.width) * float(item.bbox.height)),
                item.z_index,
            ),
        )
        for index, source in enumerate(candidates[: self.max_elements - 1], start=1):
            payload = source.model_dump()
            payload.update(
                {
                    "id": f"content_{index}",
                    "name": source.name[:300],
                    "z_index": index,
                    "layer": "content",
                    "parent_id": None,
                    "metadata": {},
                }
            )
            if source.type in {"image", "svg", "other", "group"}:
                payload.update(
                    {
                        "type": "rectangle",
                        "text": None,
                        "asset_ref": None,
                        "visual": source.visual.model_dump(),
                    }
                )
                if source.visual.fill is None:
                    payload["visual"]["fill"] = {
                        "model": "rgb",
                        "values": [230, 230, 230],
                    }
            elements.append(DesignElement.model_validate(payload))

        return DesignDocument(
            sample_id=document.sample_id,
            source=document.source.model_copy(deep=True),
            canvas=canvas,
            category=document.category,
            elements=elements,
            assets=[],
            metadata={
                "adapter": "qwen3_structured_planner_sft_v0.1",
                "research_only": not document.source.commercial_allowed,
            },
        )
