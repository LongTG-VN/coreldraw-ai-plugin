"""Clean planner abstraction for comparing design planning models under an identical contract."""

from __future__ import annotations

import abc
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from training.schemas.design import (
    AssetSpec,
    BoundingBox,
    CanvasSpec,
    ColorSpec,
    DesignDocument,
    DesignElement,
    NormalizedBoundingBox,
    SourceSpec,
    TextSpec,
    VisualSpec,
    normalize_bbox,
)


class ContentLockSpec(BaseModel):
    """Invariant content specification for benchmark content consistency."""

    model_config = ConfigDict(extra="forbid")

    brief_id: str
    category: str
    business_name: str
    headline: str
    body: str = ""
    cta: str = ""
    price_offer: str = ""
    logo_asset_id: str = ""
    hero_asset_id: str = ""
    canvas_width_mm: float
    canvas_height_mm: float

    def compute_content_hash(self) -> str:
        payload = f"{self.brief_id}|{self.category}|{self.business_name}|{self.headline}|{self.body}|{self.cta}|{self.price_offer}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def compute_asset_hash(self) -> str:
        payload = f"{self.logo_asset_id}|{self.hero_asset_id}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def compute_canvas_hash(self) -> str:
        payload = f"{self.canvas_width_mm}x{self.canvas_height_mm}mm"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DesignPlanV2(BaseModel):
    """Unified structured design plan produced by any planner."""

    model_config = ConfigDict(extra="forbid")

    planner_name: str
    brief_id: str
    layout_family: str
    canvas: CanvasSpec
    elements: list[DesignElement]
    assets: list[AssetSpec] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str
    asset_hash: str
    canvas_hash: str


@dataclass
class PlannerGenerationResult:
    planner_name: str
    brief_id: str
    candidate_index: int
    layout_family: str
    document: DesignDocument
    plan_v2: DesignPlanV2
    latency_seconds: float
    raw_output: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseDesignPlanner(abc.ABC):
    """Abstract base planner enforcing the same output contract across planners."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abc.abstractmethod
    def plan(
        self,
        lock_spec: ContentLockSpec,
        candidate_index: int,
        seed: int = 42,
    ) -> PlannerGenerationResult:
        """Produce a structured design plan satisfying the content lock."""
        pass


def validate_content_lock(doc: DesignDocument, lock_spec: ContentLockSpec) -> bool:
    """Verify that a generated DesignDocument preserves all required business content."""

    text_contents = [
        elem.text.content for elem in doc.elements if elem.type == "text" and elem.text is not None
    ]
    all_text = " ".join(text_contents)

    if lock_spec.business_name and lock_spec.business_name not in all_text:
        return False
    if lock_spec.headline and lock_spec.headline not in all_text:
        return False
    if lock_spec.cta and lock_spec.cta not in all_text:
        return False
    if lock_spec.price_offer and lock_spec.price_offer not in all_text:
        return False

    return True
