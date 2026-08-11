from __future__ import annotations

import json
from pathlib import Path

from training.inference.generation_identity import (
    build_generation_identity,
    fingerprint_checkpoint,
    sha256_text,
)
from training.inference.qwen3_planner import RawPlannerGeneration
from training.tools._benchmark_reference_rag_impl import (
    AuditedRagGenerator,
    _prepare_benchmark_output,
)


GENERATION = {
    "max_new_tokens": 512,
    "do_sample": True,
    "temperature": 0.7,
    "top_p": 0.8,
    "top_k": 20,
    "repetition_penalty": 1.05,
}


class FakeLiveGenerator:
    tokenizer = object()

    def __init__(self) -> None:
        self.calls = 0

    def generate_raw(self, **kwargs: object) -> RawPlannerGeneration:
        self.calls += 1
        return RawPlannerGeneration(
            raw_output=f"fresh-{self.calls}",
            duration_seconds=1.0,
            seed=int(kwargs["seed"]),
            generation_config=dict(GENERATION),
            peak_vram_gib=0.1,
        )


def _checkpoint(tmp_path: Path) -> Path:
    checkpoint = tmp_path / "checkpoint-5"
    checkpoint.mkdir()
    (checkpoint / "adapter_model.safetensors").write_bytes(b"adapter")
    (checkpoint / "adapter_config.json").write_text("{}", encoding="utf-8")
    return checkpoint


def _identity(checkpoint: Path, *, prompt: str = "spa", context: str = "a" * 16):
    return build_generation_identity(
        original_prompt=prompt,
        grounded_prompt=f"grounded:{prompt}:{context}",
        reference_context_hash=context,
        reference_ids=["ref-1", "ref-2"],
        width_mm=210,
        height_mm=297,
        seed=42,
        generation_config=GENERATION,
        model_id="Qwen/Qwen3-1.7B",
        model_revision="revision",
        checkpoint_sha256=fingerprint_checkpoint(checkpoint),
    )


def _cache_candidate(
    root: Path,
    checkpoint: Path,
    *,
    raw: str = "cached",
    candidate_id: str = "candidate_01",
) -> Path:
    candidate = root / "runs" / "spa" / "candidates" / candidate_id
    candidate.mkdir(parents=True)
    identity = _identity(checkpoint)
    config = {
        **GENERATION,
        "generation_identity": identity.model_dump(mode="json"),
        "generation_identity_sha256": identity.identity_sha256,
        "raw_output_sha256": sha256_text(raw),
    }
    (candidate / "raw_output.txt").write_text(raw, encoding="utf-8")
    (candidate / "generation.json").write_text(
        json.dumps(
            {
                "seed": 42,
                "duration_seconds": 2.5,
                "peak_vram_gib": 1.0,
                "config": config,
            }
        ),
        encoding="utf-8",
    )
    (candidate / "validation.json").write_text(
        json.dumps({"strict_schema_valid": False}), encoding="utf-8"
    )
    (candidate / "metrics.json").write_text("{}", encoding="utf-8")
    (candidate / "score.json").write_text("{}", encoding="utf-8")
    return candidate


def _generate(
    generator: AuditedRagGenerator,
    *,
    prompt: str = "spa",
    context: str = "a" * 16,
):
    return generator.generate_raw_with_identity(
        original_prompt=prompt,
        grounded_prompt=f"grounded:{prompt}:{context}",
        reference_context_hash=context,
        reference_ids=["ref-1", "ref-2"],
        width_mm=210,
        height_mm=297,
        seed=42,
        **GENERATION,
    )


def test_generation_identity_changes_for_prompt_context_and_model() -> None:
    common = dict(
        grounded_prompt="grounded",
        reference_context_hash=sha256_text("context-a")[:16],
        reference_ids=["ref-1"],
        width_mm=210,
        height_mm=297,
        seed=42,
        generation_config=GENERATION,
        model_id="model",
        model_revision="revision",
        checkpoint_sha256="a" * 64,
    )
    first = build_generation_identity(original_prompt="spa", **common)
    duplicate = build_generation_identity(original_prompt="spa", **common)
    prompt_change = build_generation_identity(original_prompt="cafe", **common)
    context_change = build_generation_identity(
        original_prompt="spa",
        **{**common, "reference_context_hash": sha256_text("context-b")[:16]},
    )
    model_change = build_generation_identity(
        original_prompt="spa", **{**common, "model_revision": "revision-2"}
    )

    assert first.identity_sha256 == duplicate.identity_sha256
    assert len(
        {
            first.identity_sha256,
            prompt_change.identity_sha256,
            context_change.identity_sha256,
            model_change.identity_sha256,
        }
    ) == 4


def test_resume_reuses_only_exact_verified_identity(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path)
    source = tmp_path / "resume"
    _cache_candidate(source, checkpoint)
    live = FakeLiveGenerator()
    generator = AuditedRagGenerator(
        live,  # type: ignore[arg-type]
        model_id="Qwen/Qwen3-1.7B",
        model_revision="revision",
        checkpoint=checkpoint,
        resume_roots=[source],
    )

    resumed = _generate(generator)
    different_prompt = _generate(generator, prompt="cafe")
    different_context = _generate(generator, context="b" * 16)

    assert resumed.raw_output == "cached"
    assert resumed.generation_config["resumed_verified_candidate"] is True
    assert resumed.generation_config["audited_raw_cache_reuse"] is False
    assert different_prompt.raw_output == "fresh-1"
    assert different_context.raw_output == "fresh-2"
    assert generator.resume_hits == 1
    assert generator.fresh_generation_count == 2


def test_corrupted_or_legacy_cache_entry_is_rejected(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path)
    source = tmp_path / "cache"
    candidate = _cache_candidate(source, checkpoint)
    (candidate / "raw_output.txt").write_text("tampered", encoding="utf-8")
    live = FakeLiveGenerator()
    generator = AuditedRagGenerator(
        live,  # type: ignore[arg-type]
        model_id="Qwen/Qwen3-1.7B",
        model_revision="revision",
        checkpoint=checkpoint,
        audited_cache_root=source,
    )

    result = _generate(generator)

    assert result.raw_output == "fresh-1"
    assert generator.audited_cache_hits == 0
    assert generator.fresh_generation_count == 1
    assert generator.rejected_entries[0]["reason"] == "raw_output_sha256_mismatch"


def test_ambiguous_same_identity_with_different_raw_output_is_never_reused(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint(tmp_path)
    source = tmp_path / "cache"
    _cache_candidate(source, checkpoint, raw="first", candidate_id="candidate_01")
    _cache_candidate(source, checkpoint, raw="second", candidate_id="candidate_02")
    live = FakeLiveGenerator()
    generator = AuditedRagGenerator(
        live,  # type: ignore[arg-type]
        model_id="Qwen/Qwen3-1.7B",
        model_revision="revision",
        checkpoint=checkpoint,
        audited_cache_root=source,
    )

    result = _generate(generator)

    assert result.raw_output == "fresh-1"
    assert generator.audited_cache_hits == 0
    assert len(generator.ambiguous_identities) == 1


def test_resume_preparation_preserves_interrupted_runs(tmp_path: Path) -> None:
    output = tmp_path / "benchmark"
    interrupted = output / "runs" / "spa" / "candidate.tmp"
    interrupted.mkdir(parents=True)
    (interrupted / "partial.txt").write_text("keep", encoding="utf-8")

    roots = _prepare_benchmark_output(output, resume=True)

    assert roots == [output / "resume_sources" / "attempt_001"]
    assert not (output / "runs").exists()
    assert (
        output
        / "resume_sources"
        / "attempt_001"
        / "runs"
        / "spa"
        / "candidate.tmp"
        / "partial.txt"
    ).read_text(encoding="utf-8") == "keep"
