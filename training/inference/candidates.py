"""Best-of-N generation, evaluation, ranking, and artifact orchestration."""

from __future__ import annotations

import html
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from PIL import Image, ImageDraw, ImageFont, ImageOps
from pydantic import BaseModel, ConfigDict, Field

from training.evaluation.diversity import candidate_diversity
from training.evaluation.scoring import (
    AllCandidatesInvalidError,
    CombinedScore,
    DesignScorer,
    RankingResult,
    rank_candidate_scores,
)
from training.inference.corel_compiler import CorelCompileError, compile_corel_operations
from training.inference.preview import render_preview
from training.inference.qwen3_planner import (
    ModelOutputError,
    RawPlannerGeneration,
    extract_planner_payload,
    parse_design_output,
)
from training.schemas.design import DesignDocument


class CandidateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CandidateGenerationSettings(CandidateModel):
    num_candidates: int = Field(default=4, ge=1, le=8)
    base_seed: int = Field(default=42, ge=0, le=2**31 - 1)
    max_new_tokens: int = Field(default=768, ge=64, le=4096)
    do_sample: bool = True
    temperature: float = Field(default=0.7, gt=0, le=2)
    top_p: float = Field(default=0.8, gt=0, le=1)
    top_k: int = Field(default=20, ge=0, le=200)
    repetition_penalty: float = Field(default=1.05, ge=0.8, le=2)


class CandidateGenerator(Protocol):
    def generate_raw(
        self,
        *,
        prompt: str,
        width_mm: float,
        height_mm: float,
        seed: int,
        max_new_tokens: int,
        do_sample: bool,
        temperature: float,
        top_p: float,
        top_k: int,
        repetition_penalty: float,
    ) -> RawPlannerGeneration: ...


@dataclass
class CandidateRecord:
    candidate_id: str
    seed: int
    directory: Path
    raw_output: str
    planner_payload: dict[str, Any] | None
    document: DesignDocument | None
    validation: dict[str, Any]
    operations: list[dict[str, Any]]
    preview_path: Path | None
    score: CombinedScore
    generation: dict[str, Any]


@dataclass(frozen=True)
class BestOfNResult:
    run_dir: Path
    ranking: RankingResult
    diversity: dict[str, object]
    candidates: dict[str, CandidateRecord]
    contact_sheet: Path
    comparison_report: Path


def _write_json(path: Path, payload: object) -> None:
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json")
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _comparison_html(
    *,
    run_dir: Path,
    prompt: str,
    records: dict[str, CandidateRecord],
    ranking: RankingResult,
) -> Path:
    ranks = {item.candidate_id: item.rank for item in ranking.candidates}
    cards = []
    for candidate_id, record in records.items():
        preview = (
            f"candidates/{candidate_id}/preview.png"
            if record.preview_path is not None
            else ""
        )
        image = (
            f'<img src="{html.escape(preview)}" alt="{candidate_id}">'
            if preview
            else '<div class="invalid">No valid preview</div>'
        )
        cards.append(
            "<article>"
            f"<h2>#{ranks[candidate_id]} {html.escape(candidate_id)}</h2>"
            f"{image}"
            f"<p>score={record.score.final_score:.4f} · seed={record.seed} · "
            f"eligible={str(record.score.eligible).lower()}</p>"
            f"<p>{html.escape('; '.join(record.validation.get('recovery_steps', [])))}</p>"
            "</article>"
        )
    content = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Design AI candidates</title>
<style>body{font:16px Arial;margin:24px;background:#f4f4f4;color:#222}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}
article{background:white;padding:16px;border-radius:8px}img{width:100%;height:auto}
.invalid{height:180px;display:grid;place-items:center;background:#ddd;color:#700}</style>
</head><body>"""
    content += f"<h1>{html.escape(prompt)}</h1><div class=\"grid\">"
    content += "".join(cards)
    content += "</div></body></html>\n"
    output = run_dir / "comparison.html"
    output.write_text(content, encoding="utf-8")
    return output.resolve()


def _contact_sheet(
    *,
    run_dir: Path,
    records: dict[str, CandidateRecord],
    ranking: RankingResult,
) -> Path:
    cell_width, cell_height = 640, 430
    columns = 2
    rows = (len(records) + columns - 1) // columns
    sheet = Image.new("RGB", (cell_width * columns, cell_height * rows), "#ECECEC")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    ranks = {item.candidate_id: item.rank for item in ranking.candidates}
    for index, (candidate_id, record) in enumerate(records.items()):
        column, row = index % columns, index // columns
        origin_x, origin_y = column * cell_width, row * cell_height
        if record.preview_path is not None:
            with Image.open(record.preview_path) as preview:
                fitted = ImageOps.contain(preview.convert("RGB"), (620, 370))
            sheet.paste(fitted, (origin_x + 10, origin_y + 42))
        else:
            draw.rectangle(
                (origin_x + 10, origin_y + 42, origin_x + 630, origin_y + 412),
                fill="#D8D8D8",
            )
        label = (
            f"#{ranks[candidate_id]} {candidate_id}  "
            f"score={record.score.final_score:.4f}  seed={record.seed}"
        )
        draw.text((origin_x + 10, origin_y + 12), label, fill="black", font=font)
    output = run_dir / "contact_sheet.png"
    sheet.save(output, format="PNG", optimize=True)
    return output.resolve()


class BestOfNSelector:
    def __init__(
        self,
        *,
        generator: CandidateGenerator,
        scorer: DesignScorer,
        model_provenance: dict[str, Any],
    ) -> None:
        self.generator = generator
        self.scorer = scorer
        self.model_provenance = model_provenance

    def run(
        self,
        *,
        prompt: str,
        width_mm: float,
        height_mm: float,
        settings: CandidateGenerationSettings,
        run_dir: Path,
        raise_on_all_invalid: bool = True,
    ) -> BestOfNResult:
        if not prompt.strip():
            raise ValueError("prompt cannot be empty")
        if not math.isfinite(width_mm) or width_mm <= 0:
            raise ValueError("width_mm must be a finite positive number")
        if not math.isfinite(height_mm) or height_mm <= 0:
            raise ValueError("height_mm must be a finite positive number")
        if run_dir.exists():
            raise FileExistsError(f"run directory already exists: {run_dir}")
        run_dir.mkdir(parents=True)
        candidates_dir = run_dir / "candidates"
        candidates_dir.mkdir()
        request = {
            "prompt": prompt,
            "width_mm": width_mm,
            "height_mm": height_mm,
            "generation": settings.model_dump(mode="json"),
            "model": self.model_provenance,
            "license_class": "research_only",
            "commercial_allowed": False,
        }
        _write_json(run_dir / "request.json", request)

        records: dict[str, CandidateRecord] = {}
        scores: dict[str, CombinedScore] = {}
        valid_documents: dict[str, DesignDocument] = {}
        for index in range(settings.num_candidates):
            candidate_id = f"candidate_{index + 1:02d}"
            seed = settings.base_seed + index
            candidate_dir = candidates_dir / candidate_id
            candidate_dir.mkdir()
            try:
                generation = self.generator.generate_raw(
                    prompt=prompt,
                    width_mm=width_mm,
                    height_mm=height_mm,
                    seed=seed,
                    max_new_tokens=settings.max_new_tokens,
                    do_sample=settings.do_sample,
                    temperature=settings.temperature,
                    top_p=settings.top_p,
                    top_k=settings.top_k,
                    repetition_penalty=settings.repetition_penalty,
                )
            except Exception as exc:
                generation_payload = {
                    "candidate_id": candidate_id,
                    "seed": seed,
                    "duration_seconds": 0.0,
                    "peak_vram_gib": 0.0,
                    "config": settings.model_dump(mode="json"),
                    "generation_error": {
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                }
                validation = {
                    "strict_schema_valid": False,
                    "raw_schema_valid": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "failure_stage": "generation",
                }
                score = self.scorer.score(
                    prompt=prompt,
                    document=None,
                    validation=validation,
                )
                (candidate_dir / "raw_output.txt").write_text("", encoding="utf-8")
                _write_json(candidate_dir / "generation.json", generation_payload)
                _write_json(candidate_dir / "validation.json", validation)
                _write_json(candidate_dir / "metrics.json", score.technical.metrics)
                _write_json(candidate_dir / "score.json", score)
                record = CandidateRecord(
                    candidate_id=candidate_id,
                    seed=seed,
                    directory=candidate_dir.resolve(),
                    raw_output="",
                    planner_payload=None,
                    document=None,
                    validation=validation,
                    operations=[],
                    preview_path=None,
                    score=score,
                    generation=generation_payload,
                )
                records[candidate_id] = record
                scores[candidate_id] = score
                continue
            generation_payload = {
                "candidate_id": candidate_id,
                "seed": generation.seed,
                "duration_seconds": generation.duration_seconds,
                "peak_vram_gib": generation.peak_vram_gib,
                "config": generation.generation_config,
            }
            (candidate_dir / "raw_output.txt").write_text(
                generation.raw_output,
                encoding="utf-8",
            )
            _write_json(candidate_dir / "generation.json", generation_payload)

            planner_payload: dict[str, Any] | None = None
            document: DesignDocument | None = None
            validation: dict[str, Any]
            operations: list[dict[str, Any]] = []
            preview_path: Path | None = None
            try:
                planner_payload = extract_planner_payload(generation.raw_output)
                _write_json(candidate_dir / "planner.json", planner_payload)
                document, validation = parse_design_output(generation.raw_output)
                document.metadata.update(
                    {
                        "trained_model": True,
                        "candidate_id": candidate_id,
                        "generation_seed": seed,
                        "generation_config": generation.generation_config,
                        **self.model_provenance,
                    }
                )
                document = DesignDocument.model_validate(document.model_dump())
                operations = compile_corel_operations(
                    document,
                    width_mm=width_mm,
                    height_mm=height_mm,
                )
            except (ModelOutputError, CorelCompileError) as exc:
                validation = {
                    "strict_schema_valid": False,
                    "raw_schema_valid": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "failure_stage": (
                        "corel_compile"
                        if isinstance(exc, CorelCompileError)
                        else "model_output"
                    ),
                }
                score = self.scorer.score(
                    prompt=prompt,
                    document=None,
                    validation=validation,
                )
                if isinstance(exc, ModelOutputError) and exc.raw_output:
                    (candidate_dir / "raw_output.txt").write_text(
                        exc.raw_output,
                        encoding="utf-8",
                    )
            else:
                preview_path = render_preview(document, candidate_dir / "preview.png")
                score = self.scorer.score(
                    prompt=prompt,
                    document=document,
                    preview_path=preview_path,
                    validation=validation,
                )
                valid_documents[candidate_id] = document
                _write_json(
                    candidate_dir / "design.json",
                    document.model_dump(mode="json", exclude_none=True),
                )
                _write_json(candidate_dir / "corel_operations.json", operations)
            _write_json(candidate_dir / "validation.json", validation)
            _write_json(candidate_dir / "metrics.json", score.technical.metrics)
            _write_json(candidate_dir / "score.json", score)
            record = CandidateRecord(
                candidate_id=candidate_id,
                seed=seed,
                directory=candidate_dir.resolve(),
                raw_output=generation.raw_output,
                planner_payload=planner_payload,
                document=document,
                validation=validation,
                operations=operations,
                preview_path=preview_path,
                score=score,
                generation=generation_payload,
            )
            records[candidate_id] = record
            scores[candidate_id] = score

        ranking = rank_candidate_scores(scores)
        diversity = candidate_diversity(valid_documents)
        ranking_payload = {
            **ranking.model_dump(mode="json"),
            "diversity": diversity,
            "scoring_source": self.scorer.provenance(),
        }
        _write_json(run_dir / "ranking.json", ranking_payload)
        contact_sheet = _contact_sheet(
            run_dir=run_dir,
            records=records,
            ranking=ranking,
        )
        comparison_report = _comparison_html(
            run_dir=run_dir,
            prompt=prompt,
            records=records,
            ranking=ranking,
        )
        if ranking.winner is None:
            if raise_on_all_invalid:
                raise AllCandidatesInvalidError(ranking)
        else:
            winner = records[ranking.winner]
            final_dir = run_dir / "final"
            final_dir.mkdir()
            for file_name in ("design.json", "preview.png", "corel_operations.json"):
                shutil.copy2(winner.directory / file_name, final_dir / file_name)
            _write_json(
                final_dir / "selection.json",
                {
                    "winner": ranking.winner,
                    "score": winner.score.final_score,
                    "candidate_directory": str(winner.directory),
                },
            )
        return BestOfNResult(
            run_dir=run_dir.resolve(),
            ranking=ranking,
            diversity=diversity,
            candidates=records,
            contact_sheet=contact_sheet,
            comparison_report=comparison_report,
        )
