"""GoldGrammarExtractor for extracting reusable design grammars from structured reference designs."""

from __future__ import annotations

import math
from typing import Any

from training.schemas.design import DesignDocument, DesignElement, normalize_bbox
from training.schemas.gold import (
    GoldAssetRegionV1,
    GoldDesignGrammarV1,
    GoldPaletteStrategyV1,
    GoldRelationshipV1,
    GoldSlotV1,
    GoldSpacingGrammarV1,
    GoldTypographyRoleV1,
    SemanticRole,
)


class GoldGrammarExtractor:
    """Extracts a clean, reusable GoldDesignGrammarV1 from a structured DesignDocument."""

    def extract(
        self,
        document: DesignDocument,
        grammar_id: str,
        grammar_name: str,
        role_mapping: dict[str, SemanticRole] | None = None,
    ) -> GoldDesignGrammarV1:
        w_mm = float(document.canvas.width)
        h_mm = float(document.canvas.height)
        aspect_ratio = w_mm / h_mm if h_mm > 0 else 1.0

        role_map = role_mapping or {}
        slots: list[GoldSlotV1] = []
        asset_regions: list[GoldAssetRegionV1] = []
        typography_grammar: dict[str, GoldTypographyRoleV1] = {}

        # Default body font size estimation
        body_font_size = 12.0

        for elem in document.elements:
            role: SemanticRole = role_map.get(elem.id) or role_map.get(elem.name) or self._infer_role(elem)

            # Convert bbox to normalized [0, 1]
            bbox_norm = normalize_bbox(elem.bbox, document.canvas)

            slot = GoldSlotV1(
                slot_id=elem.id,
                role=role,
                bbox_norm=bbox_norm,
                z_index=elem.z_index,
                required=True,
            )
            slots.append(slot)

            if role in {"HERO", "PRODUCT", "LOGO"}:
                asset_regions.append(
                    GoldAssetRegionV1(
                        slot_id=elem.id,
                        role=role,  # type: ignore
                        bbox_norm=bbox_norm,
                        fit_mode="contain",
                        area_ratio=float(bbox_norm.width * bbox_norm.height),
                    )
                )

            if elem.type == "text" and elem.text is not None:
                rel_scale = float(elem.text.font_size) / body_font_size if body_font_size > 0 else 1.0
                family_cls = "display_serif" if "serif" in elem.text.font_family.casefold() or "cambria" in elem.text.font_family.casefold() else "neutral_sans"
                if elem.text.font_weight == "bold" or (isinstance(elem.text.font_weight, int) and elem.text.font_weight >= 700):
                    weight_val = 700
                else:
                    weight_val = 400

                typography_grammar[role] = GoldTypographyRoleV1(
                    role=role,
                    family_class=family_cls,
                    weight=weight_val,
                    relative_scale=rel_scale,
                    alignment=elem.text.alignment if elem.text.alignment in {"left", "center", "right", "justify"} else "center",
                )

        # Extract basic relationships
        relationships = self._extract_relationships(slots)

        bg_color = "#FFFFFF"
        if document.canvas.background and document.canvas.background.fill:
            if document.canvas.background.fill.model == "hex" and document.canvas.background.fill.values:
                bg_color = str(document.canvas.background.fill.values[0])

        return GoldDesignGrammarV1(
            grammar_id=grammar_id,
            grammar_name=grammar_name,
            category=document.category.upper(),
            canvas_aspect_ratio=aspect_ratio,
            gold_status="PROVISIONAL",
            slots=slots,
            relationships=relationships,
            typography_grammar=typography_grammar,
            asset_regions=asset_regions,
            palette_strategy=GoldPaletteStrategyV1(
                background_color=bg_color,
                primary_color="#1E293B",
                accent_color="#DC2626",
            ),
            spacing_grammar=GoldSpacingGrammarV1(margin_ratio=0.05),
            provenance={
                "extracted_from_sample_id": document.sample_id,
                "license_class": "CC0_or_project_owned",
                "commercial_allowed": True,
            },
        )

    def _infer_role(self, elem: DesignElement) -> SemanticRole:
        name_lower = elem.name.lower()
        id_lower = elem.id.lower()
        combined = f"{name_lower} {id_lower}"

        if "brand" in combined or "logo" in combined:
            return "BRAND"
        if "headline" in combined or "title" in combined:
            return "HEADLINE"
        if "sub" in combined:
            return "SUBHEADLINE"
        if "body" in combined or "text" in combined:
            return "BODY"
        if "cta" in combined or "button" in combined:
            return "CTA"
        if "price" in combined or "offer" in combined or "discount" in combined:
            return "PRICE"
        if "bg" in combined or "background" in combined:
            return "BACKGROUND"
        if "frame" in combined or "banner" in combined or "rect" in combined:
            return "DECORATION"
        return "BODY"

    def _extract_relationships(self, slots: list[GoldSlotV1]) -> list[GoldRelationshipV1]:
        relationships: list[GoldRelationshipV1] = []
        headline_slot = next((s for s in slots if s.role == "HEADLINE"), None)
        body_slot = next((s for s in slots if s.role == "BODY"), None)
        cta_slot = next((s for s in slots if s.role == "CTA"), None)

        if headline_slot and body_slot:
            relationships.append(
                GoldRelationshipV1(
                    source_slot_id=headline_slot.slot_id,
                    target_slot_id=body_slot.slot_id,
                    relationship="ABOVE",
                )
            )
        if body_slot and cta_slot:
            relationships.append(
                GoldRelationshipV1(
                    source_slot_id=body_slot.slot_id,
                    target_slot_id=cta_slot.slot_id,
                    relationship="ABOVE",
                )
            )

        return relationships
