"""Convert selection artifacts into explicit auto/human preference records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal


PreferenceType = Literal["auto_preference", "human_preference"]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_payload(run_dir: Path, candidate_id: str) -> dict:
    directory = run_dir / "candidates" / candidate_id
    score = _read_json(directory / "score.json")
    planner_path = directory / "planner.json"
    design_path = directory / "design.json"
    return {
        "candidate_id": candidate_id,
        "raw_output": (directory / "raw_output.txt").read_text(encoding="utf-8"),
        "planner": _read_json(planner_path) if planner_path.is_file() else None,
        "design": _read_json(design_path) if design_path.is_file() else None,
        "score": score,
    }


def build_preference_record(
    run_dir: Path,
    *,
    preference_type: PreferenceType = "auto_preference",
    chosen_candidate_id: str | None = None,
    rejected_candidate_id: str | None = None,
) -> dict:
    request = _read_json(run_dir / "request.json")
    ranking = _read_json(run_dir / "ranking.json")
    ranked_ids = [item["candidate_id"] for item in ranking["candidates"]]
    if not ranked_ids:
        raise ValueError("ranking contains no candidates")
    if len(ranked_ids) < 2:
        raise ValueError("preference export requires at least two candidates")
    if preference_type == "auto_preference":
        chosen_id = ranking.get("winner")
        human_approved = False
        rejected_id = next(
            candidate_id
            for candidate_id in reversed(ranked_ids)
            if candidate_id != chosen_id
        )
    else:
        if chosen_candidate_id is None:
            raise ValueError("human preference requires chosen_candidate_id")
        if rejected_candidate_id is None:
            raise ValueError("human preference requires rejected_candidate_id")
        if chosen_candidate_id not in ranked_ids:
            raise ValueError(f"unknown chosen candidate: {chosen_candidate_id}")
        if rejected_candidate_id not in ranked_ids:
            raise ValueError(f"unknown rejected candidate: {rejected_candidate_id}")
        if chosen_candidate_id == rejected_candidate_id:
            raise ValueError("chosen and rejected candidates must differ")
        chosen_id = chosen_candidate_id
        rejected_id = rejected_candidate_id
        human_approved = True
    if chosen_id is None:
        raise ValueError("cannot build preference from an all-invalid run")
    chosen = _candidate_payload(run_dir, chosen_id)
    rejected = _candidate_payload(run_dir, rejected_id)
    if preference_type == "human_preference" and (
        not chosen["score"]["eligible"] or chosen["design"] is None
    ):
        raise ValueError("human preference cannot choose an invalid candidate")
    return {
        "prompt": request["prompt"],
        "chosen": chosen,
        "rejected": rejected,
        "metadata": {
            "preference_type": preference_type,
            "preference_schema_version": "0.2",
            "human_approved": human_approved,
            "scoring_source": ranking["scoring_source"],
            "generation_model": request["model"],
            "checkpoint": request["model"].get("adapter_checkpoint"),
            "license_class": request["license_class"],
            "commercial_allowed": request["commercial_allowed"],
            "source_run": str(run_dir.resolve()),
        },
    }


def export_preference(
    run_dir: Path,
    output_path: Path,
    *,
    preference_type: PreferenceType = "auto_preference",
    chosen_candidate_id: str | None = None,
    rejected_candidate_id: str | None = None,
) -> Path:
    record = build_preference_record(
        run_dir,
        preference_type=preference_type,
        chosen_candidate_id=chosen_candidate_id,
        rejected_candidate_id=rejected_candidate_id,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path.resolve()
