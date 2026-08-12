"""Semantic typography personality applied before glyph fitting."""

from __future__ import annotations

import statistics

from training.schemas.design import DesignDocument
from training.typography.fitting import infer_text_role
from training.visual.models import VisualStyleProfileV1


_FONT_FALLBACKS = {
    "serif": "DejaVuSerif.ttf",
    "sans": "DejaVuSans.ttf",
    "display": "DejaVuSans.ttf",
    "condensed": "DejaVuSansCondensed.ttf",
    "rounded": "DejaVuSans.ttf",
}


def apply_semantic_typography(
    document: DesignDocument,
    profile: VisualStyleProfileV1,
) -> tuple[DesignDocument, dict[str, object]]:
    output = document.model_copy(deep=True)
    text_elements = [element for element in output.elements if element.text is not None]
    sizes = [float(element.text.font_size or 12) for element in text_elements]
    largest = max(sizes, default=12.0)
    body_sizes = [
        float(element.text.font_size or 12)
        for element in text_elements
        if infer_text_role(element, largest_font=largest) in {"body", "menu_item"}
    ]
    base = statistics.median(body_sizes or sizes or [12.0])
    font_family = _FONT_FALLBACKS[profile.typography.font_class]
    changed = 0
    roles: dict[str, int] = {}
    for element in text_elements:
        assert element.text is not None
        previous_fit = element.metadata.get("typography_fit")
        if (
            isinstance(previous_fit, dict)
            and previous_fit.get("inserted_line_breaks")
            and not previous_fit.get("truncated")
            and isinstance(previous_fit.get("original_content"), str)
        ):
            element.text.content = previous_fit["original_content"]
            element.metadata["restored_pre_fit_content"] = True
        role = infer_text_role(element, largest_font=largest)
        roles[role] = roles.get(role, 0) + 1
        original = (
            element.text.font_family,
            element.text.font_size,
            element.text.font_weight,
            element.text.tracking,
            element.text.content,
        )
        element.text.font_family = font_family
        if role == "headline":
            element.text.font_size = max(
                float(element.text.font_size or base),
                base * float(profile.typography.headline_scale),
            )
            element.text.font_weight = profile.typography.headline_weight
            element.text.tracking = float(profile.typography.headline_tracking)
            if profile.typography.uppercase_headline:
                element.text.content = element.text.content.upper()
        elif role == "subtitle":
            element.text.font_size = max(
                float(element.text.font_size or base),
                base * float(profile.typography.subtitle_scale),
            )
            element.text.font_weight = max(profile.typography.body_weight, 500)
            element.text.tracking = float(profile.typography.body_tracking)
        elif role == "cta":
            element.text.font_size = max(
                float(element.text.font_size or base),
                base * float(profile.typography.cta_scale),
            )
            element.text.font_weight = profile.typography.cta_weight
            element.text.tracking = float(profile.typography.body_tracking)
            if profile.typography.uppercase_cta:
                element.text.content = element.text.content.upper()
        elif role == "price":
            element.text.font_size = max(float(element.text.font_size or base), base * 1.12)
            element.text.font_weight = max(profile.typography.body_weight, 700)
        else:
            element.text.font_size = float(element.text.font_size or base)
            element.text.font_weight = profile.typography.body_weight
            element.text.tracking = float(profile.typography.body_tracking)
        element.metadata["semantic_typography"] = {
            "version": "1.0",
            "role": role,
            "font_class": profile.typography.font_class,
            "fallback_family": font_family,
            "case_intent": (
                "uppercase"
                if (role == "headline" and profile.typography.uppercase_headline)
                or (role == "cta" and profile.typography.uppercase_cta)
                else "preserve"
            ),
        }
        current = (
            element.text.font_family,
            element.text.font_size,
            element.text.font_weight,
            element.text.tracking,
            element.text.content,
        )
        changed += current != original
    return output, {
        "engine": "semantic_typography_v1",
        "profile_id": profile.profile_id,
        "fallback_family": font_family,
        "changed_count": changed,
        "roles": roles,
    }


__all__ = ["apply_semantic_typography"]
