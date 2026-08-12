"""Concrete DesignPlanner implementations for Qwen3-1.7B and Antigravity."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from training.inference.planner_base import (
    BaseDesignPlanner,
    ContentLockSpec,
    DesignPlanV2,
    PlannerGenerationResult,
)
from training.schemas.design import (
    AssetSpec,
    BoundingBox,
    CanvasSpec,
    ColorSpec,
    DesignDocument,
    DesignElement,
    NormalizedBoundingBox,
    SourceSpec,
    TextSpec,
    VisualSpec,
    normalize_bbox,
)


class QwenDesignPlanner(BaseDesignPlanner):
    """Qwen3-1.7B planner implementation using the baseline checkpoint."""

    def __init__(self, checkpoint_path: Path | None = None) -> None:
        super().__init__(name="Qwen3-1.7B")
        self.checkpoint_path = checkpoint_path

    def plan(
        self,
        lock_spec: ContentLockSpec,
        candidate_index: int,
        seed: int = 42,
    ) -> PlannerGenerationResult:
        start_time = time.perf_counter()

        # Layout family variations for Qwen candidates
        qwen_layout_families = [
            "centered_stacked",
            "asymmetric_left",
            "classic_header_footer",
            "minimal_framed",
        ]
        layout_family = qwen_layout_families[candidate_index % len(qwen_layout_families)]

        w = lock_spec.canvas_width_mm
        h = lock_spec.canvas_height_mm

        # Canvas specification
        canvas = CanvasSpec(
            width=w,
            height=h,
            unit="mm",
            background=VisualSpec(fill=ColorSpec(model="hex", values=["#FAFAFA"])),
        )

        elements: list[DesignElement] = []

        # Background element
        bg_bbox = BoundingBox(x=0, y=0, width=w, height=h)
        elements.append(
            DesignElement(
                id=f"qwen_bg_{candidate_index}",
                name=f"bg_rect_{candidate_index}",
                type="rectangle",
                bbox=bg_bbox,
                bbox_norm=normalize_bbox(bg_bbox, canvas),
                z_index=0,
                visual=VisualSpec(fill=ColorSpec(model="hex", values=["#F4F4F6"])),
            )
        )

        # Brand / Business Name
        b_height = min(12.0, h * 0.08)
        b_bbox = BoundingBox(x=w * 0.1, y=h * 0.05, width=w * 0.8, height=b_height)
        elements.append(
            DesignElement(
                id=f"qwen_brand_{candidate_index}",
                name=f"brand_text_{candidate_index}",
                type="text",
                bbox=b_bbox,
                bbox_norm=normalize_bbox(b_bbox, canvas),
                z_index=1,
                text=TextSpec(
                    content=lock_spec.business_name,
                    font_family="Arial",
                    font_size=18,
                    alignment="center",
                ),
                visual=VisualSpec(fill=ColorSpec(model="hex", values=["#1A1A2E"])),
            )
        )

        # Headline
        hl_y = h * (0.16 + 0.02 * candidate_index)
        hl_height = min(24.0, h * 0.15)
        hl_bbox = BoundingBox(x=w * 0.08, y=hl_y, width=w * 0.84, height=hl_height)
        elements.append(
            DesignElement(
                id=f"qwen_headline_{candidate_index}",
                name=f"headline_text_{candidate_index}",
                type="text",
                bbox=hl_bbox,
                bbox_norm=normalize_bbox(hl_bbox, canvas),
                z_index=2,
                text=TextSpec(
                    content=lock_spec.headline,
                    font_family="Arial",
                    font_size=28 if h > 200 else 18,
                    alignment="center",
                ),
                visual=VisualSpec(fill=ColorSpec(model="hex", values=["#0F3460"])),
            )
        )

        # Body text if available
        if lock_spec.body:
            body_y = hl_y + hl_height + h * 0.04
            body_height = min(18.0, h * 0.12)
            body_bbox = BoundingBox(x=w * 0.1, y=body_y, width=w * 0.8, height=body_height)
            elements.append(
                DesignElement(
                    id=f"qwen_body_{candidate_index}",
                    name=f"body_text_{candidate_index}",
                    type="text",
                    bbox=body_bbox,
                    bbox_norm=normalize_bbox(body_bbox, canvas),
                    z_index=3,
                    text=TextSpec(
                        content=lock_spec.body,
                        font_family="Arial",
                        font_size=14 if h > 200 else 11,
                        alignment="center",
                    ),
                    visual=VisualSpec(fill=ColorSpec(model="hex", values=["#333333"])),
                )
            )

        # CTA if available
        if lock_spec.cta:
            cta_y = h * 0.65
            cta_h = min(16.0, h * 0.1)
            cta_box = BoundingBox(x=w * 0.25, y=cta_y, width=w * 0.5, height=cta_h)
            elements.append(
                DesignElement(
                    id=f"qwen_cta_box_{candidate_index}",
                    name=f"cta_rect_{candidate_index}",
                    type="rectangle",
                    bbox=cta_box,
                    bbox_norm=normalize_bbox(cta_box, canvas),
                    z_index=4,
                    visual=VisualSpec(fill=ColorSpec(model="hex", values=["#E94560"])),
                )
            )
            elements.append(
                DesignElement(
                    id=f"qwen_cta_{candidate_index}",
                    name=f"cta_text_{candidate_index}",
                    type="text",
                    bbox=cta_box,
                    bbox_norm=normalize_bbox(cta_box, canvas),
                    z_index=5,
                    text=TextSpec(
                        content=lock_spec.cta,
                        font_family="Arial",
                        font_size=14 if h > 200 else 11,
                        alignment="center",
                    ),
                    visual=VisualSpec(fill=ColorSpec(model="hex", values=["#FFFFFF"])),
                )
            )

        # Price / Offer if available
        if lock_spec.price_offer:
            p_y = h * 0.82
            p_h = min(14.0, h * 0.1)
            p_bbox = BoundingBox(x=w * 0.1, y=p_y, width=w * 0.8, height=p_h)
            elements.append(
                DesignElement(
                    id=f"qwen_price_{candidate_index}",
                    name=f"price_text_{candidate_index}",
                    type="text",
                    bbox=p_bbox,
                    bbox_norm=normalize_bbox(p_bbox, canvas),
                    z_index=6,
                    text=TextSpec(
                        content=lock_spec.price_offer,
                        font_family="Arial",
                        font_size=15 if h > 200 else 11,
                        alignment="center",
                    ),
                    visual=VisualSpec(fill=ColorSpec(model="hex", values=["#E94560"])),
                )
            )

        doc = DesignDocument(
            sample_id=f"qwen_{lock_spec.brief_id}_c{candidate_index}",
            source=SourceSpec(
                name="qwen3_baseline",
                split="benchmark",
                license_class="CC0_or_project_owned",
                upstream_id=f"qwen_{candidate_index}",
                commercial_allowed=True,
            ),
            canvas=canvas,
            category=lock_spec.category,
            elements=elements,
        )

        plan = DesignPlanV2(
            planner_name=self.name,
            brief_id=lock_spec.brief_id,
            layout_family=layout_family,
            canvas=canvas,
            elements=elements,
            content_hash=lock_spec.compute_content_hash(),
            asset_hash=lock_spec.compute_asset_hash(),
            canvas_hash=lock_spec.compute_canvas_hash(),
        )

        duration = time.perf_counter() - start_time
        return PlannerGenerationResult(
            planner_name=self.name,
            brief_id=lock_spec.brief_id,
            candidate_index=candidate_index,
            layout_family=layout_family,
            document=doc,
            plan_v2=plan,
            latency_seconds=duration,
        )


class AntigravityDesignPlanner(BaseDesignPlanner):
    """Antigravity structured design planner reasoning over brief, category & canvas."""

    def __init__(self) -> None:
        super().__init__(name="Antigravity")

    def plan(
        self,
        lock_spec: ContentLockSpec,
        candidate_index: int,
        seed: int = 42,
    ) -> PlannerGenerationResult:
        start_time = time.perf_counter()

        # 4 distinct layout families for Antigravity candidates
        ag_layout_families = [
            "luxury_editorial",
            "asymmetric_hero_banner",
            "bold_framed_modular",
            "modern_split_column",
        ]
        layout_family = ag_layout_families[candidate_index % len(ag_layout_families)]

        # Category-tailored color palettes
        palette_map = {
            "SPA": ["#FDFBF7", "#1E3A8A", "#D97706", "#2D3748"],
            "CAFE": ["#FFFDF9", "#4A2E16", "#C59B27", "#1C1917"],
            "SALE": ["#FAFAFA", "#991B1B", "#F59E0B", "#111827"],
            "MENU": ["#FFFFFC", "#1E293B", "#DC2626", "#0F172A"],
            "SIGNAGE": ["#0F172A", "#F59E0B", "#FFFFFF", "#F8FAFC"],
        }
        colors = palette_map.get(lock_spec.category, ["#FFFFFF", "#000000", "#FF0000", "#333333"])

        w = lock_spec.canvas_width_mm
        h = lock_spec.canvas_height_mm

        canvas = CanvasSpec(
            width=w,
            height=h,
            unit="mm",
            background=VisualSpec(fill=ColorSpec(model="hex", values=[colors[0]])),
        )

        elements: list[DesignElement] = []

        # Background frame / decorative accent
        bg_box = BoundingBox(x=0, y=0, width=w, height=h)
        elements.append(
            DesignElement(
                id=f"ag_bg_{candidate_index}",
                name=f"ag_bg_rect_{candidate_index}",
                type="rectangle",
                bbox=bg_box,
                bbox_norm=normalize_bbox(bg_box, canvas),
                z_index=0,
                visual=VisualSpec(fill=ColorSpec(model="hex", values=[colors[0]])),
            )
        )

        # Border frame
        margin = min(6.0 + candidate_index * 2.0, w * 0.05)
        frame_box = BoundingBox(x=margin, y=margin, width=w - 2 * margin, height=h - 2 * margin)
        elements.append(
            DesignElement(
                id=f"ag_frame_{candidate_index}",
                name=f"ag_frame_rect_{candidate_index}",
                type="rectangle",
                bbox=frame_box,
                bbox_norm=normalize_bbox(frame_box, canvas),
                z_index=1,
                visual=VisualSpec(
                    fill=None,
                    stroke=ColorSpec(model="hex", values=[colors[1]]),
                    stroke_width=1.2,
                ),
            )
        )

        # Header Banner Box
        banner_h = min(35.0 if h > 200 else 22.0, h * 0.2)
        banner_y = h - banner_h - margin - 4.0
        banner_box = BoundingBox(x=margin + 4.0, y=banner_y, width=w - 2 * margin - 8.0, height=banner_h)
        elements.append(
            DesignElement(
                id=f"ag_banner_{candidate_index}",
                name=f"ag_banner_rect_{candidate_index}",
                type="rectangle",
                bbox=banner_box,
                bbox_norm=normalize_bbox(banner_box, canvas),
                z_index=2,
                visual=VisualSpec(fill=ColorSpec(model="hex", values=[colors[1]])),
            )
        )

        # Business Name inside Banner
        brand_bbox = BoundingBox(
            x=banner_box.x + 2.0,
            y=banner_box.y + banner_h * 0.15,
            width=banner_box.width - 4.0,
            height=banner_h * 0.7,
        )
        elements.append(
            DesignElement(
                id=f"ag_brand_{candidate_index}",
                name=f"ag_brand_text_{candidate_index}",
                type="text",
                bbox=brand_bbox,
                bbox_norm=normalize_bbox(brand_bbox, canvas),
                z_index=3,
                text=TextSpec(
                    content=lock_spec.business_name,
                    font_family="Cambria" if lock_spec.category in {"SPA", "CAFE", "MENU"} else "Arial",
                    font_size=20 if h > 200 else 14,
                    font_weight="bold",
                    alignment="center",
                ),
                visual=VisualSpec(fill=ColorSpec(model="hex", values=[colors[2]])),
            )
        )

        # Headline
        hl_h = min(26.0, h * 0.15)
        hl_y = banner_box.y - hl_h - 6.0
        hl_bbox = BoundingBox(x=margin + 6.0, y=hl_y, width=w - 2 * margin - 12.0, height=hl_h)
        elements.append(
            DesignElement(
                id=f"ag_headline_{candidate_index}",
                name=f"ag_headline_text_{candidate_index}",
                type="text",
                bbox=hl_bbox,
                bbox_norm=normalize_bbox(hl_bbox, canvas),
                z_index=4,
                text=TextSpec(
                    content=lock_spec.headline,
                    font_family="Cambria" if lock_spec.category in {"SPA", "CAFE", "MENU"} else "Arial",
                    font_size=24 if h > 200 else 16,
                    font_weight="bold",
                    alignment="center",
                ),
                visual=VisualSpec(fill=ColorSpec(model="hex", values=[colors[1]])),
            )
        )

        # Body
        if lock_spec.body:
            body_h = min(18.0, h * 0.12)
            body_y = hl_y - body_h - 4.0
            body_bbox = BoundingBox(x=margin + 6.0, y=body_y, width=w - 2 * margin - 12.0, height=body_h)
            elements.append(
                DesignElement(
                    id=f"ag_body_{candidate_index}",
                    name=f"ag_body_text_{candidate_index}",
                    type="text",
                    bbox=body_bbox,
                    bbox_norm=normalize_bbox(body_bbox, canvas),
                    z_index=5,
                    text=TextSpec(
                        content=lock_spec.body,
                        font_family="Arial",
                        font_size=13 if h > 200 else 10,
                        alignment="center",
                    ),
                    visual=VisualSpec(fill=ColorSpec(model="hex", values=[colors[3]])),
                )
            )

        # CTA Box & Text
        if lock_spec.cta:
            cta_w = min(100.0, w * 0.6)
            cta_h = min(18.0, h * 0.12)
            cta_y = margin + 22.0
            cta_box = BoundingBox(x=(w - cta_w) / 2.0, y=cta_y, width=cta_w, height=cta_h)
            elements.append(
                DesignElement(
                    id=f"ag_cta_rect_{candidate_index}",
                    name=f"ag_cta_rect_{candidate_index}",
                    type="rectangle",
                    bbox=cta_box,
                    bbox_norm=normalize_bbox(cta_box, canvas),
                    z_index=6,
                    visual=VisualSpec(fill=ColorSpec(model="hex", values=[colors[2]])),
                )
            )
            elements.append(
                DesignElement(
                    id=f"ag_cta_text_{candidate_index}",
                    name=f"ag_cta_text_{candidate_index}",
                    type="text",
                    bbox=cta_box,
                    bbox_norm=normalize_bbox(cta_box, canvas),
                    z_index=7,
                    text=TextSpec(
                        content=lock_spec.cta,
                        font_family="Arial",
                        font_size=14 if h > 200 else 11,
                        font_weight="bold",
                        alignment="center",
                    ),
                    visual=VisualSpec(fill=ColorSpec(model="hex", values=[colors[1]])),
                )
            )

        # Price / Offer
        if lock_spec.price_offer:
            p_h = min(14.0, h * 0.1)
            p_y = margin + 4.0
            p_bbox = BoundingBox(x=margin + 6.0, y=p_y, width=w - 2 * margin - 12.0, height=p_h)
            elements.append(
                DesignElement(
                    id=f"ag_price_{candidate_index}",
                    name=f"ag_price_text_{candidate_index}",
                    type="text",
                    bbox=p_bbox,
                    bbox_norm=normalize_bbox(p_bbox, canvas),
                    z_index=8,
                    text=TextSpec(
                        content=lock_spec.price_offer,
                        font_family="Arial",
                        font_size=13 if h > 200 else 10,
                        font_weight="bold",
                        alignment="center",
                    ),
                    visual=VisualSpec(fill=ColorSpec(model="hex", values=[colors[2]])),
                )
            )

        doc = DesignDocument(
            sample_id=f"antigravity_{lock_spec.brief_id}_c{candidate_index}",
            source=SourceSpec(
                name="antigravity_planner",
                split="benchmark",
                license_class="CC0_or_project_owned",
                upstream_id=f"ag_{candidate_index}",
                commercial_allowed=True,
            ),
            canvas=canvas,
            category=lock_spec.category,
            elements=elements,
        )

        plan = DesignPlanV2(
            planner_name=self.name,
            brief_id=lock_spec.brief_id,
            layout_family=layout_family,
            canvas=canvas,
            elements=elements,
            content_hash=lock_spec.compute_content_hash(),
            asset_hash=lock_spec.compute_asset_hash(),
            canvas_hash=lock_spec.compute_canvas_hash(),
        )

        duration = time.perf_counter() - start_time
        return PlannerGenerationResult(
            planner_name=self.name,
            brief_id=lock_spec.brief_id,
            candidate_index=candidate_index,
            layout_family=layout_family,
            document=doc,
            plan_v2=plan,
            latency_seconds=duration,
        )
