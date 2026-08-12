# Design AI v0.4 Phase 1.2 — Category-Focused Hardening

# RESULT

```text
start_time: 2026-08-12T08:17:05.6636062Z
end_time: 2026-08-12T08:41:06.9761641Z
duration: 00:24:01
status: WAITING_FOR_CATEGORY_PILOT_HUMAN_REVIEW
```

Engineering is complete for the bounded three-category pilot. Visual success is
not claimed: only a new human review can decide whether the both-bad rate fell.

# GIT

```text
starting_sha: ffe7c88d46272c225f40be9ae4eb89563093cb31
ending_sha: 6e8f45083748ba8d00b717d8e991a4de5f4ebfd7
remote_sha_at_implementation_push: 6e8f45083748ba8d00b717d8e991a4de5f4ebfd7
branch: agent/codex-training-bootstrap
ahead_behind_at_implementation_push: 0/0
worktree_at_implementation_push: clean
```

Commit:

```text
6e8f450 feat(training): add category-focused preference hardening
```

# HUMAN REVIEW SNAPSHOT

The snapshot was created before source changes. Original human-review files
were not rewritten.

```text
review_count: 64
A wins: 14
B wins: 10
ties: 3
both_bad: 37
both_bad_rate: 57.8125%
automated labels: 0
session_count: 4
reviews_sha256: 75f253ef068c2bf49e37095cec2e736aa0f0273569aa24b5bbff6068f09b957e
sessions_sha256: 86d425cb56319b59846e3b02aab5c1e6a4a2e1bfb7b952b7acf74c1724288c49
```

Snapshot root:

```text
training/artifacts/preference/v0_4_phase1_2_category_hardening/review_snapshot/
```

# REVIEW PROVENANCE

All 64 reviews were assigned through an exact persisted session
`queue_sha256`. No timestamp/category guessing was used.

| Queue | Generation version | Reviews | A | B | Tie | Both bad | Both-bad rate |
|---|---|---:|---:|---:|---:|---:|---:|
| `v0_4_phase1_initial_pool` | `diagnostic_generation_v1` | 44 | 11 | 5 | 2 | 26 | 59.09% |
| `v04_phase1_1_pilot` | `candidate_generation_v2_pilot` | 20 | 3 | 5 | 1 | 11 | 55.00% |

```text
exact queue-hash provenance: 64/64
unknown provenance: 0
conflicting provenance: 0
```

Category aliases were merged only when queue brief IDs established the same
design family. Examples: `poster_sale -> sale`, `bang_hieu -> signage`,
`card_visit -> business_card`, `my_pham -> cosmetics`, and
`nha_hang -> menu`. The mapping is persisted in `review_analytics.json`.

# OLD VS NEW REVIEW QUALITY

The aggregate both-bad rate moved from 59.09% in the mixed old pool to 55.00%
in the five-category Phase 1.1 pilot, a reduction of 4.09 percentage points.
This is descriptive, not a causal improvement claim, because category
composition differs.

Category-matched evidence:

| Category | Old n | Old both bad | Phase 1.1 n | Phase 1.1 both bad | Interpretation |
|---|---:|---:|---:|---:|---|
| cafe | 2 | 100% | 4 | 25% | `INSUFFICIENT_SAMPLE` |
| menu | 4 | 25% | 4 | 25% | unchanged |
| sale | 4 | 100% | 4 | 100% | no improvement |
| signage | 4 | 50% | 4 | 75% | worse descriptively |
| spa | 5 | 0% | 4 | 50% | worse descriptively |

No one supplied optional 1–10 ratings or review notes in these 64 records, so
mean quality, typography quality, hierarchy quality and brand-feeling means are
`INSUFFICIENT_SAMPLE`; they were not invented.

Measured candidate-pool changes from old generation to Phase 1.1:

| Metric | Old pool | Phase 1.1 pilot |
|---|---:|---:|
| content consistency | 0.10 | 1.00 |
| asset consistency | 1.00 | 1.00 |
| business-value consistency | 0.90 | 1.00 |
| mean structural diversity | 0.010871 | 0.548542 |
| minimum structural diversity | 0.000000 | 0.355490 |
| placeholder count | 204 | 0 |
| technical pass rate | 1.00 | 1.00 |

The technical/diversity improvements did not produce an acceptable Phase 1.1
human both-bad rate.

# CATEGORY FAILURE RANKING

Combined normalized ranking is retained for future work. Categories with fewer
than three decisions are low confidence.

| Category | Reviews | Both bad | Rate | Sample status |
|---|---:|---:|---:|---|
| sale | 8 | 8 | 100.00% | eligible |
| cosmetics | 7 | 6 | 85.71% | eligible; old queue only |
| nail | 4 | 3 | 75.00% | eligible; old queue only |
| social_banner | 3 | 2 | 66.67% | eligible; old queue only |
| signage | 8 | 5 | 62.50% | eligible |
| business_card | 8 | 4 | 50.00% | eligible; old queue only |
| cafe | 6 | 3 | 50.00% | eligible |
| menu | 8 | 2 | 25.00% | eligible |
| spa | 9 | 2 | 22.22% | eligible |
| milk_tea | 1 | 1 | 100.00% | low confidence |
| opening | 2 | 1 | 50.00% | low confidence |

The Phase 1.2 pilot selection is made within the controlled
`candidate_generation_v2_pilot`, where each of the five categories has exactly
four decisions and a Phase 1.1 candidate group is available for fair visual
comparison:

| Phase 1.1 category | Reviews | Both bad | Rate |
|---|---:|---:|---:|
| sale | 4 | 4 | 100% |
| signage | 4 | 3 | 75% |
| spa | 4 | 2 | 50% |
| cafe | 4 | 1 | 25% |
| menu | 4 | 1 | 25% |

# SELECTED 3 CATEGORIES

1. `sale`: worst controlled pilot result, 4/4 both bad; also 8/8 across the
   normalized mixed dataset.
2. `signage`: 3/4 both bad in the controlled pilot and 5/8 across normalized
   history.
3. `spa`: 2/4 both bad in the controlled pilot. Although its combined historic
   rate is lower, the latest controlled version regressed from the older sample.

`cosmetics` and `nail` remain important old-pool failures, but neither had a
Phase 1.1 v2 pilot group. Selecting them here would mix generator versions and
would make the required Phase 1.1-vs-Phase 1.2 comparison unavailable.

# FAILURE DIAGNOSIS

## Sale

- HUMAN-SUPPORTED: 4/4 Phase 1.1 comparisons were `both_bad`; 8/8 after safe
  alias normalization.
- MEASURED: content/assets/discount/CTA were locked, placeholders were zero and
  technical checks passed, so broken data was not the explanation.
- INFERRED: the Phase 1.1 contact sheet separated product, offer, headline and
  CTA into weakly related boxes. The correction uses bounded product-dominant,
  type-dominant, asymmetric and split campaign clusters. This inference is not
  reported as a human typography judgment.

## Signage

- HUMAN-SUPPORTED: 3/4 Phase 1.1 comparisons were `both_bad`.
- MEASURED: the project-owned logo remained available, no placeholders were
  present, and all candidates passed technical checks.
- INFERRED: identity and tagline lacked a strong signboard relationship. The
  correction adds distance-oriented logo/name mass, monument framing and
  explicit logo contrast panels. A light-background logo contrast defect found
  during artifact inspection was repaired before the final pilot was emitted.

## Spa

- HUMAN-SUPPORTED: 2/4 Phase 1.1 comparisons were `both_bad`; the five old
  normalized spa reviews had no both-bad result, so the latest controlled group
  is a regression signal.
- MEASURED: authorized hero/logo assets and all factual copy were stable, while
  all four candidates were technically safe.
- INFERRED: Phase 1.1 leaned on repeated split layouts. The correction adds
  editorial image-led, full-bleed restrained, asymmetric luxury and panoramic
  signature compositions. This remains a hypothesis pending human review.

# IMPLEMENTATION

Phase 1.2 introduces a bounded `CategoryArtDirectionProfileV2` only for the
three selected categories. `cafe` and `menu` rules were not changed.

- Art direction: category-specific hero/whitespace/headline/CTA ranges and
  surface strategies.
- Typography: refined serif/sans for spa, condensed campaign sans for sale and
  distance-oriented sans for signage; Vietnamese content is preserved and
  passed through the existing fitting engine.
- Composition families: four distinct families per category.
- Quality floor: transparent reasons include technical failure, weak focal
  point, excessive unused space, disconnected CTA, weak headline, unintended
  fragmentation, undersized asset, poor visual-mass balance and dominant
  placeholders.
- Asset handling: reuses authorized/project-owned v0.3.3 assets; no scraping or
  new copyrighted assets.
- Safety: content, asset, business value and canvas hashes must match across all
  four candidates.

`both_bad` remains a generator-failure diagnostic and is never exported as a
chosen/rejected pair.

# MINI PILOT

```text
category count: 3
brief count: 3
candidate count: 12
review pair count: 12
generation version: candidate_generation_v3_category_hardened
quality floor: category_quality_floor_v2
full pool regenerated: false
```

| Category | Content lock | Asset lock | Business-value lock | Families | Mean diversity | Min diversity | Technical safe | Placeholders |
|---|---|---|---|---:|---:|---:|---|---:|
| sale | pass | pass | pass | 4 | 0.603980 | 0.387951 | 4/4 | 0 |
| signage | pass | pass | pass | 4 | 0.581684 | 0.391614 | 4/4 | 0 |
| spa | pass | pass | pass | 4 | 0.685720 | 0.628148 | 4/4 | 0 |

Final safety audit:

```text
strict schema: 12/12
Corel compile: 12/12
max outside canvas: 0
max overlap: 0
minimum text-fit rate: 1.0
content/asset/business/canvas locks: 100%
```

# CONTACT SHEETS

```text
training/artifacts/preference/v0_4_phase1_2_category_hardening/mini_pilot_contact_sheet.png
training/artifacts/preference/v0_4_phase1_2_category_hardening/old_vs_new_contact_sheet.png
```

The old-vs-new sheet uses equal scales and exposes all four candidates on each
side. It is an audit artifact, not a human preference label.

# REVIEW QUEUE

```text
queue_id: v04_phase1_2_category_pilot
path: training/artifacts/preference/v0_4_phase1_2_category_hardening/review_queue/review_queue.jsonl
pair_count: 12
blinded: true
generation_version_hidden_in_UI: true
```

Launch only this queue:

```powershell
cd D:\codex\coreldraw-ai-plugin
python -m training.tools.human_review_server --queue v04_phase1_2_category_pilot --port 8004
```

Open:

```text
http://127.0.0.1:8004/review
```

# TESTS

```text
focused pytest: 44 passed
full pytest: 241 passed, 1 deprecation warning
compileall training tests: pass
git diff --check: pass
GitHub CI Python 3.10: success
GitHub CI Python 3.11: success
GitHub CI Python 3.12: success
```

GitHub Actions runs `31579447524` and `31579440665` both completed successfully
for implementation SHA `6e8f450`.

# TRAINING STATUS

```text
human_reviews_preserved: true

ready_for_preference_training: false
preference_model_trained: false

full_pool_regenerated: false
v0.4_complete: false
production_ready: false
commercial_allowed: false
```

The Qwen checkpoint/reference lineage remains research-only. Candidate assets
used here are authorized/project-owned, but that does not upgrade the model or
reference corpus commercial status.

# HUMAN REVIEW STATUS

```text
WAITING_FOR_CATEGORY_PILOT_HUMAN_REVIEW
```

The engineering gate passed. The human gate is deliberately unresolved. A real
reviewer must determine whether both-bad is at most 25%, mean overall quality is
at least 6/10, and the new groups are visibly stronger.

# NEXT 3 ACTIONS

1. Review all 12 blinded Phase 1.2 pairs and enter overall quality where
   practical.
2. Re-run provenance analytics on the isolated queue and evaluate the human
   both-bad/quality/diversity gate without mixing legacy generations.
3. Only if that gate passes, prepare a broader candidate pool; keep preference
   training blocked until the separate minimum human-data gate is satisfied.
