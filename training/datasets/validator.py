"""Validation boundary for untrusted normalized dataset records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from training.schemas.design import DesignDocument


@dataclass(frozen=True)
class ValidationIssue:
    location: str
    message: str
    error_type: str


def validate_record(
    payload: dict[str, Any],
) -> tuple[DesignDocument | None, list[ValidationIssue]]:
    try:
        return DesignDocument.model_validate(payload), []
    except ValidationError as exc:
        issues = [
            ValidationIssue(
                location=".".join(str(part) for part in error["loc"]),
                message=str(error["msg"]),
                error_type=str(error["type"]),
            )
            for error in exc.errors()
        ]
        return None, issues


def validate_dataset_directory(dataset_dir: Path) -> dict[str, Any]:
    split_counts: dict[str, int] = {}
    issues: list[dict[str, Any]] = []
    license_classes: set[str] = set()

    for split in ("train", "validation", "test"):
        path = dataset_dir / f"{split}.jsonl"
        if not path.is_file():
            issues.append(
                {"file": str(path), "line": 0, "message": "missing split file"}
            )
            split_counts[split] = 0
            continue

        count = 0
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                count += 1
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    issues.append(
                        {
                            "file": str(path),
                            "line": line_number,
                            "message": f"invalid JSON: {exc}",
                        }
                    )
                    continue
                document, record_issues = validate_record(payload)
                if document is not None:
                    license_classes.add(document.source.license_class)
                for issue in record_issues:
                    issues.append(
                        {
                            "file": str(path),
                            "line": line_number,
                            "location": issue.location,
                            "message": issue.message,
                            "error_type": issue.error_type,
                        }
                    )
        split_counts[split] = count

    metadata_path = dataset_dir / "metadata.json"
    metadata: dict[str, Any] = {}
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(
                {
                    "file": str(metadata_path),
                    "line": 0,
                    "message": f"invalid metadata JSON: {exc}",
                }
            )
    else:
        issues.append(
            {"file": str(metadata_path), "line": 0, "message": "missing metadata"}
        )

    actual_total = sum(split_counts.values())
    if metadata:
        if metadata.get("total") != actual_total:
            issues.append(
                {
                    "file": str(metadata_path),
                    "line": 0,
                    "message": "metadata total does not match split files",
                }
            )
        if metadata.get("splits") != split_counts:
            issues.append(
                {
                    "file": str(metadata_path),
                    "line": 0,
                    "message": "metadata split counts do not match split files",
                }
            )

    return {
        "status": "valid" if not issues else "invalid",
        "dataset_dir": str(dataset_dir.resolve()),
        "total": actual_total,
        "splits": split_counts,
        "license_classes": sorted(license_classes),
        "issue_count": len(issues),
        "issues": issues[:100],
    }
