"""Validate explicit UI reviews and export chosen/rejected training records."""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from training.preference.v04.models import (
    HumanReviewV1,
    PreferencePairV1,
    PreferenceSplitV1,
)
from training.preference.v04.store import ReviewStore, resolve_approved_file


def _review_paths(root: Path) -> list[Path]:
    return sorted(root.resolve().rglob("*.json")) if root.exists() else []


def validate_human_reviews(store: ReviewStore) -> tuple[list[HumanReviewV1], dict[str, Any]]:
    reviews: list[HumanReviewV1] = []
    errors: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    duplicate_count = 0
    for path in _review_paths(store.reviews_dir):
        try:
            review = HumanReviewV1.model_validate_json(path.read_text(encoding="utf-8"))
            if review.pair_id not in store.by_pair:
                raise ValueError("review pair is absent from queue")
            item = store.by_pair[review.pair_id]
            expected = {item.candidate_1.design_id, item.candidate_2.design_id}
            if {review.design_a_id, review.design_b_id} != expected:
                raise ValueError("review blind mapping does not match candidate identities")
            for candidate in (item.candidate_1, item.candidate_2):
                resolve_approved_file(candidate.preview_path, store.approved_roots)
                resolve_approved_file(candidate.design_path, store.approved_roots)
            identity = (review.reviewer.casefold(), review.pair_id)
            if identity in seen:
                duplicate_count += 1
                raise ValueError("same reviewer reviewed the same underlying pair twice")
            seen.add(identity)
            reviews.append(review)
        except Exception as exc:
            errors.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
    report = {
        "schema_version": "1.0",
        "human_review_count": len(reviews),
        "invalid_review_count": len(errors),
        "duplicate_pair_count": duplicate_count,
        "valid": not errors,
        "errors": errors,
    }
    return reviews, report


def _candidate(item, design_id: str):
    if item.candidate_1.design_id == design_id:
        return item.candidate_1
    if item.candidate_2.design_id == design_id:
        return item.candidate_2
    raise ValueError("design is not part of pair")


def preference_from_review(review: HumanReviewV1, store: ReviewStore) -> PreferencePairV1 | None:
    if review.source != "human" or review.human_verified is not True:
        raise ValueError("only explicitly verified human reviews can be exported")
    if review.choice not in {"a", "b"}:
        return None
    item = store.by_pair[review.pair_id]
    chosen_id = review.design_a_id if review.choice == "a" else review.design_b_id
    rejected_id = review.design_b_id if review.choice == "a" else review.design_a_id
    chosen = _candidate(item, chosen_id)
    rejected = _candidate(item, rejected_id)
    identity = f"{review.review_id}|{chosen_id}|{rejected_id}"
    return PreferencePairV1(
        pair_id="preference:" + hashlib.sha256(identity.encode()).hexdigest()[:24],
        review_id=review.review_id,
        brief_id=review.brief_id,
        prompt=review.prompt,
        category=review.category,
        chosen_design_id=chosen_id,
        rejected_design_id=rejected_id,
        chosen_design_path=chosen.design_path,
        rejected_design_path=rejected.design_path,
        chosen_preview=chosen.preview_path,
        rejected_preview=rejected.preview_path,
        scores=review.scores,
        notes=review.notes,
        confidence=review.confidence,
        reviewer=review.reviewer,
        created_at=review.created_at,
        source="human",
        human_verified=True,
        provenance={
            "source_review": review.review_id,
            "selection_source": "human_ui_action",
            "automated_label": False,
        },
        license_class=item.license_class,
        commercial_allowed=item.commercial_allowed,
    )


def split_by_brief(
    pairs: Iterable[PreferencePairV1], *, seed: int = 404, ratios: tuple[float, float, float] = (.70, .15, .15)
) -> PreferenceSplitV1:
    if abs(sum(ratios) - 1) > 1e-9:
        raise ValueError("split ratios must total 1")
    categories: dict[str, list[str]] = defaultdict(list)
    seen: set[str] = set()
    for pair in pairs:
        if pair.brief_id not in seen:
            categories[pair.category].append(pair.brief_id)
            seen.add(pair.brief_id)
    rng = random.Random(seed)
    train: list[str] = []
    validation: list[str] = []
    test: list[str] = []
    for category in sorted(categories):
        ids = sorted(categories[category])
        rng.shuffle(ids)
        for index, brief_id in enumerate(ids):
            bucket = (index + (seed % 7)) % 20
            (train if bucket < 14 else validation if bucket < 17 else test).append(brief_id)
    return PreferenceSplitV1(
        train_brief_ids=sorted(train),
        validation_brief_ids=sorted(validation),
        test_brief_ids=sorted(test),
        seed=seed,
    )


def export_preferences(store: ReviewStore, output_dir: Path) -> dict[str, Any]:
    destination = output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    reviews, validation = validate_human_reviews(store)
    (destination / "review_validation_report.json").write_text(
        json.dumps(validation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if not validation["valid"]:
        raise ValueError("invalid human reviews; inspect review_validation_report.json")
    pairs = [pair for review in reviews if (pair := preference_from_review(review, store)) is not None]
    (destination / "preference_pairs.jsonl").write_text(
        "".join(pair.model_dump_json() + "\n" for pair in pairs), encoding="utf-8"
    )
    choices = Counter(review.choice for review in reviews)
    score_values: dict[str, list[int]] = defaultdict(list)
    for review in reviews:
        if review.scores:
            for key, value in review.scores.model_dump().items():
                if value is not None:
                    score_values[key].append(value)
    split = split_by_brief(pairs)
    (destination / "brief_split.json").write_text(split.model_dump_json(indent=2) + "\n", encoding="utf-8")
    summary = {
        "schema_version": "1.0",
        "human_review_count": len(reviews),
        "valid_non_tie_preference_pairs": len(pairs),
        "unique_briefs": len({item.brief_id for item in reviews}),
        "unique_candidates": len({design for item in reviews for design in (item.design_a_id, item.design_b_id)}),
        "a_wins": choices["a"],
        "b_wins": choices["b"],
        "ties": choices["tie"],
        "both_bad": choices["both_bad"],
        "category_distribution": dict(sorted(Counter(item.category for item in reviews).items())),
        "reviewer_distribution": dict(sorted(Counter(item.reviewer for item in reviews).items())),
        "mean_optional_scores": {key: mean(values) for key, values in sorted(score_values.items())},
        "pair_duplicate_count": validation["duplicate_pair_count"],
        "commercial_allowed_count": sum(item.commercial_allowed for item in reviews),
        "research_only_count": sum(not item.commercial_allowed for item in reviews),
        "minimum_training_gate": {
            "non_tie_pairs": 80,
            "unique_briefs": 20,
            "categories": 8,
        },
        "ready_for_preference_training": bool(
            len(pairs) >= 80
            and len({item.brief_id for item in pairs}) >= 20
            and len({item.category for item in pairs}) >= 8
        ),
        "ties_retained_but_not_exported": True,
        "both_bad_retained_without_fabricated_winner": True,
        "preference_model_trained": False,
    }
    (destination / "preference_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary
