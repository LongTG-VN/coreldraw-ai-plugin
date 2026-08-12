# Pre-Codex Stabilization Freeze — 2026-08-12

## Purpose

This branch is a **freeze/stabilization checkpoint** created after the Antigravity research experiments and before Codex resumes work.

Do not start new research milestones from this branch until the known issues below are reviewed. The goal is to preserve working Corel/API infrastructure while quarantining research claims that were not adequately validated.

## Branch

`stabilize/pre-codex-return-20260812`

Base research commit:

`028db5ead17dd2c3d54c5660ec85c5052f372d5c`

Original research branch remains untouched:

`agent/codex-training-bootstrap`

## Keep / Treat as Stable

The following areas were already verified before the later research experiments and should be preserved unless a regression is demonstrated:

- Corel Design API control path
- transaction / rollback behavior
- editable CDR save / reopen via the real Corel API path
- PNG/PDF export through Corel
- DesignDocument / schema infrastructure
- v0.3.3 Asset-Aware Composition as the last clearly successful design-quality milestone
- human review tooling and queue infrastructure
- Qwen3-1.7B local planner as an offline fallback; do not remove it

## Research Freeze

Do **not** continue or claim success for the following until Codex re-audits them:

- v0.3.4 Hybrid Visual RAG — failed experiment
- v0.3.5 Vision Critic / Self-Refine — failed experiment
- Antigravity-vs-Qwen planner shootout — inconclusive / invalid historical runs exist
- Phase 1.3 manual "Gold" grammars — manually authored templates, not extracted Gold references
- Phase 1.3b GenPoster "Real Gold" pilot — quarantined pending source-quality, license, renderer, and real-CDR review

## Known Phase 1.3b Problems

### 1. GenPoster licensing metadata is currently wrong

`training/gold/real_pipeline.py` and `training/evaluation/real_gold_pilot.py` currently use values such as:

- `license_class = "CC0_or_project_owned"`
- `project_owned = True`
- `commercial_allowed = True`

for samples discovered from the GenPoster research dataset.

These values must **not** be trusted. The GenPoster research source was previously treated as non-commercial/research-only in this project. Until Codex verifies the exact source/license record, treat all Phase 1.3b GenPoster-derived grammars and outputs as:

- research-only
- `commercial_allowed = false`
- not project-owned

### 2. Source quality gate failed visually

The generated source contact sheet showed severe typography/layout problems, including narrow character-by-character wrapping, overlap, broken hierarchy, and oversized glyphs.

The current source set is **not human-certified Gold** and should not be used to claim aesthetic improvement.

Before future Gold extraction:

1. render the source faithfully,
2. human-review the source itself,
3. only extract from approved references.

### 3. Phase 1.3b runner writes a fake `.cdr` placeholder

`training/evaluation/real_gold_pilot.py` currently creates `output.cdr` with synthetic bytes instead of invoking the real Corel save/export path.

Therefore Phase 1.3b's generated `output.cdr` files are **not evidence of editable CorelDRAW output**.

Do not reuse this placeholder mechanism in future milestones. A real CDR claim requires the verified Design API/Corel round-trip path.

### 4. Baseline is a fixture planner

Phase 1.3b currently uses `FixtureQwenPlanner()` as its baseline. It must not be described as a genuine current Qwen inference or as a clean v0.3.3 model comparison without further validation.

### 5. Provenance audit is too weak

The current provenance audit mainly checks that IDs/hashes are non-empty and performs a narrow literal-content check. It does not fully prove:

- source hash recomputation against the original dataset entry,
- high visual quality,
- correct renderer fidelity,
- commercial rights,
- real Corel CDR creation.

`REAL_GOLD_PIPELINE_VERIFIED` should therefore be treated as a historical implementation status, **not** as proof that the Gold hypothesis succeeded.

### 6. Source category discovery is heuristic and too broad

The SPA discovery keywords include broad terms such as `lorem`, `fashion`, `design`, `art`, and `style`, which can select unrelated layouts. Future source selection should require explicit approved source IDs or a human-curated manifest.

### 7. CI depended on an ignored local dataset

The Phase 1.3b tests directly required:

`training/data/research/genposter_smoke_100/train.jsonl`

which is absent on GitHub-hosted runners. The stabilization branch changes these integration-style tests to skip when the optional dataset is unavailable. They must later be refactored to use explicit fixtures or a separate integration test target.

## Current Safe Research Status

Use these labels until Codex returns:

```text
corel_api_stable: true
real_corel_cdr_roundtrip_previously_verified: true
v0_3_3_asset_aware_stable: true
qwen_fallback_preserved: true

phase_1_3_manual_gold_valid_as_gold: false
phase_1_3b_genposter_gold_quality_approved: false
phase_1_3b_commercial_allowed: false
phase_1_3b_real_cdr_verified: false
phase_1_3b_ready_for_human_adaptation_review: false

preference_training_ready: false
production_ready: false
research_frozen_for_codex_review: true
```

## Codex Resume Checklist

When Codex has token budget again, start from this stabilization branch and do the following before any new aesthetic milestone:

1. run full tests and CI and establish a clean green baseline;
2. fix GenPoster license/provenance metadata to exact, conservative values;
3. remove/rename the fake `.cdr` placeholder path and require real Corel integration for CDR claims;
4. replace dataset-dependent unit tests with small committed fixtures or a separate optional integration suite;
5. quarantine or tighten the broad source-discovery heuristics;
6. downgrade historical Phase 1.3b success flags to reflect source-quality and provenance limitations;
7. only then resume Gold Design work using a tiny human-approved source set, preferably company-owned CDR designs.

## Stop Rule

Until Codex resumes:

- no new planner experiments,
- no new VLM/RAG experiments,
- no preference training,
- no large candidate generation,
- no private archive ingestion,
- no automatic Gold promotion,
- no research-success claims from Antigravity alone.

This branch exists to be boring, reproducible, and safe.
