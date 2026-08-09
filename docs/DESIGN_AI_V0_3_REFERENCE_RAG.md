# Design AI v0.3 — Reference-Grounded Design RAG

## Scope

V0.3 keeps the trained Design AI v0.1 Qwen3 adapter and the v0.2 best-of-four
selection loop unchanged. It adds lightweight, local structural retrieval,
reference grounding, role-aware hierarchy scoring, and deterministic text
fitting. No model training, model upgrade, vision model, paid API, or bulk
dataset download is part of this milestone.

```text
brief -> deterministic analyzer -> local weighted/MMR retrieval
      -> compact structural summaries -> one loaded Qwen3 session
      -> four candidates -> typography fit -> schema/Corel/preview/critic
      -> ranking -> editable design.json + Corel operations
```

References are instructions about composition, hierarchy, alignment, spacing,
density, palette intent, hero placement, and CTA placement. The planner is
explicitly forbidden from copying reference text, brands, logos, assets, or
exact coordinates.

## Reference corpus and licensing

Build the bounded local corpus:

```powershell
python training\tools\build_reference_corpus.py `
  --source-dir training\data\research\genposter_smoke_100 `
  --output-dir training\artifacts\reference_corpora\design_v0_3
```

The current corpus has 165 records: 100 GenPoster structural records and 65
project-owned generic structural templates (13 categories times five distinct
compositions). The templates contain generic placeholder copy and no benchmark
brand, logo, or asset. GenPoster source records do not have their upstream
background images in the local smoke cache, so their previews are explicitly
debug structural renders rather than original artwork.

The mixed corpus inherits the most restrictive source license:

```text
license_class: research_only_mixed_corpus
research_only: true
commercial_allowed: false
```

GenPoster remains CC-BY-NC-4.0 and is never relabeled production-safe. The
provider boundary can later be replaced by approved `internal_cdr` records;
private CDR ingestion is disabled until that archive is normalized.

## Retrieval

`StructuredBriefV1` is produced by deterministic Vietnamese/English rules with
a strict fallback. `ReferenceFeaturesV1` derives normalized boxes, roles,
counts, alignment, margins, rhythm, whitespace, overlap, hierarchy ratios,
hero/CTA placement, composition regions, colors, aspect ratio, and density.

Retrieval uses explainable weighted similarity: category 0.28, format 0.18,
style 0.18, aspect ratio 0.15, density 0.11, and colors 0.10. A deterministic
MMR-like pass (`lambda=0.72`) prevents near-identical Top-K results.
`ReferenceDesignSummaryV1` excludes source text/assets/exact boxes and is capped
by a configurable token budget (350 by default). A 900-token estimate rendered
to 1,135 actual Qwen tokens and caused output truncation near the 1,664-token
training gate; 350 rendered to 612 tokens on the measured spa smoke prompt.

Run the retrieval-only benchmark:

```powershell
python training\tools\benchmark_retrieval.py `
  --reference-index training\artifacts\reference_corpora\design_v0_3\reference_index.jsonl `
  --top-k 5 `
  --output training\artifacts\benchmarks\design_v0_3_retrieval\retrieval_benchmark.json
```

## Generation

Run one RAG best-of-four request:

```powershell
.\.venv-training\Scripts\python.exe training\tools\reference_rag.py `
  --checkpoint training\artifacts\runs\20260809_qwen3_1_7b_smoke\checkpoint-5 `
  --reference-index training\artifacts\reference_corpora\design_v0_3\reference_index.jsonl `
  --prompt "Thiết kế menu trà sữa 6 món" `
  --width-mm 210 --height-mm 297 --num-candidates 4 `
  --reference-top-k 5 `
  --output training\artifacts\runs\design_v0_3_menu
```

The output retains the v0.2 artifact contract and adds `brief.json`,
`retrieval.json`, `reference_context.json`, `references/ref_XX.json`,
`performance.json`, and per-candidate `postprocess.json`.

Text fitting uses local glyph measurement, explicit line wrapping, bounded font
reduction, line-height handling, and safe box expansion. It never silently
truncates. Any unresolved overflow and last-resort truncation are explicit and
penalized. The fitted document is validated and compiled to Corel operations
after fitting, so the editable output and PNG preview agree.

## Fair v0.2 versus v0.3 benchmark

V0.3 uses the same trained checkpoint, 13 prompts, four seeds, and generation
settings as v0.2. Because glyph measurement and hierarchy scoring changed, the
primary comparison does not compare new scores with the published v0.2 number.
Instead, all 52 stored v0.2 candidate documents are rescored and reranked by
the exact same v0.3 scorer used for the new RAG candidates. The immutable
published v0.2 summary is preserved separately for audit.

```powershell
.\.venv-training\Scripts\python.exe training\tools\benchmark_reference_rag.py `
  --checkpoint training\artifacts\runs\20260809_qwen3_1_7b_smoke\checkpoint-5 `
  --reference-index training\artifacts\reference_corpora\design_v0_3\reference_index.jsonl `
  --output training\artifacts\benchmarks\design_v0_3_reference_rag `
  --top-k 5 --context-token-budget 350
```

The command exits zero only if all gates pass: at least 8% combined-score
improvement, 100% winner validity, no severe outside-canvas case, overlap no
more than 10% worse, text fit better, and hierarchy at least equal to the fair
v0.2 replay.

Every prompt receives `comparison.json`, `side_by_side.png`,
`comparison.html`, and `manual_review.template.json`. Human preference and
human scores remain null until a person reviews them; machine metrics are never
presented as human judgment.

## Verified checkpoint — 2026-08-09

The final fair run is
`training/artifacts/benchmarks/20260809_design_v0_3_reference_rag_final_v8`.
All 52 v0.2 candidates were rescored with critic v0.3.0, and all 52 real RAG
model outputs use the identical checkpoint, prompt set, four seeds, and
generation settings. The last replay reapplies the finalized deterministic
postprocessors to those immutable raw outputs; it does not synthesize model
responses.

| metric | v0.2 fair replay | v0.3 RAG best-of-4 |
| --- | ---: | ---: |
| combined | 0.744975 | 0.828604 |
| technical | 0.580141 | 0.863639 |
| overlap | 0.041277 | 0.000000 |
| spacing | 0.875354 | 0.885574 |
| hierarchy | 0.663317 | 0.689965 |
| text fit | 0.456410 | 0.942308 |
| coverage | 0.457239 | 0.317489 |
| schema validity | 1.000000 | 1.000000 |

The exact combined-score improvement is 11.225728%. All automated v0.3 gates
pass. Retrieval averages 0.749866 relevance and 0.467508 diversity with 100%
category and format match; measured average retrieval latency is 0.033756 s.
Reference context adds 523.69 actual prompt tokens on average (641.46 RAG vs
117.77 baseline) and remains within the 350 estimated-token context budget.

The dense ten-item menu contains ten named item/description rows and ten
aligned price elements. It has zero overflow, 1.0 text fit, 1.0 price-column
alignment, zero overlap, and hierarchy 0.770940 versus v0.2's 0.676193. Its
combined heuristic score is lower than v0.2 (0.813915 versus 0.844721), so this
case is reported as a structural/readability improvement rather than a blanket
aesthetic win. Human preference is still uncollected; the 13 side-by-side
reports are review inputs, not human-quality claims.

## Model provenance

- Model: `Qwen/Qwen3-1.7B`
- Revision: `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`
- Adapter: `checkpoint-5`
- Quantization: NF4 4-bit QLoRA
- LoRA: rank 8, alpha 16
- Retrained in v0.3: no

Elem2Design remains available as a research/reference integration and is not
deleted or replaced by this local planner path.
