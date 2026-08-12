# Pre-Codex Stabilization Freeze — 2026-08-12

## Purpose

This branch is the **safe handoff checkpoint** after the Antigravity research experiments and before Codex resumes work.

Do not start a new aesthetic/research milestone from this branch. The purpose of the branch is to preserve the verified Corel/API foundation while making later experimental code fail closed instead of silently fabricating evidence.

## Branch

- Stabilization branch: `stabilize/pre-codex-return-20260812`
- Base research commit: `028db5ead17dd2c3d54c5660ec85c5052f372d5c`
- Original research branch remains untouched: `agent/codex-training-bootstrap`
- Draft PR: `#5 [freeze] Pre-Codex stabilization checkpoint`

## Keep / Treat as Stable

Preserve these areas unless a concrete regression is demonstrated:

- Corel Design API control path
- transaction / rollback behavior
- real editable CDR save / reopen through the Corel API path
- PNG/PDF export through Corel
- `DesignDocument` and schema infrastructure
- v0.3.3 Asset-Aware Composition as the last clearly successful design-quality milestone
- human-review tooling and historical queues
- Qwen3-1.7B as the offline/local fallback planner

## Frozen / Do Not Resume Automatically

- v0.3.4 Hybrid Visual RAG — failed experiment
- v0.3.5 Vision Critic / Self-Refine — failed experiment
- Antigravity-vs-Qwen planner shootout — inconclusive; invalid historical runs exist
- Phase 1.3 manual "Gold" grammars — manually authored layout fixtures, not Gold references
- Phase 1.3b GenPoster reference pilot — research-only and rejected as a Gold-quality source set
- preference training — not ready
- private company archive ingestion — not started

## Stabilization Hardening Completed

### 1. Gold provenance now fails closed

`training/schemas/gold.py`

Unbound grammars now default to:

```text
license_class: UNKNOWN
commercial_allowed: false
project_owned: false
source: UNBOUND
```

No grammar is automatically treated as commercially usable or project-owned merely because project code created it.

### 2. Extractor inherits source rights instead of inventing them

`training/gold/extractor.py`

The extractor now inherits:

- source name/split/upstream ID,
- license class,
- commercial permission,
- explicit `project_owned` metadata.

It also avoids unsafe font-family assumptions and no longer hard-codes permissive provenance.

### 3. GenPoster is locked to research-only provenance

`training/gold/real_pipeline.py`

For this project:

```text
license_class: CC-BY-NC-4.0
commercial_allowed: false
project_owned: false
```

These values must not be widened by downstream code without a new source/license audit.

### 4. Automatic keyword-to-Gold discovery has been disabled

The previous implementation selected SALE/SPA candidates with broad text keywords. That path is no longer allowed for Gold extraction.

The stabilized pipeline separates:

```text
dataset candidate discovery
→ human source review
→ explicit approved-source manifest
→ extraction
```

`build_real_gold_library()` now requires exact approved source IDs from a human-curated manifest. Missing/unapproved manifests block the pipeline instead of falling back to heuristic selection.

### 5. Source approval is an explicit quality gate

A real-reference manifest entry must contain:

- `source_id`
- exact dataset `upstream_id`
- category
- `approved: true`
- `human_quality_status: APPROVED`

Without these fields the real-reference path stops.

This prevents another random/rejected source contact sheet from being treated as Gold.

### 6. Fake `.cdr` generation has been removed

Both:

- `training/evaluation/gold_grammar_pilot.py`
- `training/evaluation/real_gold_pilot.py`

previously wrote synthetic bytes to a file named `output.cdr`.

That mechanism has been removed.

Offline research runners now emit:

```text
corel_operations.json
cdr_request.json
```

with:

```text
status: NOT_GENERATED_REQUIRES_REAL_COREL_API
real_cdr_verified: false
```

A real `.cdr` claim now requires execution through the previously verified Windows/Corel Design API path.

### 7. Manual Phase 1.3 grammars are quarantined as fixtures

The 15 manually authored grammars are still useful for:

- schema regression,
- bounded adaptation regression,
- Corel operation compilation,
- contact-sheet tooling.

But the Phase 1.3 runner now reports:

```text
STRUCTURED_GRAMMAR_ADAPTATION_PILOT_ONLY
REGRESSION_FIXTURE_ONLY
human_review_ready: false
real_gold_reference_count: 0
real_cdr_verified: false
commercial_allowed: false
```

It no longer creates a human-preference queue.

### 8. FixtureQwenPlanner is no longer silently presented as a real baseline

The manual pilot keeps `FixtureQwenPlanner` only for regression context and labels it explicitly as a fixture.

The real-reference pilot accepts an optional baseline planner. If the baseline is a fixture, it is not eligible for a real human baseline claim.

### 9. Gold adaptation metrics no longer fabricate perfect scores

`training/gold/adapter.py`

The old adapter hard-coded values such as:

```text
alignment_preservation_rate = 1.0
spacing_preservation_rate = 1.0
hierarchy_preservation_rate = 1.0
grammar_deviation_score = 0.05
```

The stabilized adapter:

- computes slot-fill and relationship preservation from actual filled slots,
- reports exact normalized-geometry deviation as `0.0` when geometry is copied unchanged,
- reports unimplemented independent metrics as `null` instead of inventing `1.0`,
- does not fake a logo by rendering the business name into a LOGO slot.

### 10. Tests are hermetic

`tests/test_real_gold_grammar.py` now builds a small temporary dataset and approved manifest fixture.

GitHub CI no longer depends on ignored local GenPoster files and now verifies:

- source discovery does not auto-approve,
- missing/unapproved manifests fail closed,
- GenPoster rights remain research-only,
- exact approved-source extraction works,
- no fake `.cdr` is written,
- pilot blocks before generation without source approval.

`tests/test_research_integrity_guards.py` prevents the known fake-CDR magic headers and permissive GenPoster rights from being reintroduced.

## Historical Artifacts

Do not delete historical Antigravity artifacts. They are useful as negative experiments and implementation history.

But do not interpret old files containing labels such as:

```text
REAL_GOLD_PIPELINE_VERIFIED
commercial_allowed: true
output.cdr
```

as current truth. Historical artifacts may predate the stabilization fixes above.

## Current Safe Status

```text
corel_api_stable: true
real_corel_cdr_roundtrip_previously_verified: true
v0_3_3_asset_aware_stable: true
qwen_fallback_preserved: true

v0_3_4_visual_rag_enabled: false
v0_3_5_vision_critic_enabled: false

manual_gold_is_real_gold: false
manual_gold_human_review_ready: false

real_gold_requires_approved_manifest: true
genposter_commercial_allowed: false
genposter_project_owned: false
real_gold_source_quality_approved: false
real_gold_real_cdr_verified: false

preference_training_ready: false
production_ready: false
research_frozen_for_codex_review: true
```

## Codex Resume — Recommended Order

When Codex has budget again:

1. check out this stabilization branch and verify the latest CI matrix is green;
2. audit the diff in Draft PR #5 before merging anything back to the research branch;
3. preserve the verified Corel/API and v0.3.3 path;
4. decide whether to keep or further simplify the quarantined Phase 1.3/1.3b research runners;
5. build a tiny source-curation workflow for **company-owned** CDR files;
6. use only 5–10 explicitly human-approved company designs for the next Gold extractor test;
7. require real Corel API save/reopen for every future `.cdr` claim;
8. only after candidate quality improves should preference training resume.

## Best Next Research Input

Do not scan the full private archive.

Preferred next input is a tiny curated set such as:

```text
5 good SALE CDR files
5 good SPA CDR files
```

Each source should be something a human would accept as a quality target before the extractor sees it.

## Stop Rule

Until Codex resumes:

- no new planner experiments,
- no new VLM/RAG experiments,
- no preference training,
- no large candidate generation,
- no private archive bulk ingestion,
- no automatic Gold promotion,
- no research-success claims from Antigravity alone.

This branch should remain boring, reproducible, conservative, and easy for Codex to audit.
