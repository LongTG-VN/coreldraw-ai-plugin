# Design AI v0.3 — Stability / Release Audit

This document is the release-readiness companion to
`DESIGN_AI_V0_3_REFERENCE_RAG.md`. It records what is actually stable in v0.3,
what remains research-only, and which claims are intentionally **not** made.

## Release state

```text
Design AI v0.3 — Reference-Grounded Design RAG
status: verified clean research checkpoint
production_ready: false
commercial_allowed: false
next: v0.3.1 Visual Composition Engine
```

The machine-readable source of truth is
`training/config/releases/design_ai_v0_3.json`.

## Clean validation

The clean validation was rerun with 52 fresh model generations and zero reused
raw candidates. The model, checkpoint, 13 prompts, four candidates per prompt,
scorer and reference corpus were kept fixed.

| metric | v0.2 fair | v0.3 clean |
| --- | ---: | ---: |
| combined | 0.744974792 | 0.828603638 |
| technical | 0.580140556 | 0.863638563 |
| overlap | 0.041276800 | 0.000000000 |
| spacing | 0.875354372 | 0.885574350 |
| hierarchy | 0.663317341 | 0.689965230 |
| text fit | 0.456410256 | 0.942307692 |
| coverage | 0.457238988 | 0.317489274 |
| candidate diversity | 0.212174874 | 0.240638734 |
| strict schema validity | 1.0 | 1.0 |

Exact combined-score improvement: **+11.225728%**. All automatic success gates
passed. Average fresh candidate generation time was 54.211896 s and peak
inference VRAM was 1.445169 GiB on the measured local run.

## Generation identity and interrupted-run recovery

New benchmarks remain fresh by default. `GenerationIdentityV1` binds every raw
response to the original prompt hash, grounded prompt hash, reference-context
hash and ordered reference IDs, canvas, seed, complete sampling configuration,
model revision, and checkpoint content fingerprint. Saved responses also carry
a raw-output SHA-256 digest. Legacy four-field cache entries are rejected.

Resume is explicit and non-destructive:

```powershell
python -m training.tools.benchmark_reference_rag_safe `
  --checkpoint training/artifacts/runs/20260809_qwen3_1_7b_smoke/checkpoint-5 `
  --reference-index training/artifacts/reference_corpora/design_v0_3/reference_index.jsonl `
  --output training/artifacts/benchmarks/<interrupted-run> `
  --resume
```

The interrupted `runs/` tree is preserved under `resume_sources/attempt_NNN`.
Only candidates with complete artifacts, matching identity and raw-output
hashes, and the same model/checkpoint are accepted. Provenance separately
counts `fresh_generation`, `resumed_verified_candidate`, and
`audited_raw_cache_reuse` in `generation_provenance.json`. External reuse is
available only through the explicit `--audited-rag-cache-from` option; the old
`--reuse-rag-candidates-from` flag remains blocked.

## Important interpretation rules

### 1. Strict-valid does not mean raw-valid

All 52 clean candidates became valid `DesignDocument` instances after the
explicit parser/recovery path, but **0/52 raw model outputs directly validated
against the canonical schema**. Therefore:

```text
strict schema validity after recovery = 52/52
raw canonical schema validity          = 0/52
```

The recovery layer is a real part of v0.3 and must remain visible in reports.
Do not describe the current Qwen checkpoint as a canonical-schema-native model.

### 2. The v0.3 gain is RAG + deterministic postprocessing

The evaluated pipeline is:

```text
brief
-> reference retrieval / compact grounding
-> Qwen candidate
-> schema recovery when required
-> deterministic reference-layout guidance
-> deterministic typography fitting
-> heuristic critic / best-of-4 selection
```

The +11.225728% result is therefore **not** a pure RAG-only ablation. Future
research may separate RAG-only, postprocess-only and combined effects, but that
is not required to keep the v0.3 checkpoint valid.

### 3. Dense-menu values are synthetic placeholders

The current dense-menu structural regression can synthesize rows such as
`Món 01` and price-like values such as `39K` when the brief asks for a count but
does not provide real menu data. These values exist only to stress layout,
alignment and text fitting. They are **not customer-provided business data** and
must never be treated as production copy or pricing.

The release audit explicitly reports synthetic user-data elements and invented
synthetic value counts so this limitation cannot be hidden by aggregate scores.

### 4. Retrieval accuracy is optimistic by construction

The 165-reference corpus contains 65 project-owned structural templates covering
the same 13 benchmark categories, and retrieval prefers exact-category pools.
The observed 100% category/format accuracy therefore verifies deterministic
routing for the bounded benchmark; it does not prove general retrieval quality
over a large real company archive.

### 5. Coverage is the main current structural regression

Coverage falls from 0.457239 to 0.317489. Visual inspection is consistent with
this: v0.3 is cleaner and easier to read, but often too sparse and visually
underdeveloped. This is why the next milestone is visual composition rather
than more Qwen training.

## Runtime surface

The trained v0.3 path is currently exposed through the local/offline CLI:

```powershell
python training\tools\reference_rag.py `
  --checkpoint training\artifacts\runs\20260809_qwen3_1_7b_smoke\checkpoint-5 `
  --reference-index training\artifacts\reference_corpora\design_v0_3\reference_index.jsonl `
  --prompt "Thiết kế poster spa cao cấp" `
  --width-mm 108 --height-mm 135 `
  --output training\artifacts\runs\manual_v0_3_request
```

The root FastAPI `/api/v1/design/generate` endpoint still returns the
**deterministic baseline**, not the trained Qwen/RAG pipeline. This is deliberate
at the v0.3 research checkpoint and must be stated clearly in demos or reports.
Runtime API integration can be added later after the research path is promoted
and model/corpus lifecycle configuration is defined.

## Benchmark safety

The primary v0.3 benchmark entrypoint now rejects
`--reuse-rag-candidates-from`. The previous cache identity was not
prompt/context-aware and could collide across prompts sharing dimensions and
seeds. The implementation is retained internally for reproducibility, but the
public validation path requires fresh generation.

Run a clean benchmark with:

```powershell
python -m training.tools.benchmark_reference_rag `
  --checkpoint training\artifacts\runs\20260809_qwen3_1_7b_smoke\checkpoint-5 `
  --reference-index training\artifacts\reference_corpora\design_v0_3\reference_index.jsonl `
  --output training\artifacts\benchmarks\design_v0_3_clean
```

No reuse flag is accepted for release validation.

## Artifact-only stability audit

After a benchmark completes, audit it without loading Qwen or CUDA:

```powershell
python -m training.tools.audit_v03_release `
  --benchmark-root training\artifacts\benchmarks\20260809_design_v0_3_clean_validation `
  --output training\artifacts\benchmarks\20260809_design_v0_3_clean_validation\stability_audit.json
```

The audit checks:

- 13 benchmark rows and 52 candidates by default;
- required candidate artifacts;
- strict and raw schema validity separately;
- recovery count;
- positive generation durations;
- raw-generation reuse markers;
- synthetic user-data elements / invented synthetic values;
- automatic v0.3 success-gate result;
- the known coverage regression.

The audit may still classify v0.3 as a `stable_research_checkpoint` when raw
schema recovery or synthetic stress-test content exists; those are recorded
limitations, not hidden production claims. Any reused raw generation,
missing artifact, invalid candidate, non-positive generation duration, or failed
automatic gate makes the audit fail.

## Current capability assessment

```text
structured schema / Corel compile     strong
technical layout safety              strong
reference retrieval                  good for bounded corpus
text fitting                          strong for current benchmark
hierarchy                             improved, still heuristic
visual composition / branding        weak
raw schema adherence                  weak
production/commercial readiness       blocked
```

V0.3 is stable enough to serve as the baseline for the next research milestone.
It is not yet a production designer and must not be represented as one.

## Acceptance decision

```text
v0.3_complete: true
clean_validation_confirmed: true
stable_research_checkpoint: true
ready_for_v0.3.1_visual_composition: true
ready_for_v0.4_preference_training: false
production_ready: false
commercial_allowed: false
```

Do not start large-scale preference training from heuristic labels. The next
justified milestone is v0.3.1 visual composition: richer assets, typography,
brand treatment, decorative composition, campaign energy and category-aware
visual density while preserving v0.3 technical safety.
