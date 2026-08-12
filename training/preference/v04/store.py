"""Crash-safe local review sessions with persisted blind A/B mappings."""

from __future__ import annotations

import hashlib
import json
import random
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from training.preference.v04.models import (
    BlindMappingV1,
    HumanReviewV1,
    ReviewQueueItemV1,
    ReviewSessionV1,
    ReviewSubmissionV1,
)
from training.preference.v04.pairing import load_queue, sha256_file


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    data = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def resolve_approved_file(path: str | Path, roots: list[Path]) -> Path:
    candidate = Path(path).expanduser().resolve()
    approved = [root.expanduser().resolve() for root in roots]
    if not any(candidate == root or root in candidate.parents for root in approved):
        raise PermissionError("preview/design path is outside approved artifact roots")
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


class ReviewStore:
    def __init__(self, *, data_root: Path, queue_path: Path, approved_roots: list[Path]) -> None:
        self.data_root = data_root.resolve()
        self.queue_path = queue_path.resolve()
        self.approved_roots = [item.resolve() for item in approved_roots]
        self.queue = load_queue(self.queue_path)
        self.by_pair = {item.pair_id: item for item in self.queue}
        self.queue_sha256 = sha256_file(self.queue_path)
        for item in self.queue:
            resolve_approved_file(item.candidate_1.preview_path, self.approved_roots)
            resolve_approved_file(item.candidate_2.preview_path, self.approved_roots)
            resolve_approved_file(item.candidate_1.design_path, self.approved_roots)
            resolve_approved_file(item.candidate_2.design_path, self.approved_roots)

    @property
    def sessions_dir(self) -> Path:
        return self.data_root / "sessions"

    @property
    def reviews_dir(self) -> Path:
        return self.data_root / "reviews"

    def _session_path(self, session_id: str) -> Path:
        token = session_id.removeprefix("session:")
        if not session_id.startswith("session:") or re.fullmatch(r"[a-f0-9]{24}", token) is None:
            raise ValueError("invalid session id")
        return self.sessions_dir / f"{token}.json"

    def _review_path(self, session_id: str, pair_id: str) -> Path:
        token = session_id.removeprefix("session:")
        pair = pair_id.removeprefix("pair:")
        if re.fullmatch(r"[a-f0-9]{24}", token) is None or re.fullmatch(r"[a-f0-9]{24}", pair) is None:
            raise ValueError("invalid review identity")
        return self.reviews_dir / token / f"{pair}.json"

    def create_or_resume_session(self, reviewer: str) -> ReviewSessionV1:
        reviewer = reviewer.strip()
        for path in sorted(self.sessions_dir.glob("*.json"), reverse=True) if self.sessions_dir.exists() else []:
            session = ReviewSessionV1.model_validate_json(path.read_text(encoding="utf-8"))
            # Reuse completed sessions too: the same reviewer must not silently
            # receive the identical queue again under a new session identity.
            if session.reviewer == reviewer and session.queue_sha256 == self.queue_sha256:
                return session
        token = secrets.token_hex(12)
        session_id = f"session:{token}"
        seed = int(hashlib.sha256(f"{reviewer}|{self.queue_sha256}|{token}".encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        pair_ids = [item.pair_id for item in self.queue]
        rng.shuffle(pair_ids)
        mappings: dict[str, BlindMappingV1] = {}
        for pair_id in pair_ids:
            item = self.by_pair[pair_id]
            ids = [item.candidate_1.design_id, item.candidate_2.design_id]
            rng.shuffle(ids)
            mappings[pair_id] = BlindMappingV1(design_a_id=ids[0], design_b_id=ids[1])
        session = ReviewSessionV1(
            session_id=session_id,
            reviewer=reviewer,
            queue_sha256=self.queue_sha256,
            seed=seed,
            ordered_pair_ids=pair_ids,
            blind_mappings=mappings,
            started_at=utc_now(),
        )
        _atomic_json(self._session_path(session_id), session)
        return session

    def load_session(self, session_id: str) -> ReviewSessionV1:
        return ReviewSessionV1.model_validate_json(
            self._session_path(session_id).read_text(encoding="utf-8")
        )

    def _reviewed_ids(self, session: ReviewSessionV1) -> set[str]:
        directory = self.reviews_dir / session.session_id.removeprefix("session:")
        if not directory.exists():
            return set()
        return {
            HumanReviewV1.model_validate_json(path.read_text(encoding="utf-8")).pair_id
            for path in directory.glob("*.json")
        }

    def progress(self, session: ReviewSessionV1) -> dict[str, int | bool]:
        reviewed = self._reviewed_ids(session)
        completed = len(reviewed)
        skipped = len(set(session.skipped_pair_ids) - reviewed)
        total = len(session.ordered_pair_ids)
        return {
            "completed": completed,
            "skipped": skipped,
            "remaining": max(0, total - completed - skipped),
            "total": total,
            "done": completed + skipped >= total,
        }

    def next_item(self, session: ReviewSessionV1) -> ReviewQueueItemV1 | None:
        reviewed = self._reviewed_ids(session)
        excluded = reviewed | set(session.skipped_pair_ids)
        return next((self.by_pair[pair_id] for pair_id in session.ordered_pair_ids if pair_id not in excluded), None)

    def previous_item(self, session: ReviewSessionV1) -> ReviewQueueItemV1 | None:
        directory = self.reviews_dir / session.session_id.removeprefix("session:")
        paths = sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True) if directory.exists() else []
        if not paths:
            return None
        review = HumanReviewV1.model_validate_json(paths[0].read_text(encoding="utf-8"))
        return self.by_pair[review.pair_id]

    def public_item(self, session: ReviewSessionV1, item: ReviewQueueItemV1) -> dict[str, Any]:
        progress = self.progress(session)
        return {
            "pair_id": item.pair_id,
            "brief_id": item.brief_id,
            "brief": item.prompt,
            "category": item.category,
            "preview_a": f"/api/v1/review/preview/{session.session_id}/{item.pair_id}/a",
            "preview_b": f"/api/v1/review/preview/{session.session_id}/{item.pair_id}/b",
            "progress": progress,
        }

    def candidate_for_side(self, session: ReviewSessionV1, pair_id: str, side: str):
        if side not in {"a", "b"}:
            raise ValueError("side must be a or b")
        item = self.by_pair[pair_id]
        design_id = getattr(session.blind_mappings[pair_id], f"design_{side}_id")
        return item.candidate_1 if item.candidate_1.design_id == design_id else item.candidate_2

    def submit(self, *, session: ReviewSessionV1, pair_id: str, submission: ReviewSubmissionV1) -> HumanReviewV1:
        item = self.by_pair[pair_id]
        mapping = session.blind_mappings[pair_id]
        identity = f"{session.session_id}|{pair_id}|{session.reviewer}"
        review = HumanReviewV1(
            review_id="review:" + hashlib.sha256(identity.encode()).hexdigest()[:24],
            pair_id=pair_id,
            brief_id=item.brief_id,
            prompt=item.prompt,
            category=item.category,
            design_a_id=mapping.design_a_id,
            design_b_id=mapping.design_b_id,
            choice=submission.choice,
            scores=submission.scores,
            notes=submission.notes.strip() if submission.notes else None,
            confidence=submission.confidence,
            reviewer=session.reviewer,
            session_id=session.session_id,
            created_at=utc_now(),
            source="human",
            human_verified=True,
            provenance={
                "selection_source": "human_ui_action",
                "blind_assignment_persisted": True,
                "automated_score_used": False,
                "benchmark_sample_data": item.benchmark_sample_data,
                "customer_provided": item.customer_provided,
            },
            license_class=item.license_class,
            commercial_allowed=item.commercial_allowed,
        )
        _atomic_json(self._review_path(session.session_id, pair_id), review)
        if pair_id in session.skipped_pair_ids:
            session.skipped_pair_ids.remove(pair_id)
            _atomic_json(self._session_path(session.session_id), session)
        self._complete_if_done(session)
        return review

    def skip(self, session: ReviewSessionV1, pair_id: str) -> None:
        if pair_id not in self.by_pair:
            raise KeyError(pair_id)
        if pair_id not in session.skipped_pair_ids:
            session.skipped_pair_ids.append(pair_id)
        _atomic_json(self._session_path(session.session_id), session)
        self._complete_if_done(session)

    def _complete_if_done(self, session: ReviewSessionV1) -> None:
        if self.progress(session)["done"] and session.completed_at is None:
            session.completed_at = utc_now()
            _atomic_json(self._session_path(session.session_id), session)
