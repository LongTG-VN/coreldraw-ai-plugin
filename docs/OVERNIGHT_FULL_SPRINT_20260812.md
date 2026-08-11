# OVERNIGHT SPRINT RESULT

start_time: 2026-08-12 00:11:19 GMT+7  
end_time: 2026-08-12 01:58:31 GMT+7  
duration: 1h 47m 12s of implementation, real GPU generation, audit, and release verification

# GIT

branch: `agent/codex-training-bootstrap`  
starting_sha: `e6a34813aac748d98d234adf8ae15e09902273ad`  
ending_sha: `6b71d3efceec0f35d9f3d04636ef2c144f5fe0ec` (release checkpoint before this report-only commit)  
remote_sha: `6b71d3efceec0f35d9f3d04636ef2c144f5fe0ec`  
ahead/behind: `0/0`  
worktree: clean before this report-only commit  
commits:

- `3977b45 fix(training): harden RAG benchmark identity and resume`
- `2f0399f feat(training): add visual composition engine`
- `5ea62db feat(runtime): add lazy trained Design AI service`
- `1e52354 feat(training): add human preference and held-out evaluation`
- `543497d feat(training): benchmark frozen visual composition`
- `60380fb fix(training): sanitize ungrounded campaign values`
- `6bcbf76 feat(training): compare clean v0.3 visual winners`
- `04be16d docs(runtime): document local trained Design AI service`
- `d2f4f64 fix(training): preserve benchmark provenance in comparison`
- `65a18f0 feat(training): audit visual and dense-menu release metrics`
- `d1ab4ab test(training): audit v0.3.1 release artifacts`
- `6b71d3e chore(training): record Design AI v0.3.1 research checkpoint`

push_status: every stable checkpoint above was pushed without force; release SHA equals remote SHA

# V0.3 BASELINE AUDIT

status: `stable_research_checkpoint: true`  
52 candidates: present and structurally complete  
reuse: 52 fresh, 0 reused  
schema: strict-valid 52/52 after explicit recovery; raw canonical-valid 0/52  
warnings:

- Raw model schema validity is 0/52; validated candidates depend on explicit recovery.
- The audit found 128 historical synthetic menu/business values; they were benchmark placeholders, not customer data.
- Coverage `0.317489274` was lower than v0.2 fair and remained a visual-density limitation.

# PHASE A — BENCHMARK HARDENING

cache identity: `GenerationIdentityV1` hashes the original prompt, grounded prompt, reference context and IDs, canvas, seed, generation settings, exact model revision, and checkpoint fingerprint  
resume: opt-in only; completed candidates are accepted only after exact identity and artifact verification; `resumed_verified_candidate` is distinct from audited raw-cache reuse  
tests: full suite at phase checkpoint: 133 passed  
result: safe public entrypoint remains fresh by default; collision tests pass; final benchmark recorded 52 fresh, 0 resume, 0 audited cache, 0 unsafe reuse, and 0 rejected identities

# PHASE B — V0.3.1 VISUAL COMPOSITION

implemented:

- profile: strict versioned profiles for 13 categories plus unknown-category fallback
- density: category-aware targets and reproducible density diagnostics
- palette: prompt-first role palette, deterministic fallback, and contrast checks
- typography: semantic font class/weight/case/tracking before deterministic glyph fitting
- hero/assets: editable hero/product/logo intent survives; missing real assets remain marked placeholders
- decorative composition: bounded panels, accents, dividers, CTA containers, campaign elements
- CTA: deterministic container/emphasis with a frozen diagnostic
- sale/opening: campaign profiles, focal accents, and explicit missing-offer placeholders
- business-data safety: missing menu data uses `[ITEM_nn]`, `[DESCRIPTION_nn]`, `[PRICE_nn]`; ungrounded campaign percentages/offers/dates are sanitized to marked placeholders

files: `training/visual/`, `training/inference/reference_layout.py`, comparison/replay/audit tools, and focused tests  
tests: phase replay/full checkpoint 141 passed; final suite 160 passed  
limitations: visuals remain template-like; average CTA prominence is only `0.344038462`; two prompts regress slightly in heuristic combined score; human aesthetic review is still required

# PHASE C — TRAINED RUNTIME

service: `training.inference.service.TrainedDesignService`, pinned to `Qwen/Qwen3-1.7B` revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` and local `checkpoint-5`  
lazy loading: model is not imported or allocated while the status endpoint is queried  
status endpoint: `GET /api/v1/design/model/status`  
trained endpoint: `POST /api/v1/design/generate-trained`  
baseline compatibility: `POST /api/v1/design/generate` remains the lightweight deterministic endpoint and returns `trained_model: false`  
model lifecycle: real GPU smoke proved one 4.023-second load, one reused session, and generation count `0 -> 1 -> 2`; requests are serialized by one lock  
tests: fake lifecycle/API tests plus real 3-prompt artifact smoke; final suite 160 passed  
limitations: synchronous local service, one GPU queue, raw schema recovery required, research-only output

# PHASE D — EVALUATION

ablation: 13 prompts per variant, all schema/Corel/preview valid. Recovery-only `0.434237`; reference layout + typography `0.836721`; full visual `0.871890`.  
held-out retrieval: full corpus relevance/category/format `0.749866/1.0/1.0`; excluding exact-category owned templates drops to `0.386552/0.0/0.692308`; GenPoster-only is `0.339243/0.0/0.538462`. The original retrieval benchmark is therefore optimistic.  
human review collector: validates only completed real-human review JSON and rejects incomplete, duplicate, or heuristic-derived preference  
preference pair exporter: strict `PreferencePairV1` retains prompt, references, chosen/rejected designs and previews, reviewer dimensions, provenance, and license state  
tests: phase checkpoint 154 passed; final suite 160 passed

# ARTIFACT REPLAY

prompts: 13 existing strict-valid v0.3 winners; 0 new model generations  
before: combined `0.828603638`, technical `0.863638563`  
after: combined `0.869261781`, technical `0.899487179`  
coverage: `0.317489274 -> 0.437100505`  
overlap: `0 -> 0`  
text fit: `0.942307692 -> 1.0`  
hierarchy: headline-dominance diagnostic `0.590646066 -> 0.633890720`  
visual findings: density, palette, asset intent, and editable structure improve without destructive overlap; layouts remain visually basic and need human review  
artifact: `training/artifacts/benchmarks/20260812_design_v0_3_1_visual_replay_v4`

# FINAL CLEAN BENCHMARK

fresh candidates: 52  
resumed verified candidates: 0  
unsafe reused candidates: 0  

average latency: 34.335444 seconds/candidate; retrieval 0.018067 seconds/prompt  
peak VRAM: 1.445169 GiB reported by the generation session

| METRIC | V0.3 | V0.3.1 |
| --- | ---: | ---: |
| combined | 0.828603638 | 0.871889612 |
| technical | 0.863638563 | 0.899487179 |
| overlap | 0.000000000 | 0.000000000 |
| spacing | 0.885574350 | 0.942829749 |
| hierarchy | 0.689965230 | 0.704646568 |
| text fit | 0.942307692 | 1.000000000 |
| coverage | 0.317489274 | 0.446677428 |
| diversity | 0.240638734 | 0.264210753 |
| schema validity | 1.000000000 | 1.000000000 |

Combined improvement over v0.3 clean is `+5.223966%`. Improvement over v0.2 fair is `+17.036123%`. The scorer and its weights were not changed.

# NEW VISUAL METRICS

density_fit: 0.877543863  
palette_cohesion: 0.980769231  
contrast: 0.805179589  
headline_dominance: 0.525746773  
cta_prominence: 0.344038462  
typography_differentiation: 0.630769231  
asset_intent_preservation: 1.000000000  
decorative_balance: 0.842948718  
focal_point_strength: 0.674930070

# PER-PROMPT RESULTS

prompt: `business_card`  
v0.3 score: 0.753045  
v0.3.1 score: 0.859152  
technical: 0.920000  
coverage: 0.619600  
visual notes: strong density/asset intent; no CTA requested or detected; card stays editable  
comparison path: `training/artifacts/benchmarks/20260812_design_v0_3_1_clean/comparisons/v0_3_vs_v0_3_1_clean/runs/business_card/comparison.html`

prompt: `cafe_vintage`  
v0.3 score: 0.877005  
v0.3.1 score: 0.906266  
technical: 0.920000  
coverage: 0.504650  
visual notes: hierarchy 0.841185, CTA present, hero placeholder retained  
comparison path: `training/artifacts/benchmarks/20260812_design_v0_3_1_clean/comparisons/v0_3_vs_v0_3_1_clean/runs/cafe_vintage/comparison.html`

prompt: `cosmetics_clean`  
v0.3 score: 0.827306  
v0.3.1 score: 0.876381  
technical: 0.920000  
coverage: 0.347600  
visual notes: premium whitespace retained; palette and asset intent 1.0; CTA container added  
comparison path: `training/artifacts/benchmarks/20260812_design_v0_3_1_clean/comparisons/v0_3_vs_v0_3_1_clean/runs/cosmetics_clean/comparison.html`

prompt: `dense_food_menu`  
v0.3 score: 0.813915  
v0.3.1 score: 0.808251  
technical: 0.653333  
coverage: 0.628657  
visual notes: slight combined regression; 10 item and 10 price placeholders are explicit, aligned, non-overflowing, and not fake customer values  
comparison path: `training/artifacts/benchmarks/20260812_design_v0_3_1_clean/comparisons/v0_3_vs_v0_3_1_clean/runs/dense_food_menu/comparison.html`

prompt: `grand_opening`  
v0.3 score: 0.883598  
v0.3.1 score: 0.888985  
technical: 0.920000  
coverage: 0.481450  
visual notes: campaign palette/hero applied; CTA prominence remains 0 and needs human review  
comparison path: `training/artifacts/benchmarks/20260812_design_v0_3_1_clean/comparisons/v0_3_vs_v0_3_1_clean/runs/grand_opening/comparison.html`

prompt: `milk_tea_social`  
v0.3 score: 0.828679  
v0.3.1 score: 0.889569  
technical: 0.920000  
coverage: 0.381150  
visual notes: CTA and product intent retained; density fits social profile  
comparison path: `training/artifacts/benchmarks/20260812_design_v0_3_1_clean/comparisons/v0_3_vs_v0_3_1_clean/runs/milk_tea_social/comparison.html`

prompt: `nail_pastel`  
v0.3 score: 0.845146  
v0.3.1 score: 0.891661  
technical: 0.920000  
coverage: 0.366200  
visual notes: requested pastel intent, CTA, asset placeholder, and spacing remain bounded  
comparison path: `training/artifacts/benchmarks/20260812_design_v0_3_1_clean/comparisons/v0_3_vs_v0_3_1_clean/runs/nail_pastel/comparison.html`

prompt: `restaurant_menu`  
v0.3 score: 0.899485  
v0.3.1 score: 0.882657  
technical: 0.920000  
coverage: 0.555600  
visual notes: slight combined regression; menu remains aligned, readable, non-overlapping, and business-safe  
comparison path: `training/artifacts/benchmarks/20260812_design_v0_3_1_clean/comparisons/v0_3_vs_v0_3_1_clean/runs/restaurant_menu/comparison.html`

prompt: `sale_bold`  
v0.3 score: 0.798814  
v0.3.1 score: 0.825473  
technical: 0.920000  
coverage: 0.278700  
visual notes: campaign asset/CTA added, but density and headline diagnostics remain weak; human review required  
comparison path: `training/artifacts/benchmarks/20260812_design_v0_3_1_clean/comparisons/v0_3_vs_v0_3_1_clean/runs/sale_bold/comparison.html`

prompt: `salon_black`  
v0.3 score: 0.833476  
v0.3.1 score: 0.866545  
technical: 0.920000  
coverage: 0.374400  
visual notes: dark/premium styling and asset intent improve density; CTA absent  
comparison path: `training/artifacts/benchmarks/20260812_design_v0_3_1_clean/comparisons/v0_3_vs_v0_3_1_clean/runs/salon_black/comparison.html`

prompt: `signage_wide`  
v0.3 score: 0.693550  
v0.3.1 score: 0.829770  
technical: 0.920000  
coverage: 0.357600  
visual notes: strongest structural gain; wide dark signage remains inside canvas and Corel-editable  
comparison path: `training/artifacts/benchmarks/20260812_design_v0_3_1_clean/comparisons/v0_3_vs_v0_3_1_clean/runs/signage_wide/comparison.html`

prompt: `social_banner`  
v0.3 score: 0.835300  
v0.3.1 score: 0.884415  
technical: 0.920000  
coverage: 0.438800  
visual notes: density fit 0.974545, CTA and asset intent retained, no overlap  
comparison path: `training/artifacts/benchmarks/20260812_design_v0_3_1_clean/comparisons/v0_3_vs_v0_3_1_clean/runs/social_banner/comparison.html`

prompt: `spa_luxury`  
v0.3 score: 0.882528  
v0.3.1 score: 0.925438  
technical: 0.920000  
coverage: 0.472400  
visual notes: strongest absolute score; deliberate whitespace, hero placeholder, CTA, and hierarchy retained  
comparison path: `training/artifacts/benchmarks/20260812_design_v0_3_1_clean/comparisons/v0_3_vs_v0_3_1_clean/runs/spa_luxury/comparison.html`

# DENSE MENU

items: 10 explicit `[ITEM_nn]` plus 10 `[DESCRIPTION_nn]` placeholders  
prices: 10 explicit `[PRICE_nn]` placeholders  
fake_customer_prices: false  
placeholders: `benchmark_placeholder`, `placeholder_only: true`, `requires_user_data: true`; no value is labeled customer-provided  
alignment: price alignment consistency 1.0  
text fit: 1.0  
coverage: 0.628656566  
overlap: 0.0  
hierarchy: 0.740324358

# TESTS

pytest: 160 passed, 1 Starlette/FastAPI TestClient deprecation warning  
compile: `python -m compileall -q training tests` passed  
git diff check: passed  
GitHub CI: success for release SHA `6b71d3e`; runs `31525301766` and `31525293430`  
warnings: 15 reported unresolved text overflows exist in 6 rejected candidates; all 13 winners have zero unresolved overflow and all 52 candidates have zero truncation

# HUMAN REVIEW

comparison_count: 13  
human_review_status: pending; side-by-side PNG/HTML and strict manual templates are ready  
human_preference_collected: false

# LICENSE

research_only: true  
commercial_allowed: false  
production dataset used: no  
public research data used: 100 GenPoster structural records, CC-BY-NC-4.0, retained as non-commercial research provenance; 65 project-owned structural templates share the mixed research index

# KNOWN LIMITATIONS

P0

- Production/commercial use is prohibited for this checkpoint because the mixed reference corpus includes CC-BY-NC-4.0 research material and no human acceptance has been collected.

P1

- Raw Qwen output is canonical-valid 0/52 and still requires explicit deterministic recovery.
- Held-out retrieval collapses when exact-category owned templates are removed; relevance falls from 0.749866 to 0.386552 and category accuracy from 1.0 to 0.0.
- Visual output remains template-like; CTA prominence is 0.344038 and several category-specific compositions are aesthetically rudimentary.
- `dense_food_menu` and `restaurant_menu` regress slightly in combined heuristic score even though safety/fit/alignment gates pass.

P2

- Six rejected candidates contain 15 reported unresolved overflows; selection excludes them, all winners are clean, and truncation remains zero.
- CI reports one deprecation warning in the FastAPI/Starlette TestClient compatibility layer.
- Placeholder previews communicate editable asset intent but are not finished brand imagery.

# FINAL DECISION

v0.3_stable: true  
v0.3.1_complete: true  
v0.3.1_technically_safe: true  
visual_composition_improved: true on aggregate; human aesthetic judgment pending  
trained_runtime_ready: true for local research use  
human_review_pipeline_ready: true  
ready_for_human_review: true  
ready_for_v0.4_preference_training: false; no real human preference records exist  
production_ready: false  
commercial_allowed: false

# NEXT 3 ACTIONS

1. Complete human side-by-side review for all 13 v0.3 vs v0.3.1 comparisons and export only validated human preference pairs.
2. Replace benchmark-aligned research templates with held-out company-owned or commercially verified references, then rerun retrieval and visual evaluation.
3. Start v0.4 preference training only after enough licensed human chosen/rejected pairs exist and the two menu regressions are reviewed.

# MORNING TL;DR

v0.3.1 is a technically verified local research checkpoint; it is not production or commercial ready.  
The visual engine adds category profiles, density, palette, typography, editable assets, decoration, CTA, and business-safe placeholders.  
The trained Qwen endpoint now lazy-loads once, reuses one GPU session, and leaves the baseline endpoint unchanged.  
The final benchmark generated 52 new candidates: 0 resume, 0 cache reuse, 0 unsafe reuse.  
All 52 pass strict schema, preview, and Corel compilation; all 13 winners have zero overflow/truncation.  
Combined score improved `0.828604 -> 0.871890` (+5.224% over v0.3 clean).  
Coverage improved `0.317489 -> 0.446677`; text fit reached 1.0; overlap stayed 0.  
Dense menu uses 10 explicit item and price placeholders and contains no fake customer prices.  
The biggest problem is aesthetic maturity and weak held-out retrieval, not schema/runtime safety.  
Human preference is still false; v0.4 must not start yet.  
Open `training/artifacts/benchmarks/20260812_design_v0_3_1_clean/comparisons/v0_3_vs_v0_3_1_clean/contact_sheet_all_13.png` first.
