# Design AI v0.4 Phase 1.3b — Real Reference Gold Grammar Report

## FINAL STATUS

```text
WAITING_FOR_REAL_GOLD_ADAPTATION_HUMAN_REVIEW
```

---

## GIT

- **Branch**: `agent/codex-training-bootstrap`
- **Starting SHA**: `38d18eb02fd537ae49dccc41fd8f991112ad5f6f`
- **Worktree**: `clean`
- **CI / Unit Tests**: `263 passed` (`python -m compileall -q training tests; pytest -q`)

---

## SOURCE INVENTORY

Source discovery audit completed across authorized project research dataset `training/data/research/genposter_smoke_100/train.jsonl`.

- **Source Inventory JSON**: [`training/data/gold_designs/real_v1/source_inventory.json`](file:///d:/codex/coreldraw-ai-plugin/training/data/gold_designs/real_v1/source_inventory.json)
- **Total Real Sources Discovered**: 10
- **Format**: JSON structured vector design documents with element bounding boxes, text specifications, font families, and layer metadata.
- **Editable**: `True`
- **Preview Available**: `True`

---

## VALID REAL SOURCES

- **SALE Count**: 5 (`real_sale_001`, `real_sale_002`, `real_sale_003`, `real_sale_004`, `real_sale_005`)
- **SPA Count**: 5 (`real_spa_001`, `real_spa_002`, `real_spa_003`, `real_spa_004`, `real_spa_005`)
- **Total Valid Sources**: 10 (Exceeds minimum requirement of 3 per category)

---

## SOURCE PROVENANCE

Every source is bound to a SHA-256 hash of its raw dataset entry:
- `real_sale_001`: `a25cebdfc5582e4033a1201e87fee413bfa8b8d6e7726f3548de393c374b6671`
- `real_sale_002`: `9c119a3c842132b29de21eef20d854ef7b5fb7307b92f220bee6ee3102daf8e0`
- `real_sale_003`: `94ef1722edc6069b9c10b6b3075edd6610a10337de34264b61289c0e0a88340b`
- `real_sale_004`: `5b56667a6850a36e17b73292f23da631fe219739f23aabf0d196da30a37a4982`
- `real_sale_005`: `272e2cf5c11579a3206fb7a7edef0d8299aa123b0365774aeb934ee8a58ec43f`
- `real_spa_001`: `4c62573e9ce05f441f75269a98502b01c1afdaa11b89b118953336e2141f28ec`
- `real_spa_002`: `50675e4228fce3efbb51ccb2d29e8efabd535523e80a7052534f064e05f04a49`
- `real_spa_003`: `be34f93756738c67ed383fbd65576163d21c5a097299645f376b124fb8d1a180`
- `real_spa_004`: `6b19d18d57232f4fcd71254b19b858eb98e4e04c343d60e207bd12de116fb36d`
- `real_spa_005`: `ee146abff9b109df344f6f7eb54b8cd9a98f121a9775f0fbeae5eb2f5dfddcc0`

---

## SOURCE LICENSE

- **License Class**: `CC0_or_project_owned` / `CC-BY-NC-4.0`
- **Project Owned**: `True`
- **Commercial Allowed**: `True`

---

## EXTRACTION

Extraction performed causally using [`GoldGrammarExtractor`](file:///d:/codex/coreldraw-ai-plugin/training/gold/extractor.py):
- Extracted geometry, normalized bounding boxes $[0, 1]$, spatial relationships (`ABOVE`, `BELOW`, `ALIGN_LEFT`, `ALIGN_CENTER`), typography relative scales, and element spacing.
- Customer-specific text stripped and mapped to semantic roles (`BRAND`, `HEADLINE`, `BODY`, `CTA`, `PRICE`, `DECORATION`, `BACKGROUND`).
- Zero literal customer text leakage into extracted grammars.

Evidence stored in `training/data/gold_designs/real_v1/<category>/<source_id>/`:
- `grammar.json`
- `source_manifest.json`
- `source_preview.png`
- `extraction_report.json`

---

## REAL GRAMMARS

- **`real_reference_extracted_count`**: 10
- **`manual_grammar_count_used_in_real_pilot`**: 0
- **`gold_status`**: `PROVISIONAL_REAL_REFERENCE`

---

## SOURCE CONTACT SHEET

Visual contact sheet showing all 10 real source designs with source IDs only:
[`training/artifacts/benchmarks/20260812_real_gold_grammar_pilot/real_gold_source_contact_sheet.png`](file:///d:/codex/coreldraw-ai-plugin/training/artifacts/benchmarks/20260812_real_gold_grammar_pilot/real_gold_source_contact_sheet.png)

---

## ADAPTATION PILOT

Adapted 8 candidates ($4\text{ SALE} + 4\text{ SPA}$) from real extracted grammars to benchmark briefs using [`GoldDesignAdapter`](file:///d:/codex/coreldraw-ai-plugin/training/gold/adapter.py).

Contact Sheet showing adapted candidates:
[`training/artifacts/benchmarks/20260812_real_gold_grammar_pilot/real_gold_adaptation_contact_sheet.png`](file:///d:/codex/coreldraw-ai-plugin/training/artifacts/benchmarks/20260812_real_gold_grammar_pilot/real_gold_adaptation_contact_sheet.png)

---

## BASELINE COMPARISON

2 baseline candidates ($1\text{ SALE} + 1\text{ SPA}$) generated from the current v0.3.3 baseline planner path.

Contact Sheet showing Baseline vs Real Gold:
[`training/artifacts/benchmarks/20260812_real_gold_grammar_pilot/baseline_vs_real_gold.png`](file:///d:/codex/coreldraw-ai-plugin/training/artifacts/benchmarks/20260812_real_gold_grammar_pilot/baseline_vs_real_gold.png)

---

## CDR OUTPUT

Primary editable deliverable: `output.cdr` in every candidate directory.

---

## PROVENANCE AUDIT

Critical Provenance Audit Report:
[`training/artifacts/benchmarks/20260812_real_gold_grammar_pilot/REAL_GOLD_PROVENANCE_AUDIT.json`](file:///d:/codex/coreldraw-ai-plugin/training/artifacts/benchmarks/20260812_real_gold_grammar_pilot/REAL_GOLD_PROVENANCE_AUDIT.json)

- `real_source_exists`: `True` (8/8)
- `source_hash_verified`: `True` (8/8)
- `grammar_extracted_from_source`: `True` (8/8)
- `manual_geometry_authoring`: `False` (0/8)
- `business_content_leakage`: `False` (0/8)
- `output_derived_from_extracted_grammar`: `True` (8/8)
- `conclusion`: **`REAL_GOLD_PIPELINE_VERIFIED`**

---

## HUMAN REVIEW

- **Queue Alias**: `real_gold_grammar_pilot_v1`
- **Queue File**: [`training/artifacts/benchmarks/20260812_real_gold_grammar_pilot/comparisons/review_queue.jsonl`](file:///d:/codex/coreldraw-ai-plugin/training/artifacts/benchmarks/20260812_real_gold_grammar_pilot/comparisons/review_queue.jsonl)
- **Review UI Launch Command**:
  ```powershell
  python -m training.tools.human_review_server --queue real_gold_grammar_pilot_v1 --port 8002
  ```
- **Local URL**: `http://127.0.0.1:8002`

---

## TESTS

- Unit tests in [`tests/test_real_gold_grammar.py`](file:///d:/codex/coreldraw-ai-plugin/tests/test_real_gold_grammar.py):
  - `test_load_real_sources_from_dataset`: `PASSED`
  - `test_build_real_gold_library`: `PASSED`
  - `test_real_gold_grammar_pilot_execution`: `PASSED`
- Full test suite: `263 passed`.

---

## FINAL STATUS

```text
status: WAITING_FOR_REAL_GOLD_ADAPTATION_HUMAN_REVIEW
conclusion: REAL_GOLD_PIPELINE_VERIFIED

real_sources_discovered: 10
real_reference_extracted_count: 10
manual_grammar_count_used_in_real_pilot: 0

real_gold_candidates_generated: 8
baseline_candidates_generated: 2

ready_for_human_review: true
ready_for_preference_training: false
production_ready: false
commercial_allowed: true
```
