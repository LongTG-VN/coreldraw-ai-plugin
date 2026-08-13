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

The following historical research runners previously manufactured bytes and saved them with a `.cdr` extension:

- `training/evaluation/gold_grammar_pilot.py`
- `training/evaluation/real_gold_pilot.py`
- `training/evaluation/planner_shootout.py`
- historical real-planner pilot code

The stabilized offline artifact runners no longer do that.

Where a future CDR would be needed, they emit a request marker such as:

```text
status: NOT_GENERATED_REQUIRES_REAL_COREL_API
real_cdr_verified: false
```

A real `.cdr` claim requires execution through the previously verified Windows/Corel Design API path.

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

`tests/test_real_gold_grammar.py` now builds a small temporary dataset and approved-manifest fixture.

GitHub CI no longer depends on ignored local GenPoster files and verifies:

- source discovery does not auto-approve,
- missing/unapproved manifests fail closed,
- GenPoster rights remain research-only,
- exact approved-source extraction works,
- no fake `.cdr` is written,
- pilot blocks before generation without source approval.

`tests/test_research_integrity_guards.py` prevents known fake-CDR magic headers and permissive GenPoster rights from being reintroduced.

### 11. The first planner shootout is explicitly a fixture smoke

`training/evaluation/planner_shootout.py`

The original 40-candidate benchmark used deterministic Qwen/Antigravity adapters. It is now explicitly classified as:

```text
DETERMINISTIC_ADAPTER_FRAMEWORK_SMOKE
NOT_VALID_FOR_AI_PLANNER_COMPARISON
```

It can still exercise:

- the shared planner contract,
- content locks,
- preview generation,
- Corel-operation compilation,
- artifact layout.

It no longer:

- creates a blind human-review queue,
- claims an AI-vs-AI comparison,
- writes fake `.cdr` files,
- marks fixture outputs as commercially usable.

### 12. The "real planner" pilot is frozen behind a provenance gate

`training/evaluation/real_planner_audit.py`

A historical bug remained after the first audit:

- `RealQwenDesignPlanner` could invoke a model but still return a structured design originating from a fixture path;
- `RealAntigravityDesignPlanner` could construct a reasoning-looking JSON string locally and mark `real_agent_planning = true` without proving an external Antigravity execution.

The v2 audit therefore requires more than non-empty raw output or a model/agent-looking class name.

For Qwen, a valid run must prove:

```text
real_model_invoked = true
design_plan_derived_from_ai_output = true
no fixture / historical fallback
fresh raw output exists
content lock valid
```

For Antigravity, a valid run must additionally prove:

```text
real_agent_planning = true
external_execution_verified = true
design_plan_derived_from_ai_output = true
synthetic_reasoning_trace = false
```

The current wrappers do not satisfy those requirements. Therefore the benchmark defaults to:

```text
PLANNER_SHOOTOUT_FROZEN
benchmark_valid: false
human_review_ready: false
```

and does not generate candidates or review queues.

### 13. Nonce echo is no longer accepted as Antigravity provenance

`training/evaluation/final_provenance_audit.py`

The historical final audit treated a fresh nonce appearing in a response as evidence of a fresh Antigravity execution. That is insufficient because a deterministic local adapter can echo the same nonce.

The final audit now delegates to the v2 provenance gate and records:

```text
historical_nonce_probe_policy: NOT_SUFFICIENT_EVIDENCE
historical_candidate_outputs_accepted_as_fresh_proof: false
```

It defaults to `execute = false`. Codex must explicitly opt into a live audit once a genuine execution bridge exists.

## Historical Artifacts

Do not delete historical Antigravity artifacts. They are useful as negative experiments and implementation history.

But do not interpret old files containing labels such as:

```text
REAL_GOLD_PIPELINE_VERIFIED
REAL_PLANNER_SHOOTOUT_VALID
REAL_PLANNER_PROVENANCE_VERIFIED
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

deterministic_planner_shootout_valid_as_ai_comparison: false
real_planner_shootout_frozen: true
antigravity_external_execution_verified: false
qwen_design_plan_ai_derivation_verified_in_shootout_wrapper: false

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
4. decide whether to delete, keep, or rebuild the quarantined planner wrappers — do **not** unfreeze the shootout until `DesignPlanV2` is demonstrably derived from real AI outputs;
5. keep Phase 1.3 manual grammar code only as regression tooling;
6. build a tiny source-curation workflow for **company-owned** CDR files;
7. use only 5–10 explicitly human-approved company designs for the next Gold extractor test;
8. require real Corel API save/reopen for every future `.cdr` claim;
9. only after candidate quality improves should preference training resume.

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

## Codex Resume Audit — 2026-08-13

Codex resumed from exact stabilization SHA
`abe283b5281551d487cd3b85b1bf85ba26de17ac`, audited Draft PR #5 and the
stabilization diff, and reran the hermetic suite before company-data work. The
baseline was clean and all 272 existing tests passed.

One real-runtime defect was found during the resumed Corel audit: the bridge set
`Document.Unit = 4` while describing that value as millimetres. In the CorelDRAW
2020 automation enum, millimetres are value `3`; value `4` is centimetres. The
bridge and regression test now use `3`.

A real CorelDRAW 2020 smoke then passed snapshot, editable object creation,
mutation, transaction commit, intentional rollback, real Corel `SaveAs`,
close/open, post-reopen text/vector mutation, current save, PNG export, and PDF
export. No synthetic bytes were written to a `.cdr` file.

The new `training.company_archive` package is a conservative bootstrap only. It
provides read-only/resumable inventory, staged hashes, verified duplicate
grouping, bounded previews, human-only Gold curation, safe Corel inspection, and
a page-one CDR-to-`DesignDocument` prototype. It has not scanned the private 800
GB archive. Its live smoke used only a project-created Corel CDR, not a company
sample. See `docs/COMPANY_CDR_ARCHIVE_PIPELINE.md`.

Current resume status:

```text
stabilization_audit_passed: true
real_corel_runtime_verified: true
company_archive_full_scan_started: false
company_cdr_sample_supplied: false
company_gold_promoted: false
preference_training_started: false
status: WAITING_FOR_COMPANY_CDR_SAMPLE
```
