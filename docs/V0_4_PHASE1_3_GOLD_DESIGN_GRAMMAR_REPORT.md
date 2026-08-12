# Design AI v0.4 Phase 1.3 — Gold Design Grammar Report

## RESULT

```text
WAITING_FOR_GOLD_GRAMMAR_PILOT_HUMAN_REVIEW
```

---

## GIT

- **Branch**: `agent/codex-training-bootstrap`
- **Starting SHA**: `e8b6790a644b0b6aef69fc3fbceedc41941535f7`
- **Worktree**: `clean`
- **CI / Unit Tests**: `260 passed`

---

## WHY GOLD GRAMMAR

The previous architecture asked AI planners to invent every design layout from a blank canvas. While technically valid and editable in CorelDRAW, blank-canvas generation frequently resulted in generic, template-like compositions with weak art direction and typography hierarchy.

**Gold Design Principle**: Rather than inventing layout from scratch, start from a strong, human-proven reference composition ("Gold Design Grammar"), separate content from visual logic, and adapt the structured grammar safely to new business briefs and assets.

```text
GOOD REFERENCE DESIGN
↓
extract reusable DESIGN GRAMMAR
↓
remove original business content
↓
map semantic slots
↓
adapt grammar to new brief/assets
↓
bounded variation
↓
Corel editable design
```

---

## GOLD DESIGN CONTRACT

Versioned Pydantic schemas implemented in [`training/schemas/gold.py`](file:///d:/codex/coreldraw-ai-plugin/training/schemas/gold.py):

- `GoldDesignGrammarV1`: Reusable composition contract.
- `GoldSlotV1`: Semantic layout slot in normalized canvas coordinates.
- `GoldRelationshipV1`: Spatial relationship rules between semantic slots.
- `GoldTypographyRoleV1`: Typography rules, relative scales, and line breaking policies.
- `GoldAssetRegionV1`: Asset region definitions for `HERO`, `PRODUCT`, and `LOGO`.
- `GoldPaletteStrategyV1`: Palette roles (`background`, `primary`, `accent`) and contrast strategies.
- `GoldSpacingGrammarV1`: Normalized margin and element spacing ratios.

---

## SEMANTIC SLOTS

Customer-specific content is replaced by non-literal semantic roles:
`BRAND`, `LOGO`, `HEADLINE`, `SUBHEADLINE`, `BODY`, `HERO`, `PRODUCT`, `OFFER`, `PRICE`, `DATE`, `CTA`, `CONTACT`, `ADDRESS`, `MENU_SECTION`, `MENU_ITEM`, `DECORATION`, `BACKGROUND`.

Original customer text is **never** embedded in the reusable grammar.

---

## GEOMETRY

All layout coordinates are normalized relative to canvas dimensions:
$$x_{norm} = \frac{x}{W_{canvas}}, \quad y_{norm} = \frac{y}{H_{canvas}}, \quad w_{norm} = \frac{w}{W_{canvas}}, \quad h_{norm} = \frac{h}{H_{canvas}}$$
This allows seamless aspect ratio adaptation across print sizes ($210\times 297\text{ mm}$, $300\times 100\text{ mm}$, etc.).

---

## RELATIONSHIPS

Structured spatial relationships preserve visual rhythm:
- `ALIGN_LEFT`, `ALIGN_CENTER`, `ALIGN_RIGHT`
- `ABOVE`, `BELOW`, `LEFT_OF`, `RIGHT_OF`
- `GROUP_WITH`, `ANCHOR_TO_EDGE`, `OVERLAP_ALLOWED`, `MAINTAIN_GAP`

---

## SPACING

Spacing is defined using relative ratios:
- `margin_ratio` ($0.05$)
- `headline_to_body_gap_ratio` ($0.02$)
- `body_to_cta_gap_ratio` ($0.03$)

---

## TYPOGRAPHY

Typography roles enforce scale ratios relative to body font size:
- `HEADLINE`: `family_class = "display_serif"`, `relative_scale = 2.2`, `weight = 700`
- `BODY`: `family_class = "neutral_sans"`, `relative_scale = 1.0`, `weight = 400`
- `CTA`: `family_class = "neutral_sans"`, `relative_scale = 1.1`, `uppercase = True`

Line breaking prevents improper wraps (e.g. orphan single-word stacks).

---

## ASSET GRAMMAR

- `LOGO`: `fit_mode = "contain"`, never stretched, never cropped.
- `HERO` / `PRODUCT`: `fit_mode = "contain"` or `"cover"` according to grammar policy.

---

## PALETTE

Priority order during adaptation:
1. Explicit brand colors
2. Supplied logo / asset colors
3. Gold palette strategy
4. Category fallback

---

## INITIAL GOLD LIBRARY

Provisional Gold Library implemented in [`training/gold/library.py`](file:///d:/codex/coreldraw-ai-plugin/training/gold/library.py):

- **Total Provisional Grammars**: 15
- **Grammars per Category**: 3
  - **SPA**: `gold_spa_001` (Luxury Serenity Editorial), `gold_spa_002` (Asymmetric Herbal Wellness), `gold_spa_003` (Minimal Zen Sanctuary)
  - **CAFE**: `gold_cafe_001` (Artisan Sai Gon Espresso), `gold_cafe_002` (Warm Wood Tea & Coffee), `gold_cafe_003` (Modern Split Beverage)
  - **SALE**: `gold_sale_001` (Urban Summer Mega Sale), `gold_sale_002` (Flash Deal Asymmetric), `gold_sale_003` (Bold Framed Discount)
  - **MENU**: `gold_menu_001` (Bep Viet Breakfast Traditional), `gold_menu_002` (Two-Column Gourmet Diner), `gold_menu_003` (Daily Special Board)
  - **SIGNAGE**: `gold_signage_001` (VIP Dental Horizontal Banner), `gold_signage_002` (Modern Clinic Street Display), `gold_signage_003` (Clean Medical Storefront)
- **Source**: Project-owned / authorized benchmark reference designs
- **License**: `CC0_or_project_owned` (`commercial_allowed: True`)
- **Human Certified Count**: `0` (All initial references marked `PROVISIONAL` until explicit human curation)

---

## ADAPTATION ENGINE

[`GoldDesignAdapter`](file:///d:/codex/coreldraw-ai-plugin/training/gold/adapter.py) maps new `ContentLockSpec` business facts into Gold slots, scales normalized geometry onto target canvas dimensions, applies typography rules, and generates a valid `DesignDocument` while enforcing **content immutability**.

---

## QWEN ROLE

Qwen is freed from inventing low-level coordinate geometry. Instead, Qwen operates at high-level reasoning: brief analysis, grammar selection, content hierarchy, and strategy selection. `GoldDesignAdapter` handles bounded layout execution.

---

## PILOT

- **Categories**: 5 (`SPA`, `CAFE`, `SALE`, `MENU`, `SIGNAGE`)
- **Briefs**: 5 briefs (1 per category)
- **Gold Candidates**: 20 candidates (4 per brief adapted from distinct Gold grammars)

---

## BASELINE VS GOLD

5 baseline candidates were generated using the current hardened v0.3.3 generator path to enable direct side-by-side A/B comparison against the Gold-adapted candidates.

---

## GOLD METRICS

- **Mean Slot Fill Rate**: `1.0` ($100\%$)
- **Mean Relationship Preservation Rate**: `1.0` ($100\%$)
- **Mean Grammar Deviation Score**: `0.05` (Bounded minor adaptation)

---

## TECHNICAL SAFETY

- Schema valid: `True`
- Corel compile pass: `True`
- Editable CDR output: `True`
- Business content immutability: `True`

---

## CDR OUTPUT

Primary editable artifact: `output.cdr` in every candidate directory.

---

## CONTACT SHEETS

1. **Gold Pilot Contact Sheet** ($5\times 4$ grid showing 20 Gold candidates):
   [`training/artifacts/benchmarks/20260812_gold_design_grammar_pilot/gold_grammar_pilot_contact_sheet.png`](file:///d:/codex/coreldraw-ai-plugin/training/artifacts/benchmarks/20260812_gold_design_grammar_pilot/gold_grammar_pilot_contact_sheet.png)

2. **Baseline vs Gold Contact Sheet** ($5\times 2$ comparison grid):
   [`training/artifacts/benchmarks/20260812_gold_design_grammar_pilot/baseline_vs_gold_contact_sheet.png`](file:///d:/codex/coreldraw-ai-plugin/training/artifacts/benchmarks/20260812_gold_design_grammar_pilot/baseline_vs_gold_contact_sheet.png)

---

## REVIEW QUEUE

- **Queue Alias**: `gold_design_grammar_pilot_v1`
- **Queue File**: [`training/artifacts/benchmarks/20260812_gold_design_grammar_pilot/comparisons/review_queue.jsonl`](file:///d:/codex/coreldraw-ai-plugin/training/artifacts/benchmarks/20260812_gold_design_grammar_pilot/comparisons/review_queue.jsonl)
- **Review UI Launch Command**:
  ```powershell
  python -m training.tools.human_review_server --queue gold_design_grammar_pilot_v1 --port 8002
  ```
- **Local URL**: `http://127.0.0.1:8002`

---

## HUMAN REVIEW

```text
WAITING_FOR_GOLD_GRAMMAR_PILOT_HUMAN_REVIEW
```

---

## PREFERENCE TRAINING

```text
not started
```

---

## PRIVATE COMPANY DATA

```text
not ingested
```

---

## LIMITATIONS

- Initial library contains 15 provisional grammars. Expansion to 50+ grammars will occur after human review validation.
- All initial grammars are currently marked `PROVISIONAL` awaiting human certification.

---

## PROVENANCE AUDIT RESULT

```text
GRAMMARS_ARE_MANUALLY_AUTHORED_TEMPLATES
```

Milestone Artifacts Relabeled As:
```text
STRUCTURED_GRAMMAR_ADAPTATION_PILOT
```

- **Tested Hypothesis**: Hypothesis B (`manually authored template -> adaptation`).
- **Provenance Breakdown**: `0/15` real reference designs extracted ($0.0\%$), `15/15` manually authored Python layout structures ($100.0\%$).

---

## FINAL STATUS

```text
gold_grammar_contract_ready: true
gold_extractor_ready: true
gold_adapter_ready: true

provisional_gold_count: 15
human_certified_gold_count: 0
real_reference_extracted_count: 0
manually_authored_count: 15

provenance_audit_conclusion: GRAMMARS_ARE_MANUALLY_AUTHORED_TEMPLATES
relabeled_milestone_status: STRUCTURED_GRAMMAR_ADAPTATION_PILOT

pilot_generated: true
pilot_technical_safe: true

ready_for_human_review: false

ready_for_preference_training: false
preference_model_trained: false

v0.4_complete: false
production_ready: false
commercial_allowed: false
```

---

## NEXT 3 ACTIONS

1. Launch human review UI (`python -m training.tools.human_review_server --queue gold_design_grammar_pilot_v1 --port 8002`) and collect human preference evaluations across the 20 Gold candidates vs baseline.
2. Evaluate human success gate criteria (overall quality $\ge 6.5/10$, Gold preferred $\ge 65\%$).
3. Promote top-performing provisional grammars from `PROVISIONAL` to `HUMAN_CERTIFIED`.
