"""Deterministic target resolution with explicit ambiguity failures."""

from __future__ import annotations

import re
from collections.abc import Iterable

from training.company_archive.models import CdrObjectV1
from training.corel_operator.models import ResolvedTargetV1, SelectorKind, TargetSelectorV1


class TargetResolutionError(ValueError):
    """Base class for non-executable target selectors."""


class TargetNotFoundError(TargetResolutionError):
    pass


class AmbiguousTargetError(TargetResolutionError):
    pass


_PHONE_RE = re.compile(r"(?<!\d)(?:\+?84|0)(?:[ .-]?\d){8,10}(?!\d)")
_PRICE_RE = re.compile(
    r"(?i)(?<!\w)(?:\d{1,3}(?:[., ]\d{3})+|\d+)(?:\s?)(?:k|đ|₫|vnd)(?!\w)"
)


def _matches(item: CdrObjectV1, selector: TargetSelectorV1) -> bool:
    value = selector.value
    text = item.text or ""
    if selector.kind == SelectorKind.OBJECT_ID:
        return item.object_id == value
    if selector.kind == SelectorKind.COREL_NAME:
        return item.corel_name == value
    if selector.kind == SelectorKind.EXACT_TEXT:
        return text == value
    if selector.kind == SelectorKind.CASEFOLD_TEXT:
        return text.casefold() == value.casefold()
    if selector.kind == SelectorKind.REGEX_TEXT:
        try:
            return re.search(value, text) is not None
        except re.error as exc:
            raise TargetResolutionError(f"invalid regex selector: {exc}") from exc
    if selector.kind == SelectorKind.PHONE:
        return bool(_PHONE_RE.search(text)) and (value == "*" or value in text)
    if selector.kind == SelectorKind.PRICE:
        return bool(_PRICE_RE.search(text)) and (value == "*" or value.casefold() in text.casefold())
    return False


def resolve_target(
    objects: Iterable[CdrObjectV1], selector: TargetSelectorV1
) -> ResolvedTargetV1:
    if selector.kind == SelectorKind.REGEX_TEXT and len(selector.value) > 200:
        raise TargetResolutionError("regex selector exceeds 200 characters")
    candidates = [
        item
        for item in objects
        if _matches(item, selector)
        and (selector.object_type is None or item.object_type == selector.object_type)
        and int(item.metadata.get("source_page", 1)) == selector.page
    ]
    if not candidates:
        raise TargetNotFoundError("selector matched no object")
    if selector.require_unique and len(candidates) != 1:
        raise AmbiguousTargetError(f"selector matched {len(candidates)} objects")
    chosen = candidates[0]
    duplicate_names = [item for item in objects if item.corel_name == chosen.corel_name]
    if len(duplicate_names) != 1:
        raise AmbiguousTargetError(
            f"Corel object name '{chosen.corel_name}' is not unique"
        )
    return ResolvedTargetV1(
        object_id=chosen.object_id,
        corel_name=chosen.corel_name,
        object_type=chosen.object_type,
        page=selector.page,
    )
