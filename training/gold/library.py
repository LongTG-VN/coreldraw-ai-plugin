"""Initial Gold Library containing 15 provisional Gold Design Grammars across 5 categories."""

from __future__ import annotations

import json
from pathlib import Path
from training.schemas.design import NormalizedBoundingBox
from training.schemas.gold import (
    GoldAssetRegionV1,
    GoldDesignGrammarV1,
    GoldPaletteStrategyV1,
    GoldRelationshipV1,
    GoldSlotV1,
    GoldSpacingGrammarV1,
    GoldTypographyRoleV1,
)


GOLD_LIBRARY_DIR = Path("training/data/gold_designs/v1")


def _build_provisional_grammars() -> list[GoldDesignGrammarV1]:
    grammars: list[GoldDesignGrammarV1] = []

    # ==================== SPA CATEGORY ====================
    # 1. gold_spa_001: Luxury Serenity Editorial
    grammars.append(
        GoldDesignGrammarV1(
            grammar_id="gold_spa_001",
            grammar_name="Luxury Serenity Editorial",
            category="SPA",
            canvas_aspect_ratio=0.707,
            gold_status="PROVISIONAL",
            slots=[
                GoldSlotV1(slot_id="bg", role="BACKGROUND", bbox_norm=NormalizedBoundingBox(x=0, y=0, width=1, height=1), z_index=0),
                GoldSlotV1(slot_id="frame", role="DECORATION", bbox_norm=NormalizedBoundingBox(x=0.04, y=0.04, width=0.92, height=0.92), z_index=1),
                GoldSlotV1(slot_id="banner", role="DECORATION", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.78, width=0.84, height=0.16), z_index=2),
                GoldSlotV1(slot_id="brand", role="BRAND", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.8, width=0.8, height=0.1), z_index=3),
                GoldSlotV1(slot_id="headline", role="HEADLINE", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.6, width=0.84, height=0.14), z_index=4),
                GoldSlotV1(slot_id="body", role="BODY", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.48, width=0.8, height=0.08), z_index=5),
                GoldSlotV1(slot_id="cta", role="CTA", bbox_norm=NormalizedBoundingBox(x=0.25, y=0.2, width=0.5, height=0.08), z_index=6),
                GoldSlotV1(slot_id="offer", role="OFFER", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.08, width=0.8, height=0.08), z_index=7),
            ],
            relationships=[
                GoldRelationshipV1(source_slot_id="headline", target_slot_id="body", relationship="ABOVE"),
                GoldRelationshipV1(source_slot_id="body", target_slot_id="cta", relationship="ABOVE"),
            ],
            typography_grammar={
                "HEADLINE": GoldTypographyRoleV1(role="HEADLINE", family_class="display_serif", weight=700, relative_scale=2.2, alignment="center"),
                "BRAND": GoldTypographyRoleV1(role="BRAND", family_class="display_serif", weight=700, relative_scale=1.6, alignment="center"),
                "BODY": GoldTypographyRoleV1(role="BODY", family_class="neutral_sans", weight=400, relative_scale=1.0, alignment="center"),
                "CTA": GoldTypographyRoleV1(role="CTA", family_class="neutral_sans", weight=700, relative_scale=1.1, alignment="center", uppercase=True),
            },
            palette_strategy=GoldPaletteStrategyV1(
                background_color="#FDFBF7", surface_color="#F4EFE6", primary_color="#1E3A8A", secondary_color="#475569", accent_color="#D97706"
            ),
        )
    )

    # 2. gold_spa_002: Asymmetric Herbal Wellness
    grammars.append(
        GoldDesignGrammarV1(
            grammar_id="gold_spa_002",
            grammar_name="Asymmetric Herbal Wellness",
            category="SPA",
            canvas_aspect_ratio=0.707,
            gold_status="PROVISIONAL",
            slots=[
                GoldSlotV1(slot_id="bg", role="BACKGROUND", bbox_norm=NormalizedBoundingBox(x=0, y=0, width=1, height=1), z_index=0),
                GoldSlotV1(slot_id="brand", role="BRAND", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.82, width=0.6, height=0.12), z_index=1),
                GoldSlotV1(slot_id="headline", role="HEADLINE", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.55, width=0.7, height=0.22), z_index=2),
                GoldSlotV1(slot_id="body", role="BODY", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.38, width=0.7, height=0.12), z_index=3),
                GoldSlotV1(slot_id="cta", role="CTA", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.18, width=0.45, height=0.09), z_index=4),
                GoldSlotV1(slot_id="offer", role="OFFER", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.06, width=0.5, height=0.08), z_index=5),
            ],
            relationships=[
                GoldRelationshipV1(source_slot_id="headline", target_slot_id="body", relationship="ALIGN_LEFT"),
            ],
            typography_grammar={
                "HEADLINE": GoldTypographyRoleV1(role="HEADLINE", family_class="display_serif", weight=700, relative_scale=2.4, alignment="left"),
                "BRAND": GoldTypographyRoleV1(role="BRAND", family_class="neutral_sans", weight=700, relative_scale=1.4, alignment="left"),
                "BODY": GoldTypographyRoleV1(role="BODY", family_class="neutral_sans", weight=400, relative_scale=1.0, alignment="left"),
            },
            palette_strategy=GoldPaletteStrategyV1(
                background_color="#F7F9F6", surface_color="#E2E8F0", primary_color="#14532D", secondary_color="#334155", accent_color="#15803D"
            ),
        )
    )

    # 3. gold_spa_003: Minimal Zen Sanctuary
    grammars.append(
        GoldDesignGrammarV1(
            grammar_id="gold_spa_003",
            grammar_name="Minimal Zen Sanctuary",
            category="SPA",
            canvas_aspect_ratio=0.707,
            gold_status="PROVISIONAL",
            slots=[
                GoldSlotV1(slot_id="bg", role="BACKGROUND", bbox_norm=NormalizedBoundingBox(x=0, y=0, width=1, height=1), z_index=0),
                GoldSlotV1(slot_id="brand", role="BRAND", bbox_norm=NormalizedBoundingBox(x=0.15, y=0.84, width=0.7, height=0.09), z_index=1),
                GoldSlotV1(slot_id="headline", role="HEADLINE", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.62, width=0.8, height=0.18), z_index=2),
                GoldSlotV1(slot_id="body", role="BODY", bbox_norm=NormalizedBoundingBox(x=0.12, y=0.44, width=0.76, height=0.12), z_index=3),
                GoldSlotV1(slot_id="cta", role="CTA", bbox_norm=NormalizedBoundingBox(x=0.2, y=0.22, width=0.6, height=0.08), z_index=4),
                GoldSlotV1(slot_id="offer", role="OFFER", bbox_norm=NormalizedBoundingBox(x=0.15, y=0.08, width=0.7, height=0.08), z_index=5),
            ],
            typography_grammar={
                "HEADLINE": GoldTypographyRoleV1(role="HEADLINE", family_class="display_serif", weight=400, relative_scale=2.0, alignment="center"),
            },
            palette_strategy=GoldPaletteStrategyV1(
                background_color="#FAF9F6", primary_color="#1E293B", accent_color="#B45309"
            ),
        )
    )

    # ==================== CAFE CATEGORY ====================
    # 4. gold_cafe_001: Artisan Sai Gon Espresso
    grammars.append(
        GoldDesignGrammarV1(
            grammar_id="gold_cafe_001",
            grammar_name="Artisan Sai Gon Espresso",
            category="CAFE",
            canvas_aspect_ratio=0.707,
            gold_status="PROVISIONAL",
            slots=[
                GoldSlotV1(slot_id="bg", role="BACKGROUND", bbox_norm=NormalizedBoundingBox(x=0, y=0, width=1, height=1), z_index=0),
                GoldSlotV1(slot_id="banner", role="DECORATION", bbox_norm=NormalizedBoundingBox(x=0.05, y=0.78, width=0.9, height=0.18), z_index=1),
                GoldSlotV1(slot_id="brand", role="BRAND", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.81, width=0.84, height=0.12), z_index=2),
                GoldSlotV1(slot_id="headline", role="HEADLINE", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.58, width=0.84, height=0.16), z_index=3),
                GoldSlotV1(slot_id="body", role="BODY", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.42, width=0.8, height=0.1), z_index=4),
                GoldSlotV1(slot_id="cta", role="CTA", bbox_norm=NormalizedBoundingBox(x=0.2, y=0.22, width=0.6, height=0.09), z_index=5),
                GoldSlotV1(slot_id="offer", role="OFFER", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.08, width=0.8, height=0.08), z_index=6),
            ],
            typography_grammar={
                "HEADLINE": GoldTypographyRoleV1(role="HEADLINE", family_class="condensed_sans", weight=700, relative_scale=2.2, alignment="center"),
                "BRAND": GoldTypographyRoleV1(role="BRAND", family_class="display_serif", weight=700, relative_scale=1.5, alignment="center"),
            },
            palette_strategy=GoldPaletteStrategyV1(
                background_color="#FFFDF9", surface_color="#4A2E16", primary_color="#4A2E16", secondary_color="#78350F", accent_color="#C59B27"
            ),
        )
    )

    # 5. gold_cafe_002: Warm Wood Tea & Coffee
    grammars.append(
        GoldDesignGrammarV1(
            grammar_id="gold_cafe_002",
            grammar_name="Warm Wood Tea & Coffee",
            category="CAFE",
            canvas_aspect_ratio=0.707,
            gold_status="PROVISIONAL",
            slots=[
                GoldSlotV1(slot_id="bg", role="BACKGROUND", bbox_norm=NormalizedBoundingBox(x=0, y=0, width=1, height=1), z_index=0),
                GoldSlotV1(slot_id="frame", role="DECORATION", bbox_norm=NormalizedBoundingBox(x=0.05, y=0.05, width=0.9, height=0.9), z_index=1),
                GoldSlotV1(slot_id="brand", role="BRAND", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.82, width=0.8, height=0.1), z_index=2),
                GoldSlotV1(slot_id="headline", role="HEADLINE", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.6, width=0.84, height=0.16), z_index=3),
                GoldSlotV1(slot_id="body", role="BODY", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.45, width=0.8, height=0.1), z_index=4),
                GoldSlotV1(slot_id="cta", role="CTA", bbox_norm=NormalizedBoundingBox(x=0.22, y=0.22, width=0.56, height=0.09), z_index=5),
                GoldSlotV1(slot_id="offer", role="OFFER", bbox_norm=NormalizedBoundingBox(x=0.15, y=0.08, width=0.7, height=0.08), z_index=6),
            ],
            palette_strategy=GoldPaletteStrategyV1(
                background_color="#FDFBF7", primary_color="#271C19", accent_color="#D97706"
            ),
        )
    )

    # 6. gold_cafe_003: Modern Split Beverage
    grammars.append(
        GoldDesignGrammarV1(
            grammar_id="gold_cafe_003",
            grammar_name="Modern Split Beverage",
            category="CAFE",
            canvas_aspect_ratio=0.707,
            gold_status="PROVISIONAL",
            slots=[
                GoldSlotV1(slot_id="bg", role="BACKGROUND", bbox_norm=NormalizedBoundingBox(x=0, y=0, width=1, height=1), z_index=0),
                GoldSlotV1(slot_id="brand", role="BRAND", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.84, width=0.84, height=0.1), z_index=1),
                GoldSlotV1(slot_id="headline", role="HEADLINE", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.62, width=0.84, height=0.16), z_index=2),
                GoldSlotV1(slot_id="body", role="BODY", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.46, width=0.84, height=0.1), z_index=3),
                GoldSlotV1(slot_id="cta", role="CTA", bbox_norm=NormalizedBoundingBox(x=0.15, y=0.24, width=0.7, height=0.09), z_index=4),
                GoldSlotV1(slot_id="offer", role="OFFER", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.08, width=0.8, height=0.08), z_index=5),
            ],
            palette_strategy=GoldPaletteStrategyV1(
                background_color="#FEFCE8", primary_color="#713F12", accent_color="#CA8A04"
            ),
        )
    )

    # ==================== SALE CATEGORY ====================
    # 7. gold_sale_001: Urban Summer Mega Sale
    grammars.append(
        GoldDesignGrammarV1(
            grammar_id="gold_sale_001",
            grammar_name="Urban Summer Mega Sale",
            category="SALE",
            canvas_aspect_ratio=0.707,
            gold_status="PROVISIONAL",
            slots=[
                GoldSlotV1(slot_id="bg", role="BACKGROUND", bbox_norm=NormalizedBoundingBox(x=0, y=0, width=1, height=1), z_index=0),
                GoldSlotV1(slot_id="brand", role="BRAND", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.84, width=0.8, height=0.1), z_index=1),
                GoldSlotV1(slot_id="headline", role="HEADLINE", bbox_norm=NormalizedBoundingBox(x=0.05, y=0.58, width=0.9, height=0.2), z_index=2),
                GoldSlotV1(slot_id="body", role="BODY", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.42, width=0.8, height=0.1), z_index=3),
                GoldSlotV1(slot_id="cta", role="CTA", bbox_norm=NormalizedBoundingBox(x=0.2, y=0.22, width=0.6, height=0.1), z_index=4),
                GoldSlotV1(slot_id="offer", role="OFFER", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.06, width=0.8, height=0.1), z_index=5),
            ],
            typography_grammar={
                "HEADLINE": GoldTypographyRoleV1(role="HEADLINE", family_class="condensed_sans", weight=900, relative_scale=3.0, alignment="center", uppercase=True),
                "CTA": GoldTypographyRoleV1(role="CTA", family_class="condensed_sans", weight=800, relative_scale=1.4, alignment="center", uppercase=True),
            },
            palette_strategy=GoldPaletteStrategyV1(
                background_color="#FAFAFA", primary_color="#991B1B", secondary_color="#1E293B", accent_color="#F59E0B", contrast_strategy="high_contrast"
            ),
        )
    )

    # 8. gold_sale_002: Flash Deal Asymmetric
    grammars.append(
        GoldDesignGrammarV1(
            grammar_id="gold_sale_002",
            grammar_name="Flash Deal Asymmetric",
            category="SALE",
            canvas_aspect_ratio=0.707,
            gold_status="PROVISIONAL",
            slots=[
                GoldSlotV1(slot_id="bg", role="BACKGROUND", bbox_norm=NormalizedBoundingBox(x=0, y=0, width=1, height=1), z_index=0),
                GoldSlotV1(slot_id="brand", role="BRAND", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.85, width=0.6, height=0.1), z_index=1),
                GoldSlotV1(slot_id="headline", role="HEADLINE", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.58, width=0.84, height=0.22), z_index=2),
                GoldSlotV1(slot_id="body", role="BODY", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.42, width=0.7, height=0.1), z_index=3),
                GoldSlotV1(slot_id="cta", role="CTA", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.22, width=0.5, height=0.1), z_index=4),
                GoldSlotV1(slot_id="offer", role="OFFER", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.06, width=0.6, height=0.1), z_index=5),
            ],
            palette_strategy=GoldPaletteStrategyV1(
                background_color="#FFF1F2", primary_color="#BE123C", accent_color="#FBBF24"
            ),
        )
    )

    # 9. gold_sale_003: Bold Framed Discount
    grammars.append(
        GoldDesignGrammarV1(
            grammar_id="gold_sale_003",
            grammar_name="Bold Framed Discount",
            category="SALE",
            canvas_aspect_ratio=0.707,
            gold_status="PROVISIONAL",
            slots=[
                GoldSlotV1(slot_id="bg", role="BACKGROUND", bbox_norm=NormalizedBoundingBox(x=0, y=0, width=1, height=1), z_index=0),
                GoldSlotV1(slot_id="frame", role="DECORATION", bbox_norm=NormalizedBoundingBox(x=0.04, y=0.04, width=0.92, height=0.92), z_index=1),
                GoldSlotV1(slot_id="brand", role="BRAND", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.82, width=0.8, height=0.1), z_index=2),
                GoldSlotV1(slot_id="headline", role="HEADLINE", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.58, width=0.84, height=0.2), z_index=3),
                GoldSlotV1(slot_id="body", role="BODY", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.42, width=0.8, height=0.1), z_index=4),
                GoldSlotV1(slot_id="cta", role="CTA", bbox_norm=NormalizedBoundingBox(x=0.2, y=0.22, width=0.6, height=0.1), z_index=5),
                GoldSlotV1(slot_id="offer", role="OFFER", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.06, width=0.8, height=0.1), z_index=6),
            ],
            palette_strategy=GoldPaletteStrategyV1(
                background_color="#1E1B4B", primary_color="#EEF2FF", secondary_color="#C7D2FE", accent_color="#F59E0B", contrast_strategy="light_on_dark"
            ),
        )
    )

    # ==================== MENU CATEGORY ====================
    # 10. gold_menu_001: Bep Viet Breakfast Traditional (Inspired by DIEM TAM SANG reference)
    grammars.append(
        GoldDesignGrammarV1(
            grammar_id="gold_menu_001",
            grammar_name="Bep Viet Breakfast Traditional",
            category="MENU",
            canvas_aspect_ratio=0.707,
            gold_status="PROVISIONAL",
            slots=[
                GoldSlotV1(slot_id="bg", role="BACKGROUND", bbox_norm=NormalizedBoundingBox(x=0, y=0, width=1, height=1), z_index=0),
                GoldSlotV1(slot_id="banner", role="DECORATION", bbox_norm=NormalizedBoundingBox(x=0.06, y=0.78, width=0.88, height=0.17), z_index=1),
                GoldSlotV1(slot_id="brand", role="BRAND", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.81, width=0.84, height=0.11), z_index=2),
                GoldSlotV1(slot_id="headline", role="HEADLINE", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.6, width=0.84, height=0.15), z_index=3),
                GoldSlotV1(slot_id="body", role="BODY", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.44, width=0.8, height=0.1), z_index=4),
                GoldSlotV1(slot_id="cta", role="CTA", bbox_norm=NormalizedBoundingBox(x=0.2, y=0.24, width=0.6, height=0.09), z_index=5),
                GoldSlotV1(slot_id="offer", role="OFFER", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.08, width=0.8, height=0.09), z_index=6),
            ],
            typography_grammar={
                "HEADLINE": GoldTypographyRoleV1(role="HEADLINE", family_class="display_serif", weight=700, relative_scale=2.2, alignment="center"),
                "BRAND": GoldTypographyRoleV1(role="BRAND", family_class="display_serif", weight=700, relative_scale=1.6, alignment="center"),
            },
            palette_strategy=GoldPaletteStrategyV1(
                background_color="#FFFFFC", surface_color="#1E293B", primary_color="#1E293B", secondary_color="#0F172A", accent_color="#DC2626"
            ),
        )
    )

    # 11. gold_menu_002: Two-Column Gourmet Diner
    grammars.append(
        GoldDesignGrammarV1(
            grammar_id="gold_menu_002",
            grammar_name="Two-Column Gourmet Diner",
            category="MENU",
            canvas_aspect_ratio=0.707,
            gold_status="PROVISIONAL",
            slots=[
                GoldSlotV1(slot_id="bg", role="BACKGROUND", bbox_norm=NormalizedBoundingBox(x=0, y=0, width=1, height=1), z_index=0),
                GoldSlotV1(slot_id="brand", role="BRAND", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.84, width=0.8, height=0.1), z_index=1),
                GoldSlotV1(slot_id="headline", role="HEADLINE", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.62, width=0.84, height=0.16), z_index=2),
                GoldSlotV1(slot_id="body", role="BODY", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.45, width=0.84, height=0.12), z_index=3),
                GoldSlotV1(slot_id="cta", role="CTA", bbox_norm=NormalizedBoundingBox(x=0.2, y=0.22, width=0.6, height=0.09), z_index=4),
                GoldSlotV1(slot_id="offer", role="OFFER", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.06, width=0.8, height=0.09), z_index=5),
            ],
            palette_strategy=GoldPaletteStrategyV1(
                background_color="#F8FAFC", primary_color="#0F172A", accent_color="#EA580C"
            ),
        )
    )

    # 12. gold_menu_003: Daily Special Board
    grammars.append(
        GoldDesignGrammarV1(
            grammar_id="gold_menu_003",
            grammar_name="Daily Special Board",
            category="MENU",
            canvas_aspect_ratio=0.707,
            gold_status="PROVISIONAL",
            slots=[
                GoldSlotV1(slot_id="bg", role="BACKGROUND", bbox_norm=NormalizedBoundingBox(x=0, y=0, width=1, height=1), z_index=0),
                GoldSlotV1(slot_id="frame", role="DECORATION", bbox_norm=NormalizedBoundingBox(x=0.04, y=0.04, width=0.92, height=0.92), z_index=1),
                GoldSlotV1(slot_id="brand", role="BRAND", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.82, width=0.8, height=0.1), z_index=2),
                GoldSlotV1(slot_id="headline", role="HEADLINE", bbox_norm=NormalizedBoundingBox(x=0.08, y=0.6, width=0.84, height=0.16), z_index=3),
                GoldSlotV1(slot_id="body", role="BODY", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.44, width=0.8, height=0.1), z_index=4),
                GoldSlotV1(slot_id="cta", role="CTA", bbox_norm=NormalizedBoundingBox(x=0.22, y=0.22, width=0.56, height=0.09), z_index=5),
                GoldSlotV1(slot_id="offer", role="OFFER", bbox_norm=NormalizedBoundingBox(x=0.1, y=0.06, width=0.8, height=0.09), z_index=6),
            ],
            palette_strategy=GoldPaletteStrategyV1(
                background_color="#0F172A", primary_color="#F8FAFC", secondary_color="#94A3B8", accent_color="#F59E0B", contrast_strategy="light_on_dark"
            ),
        )
    )

    # ==================== SIGNAGE CATEGORY ====================
    # 13. gold_signage_001: VIP Dental Horizontal Banner (300 x 100 mm)
    grammars.append(
        GoldDesignGrammarV1(
            grammar_id="gold_signage_001",
            grammar_name="VIP Dental Horizontal Banner",
            category="SIGNAGE",
            canvas_aspect_ratio=3.0,  # 300 / 100
            gold_status="PROVISIONAL",
            slots=[
                GoldSlotV1(slot_id="bg", role="BACKGROUND", bbox_norm=NormalizedBoundingBox(x=0, y=0, width=1, height=1), z_index=0),
                GoldSlotV1(slot_id="brand", role="BRAND", bbox_norm=NormalizedBoundingBox(x=0.04, y=0.6, width=0.4, height=0.3), z_index=1),
                GoldSlotV1(slot_id="headline", role="HEADLINE", bbox_norm=NormalizedBoundingBox(x=0.04, y=0.18, width=0.48, height=0.36), z_index=2),
                GoldSlotV1(slot_id="body", role="BODY", bbox_norm=NormalizedBoundingBox(x=0.54, y=0.6, width=0.42, height=0.3), z_index=3),
                GoldSlotV1(slot_id="cta", role="CTA", bbox_norm=NormalizedBoundingBox(x=0.54, y=0.18, width=0.42, height=0.36), z_index=4),
            ],
            typography_grammar={
                "HEADLINE": GoldTypographyRoleV1(role="HEADLINE", family_class="condensed_sans", weight=800, relative_scale=1.8, alignment="left"),
                "BRAND": GoldTypographyRoleV1(role="BRAND", family_class="neutral_sans", weight=700, relative_scale=1.2, alignment="left"),
            },
            palette_strategy=GoldPaletteStrategyV1(
                background_color="#0F172A", primary_color="#FFFFFF", secondary_color="#94A3B8", accent_color="#F59E0B", contrast_strategy="light_on_dark"
            ),
        )
    )

    # 14. gold_signage_002: Modern Clinic Street Display (300 x 100 mm)
    grammars.append(
        GoldDesignGrammarV1(
            grammar_id="gold_signage_002",
            grammar_name="Modern Clinic Street Display",
            category="SIGNAGE",
            canvas_aspect_ratio=3.0,
            gold_status="PROVISIONAL",
            slots=[
                GoldSlotV1(slot_id="bg", role="BACKGROUND", bbox_norm=NormalizedBoundingBox(x=0, y=0, width=1, height=1), z_index=0),
                GoldSlotV1(slot_id="brand", role="BRAND", bbox_norm=NormalizedBoundingBox(x=0.05, y=0.62, width=0.45, height=0.28), z_index=1),
                GoldSlotV1(slot_id="headline", role="HEADLINE", bbox_norm=NormalizedBoundingBox(x=0.05, y=0.2, width=0.5, height=0.35), z_index=2),
                GoldSlotV1(slot_id="body", role="BODY", bbox_norm=NormalizedBoundingBox(x=0.58, y=0.62, width=0.38, height=0.28), z_index=3),
                GoldSlotV1(slot_id="cta", role="CTA", bbox_norm=NormalizedBoundingBox(x=0.58, y=0.2, width=0.38, height=0.35), z_index=4),
            ],
            palette_strategy=GoldPaletteStrategyV1(
                background_color="#0284C7", primary_color="#FFFFFF", secondary_color="#E0F2FE", accent_color="#F59E0B", contrast_strategy="light_on_dark"
            ),
        )
    )

    # 15. gold_signage_003: Clean Medical Storefront (300 x 100 mm)
    grammars.append(
        GoldDesignGrammarV1(
            grammar_id="gold_signage_003",
            grammar_name="Clean Medical Storefront",
            category="SIGNAGE",
            canvas_aspect_ratio=3.0,
            gold_status="PROVISIONAL",
            slots=[
                GoldSlotV1(slot_id="bg", role="BACKGROUND", bbox_norm=NormalizedBoundingBox(x=0, y=0, width=1, height=1), z_index=0),
                GoldSlotV1(slot_id="brand", role="BRAND", bbox_norm=NormalizedBoundingBox(x=0.06, y=0.64, width=0.42, height=0.26), z_index=1),
                GoldSlotV1(slot_id="headline", role="HEADLINE", bbox_norm=NormalizedBoundingBox(x=0.06, y=0.22, width=0.46, height=0.34), z_index=2),
                GoldSlotV1(slot_id="body", role="BODY", bbox_norm=NormalizedBoundingBox(x=0.55, y=0.64, width=0.4, height=0.26), z_index=3),
                GoldSlotV1(slot_id="cta", role="CTA", bbox_norm=NormalizedBoundingBox(x=0.55, y=0.22, width=0.4, height=0.34), z_index=4),
            ],
            palette_strategy=GoldPaletteStrategyV1(
                background_color="#FFFFFF", primary_color="#0F172A", secondary_color="#334155", accent_color="#0284C7", contrast_strategy="dark_on_light"
            ),
        )
    )

    return grammars


# Cached in-memory library
_GOLD_LIBRARY: list[GoldDesignGrammarV1] | None = None


def get_gold_library() -> list[GoldDesignGrammarV1]:
    """Retrieve the full provisional Gold Design Library (15 grammars)."""
    global _GOLD_LIBRARY
    if _GOLD_LIBRARY is None:
        _GOLD_LIBRARY = _build_provisional_grammars()
    return _GOLD_LIBRARY


def get_grammars_by_category(category: str) -> list[GoldDesignGrammarV1]:
    """Retrieve Gold Design Grammars matching a category (e.g. SPA, CAFE, SALE, MENU, SIGNAGE)."""
    cat_upper = category.upper()
    return [g for g in get_gold_library() if g.category.upper() == cat_upper]


def get_grammar_by_id(grammar_id: str) -> GoldDesignGrammarV1:
    """Retrieve a specific Gold Design Grammar by its ID."""
    for g in get_gold_library():
        if g.grammar_id == grammar_id:
            return g
    raise ValueError(f"Gold Grammar not found: {grammar_id}")
