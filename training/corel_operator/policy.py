"""Fail-closed path and mutation-scope policy for the Corel operator."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from training.company_archive.safety import resolve_source_file


class OperatorPolicyError(ValueError):
    pass


def source_token(path: Path, archive_root: Path) -> str:
    source = resolve_source_file(path, archive_root, suffixes={".cdr", ".cdt"})
    relative = source.relative_to(archive_root.resolve()).as_posix().encode("utf-8")
    return "source:" + hashlib.sha256(relative).hexdigest()[:24]


def validate_working_copy_path(path: Path, workspace: Path, source: Path) -> Path:
    root = workspace.expanduser().resolve()
    target = path.expanduser().resolve(strict=False)
    source_resolved = source.expanduser().resolve()
    if target.suffix.casefold() != ".cdr":
        raise OperatorPolicyError("working copy must use .cdr")
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise OperatorPolicyError("working copy must remain under operator workspace") from exc
    if target == source_resolved:
        raise OperatorPolicyError("source and working copy must differ")
    if target.exists():
        raise OperatorPolicyError("working copy target already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def sanitize_error(error: BaseException | str, *, archive_root: Path | None = None) -> str:
    message = str(error).replace("\r", " ").replace("\n", " ")
    message = re.sub(r"[\\/]+", "/", message)
    if archive_root is not None:
        normalized_root = str(archive_root.resolve()).replace("\\", "/")
        message = re.sub(
            re.escape(normalized_root),
            "<ARCHIVE_ROOT>",
            message,
            flags=re.IGNORECASE,
        )
    return message[:500]
