"""Diagnose prior text-target refusals without exposing customer text."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from training.company_archive.database import ArchiveDatabase
from training.company_archive.inspector import CompanyCdrInspector
from training.corel_operator.policy import source_token
from training.corel_operator.state import OperatorStateDatabase


def classify_text_target_refusal(inspection: Any) -> tuple[str, dict[str, Any]]:
    stable_counts = Counter(item.object_id for item in inspection.objects if item.object_id)
    stable = [
        item
        for item in inspection.objects
        if item.object_id and stable_counts[item.object_id] == 1
    ]
    text = [item for item in stable if item.object_type == "text" and item.text]
    eligible = [
        item
        for item in text
        if not bool(item.metadata.get("locked", False))
        and not bool(item.metadata.get("bbox_clipped_to_page", False))
    ]
    alpha = [item for item in eligible if any(char.isalpha() for char in item.text or "")]
    with_font = [item for item in alpha if item.font_family]
    conventional_size = [
        item
        for item in with_font
        if item.font_size is not None and 3.0 <= float(item.font_size) <= 36.0
    ]
    normalized = Counter((item.text or "").strip().casefold() for item in conventional_size)
    unique_text = [
        item
        for item in conventional_size
        if normalized[(item.text or "").strip().casefold()] == 1
    ]
    metrics = {
        "stable_text": len(text),
        "eligible_text": len(eligible),
        "alpha_text": len(alpha),
        "stable_font_text": len(with_font),
        "conventional_size_text": len(conventional_size),
        "unique_conventional_text": len(unique_text),
        "duplicate_conventional_text": len(conventional_size) - len(unique_text),
        "font_size_missing": sum(item.font_size is None for item in with_font),
        "font_size_above_36": sum(
            item.font_size is not None and float(item.font_size) > 36.0
            for item in with_font
        ),
        "font_size_below_3": sum(
            item.font_size is not None and float(item.font_size) < 3.0
            for item in with_font
        ),
        "font_size_min": min(
            (float(item.font_size) for item in with_font if item.font_size is not None),
            default=None,
        ),
        "font_size_max": max(
            (float(item.font_size) for item in with_font if item.font_size is not None),
            default=None,
        ),
    }
    if not text or not eligible:
        reason = "TARGET_NOT_FOUND"
    elif not alpha:
        reason = "UNSUPPORTED_TEXT_TYPE"
    elif not with_font:
        reason = "MIXED_FONT"
    elif not conventional_size:
        reason = "SELECTOR_TOO_STRICT"
    elif not unique_text:
        reason = "MULTIPLE_MATCHES"
    else:
        reason = "OTHER"
    return reason, metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--previous-state", type=Path, required=True)
    parser.add_argument("--move-state", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    archive_root = args.archive_root.resolve()
    previous = OperatorStateDatabase(args.previous_state)
    refused = {
        str(row["result"]["source_token"])
        for row in previous.batch_rows("real-mutation-pilot-001")
        if row["result"].get("result") == "UNSUPPORTED"
    }
    source_rows = {
        source_token(Path(str(row["absolute_path"])), archive_root): row
        for row in ArchiveDatabase(args.inventory).rows("cdr_candidate=1")
    }
    rows: list[dict[str, Any]] = []
    for index, token in enumerate(sorted(refused), start=1):
        source_row = source_rows.get(token)
        if source_row is None:
            rows.append({"source_token": token, "reason": "TARGET_NOT_FOUND"})
            continue
        inspection = CompanyCdrInspector().inspect(
            Path(str(source_row["absolute_path"])), archive_root=archive_root
        )
        reason, metrics = classify_text_target_refusal(inspection)
        rows.append({"source_token": token, "reason": reason, "metrics": metrics})
        print(f"[{index}/{len(refused)}] {token} {reason}", flush=True)

    move_rows: list[dict[str, Any]] = []
    if args.move_state is not None:
        move_failures = [
            row["result"]
            for row in OperatorStateDatabase(args.move_state).batch_rows(
                "real-mutation-pilot-001"
            )
            if row["result"].get("result") == "FAILED"
        ]
        for previous_result in move_failures:
            token = str(previous_result["source_token"])
            source_row = source_rows[token]
            inspection = CompanyCdrInspector().inspect(
                Path(str(source_row["absolute_path"])), archive_root=archive_root
            )
            stable_counts = Counter(
                item.object_id for item in inspection.objects if item.object_id
            )
            movable = [
                item
                for item in inspection.objects
                if item.object_id
                and stable_counts[item.object_id] == 1
                and not bool(item.metadata.get("locked", False))
                and not bool(item.metadata.get("bbox_clipped_to_page", False))
                and item.parent_id is None
                and item.object_type != "group"
                and item.bbox["x"] + item.bbox["width"] + 1 <= inspection.page_width
                and item.bbox["y"] + item.bbox["height"] + 1 <= inspection.page_height
            ]
            target = (previous_result.get("resolved_targets") or [{}])[0]
            move_rows.append(
                {
                    "source_token": token,
                    "previous_target_type": target.get("object_type"),
                    "error_code": previous_result.get("error_code"),
                    "error_class": (
                        "OBJECT_IDENTITY_DRIFT"
                        if previous_result.get("error") == "object identity set changed"
                        else "COLLATERAL_BBOX_VALIDATION"
                    ),
                    "movable_by_type": dict(
                        sorted(Counter(item.object_type for item in movable).items())
                    ),
                    "non_text_alternative_count": sum(
                        item.object_type != "text" for item in movable
                    ),
                    "rollback_verified": bool(previous_result.get("rollback_verified")),
                }
            )

    summary = {
        "schema_version": "1.0",
        "expected": len(refused),
        "processed": len(rows),
        "source_content_included": False,
        "reasons": dict(sorted(Counter(row["reason"] for row in rows).items())),
        "rows": rows,
        "move_rows": move_rows,
    }
    args.workspace.mkdir(parents=True, exist_ok=True)
    (args.workspace / "text_target_diagnosis.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if len(rows) == len(refused) else 2


if __name__ == "__main__":
    raise SystemExit(main())
