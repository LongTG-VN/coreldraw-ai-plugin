from __future__ import annotations

from training.evaluation.layout_metrics import evaluate_layout
from training.evaluation.critics import HeuristicAestheticCritic
from training.inference.corel_compiler import compile_corel_operations
from training.inference.preview import render_preview
from training.typography.fitting import fit_design_typography, measure_text
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


def _text(
    canvas: CanvasSpec,
    *,
    element_id: str,
    content: str,
    x: float,
    y: float,
    width: float,
    height: float,
    font_size: float,
    role: str,
) -> DesignElement:
    bbox = BoundingBox(x=x, y=y, width=width, height=height)
    return DesignElement(
        id=element_id,
        name=role,
        type="text",
        bbox=bbox,
        bbox_norm=normalize_bbox(bbox, canvas),
        text=TextSpec(content=content, font_family="Arial", font_size=font_size),
        visual=VisualSpec(fill=ColorSpec(model="hex", values=["#111111"])),
        metadata={"role": role},
    )


def _dense_menu() -> DesignDocument:
    canvas = CanvasSpec(width=210, height=297, unit="mm")
    background = BoundingBox(x=0, y=0, width=210, height=297)
    elements = [
        DesignElement(
            id="background",
            name="Background",
            type="rectangle",
            bbox=background,
            bbox_norm=normalize_bbox(background, canvas),
            layer="background",
            visual=VisualSpec(fill=ColorSpec(model="hex", values=["#FFF8E8"])),
        ),
        _text(
            canvas,
            element_id="headline",
            content="MENU BẾP NHÀ",
            x=15,
            y=12,
            width=180,
            height=30,
            font_size=28,
            role="headline",
        ),
    ]
    for index in range(6):
        y = 58 + index * 31
        elements.append(
            _text(
                canvas,
                element_id=f"dish_{index}",
                content=f"Món {index + 1} với mô tả nguyên liệu tươi ngon",
                x=15,
                y=y,
                width=135,
                height=18,
                font_size=18,
                role="menu_item",
            )
        )
        elements.append(
            _text(
                canvas,
                element_id=f"price_{index}",
                content=f"{39 + index * 5}K",
                x=160,
                y=y,
                width=35,
                height=18,
                font_size=18,
                role="price",
            )
        )
    return DesignDocument(
        sample_id="synthetic:dense-menu-fit",
        source=SourceSpec(
            name="synthetic_owned",
            split="test",
            license_class="production_safe",
            upstream_id="dense-menu-fit",
            commercial_allowed=True,
        ),
        canvas=canvas,
        category="food_menu",
        elements=elements,
    )


def test_measure_text_uses_glyph_width_and_explicit_lines() -> None:
    measured = measure_text(
        "A long headline that wraps",
        box_width=70,
        font_size=18,
        family="Arial",
    )

    assert len(measured.lines) >= 2
    assert measured.width <= 70
    assert measured.height > 18


def test_typography_fit_removes_dense_menu_overflow_without_truncation() -> None:
    document = _dense_menu()
    before = evaluate_layout(document)

    fitted, report = fit_design_typography(document)
    after = evaluate_layout(fitted)

    assert before["text_fit_rate"] < after["text_fit_rate"]
    assert after["text_fit_rate"] == 1
    assert after["text_overflow_count"] == 0
    assert after["headline_dominance"] >= 0.8
    assert after["price_alignment_consistency"] == 1
    assert after["price_element_count"] == 6
    assert report["truncated_count"] == 0
    assert report["unresolved_overflow_count"] == 0
    assert all(
        not element.metadata.get("typography_fit", {}).get("truncated", False)
        for element in fitted.elements
    )


def test_fitted_design_remains_corel_compilable() -> None:
    fitted, _ = fit_design_typography(_dense_menu())

    operations = compile_corel_operations(fitted)

    text_operations = [item for item in operations if item["op"] == "create_text"]
    assert len(text_operations) == 13
    assert all(float(item["font_size"]) >= 6 for item in text_operations)


def test_role_aware_critic_rewards_fitted_hierarchy(tmp_path) -> None:
    original = _dense_menu()
    flat_payload = original.model_dump()
    for element in flat_payload["elements"]:
        if element.get("text"):
            element["text"]["font_size"] = 18
    flat = DesignDocument.model_validate(flat_payload)
    fitted, _ = fit_design_typography(original)
    critic = HeuristicAestheticCritic()

    flat_score = critic.score(
        prompt="Menu 6 món, giá căn thẳng hàng",
        document=flat,
        preview_path=render_preview(flat, tmp_path / "flat.png"),
        metrics=evaluate_layout(flat),
    )
    fitted_score = critic.score(
        prompt="Menu 6 món, giá căn thẳng hàng",
        document=fitted,
        preview_path=render_preview(fitted, tmp_path / "fitted.png"),
        metrics=evaluate_layout(fitted),
    )

    assert fitted_score.critic_version == "0.3.0"
    assert fitted_score.visual_hierarchy > flat_score.visual_hierarchy
