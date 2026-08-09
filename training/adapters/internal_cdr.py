"""Future private CorelDRAW adapter contract.

Private CDR extraction is intentionally not implemented until the company
archive is available. Keeping this boundary now prevents a second schema later.
"""

from __future__ import annotations

from typing import Any

from training.adapters.base import AdapterError
from training.schemas.design import DesignDocument


class InternalCdrAdapter:
    def convert(self, row: dict[str, Any], index: int) -> DesignDocument:
        raise AdapterError(
            "Private CorelDRAW extraction is disabled until the approved archive "
            "and exporter contract are available."
        )
