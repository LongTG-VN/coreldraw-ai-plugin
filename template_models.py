"""Pydantic models for template-based CorelDRAW production jobs."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class PlaceholderKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"


class PlaceholderSpec(BaseModel):
    """Map one business field to a named CorelDRAW shape."""

    key: str = Field(min_length=1, max_length=120)
    shape_name: str = Field(min_length=1, max_length=120)
    kind: PlaceholderKind = PlaceholderKind.TEXT
    required: bool = True
    max_length: Optional[int] = Field(default=None, ge=1, le=20_000)
    min_font_size: float = Field(default=10.0, gt=0, le=500)
    max_width: Optional[float] = Field(default=None, gt=0)


class RepeaterSpec(BaseModel):
    """Describe indexed placeholders such as item_1_name/item_1_price."""

    source: Literal["items"] = "items"
    start_index: int = Field(default=1, ge=0, le=10_000)
    max_items: int = Field(ge=1, le=1_000)
    fields: dict[str, str] = Field(min_length=1)
    clear_unused: bool = True

    @model_validator(mode="after")
    def validate_patterns(self) -> "RepeaterSpec":
        for field_name, pattern in self.fields.items():
            if not field_name.strip():
                raise ValueError("Repeater field names cannot be empty")
            if "{index}" not in pattern:
                raise ValueError(
                    f"Repeater pattern for '{field_name}' must contain '{{index}}'"
                )
        return self


class TemplateManifest(BaseModel):
    """Declarative contract between a .cdr template and the automation engine."""

    schema_version: str = "1.0"
    template_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,79}$")
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=1_000)
    cdr_path: str = Field(min_length=1, max_length=4_096)
    page_size: Optional[str] = Field(default=None, max_length=80)
    placeholders: list[PlaceholderSpec] = Field(default_factory=list)
    repeaters: list[RepeaterSpec] = Field(default_factory=list)

    def resolve_cdr_path(self, manifest_path: Path) -> Path:
        candidate = Path(self.cdr_path).expanduser()
        if not candidate.is_absolute():
            candidate = manifest_path.parent / candidate
        return candidate.resolve()


class MenuItem(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    price: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=1_000)
    section: str = Field(default="", max_length=160)
    image_path: Optional[str] = Field(default=None, max_length=4_096)
    image_prompt: Optional[str] = Field(default=None, max_length=4_000)


class MenuSection(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    items: list[MenuItem] = Field(min_length=1, max_length=500)


class MenuRenderRequest(BaseModel):
    """Input for one editable menu document and its print/preview outputs."""

    template_path_override: Optional[str] = Field(default=None, max_length=4_096)
    title: str = Field(min_length=1, max_length=300)
    subtitle: str = Field(default="", max_length=500)
    address: str = Field(default="", max_length=500)
    phone: str = Field(default="", max_length=120)
    sections: list[MenuSection] = Field(min_length=1, max_length=100)
    output_dir: str = Field(min_length=1, max_length=4_096)
    file_stem: str = Field(
        default="menu",
        pattern=r"^[A-Za-z0-9._-]{1,120}$",
    )
    generate_missing_images: bool = False
    image_model: Optional[str] = Field(default=None, max_length=200)
    image_aspect_ratio: str = Field(default="1:1", max_length=20)
    export_pdf: bool = True
    export_png: bool = True
    preview_dpi: int = Field(default=150, ge=72, le=600)

    def flattened_items(self) -> list[MenuItem]:
        flattened: list[MenuItem] = []
        for section in self.sections:
            for item in section.items:
                if item.section:
                    flattened.append(item)
                else:
                    flattened.append(item.model_copy(update={"section": section.name}))
        return flattened
