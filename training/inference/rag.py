"""Reference-grounded Qwen generation and best-of-N orchestration."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from training.evaluation.scoring import DesignScorer
from training.inference.candidates import (
    BestOfNResult,
    BestOfNSelector,
    CandidateGenerationSettings,
    CandidateGenerator,
)
from training.inference.qwen3_planner import RawPlannerGeneration, planner_messages
from training.inference.reference_layout import apply_reference_layout_guidance
from training.retrieval import (
    ReferenceContextV1,
    ReferenceProvider,
    ReferenceRetrievalResultV1,
    ReferenceRetriever,
    StructuredBriefV1,
    analyze_brief,
    build_reference_context,
    estimate_reference_tokens,
)
from training.typography.fitting import fit_design_typography
from training.visual import apply_visual_composition, evaluate_visual_quality, get_visual_profile


def _write_json(path: Path, payload: object) -> None:
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json", exclude_none=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _context_hash(context: ReferenceContextV1) -> str:
    payload = context.model_dump_json(exclude_none=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _rendered_prompt_tokens(
    generator: CandidateGenerator,
    *,
    prompt: str,
    width_mm: float,
    height_mm: float,
) -> int:
    tokenizer = getattr(generator, "tokenizer", None)
    if tokenizer is None:
        return estimate_reference_tokens(
            planner_messages(prompt, width_mm, height_mm)
        )
    messages = planner_messages(prompt, width_mm, height_mm)
    rendered = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    encoded = tokenizer(rendered, add_special_tokens=False)
    input_ids = encoded["input_ids"] if isinstance(encoded, dict) else encoded.input_ids
    return len(input_ids)


class ReferenceGroundedGenerator:
    """Wrap one loaded planner without changing the v0.2 generator protocol."""

    def __init__(
        self,
        *,
        base_generator: CandidateGenerator,
        brief: StructuredBriefV1,
        retrieval: list[ReferenceRetrievalResultV1],
        context: ReferenceContextV1,
    ) -> None:
        if not retrieval:
            raise ValueError("reference-grounded generation requires references")
        if not context.references:
            raise ValueError("reference context contains no summaries")
        self.base_generator = base_generator
        self.brief = brief
        self.retrieval = retrieval
        self.context = context
        self.reference_ids = [item.reference_id for item in retrieval]
        self.context_hash = _context_hash(context)

    def grounded_prompt(self, prompt: str) -> str:
        payload = {
            "brief": self.brief.model_dump(
                mode="json",
                exclude={"prompt"},
                exclude_none=True,
            ),
            "reference_context": self.context.model_dump(
                mode="json",
                exclude_none=True,
            ),
        }
        return (
            f"ORIGINAL USER BRIEF: {prompt}\n"
            "REFERENCE-GROUNDED MODE. References are structural inspiration only. "
            "Do not copy any reference text, brand, logo, asset, or exact coordinates. "
            "Synthesize a new editable layout that preserves every requested element. "
            "Use the reference composition, hierarchy ratios, spacing, alignment, "
            "density, hero region, CTA region, and palette intent as guidance. "
            "Use the exact compact flat elements ARRAY required by the system prompt. "
            "Never create nested element maps, layout/design wrappers, or a text object "
            "inside another element. Each text element needs one text STRING, role, "
            "bbox with x/y/width/height, font_size, and alignment. Keep the response "
            "under the generation limit and return JSON only.\n"
            f"GROUNDING_JSON={json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
        )

    def generate_raw(self, **kwargs: Any) -> RawPlannerGeneration:
        original_prompt = str(kwargs["prompt"])
        grounded = self.grounded_prompt(original_prompt)
        baseline_tokens = _rendered_prompt_tokens(
            self.base_generator,
            prompt=original_prompt,
            width_mm=float(kwargs["width_mm"]),
            height_mm=float(kwargs["height_mm"]),
        )
        rag_tokens = _rendered_prompt_tokens(
            self.base_generator,
            prompt=grounded,
            width_mm=float(kwargs["width_mm"]),
            height_mm=float(kwargs["height_mm"]),
        )
        identity_generator = getattr(
            self.base_generator,
            "generate_raw_with_identity",
            None,
        )
        if callable(identity_generator):
            generation = identity_generator(
                **{key: value for key, value in kwargs.items() if key != "prompt"},
                original_prompt=original_prompt,
                grounded_prompt=grounded,
                reference_context_hash=self.context_hash,
                reference_ids=self.reference_ids,
            )
        else:
            generation = self.base_generator.generate_raw(
                **{**kwargs, "prompt": grounded}
            )
        return RawPlannerGeneration(
            raw_output=generation.raw_output,
            duration_seconds=generation.duration_seconds,
            seed=generation.seed,
            generation_config={
                **generation.generation_config,
                "reference_mode": "rag",
                "reference_ids": self.reference_ids,
                "reference_context_hash": self.context_hash,
                "reference_context_estimated_tokens": self.context.estimated_tokens,
                "baseline_prompt_tokens": baseline_tokens,
                "rag_prompt_tokens": rag_tokens,
                "reference_prompt_token_delta": rag_tokens - baseline_tokens,
            },
            peak_vram_gib=generation.peak_vram_gib,
        )


@dataclass(frozen=True)
class ReferenceGroundedRunResult:
    selection: BestOfNResult
    brief: StructuredBriefV1
    retrieval: list[ReferenceRetrievalResultV1]
    context: ReferenceContextV1
    retrieval_latency_seconds: float


class ReferenceGroundedDesignPipeline:
    """Brief -> retrieval -> compact context -> Qwen -> fitted best-of-4."""

    def __init__(
        self,
        *,
        base_generator: CandidateGenerator,
        provider: ReferenceProvider,
        scorer: DesignScorer,
        model_provenance: dict[str, Any],
        top_k: int = 5,
        context_token_budget: int = 350,
        visual_composition: bool = False,
        benchmark_mode: bool = False,
        document_postprocessor: Callable[
            [Any, StructuredBriefV1], tuple[Any, dict[str, object]]
        ] | None = None,
    ) -> None:
        if not 1 <= top_k <= 8:
            raise ValueError("reference top_k must be between 1 and 8")
        self.base_generator = base_generator
        self.provider = provider
        self.scorer = scorer
        self.model_provenance = {
            **model_provenance,
            "generator": "qwen3_1_7b_local_qlora_reference_rag_v0.3",
            "reference_mode": "rag",
        }
        self.top_k = top_k
        self.context_token_budget = context_token_budget
        self.visual_composition = visual_composition
        self.benchmark_mode = benchmark_mode
        self.document_postprocessor = document_postprocessor

    def run(
        self,
        *,
        prompt: str,
        width_mm: float,
        height_mm: float,
        settings: CandidateGenerationSettings,
        run_dir: Path,
        raise_on_all_invalid: bool = True,
    ) -> ReferenceGroundedRunResult:
        brief = analyze_brief(prompt, width=width_mm, height=height_mm)
        started = time.perf_counter()
        retrieval = ReferenceRetriever(self.provider).retrieve_references(
            brief,
            top_k=self.top_k,
        )
        retrieval_latency = time.perf_counter() - started
        context = build_reference_context(
            retrieval,
            max_tokens=self.context_token_budget,
        )
        generator = ReferenceGroundedGenerator(
            base_generator=self.base_generator,
            brief=brief,
            retrieval=retrieval,
            context=context,
        )

        def postprocess(document: Any) -> tuple[Any, dict[str, object]]:
            grounded, layout_report = apply_reference_layout_guidance(
                document,
                brief=brief,
                context=context,
                benchmark_mode=self.benchmark_mode,
            )
            visual_report: dict[str, object] | None = None
            if self.visual_composition:
                grounded, composition_report = apply_visual_composition(
                    grounded,
                    brief=brief,
                    reference_palette=(
                        context.references[0].palette if context.references else []
                    ),
                    benchmark_mode=self.benchmark_mode,
                )
                visual_report = composition_report.model_dump(mode="json")
            fitted, typography_report = fit_design_typography(
                grounded,
                allow_expand=False,
            )
            report: dict[str, object] = {
                "engine": (
                    "reference_grounded_postprocessor_v0.3.1"
                    if self.visual_composition
                    else "reference_grounded_postprocessor_v1"
                ),
                "reference_layout": layout_report,
                "typography": typography_report,
                "truncated_count": typography_report.get("truncated_count", 0),
                "unresolved_overflow_count": typography_report.get(
                    "unresolved_overflow_count", 0
                ),
            }
            if visual_report is not None:
                report["visual_composition"] = visual_report
                report["visual_metrics"] = evaluate_visual_quality(
                    fitted,
                    profile=get_visual_profile(brief.category, format_name=brief.format),
                )
            if self.document_postprocessor is not None:
                fitted, extension_report = self.document_postprocessor(fitted, brief)
                fitted, final_typography = fit_design_typography(
                    fitted,
                    allow_expand=False,
                )
                report["extension"] = extension_report
                report["final_typography"] = final_typography
                report["truncated_count"] = final_typography.get("truncated_count", 0)
                report["unresolved_overflow_count"] = final_typography.get(
                    "unresolved_overflow_count", 0
                )
            return fitted, report
        selection = BestOfNSelector(
            generator=generator,
            scorer=self.scorer,
            model_provenance=self.model_provenance,
            document_postprocessor=postprocess,
        ).run(
            prompt=prompt,
            width_mm=width_mm,
            height_mm=height_mm,
            settings=settings,
            run_dir=run_dir,
            raise_on_all_invalid=raise_on_all_invalid,
        )

        _write_json(run_dir / "brief.json", brief)
        _write_json(
            run_dir / "retrieval.json",
            {
                "schema_version": "1.0",
                "provider": self.provider.provider_name,
                "top_k_requested": self.top_k,
                "result_count": len(retrieval),
                "latency_seconds": retrieval_latency,
                "context_hash": generator.context_hash,
                "context_estimated_tokens": context.estimated_tokens,
                "context_truncated": context.truncated,
                "results": [item.model_dump(mode="json") for item in retrieval],
                "license_class": "research_only",
                "commercial_allowed": False,
            },
        )
        _write_json(run_dir / "reference_context.json", context)
        references_dir = run_dir / "references"
        references_dir.mkdir()
        for index, result in enumerate(retrieval, start=1):
            _write_json(
                references_dir / f"ref_{index:02d}.json",
                result,
            )

        request_path = run_dir / "request.json"
        request = json.loads(request_path.read_text(encoding="utf-8"))
        request.update(
            {
                "reference_mode": "rag",
                "reference_top_k": self.top_k,
                "reference_ids": generator.reference_ids,
                "reference_context_hash": generator.context_hash,
            }
        )
        _write_json(request_path, request)
        durations = [
            float(record.generation["duration_seconds"])
            for record in selection.candidates.values()
        ]
        _write_json(
            run_dir / "performance.json",
            {
                "retrieval_latency_seconds": retrieval_latency,
                "total_candidate_generation_seconds": sum(durations),
                "average_candidate_generation_seconds": sum(durations) / len(durations),
                "peak_vram_gib": max(
                    float(record.generation["peak_vram_gib"])
                    for record in selection.candidates.values()
                ),
                "baseline_prompt_tokens": min(
                    int(record.generation["config"].get("baseline_prompt_tokens", 0))
                    for record in selection.candidates.values()
                ),
                "rag_prompt_tokens": max(
                    int(record.generation["config"].get("rag_prompt_tokens", 0))
                    for record in selection.candidates.values()
                ),
            },
        )
        return ReferenceGroundedRunResult(
            selection=selection,
            brief=brief,
            retrieval=retrieval,
            context=context,
            retrieval_latency_seconds=retrieval_latency,
        )
