# Design AI v0.2 — Aesthetic Selection Loop

## Scope

v0.2 keeps the real v0.1 `Qwen/Qwen3-1.7B` QLoRA checkpoint unchanged and
adds an inference-time best-of-N selection loop:

```text
prompt
  -> one 4-bit Qwen3 + LoRA session
  -> N sequential seeded candidates
  -> explicit JSON recovery + unified schema validation
  -> Corel transaction compilation + preview PNG
  -> deterministic technical critic + offline aesthetic heuristic
  -> hard eligibility gate + weighted ranking
  -> final editable design and chosen/rejected preference record
```

This phase does not train a new model, start PosterReward/LLM4SVG, or change
the Elem2Design research integration.

## Reproducible generation

`Qwen3PlannerSession` loads the NF4 base model and PEFT adapter once. Candidate
generation is sequential to fit the RTX 3060 Laptop 6GB GPU. Candidate `i`
uses `base_seed + i`, calls Transformers' deterministic seed helper, and logs
the complete sampling configuration. Defaults follow Qwen3 non-thinking
sampling guidance: temperature 0.7, top-p 0.8, top-k 20, repetition penalty
1.05. The maximum number of candidates is eight.

Raw model text is always retained. Observed v0.1 outputs use `canvas`,
`canvas_size`, `design`, or `design_document` shorthand variants. Recovery is
explicit in `validation.json`; remote asset URLs are never fetched and become
editable local placeholders with asset intent metadata.

## Critics and ranking

All scores share a documented 0..1 scale. The deterministic technical critic
hard-fails invalid schema, invalid normalized geometry, out-of-canvas objects,
invalid dimensions, and duplicate IDs. Soft rules cover overlap, tiny text,
duplicate semantic elements, excessive element count, coverage, and use of
schema recovery.

The offline aesthetic critic is deliberately marked `model_based: false`. It
scores composition, visual hierarchy, typography, spacing, color harmony,
balance, readability, and prompt/style match from validated layout structure
and preview availability. `VisionAestheticCritic` is the extension point for a
future learned critic; v0.2 does not pretend that a vision model was used.

Weights are versioned in
`training/config/scoring/aesthetic_v0_2.json`. The calibrated v0.2 heuristic
uses 25% technical, 15% composition, 15% hierarchy, 10% typography, 10%
spacing, 8% color harmony, 5% balance, 10% readability, and 2% prompt match.
Readability includes normalized text/background contrast and estimated rendered
text fit. Critic v0.2.3 also penalizes text-box overflow and separately penalizes
truncated-prefix recovery so an incomplete design cannot win merely because its
missing tail reduced element overlap. Hard-failed candidates are ineligible
regardless of aesthetic score. Remaining ties are resolved by technical score
and stable candidate ID.

## Artifact contract

Every run uses a new directory and refuses to overwrite an existing run:

```text
run/
  request.json
  ranking.json
  contact_sheet.png
  comparison.html
  preference.auto.json
  candidates/candidate_01/
    raw_output.txt
    generation.json
    planner.json
    design.json
    validation.json
    corel_operations.json
    preview.png
    metrics.json
    score.json
  final/
    design.json
    corel_operations.json
    preview.png
    selection.json
```

Invalid model/compile candidates keep diagnostics and receive score zero. A
mixture of valid and invalid candidates continues normally. Infrastructure
failures in rendering or critic code are surfaced instead of being mislabeled
as bad model output. If every candidate is invalid, the
run still writes ranking/contact-sheet diagnostics and then exits with an
explicit `AllCandidatesInvalidError`; no false winner is created. N=1 remains
a supported fallback but cannot produce a chosen/rejected pair.

Preference records distinguish `auto_preference` from `human_preference` and
store critic source/version, model revision, checkpoint, source run, and data
license. Automated selections are never labeled as human-approved. A human
record requires explicit, distinct chosen and rejected IDs, and cannot approve
an invalid candidate.

## Commands

Single best-of-N run:

```powershell
.\.venv-training\Scripts\python.exe training\tools\best_of_n.py `
  --checkpoint training\artifacts\runs\20260809_qwen3_1_7b_smoke\checkpoint-5 `
  --model-config training\config\experiments\qwen3_1_7b_local_qlora.json `
  --prompt "Thiết kế poster spa cao cấp màu kem và vàng" `
  --width-mm 400 --height-mm 120 --num-candidates 4 `
  --base-seed 420 --max-new-tokens 384 `
  --output training\artifacts\runs\20260809_v0_2_spa_best_of_4
```

Multi-category benchmark:

```powershell
.\.venv-training\Scripts\python.exe training\tools\benchmark_best_of_n.py `
  --checkpoint training\artifacts\runs\20260809_qwen3_1_7b_smoke\checkpoint-5 `
  --model-config training\config\experiments\qwen3_1_7b_local_qlora.json `
  --benchmark-config training\config\benchmarks\design_v0_2.json `
  --max-new-tokens 512 --base-seed 4200 `
  --output training\artifacts\benchmarks\20260809_design_v0_2_best_of_4
```

The benchmark defines single-shot as `candidate_01` and best-of-4 as the
highest eligible score from the same four-candidate run. This pairing keeps
prompt, checkpoint, generation family, and critic identical.

## Verified 13-prompt benchmark

The final local benchmark is
`training/artifacts/benchmarks/20260809_design_v0_2_best_of_4_final_v7`.
It covers spa, nail, salon, cafe, milk tea, restaurant, sale, opening,
cosmetics, signage, business card, social banner, and a dense food menu.
All 52 raw generations came from the unchanged trained v0.1 checkpoint. The
final v0.2.3 scoring pass reused those exact outputs after matching prompt,
dimensions, seed, token cap, sampling settings, model ID/revision, and adapter
path; this reuse is recorded in the benchmark summary.

Measured results:

- single-shot average: 0.650236;
- best-of-4 average: 0.759019;
- relative improvement: 16.7298% (10% target passed);
- schema-eligible rate: 100% for single-shot and selected outputs;
- mean technical score: 0.418183 -> 0.600481;
- mean overlap ratio: 0.200695 -> 0.041277;
- mean spacing: 0.589770 -> 0.872212;
- mean estimated text fit: 0.397436 -> 0.498077;
- mean hierarchy: 0.751865 -> 0.698028 (regressed and must not be hidden);
- mean layout diversity: 0.212175;
- recorded generation latency: 118.73 seconds per candidate;
- peak allocated inference VRAM: 1.39545 GiB.

The internal score target passed, but this is not a claim of professional
visual quality. Manual contact-sheet inspection found clear selection wins for
restaurant and dense menu layouts, while the sale prompt had no professional
candidate: even its selected complete output still has severe glyph overflow.
The heuristic and fallback renderer are therefore a useful local filter, not a
replacement for designer review or a learned visual critic. See
`docs/DESIGN_AI_V0_2_HUMAN_REVIEW.md`.

## Verified local smoke

The real four-candidate smoke run at seeds 420–423 completed on the local RTX
3060 Laptop GPU. Three candidates validated and compiled; one 384-token output
was truncated and correctly hard-failed. The winner scored 0.853615, average
structural diversity was 0.396495, peak allocated inference VRAM was 1.3405
GiB, and average generation latency was 94.74 seconds per candidate. The
winner produced strict unified `design.json`, editable Corel operations, PNG
preview, comparison report, and an auto-preference record.

Re-running seeds 420–423 with a lower token cap produced byte-identical raw
outputs for the three naturally completed candidates. The longer fourth output
was an identical prefix up to the lower cap. This verifies deterministic local
sampling on the recorded hardware/software stack; it does not promise identical
CUDA results on a different stack.

## License boundary

The base model license is Apache-2.0, but this adapter was trained on
GenPoster100K CC-BY-NC-4.0 data. Every v0.2 request, design, and preference
artifact therefore remains `research_only` with `commercial_allowed: false`.
Selection does not change training-data rights.
