# Design AI v0.3.5 — Vision Critic + Self-Refine

## RESULT

- `start_time`: 2026-08-12T11:40:46+07:00 (derived from the calibration artifact write time and its measured 626.8-second run)
- `end_time`: 2026-08-12T12:00:00+07:00 (smoke benchmark artifact write time)
- `measured_model_runtime`: approximately 925.1 seconds across calibration and the two-case smoke, excluding implementation and test time
- `result`: **quality gate failed**
- No release manifest was created and no production runtime integration was enabled.

The bounded refinement path was technically safe in both executed cases, but it did not produce a credible visual improvement. The same critic that raised SALE's absolute score from 0.75 to 0.78 preferred the original v0.3.3 image in a blinded pairwise comparison. SPA stayed at 0.78 and the best-iteration selector correctly retained iteration 0.

## GIT

- `starting_sha`: `ab50d27e40cfb2b9cd0c19798f43c4ae7a38cd02`
- `ending_sha`: recorded by the final Git handoff after this report is committed
- `branch`: `agent/codex-training-bootstrap`
- `push_status`: recorded by the final Git handoff

## MODEL RESEARCH

Two local candidates were compared from their official model cards before any weight download:

| Candidate | Exact revision | License | Published size/precision | Hardware assessment | Decision |
|---|---|---|---|---|---|
| `Qwen/Qwen3-VL-2B-Instruct` | `89644892e4d85e24eaac8bacfd4f463576704203` | Apache-2.0 | 2,127,532,032 BF16 parameters | Fits the 6 GB GPU with 4-bit NF4; multilingual fit is preferable for Vietnamese briefs | Selected |
| `HuggingFaceTB/SmolVLM2-2.2B-Instruct` | `482adb537c021c86670beed01cd58990d01e72e4` | Apache-2.0 | 2,246,784,880 F32 parameters; card documents about 5.2 GB for video inference | Feasible but the card emphasizes English and video; weaker fit for this design-critique task | Not downloaded |

Only the selected model was downloaded. This avoided spending storage and bandwidth on a second multi-gigabyte model. The model card URLs are:

- https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct
- https://huggingface.co/HuggingFaceTB/SmolVLM2-2.2B-Instruct

## CHOSEN CRITIC

- `model`: `Qwen/Qwen3-VL-2B-Instruct`
- `revision`: `89644892e4d85e24eaac8bacfd4f463576704203`
- `quantization`: bitsandbytes NF4 4-bit, double quantization, float16 compute
- `image_bound`: longest side 768 px
- `decoding`: greedy, temperature 0, at most 256 new tokens
- `issue_bound`: at most 2 structured issues per critique
- `load_time`: 12.04–16.70 seconds in measured runs
- `peak_vram`: 2.1474 GiB calibration; 1.8884 GiB self-refine smoke
- `average_critic_latency`: 92.3760 seconds in the two-case smoke

The training environment already had PyTorch `2.12.1+cu126`, Transformers `5.14.1`, Accelerate, and bitsandbytes. Qwen3-VL image processing required torchvision, so `torchvision==0.27.1+cu126` was installed from the official PyTorch CUDA 12.6 index. Optional vision dependencies are isolated in `training/requirements-vision.txt` and are not added to the default CI install.

## CRITIC SCHEMA

`VisionCritiqueV1` is strict and bounded. It contains:

- an overall quality score and confidence;
- zero to two issues from an allow-listed issue taxonomy;
- severity, confidence, target role, reason, recommended action, and magnitude;
- exact critic model/revision and latency metadata.

Unknown issue types and free-form commands are rejected. JSON fence recovery and a small allow-listed normalization layer handle common local-model formatting mistakes, but truncated outer objects are rejected. The prompt is category-aware and explicitly prioritizes visual hierarchy, focal point, image/text balance, spacing, whitespace, typography, CTA, palette, crop quality, menu grouping, and campaign energy. It does not expose hidden scorer values or version labels.

## SELF-REFINE PIPELINE

The implemented loop is:

`design.json → preview → local VLM critique → strict issue schema → bounded deterministic plan → safety validation → Corel compilation → rerender → re-critique → best safe iteration`

Only known operations are permitted: bounded role scaling, small role shifts, text/CTA emphasis, contrast adjustment, existing-decoration adjustment, and existing menu-group adjustment. Limits are enforced at 12% scale/font change, 8% bbox delta, and 5% canvas movement. The loop defaults to two iterations, permits one to three, stops on no issues/no operations/repeated issues/unsafe refinement/no improvement, and selects the best technically safe iteration instead of blindly returning the last one.

Every iteration saves `design.json`, `preview.png`, `preview_annotated.png`, `vision_critique.json`, `refinement_plan.json`, `refinement_report.json`, `technical_validation.json`, `metrics.json`, and `corel_operations.json`.

## CALIBRATION

Calibration used the existing five v0.3.2 placeholder versus v0.3.3 real-asset comparisons.

| Metric | Result |
|---|---:|
| Known comparisons | 5 |
| Higher absolute score for v0.3.3 | 4/5 |
| Blinded pairwise preference for v0.3.3 | 4/5 |
| Blinded pairwise preference for v0.3.2 | 1/5 (SPA) |
| Mean absolute-score delta | +0.032 |
| SALE repeats | 3 |
| Score variance | 0.0 |
| Top-issue stability | 1.0 |
| Issue agreement | 1.0 |

Calibration therefore passed its machine gate. However, this apparently perfect repeatability is not sufficient evidence of perceptual quality: scores clustered at 0.75/0.78 and the model repeated `weak_focal_point` plus `weak_hierarchy` across categories. That low issue diversity was treated as a warning and tested in the repair smoke.

Calibration artifact: `training/artifacts/benchmarks/20260812_design_v0_3_5_vision_critic/calibration/calibration_summary.json`.

## BASELINE VS REFINED

The mission required SALE and SPA first and explicitly allowed expansion only if those repairs were credible. They were not, so CAFE, MENU, and SIGNAGE were deliberately not run.

| Case | v0.3.3 critic | selected v0.3.5 critic | Delta | Frozen score before → after | Pairwise preference | Technical result |
|---|---:|---:|---:|---:|---|---|
| SALE | 0.75 | 0.78 | +0.03 | 0.910921 → 0.894883 | v0.3.3 (0.98) | safe, but frozen score regressed |
| SPA | 0.78 | 0.78 | 0.00 | 0.876437 → 0.876437 | v0.3.3 (0.98) | safe; iteration 0 retained |
| CAFE | not run | not run | — | — | — | stopped by primary gate |
| MENU | not run | not run | — | — | — | stopped by primary gate |
| SIGNAGE | not run | not run | — | — | — | stopped by primary gate |

The two-case mean critic delta was +0.015, but refined pairwise wins were 0/2. SALE's score increased only after enlarging the product hero and headline, while the frozen scorer declined by 0.016038 and the critic's own pairwise mode preferred the baseline. SPA's proposed larger hero/headline was not selected because it did not improve the combined selection objective.

## REPAIR PERFORMANCE

- cases executed: 2/5
- iterations executed: one refinement iteration per case
- accepted bounded operations: 2 per case
- rejected operations: 0
- selected refined iteration: SALE only
- selected baseline iteration: SPA
- positive absolute critic delta: 1/2
- refined pairwise preferred: 0/2
- baseline pairwise preferred: 2/2
- mean absolute critic delta: +0.015
- average total self-refine latency: 149.1576 seconds/case
- optional 13-case replay: not run because the primary gate failed

## TECHNICAL SAFETY

For both executed cases:

- schema valid: 2/2
- outside-canvas rate: 0.0
- overlap ratio: 0.0
- text-fit rate: 1.0
- Corel compilation: 2/2
- business content immutable: 2/2
- asset/logo aspect metadata preserved: 2/2
- no hidden truncation: 2/2
- no fabricated business data: 2/2

The system validates after every operation. A rejected operation cannot replace the current safe document. The test suite covers invalid/truncated critic JSON, strict issue taxonomy, bounded recovery, operation caps, repeated-issue stalls, business-content mutation, outside-canvas rejection, overlap regression, Corel compilation, best-iteration selection, lazy/no-weight unit behavior, and deterministic blinded order.

## COST / PERFORMANCE

- critic load: 12.04–16.70 seconds
- average critic inference within smoke: 92.3760 seconds
- average complete self-refine case: 149.1576 seconds
- peak VRAM: 2.1474 GiB
- local API spend: zero
- model download: only the selected Qwen3-VL checkpoint

The memory footprint is acceptable for the RTX 3060 Laptop 6 GB. Latency is high for interactive use, and the weak/templated critique quality means optimizing latency is not justified yet.

## CONTACT SHEET

- Partial, honest SALE/SPA sheet: `training/artifacts/benchmarks/20260812_design_v0_3_5_vision_critic/contact_sheet_v033_vs_v035_real_assets.png`
- SALE comparison: `training/artifacts/benchmarks/20260812_design_v0_3_5_vision_critic/runs/sale/comparison.png`
- SPA comparison: `training/artifacts/benchmarks/20260812_design_v0_3_5_vision_critic/runs/spa/comparison.png`

The filename follows the planned five-case convention, but the artifact contains only the two primary-gate cases. No five-case result is claimed. `human_preference_collected` remains `false`; pairwise judgments are machine judgments, not human preference.

## LICENSE MATRIX

| Component | License/commercial state |
|---|---|
| Qwen3-VL critic | Apache-2.0; commercial use allowed by the model license |
| v0.3.3 public/project benchmark assets | CC0 or project-owned according to the existing per-asset manifests |
| Qwen planner checkpoint | research checkpoint trained on GenPoster-derived CC-BY-NC material |
| Reference corpus | research-only; `commercial_allowed=false` |
| Combined v0.3.5 pipeline | research-only; `commercial_allowed=false` |

The critic's permissive license does not override the non-commercial restrictions of the planner checkpoint/reference corpus.

## FAILURE ANALYSIS

1. **Critic output is too templated.** It repeats the same two issues across different categories and produces coarse, clustered scores.
2. **Absolute and pairwise modes disagree.** SALE's absolute score rises after refinement, yet pairwise comparison strongly prefers the baseline. This is direct evidence that the current critic is not a reliable optimization target.
3. **The refiner can execute safely but has weak art-direction leverage.** Enlarging hero/headline is mechanically valid, but it does not create a better composition and can lower the frozen score.
4. **More cases would not repair the evidence.** Running CAFE/MENU/SIGNAGE after the primary gate failed would add cost, not establish credibility.

## QUALITY DECISION

`VISION_CRITIC_NOT_RELIABLE`

The local critic is hardware-feasible and its strict integration is technically sound, but its judgments are not internally consistent enough to drive autonomous visual repair. v0.3.3 therefore remains the stable research checkpoint. No v0.3.5 release manifest or default runtime integration is created.

## FINAL DECISION

- `v0.3.5_complete`: false
- `critic_calibrated`: true
- `self_refine_improved`: false
- `technically_safe`: true for the 2 executed primary cases
- `visually_improved`: false
- `ready_for_human_review`: true for diagnostic SALE/SPA comparison only
- `ready_for_v0.4_preference_training`: false
- `production_ready`: false
- `commercial_allowed`: false

## LIMITATIONS

- Repair evaluation stopped at 2/5 cases as required by the gate.
- There is no human preference result.
- Calibration contains only five known comparisons.
- The critic uses deterministic image-level judgment without region annotations or typography OCR measurements.
- The strict action set intentionally cannot perform structural redesign.

## NEXT 3 ACTIONS

1. Build a human-labeled calibration set with explicit region-level issues for at least SALE, SPA, MENU, CAFE, and SIGNAGE.
2. Re-evaluate Qwen3-VL with contrastive/pairwise prompts that require evidence coordinates and reject generic repeated critiques before allowing refinement.
3. Resume self-refine only after the critic agrees with held-out human pairwise labels and with its own absolute ranking; keep v0.3.3 stable until then.

## TL;DR

- Qwen3-VL-2B fits the RTX 3060 6 GB in NF4 at about 2.15 GiB peak VRAM.
- Calibration ranked real assets above placeholders in 4/5 cases.
- The critic's issues and scores were overly repetitive.
- SALE/SPA refinements remained schema/Corel/content safe.
- SALE's critic score rose, but its frozen score fell.
- Pairwise critic preferred v0.3.3 in both SALE and SPA.
- SPA correctly rolled back to iteration 0.
- The five-case expansion and optional 13-case replay were stopped.
- No release manifest or production integration was created.
- `v0.3.5_complete=false`; v0.3.3 remains stable.
