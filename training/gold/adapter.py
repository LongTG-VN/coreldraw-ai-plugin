"""GoldDesignAdapter for bounded adaptation of a reference grammar to new content."""

from __future__ import annotations

import time
from typing import Any

from training.inference.planner_base import ContentLockSpec
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
from training.schemas.gold import GoldDesignGrammarV1


class GoldDesignAdapter:
    """Adapt a reusable grammar without widening business facts or source rights."""

    def adapt(
        self,
        grammar: GoldDesignGrammarV1,
        lock_spec: ContentLockSpec,
        candidate_index: int = 0,
        seed: int = 42,
    ) -> tuple[DesignDocument, dict[str, Any]]:
        del seed  # deterministic bounded adaptation; retained for interface compatibility
        start_time = time.perf_counter()

        width = lock_spec.canvas_width_mm
        height = lock_spec.canvas_height_mm
        canvas = CanvasSpec(
            width=width,
            height=height,
            unit="mm",
            background=VisualSpec(
                fill=ColorSpec(model="hex", values=[grammar.palette_strategy.background_color])
            ),
        )

        elements: list[DesignElement] = []
        filled_slots: set[str] = set()

        for slot in grammar.slots:
            bbox = BoundingBox(
                x=slot.bbox_norm.x * width,
                y=slot.bbox_norm.y * height,
                width=slot.bbox_norm.width * width,
                height=slot.bbox_norm.height * height,
            )
            typo = grammar.typography_grammar.get(slot.role)
            alignment = typo.alignment if typo else "center"
            font_family = "Cambria" if typo and typo.family_class == "display_serif" else "Arial"
            primary = grammar.palette_strategy.primary_color
            secondary = grammar.palette_strategy.secondary_color
            accent = grammar.palette_strategy.accent_color

            if slot.role == "BRAND":
                self._append_text(
                    elements, slot, candidate_index, bbox, canvas,
                    name="Gold Brand", content=lock_spec.business_name,
                    font_family=font_family,
                    font_size=self._font_size(height, 18.0, typo.relative_scale if typo else 1.2, 12.0),
                    font_weight="bold" if typo and typo.weight >= 700 else "normal",
                    alignment=alignment, color=primary,
                )
                filled_slots.add(slot.slot_id)

            elif slot.role == "LOGO":
                # ContentLockSpec currently carries only an asset ID, not an AssetSpec/file.
                # Do not fake a logo as business-name text. Leave the slot unfilled until the
                # asset pipeline supplies a concrete logo asset.
                continue

            elif slot.role in {"HEADLINE", "SUBHEADLINE"}:
                self._append_text(
                    elements, slot, candidate_index, bbox, canvas,
                    name="Gold Headline", content=lock_spec.headline,
                    font_family=font_family,
                    font_size=self._font_size(height, 24.0, typo.relative_scale if typo else 1.8, 16.0),
                    font_weight="bold" if typo and typo.weight >= 700 else "normal",
                    alignment=alignment, color=primary,
                )
                filled_slots.add(slot.slot_id)

            elif slot.role == "BODY" and lock_spec.body:
                self._append_text(
                    elements, slot, candidate_index, bbox, canvas,
                    name="Gold Body", content=lock_spec.body,
                    font_family=font_family,
                    font_size=13.0 if height > 200 else 10.0,
                    font_weight="normal", alignment=alignment, color=secondary,
                )
                filled_slots.add(slot.slot_id)

            elif slot.role == "CTA" and lock_spec.cta:
                elements.append(
                    DesignElement(
                        id=f"gold_elem_{slot.slot_id}_box_{candidate_index}",
                        name=f"Gold CTA Box ({slot.slot_id})",
                        type="rectangle",
                        bbox=bbox,
                        bbox_norm=normalize_bbox(bbox, canvas),
                        z_index=slot.z_index,
                        visual=VisualSpec(fill=ColorSpec(model="hex", values=[accent])),
                    )
                )
                self._append_text(
                    elements, slot, candidate_index, bbox, canvas,
                    name="Gold CTA Text", content=lock_spec.cta,
                    font_family="Arial", font_size=14.0 if height > 200 else 11.0,
                    font_weight="bold", alignment="center", color="#FFFFFF",
                    z_offset=1,
                )
                filled_slots.add(slot.slot_id)

            elif slot.role in {"PRICE", "OFFER"} and lock_spec.price_offer:
                self._append_text(
                    elements, slot, candidate_index, bbox, canvas,
                    name="Gold Offer", content=lock_spec.price_offer,
                    font_family="Arial", font_size=14.0 if height > 200 else 11.0,
                    font_weight="bold", alignment="center", color=accent,
                )
                filled_slots.add(slot.slot_id)

            elif slot.role == "BACKGROUND":
                elements.append(
                    DesignElement(
                        id=f"gold_elem_{slot.slot_id}_{candidate_index}",
                        name=f"Gold Background ({slot.slot_id})",
                        type="rectangle",
                        bbox=bbox,
                        bbox_norm=normalize_bbox(bbox, canvas),
                        z_index=0,
                        visual=VisualSpec(
                            fill=ColorSpec(
                                model="hex", values=[grammar.palette_strategy.background_color]
                            )
                        ),
                    )
                )
                filled_slots.add(slot.slot_id)

            elif slot.role == "DECORATION":
                elements.append(
                    DesignElement(
                        id=f"gold_elem_{slot.slot_id}_{candidate_index}",
                        name=f"Gold Decoration ({slot.slot_id})",
                        type="rectangle",
                        bbox=bbox,
                        bbox_norm=normalize_bbox(bbox, canvas),
                        z_index=slot.z_index,
                        visual=VisualSpec(
                            fill=ColorSpec(model="hex", values=[grammar.palette_strategy.surface_color])
                        ),
                    )
                )
                filled_slots.add(slot.slot_id)

            # HERO/PRODUCT/DATE/CONTACT/etc. are intentionally not fabricated here.
            # They require explicit content/asset support in ContentLockSpec.

        commercial_allowed = bool(grammar.provenance.get("commercial_allowed", False))
        license_class = str(grammar.provenance.get("license_class") or "UNKNOWN")
        doc = DesignDocument(
            sample_id=f"gold_{grammar.grammar_id}_{lock_spec.brief_id}_c{candidate_index}",
            source=SourceSpec(
                name=f"gold_grammar_{grammar.grammar_id}",
                split="benchmark",
                license_class=license_class,
                upstream_id=grammar.grammar_id,
                commercial_allowed=commercial_allowed,
            ),
            canvas=canvas,
            category=lock_spec.category,
            elements=elements,
            metadata={
                "source_grammar_id": grammar.grammar_id,
                "source_gold_status": grammar.gold_status,
                "source_project_owned": bool(grammar.provenance.get("project_owned", False)),
            },
        )

        elapsed = max(time.perf_counter() - start_time, 0.0)
        slot_fill_rate = len(filled_slots) / len(grammar.slots) if grammar.slots else 1.0
        preserved_relationships = sum(
            1
            for rel in grammar.relationships
            if rel.source_slot_id in filled_slots and rel.target_slot_id in filled_slots
        )
        relationship_preservation_rate = (
            preserved_relationships / len(grammar.relationships) if grammar.relationships else 1.0
        )

        report = {
            "grammar_id": grammar.grammar_id,
            "grammar_name": grammar.grammar_name,
            "gold_status": grammar.gold_status,
            "brief_id": lock_spec.brief_id,
            "category": lock_spec.category,
            "candidate_index": candidate_index,
            "latency_seconds": elapsed,
            "slot_fill_rate": slot_fill_rate,
            "filled_slot_ids": sorted(filled_slots),
            # Geometry is copied exactly in normalized coordinates for filled slots.
            "grammar_deviation_score": 0.0,
            "relationship_preservation_rate": relationship_preservation_rate,
            # These metrics are not yet measured independently; do not fabricate 1.0.
            "alignment_preservation_rate": None,
            "spacing_preservation_rate": None,
            "hierarchy_preservation_rate": None,
            "commercial_allowed": commercial_allowed,
            "license_class": license_class,
        }
        return doc, report

    @staticmethod
    def _font_size(height: float, base: float, relative_scale: float, small: float) -> float:
        return base * relative_scale if height > 200 else small

    @staticmethod
    def _append_text(
        elements: list[DesignElement],
        slot: Any,
        candidate_index: int,
        bbox: BoundingBox,
        canvas: CanvasSpec,
        *,
        name: str,
        content: str,
        font_family: str,
        font_size: float,
        font_weight: str,
        alignment: str,
        color: str,
        z_offset: int = 0,
    ) -> None:
        elements.append(
            DesignElement(
                id=f"gold_elem_{slot.slot_id}_{candidate_index}",
                name=f"{name} ({slot.slot_id})",
                type="text",
                bbox=bbox,
                bbox_norm=normalize_bbox(bbox, canvas),
                z_index=slot.z_index + z_offset,
                text=TextSpec(
                    content=content,
                    font_family=font_family,
                    font_size=max(1.0, font_size),
                    font_weight=font_weight,
                    alignment=alignment,
                ),
                visual=VisualSpec(fill=ColorSpec(model="hex", values=[color])),
            )
        )
