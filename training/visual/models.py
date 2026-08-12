"""Strict versioned contracts for the v0.3.1 visual composition engine."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class StrictVisualModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PaletteRolesV1(StrictVisualModel):
    background: str = Field(pattern=r"^#[0-9A-F]{6}$")
    surface: str = Field(pattern=r"^#[0-9A-F]{6}$")
    primary: str = Field(pattern=r"^#[0-9A-F]{6}$")
    secondary: str = Field(pattern=r"^#[0-9A-F]{6}$")
    accent: str = Field(pattern=r"^#[0-9A-F]{6}$")
    headline: str = Field(pattern=r"^#[0-9A-F]{6}$")
    body: str = Field(pattern=r"^#[0-9A-F]{6}$")
    muted: str = Field(pattern=r"^#[0-9A-F]{6}$")
    cta_background: str = Field(pattern=r"^#[0-9A-F]{6}$")
    cta_text: str = Field(pattern=r"^#[0-9A-F]{6}$")


class TypographyStyleV1(StrictVisualModel):
    font_class: Literal["serif", "sans", "display", "condensed", "rounded"]
    headline_weight: int = Field(ge=100, le=900)
    body_weight: int = Field(ge=100, le=900)
    cta_weight: int = Field(ge=100, le=900)
    headline_scale: FiniteFloat = Field(ge=1.4, le=4.5)
    subtitle_scale: FiniteFloat = Field(ge=1.0, le=2.5)
    cta_scale: FiniteFloat = Field(ge=1.0, le=2.2)
    headline_tracking: FiniteFloat = Field(ge=-5, le=20)
    body_tracking: FiniteFloat = Field(ge=-5, le=20)
    uppercase_headline: bool = False
    uppercase_cta: bool = False


class VisualStyleProfileV1(StrictVisualModel):
    schema_version: Literal["1.0"] = "1.0"
    profile_id: str = Field(pattern=r"^[a-z0-9_]+$")
    category: str = Field(min_length=1, max_length=100)
    mood: list[str] = Field(min_length=1, max_length=8)
    composition_style: str = Field(min_length=1, max_length=100)
    density_target: FiniteFloat = Field(gt=0, lt=1)
    density_min: FiniteFloat = Field(gt=0, lt=1)
    density_max: FiniteFloat = Field(gt=0, lt=1)
    palette_roles: PaletteRolesV1
    typography: TypographyStyleV1
    hero_strategy: Literal[
        "none", "right_frame", "left_frame", "product_card", "logo_frame"
    ]
    background_strategy: Literal["solid", "split", "soft_surface", "campaign"]
    surface_strategy: Literal["none", "single_panel", "section_panels"]
    accent_strategy: Literal["line", "corner", "orb", "burst", "none"]
    badge_strategy: Literal["none", "pill", "circle", "campaign"]
    divider_strategy: Literal["none", "line", "menu_rows"]
    decorative_intensity: FiniteFloat = Field(ge=0, le=1)
    max_decorative_elements: int = Field(ge=0, le=12)

    @model_validator(mode="after")
    def validate_density_range(self) -> "VisualStyleProfileV1":
        if not self.density_min <= self.density_target <= self.density_max:
            raise ValueError("density target must be inside min/max")
        return self


class DensityDiagnosticsV1(StrictVisualModel):
    actual_coverage: FiniteFloat = Field(ge=0, le=1)
    target_coverage: FiniteFloat = Field(gt=0, lt=1)
    density_min: FiniteFloat = Field(gt=0, lt=1)
    density_max: FiniteFloat = Field(gt=0, lt=1)
    density_error: FiniteFloat = Field(ge=0, le=1)
    density_fit: FiniteFloat = Field(ge=0, le=1)


class VisualCompositionReportV1(StrictVisualModel):
    schema_version: Literal["1.0"] = "1.0"
    engine: Literal["visual_composition_v0.3.1"] = "visual_composition_v0.3.1"
    profile_id: str
    source_category: str
    palette: PaletteRolesV1
    density_before: DensityDiagnosticsV1
    density_after: DensityDiagnosticsV1
    semantic_typography_count: int = Field(ge=0)
    asset_placeholder_count: int = Field(ge=0)
    asset_placeholders_created: int = Field(ge=0)
    decorative_element_count: int = Field(ge=0)
    business_placeholder_count: int = Field(ge=0)
    content_mutated: bool
    provenance_version: Literal["content_provenance_v1"] = "content_provenance_v1"
