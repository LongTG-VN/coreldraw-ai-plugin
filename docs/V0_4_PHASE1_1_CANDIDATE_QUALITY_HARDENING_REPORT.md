# Design AI v0.4 Phase 1.1 — Candidate Quality Hardening

## RESULT

- `start_time`: `2026-08-12T14:27:00+07:00`
- `end_time`: `2026-08-12T15:00:52+07:00`
- `duration`: 33 minutes 52 seconds
- `status`: `WAITING_FOR_PILOT_HUMAN_REVIEW`

The generator now produces four content-locked, asset-locked and structurally distinct compositions for each of five pilot briefs. All 20 designs passed strict schema, Corel compilation, bounds, overlap and text-fit gates. Human visual improvement is deliberately not claimed before the pilot is reviewed.

## GIT

- `starting_sha`: `d0332bd56c7d5de030f4d948030aca93e5ed27ee`
- `ending_sha`: recorded by final Git handoff
- `remote_sha`: recorded after push
- `ahead_behind`: recorded after push
- `worktree`: recorded after final verification
- branch: `agent/codex-training-bootstrap`

## OLD HUMAN REVIEW SNAPSHOT

- review count: 44
- actual ratings available: 0
- A wins: 11
- B wins: 5
- ties: 2
- both bad: 26 (59.09%)
- notes available: 0
- categories represented: 15
- reviewer distribution: `long: 44`
- snapshot class: `diagnostic_generation_v1`
- snapshot SHA-256: `da646f1225da115c94078a7bb6356c7a4a37cee04be6af52885fad231799ff6c`
- `user_reported_overall_quality`: approximately 4/10

The 4/10 value is user-reported pool-level diagnostic feedback, not a per-candidate ground-truth label. The snapshot is immutable and is not marked eligible for preference training.

## OLD POOL DIAGNOSIS

Measured over 20 four-candidate groups:

| Metric | Old pool |
|---|---:|
| Content consistency | 10% |
| Asset consistency | 100% |
| Business-value consistency | 90% |
| Canvas consistency | 100% |
| Mean layout families per brief | 1.0 |
| Mean pairwise structural diversity | 0.010871 |
| Minimum pairwise structural diversity | 0.0 |
| Placeholder count | 204 |
| Mean placeholder-area ratio | 0.179000 |
| Technical pass rate | 100% |

Human evidence is limited to the 59.09% both-bad rate and pool-level 4/10 report. The content, diversity, and placeholder findings above are deterministic measurements, not inferred human complaints.

## IMPLEMENTATION

- `CandidateInvariantV1` locks brief/category/canvas, business name, headline, subheadline, body, CTA, prices, discounts, offers, dates, menu data, assets, asset hashes and explicit colors.
- `content_lock_hash`, `asset_lock_hash`, `business_value_hash`, and `canvas_hash` must match across all four candidates.
- `CandidateStyleVariantV1` contains design-only decisions; it has no factual-copy fields.
- Category-aware composition families provide editorial, split, asymmetric, image/type-dominant, modular, centered and edge-aligned options.
- Structural diversity measures family, hero, headline and CTA geometry. Generic image embeddings are not used.
- The quality floor reports transparent reasons including technical failure, excessive whitespace, weak hero, placeholder dominance, and broken text rhythm.
- Regeneration is capped at 3–5 attempts; the pilot used a cap of 3. It must emit `CANDIDATE_POOL_INSUFFICIENT` instead of silently inserting duplicates.
- Typography variants use installed DejaVu serif/sans/condensed fallbacks, preserve Vietnamese, restore pre-fit content, and run deterministic glyph fitting.
- Hero/product/logo geometry changes by composition family while asset hashes and aspect intent remain fixed.
- The successful v0.3.3 asset-aware artifacts and v0.3.2 hardening lineage are used. Failed visual RAG and vision critic paths remain disabled.
- Pilot reviews are tagged `candidate_generation_v2_pilot`; old reviews remain `diagnostic_generation_v1`.

## PILOT

- brief count: 5
- candidate count: 20
- review comparisons: 20
- categories: SPA, CAFE, SALE, MENU, SIGNAGE
- real/project-owned authorized assets used: yes
- placeholder count: 0
- strict content/asset/business/canvas lock rate: 100%
- technical pass rate: 100%

| Category | Layout families | Mean diversity | Minimum diversity | Locks | Technical safety |
|---|---|---:|---:|---|---|
| SPA | editorial, split-left, asymmetric, image-dominant | 0.577143 | 0.393850 | pass | pass |
| CAFE | editorial, split-right, asymmetric, image-dominant | 0.566740 | 0.473780 | pass | pass |
| SALE | image-dominant, type-dominant, asymmetric, split-left | 0.624408 | 0.402660 | pass | pass |
| MENU | editorial, modular, split-right, centered grid | 0.364395 | 0.355490 | pass | pass |
| SIGNAGE | split-left, centered, type-dominant, edge-aligned | 0.610023 | 0.417000 | pass | pass |

SALE discount and MENU prices are explicit project benchmark sample data with `customer_provided: false`. They are locked across variants and are not represented as customer facts.

## OLD VS PILOT STRUCTURAL QUALITY

| Metric | Old | Pilot |
|---|---:|---:|
| Content consistency | 0.10 | 1.00 |
| Asset consistency | 1.00 | 1.00 |
| Business-value consistency | 0.90 | 1.00 |
| Canvas consistency | 1.00 | 1.00 |
| Mean layout-family count | 1.0 | 4.0 |
| Mean pairwise diversity | 0.010871 | 0.548542 |
| Minimum pairwise diversity | 0.0 | 0.355490 |
| Placeholder count | 204 | 0 |
| Mean placeholder-area ratio | 0.179000 | 0.0 |
| Technical pass rate | 1.00 | 1.00 |

This proves that the generator contract changed materially. It does not prove that humans rate the new designs at 6/10 or better.

## PILOT CONTACT SHEET

`D:\codex\coreldraw-ai-plugin\training\artifacts\preference\v0_4_phase1_1_candidate_hardening\pilot_contact_sheet_5x4.png`

The sheet was visually audited during implementation for hidden text, contrast, asset presentation, and visibly distinct composition. It is still awaiting the user's judgment.

## PILOT REVIEW

- queue: `v04_phase1_1_pilot`
- pair count: 20
- blind A/B: enabled and persisted by session
- optional prominent `overall_quality`: 1–10
- optional composition, hierarchy, typography, brand feeling, note, and confidence fields: enabled
- human labels collected at artifact creation: 0
- status: `WAITING_FOR_PILOT_HUMAN_REVIEW`
- browser smoke: 20-pair progress, equal A/B imagery, 1–10 overall-quality control and blind metadata verified; no choice was submitted

Launch command:

```powershell
python -m training.tools.human_review_server --queue v04_phase1_1_pilot --port 8003
```

Open `http://127.0.0.1:8003/review`.

## TESTS

- focused contracts/UI tests: 31 passed
- full `pytest`: 228 passed; one existing Starlette/httpx deprecation warning
- `python -m compileall -q training tests`: passed
- `git diff --check`: passed
- GitHub CI: recorded after push; it uses deterministic fixtures and does not download Qwen/assets or require GPU/human reviews

## TRAINING STATUS

- `old_human_reviews_preserved`: true (44)
- `pilot_ready_for_review`: true
- `ready_for_preference_training`: false
- `preference_model_trained`: false
- `v0.4_complete`: false
- `production_ready`: false
- `commercial_allowed`: false

## FULL POOL STATUS

- `full_candidate_pool_regenerated`: false
- reason: waiting for the pilot human quality gate (guidance: mean quality at least 6/10, both-bad at most 25%, and materially improved diversity reported by the reviewer)

## NEXT 3 ACTIONS

1. Launch the isolated pilot queue and review its 20 blinded comparisons.
2. Check actual human mean quality, both-bad rate, and written diversity feedback against the pilot gate.
3. Only after the human gate passes, generate the 30–50 brief `candidate_generation_v2` pool; otherwise harden the weak categories again.
