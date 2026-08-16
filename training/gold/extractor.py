"""GoldGrammarExtractor for extracting reusable design grammars from structured reference designs."""

from __future__ import annotations

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
    """Extract a reusable ``GoldDesignGrammarV1`` from a structured document.

    The extractor never upgrades licensing or ownership. Rights are inherited from
    ``DesignDocument.source`` and explicit document metadata. Callers may only
    tighten those rights downstream, not widen them without a new source audit.
    """

    def extract(
        self,
        document: DesignDocument,
        grammar_id: str,
        grammar_name: str,
        role_mapping: dict[str, SemanticRole] | None = None,
    ) -> GoldDesignGrammarV1:
        width = float(document.canvas.width)
        height = float(document.canvas.height)
        aspect_ratio = width / height if height > 0 else 1.0

        role_map = role_mapping or {}
        slots: list[GoldSlotV1] = []
        asset_regions: list[GoldAssetRegionV1] = []
        typography_grammar: dict[str, GoldTypographyRoleV1] = {}
        body_font_size = self._estimate_body_font_size(document)

        for elem in document.elements:
            role: SemanticRole = role_map.get(elem.id) or role_map.get(elem.name) or self._infer_role(elem)
            bbox_norm = normalize_bbox(elem.bbox, document.canvas)
            slots.append(
                GoldSlotV1(
                    slot_id=elem.id,
                    role=role,
                    bbox_norm=bbox_norm,
                    z_index=elem.z_index,
                    required=True,
                )
            )

            if role in {"HERO", "PRODUCT", "LOGO"}:
                asset_regions.append(
                    GoldAssetRegionV1(
                        slot_id=elem.id,
                        role=role,  # type: ignore[arg-type]
                        bbox_norm=bbox_norm,
                        fit_mode="contain",
                        area_ratio=float(bbox_norm.width * bbox_norm.height),
                    )
                )

            if elem.type == "text" and elem.text is not None:
                font_size = float(elem.text.font_size or body_font_size)
                rel_scale = font_size / body_font_size if body_font_size > 0 else 1.0
                family = (elem.text.font_family or "").casefold()
                family_cls = (
                    "display_serif"
                    if "serif" in family or "cambria" in family
                    else "neutral_sans"
                )
                if elem.text.font_weight == "bold" or (
                    isinstance(elem.text.font_weight, int) and elem.text.font_weight >= 700
                ):
                    weight_val = 700
                else:
                    weight_val = 400

                typography_grammar[role] = GoldTypographyRoleV1(
                    role=role,
                    family_class=family_cls,
                    weight=weight_val,
                    relative_scale=rel_scale,
                    alignment=(
                        elem.text.alignment
                        if elem.text.alignment in {"left", "center", "right", "justify"}
                        else "center"
                    ),
                )

        relationships = self._extract_relationships(slots)

        bg_color = "#FFFFFF"
        if document.canvas.background and document.canvas.background.fill:
            fill = document.canvas.background.fill
            if fill.model == "hex" and fill.values:
                bg_color = str(fill.values[0])

        project_owned = document.metadata.get("project_owned") is True
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
                "source_name": document.source.name,
                "source_split": document.source.split,
                "source_upstream_id": document.source.upstream_id,
                "license_class": document.source.license_class,
                "commercial_allowed": bool(document.source.commercial_allowed),
                "project_owned": project_owned,
            },
        )

    def _estimate_body_font_size(self, document: DesignDocument) -> float:
        """Use a robust median-ish text size instead of a hard-coded 12pt baseline."""
        sizes = sorted(
            float(elem.text.font_size)
            for elem in document.elements
            if elem.type == "text" and elem.text is not None and elem.text.font_size is not None
        )
        if not sizes:
            return 12.0
        return max(1.0, sizes[len(sizes) // 2])

    def _infer_role(self, elem: DesignElement) -> SemanticRole:
        combined = f"{elem.name.lower()} {elem.id.lower()}"

        if "logo" in combined:
            return "LOGO"
        if "brand" in combined:
            return "BRAND"
        if "headline" in combined or "title" in combined:
            return "HEADLINE"
        if "sub" in combined:
            return "SUBHEADLINE"
        if "cta" in combined or "button" in combined:
            return "CTA"
        if "price" in combined:
            return "PRICE"
        if "offer" in combined or "discount" in combined:
            return "OFFER"
        if "date" in combined:
            return "DATE"
        if "contact" in combined or "phone" in combined or "hotline" in combined:
            return "CONTACT"
        if "hero" in combined:
            return "HERO"
        if "product" in combined:
            return "PRODUCT"
        if "bg" in combined or "background" in combined:
            return "BACKGROUND"
        if "frame" in combined or "banner" in combined or "rect" in combined:
            return "DECORATION"
        if "body" in combined or "text" in combined:
            return "BODY"
        return "UNKNOWN"

    def _extract_relationships(self, slots: list[GoldSlotV1]) -> list[GoldRelationshipV1]:
        relationships: list[GoldRelationshipV1] = []
        headline_slot = next((slot for slot in slots if slot.role == "HEADLINE"), None)
        body_slot = next((slot for slot in slots if slot.role == "BODY"), None)
        cta_slot = next((slot for slot in slots if slot.role == "CTA"), None)

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
