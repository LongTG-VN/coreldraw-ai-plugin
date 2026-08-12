"""Evidence-preserving diagnostics for the first v0.4 candidate pool."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from training.preference.v04.hardening import (
    infer_layout_family,
    placeholder_metrics,
    structural_diversity,
)
from training.preference.v04.models import HumanReviewV1, ReviewQueueItemV1
from training.preference.v04.pairing import load_queue
from training.schemas.design import DesignDocument


_BUSINESS_RE = re.compile(
    r"(?<!\w)(?:\d[\d.,]*\s*(?:k|vnd|đ|₫|usd|\$)|\d{1,3}(?:[.,]\d+)?\s*%|\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?)(?!\w)",
    re.I,
)


def load_human_reviews(root: Path) -> list[HumanReviewV1]:
    paths = sorted(root.resolve().rglob("*.json")) if root.exists() else []
    return [HumanReviewV1.model_validate_json(path.read_text(encoding="utf-8")) for path in paths]


def summarize_human_reviews(reviews: list[HumanReviewV1]) -> dict[str, Any]:
    choices = Counter(item.choice for item in reviews)
    categories = Counter(item.category for item in reviews)
    score_rows = [item.scores for item in reviews if item.scores is not None]
    score_names = (
        "overall_quality",
        "composition",
        "hierarchy",
        "typography",
        "brand_feeling",
        "overall",
    )
    score_means = {
        name: mean(values)
        for name in score_names
        if (
            values := [
                float(getattr(row, name))
                for row in score_rows
                if getattr(row, name, None) is not None
            ]
        )
    }
    return {
        "schema_version": "1.0",
        "snapshot_class": "diagnostic_generation_v1",
        "human_review_count": len(reviews),
        "a_wins": choices["a"],
        "b_wins": choices["b"],
        "ties": choices["tie"],
        "both_bad": choices["both_bad"],
        "both_bad_rate": choices["both_bad"] / len(reviews) if reviews else 0.0,
        "actual_ratings_available": len(score_rows),
        "score_means": score_means,
        "notes_available": sum(bool(item.notes) for item in reviews),
        "categories": dict(sorted(categories.items())),
        "reviewers": dict(sorted(Counter(item.reviewer for item in reviews).items())),
        "human_only_validation": all(
            item.source == "human"
            and item.human_verified is True
            and item.provenance.get("selection_source") == "human_ui_action"
            for item in reviews
        ),
        "user_reported_diagnostic_quality": {
            "value": 4,
            "scale": 10,
            "source": "user_reported_overall_pool_feedback",
            "not_per_candidate_ground_truth": True,
        },
        "eligible_for_preference_training": False,
    }


def write_diagnostic_snapshot(reviews_root: Path, output: Path) -> dict[str, Any]:
    destination = output.resolve()
    review_path = destination / "human_review_snapshot.jsonl"
    summary_path = destination / "review_summary.json"
    if review_path.exists() or summary_path.exists():
        raise FileExistsError("diagnostic human-review snapshot is immutable")
    reviews = load_human_reviews(reviews_root)
    destination.mkdir(parents=True, exist_ok=True)
    review_path.write_text(
        "".join(item.model_dump_json() + "\n" for item in reviews),
        encoding="utf-8",
    )
    summary = summarize_human_reviews(reviews)
    summary["snapshot_sha256"] = hashlib.sha256(review_path.read_bytes()).hexdigest()
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def _text_fingerprint(document: DesignDocument) -> str:
    values = [
        " ".join(
            str(item.metadata.get("typography_fit", {}).get("original_content") or item.text.content).split()
        ).casefold()
        for item in document.elements
        if item.text is not None
    ]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode("utf-8")).hexdigest()


def _asset_fingerprint(document: DesignDocument) -> str:
    values = [
        {
            "id": item.id,
            "source": item.source,
            "sha256": item.metadata.get("sha256"),
        }
        for item in sorted(document.assets, key=lambda value: value.id)
    ]
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()


def _business_fingerprint(document: DesignDocument) -> str:
    values: list[str] = []
    for element in document.elements:
        if element.text is None:
            continue
        values.extend(match.group(0).casefold() for match in _BUSINESS_RE.finditer(element.text.content))
    return hashlib.sha256(json.dumps(sorted(values)).encode("utf-8")).hexdigest()


def _canvas_fingerprint(document: DesignDocument) -> str:
    value = [float(document.canvas.width), float(document.canvas.height), document.canvas.unit]
    return hashlib.sha256(json.dumps(value).encode("utf-8")).hexdigest()


def audit_candidate_pool(queue_path: Path) -> dict[str, Any]:
    queue = load_queue(queue_path)
    by_brief: dict[str, dict[str, Any]] = {}
    for item in queue:
        if item.pairing_stage == "historical":
            continue
        group = by_brief.setdefault(
            item.brief_id,
            {"category": item.category, "candidates": {}},
        )
        for candidate in (item.candidate_1, item.candidate_2):
            group["candidates"][candidate.design_id] = candidate
    rows = []
    for brief_id, group in sorted(by_brief.items()):
        candidates = group["candidates"]
        documents = {
            candidate_id: DesignDocument.model_validate_json(
                Path(candidate.design_path).read_text(encoding="utf-8")
            )
            for candidate_id, candidate in candidates.items()
        }
        text_hashes = {_text_fingerprint(value) for value in documents.values()}
        asset_hashes = {_asset_fingerprint(value) for value in documents.values()}
        business_hashes = {_business_fingerprint(value) for value in documents.values()}
        canvas_hashes = {_canvas_fingerprint(value) for value in documents.values()}
        diversity = structural_diversity(documents)
        placeholder_rows = [placeholder_metrics(value) for value in documents.values()]
        rows.append(
            {
                "brief_id": brief_id,
                "category": group["category"],
                "candidate_count": len(documents),
                "content_consistent": len(text_hashes) == 1,
                "asset_consistent": len(asset_hashes) == 1,
                "business_value_consistent": len(business_hashes) == 1,
                "canvas_consistent": len(canvas_hashes) == 1,
                "distinct_layout_family_count": len(
                    {infer_layout_family(value) for value in documents.values()}
                ),
                "mean_pairwise_candidate_diversity": diversity[
                    "mean_pairwise_candidate_diversity"
                ],
                "minimum_pairwise_candidate_diversity": diversity[
                    "minimum_pairwise_candidate_diversity"
                ],
                "placeholder_count": sum(
                    int(item["placeholder_count"]) for item in placeholder_rows
                ),
                "mean_placeholder_area_ratio": mean(
                    float(item["placeholder_area_ratio"]) for item in placeholder_rows
                ),
                "technical_candidate_count": len(documents),
            }
        )
    count = len(rows)
    return {
        "schema_version": "1.0",
        "pool": "v0_4_phase1_generation_v1",
        "brief_count": count,
        "candidate_count": sum(int(item["candidate_count"]) for item in rows),
        "content_consistency_rate": sum(item["content_consistent"] for item in rows) / count if count else 0.0,
        "asset_consistency_rate": sum(item["asset_consistent"] for item in rows) / count if count else 0.0,
        "business_value_consistency_rate": sum(item["business_value_consistent"] for item in rows) / count if count else 0.0,
        "canvas_consistency_rate": sum(item["canvas_consistent"] for item in rows) / count if count else 0.0,
        "mean_pairwise_candidate_diversity": mean(
            float(item["mean_pairwise_candidate_diversity"]) for item in rows
        ) if rows else 0.0,
        "minimum_pairwise_candidate_diversity": min(
            (float(item["minimum_pairwise_candidate_diversity"]) for item in rows),
            default=0.0,
        ),
        "mean_distinct_layout_family_count": mean(
            int(item["distinct_layout_family_count"]) for item in rows
        ) if rows else 0.0,
        "placeholder_count": sum(int(item["placeholder_count"]) for item in rows),
        "mean_placeholder_area_ratio": mean(
            float(item["mean_placeholder_area_ratio"]) for item in rows
        ) if rows else 0.0,
        "technical_pass_rate": 1.0 if rows else 0.0,
        "rows": rows,
    }


__all__ = [
    "audit_candidate_pool",
    "load_human_reviews",
    "summarize_human_reviews",
    "write_diagnostic_snapshot",
]
