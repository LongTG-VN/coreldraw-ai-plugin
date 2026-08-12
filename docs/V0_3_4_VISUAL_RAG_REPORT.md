# Design AI v0.3.4 — Hybrid Visual RAG Report

## RESULT

- Started: `2026-08-12T09:30:00+07:00` (implementation session)
- Completed: `2026-08-12T11:05:38+07:00`
- Duration: approximately 1 hour 35 minutes
- Outcome: the local visual-index and hybrid-retrieval architecture is implemented
  and verified, but its research quality gate failed on the current 165-reference
  corpus.
- Qwen retrained: `false`
- Human preference collected: `false`

## GIT

- Starting SHA: `0702fc781bf9234d36a5aec7ba76105bd68a6b7c`
- Implementation commit: `cc3df43d3b0409f7c1637e7d8bb2986247c92295`
- Branch: `agent/codex-training-bootstrap`
- Remote: `origin/agent/codex-training-bootstrap`
- Local index, cache, model weights, and benchmark images remain ignored artifacts.

## VISUAL EMBEDDING MODEL

- Selected model: `google/siglip2-base-patch16-224`
- Revision: `75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2`
- License: Apache-2.0
- Dimension: 768
- Input: RGB, EXIF-transposed, processor-defined 224-pixel preprocessing
- Text input: tokenizer/processor, fixed maximum 64 tokens with truncation
- Device: RTX 3060 Laptop GPU / CUDA FP16
- Peak measured VRAM: `0.726162 GiB`
- Cold model-load time: `15.21–16.31 s`
- Mean full-corpus retrieval latency after load: `1.854851 s/query`
- Mean query embedding time: `0.139870 s/query`

SigLIP2 was selected because it supplies compatible multilingual image/text
embeddings, has an explicit Apache-2.0 license, and fits comfortably on the 6 GB
GPU. The alternative inspected was `openai/clip-vit-base-patch32`, revision
`3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268` (512 dimensions, MIT). It was not
downloaded because its model card identifies English as the intended language;
the final briefs are primarily Vietnamese. Only one large embedding model was
downloaded.

## VISUAL INDEX

- References: `165` (`100` GenPoster-derived + `65` project-owned templates)
- Previews embedded: `165`
- Missing previews: `0`
- Index ID: `design_v0_3_4_visual:999fef359212b151`
- Fingerprint: `999fef359212b151863bd8a3482b330dff6955f2be212bbb2217c07d46c72c42`
- Cache identity: source SHA-256 + model ID + exact revision + preprocessing ID
- Cache: `54` hits, `111` misses
- Build time: `27.713174 s`
- Embedding time: `23.422963 s`
- Representation: deterministic JSONL metadata plus portable little-endian
  float32 vectors; brute-force cosine search.

## HYBRID RETRIEVAL

- Frozen weights: structural `0.35`, visual-text `0.50`, visual-asset `0.15`
- Calibration: five development briefs excluded from the final 18 queries
- MMR lambda: `0.70`
- Near-duplicate cosine threshold: `0.985`
- Top-K: `5`
- Planner context token budget: `500`
- Query modes: brief-only and brief + supplied hero/product assets
- Exact-category hard filter: removed; category is a structural feature only
- Leakage controls: reference ID, source ID, template family, preview SHA-256,
  and query-asset embedding near-duplicate exclusion
- Qwen receives only compact measurable summaries, never preview pixels.

The asset coefficient is renormalized out for brief-only requests. Runtime
loading is lazy and independently reports planner model, visual model,
structural index, and visual index status. If the optional visual stack or index
is unavailable, the existing structural retriever remains the compatible
fallback.

## RETRIEVAL EVALUATION

The benchmark contains 13 existing briefs and five v0.3.3 real-asset cases.
Metrics below are Top-5 means. `retrieval quality` is a frozen comparison measure
of `0.5 × structural relevance + 0.5 × visual-text relevance`; it is not a human
aesthetic score.

| Corpus mode | Method | Structural | Visual text | Retrieval quality | Category | Format | Diversity | Source diversity |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Full | structural | 0.743066 | 0.531768 | 0.637417 | 1.000000 | 1.000000 | 0.466367 | 0.200000 |
| Full | hybrid | 0.712113 | 0.533037 | 0.622575 | 0.888889 | 1.000000 | 0.352985 | 0.277778 |
| No exact-category project templates | structural | 0.386243 | 0.531546 | 0.458894 | 0.000000 | 0.722222 | 0.685236 | 0.366667 |
| No exact-category project templates | hybrid | 0.366726 | 0.536636 | 0.451681 | 0.000000 | 0.644444 | 0.485669 | 0.400000 |
| GenPoster only | structural | 0.337055 | 0.531187 | 0.434121 | 0.000000 | 0.555556 | 0.718742 | 0.200000 |
| GenPoster only | hybrid | 0.330492 | 0.536132 | 0.433312 | 0.000000 | 0.555556 | 0.418156 | 0.200000 |
| Leave category-template family out | structural | 0.386243 | 0.531546 | 0.458894 | 0.000000 | 0.722222 | 0.685236 | 0.366667 |
| Leave category-template family out | hybrid | 0.366726 | 0.536636 | 0.451681 | 0.000000 | 0.644444 | 0.485669 | 0.400000 |

Full-corpus hybrid deltas:

- structural relevance: `-0.030952`
- visual-text similarity: `+0.001269`
- retrieval quality: `-0.014842`
- category accuracy: `-0.111111`
- diversity: `-0.113382`
- source diversity: `+0.077778`

The five asset queries have mean selected-reference asset similarity
`0.757552`. This does not rescue retrieval quality: the retrieved geometry and
style are not materially better. No near-duplicate asset/reference exceeded the
`0.985` threshold; other held-out exclusions were still recorded.

All three frozen gates failed:

- full retrieval quality improved: `false`
- held-out retrieval quality improved: `false`
- meaningful visual gain (at least `+0.01`): `false`

Removing exact-category templates still collapses structural relevance from
`0.712113` to `0.366726`. Visual-text similarity stays numerically stable but is
too weakly discriminative to recover useful art direction.

## RETRIEVAL CONTACT SHEET

- Root: `training/artifacts/benchmarks/20260812_design_v0_3_4_visual_rag/`
- Contact sheet: `retrieval_contact_sheet_all.png`
- Rows: `retrieval_rows.json` and `benchmark_rows.json`
- Summary: `retrieval_summary.json` and `benchmark_summary.json`
- Per-query HTML and Top-5 sheets: `retrieval_review/<query_id>/`

Visual inspection agrees with the metrics: hybrid results still cycle through
the same small set of flat deterministic templates and sometimes introduce
public posters with irrelevant visible text. The references do not feel more
style-matched or less template-like.

## SMALL FRESH SMOKE

- Planned: five cases × two fresh Qwen candidates
- Run: `false`
- Fresh candidates: `0`
- Unsafe reuse: `0`

The requirement explicitly says not to spend generation time when retrieval
already fails its credibility gate. Running Qwen would confound a failed
retrieval experiment with planner sampling and would not establish a valid
v0.3.4 improvement.

## FULL BENCHMARK

- Run: `false`
- Fresh candidates: `0`
- Resume candidates: `0`
- Unsafe raw-output reuse: `0`

The 52-candidate benchmark condition was not met because the smaller retrieval
gate failed before generation.

## TECHNICAL SAFETY

- `python -m compileall -q training tests`: pass
- `python -m pytest -q`: `186 passed`, one existing Starlette deprecation warning
- `git diff --check`: pass
- Runtime visual model lifecycle: lazy and GPU-free under unit tests
- Structural-only RAG compatibility: preserved
- Missing/corrupt image behavior: explicit failure/fallback; no silent acceptance
- Schema/Corel/layout safety for new designs: not measured because generation
  correctly did not run
- Fake business data introduced: none

## HUMAN REVIEW

- Status: `pending`
- Human preference collected: `false`
- Automated contact-sheet inspection is reported as engineering evidence only,
  not as human preference.

## LICENSE MATRIX

| Layer | Commercial allowed | Evidence/state |
|---|---:|---|
| Embedding model | true | SigLIP2 model card: Apache-2.0 |
| GenPoster reference previews | false | CC-BY-NC-4.0, research-only |
| Project-owned reference templates | true | Original deterministic templates |
| Mixed 165-reference corpus | false | Contains GenPoster-derived references |
| Qwen LoRA checkpoint | false | Trained with non-commercial GenPoster-derived data |
| v0.3.3 benchmark assets | true | Verified CC0/project-owned manifests |
| Final combined research pipeline | false | Most restrictive model/reference input governs use |

No mixed-corpus or checkpoint flag is upgraded by the Apache-2.0 embedding
model license.

## LIMITATIONS

- The previews are visually sparse design-schema renders, not rich production
  artwork. Fifty-four preview embeddings are content-identical cache hits.
- The 100 GenPoster samples use generic `poster` metadata and frequently contain
  visible source text that is not semantically useful to Vietnamese briefs.
- The selected SigLIP2 pooled features produce a narrow visual-text score range
  on this corpus; the model is not an aesthetic critic.
- Category-template held-out and leave-family-out are equivalent for current
  five-variant category families, so both expose the same collapse.
- The retrieval benchmark has no real human relevance labels; its metrics and
  contact sheets can reject a weak system but cannot certify beauty.

## BOTTLENECK DECISION

`VISUAL_RETRIEVAL_NOT_USEFUL`

The implementation works, runs locally within hardware limits, and increases
source variety. It does not provide meaningful visual relevance gain and makes
structural relevance/diversity worse. The current bottleneck is the visual
reference corpus and representation, not the absence of a fusion formula.

## FINAL DECISION

- `v0.3.4_complete: false`
- `hybrid_retrieval_ready: false` for default design generation; research CLI/index are ready
- `held_out_retrieval_improved: false`
- `visual_quality_improved: false` (generation not justified)
- `technically_safe: true`
- `ready_for_vision_critic: true` as a separate research direction
- `ready_for_v0.4_preference_training: false`
- `production_ready: false`
- `commercial_allowed: false`

## NEXT 3 ACTIONS

1. Replace sparse schema-render previews with a legally cleared, visually rich reference corpus and add explicit prompt-to-reference relevance judgments.
2. Re-evaluate SigLIP2 embeddings with learned-free score calibration and true leave-case/family splits before reconnecting them to Qwen.
3. In parallel, prototype a small local vision critic on rendered outputs because retrieval alone did not solve art direction.
