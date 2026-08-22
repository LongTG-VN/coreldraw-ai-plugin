"""Sanitized root-cause clustering for Corel operator terminal failures."""

from __future__ import annotations

from collections import Counter
from typing import Any


def classify_operator_failure(result: dict[str, Any]) -> tuple[str, str]:
    error_code = str(result.get("error_code") or "UNKNOWN")
    error = str(result.get("error") or "").casefold()
    if "textrange" in error or "text range" in error:
        return (
            "TEXT_RANGE_COM",
            "reacquire the live text shape and apply a bounded retry",
        )
    if "changed outside policy" in error or "bbox" in error:
        return (
            "COLLATERAL_BBOX_POLICY",
            "allow only an explicitly declared direct container dependency",
        )
    if "worker" in error_code.casefold() or "worker" in error:
        return (
            "WORKER_RUNTIME",
            "isolate the file, preserve timeout evidence, and retry once",
        )
    return "OTHER", "retain terminal failure pending a narrow reproduced fix"


def build_failure_analysis(results: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [item for item in results if item.get("result") == "FAILED"]
    records: list[dict[str, Any]] = []
    for item in failures:
        category, fix_candidate = classify_operator_failure(item)
        records.append(
            {
                "design_id": item.get("source_token"),
                "operation": item.get("metadata", {})
                .get("planner", {})
                .get("operation_mode"),
                "error_category": category,
                "error_code": item.get("error_code"),
                "corel_stage": (
                    "transaction"
                    if category in {"TEXT_RANGE_COM", "COLLATERAL_BBOX_POLICY"}
                    else "worker"
                    if category == "WORKER_RUNTIME"
                    else "unknown"
                ),
                "attempt_count": item.get("attempt"),
                "rollback_status": (
                    "VERIFIED" if item.get("rollback_verified") else "NOT_VERIFIED"
                ),
                "source_unchanged": bool(item.get("source_unchanged")),
                "reproducible": None,
                "fix_candidate": fix_candidate,
            }
        )
    categories = Counter(item["error_category"] for item in records)
    return {
        "schema_version": "1.0",
        "failure_count": len(records),
        "categories": dict(sorted(categories.items())),
        "records": records,
        "contains_private_paths": False,
    }


__all__ = ["build_failure_analysis", "classify_operator_failure"]
