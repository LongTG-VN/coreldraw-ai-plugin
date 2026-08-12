"""Evidence-preserving analytics for mixed human-review queues.

Queue identity is recovered from the persisted session queue hash.  A review is
never assigned to a generation merely because its timestamp or category looks
similar to another review.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

from pydantic import Field, model_validator

from training.preference.v04.models import (
    HumanReviewV1,
    ReviewSessionV1,
    StrictModel,
)
from training.preference.v04.pairing import sha256_file


CATEGORY_ALIAS_MAP: dict[str, str] = {
    # Each alias is backed by the queue brief IDs (for example sale_bold,
    # business_card and restaurant_menu), not by color/style similarity.
    "poster_sale": "sale",
    "sale": "sale",
    "bang_hieu": "signage",
    "signage": "signage",
    "business_card": "business_card",
    "card_visit": "business_card",
    "cosmetics": "cosmetics",
    "my_pham": "cosmetics",
    "menu": "menu",
    "nha_hang": "menu",
    "grand_opening": "opening",
    "khai_truong": "opening",
    "banner_social": "social_banner",
    "social_banner": "social_banner",
    "tra_sua": "milk_tea",
    "milk_tea": "milk_tea",
}


class QueueIdentityV1(StrictModel):
    queue_id: str = Field(min_length=1, max_length=200)
    generation_version: str = Field(min_length=1, max_length=200)
    queue_path: str = Field(min_length=1, max_length=4096)
    queue_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ReconstructedReviewV1(StrictModel):
    review_id: str
    session_id: str
    queue_id: str
    generation_version: str
    provenance_status: str
    provenance_issues: list[str] = Field(default_factory=list)
    brief_id: str
    category: str
    normalized_category: str
    design_a_id: str
    design_b_id: str
    choice: str
    reviewer: str
    timestamp: str
    scores: dict[str, int | None] | None = None
    notes: str | None = None
    source: str
    human_verified: bool

    @model_validator(mode="after")
    def human_only(self) -> "ReconstructedReviewV1":
        if self.source != "human" or self.human_verified is not True:
            raise ValueError("analytics accepts explicit human records only")
        return self


def queue_identity(
    path: Path,
    *,
    queue_id: str,
    generation_version: str,
) -> QueueIdentityV1:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return QueueIdentityV1(
        queue_id=queue_id,
        generation_version=generation_version,
        queue_path=str(resolved),
        queue_sha256=sha256_file(resolved),
    )


def load_sessions(root: Path) -> list[ReviewSessionV1]:
    paths = sorted(root.resolve().glob("*.json")) if root.exists() else []
    return [
        ReviewSessionV1.model_validate_json(path.read_text(encoding="utf-8"))
        for path in paths
    ]


def normalize_category(category: str) -> str:
    normalized = category.strip().casefold().replace("-", "_").replace(" ", "_")
    return CATEGORY_ALIAS_MAP.get(normalized, normalized)


def reconstruct_review_provenance(
    reviews: Iterable[HumanReviewV1],
    sessions: Iterable[ReviewSessionV1],
    queues: Iterable[QueueIdentityV1],
) -> list[ReconstructedReviewV1]:
    session_index = {item.session_id: item for item in sessions}
    queue_index = {item.queue_sha256: item for item in queues}
    rows: list[ReconstructedReviewV1] = []
    for review in reviews:
        issues: list[str] = []
        session = session_index.get(review.session_id)
        explicit_generation = str(
            review.provenance.get("generation_version") or ""
        ).strip()
        queue = queue_index.get(session.queue_sha256) if session is not None else None
        if session is None:
            issues.append("SESSION_NOT_FOUND")
        if queue is not None:
            if explicit_generation and explicit_generation != queue.generation_version:
                issues.append("GENERATION_VERSION_CONFLICT")
                queue_id = "unknown"
                generation_version = "unknown"
                status = "conflict"
            else:
                queue_id = queue.queue_id
                generation_version = queue.generation_version
                status = "queue_hash_and_record" if explicit_generation else "queue_hash"
        elif explicit_generation:
            queue_id = "unknown"
            generation_version = explicit_generation
            status = "record_metadata_only"
            issues.append("QUEUE_HASH_UNKNOWN")
        else:
            queue_id = "unknown"
            generation_version = "unknown"
            status = "unknown"
            issues.append("QUEUE_HASH_UNKNOWN")
        rows.append(
            ReconstructedReviewV1(
                review_id=review.review_id,
                session_id=review.session_id,
                queue_id=queue_id,
                generation_version=generation_version,
                provenance_status=status,
                provenance_issues=issues,
                brief_id=review.brief_id,
                category=review.category,
                normalized_category=normalize_category(review.category),
                design_a_id=review.design_a_id,
                design_b_id=review.design_b_id,
                choice=review.choice,
                reviewer=review.reviewer,
                timestamp=review.created_at.isoformat(),
                scores=(
                    review.scores.model_dump(mode="json")
                    if review.scores is not None
                    else None
                ),
                notes=review.notes,
                source=review.source,
                human_verified=review.human_verified,
            )
        )
    return sorted(rows, key=lambda item: (item.timestamp, item.review_id))


def _aggregate(rows: Iterable[ReconstructedReviewV1]) -> dict[str, Any]:
    records = list(rows)
    choices = Counter(item.choice for item in records)
    score_names = (
        "overall_quality",
        "composition",
        "hierarchy",
        "typography",
        "brand_feeling",
        "overall",
    )
    values_by_score: dict[str, list[float]] = defaultdict(list)
    for item in records:
        for name in score_names:
            value = item.scores.get(name) if item.scores else None
            if value is not None:
                values_by_score[name].append(float(value))
    means = {name: mean(values) for name, values in values_by_score.items()}
    medians = {name: median(values) for name, values in values_by_score.items()}
    quality_values = values_by_score.get("overall_quality") or values_by_score.get(
        "overall", []
    )
    return {
        "review_count": len(records),
        "a_wins": choices["a"],
        "b_wins": choices["b"],
        "ties": choices["tie"],
        "both_bad": choices["both_bad"],
        "both_bad_rate": choices["both_bad"] / len(records) if records else 0.0,
        "rating_record_count": sum(item.scores is not None for item in records),
        "mean_overall_quality": mean(quality_values) if quality_values else None,
        "median_overall_quality": median(quality_values) if quality_values else None,
        "score_means": means,
        "score_medians": medians,
        "notes_available": sum(bool(item.notes) for item in records),
    }


def _grouped(
    rows: list[ReconstructedReviewV1],
    key_name: str,
) -> list[dict[str, Any]]:
    groups: dict[str, list[ReconstructedReviewV1]] = defaultdict(list)
    for item in rows:
        groups[str(getattr(item, key_name))].append(item)
    return [
        {key_name: key, **_aggregate(group)}
        for key, group in sorted(groups.items())
    ]


def category_failure_ranking(
    rows: list[ReconstructedReviewV1],
    *,
    generation_version: str | None = None,
    minimum_sample: int = 3,
) -> list[dict[str, Any]]:
    selected = [
        item
        for item in rows
        if generation_version is None or item.generation_version == generation_version
    ]
    groups: dict[str, list[ReconstructedReviewV1]] = defaultdict(list)
    for item in selected:
        groups[item.normalized_category].append(item)
    ranking = []
    for category, group in groups.items():
        metrics = _aggregate(group)
        ranking.append(
            {
                "category": category,
                **metrics,
                "generation_version": generation_version or "mixed",
                "eligible_for_ranking": len(group) >= minimum_sample,
                "sample_note": (
                    "eligible" if len(group) >= minimum_sample else "LOW_CONFIDENCE"
                ),
                "raw_categories": sorted({item.category for item in group}),
            }
        )
    return sorted(
        ranking,
        key=lambda item: (
            not bool(item["eligible_for_ranking"]),
            -float(item["both_bad_rate"]),
            (
                float(item["mean_overall_quality"])
                if item["mean_overall_quality"] is not None
                else 999.0
            ),
            -int(item["review_count"]),
            str(item["category"]),
        ),
    )


def select_weak_categories(
    ranking: list[dict[str, Any]],
    *,
    count: int = 3,
) -> list[dict[str, Any]]:
    eligible = [item for item in ranking if item["eligible_for_ranking"]]
    if len(eligible) < count:
        raise ValueError("insufficient eligible categories for targeted hardening")
    return [
        {
            "category": item["category"],
            "review_count": item["review_count"],
            "both_bad": item["both_bad"],
            "both_bad_rate": item["both_bad_rate"],
            "mean_overall_quality": item["mean_overall_quality"],
            "generation_version": item["generation_version"],
            "selection_basis": "human_both_bad_rate_with_minimum_sample",
        }
        for item in eligible[:count]
    ]


def build_review_analytics(
    rows: list[ReconstructedReviewV1],
    *,
    pilot_generation: str = "candidate_generation_v2_pilot",
) -> dict[str, Any]:
    overall_ranking = category_failure_ranking(rows)
    pilot_ranking = category_failure_ranking(
        rows, generation_version=pilot_generation
    )
    selected = select_weak_categories(pilot_ranking)
    old_rows = [item for item in rows if item.generation_version == "diagnostic_generation_v1"]
    pilot_rows = [item for item in rows if item.generation_version == pilot_generation]
    common_categories = sorted(
        {item.normalized_category for item in old_rows}
        & {item.normalized_category for item in pilot_rows}
    )
    category_comparison = []
    for category in common_categories:
        old = [item for item in old_rows if item.normalized_category == category]
        new = [item for item in pilot_rows if item.normalized_category == category]
        old_metrics = _aggregate(old)
        new_metrics = _aggregate(new)
        category_comparison.append(
            {
                "category": category,
                "old": old_metrics,
                "new_pilot": new_metrics,
                "both_bad_rate_change_percentage_points": 100.0
                * (new_metrics["both_bad_rate"] - old_metrics["both_bad_rate"]),
                "sample_note": (
                    "INSUFFICIENT_SAMPLE"
                    if min(len(old), len(new)) < 3
                    else "descriptive_only_not_randomized"
                ),
            }
        )
    exact_provenance = sum(
        item.provenance_status in {"queue_hash", "queue_hash_and_record"}
        for item in rows
    )
    return {
        "schema_version": "1.0",
        "analytics_type": "human_review_failure_diagnostic_not_training_labels",
        "overall": _aggregate(rows),
        "by_queue": _grouped(rows, "queue_id"),
        "by_generation_version": _grouped(rows, "generation_version"),
        "by_category_raw": _grouped(rows, "category"),
        "by_category_normalized": _grouped(rows, "normalized_category"),
        "by_reviewer": _grouped(rows, "reviewer"),
        "category_alias_normalization": CATEGORY_ALIAS_MAP,
        "provenance": {
            "exact_queue_hash_count": exact_provenance,
            "unknown_or_conflict_count": len(rows) - exact_provenance,
            "rows": [item.model_dump(mode="json") for item in rows],
        },
        "category_failure_ranking": overall_ranking,
        "pilot_category_failure_ranking": pilot_ranking,
        "selected_categories": selected,
        "old_vs_phase1_1": {
            "old": _aggregate(old_rows),
            "new_pilot": _aggregate(pilot_rows),
            "overall_both_bad_rate_change_percentage_points": 100.0
            * (_aggregate(pilot_rows)["both_bad_rate"] - _aggregate(old_rows)["both_bad_rate"]),
            "category_matched": category_comparison,
            "quality_comparison": "INSUFFICIENT_SAMPLE"
            if not any(item.scores for item in rows)
            else "AVAILABLE",
            "causal_improvement_claimed": False,
        },
        "automated_preference_labels": 0,
        "both_bad_exported_as_preference": False,
    }


def write_analytics_artifacts(
    analytics: dict[str, Any],
    output: Path,
) -> dict[str, Path]:
    destination = output.resolve()
    paths = {
        "json": destination / "review_analytics.json",
        "markdown": destination / "review_analytics.md",
        "ranking": destination / "category_failure_ranking.json",
        "selected": destination / "selected_categories.json",
    }
    if any(path.exists() for path in paths.values()):
        raise FileExistsError("refusing to overwrite Phase 1.2 analytics")
    destination.mkdir(parents=True, exist_ok=True)
    paths["json"].write_text(
        json.dumps(analytics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths["ranking"].write_text(
        json.dumps(
            {
                "all_reviews": analytics["category_failure_ranking"],
                "phase1_1_pilot": analytics["pilot_category_failure_ranking"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    paths["selected"].write_text(
        json.dumps(
            {
                "selection_generation": "candidate_generation_v2_pilot",
                "minimum_sample": 3,
                "categories": analytics["selected_categories"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Human review failure analytics",
        "",
        "This report is diagnostic. It does not create preference labels.",
        "",
        "## Overall",
        "",
        f"- Reviews: {analytics['overall']['review_count']}",
        f"- Both bad: {analytics['overall']['both_bad']} ({analytics['overall']['both_bad_rate']:.1%})",
        f"- A/B/tie: {analytics['overall']['a_wins']}/{analytics['overall']['b_wins']}/{analytics['overall']['ties']}",
        "",
        "## Generation provenance",
        "",
    ]
    for row in analytics["by_generation_version"]:
        lines.append(
            f"- {row['generation_version']}: n={row['review_count']}, both_bad={row['both_bad_rate']:.1%}"
        )
    lines.extend(["", "## Phase 1.1 category ranking", ""])
    for row in analytics["pilot_category_failure_ranking"]:
        lines.append(
            f"- {row['category']}: n={row['review_count']}, both_bad={row['both_bad_rate']:.1%}, {row['sample_note']}"
        )
    lines.extend(["", "## Selected for Phase 1.2", ""])
    for row in analytics["selected_categories"]:
        lines.append(
            f"- {row['category']}: {row['both_bad']}/{row['review_count']} both bad ({row['both_bad_rate']:.1%})"
        )
    lines.extend(
        [
            "",
            "No optional quality ratings were present in this snapshot; mean quality is not invented.",
            "",
        ]
    )
    paths["markdown"].write_text("\n".join(lines), encoding="utf-8")
    return paths


def snapshot_digest(path: Path) -> str:
    return hashlib.sha256(path.resolve().read_bytes()).hexdigest()


__all__ = [
    "CATEGORY_ALIAS_MAP",
    "QueueIdentityV1",
    "ReconstructedReviewV1",
    "build_review_analytics",
    "category_failure_ranking",
    "load_sessions",
    "normalize_category",
    "queue_identity",
    "reconstruct_review_provenance",
    "select_weak_categories",
    "snapshot_digest",
    "write_analytics_artifacts",
]
