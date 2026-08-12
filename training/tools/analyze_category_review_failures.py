"""Reconstruct mixed review provenance and select Phase 1.2 weak categories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.preference.v04.models import HumanReviewV1, ReviewSessionV1
from training.preference.v04.review_analytics import (
    build_review_analytics,
    queue_identity,
    reconstruct_review_provenance,
    snapshot_digest,
    write_analytics_artifacts,
)


def _read(path: Path):
    return json.loads(path.resolve().read_text(encoding="utf-8"))


def _load_snapshot(snapshot: Path) -> tuple[list[HumanReviewV1], list[ReviewSessionV1]]:
    manifest = _read(snapshot / "snapshot_manifest.json")
    reviews_path = snapshot / "reviews.jsonl"
    sessions_path = snapshot / "sessions.json"
    if snapshot_digest(reviews_path) != manifest["files"]["reviews.jsonl"]["sha256"]:
        raise ValueError("review snapshot hash mismatch")
    if snapshot_digest(sessions_path) != manifest["files"]["sessions.json"]["sha256"]:
        raise ValueError("session snapshot hash mismatch")
    reviews = [
        HumanReviewV1.model_validate_json(line)
        for line in reviews_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    sessions = [
        ReviewSessionV1.model_validate_json(json.dumps(item))
        for item in _read(sessions_path)
    ]
    if len(reviews) != int(manifest["review_file_count"]):
        raise ValueError("review snapshot count mismatch")
    if len(sessions) != int(manifest["session_file_count"]):
        raise ValueError("session snapshot count mismatch")
    return reviews, sessions


def analyze(args: argparse.Namespace) -> dict:
    output = args.output.resolve()
    reviews, sessions = _load_snapshot(output / "review_snapshot")
    queue_catalog = [
        queue_identity(
            args.old_queue,
            queue_id="v0_4_phase1_initial_pool",
            generation_version="diagnostic_generation_v1",
        ),
        queue_identity(
            args.phase1_1_queue,
            queue_id="v04_phase1_1_pilot",
            generation_version="candidate_generation_v2_pilot",
        ),
    ]
    rows = reconstruct_review_provenance(reviews, sessions, queue_catalog)
    analytics = build_review_analytics(rows)
    analytics["queue_catalog"] = [item.model_dump(mode="json") for item in queue_catalog]
    old_audit = _read(args.old_pool_audit)
    pilot_quality = _read(args.phase1_1_quality)
    pilot_diversity = _read(args.phase1_1_diversity)
    analytics["candidate_pool_measurements"] = {
        "old": {
            key: old_audit.get(key)
            for key in (
                "candidate_count",
                "content_consistency_rate",
                "asset_consistency_rate",
                "business_value_consistency_rate",
                "canvas_consistency_rate",
                "mean_pairwise_candidate_diversity",
                "minimum_pairwise_candidate_diversity",
                "placeholder_count",
                "mean_placeholder_area_ratio",
                "technical_pass_rate",
            )
        },
        "phase1_1_pilot": {
            "candidate_count": pilot_quality.get("candidate_count"),
            "content_consistency_rate": pilot_quality.get("content_consistency_rate"),
            "asset_consistency_rate": pilot_quality.get("asset_consistency_rate"),
            "business_value_consistency_rate": pilot_quality.get("business_value_consistency_rate"),
            "canvas_consistency_rate": pilot_quality.get("canvas_consistency_rate"),
            "mean_pairwise_candidate_diversity": pilot_diversity.get("mean_pairwise_candidate_diversity"),
            "minimum_pairwise_candidate_diversity": pilot_diversity.get("minimum_pairwise_candidate_diversity"),
            "placeholder_count": pilot_quality.get("placeholder_count"),
            "mean_placeholder_area_ratio": pilot_quality.get("mean_placeholder_area_ratio"),
            "technical_pass_rate": (
                pilot_quality.get("technical_pass_count", 0)
                / max(pilot_quality.get("candidate_count", 0), 1)
            ),
        },
        "comparison_note": "descriptive_only; pool category composition differs",
    }
    paths = write_analytics_artifacts(analytics, output)
    return {
        "review_count": analytics["overall"]["review_count"],
        "provenance_exact": analytics["provenance"]["exact_queue_hash_count"],
        "selected_categories": [
            item["category"] for item in analytics["selected_categories"]
        ],
        "paths": {key: str(path) for key, path in paths.items()},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("training/artifacts/preference/v0_4_phase1_2_category_hardening"),
    )
    parser.add_argument(
        "--old-queue",
        type=Path,
        default=Path("training/artifacts/preference/v0_4_initial_pool/review_queue/review_queue.jsonl"),
    )
    parser.add_argument(
        "--phase1-1-queue",
        type=Path,
        default=Path("training/artifacts/preference/v0_4_phase1_1_candidate_hardening/review_queue/review_queue.jsonl"),
    )
    parser.add_argument(
        "--old-pool-audit",
        type=Path,
        default=Path("training/artifacts/preference/v0_4_phase1_1_diagnostic/old_pool_quality_audit.json"),
    )
    parser.add_argument(
        "--phase1-1-quality",
        type=Path,
        default=Path("training/artifacts/preference/v0_4_phase1_1_candidate_hardening/pilot_quality_report.json"),
    )
    parser.add_argument(
        "--phase1-1-diversity",
        type=Path,
        default=Path("training/artifacts/preference/v0_4_phase1_1_candidate_hardening/pilot_diversity_report.json"),
    )
    return parser


def main() -> int:
    print(json.dumps(analyze(build_parser().parse_args()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
