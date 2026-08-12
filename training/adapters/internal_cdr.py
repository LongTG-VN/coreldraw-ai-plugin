"""Future private CorelDRAW adapter contract.

Private CDR extraction is intentionally not implemented until the company
archive is available. Keeping this boundary now prevents a second schema later.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from training.adapters.base import AdapterError
from training.schemas.design import DesignDocument


class InternalCdrModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class InternalCdrAssetV1(InternalCdrModel):
    asset_id: str = Field(min_length=1, max_length=200)
    source_path: str = Field(min_length=1, max_length=4096)
    asset_type: str = Field(min_length=1, max_length=100)
    license_class: str = Field(min_length=1, max_length=100)
    commercial_allowed: bool


class InternalCdrVersionV1(InternalCdrModel):
    version_id: str = Field(min_length=1, max_length=200)
    created_at: str = Field(min_length=1, max_length=100)
    design_document_path: str = Field(min_length=1, max_length=4096)
    preview_path: str = Field(min_length=1, max_length=4096)


class InternalCdrExportBundleV1(InternalCdrModel):
    """Future exporter hand-off; this does not parse proprietary CDR files."""

    schema_version: str = Field(pattern=r"^1\.0$")
    bundle_id: str = Field(min_length=1, max_length=200)
    cdr_path: str = Field(min_length=1, max_length=4096)
    preview_path: str = Field(min_length=1, max_length=4096)
    design_document_path: str = Field(min_length=1, max_length=4096)
    category: str = Field(min_length=1, max_length=200)
    assets: list[InternalCdrAssetV1] = Field(default_factory=list, max_length=10_000)
    font_families: list[str] = Field(default_factory=list, max_length=1_000)
    colors: list[str] = Field(default_factory=list, max_length=1_000)
    z_order: list[str] = Field(default_factory=list, max_length=10_000)
    project_metadata: dict[str, Any] = Field(default_factory=dict)
    version_history: list[InternalCdrVersionV1] = Field(default_factory=list, max_length=1_000)
    license_class: str = Field(min_length=1, max_length=100)
    commercial_allowed: bool
    approved_for_training: bool

    @model_validator(mode="after")
    def validate_training_rights(self) -> "InternalCdrExportBundleV1":
        if self.approved_for_training and not self.commercial_allowed:
            raise ValueError(
                "training-approved internal bundles must have verified commercial rights"
            )
        if len(self.z_order) != len(set(self.z_order)):
            raise ValueError("z_order contains duplicate object IDs")
        return self


class InternalCdrAdapter:
    def validate_export_bundle(self, row: dict[str, Any]) -> InternalCdrExportBundleV1:
        """Validate the future exporter manifest without ingesting private data."""

        return InternalCdrExportBundleV1.model_validate(row)

    def convert(self, row: dict[str, Any], index: int) -> DesignDocument:
        raise AdapterError(
            "Private CorelDRAW extraction is disabled until the approved archive "
            "and exporter contract are available."
        )


__all__ = [
    "InternalCdrAdapter",
    "InternalCdrAssetV1",
    "InternalCdrExportBundleV1",
    "InternalCdrVersionV1",
]
