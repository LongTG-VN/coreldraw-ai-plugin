"""Common dataset adapter contract."""

from __future__ import annotations

from typing import Any, Protocol

from training.schemas.design import DesignDocument


class AdapterError(ValueError):
    """Raised when an upstream row cannot be normalized safely."""


class DesignAdapter(Protocol):
    def convert(self, row: dict[str, Any], index: int) -> DesignDocument: ...
