from __future__ import annotations

from training.evaluation.layout_metrics import evaluate_layout
from training.inference.corel_compiler import compile_corel_operations
from training.retrieval import analyze_brief
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
from training.typography.fitting import fit_design_typography
from training.visual import apply_visual_composition, evaluate_visual_quality, get_visual_profile
from training.visual.palette import contrast_ratio, resolve_palette
from training.visual.profiles import supported_visual_categories


def _text(
    canvas: CanvasSpec,
    *,
    element_id: str,
    role: str,
    content: str,
    box: tuple[float, float, float, float],
    font_size: float,
) -> DesignElement:
    x, y, width, height = box
    bbox = BoundingBox(
        x=x * float(canvas.width),
        y=y * float(canvas.height),
        width=width * float(canvas.width),
        height=height * float(canvas.height),
    )
    return DesignElement(
        id=element_id,
        name=role.title(),
        type="text",
        bbox=bbox,
        bbox_norm=normalize_bbox(bbox, canvas),
        z_index=10,
        layer="content",
        text=TextSpec(content=content, font_family="Arial", font_size=font_size),
        visual=VisualSpec(fill=ColorSpec(model="hex", values=["#222222"])),
        metadata={"role": role},
    )


def _document(*, category: str = "spa", width: float = 210, height: float = 297) -> DesignDocument:
    canvas = CanvasSpec(width=width, height=height, unit="mm")
    return DesignDocument(
        sample_id=f"visual:{category}",
        source=SourceSpec(
            name="synthetic_owned",
            split="test",
            license_class="production_safe",
            upstream_id=f"visual:{category}",
            commercial_allowed=True,
        ),
        canvas=canvas,
        category=category,
        elements=[
            _text(
                canvas,
                element_id="headline",
                role="headline",
                content="AN NHIÊN SPA",
                box=(.07, .08, .50, .15),
                font_size=24,
            ),
            _text(
                canvas,
                element_id="body",
                role="body",
                content="Chăm sóc cân bằng và thư giãn",
                box=(.07, .31, .48, .16),
                font_size=11,
            ),
            _text(
                canvas,
                element_id="cta",
                role="cta",
                content="ĐẶT LỊCH",
                box=(.07, .82, .30, .08),
                font_size=12,
            ),
        ],
    )


def test_all_required_profiles_and_unknown_fallback_are_strict() -> None:
    assert set(supported_visual_categories()) == {
        "spa",
        "nail",
        "salon",
        "cafe",
        "milk_tea",
        "restaurant",
        "food_menu",
        "cosmetics",
        "sale",
        "grand_opening",
        "business_card",
        "signage",
        "social_banner",
    }
    assert get_visual_profile("tra_sua").category == "milk_tea"
    assert get_visual_profile("unexpected_vertical").profile_id == "general_v1"


def test_prompt_color_wins_and_contrast_is_deterministic() -> None:
    brief = analyze_brief("Poster spa cao cấp màu kem và vàng", width=210, height=297)
    profile = get_visual_profile(brief.category)
    first = resolve_palette(profile, brief=brief, reference_palette=["pink"])
    second = resolve_palette(profile, brief=brief, reference_palette=["red"])

    assert first == second
    assert first.primary == "#F5EBDD"
    assert first.accent == "#C49A52"
    assert contrast_ratio(first.headline, first.background) >= 4.5
    assert contrast_ratio(first.cta_text, first.cta_background) >= 4.5


def test_spa_visual_engine_adds_editable_asset_and_bounded_decor() -> None:
    original = _document()
    brief = analyze_brief("Thiết kế poster spa cao cấp màu kem và vàng", width=210, height=297)
    visual, report = apply_visual_composition(original, brief=brief)
    fitted, typography = fit_design_typography(visual, allow_expand=False)
    metrics = evaluate_layout(fitted)
    diagnostics = evaluate_visual_quality(fitted, profile=get_visual_profile("spa"))

    placeholders = [item for item in fitted.elements if item.metadata.get("asset_required")]
    decorations = [item for item in fitted.elements if item.metadata.get("decorative_role")]
    assert report.asset_placeholders_created == 1
    assert len(placeholders) == 1
    assert placeholders[0].metadata == {
        **placeholders[0].metadata,
        "asset_required": True,
        "asset_role": "hero",
        "placeholder": True,
        "source_provided": False,
        "editable_placeholder": True,
    }
    assert 1 <= len(decorations) <= get_visual_profile("spa").max_decorative_elements + 2
    assert metrics["outside_canvas_rate"] == 0
    assert metrics["coverage"] > evaluate_layout(original)["coverage"]
    assert typography["truncated_count"] == 0
    assert diagnostics["asset_intent_preservation"] == 1
    operations = compile_corel_operations(fitted)
    assert any(operation["op"] == "create_rectangle" for operation in operations)


def test_existing_hero_placeholder_survives_without_fake_asset() -> None:
    original = _document()
    canvas = original.canvas
    bbox = BoundingBox(x=132, y=73, width=65, height=150)
    original.elements.append(
        DesignElement(
            id="hero_intent",
            name="Hero Intent",
            type="rectangle",
            bbox=bbox,
            bbox_norm=normalize_bbox(bbox, canvas),
            metadata={"asset_intent": {"role": "hero", "placeholder": True}},
        )
    )
    brief = analyze_brief("Poster spa cao cấp", width=210, height=297)
    visual, report = apply_visual_composition(original, brief=brief)
    hero = next(item for item in visual.elements if item.id == "hero_intent")

    assert report.asset_placeholders_created == 0
    assert hero.type == "rectangle"
    assert hero.metadata["asset_role"] == "hero"
    assert hero.metadata["source_provided"] is False
    assert hero.metadata["editable_placeholder"] is True


def test_sale_without_customer_discount_uses_marked_placeholder() -> None:
    original = _document(category="poster_sale")
    brief = analyze_brief("Thiết kế poster MEGA SALE nổi bật", width=210, height=297)
    visual, report = apply_visual_composition(original, brief=brief, benchmark_mode=True)
    placeholders = [
        item for item in visual.elements if item.metadata.get("placeholder_only")
    ]

    assert report.business_placeholder_count == 1
    assert [item.text.content for item in placeholders if item.text] == ["[DISCOUNT]"]
    assert placeholders[0].metadata["requires_user_data"] is True
    assert placeholders[0].metadata["content_provenance"] == "benchmark_placeholder"
    assert placeholders[0].metadata["benchmark_placeholder"] is True
    assert not any("39K" in item.text.content for item in visual.elements if item.text)


def test_ungrounded_campaign_values_are_sanitized_but_user_values_survive() -> None:
    original = _document(category="khai_truong")
    original.elements.extend(
        [
            _text(
                original.canvas,
                element_id="invented_discount",
                role="promotion",
                content="Sale 50% off",
                box=(.08, .50, .40, .08),
                font_size=15,
            ),
            _text(
                original.canvas,
                element_id="invented_offer",
                role="promotion",
                content="Mua 1, tặng 1",
                box=(.08, .60, .40, .08),
                font_size=13,
            ),
            _text(
                original.canvas,
                element_id="invented_date",
                role="body",
                content="Hạn chót ngày 30/10",
                box=(.08, .70, .40, .08),
                font_size=10,
            ),
        ]
    )
    brief = analyze_brief("Thiết kế poster sale khai trương nổi bật", width=210, height=297)
    visual, report = apply_visual_composition(original, brief=brief)
    values = {
        item.id: item.text.content for item in visual.elements if item.text is not None
    }

    assert values["invented_discount"] == "[DISCOUNT]"
    assert values["invented_offer"] == "[OFFER]"
    assert values["invented_date"] == "[DATE]"
    assert report.business_placeholder_count == 3
    sanitized = [
        item
        for item in visual.elements
        if item.metadata.get("sanitized_ungrounded_business_value")
    ]
    assert len(sanitized) == 3
    assert all(item.metadata["content_provenance"] == "system_placeholder" for item in sanitized)
    assert all(item.metadata["requires_user_data"] is True for item in sanitized)

    supplied = _document(category="poster_sale")
    supplied.elements.append(
        _text(
            supplied.canvas,
            element_id="provided_discount",
            role="promotion",
            content="Sale 50% off",
            box=(.08, .50, .40, .08),
            font_size=15,
        )
    )
    supplied_brief = analyze_brief("Poster sale giảm 50%", width=210, height=297)
    grounded, _ = apply_visual_composition(supplied, brief=supplied_brief)
    preserved = next(item for item in grounded.elements if item.id == "provided_discount")
    assert preserved.text is not None and preserved.text.content == "Sale 50% off"
    assert preserved.metadata["content_provenance"] == "model_generated_copy"


def test_light_requested_menu_color_is_not_used_as_price_text() -> None:
    original = _document(category="menu")
    original.elements.append(
        _text(
            original.canvas,
            element_id="price",
            role="price",
            content="39K",
            box=(.75, .40, .18, .08),
            font_size=11,
        )
    )
    brief = analyze_brief(
        "Food menu 6 items with prices, màu kem và vàng",
        width=210,
        height=297,
    )
    visual, _ = apply_visual_composition(original, brief=brief, benchmark_mode=True)
    price = next(item for item in visual.elements if item.id == "price")
    palette = visual.metadata["visual_composition"]["palette"]

    assert price.text is not None and price.text.content == "[PRICE_01]"
    assert contrast_ratio(str(price.visual.fill.values[0]), palette["background"]) >= 4.5


def test_wide_signage_remains_inside_canvas_and_corel_compilable() -> None:
    original = _document(category="bang_hieu", width=4000, height=1200)
    brief = analyze_brief("Bảng hiệu salon hiện đại", width=4000, height=1200)
    visual, _ = apply_visual_composition(original, brief=brief)
    fitted, report = fit_design_typography(visual, allow_expand=False)

    assert evaluate_layout(fitted)["outside_canvas_rate"] == 0
    assert report["truncated_count"] == 0
    assert compile_corel_operations(fitted, width_mm=4000, height_mm=1200)
