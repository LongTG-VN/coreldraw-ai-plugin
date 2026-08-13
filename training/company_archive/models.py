"""Strict contracts for immutable archive inventory and human Gold curation."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FileType(str, Enum):
    CDR = "CDR"
    CDR_TEMPLATE = "CDR_TEMPLATE"
    PDF = "PDF"
    VECTOR = "VECTOR"
    IMAGE = "IMAGE"
    OTHER = "OTHER"


class InventoryStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    METADATA_INDEXED = "METADATA_INDEXED"
    ERROR = "ERROR"


class WorkStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class HumanQualityStatus(str, Enum):
    UNREVIEWED = "UNREVIEWED"
    APPROVE = "APPROVE"
    MAYBE = "MAYBE"
    REJECT = "REJECT"


class GoldStatus(str, Enum):
    NOT_GOLD = "NOT_GOLD"
    GOLD_CANDIDATE = "GOLD_CANDIDATE"
    HUMAN_CERTIFIED_GOLD = "HUMAN_CERTIFIED_GOLD"


class RightsStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    CONFIRMED_COMPANY_OWNED = "CONFIRMED_COMPANY_OWNED"
    RESTRICTED = "RESTRICTED"


class ArchiveCategory(str, Enum):
    SALE = "SALE"
    SPA = "SPA"
    SIGNAGE = "SIGNAGE"
    MENU = "MENU"
    CAFE = "CAFE"
    BUSINESS_CARD = "BUSINESS_CARD"
    BANNER = "BANNER"
    LOGO = "LOGO"
    PRINT = "PRINT"
    OTHER = "OTHER"


class ArchiveFileRecord(StrictModel):
    file_id: str = Field(pattern=r"^file:[a-f0-9]{32}$")
    absolute_path: str
    relative_path: str
    filename: str
    extension: str
    size_bytes: int = Field(ge=0)
    modified_time: float
    created_time: float | None = None
    fast_hash: str | None = None
    sha256_status: WorkStatus = WorkStatus.PENDING
    sha256: str | None = None
    file_type: FileType
    cdr_candidate: bool = False
    pdf_candidate: bool = False
    image_candidate: bool = False
    inventory_status: InventoryStatus = InventoryStatus.METADATA_INDEXED
    preview_status: WorkStatus = WorkStatus.PENDING
    corel_inspection_status: WorkStatus = WorkStatus.PENDING
    duplicate_group_id: str | None = None
    duplicate_confidence: str | None = None
    category: ArchiveCategory | None = None
    category_source: str | None = None
    human_quality_status: HumanQualityStatus = HumanQualityStatus.UNREVIEWED
    gold_status: GoldStatus = GoldStatus.NOT_GOLD
    rights_status: RightsStatus = RightsStatus.UNKNOWN
    commercial_allowed: bool = False
    human_reviewer: str | None = None
    notes: str | None = None
    preview_path: str | None = None
    preview_width: int | None = Field(default=None, ge=1)
    preview_height: int | None = Field(default=None, ge=1)
    render_error: str | None = None
    inspection_json: str | None = None

    @model_validator(mode="after")
    def enforce_human_gold_rights(self) -> "ArchiveFileRecord":
        if self.gold_status == GoldStatus.HUMAN_CERTIFIED_GOLD:
            if self.human_quality_status != HumanQualityStatus.APPROVE:
                raise ValueError("human-certified Gold requires APPROVE quality status")
            if self.rights_status != RightsStatus.CONFIRMED_COMPANY_OWNED:
                raise ValueError("human-certified Gold requires confirmed company ownership")
            if not self.human_reviewer:
                raise ValueError("human-certified Gold requires a reviewer")
            if not self.sha256:
                raise ValueError("human-certified Gold requires full SHA256 provenance")
        if self.commercial_allowed and self.rights_status != RightsStatus.CONFIRMED_COMPANY_OWNED:
            raise ValueError("commercial permission requires confirmed company ownership")
        return self


class CdrObjectV1(StrictModel):
    object_id: str
    corel_name: str
    object_type: str
    bbox: dict[str, float]
    bbox_norm: dict[str, float]
    rotation: float = 0.0
    z_index: int = 0
    layer: str = "default"
    parent_id: str | None = None
    text: str | None = None
    font_family: str | None = None
    font_size: float | None = None
    font_weight: int | str | None = None
    alignment: str | None = None
    fill: dict[str, Any] | None = None
    stroke: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CdrInspectionV1(StrictModel):
    schema_version: str = "1.0"
    source_path: str
    source_size_bytes: int = Field(ge=0)
    source_mtime_ns: int
    corel_version: str
    document_version: str | None = None
    page_count: int = Field(ge=1)
    page_width: float = Field(gt=0)
    page_height: float = Field(gt=0)
    unit: str
    corel_unit_code: int
    layer_count: int = Field(ge=0)
    object_count: int = Field(ge=0)
    text_object_count: int = Field(ge=0)
    bitmap_count: int = Field(ge=0)
    vector_count: int = Field(ge=0)
    group_count: int = Field(ge=0)
    font_families: list[str] = Field(default_factory=list)
    color_summary: list[dict[str, Any]] = Field(default_factory=list)
    objects: list[CdrObjectV1] = Field(default_factory=list)
    source_save_called: bool = False


class ScanSummary(StrictModel):
    root: str
    workspace: str
    scan_id: str
    resumed: bool
    completed: bool
    scanned_files: int = Field(ge=0)
    skipped_before_cursor: int = Field(ge=0)
    total_files: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    cdr_count: int = Field(ge=0)
    cdr_total_size: int = Field(ge=0)
    pdf_count: int = Field(ge=0)
    image_count: int = Field(ge=0)
    other_count: int = Field(ge=0)
    largest_files: list[dict[str, Any]] = Field(default_factory=list)
    oldest_modified_time: float | None = None
    newest_modified_time: float | None = None
