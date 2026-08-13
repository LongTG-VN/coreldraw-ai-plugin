"""Filesystem safety guards for immutable company source archives."""

from __future__ import annotations

from pathlib import Path


class ArchiveSafetyError(ValueError):
    """Raised when an archive/workspace path could permit source mutation."""


def resolve_archive_paths(root: Path, workspace: Path) -> tuple[Path, Path]:
    source = root.expanduser().resolve(strict=True)
    target = workspace.expanduser().resolve(strict=False)
    if not source.is_dir():
        raise ArchiveSafetyError(f"archive root is not a directory: {source}")
    if source == target or source in target.parents or target in source.parents:
        raise ArchiveSafetyError("workspace and immutable archive root must be disjoint")
    target.mkdir(parents=True, exist_ok=True)
    return source, target


def resolve_source_file(path: Path, root: Path, *, suffixes: set[str] | None = None) -> Path:
    source_root = root.expanduser().resolve(strict=True)
    candidate = path.expanduser().resolve(strict=True)
    if candidate == source_root or source_root not in candidate.parents:
        raise ArchiveSafetyError("source file is outside approved archive root")
    if not candidate.is_file():
        raise ArchiveSafetyError("source path is not a regular file")
    if suffixes and candidate.suffix.casefold() not in {item.casefold() for item in suffixes}:
        raise ArchiveSafetyError(f"unsupported source extension: {candidate.suffix}")
    return candidate


def source_stat_guard(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, getattr(stat, "st_ctime_ns", 0)


def assert_source_unchanged(path: Path, before: tuple[int, int, int]) -> None:
    after = source_stat_guard(path)
    if before != after:
        raise ArchiveSafetyError(
            f"immutable source changed during read-only operation: {path}"
        )

