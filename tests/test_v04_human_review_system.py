from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from training.inference.baseline import generate_baseline_design
from training.inference.corel_compiler import compile_corel_operations
from training.preference.v04.exporter import export_preferences, split_by_brief
from training.preference.v04.models import HumanReviewV1, ReviewSubmissionV1
from training.preference.v04.pairing import (
    candidate_from_directory,
    canonical_pair_id,
    tournament_pairs,
    write_queue,
)
from training.preference.v04.review_app import create_review_app
from training.preference.v04.store import ReviewStore


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _candidate(root: Path, index: int, *, brief_id: str = "spa_01"):
    directory = root / f"candidate_{index:02d}"
    directory.mkdir(parents=True)
    document = generate_baseline_design(f"Spa premium variant {index}", 210, 297)
    document.sample_id = f"human-review:{brief_id}:{index}"
    document.metadata["controlled_seed"] = 100 + index
    # Preserve validity while ensuring each structured artifact differs.
    document.elements[1].visual.opacity = 0.80 + index * 0.03
    (directory / "design.json").write_text(document.model_dump_json(), encoding="utf-8")
    Image.new("RGB", (120 + index, 180), f"#{20 + index:02x}3344").save(directory / "preview.png")
    operations = compile_corel_operations(document, width_mm=210, height_mm=297)
    _write_json(directory / "corel_operations.json", operations)
    _write_json(directory / "validation.json", {"strict_schema_valid": True})
    _write_json(directory / "metrics.json", {
        "outside_canvas_rate": 0.0, "overlap_ratio": 0.0,
        "text_fit_rate": 1.0, "text_overflow_count": 0,
    })
    _write_json(directory / "generation.json", {"seed": 100 + index, "source": "fixture"})
    return candidate_from_directory(
        candidate_dir=directory,
        brief_id=brief_id,
        design_id=f"design:{brief_id}:{index}",
        generation_source="test_fixture_not_model",
        provenance={"automated_preference": False},
        license_class="research_only",
        commercial_allowed=False,
    )


def _store(tmp_path: Path) -> ReviewStore:
    artifacts = tmp_path / "artifacts"
    candidates = [_candidate(artifacts, index) for index in range(1, 5)]
    items = tournament_pairs(
        brief_id="spa_01", prompt="Thiết kế poster spa premium", category="spa",
        candidates=candidates, benchmark_sample_data=True, customer_provided=False,
        provenance={
            "source": "unit_test",
            "generation_version": "candidate_generation_v2_pilot",
            "quality_floor_passed": True,
        },
    )
    queue = write_queue(items, artifacts / "queue.jsonl")
    return ReviewStore(
        data_root=tmp_path / "human_preferences", queue_path=queue,
        approved_roots=[artifacts],
    )


def test_pair_identity_canonicalizes_ab_order_and_queue_has_four_pairs(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert len(store.queue) == 4
    first = store.queue[0]
    assert canonical_pair_id(first.brief_id, first.candidate_1.content_sha256, first.candidate_2.content_sha256) == canonical_pair_id(
        first.brief_id, first.candidate_2.content_sha256, first.candidate_1.content_sha256
    )


def test_session_blinding_is_persisted_and_resume_is_stable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.create_or_resume_session("Designer_01")
    resumed = store.create_or_resume_session("Designer_01")
    assert resumed.session_id == first.session_id
    assert resumed.ordered_pair_ids == first.ordered_pair_ids
    assert resumed.blind_mappings == first.blind_mappings
    public = store.public_item(first, store.next_item(first))
    assert "v0.3" not in json.dumps(public)
    assert "score" not in json.dumps(public).casefold()


def test_completed_reviewer_does_not_receive_duplicate_session(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create_or_resume_session("Designer_01")
    for pair_id in session.ordered_pair_ids:
        store.submit(session=session, pair_id=pair_id, submission=ReviewSubmissionV1(choice="tie"))
    resumed = store.create_or_resume_session("Designer_01")
    assert resumed.session_id == session.session_id
    assert store.next_item(resumed) is None


def test_human_only_schema_rejects_automatic_or_unverified_records(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create_or_resume_session("Long")
    item = store.next_item(session)
    review = store.submit(
        session=session, pair_id=item.pair_id,
        submission=ReviewSubmissionV1(choice="a"),
    )
    assert review.provenance["generation_version"] == "candidate_generation_v2_pilot"
    assert review.provenance["quality_floor_passed"] is True
    payload = review.model_dump()
    payload["source"] = "heuristic"
    with pytest.raises(ValidationError):
        HumanReviewV1.model_validate(payload)
    payload = review.model_dump()
    payload["human_verified"] = False
    with pytest.raises(ValidationError):
        HumanReviewV1.model_validate(payload)
    payload = review.model_dump()
    payload["provenance"]["selection_source"] = "vision_critic"
    with pytest.raises(ValidationError, match="human UI"):
        HumanReviewV1.model_validate(payload)


def test_api_submit_skip_progress_back_and_resume(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client = TestClient(create_review_app(store))
    created = client.post("/api/v1/review/session", json={"reviewer_name": "Long"})
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    first = client.get("/api/v1/review/next", params={"session_id": session_id}).json()["item"]
    assert client.get(first["preview_a"]).status_code == 200
    saved = client.post("/api/v1/review/submit", json={
        "session_id": session_id, "pair_id": first["pair_id"],
        "review": {"choice": "tie", "scores": {"overall_quality": 7}, "notes": "Cân bằng", "confidence": 4},
    })
    assert saved.status_code == 200
    second = client.get("/api/v1/review/next", params={"session_id": session_id}).json()["item"]
    skipped = client.post("/api/v1/review/skip", json={"session_id": session_id, "pair_id": second["pair_id"]})
    assert skipped.status_code == 200
    progress = client.get("/api/v1/review/progress", params={"session_id": session_id}).json()
    assert progress["completed"] == 1
    assert progress["skipped"] == 1
    assert client.get("/api/v1/review/previous", params={"session_id": session_id}).json()["item"]["pair_id"] == first["pair_id"]
    assert client.post("/api/v1/review/session", json={"reviewer_name": "Long"}).json()["session_id"] == session_id


def test_review_preview_cannot_escape_approved_artifact_root(tmp_path: Path) -> None:
    store = _store(tmp_path)
    outside = tmp_path / "private.png"
    Image.new("RGB", (10, 10)).save(outside)
    queue_payload = [item.model_dump(mode="json") for item in store.queue]
    queue_payload[0]["candidate_1"]["preview_path"] = str(outside)
    unsafe_queue = tmp_path / "artifacts" / "unsafe.jsonl"
    unsafe_queue.write_text("".join(json.dumps(item) + "\n" for item in queue_payload), encoding="utf-8")
    with pytest.raises(PermissionError, match="outside approved"):
        ReviewStore(data_root=tmp_path / "data2", queue_path=unsafe_queue, approved_roots=[tmp_path / "artifacts"])


def test_api_rejects_path_traversal_identifiers(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client = TestClient(create_review_app(store))
    response = client.get("/api/v1/review/preview/session:../../secret/pair:../../secret/a")
    assert response.status_code == 404


def test_tie_and_both_bad_are_retained_without_fabricating_winner(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create_or_resume_session("Reviewer")
    choices = ["a", "b", "tie", "both_bad"]
    for pair_id, choice in zip(session.ordered_pair_ids, choices):
        store.submit(session=session, pair_id=pair_id, submission=ReviewSubmissionV1(choice=choice))
    summary = export_preferences(store, tmp_path / "exports")
    assert summary["human_review_count"] == 4
    assert summary["valid_non_tie_preference_pairs"] == 2
    assert summary["ties"] == 1
    assert summary["both_bad"] == 1
    assert summary["ready_for_preference_training"] is False
    assert len((tmp_path / "exports" / "preference_pairs.jsonl").read_text().splitlines()) == 2


def test_export_rejects_tampered_automatic_review(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create_or_resume_session("Reviewer")
    item = store.next_item(session)
    review = store.submit(session=session, pair_id=item.pair_id, submission=ReviewSubmissionV1(choice="a"))
    review_path = store.reviews_dir / session.session_id.removeprefix("session:") / f"{item.pair_id.removeprefix('pair:')}.json"
    payload = review.model_dump(mode="json")
    payload["source"] = "automatic"
    review_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid human reviews"):
        export_preferences(store, tmp_path / "exports")
    report = json.loads((tmp_path / "exports" / "review_validation_report.json").read_text())
    assert report["valid"] is False


def test_additional_briefs_mark_fictional_content_provenance() -> None:
    config = json.loads(Path("training/config/preference/v0_4_phase1_additional_briefs.json").read_text(encoding="utf-8"))
    assert config["benchmark_sample_data"] is True
    assert config["customer_provided"] is False
    assert len(config["briefs"]) == 7


def test_split_is_by_brief_and_never_leaks() -> None:
    from training.preference.v04.models import PreferencePairV1
    # Construct bypassed fixtures solely to exercise grouping; each brief has two pairs.
    pairs = []
    for brief in range(24):
        for pair_index in range(2):
            pairs.append(PreferencePairV1.model_construct(brief_id=f"brief_{brief}", category=f"cat_{brief % 8}"))
    split = split_by_brief(pairs, seed=404)
    groups = [set(split.train_brief_ids), set(split.validation_brief_ids), set(split.test_brief_ids)]
    assert not groups[0] & groups[1]
    assert not groups[0] & groups[2]
    assert not groups[1] & groups[2]
    assert set.union(*groups) == {f"brief_{index}" for index in range(24)}


def test_broken_candidate_is_filtered_before_human_queue(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    candidate = _candidate(artifacts, 1)
    directory = Path(candidate.design_path).parent
    _write_json(directory / "metrics.json", {
        "outside_canvas_rate": 0.2, "overlap_ratio": 0,
        "text_fit_rate": 1, "text_overflow_count": 0,
    })
    with pytest.raises(ValueError, match="outside-canvas"):
        candidate_from_directory(
            candidate_dir=directory, brief_id="spa_01", design_id="design:bad",
            generation_source="fixture", provenance={}, license_class="research_only",
            commercial_allowed=False,
        )
