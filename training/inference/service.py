"""Lazy local trained Design AI service with explicit research-only status."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from training.evaluation.critics import HeuristicAestheticCritic
from training.evaluation.scoring import DesignScorer, ScoreWeights
from training.inference.candidates import CandidateGenerationSettings
from training.inference.corel_compiler import compile_corel_operations
from training.inference.generation_identity import fingerprint_checkpoint
from training.inference.qwen3_planner import Qwen3PlannerSession
from training.inference.rag import ReferenceGroundedDesignPipeline
from training.retrieval import JsonlReferenceProvider
from training.schemas.design import AssetSpec, DesignDocument
from training.visual.composition import VISUAL_ENGINE_VERSION


MODEL_ID = "Qwen/Qwen3-1.7B"
MODEL_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"


class ServiceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrainedDesignRequest(ServiceModel):
    prompt: str = Field(min_length=1, max_length=4_000)
    width_mm: FiniteFloat = Field(gt=0, le=20_000)
    height_mm: FiniteFloat = Field(gt=0, le=20_000)
    num_candidates: int = Field(default=4, ge=1, le=8)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    reference_top_k: int = Field(default=5, ge=1, le=8)


class TrainedDesignResponse(ServiceModel):
    run_id: str
    design: DesignDocument
    assets: list[AssetSpec] = Field(default_factory=list)
    winner: str
    ranking: dict[str, Any]
    metrics: dict[str, Any]
    generation_metadata: dict[str, Any]
    references: list[dict[str, Any]]
    corel_operations: list[dict[str, Any]]
    research_only: bool = True
    commercial_allowed: bool = False


class TrainedModelStatus(ServiceModel):
    configured: bool
    available: bool
    loaded: bool
    model_id: str
    revision: str
    checkpoint_exists: bool
    reference_index_exists: bool
    device: str
    research_only: bool = True
    commercial_allowed: bool = False
    generation_count: int = Field(ge=0)
    load_duration_seconds: float | None = Field(default=None, ge=0)
    load_error: str | None = None


class TrainedDesignUnavailableError(RuntimeError):
    pass


class TrainedDesignGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class TrainedDesignServiceConfig:
    repo_root: Path
    checkpoint: Path
    reference_index: Path
    model_config: Path
    score_config: Path
    artifact_root: Path
    enabled: bool = True
    context_token_budget: int = 350
    max_new_tokens: int = 512

    @classmethod
    def from_environment(cls, repo_root: Path) -> "TrainedDesignServiceConfig":
        root = repo_root.resolve()

        def local_path(name: str, default: str) -> Path:
            raw = os.getenv(name, default)
            path = Path(raw).expanduser()
            return (root / path).resolve() if not path.is_absolute() else path.resolve()

        enabled = os.getenv("DESIGN_AI_TRAINED_ENABLED", "auto").strip().casefold()
        return cls(
            repo_root=root,
            checkpoint=local_path(
                "DESIGN_AI_CHECKPOINT",
                "training/artifacts/runs/20260809_qwen3_1_7b_smoke/checkpoint-5",
            ),
            reference_index=local_path(
                "DESIGN_AI_REFERENCE_INDEX",
                "training/artifacts/reference_corpora/design_v0_3/reference_index.jsonl",
            ),
            model_config=local_path(
                "DESIGN_AI_MODEL_CONFIG",
                "training/config/experiments/qwen3_1_7b_local_qlora.json",
            ),
            score_config=local_path(
                "DESIGN_AI_SCORE_CONFIG",
                "training/config/scoring/aesthetic_v0_3.json",
            ),
            artifact_root=local_path(
                "DESIGN_AI_RUNTIME_ARTIFACT_ROOT",
                "training/artifacts/runtime/trained",
            ),
            enabled=enabled not in {"0", "false", "off", "disabled"},
            context_token_budget=int(os.getenv("DESIGN_AI_CONTEXT_TOKEN_BUDGET", "350")),
            max_new_tokens=int(os.getenv("DESIGN_AI_MAX_NEW_TOKENS", "512")),
        )


SessionFactory = Callable[..., Any]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json", exclude_none=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class TrainedDesignService:
    """Own exactly one Qwen session and serialize local GPU generation."""

    def __init__(
        self,
        config: TrainedDesignServiceConfig,
        *,
        session_factory: SessionFactory = Qwen3PlannerSession,
    ) -> None:
        self.config = config
        self._session_factory = session_factory
        self._session: Any | None = None
        self._lock = threading.RLock()
        self._generation_count = 0
        self._load_error: str | None = None

    @classmethod
    def from_environment(cls, repo_root: Path) -> "TrainedDesignService":
        return cls(TrainedDesignServiceConfig.from_environment(repo_root))

    def _static_available(self) -> bool:
        return bool(
            self.config.enabled
            and self.config.checkpoint.is_dir()
            and self.config.reference_index.is_file()
            and self.config.model_config.is_file()
            and self.config.score_config.is_file()
        )

    def status(self) -> TrainedModelStatus:
        loaded = self._session is not None
        if loaded:
            device = "cuda"
        elif importlib.util.find_spec("torch") is None:
            device = "unavailable"
        else:
            device = "cuda_required_not_loaded"
        return TrainedModelStatus(
            configured=self.config.enabled,
            available=self._static_available() and self._load_error is None,
            loaded=loaded,
            model_id=MODEL_ID,
            revision=MODEL_REVISION,
            checkpoint_exists=self.config.checkpoint.is_dir(),
            reference_index_exists=self.config.reference_index.is_file(),
            device=device,
            generation_count=self._generation_count,
            load_duration_seconds=(
                float(self._session.load_duration_seconds) if loaded else None
            ),
            load_error=self._load_error,
        )

    def _ensure_session(self) -> Any:
        if self._session is not None:
            return self._session
        if not self._static_available():
            status = self.status()
            missing = []
            if not self.config.enabled:
                missing.append("service disabled")
            if not status.checkpoint_exists:
                missing.append("checkpoint missing")
            if not status.reference_index_exists:
                missing.append("reference index missing")
            if not self.config.model_config.is_file():
                missing.append("model config missing")
            if not self.config.score_config.is_file():
                missing.append("score config missing")
            raise TrainedDesignUnavailableError(", ".join(missing))
        model_config = _read_json(self.config.model_config)
        if not isinstance(model_config, dict):
            raise TrainedDesignUnavailableError("model config root must be an object")
        if model_config.get("model_id") != MODEL_ID:
            raise TrainedDesignUnavailableError("configured model ID does not match release")
        if model_config.get("model_revision") != MODEL_REVISION:
            raise TrainedDesignUnavailableError("configured model revision does not match release")
        try:
            self._session = self._session_factory(
                checkpoint=self.config.checkpoint,
                model_id=MODEL_ID,
                model_revision=MODEL_REVISION,
            )
        except Exception as exc:
            self._load_error = f"{type(exc).__name__}: {exc}"
            raise TrainedDesignUnavailableError(
                f"trained model failed to load: {self._load_error}"
            ) from exc
        self._load_error = None
        return self._session

    def _next_run(self) -> tuple[str, Path]:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        run_id = f"trained-{timestamp}-{uuid.uuid4().hex[:8]}"
        root = self.config.artifact_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        run_dir = (root / run_id).resolve()
        if root not in run_dir.parents:
            raise TrainedDesignGenerationError("runtime artifact path escaped configured root")
        return run_id, run_dir

    def generate(self, request: TrainedDesignRequest) -> TrainedDesignResponse:
        with self._lock:
            session = self._ensure_session()
            run_id, run_dir = self._next_run()
            model_config = _read_json(self.config.model_config)
            score_config = _read_json(self.config.score_config)
            if not isinstance(model_config, dict) or not isinstance(score_config, dict):
                raise TrainedDesignGenerationError("model/score config root must be an object")
            scorer = DesignScorer(
                weights=ScoreWeights.model_validate(score_config["weights"]),
                aesthetic_critic=HeuristicAestheticCritic(),
            )
            pipeline = ReferenceGroundedDesignPipeline(
                base_generator=session,
                provider=JsonlReferenceProvider(self.config.reference_index),
                scorer=scorer,
                model_provenance={
                    "model_id": MODEL_ID,
                    "model_revision": MODEL_REVISION,
                    "adapter_checkpoint": str(self.config.checkpoint),
                    "trained_model": True,
                    "quantization": "NF4 4-bit",
                    "lora_rank": model_config["lora"]["rank"],
                    "lora_alpha": model_config["lora"]["alpha"],
                },
                top_k=request.reference_top_k,
                context_token_budget=self.config.context_token_budget,
                visual_composition=True,
                benchmark_mode=False,
            )
            started = time.perf_counter()
            try:
                result = pipeline.run(
                    prompt=request.prompt,
                    width_mm=float(request.width_mm),
                    height_mm=float(request.height_mm),
                    settings=CandidateGenerationSettings(
                        num_candidates=request.num_candidates,
                        base_seed=request.seed,
                        max_new_tokens=self.config.max_new_tokens,
                    ),
                    run_dir=run_dir,
                )
            except Exception as exc:
                raise TrainedDesignGenerationError(
                    f"trained generation failed for run {run_id}: {type(exc).__name__}: {exc}"
                ) from exc
            winner = result.selection.ranking.winner
            if winner is None:
                raise TrainedDesignGenerationError(f"run {run_id} produced no eligible winner")
            final_dir = run_dir / "final"
            design = DesignDocument.model_validate(_read_json(final_dir / "design.json"))
            operations = _read_json(final_dir / "corel_operations.json")
            if not isinstance(operations, list):
                operations = compile_corel_operations(
                    design,
                    width_mm=float(request.width_mm),
                    height_mm=float(request.height_mm),
                )
            winner_metrics = _read_json(run_dir / "candidates" / winner / "metrics.json")
            performance = _read_json(run_dir / "performance.json")
            elapsed = time.perf_counter() - started
            self._generation_count += 1
            references = [
                {
                    "reference_id": item.reference_id,
                    "score": item.score,
                    "match": item.match.model_dump(mode="json"),
                }
                for item in result.retrieval
            ]
            manifest = {
                "schema_version": "1.0",
                "run_id": run_id,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "prompt_sha256": hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
                "model_id": MODEL_ID,
                "model_revision": MODEL_REVISION,
                "checkpoint": str(self.config.checkpoint),
                "checkpoint_sha256": fingerprint_checkpoint(self.config.checkpoint),
                "reference_index": str(self.config.reference_index),
                "reference_index_sha256": _sha256_file(self.config.reference_index),
                "reference_top_k": request.reference_top_k,
                "reference_ids": [item["reference_id"] for item in references],
                "candidate_count": request.num_candidates,
                "seeds": [request.seed + index for index in range(request.num_candidates)],
                "visual_engine_version": VISUAL_ENGINE_VERSION,
                "critic": scorer.provenance(),
                "license_class": "research_only",
                "research_only": True,
                "commercial_allowed": False,
                "winner": winner,
                "duration_seconds": elapsed,
            }
            _write_json(run_dir / "run_manifest.json", manifest)
            return TrainedDesignResponse(
                run_id=run_id,
                design=design,
                assets=design.assets,
                winner=winner,
                ranking=result.selection.ranking.model_dump(mode="json"),
                metrics=winner_metrics,
                generation_metadata={
                    **manifest,
                    "performance": performance,
                    "artifact_path": str(run_dir),
                },
                references=references,
                corel_operations=operations,
            )


__all__ = [
    "MODEL_ID",
    "MODEL_REVISION",
    "TrainedDesignGenerationError",
    "TrainedDesignRequest",
    "TrainedDesignResponse",
    "TrainedDesignService",
    "TrainedDesignServiceConfig",
    "TrainedDesignUnavailableError",
    "TrainedModelStatus",
]
