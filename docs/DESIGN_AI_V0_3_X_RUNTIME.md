# Design AI v0.3.x local trained runtime

This runtime exposes the research-only Qwen3 planner without changing the lightweight
deterministic endpoint. It is intended for a single local GPU process and serializes
generation so only one Qwen session owns VRAM.

## Compatibility boundary

- `POST /api/v1/design/generate` remains the existing deterministic baseline and returns
  `trained_model: false`.
- `GET /api/v1/design/model/status` reports configuration and file availability without
  importing or loading the model.
- `POST /api/v1/design/generate-trained` lazy-loads the pinned checkpoint on its first
  request and reuses that session for later requests.
- CI and CPU-only installs do not need a GPU, checkpoint, Transformers, PEFT, or
  bitsandbytes unless the trained endpoint is called.

The pinned identity is:

- model: `Qwen/Qwen3-1.7B`
- revision: `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`
- adapter: `training/artifacts/runs/20260809_qwen3_1_7b_smoke/checkpoint-5`
- reference index: `training/artifacts/reference_corpora/design_v0_3/reference_index.jsonl`
- license state: `research_only: true`, `commercial_allowed: false`

## Local configuration

All paths are resolved below the repository unless an absolute local path is supplied.
The API never accepts arbitrary checkpoint or index paths from the request body.

| Variable | Default |
| --- | --- |
| `DESIGN_AI_TRAINED_ENABLED` | `auto` |
| `DESIGN_AI_CHECKPOINT` | pinned `checkpoint-5` path above |
| `DESIGN_AI_REFERENCE_INDEX` | pinned v0.3 index above |
| `DESIGN_AI_MODEL_CONFIG` | `training/config/experiments/qwen3_1_7b_local_qlora.json` |
| `DESIGN_AI_SCORE_CONFIG` | `training/config/scoring/aesthetic_v0_3.json` |
| `DESIGN_AI_RUNTIME_ARTIFACT_ROOT` | `training/artifacts/runtime/trained` |
| `DESIGN_AI_CONTEXT_TOKEN_BUDGET` | `350` |
| `DESIGN_AI_MAX_NEW_TOKENS` | `512` |
| `DESIGN_AI_VISUAL_RAG_ENABLED` | `false` (failed v0.3.4 research path; explicit opt-in only) |

The v0.3.4 visual retriever is preserved for controlled ablations but is not
enabled by default because it failed its frozen quality gates. The v0.3.5
vision critic is a standalone research tool and is also not part of this
runtime path.

## Requests

Status is a cheap readiness probe:

```http
GET /api/v1/design/model/status
```

`loaded: false` is normal before the first generation. `available: false` includes a
stable unavailable state such as a missing checkpoint or reference index.

Generation accepts bounded product inputs only:

```http
POST /api/v1/design/generate-trained
Content-Type: application/json

{
  "prompt": "Thiết kế poster spa cao cấp màu kem và vàng",
  "width_mm": 210,
  "height_mm": 297,
  "num_candidates": 4,
  "seed": 4200,
  "reference_top_k": 5
}
```

The response contains the strict `DesignDocument`, editable Corel operations, ranking,
winner metrics, references, local run ID, and explicit research-only flags. A missing
runtime returns HTTP 503 with `trained_design_unavailable`; a generation failure returns
HTTP 500 with `trained_design_generation_failed`. Neither error disables the baseline
endpoint.

## Artifact and provenance contract

Each trained request writes a unique directory under the configured artifact root:

```text
trained-<utc>-<id>/
  request.json
  brief.json
  retrieval.json
  reference_context.json
  candidates/
  ranking.json
  performance.json
  final/design.json
  final/preview.png
  final/corel_operations.json
  run_manifest.json
```

`run_manifest.json` records prompt/checkpoint/reference-index hashes, exact model
revision, seeds, top-k, visual and critic versions, winner, duration, and license state.
Text invented by the model is marked `model_generated_copy`. Missing menu, discount,
offer, or date values are explicit editable placeholders with `requires_user_data: true`;
they are never represented as customer-provided facts.

## Operational limits

- The service is local and synchronous; concurrent calls queue behind one lock.
- Raw Qwen output still needs deterministic schema recovery.
- The corpus includes GenPoster CC-BY-NC-4.0 structural references, so generated
  checkpoint results are not production/commercial approved.
- The critic is heuristic. It is not a human aesthetic preference or a vision model.
- Human review is required before preference training or any visual-quality claim.
