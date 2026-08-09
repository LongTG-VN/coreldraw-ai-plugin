"""Configurable combined scoring and deterministic candidate ranking."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from training.evaluation.critics import (
    AestheticCritic,
    AestheticCriticResult,
    TechnicalCritic,
    TechnicalCriticResult,
)
from training.schemas.design import DesignDocument


class ScoreModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScoreWeights(ScoreModel):
    technical: float = Field(ge=0, le=1)
    composition: float = Field(ge=0, le=1)
    visual_hierarchy: float = Field(ge=0, le=1)
    typography: float = Field(ge=0, le=1)
    spacing: float = Field(ge=0, le=1)
    color_harmony: float = Field(ge=0, le=1)
    balance: float = Field(ge=0, le=1)
    readability: float = Field(ge=0, le=1)
    prompt_match: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_sum(self) -> "ScoreWeights":
        if abs(sum(self.model_dump().values()) - 1.0) > 1e-8:
            raise ValueError("score weights must sum to 1.0")
        return self


class CombinedScore(ScoreModel):
    scale: str = "0..1"
    final_score: float = Field(ge=0, le=1)
    eligible: bool
    technical: TechnicalCriticResult
    aesthetic: AestheticCriticResult | None
    weights: ScoreWeights


class RankedCandidate(ScoreModel):
    candidate_id: str
    rank: int = Field(ge=1)
    final_score: float = Field(ge=0, le=1)
    eligible: bool
    hard_failure: bool


class RankingResult(ScoreModel):
    winner: str | None
    candidates: list[RankedCandidate]
    all_candidates_invalid: bool
    tie_breaker: str = "eligible, final_score, technical_score, candidate_id"


class AllCandidatesInvalidError(RuntimeError):
    def __init__(self, ranking: RankingResult) -> None:
        super().__init__("all generated candidates are invalid")
        self.ranking = ranking


class DesignScorer:
    def __init__(
        self,
        *,
        weights: ScoreWeights,
        aesthetic_critic: AestheticCritic,
        technical_critic: TechnicalCritic | None = None,
    ) -> None:
        self.weights = weights
        self.technical_critic = technical_critic or TechnicalCritic()
        self.aesthetic_critic = aesthetic_critic

    def provenance(self) -> dict[str, str | bool]:
        return {
            "technical": (
                f"{self.technical_critic.critic_name}:"
                f"{self.technical_critic.critic_version}"
            ),
            "aesthetic": (
                f"{self.aesthetic_critic.critic_name}:"
                f"{self.aesthetic_critic.critic_version}"
            ),
            "vision_model_used": self.aesthetic_critic.model_based,
        }

    def score(
        self,
        *,
        prompt: str,
        document: DesignDocument | None,
        preview_path: Path | None = None,
        validation: dict[str, Any] | None = None,
    ) -> CombinedScore:
        technical = self.technical_critic.score(document, validation=validation)
        if document is None or technical.hard_failure:
            return CombinedScore(
                final_score=0,
                eligible=False,
                technical=technical,
                aesthetic=None,
                weights=self.weights,
            )
        if preview_path is None:
            raise ValueError("valid candidates require a preview path")
        aesthetic = self.aesthetic_critic.score(
            prompt=prompt,
            document=document,
            preview_path=preview_path,
            metrics=technical.metrics,
        )
        weighted = (
            self.weights.technical * technical.overall
            + self.weights.composition * aesthetic.composition
            + self.weights.visual_hierarchy * aesthetic.visual_hierarchy
            + self.weights.typography * aesthetic.typography
            + self.weights.spacing * aesthetic.spacing
            + self.weights.color_harmony * aesthetic.color_harmony
            + self.weights.balance * aesthetic.balance
            + self.weights.readability * aesthetic.readability
            + self.weights.prompt_match * aesthetic.style_match
        )
        return CombinedScore(
            final_score=max(0.0, min(weighted, 1.0)),
            eligible=True,
            technical=technical,
            aesthetic=aesthetic,
            weights=self.weights,
        )


def rank_candidate_scores(scores: dict[str, CombinedScore]) -> RankingResult:
    ordered = sorted(
        scores.items(),
        key=lambda item: (
            not item[1].eligible,
            -item[1].final_score,
            -item[1].technical.overall,
            item[0],
        ),
    )
    candidates = [
        RankedCandidate(
            candidate_id=candidate_id,
            rank=index,
            final_score=score.final_score,
            eligible=score.eligible,
            hard_failure=score.technical.hard_failure,
        )
        for index, (candidate_id, score) in enumerate(ordered, start=1)
    ]
    winner = next(
        (candidate.candidate_id for candidate in candidates if candidate.eligible),
        None,
    )
    return RankingResult(
        winner=winner,
        candidates=candidates,
        all_candidates_invalid=winner is None,
    )
