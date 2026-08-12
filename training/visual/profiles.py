"""Category-aware, deterministic visual profiles without artwork cloning."""

from __future__ import annotations

from training.visual.models import PaletteRolesV1, TypographyStyleV1, VisualStyleProfileV1


_ALIASES = {
    "tra_sua": "milk_tea",
    "my_pham": "cosmetics",
    "nha_hang": "restaurant",
    "menu": "food_menu",
    "poster_sale": "sale",
    "khai_truong": "grand_opening",
    "card_visit": "business_card",
    "bang_hieu": "signage",
    "banner_social": "social_banner",
}


def _palette(
    background: str,
    surface: str,
    primary: str,
    secondary: str,
    accent: str,
    headline: str,
    body: str,
    muted: str,
    cta_background: str,
    cta_text: str,
) -> PaletteRolesV1:
    return PaletteRolesV1(
        background=background,
        surface=surface,
        primary=primary,
        secondary=secondary,
        accent=accent,
        headline=headline,
        body=body,
        muted=muted,
        cta_background=cta_background,
        cta_text=cta_text,
    )


_LIGHT_LUXURY = _palette(
    "#F7F0E6", "#FFF9F1", "#3D2B24", "#9D7B55", "#C49A52",
    "#2A1C17", "#4E4038", "#76645A", "#3D2B24", "#FFFFFF",
)
_MODERN_GREEN = _palette(
    "#F2F4EA", "#FFFFFF", "#173F35", "#668C63", "#D8A84E",
    "#12352D", "#294A42", "#62766F", "#173F35", "#FFFFFF",
)
_CAMPAIGN = _palette(
    "#FFF4E8", "#FFFFFF", "#A51D2D", "#F05A28", "#F5C542",
    "#6E1020", "#391D21", "#76565A", "#A51D2D", "#FFFFFF",
)
_DARK_SIGNAGE = _palette(
    "#121416", "#202428", "#F2C14E", "#F7F2E8", "#E85D3F",
    "#FFFFFF", "#ECE7DC", "#BDB7AD", "#F2C14E", "#121416",
)
_SOCIAL = _palette(
    "#F5F3FF", "#FFFFFF", "#4C35A8", "#7161D6", "#FF5C8A",
    "#261B59", "#40385A", "#756F86", "#4C35A8", "#FFFFFF",
)


def _type(
    font_class: str,
    headline_scale: float,
    *,
    upper_headline: bool = False,
    upper_cta: bool = False,
    headline_weight: int = 700,
) -> TypographyStyleV1:
    return TypographyStyleV1(
        font_class=font_class,
        headline_weight=headline_weight,
        body_weight=400,
        cta_weight=700,
        headline_scale=headline_scale,
        subtitle_scale=1.25,
        cta_scale=1.15,
        headline_tracking=0.5 if font_class == "serif" else 0.0,
        body_tracking=0.0,
        uppercase_headline=upper_headline,
        uppercase_cta=upper_cta,
    )


def _profile(
    category: str,
    *,
    mood: list[str],
    composition: str,
    density: tuple[float, float, float],
    palette: PaletteRolesV1,
    typography: TypographyStyleV1,
    hero: str,
    background: str = "soft_surface",
    surface: str = "single_panel",
    accent: str = "corner",
    badge: str = "none",
    divider: str = "none",
    intensity: float = 0.35,
    maximum: int = 5,
) -> VisualStyleProfileV1:
    low, target, high = density
    return VisualStyleProfileV1(
        profile_id=f"{category}_v1",
        category=category,
        mood=mood,
        composition_style=composition,
        density_min=low,
        density_target=target,
        density_max=high,
        palette_roles=palette,
        typography=typography,
        hero_strategy=hero,
        background_strategy=background,
        surface_strategy=surface,
        accent_strategy=accent,
        badge_strategy=badge,
        divider_strategy=divider,
        decorative_intensity=intensity,
        max_decorative_elements=maximum,
    )


_PROFILES = {
    "spa": _profile("spa", mood=["premium", "calm"], composition="editorial_split", density=(.28, .35, .42), palette=_LIGHT_LUXURY, typography=_type("serif", 2.7), hero="right_frame", accent="orb"),
    "nail": _profile("nail", mood=["elegant", "feminine"], composition="soft_split", density=(.30, .39, .48), palette=_palette("#FFF2F5", "#FFFFFF", "#6D2940", "#C0748C", "#D8A34D", "#4A1D2D", "#533943", "#8C6975", "#6D2940", "#FFFFFF"), typography=_type("serif", 2.55), hero="right_frame", accent="orb"),
    "salon": _profile("salon", mood=["editorial", "bold"], composition="asymmetric_split", density=(.32, .42, .52), palette=_palette("#F4F1EC", "#FFFFFF", "#222222", "#70665D", "#C75932", "#161616", "#3E3A36", "#77716C", "#222222", "#FFFFFF"), typography=_type("display", 2.8, upper_headline=True), hero="right_frame", accent="line"),
    "cafe": _profile("cafe", mood=["warm", "crafted"], composition="warm_split", density=(.34, .44, .54), palette=_palette("#F1E4D2", "#FFF8ED", "#5A3425", "#8D6449", "#C67C3B", "#39231B", "#51382E", "#846D61", "#5A3425", "#FFFFFF"), typography=_type("serif", 2.45), hero="product_card", accent="corner"),
    "milk_tea": _profile("milk_tea", mood=["youthful", "friendly"], composition="playful_product", density=(.36, .47, .58), palette=_palette("#FFF4D9", "#FFFFFF", "#5D3A29", "#8BC0A8", "#F28B66", "#3F281E", "#4F413A", "#7E7069", "#5D3A29", "#FFFFFF"), typography=_type("rounded", 2.5), hero="product_card", accent="orb", badge="pill", intensity=.5, maximum=6),
    "restaurant": _profile("restaurant", mood=["premium", "appetizing"], composition="editorial_food", density=(.38, .50, .62), palette=_MODERN_GREEN, typography=_type("serif", 2.45), hero="product_card", accent="line"),
    "food_menu": _profile("food_menu", mood=["organized", "readable"], composition="structured_menu", density=(.48, .59, .70), palette=_MODERN_GREEN, typography=_type("sans", 2.15), hero="none", background="solid", surface="section_panels", accent="line", divider="menu_rows", intensity=.25, maximum=8),
    "cosmetics": _profile("cosmetics", mood=["clean", "premium"], composition="minimal_product", density=(.28, .37, .46), palette=_palette("#F8F3F0", "#FFFFFF", "#4A3842", "#B59CA8", "#B78A6A", "#34262D", "#51454B", "#897A81", "#4A3842", "#FFFFFF"), typography=_type("serif", 2.7), hero="product_card", accent="orb"),
    "sale": _profile("sale", mood=["urgent", "energetic"], composition="campaign_focal", density=(.42, .54, .65), palette=_CAMPAIGN, typography=_type("display", 3.25, upper_headline=True, upper_cta=True, headline_weight=800), hero="product_card", background="campaign", surface="single_panel", accent="burst", badge="campaign", intensity=.75, maximum=8),
    "grand_opening": _profile("grand_opening", mood=["celebratory", "bold"], composition="campaign_focal", density=(.40, .52, .64), palette=_CAMPAIGN, typography=_type("display", 3.0, upper_headline=True, upper_cta=True, headline_weight=800), hero="right_frame", background="campaign", accent="burst", badge="circle", intensity=.7, maximum=8),
    "business_card": _profile("business_card", mood=["professional", "minimal"], composition="identity_grid", density=(.30, .39, .48), palette=_DARK_SIGNAGE, typography=_type("condensed", 2.1), hero="logo_frame", background="split", surface="none", accent="line", intensity=.2, maximum=3),
    "signage": _profile("signage", mood=["bold", "legible"], composition="wide_focal", density=(.25, .35, .45), palette=_DARK_SIGNAGE, typography=_type("condensed", 3.2, upper_headline=True, headline_weight=800), hero="logo_frame", background="solid", surface="none", accent="line", intensity=.25, maximum=3),
    "social_banner": _profile("social_banner", mood=["modern", "engaging"], composition="dynamic_split", density=(.34, .45, .56), palette=_SOCIAL, typography=_type("sans", 2.65, headline_weight=800), hero="right_frame", background="split", accent="orb", badge="pill", intensity=.55, maximum=6),
    "general": _profile("general", mood=["balanced", "clear"], composition="balanced_grid", density=(.30, .40, .50), palette=_SOCIAL, typography=_type("sans", 2.4), hero="right_frame", accent="line", intensity=.25, maximum=4),
}


def normalize_visual_category(category: str) -> str:
    normalized = category.strip().casefold().replace("-", "_").replace(" ", "_")
    return _ALIASES.get(normalized, normalized if normalized in _PROFILES else "general")


def get_visual_profile(
    category: str,
    *,
    format_name: str | None = None,
) -> VisualStyleProfileV1:
    """Return an immutable copy so callers cannot mutate global defaults."""

    normalized = "food_menu" if format_name == "menu" else normalize_visual_category(category)
    return _PROFILES[normalized].model_copy(deep=True)


def supported_visual_categories() -> tuple[str, ...]:
    return tuple(key for key in _PROFILES if key != "general")


__all__ = ["get_visual_profile", "normalize_visual_category", "supported_visual_categories"]
