"""Shared deterministic aggregation for Design AI postprocessor ablations."""

from __future__ import annotations

from statistics import mean
from typing import Any


ABLATION_VARIANTS = (
    "rag_recovery_only",
    "rag_reference_layout_typography",
    "rag_reference_visual_full",
)


def aggregate_ablation_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("ablation requires at least one row")
    output: dict[str, Any] = {}
    metrics = (
        "combined",
        "technical",
        "overlap",
        "spacing",
        "hierarchy",
        "text_fit",
        "coverage",
    )
    for variant in ABLATION_VARIANTS:
        values = [row["variants"][variant] for row in rows]
        valid = [value for value in values if value.get("strict_schema_valid")]
        output[variant] = {
            "prompt_count": len(values),
            "strict_schema_valid": len(valid),
            "corel_compile_success": sum(bool(value.get("corel_compile_success")) for value in values),
            "preview_success": sum(bool(value.get("preview_exists")) for value in values),
            "metrics": {
                metric: mean(float(value["metrics"][metric]) for value in valid)
                if valid
                else 0.0
                for metric in metrics
            },
        }
    return output


__all__ = ["ABLATION_VARIANTS", "aggregate_ablation_rows"]
