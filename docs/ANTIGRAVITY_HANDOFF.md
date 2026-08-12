# Antigravity Handoff

> **READ THESE FIRST**
>
> 1. `docs/ANTIGRAVITY_HANDOFF.md`
> 2. `docs/ANTIGRAVITY_DESIGN_AGENT_RULES.md`
> 3. `docs/DESIGN_API_REFERENCE.md`
> 4. `docs/LOCAL_COREL_RUNBOOK.md`
>
> Do not enable v0.3.4 or v0.3.5 by default. Do not train v0.4 yet. Do not
> bypass the Design API for routine Corel mutations.

## Start here

This repository is a local Windows AI-assisted CorelDRAW design system. Its
goal is not merely to generate preview images: structured planners produce
editable operations, Python safely owns Corel COM, and CorelDRAW produces an
editable `.cdr` plus optional PNG/PDF derivatives.

## Current checkpoint

- Branch: `agent/codex-training-bootstrap`
- Starting handoff SHA: `5955dd246b854b13374519d9f9055e266400230e`
- Final SHA: resolve with `git rev-parse HEAD` after checkout; it is also
  recorded in `docs/CODEX_TO_ANTIGRAVITY_FINAL_HANDOFF_REPORT.md` and the final
  Codex message because a commit cannot contain its own SHA.
- Stable Design AI milestone: v0.3.3 Asset-Aware Composition.
- v0.3.4 Hybrid Visual RAG: failed research, code preserved, runtime off by default.
- v0.3.5 Vision Critic + Self-Refine: failed research, standalone code preserved, not in default runtime.
- v0.4 Phase 1.2: engineering complete; `WAITING_FOR_CATEGORY_PILOT_HUMAN_REVIEW`.

## Project goal

```text
human / Antigravity brief
→ structured planner / DesignDocument
→ validated Corel transaction operations
→ serialized Python COM bridge
→ CorelDRAW editable objects
→ editable CDR (primary)
→ PNG preview / PDF export (derivatives)
```

Text should remain text, shapes remain vectors, and imported assets remain
independent objects. Whole-page rasterization is not the product output.

## Architecture

| Responsibility | Actual implementation |
|---|---|
| Canonical design schema | `training/schemas/design.py` (`DesignDocument`, elements, typography, visual/asset specs) |
| Deterministic baseline | `training/inference/baseline.py` |
| Qwen planner/runtime | `training/inference/qwen3_planner.py`, `training/inference/service.py` |
| Design→Corel compiler | `training/inference/corel_compiler.py` |
| Research preview renderer | `training/inference/preview.py` |
| HTTP orchestration | `main.py` |
| COM ownership/primitive creation | `corel_bridge.py` (`CorelDrawBridge`, singleton `corel_bridge`) |
| High-level object mutation/check/undo | `design_bridge.py` (`DesignBridge`) |
| Grouped transaction/rollback | `transaction_engine.py` (`DesignTransactionEngine`) |
| Outline/group/PNG/PDF | `extended_bridge.py` |
| Safe CDR lifecycle | `document_io.py` (`DocumentIOService`) |
| Template workflow | `template_engine.py`, `template_models.py`, `templates/manifests/` |
| Blinded human review | `training/preference/v04/`, `training/tools/human_review_server.py` |

FastAPI sync endpoints execute in worker threads. `CorelDrawBridge.session()`
initializes that thread's COM apartment and holds a process-local `RLock`, so
one Python process serializes document access. Do not run competing API/COM
controllers against the same active document.

## What is stable

- Strict canonical DesignDocument validation and deterministic Corel compiler.
- v0.3.3 authorized/project-owned asset-aware composition research checkpoint.
- Corel primitives, object inspection, transformations, typography, order,
  alignment/distribution, fitting/PowerClip, import, check, undo, and grouped
  transactions.
- Safe absolute-path CDR save/save-as/open and PDF/PNG export.
- Real Corel 2020 round-trip: vector rectangle, ellipse, editable text, CDR
  save-as, close/open, post-open mutation/save, PNG, and PDF all passed.
- Local blinded review UI, immutable human-source enforcement, provenance,
  queues, exporter, and Phase 1.2 category pilot.

## What failed

### v0.3.4

Hybrid visual retrieval was technically implemented but failed frozen quality
gates (`VISUAL_RETRIEVAL_NOT_USEFUL`). Its embedding/index/leakage abstractions
are preserved for ablation work. `DESIGN_AI_VISUAL_RAG_ENABLED` defaults to
`false`; do not enable it for normal generation.

### v0.3.5

The local VLM critic/refiner was technically safe but inconsistent and failed
its quality gate (`VISION_CRITIC_NOT_RELIABLE`). Its schemas, bounded refinement,
and rollback code are preserved. It is not wired into the default runtime and
must never be presented as human preference.

## Current human-review state

Historical aggregate: 64 real human decisions, 14 A wins, 10 B wins, 3 ties,
37 both-bad, and 0 automated preference labels. Provenance reconstructs these
as 44 legacy/diagnostic and 20 Phase 1.1 pilot reviews—not Phase 1.2 results.
The isolated Phase 1.2 SALE/SIGNAGE/SPA queue has 12 pairs and is waiting for a
real reviewer. Therefore:

```text
ready_for_preference_training: false
preference_model_trained: false
v0.4_complete: false
```

## Corel output

1. `POST /api/v1/design/transaction` creates/mutates editable objects.
2. `POST /api/v1/design/check` and `/render-preview` or safe `/export` verify.
3. `POST /api/v1/design/save-as` writes the first `.cdr` with no overwrite by default.
4. `POST /api/v1/design/save` saves an already named active CDR.
5. `POST /api/v1/design/open` reopens a CDR.
6. `POST /api/v1/design/export` writes PNG/PDF derivatives.

Exact requests are in `docs/LOCAL_COREL_RUNBOOK.md`.

## Design API

The complete route/operation inventory, schemas, failure semantics, object IDs,
and examples are in `docs/DESIGN_API_REFERENCE.md`.

## Agent rules

Mandatory Antigravity control, business-data, transaction, COM, file, license,
and research-default rules are in `docs/ANTIGRAVITY_DESIGN_AGENT_RULES.md`.

## How to start local services

Corel API:

```powershell
cd D:\codex\coreldraw-ai-plugin
python -m pip install -r requirements.txt
python main.py
```

Swagger: `http://127.0.0.1:8001/docs`.

Phase 1.2 blinded review only:

```powershell
python -m training.tools.human_review_server `
  --queue v04_phase1_2_category_pilot --port 8004
```

Review: `http://127.0.0.1:8004/review`.

## How to connect Corel

- Run Windows and install matching-bitness Python + `pywin32` and CorelDRAW.
- Open CorelDRAW visibly.
- Start one API process.
- POST `/api/v1/corel/connect`, then inspect `/api/v1/design/snapshot` and verify
  the active document before mutation.
- Follow `docs/LOCAL_COREL_RUNBOOK.md` for create/check/save/reopen/undo.

## How to run tests

```powershell
python -m compileall -q training tests
python -m pytest -q
git diff --check
```

CI uses Python 3.10/3.11/3.12 and must not require Corel COM, CUDA, checkpoints,
downloaded models/assets, or human review records.

## Local data and artifact locations

These paths are intentionally ignored and must be preserved:

- `training/artifacts/`: runs, checkpoints, benchmarks, handoff smoke artifacts.
- `training/data/`: research data, local assets, human preferences.
- `training/workspace/`: generated workspace/caches.
- configured Hugging Face/model cache locations.
- v0.3.3 local real-asset benchmark roots.

Do not `git clean` them. Human review JSONL is user data, not disposable output.

## Models

- Offline/local fallback planner: `Qwen/Qwen3-1.7B`, revision
  `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`.
- Default adapter convention:
  `training/artifacts/runs/20260809_qwen3_1_7b_smoke/checkpoint-5`.
- Structural reference convention:
  `training/artifacts/reference_corpora/design_v0_3/reference_index.jsonl`.
- The checkpoint/reference lineage contains GenPoster CC-BY-NC-derived data,
  so it is research-only and not commercially approved.
- v0.3.4 SigLIP2 visual embedding and v0.3.5 Qwen3-VL critic are failed research
  experiments, opt-in/standalone only.

## What Antigravity may modify

- Review UI and audit tooling.
- API wrappers/documentation.
- Easy/medium correctness and maintenance bugs.
- Tested design operations and Corel workflows.
- Candidate generation/benchmark utilities within existing safety contracts.

## What requires extra caution

- COM ownership and concurrency.
- Transaction rollback guarantees.
- DesignDocument and request/response schema compatibility.
- Save/open/export paths and overwrite semantics.
- Qwen/CUDA lazy loading and model identity.
- Human review persistence/provenance and source enforcement.
- Dataset, model, reference, and asset license metadata.

## Do not do

- Do not force push, reset/clean user artifacts, delete datasets/checkpoints, or
  overwrite human reviews.
- Do not claim failed research passed or enable v0.3.4/v0.3.5 by default.
- Do not train preference models before a future human gate explicitly passes.
- Do not invent customer/business data.
- Do not use GUI automation or arbitrary direct COM for routine mutations.
- Do not call the current research pipeline production/commercial ready.

## Next recommended work

1. Learn the repository through these handoff documents.
2. Verify local Corel control and perform easy/medium maintenance through the Design API.
3. Later, run a controlled Antigravity/Gemini-style planner versus Qwen benchmark.

Do not start the planner benchmark merely by reading this handoff.
