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
from training.visual import apply_aesthetic_hardening, apply_visual_composition
from training.visual.hardening import HARDENING_ENGINE_VERSION, evaluate_aesthetic_hardening


def _text(
    canvas: CanvasSpec,
    element_id: str,
    role: str,
    content: str,
    box: tuple[float, float, float, float],
    size: float,
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
        text=TextSpec(content=content, font_family="Arial", font_size=size),
        visual=VisualSpec(fill=ColorSpec(model="hex", values=["#222222"])),
        metadata={"role": role},
    )


def _document(category: str, *, menu: bool = False) -> DesignDocument:
    canvas = CanvasSpec(width=210, height=297, unit="mm")
    elements = [
        _text(canvas, "headline", "headline", "THIẾT KẾ AN NHIÊN", (.05, .06, .56, .14), 21),
        _text(canvas, "body", "body", "Nội dung do khách cung cấp", (.05, .29, .52, .12), 10),
        _text(canvas, "cta", "cta", "ĐẶT LỊCH", (.05, .84, .30, .08), 11),
    ]
    if menu:
        elements = [elements[0]]
        for index in range(4):
            y = .31 + index * .12
            elements.extend(
                [
                    _text(canvas, f"item_{index}", "menu_item", f"[ITEM_{index + 1:02d}]\n[DESCRIPTION_{index + 1:02d}]", (.06, y, .64, .08), 9),
                    _text(canvas, f"price_{index}", "price", f"[PRICE_{index + 1:02d}]", (.76, y, .18, .08), 9),
                ]
            )
    return DesignDocument(
        sample_id=f"hardening:{category}",
        source=SourceSpec(
            name="synthetic_owned",
            split="test",
            license_class="production_safe",
            upstream_id=f"hardening:{category}",
            commercial_allowed=True,
        ),
        canvas=canvas,
        category=category,
        elements=elements,
    )


def _visual(category: str, *, menu: bool = False, prompt: str | None = None):
    request = prompt or f"Thiết kế {category}"
    brief = analyze_brief(request, width=210, height=297)
    base, _ = apply_visual_composition(
        _document(category, menu=menu),
        brief=brief,
        benchmark_mode=True,
    )
    return base, brief


def test_placeholder_presentation_is_soft_explicit_and_editable() -> None:
    base, brief = _visual("spa", prompt="Poster spa cao cấp có ảnh")
    hardened, report = apply_aesthetic_hardening(base, brief=brief)
    placeholder = next(item for item in hardened.elements if item.metadata.get("asset_required"))
    label = next(item for item in hardened.elements if item.metadata.get("placeholder_label") is True)

    assert report["engine"] == HARDENING_ENGINE_VERSION
    assert placeholder.metadata["placeholder_presentation"] == "soft_frame_v1"
    assert placeholder.metadata["requires_real_asset"] is True
    assert label.text is not None and label.text.content in {"PHOTO", "PRODUCT PHOTO", "LOGO", "IMAGE"}
    assert label.metadata["editable"] is True
    assert evaluate_aesthetic_hardening(hardened)["placeholder_quality"] == 1


def test_typography_personality_and_cta_are_category_aware() -> None:
    base, brief = _visual("spa", prompt="Poster spa cao cấp, CTA Đặt lịch")
    hardened, _ = apply_aesthetic_hardening(base, brief=brief)
    headline = next(item for item in hardened.elements if item.metadata.get("role") == "headline")
    cta = next(item for item in hardened.elements if item.metadata.get("role") == "cta")
    containers = [item for item in hardened.elements if item.metadata.get("decorative_role") == "cta_container"]

    assert headline.text is not None and headline.text.font_family == "DejaVuSerif.ttf"
    assert cta.text is not None and cta.text.font_weight == 800
    assert cta.metadata["cta_hardened"] is True
    assert containers and containers[0].metadata["cta_hardened"] is True


def test_menu_refinement_preserves_explicit_prices_and_adds_row_rhythm() -> None:
    base, brief = _visual("menu", menu=True, prompt="Menu nhà hàng 4 món có giá")
    before = [item.text.content for item in base.elements if item.text]
    hardened, report = apply_aesthetic_hardening(base, brief=brief)
    after = [
        item.text.content for item in hardened.elements
        if item.text and not item.metadata.get("placeholder_label")
    ]

    assert after == before
    assert report["fake_customer_data_added"] is False
    assert report["menu_decoration_count"] >= 3
    assert all("39K" not in content for content in after)
    assert all(
        item.text.alignment == "right"
        for item in hardened.elements
        if item.metadata.get("role") == "price" and item.text
    )


def test_sale_hardening_does_not_invent_offer_or_date() -> None:
    base, brief = _visual("poster_sale", prompt="Poster MEGA SALE nổi bật, CTA Mua ngay")
    before = [item.text.content for item in base.elements if item.text]
    hardened, report = apply_aesthetic_hardening(base, brief=brief)
    after = [
        item.text.content for item in hardened.elements
        if item.text and not item.metadata.get("placeholder_label")
    ]

    assert after == before
    assert report["campaign_decoration_count"] == 3
    assert not any(value in " ".join(after) for value in ("39K", "50%", "30/10"))


def test_hardening_is_deterministic_bounded_and_corel_compatible() -> None:
    base, brief = _visual("bang_hieu", prompt="Bảng hiệu salon hiện đại có logo")
    first, _ = apply_aesthetic_hardening(base, brief=brief)
    second, _ = apply_aesthetic_hardening(base, brief=brief)
    fitted, typography = fit_design_typography(first, allow_expand=False)

    assert first == second
    assert evaluate_layout(fitted)["outside_canvas_rate"] == 0
    assert typography["truncated_count"] == 0
    assert compile_corel_operations(fitted)
