"""Gold Design Grammar contracts and versioned schemas (v1)."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

from training.schemas.design import ColorSpec, NormalizedBoundingBox


SemanticRole = Literal[
    "BRAND",
    "LOGO",
    "HEADLINE",
    "SUBHEADLINE",
    "BODY",
    "HERO",
    "PRODUCT",
    "OFFER",
    "PRICE",
    "DATE",
    "CTA",
    "CONTACT",
    "ADDRESS",
    "MENU_SECTION",
    "MENU_ITEM",
    "MENU_DESCRIPTION",
    "MENU_PRICE",
    "DECORATION",
    "BACKGROUND",
]

RelationshipType = Literal[
    "ALIGN_LEFT",
    "ALIGN_CENTER",
    "ALIGN_RIGHT",
    "ABOVE",
    "BELOW",
    "LEFT_OF",
    "RIGHT_OF",
    "GROUP_WITH",
    "ANCHOR_TO_EDGE",
    "OVERLAP_ALLOWED",
    "MAINTAIN_GAP",
    "MAINTAIN_RATIO",
]


class GoldSlotV1(BaseModel):
    """Semantic layout slot defined in normalized canvas coordinates [0, 1]."""

    model_config = ConfigDict(extra="forbid")

    slot_id: str
    role: SemanticRole
    bbox_norm: NormalizedBoundingBox
    z_index: int = 1
    required: bool = True
    aspect_ratio_constraint: float | None = None


class GoldRelationshipV1(BaseModel):
    """Spatial or structural relationship between two semantic slots."""

    model_config = ConfigDict(extra="forbid")

    source_slot_id: str
    target_slot_id: str
    relationship: RelationshipType
    min_distance_ratio: float = 0.0
    max_distance_ratio: float = 1.0


class GoldTypographyRoleV1(BaseModel):
    """Typography rules and relative scaling for a semantic slot role."""

    model_config = ConfigDict(extra="forbid")

    role: SemanticRole
    family_class: str = "neutral_sans"  # e.g., display_serif, condensed_sans, neutral_sans
    weight: int = 400
    relative_scale: float = 1.0  # Font size ratio relative to body font size
    alignment: Literal["left", "center", "right", "justify"] = "center"
    uppercase: bool = False
    max_lines: int = 3
    line_height_ratio: float = 1.2


class GoldAssetRegionV1(BaseModel):
    """Asset region specification for HERO, PRODUCT, or LOGO slots."""

    model_config = ConfigDict(extra="forbid")

    slot_id: str
    role: Literal["HERO", "PRODUCT", "LOGO"]
    bbox_norm: NormalizedBoundingBox
    fit_mode: Literal["contain", "cover", "fill"] = "contain"
    safe_margin_ratio: float = 0.05
    area_ratio: float = 0.3


class GoldPaletteStrategyV1(BaseModel):
    """Color palette strategy and contrast roles."""

    model_config = ConfigDict(extra="forbid")

    background_color: str = "#FFFFFF"
    surface_color: str = "#FAFAFA"
    primary_color: str = "#1E293B"
    secondary_color: str = "#475569"
    accent_color: str = "#DC2626"
    contrast_strategy: Literal["light_on_dark", "dark_on_light", "high_contrast"] = "dark_on_light"


class GoldSpacingGrammarV1(BaseModel):
    """Normalized spacing ratios and margin grammars."""

    model_config = ConfigDict(extra="forbid")

    margin_ratio: float = 0.05
    headline_to_body_gap_ratio: float = 0.02
    body_to_cta_gap_ratio: float = 0.03
    element_spacing_ratio: float = 0.02


class GoldDesignGrammarV1(BaseModel):
    """Reusable structured composition grammar extracted from a Gold reference design."""

    model_config = ConfigDict(extra="forbid")

    grammar_id: str
    grammar_name: str
    category: str
    canvas_aspect_ratio: float  # width_mm / height_mm
    gold_status: Literal["PROVISIONAL", "HUMAN_CERTIFIED"] = "PROVISIONAL"
    slots: list[GoldSlotV1]
    relationships: list[GoldRelationshipV1] = Field(default_factory=list)
    typography_grammar: dict[str, GoldTypographyRoleV1] = Field(default_factory=dict)
    asset_regions: list[GoldAssetRegionV1] = Field(default_factory=list)
    palette_strategy: GoldPaletteStrategyV1 = Field(default_factory=GoldPaletteStrategyV1)
    spacing_grammar: GoldSpacingGrammarV1 = Field(default_factory=GoldSpacingGrammarV1)
    provenance: dict[str, Any] = Field(
        default_factory=lambda: {
            "license_class": "CC0_or_project_owned",
            "commercial_allowed": True,
            "source": "project_gold_archive",
        }
    )
