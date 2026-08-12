"""Adapter from unified design JSON to elem2design/LaDeCo conversations."""

from __future__ import annotations

import json
from typing import Any

from training.adapters.base import AdapterError
from training.schemas.design import ColorSpec, DesignDocument, DesignElement


LAYER_NAMES = (
    "background",
    "underlay",
    "logo/image",
    "text",
    "embellishment",
)


def _role(element: DesignElement) -> int:
    if element.id == "background" or element.layer.casefold() == "background":
        return 0
    if element.type in {"rectangle", "ellipse"}:
        return 1
    if element.type in {"image", "svg"}:
        return 2
    if element.type == "text":
        return 3
    return 4


def _rgb(color: ColorSpec | None) -> list[float]:
    if color is None:
        return [0.0, 0.0, 0.0]
    if color.model in {"rgb", "rgba"}:
        return [float(value) for value in color.values[:3]]
    if color.model == "hex":
        value = str(color.values[0]).lstrip("#")
        if len(value) in {3, 4}:
            value = "".join(character * 2 for character in value[:3])
        return [float(int(value[index : index + 2], 16)) for index in (0, 2, 4)]
    cyan, magenta, yellow, black = (
        float(value) / 100 for value in color.values
    )
    return [
        255 * (1 - cyan) * (1 - black),
        255 * (1 - magenta) * (1 - black),
        255 * (1 - yellow) * (1 - black),
    ]


def _layout_element(element: DesignElement) -> dict[str, Any]:
    text = element.text
    return {
        "index": element.id,
        "left": float(element.bbox.x),
        "top": float(element.bbox.y),
        "width": float(element.bbox.width),
        "height": float(element.bbox.height),
        "angle": float(element.rotation),
        "font": text.font_family if text else None,
        "font_size": float(text.font_size) if text and text.font_size else None,
        "color": _rgb(element.visual.fill),
        "text_align": text.alignment if text and text.alignment else "left",
        "capitalize": False,
        "letter_spacing": float(text.tracking) if text and text.tracking else 0.0,
        "line_height": float(text.line_height) if text and text.line_height else 1.0,
        "text": text.content if text else "",
    }


def to_elem2design_sample(
    document: DesignDocument,
    *,
    render_images: list[str] | None = None,
) -> dict[str, Any]:
    if document.canvas.unit != "px":
        raise AdapterError("elem2design adapter currently requires a pixel canvas")
    images = list(render_images or [])
    if images and len(images) != 4:
        raise AdapterError("elem2design requires exactly four intermediate renders")

    by_layer: list[list[DesignElement]] = [[] for _ in range(5)]
    for element in sorted(document.elements, key=lambda item: item.z_index):
        if element.type == "group":
            continue
        by_layer[_role(element)].append(element)

    context_by_layer = [
        ", ".join(f"{element.name} ({element.type})" for element in elements)
        or "none"
        for elements in by_layer
    ]
    targets = [
        " ".join(
            json.dumps(_layout_element(element), ensure_ascii=False)
            for element in elements
        )
        or "{}"
        for elements in by_layer
    ]
    canvas = document.canvas
    preamble = (
        f"A poster of canvas width {float(canvas.width):g}px, canvas height "
        f"{float(canvas.height):g}px. Predict layered editable elements. "
    )
    conversations: list[dict[str, str]] = []
    for layer_index, layer_name in enumerate(LAYER_NAMES):
        if layer_index == 0:
            value = (
                preamble
                + f"Now predict the {layer_name} elements: "
                + context_by_layer[layer_index]
            )
        else:
            image_context = "<image>. " if images else ""
            value = (
                f"current canvas state: {image_context}Now predict the "
                f"{layer_name} elements: {context_by_layer[layer_index]}"
            )
        conversations.extend(
            [
                {"from": "human", "value": value},
                {"from": "gpt", "value": targets[layer_index]},
            ]
        )

    return {
        "id": document.sample_id,
        "image": images,
        "conversations": conversations,
        "render_image": images,
        "render_text": [
            element.text.content
            for element in document.elements
            if element.text is not None
        ],
        "metadata": {
            "source": document.source.name,
            "license_class": document.source.license_class,
            "commercial_allowed": document.source.commercial_allowed,
            "adapter_mode": (
                "rendered_multimodal" if images else "layout_only_dry_run"
            ),
        },
    }


def validate_elem2design_sample(sample: dict[str, Any]) -> None:
    conversations = sample.get("conversations")
    if not isinstance(conversations, list) or len(conversations) != 10:
        raise AdapterError("elem2design sample requires ten conversation messages")
    for index, message in enumerate(conversations):
        expected = "human" if index % 2 == 0 else "gpt"
        if message.get("from") != expected or not str(message.get("value", "")):
            raise AdapterError(f"invalid elem2design conversation at index {index}")
    images = sample.get("image")
    if not isinstance(images, list) or len(images) not in {0, 4}:
        raise AdapterError("elem2design image list must contain zero or four paths")
    image_tokens = sum(message["value"].count("<image>") for message in conversations)
    if image_tokens != len(images):
        raise AdapterError("image token count does not match image paths")
