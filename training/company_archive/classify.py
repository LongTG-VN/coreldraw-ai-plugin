"""Deterministic extension classification without reading customer content."""

from __future__ import annotations

from training.company_archive.models import FileType


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}
VECTOR_SUFFIXES = {".svg", ".ai", ".eps"}


def classify_extension(extension: str) -> tuple[FileType, bool, bool, bool]:
    suffix = extension.casefold()
    if suffix == ".cdr":
        return FileType.CDR, True, False, False
    if suffix == ".cdt":
        return FileType.CDR_TEMPLATE, True, False, False
    if suffix == ".pdf":
        return FileType.PDF, False, True, False
    if suffix in VECTOR_SUFFIXES:
        return FileType.VECTOR, False, False, False
    if suffix in IMAGE_SUFFIXES:
        return FileType.IMAGE, False, False, True
    return FileType.OTHER, False, False, False
