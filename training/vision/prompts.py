"""Neutral, category-aware prompts for the local vision critic."""

from __future__ import annotations

import json

from training.schemas.design import DesignDocument


CATEGORY_INTENT = {
    "spa": "premium, calm, intentional whitespace, restrained decoration",
    "cafe": "warm, friendly, clear beverage focal point, social readability",
    "sale": "strong campaign hierarchy, product focal point, prominent CTA, visual energy",
    "food_menu": "scanability, grouping, aligned prices, supporting food image, not spreadsheet-like",
    "signage": "distance readability, name/logo dominance, minimal clutter, strong contrast",
}

ISSUES = (
    "weak_focal_point, hero_too_small, hero_too_large, weak_headline, "
    "headline_too_large, headline_too_small, weak_cta, cta_too_large, "
    "cta_too_small, poor_visual_balance, excessive_whitespace, "
    "insufficient_whitespace, uneven_spacing, weak_hierarchy, flat_typography, "
    "poor_text_grouping, poor_image_text_balance, low_contrast, "
    "palette_incoherence, too_much_decoration, too_little_decoration, "
    "menu_spreadsheet_feel, menu_grouping_weak, campaign_energy_low, "
    "logo_too_small, logo_too_large, logo_competes_with_headline, asset_crop_awkward"
)


def compact_document_summary(document: DesignDocument) -> dict[str, object]:
    rows = []
    for element in document.elements:
        role = element.metadata.get("role") or element.metadata.get("asset_role")
        if not role:
            continue
        rows.append(
            {
                "role": str(role),
                "type": element.type,
                "bbox": [
                    round(float(element.bbox_norm.x), 3),
                    round(float(element.bbox_norm.y), 3),
                    round(float(element.bbox_norm.width), 3),
                    round(float(element.bbox_norm.height), 3),
                ],
            }
        )
    return {"category": document.category, "elements": rows[:20]}


def critique_prompt(
    *, brief: str, category: str, business_content: dict[str, object],
    asset_roles: list[str], document: DesignDocument,
) -> str:
    intent = CATEGORY_INTENT.get(category, "clear hierarchy, balance, readable professional presentation")
    context = {
        "brief": brief,
        "category_intent": intent,
        "canvas": [float(document.canvas.width), float(document.canvas.height)],
        "supplied_business_content": business_content,
        "available_asset_roles": asset_roles,
        "layout_summary": compact_document_summary(document),
    }
    return f"""Act as a neutral visual design reviewer. Inspect the rendered image, not hidden scores.
Context: {json.dumps(context, ensure_ascii=False, separators=(',', ':'))}
Judge focal point, balance, hierarchy, image/text relationship, whitespace, typography, CTA, palette/contrast, category fit, rhythm, and professional presentation. Distinguish technical defects from aesthetic preferences.
Return JSON only with keys overall and issues. overall must contain evidence-based decimal quality_score and confidence values between 0 and 1. Never output zero confidence unless the image is unreadable. Each issue must contain issue_type, severity, a nonzero confidence decimal, target_role, reason, recommended_action, and magnitude. Return at most 2 issues; keep each reason under 12 words.
Allowed target_role: hero, headline, cta, layout, typography, palette, decoration, menu, logo.
Allowed recommended_action: increase_area, decrease_area, increase_emphasis, decrease_emphasis, rebalance, increase_contrast, harmonize_palette, add_bounded_decoration, reduce_decoration, improve_grouping.
Allowed issue_type: {ISSUES}.
Never invent or rewrite prices, offers, dates, phones, addresses, menu values, CTA copy, products, logos, or assets. Never output commands. Prefer the 1-2 most actionable visible issues."""


def pairwise_prompt(*, brief: str, category: str) -> str:
    intent = CATEGORY_INTENT.get(category, "clear hierarchy and professional presentation")
    return f"""Compare Image A and Image B blindly for this brief: {brief}
Category intent: {intent}.
Judge focal hierarchy, balance, typography, CTA, image/text relationship, whitespace, contrast, and professional presentation. Do not assume either is newer. Return JSON only:
Use keys preferred, confidence, reasons. preferred is A, B, or tie; confidence is an evidence-based decimal between 0 and 1; reasons is one to three short observable strings.
Do not infer or reward invented business facts."""


__all__ = ["CATEGORY_INTENT", "compact_document_summary", "critique_prompt", "pairwise_prompt"]
