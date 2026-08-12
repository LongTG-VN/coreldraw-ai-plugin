"""Technical candidate admission and deterministic tournament pairing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from training.inference.corel_compiler import compile_corel_operations
from training.schemas.design import DesignDocument
from training.preference.v04.models import CandidateArtifactV1, ReviewQueueItemV1


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_pair_id(brief_id: str, left_hash: str, right_hash: str) -> str:
    identity = "|".join((brief_id, *sorted((left_hash, right_hash))))
    return "pair:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def candidate_from_directory(
    *,
    candidate_dir: Path,
    brief_id: str,
    design_id: str,
    generation_source: str,
    provenance: dict[str, Any],
    license_class: str,
    commercial_allowed: bool,
) -> CandidateArtifactV1:
    """Admit a candidate only after strict, non-aesthetic technical checks."""

    root = candidate_dir.resolve()
    required = {
        "design": root / "design.json",
        "preview": root / "preview.png",
        "operations": root / "corel_operations.json",
        "validation": root / "validation.json",
        "metrics": root / "metrics.json",
        "generation": root / "generation.json",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise ValueError(f"candidate is missing required artifacts: {missing}")
    validation = json.loads(required["validation"].read_text(encoding="utf-8"))
    metrics = json.loads(required["metrics"].read_text(encoding="utf-8"))
    if validation.get("strict_schema_valid") is not True:
        raise ValueError("candidate failed strict schema validation")
    if float(metrics.get("outside_canvas_rate", 1)) > 0:
        raise ValueError("candidate has outside-canvas elements")
    if float(metrics.get("overlap_ratio", 1)) > 0.10:
        raise ValueError("candidate has severe overlap")
    if float(metrics.get("text_fit_rate", 0)) < 0.95:
        raise ValueError("candidate has unresolved text fitting")
    if int(metrics.get("text_overflow_count", 0)) > 0:
        raise ValueError("candidate has unresolved text overflow")
    document = DesignDocument.model_validate_json(required["design"].read_text(encoding="utf-8"))
    compile_corel_operations(
        document,
        width_mm=float(document.canvas.width),
        height_mm=float(document.canvas.height),
    )
    operations = json.loads(required["operations"].read_text(encoding="utf-8"))
    if not isinstance(operations, list) or not operations:
        raise ValueError("candidate has no Corel operations")
    return CandidateArtifactV1(
        design_id=design_id,
        brief_id=brief_id,
        design_path=str(required["design"]),
        preview_path=str(required["preview"]),
        content_sha256=sha256_file(required["design"]),
        generation_source=generation_source,
        technically_eligible=True,
        provenance={**provenance, "technical_filter": "v0.4_phase1_strict"},
        license_class=license_class,
        commercial_allowed=commercial_allowed,
    )


def candidate_from_explicit_artifacts(
    *,
    design_path: Path,
    preview_path: Path,
    brief_id: str,
    design_id: str,
    generation_source: str,
    provenance: dict[str, Any],
    license_class: str,
    commercial_allowed: bool,
) -> CandidateArtifactV1:
    """Validate historical artifacts without inventing missing generation metadata."""

    design = design_path.resolve()
    preview = preview_path.resolve()
    if not design.is_file() or not preview.is_file():
        raise FileNotFoundError("historical design or preview is missing")
    document = DesignDocument.model_validate_json(design.read_text(encoding="utf-8"))
    compile_corel_operations(
        document,
        width_mm=float(document.canvas.width),
        height_mm=float(document.canvas.height),
    )
    return CandidateArtifactV1(
        design_id=design_id,
        brief_id=brief_id,
        design_path=str(design),
        preview_path=str(preview),
        content_sha256=sha256_file(design),
        generation_source=generation_source,
        technically_eligible=True,
        provenance={
            **provenance,
            "historical_import": True,
            "missing_generation_fields_invented": False,
            "technical_filter": "schema_plus_corel_compile",
        },
        license_class=license_class,
        commercial_allowed=commercial_allowed,
    )


def tournament_pairs(
    *,
    brief_id: str,
    prompt: str,
    category: str,
    candidates: list[CandidateArtifactV1],
    benchmark_sample_data: bool,
    customer_provided: bool,
    provenance: dict[str, Any],
) -> list[ReviewQueueItemV1]:
    if len(candidates) != 4:
        raise ValueError("deterministic Phase 1 tournament requires exactly four candidates")
    if len({item.content_sha256 for item in candidates}) != 4:
        raise ValueError("all four candidates must be meaningfully distinct artifacts")
    # Two opening comparisons plus two cross comparisons. This is intentionally
    # fixed; later active learning can replace it without changing review data.
    schedule = ((0, 1, "opening"), (2, 3, "opening"), (0, 2, "cross"), (1, 3, "cross"))
    pairs = []
    for left_index, right_index, stage in schedule:
        left, right = candidates[left_index], candidates[right_index]
        pair_commercial = left.commercial_allowed and right.commercial_allowed
        license_class = (
            left.license_class
            if left.license_class == right.license_class
            else "mixed_research_only"
        )
        pairs.append(
            ReviewQueueItemV1(
                pair_id=canonical_pair_id(brief_id, left.content_sha256, right.content_sha256),
                brief_id=brief_id,
                prompt=prompt,
                category=category,
                candidate_1=left,
                candidate_2=right,
                pairing_stage=stage,
                benchmark_sample_data=benchmark_sample_data,
                customer_provided=customer_provided,
                provenance={**provenance, "pairing": "deterministic_tournament_v1"},
                license_class=license_class,
                commercial_allowed=pair_commercial,
            )
        )
    return pairs


def write_queue(items: Iterable[ReviewQueueItemV1], output: Path) -> Path:
    records = list(items)
    pair_ids = [item.pair_id for item in records]
    if len(set(pair_ids)) != len(pair_ids):
        raise ValueError("review queue contains duplicate underlying pairs")
    destination = output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite review queue: {destination}")
    destination.write_text(
        "".join(item.model_dump_json() + "\n" for item in records),
        encoding="utf-8",
    )
    return destination


def load_queue(path: Path) -> list[ReviewQueueItemV1]:
    records = [
        ReviewQueueItemV1.model_validate_json(line)
        for line in path.resolve().read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len({item.pair_id for item in records}) != len(records):
        raise ValueError("review queue contains duplicate pairs")
    return records
