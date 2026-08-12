"""Deterministic Vietnamese/English design brief analysis."""

from __future__ import annotations

import re
import unicodedata

from training.retrieval.models import StructuredBriefV1, TextDensity


def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        "".join(character for character in normalized if not unicodedata.combining(character)).split()
    )


CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tra_sua", ("tra sua", "milk tea", "boba")),
    ("my_pham", ("my pham", "cosmetic", "serum", "skincare")),
    ("card_visit", ("card visit", "business card", "name card")),
    ("bang_hieu", ("bang hieu", "signage", "shop sign")),
    ("banner_social", ("social banner", "banner social", "workshop banner")),
    ("nha_hang", ("nha hang", "restaurant")),
    ("menu", ("food menu", "menu quan", "menu 6", "menu 10", "thuc don")),
    ("spa", ("spa", "wellness", "massage")),
    ("nail", ("nail", "manicure", "pedicure")),
    ("salon", ("salon", "hair", "toc")),
    ("cafe", ("cafe", "coffee", "quan ca phe")),
    # Vertical categories take precedence over campaign intent. For example,
    # "khai truong quan cafe" should retrieve cafe compositions, while a bare
    # grand-opening request still falls through to the campaign category.
    ("poster_sale", ("mega sale", "poster sale", "flash sale", "giam gia")),
    ("khai_truong", ("khai truong", "grand opening", "opening promotion")),
)

STYLE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("luxury", ("cao cap", "sang trong", "luxury", "premium")),
    ("minimal", ("toi gian", "minimal", "clean")),
    ("modern", ("hien dai", "modern", "digital")),
    ("vintage", ("vintage", "retro", "moc")),
    ("youthful", ("tre trung", "youthful", "nang dong", "energetic")),
    ("festive", ("le hoi", "festive", "grand opening")),
    ("bold", ("noi bat", "bold", "manh", "mega sale")),
    ("elegant", ("trang nha", "elegant")),
    ("editorial", ("editorial", "tap chi")),
)

COLOR_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cream", ("kem", "cream")),
    ("gold", ("vang", "gold")),
    ("red", ("do", "red")),
    ("black", ("den", "black")),
    ("white", ("trang", "white")),
    ("green", ("xanh la", "green")),
    ("blue", ("xanh duong", "blue", "navy")),
    ("purple", ("tim", "purple")),
    ("pink", ("hong", "pink")),
    ("orange", ("cam", "orange")),
    ("brown", ("nau", "brown")),
    ("silver", ("bac", "silver")),
)


def _contains(text: str, needle: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", text) is not None


def _first_match(text: str, rules: tuple[tuple[str, tuple[str, ...]], ...]) -> str | None:
    for value, needles in rules:
        if any(_contains(text, needle) for needle in needles):
            return value
    return None


def _all_matches(text: str, rules: tuple[tuple[str, tuple[str, ...]], ...]) -> list[str]:
    return [value for value, needles in rules if any(_contains(text, needle) for needle in needles)]


def _format(text: str, category: str) -> str:
    if "menu" in text or "thuc don" in text:
        return "menu"
    if category == "card_visit":
        return "business_card"
    if category == "bang_hieu":
        return "signage"
    if "social" in text or category in {"tra_sua", "banner_social"}:
        return "social_post" if category == "tra_sua" else "banner"
    if "banner" in text:
        return "banner"
    return "poster"


def _requested_elements(text: str) -> list[str]:
    rules = (
        ("brand", ("ten ", "brand", "headline", "tieu de")),
        ("logo", ("logo",)),
        ("prices", ("gia", "price", "49k", "%")),
        ("contact", ("hotline", "dien thoai", "phone", "email", "contact")),
        ("cta", ("cta", "dat lich", "order", "mua ngay", "dang ky", "inbox", "kham pha")),
        ("date", ("ngay", "date", "thoi gian", "time")),
        ("address", ("dia chi", "address")),
        ("benefits", ("loi ich", "benefit")),
        ("speaker", ("dien gia", "speaker")),
        ("promotion", ("uu dai", "sale", "giam", "tang")),
    )
    values = [name for name, needles in rules if any(needle in text for needle in needles)]
    count_match = re.search(r"\b(\d{1,2})\s*(mon|products?|items?)\b", text)
    if count_match:
        values.append(f"{count_match.group(1)}_items")
    return values


def _density(text: str, requested: list[str]) -> TextDensity:
    count_match = re.search(r"\b(\d{1,2})\s*(mon|products?|items?)\b", text)
    count = int(count_match.group(1)) if count_match else 0
    if count >= 6 or len(requested) >= 7 or "dense" in text:
        return "high"
    if len(requested) <= 2 and len(text.split()) < 14:
        return "low"
    return "medium"


def analyze_brief(
    prompt: str,
    *,
    width: float,
    height: float,
) -> StructuredBriefV1:
    """Parse a strict brief without invoking another model."""

    prompt = prompt.strip()
    if not prompt:
        raise ValueError("prompt cannot be empty")
    if width <= 0 or height <= 0:
        raise ValueError("brief dimensions must be positive")
    text = _plain(prompt)
    category = _first_match(text, CATEGORY_RULES)
    fallback = category is None
    category = category or "general"
    requested = _requested_elements(text)
    styles = _all_matches(text, STYLE_RULES) or ["balanced"]
    colors = _all_matches(text, COLOR_RULES)
    return StructuredBriefV1(
        prompt=prompt,
        category=category,
        format=_format(text, category),
        style=styles,
        colors=colors,
        text_density=_density(text, requested),
        requested_elements=requested,
        aspect_ratio=float(width) / float(height),
        analyzer="fallback" if fallback else "deterministic_rules",
        fallback_used=fallback,
    )
