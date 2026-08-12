"""Strict local-asset contracts and integrity validation for Design AI v0.3.3."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, model_validator


AssetRole = Literal["logo", "hero", "product", "background", "icon", "illustration"]
FitMode = Literal["contain", "cover", "fit_width", "fit_height"]
SourceType = Literal["user_provided", "project_owned", "public_asset", "benchmark_asset"]


class AssetContractError(ValueError):
    """Raised when a local asset or its declared provenance is invalid."""


class StrictAssetModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssetInputV1(StrictAssetModel):
    schema_version: Literal["1.0"] = "1.0"
    asset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,99}$")
    role: AssetRole
    path: str = Field(min_length=1, max_length=4096)
    mime_type: Literal["image/jpeg", "image/png", "image/svg+xml"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width_px: int = Field(gt=0, le=100_000)
    height_px: int = Field(gt=0, le=100_000)
    aspect_ratio: float = Field(gt=0, le=1000)
    has_alpha: bool
    source_type: SourceType
    source_url: str | None = Field(default=None, max_length=4096)
    source_original_url: str | None = Field(default=None, max_length=4096)
    source_page: str | None = Field(default=None, max_length=4096)
    license_name: str = Field(min_length=1, max_length=200)
    license_url: str | None = Field(default=None, max_length=4096)
    commercial_allowed: bool
    modification_allowed: bool
    research_only: bool
    benchmark_only: bool = True
    project_owned: bool = False
    downloaded_at: str | None = None
    fit_mode: FitMode
    focal_x: float | None = Field(default=None, ge=0, le=1)
    focal_y: float | None = Field(default=None, ge=0, le=1)
    palette_hint: list[str] = Field(default_factory=list, max_length=8)
    preview_path: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def validate_provenance(self) -> "AssetInputV1":
        if not math.isclose(
            self.aspect_ratio,
            self.width_px / self.height_px,
            rel_tol=1e-4,
            abs_tol=1e-6,
        ):
            raise ValueError("aspect_ratio does not match dimensions")
        if self.role == "logo" and self.fit_mode != "contain":
            raise ValueError("logos must use contain fit by default")
        if (self.focal_x is None) != (self.focal_y is None):
            raise ValueError("focal_x and focal_y must be provided together")
        if self.project_owned != (self.source_type == "project_owned"):
            raise ValueError("project_owned must match source_type")
        if self.source_type == "public_asset" and not self.source_page:
            raise ValueError("public assets require an original source page")
        if self.commercial_allowed and self.research_only:
            raise ValueError("commercial assets cannot also be research_only")
        if self.commercial_allowed and not self.modification_allowed:
            raise ValueError("commercial benchmark assets must allow modification")
        return self


class AssetManifestV1(StrictAssetModel):
    schema_version: Literal["1.0"] = "1.0"
    case_id: Literal["spa", "cafe", "sale", "menu", "signage"]
    benchmark_name: Literal["design_ai_v0.3.3_real_assets"] = (
        "design_ai_v0.3.3_real_assets"
    )
    benchmark_sample_data: bool
    customer_provided: bool = False
    assets: list[AssetInputV1] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_unique_assets(self) -> "AssetManifestV1":
        ids = [asset.asset_id for asset in self.assets]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate asset IDs")
        roles = [asset.role for asset in self.assets]
        if len(roles) != len(set(roles)):
            raise ValueError("v0.3.3 benchmark allows one asset per role")
        if self.case_id in {"sale", "menu"} and not self.benchmark_sample_data:
            raise ValueError("sale/menu benchmark content must be marked sample data")
        return self


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _svg_dimensions(path: Path) -> tuple[int, int]:
    import xml.etree.ElementTree as ET

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise AssetContractError(f"invalid SVG: {path}") from exc
    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise AssetContractError(f"SVG root element is missing: {path}")
    if any(node.tag.rsplit("}", 1)[-1].casefold() == "script" for node in root.iter()):
        raise AssetContractError(f"SVG script is not allowed: {path}")
    for node in root.iter():
        for key, value in node.attrib.items():
            if key.rsplit("}", 1)[-1].casefold() == "href" and "://" in value:
                raise AssetContractError(f"remote SVG references are not allowed: {path}")
    try:
        width = int(round(float(str(root.attrib["width"]).removesuffix("px"))))
        height = int(round(float(str(root.attrib["height"]).removesuffix("px"))))
    except (KeyError, ValueError) as exc:
        raise AssetContractError(f"SVG requires numeric width and height: {path}") from exc
    return width, height


def inspect_asset_file(path: Path) -> tuple[str, int, int, bool]:
    suffix = path.suffix.casefold()
    if suffix == ".svg":
        width, height = _svg_dimensions(path)
        return "image/svg+xml", width, height, True
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            mime = Image.MIME.get(image.format or "")
            if mime not in {"image/jpeg", "image/png"}:
                raise AssetContractError(f"unsupported raster format: {path}")
            oriented = ImageOps.exif_transpose(image)
            return mime, oriented.width, oriented.height, "A" in oriented.getbands()
    except (UnidentifiedImageError, OSError) as exc:
        raise AssetContractError(f"invalid image file: {path}") from exc


def validate_asset_input(asset: AssetInputV1, *, base_dir: Path) -> Path:
    base = base_dir.expanduser().resolve()
    path = (base / asset.path).resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise AssetContractError("asset path escapes manifest directory") from exc
    if not path.is_file():
        raise AssetContractError(f"asset file does not exist: {path}")
    mime, width, height, has_alpha = inspect_asset_file(path)
    if mime != asset.mime_type:
        raise AssetContractError(f"MIME mismatch for {asset.asset_id}")
    if (width, height) != (asset.width_px, asset.height_px):
        raise AssetContractError(f"dimension mismatch for {asset.asset_id}")
    if has_alpha != asset.has_alpha:
        raise AssetContractError(f"alpha metadata mismatch for {asset.asset_id}")
    if sha256_file(path) != asset.sha256:
        raise AssetContractError(f"SHA-256 mismatch for {asset.asset_id}")
    return path


def validate_asset_manifest(manifest: AssetManifestV1, *, base_dir: Path) -> dict[str, Path]:
    return {
        asset.asset_id: validate_asset_input(asset, base_dir=base_dir)
        for asset in manifest.assets
    }


__all__ = [
    "AssetContractError",
    "AssetInputV1",
    "AssetManifestV1",
    "FitMode",
    "inspect_asset_file",
    "sha256_file",
    "validate_asset_input",
    "validate_asset_manifest",
]
