"""Stable request/response contract for a future Design AI service."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from training.schemas.design import AssetSpec, DesignDocument


class DesignGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=4_000)
    width_mm: FiniteFloat = Field(gt=0, le=20_000)
    height_mm: FiniteFloat = Field(gt=0, le=20_000)


class DesignGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    design: DesignDocument
    assets: list[AssetSpec] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
