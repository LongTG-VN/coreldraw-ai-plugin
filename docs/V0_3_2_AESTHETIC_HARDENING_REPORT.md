# Design AI v0.3.2 — Aesthetic Hardening Report

## RESULT

- start_time: `2026-08-12T06:40:14.9298367+07:00`
- end_time: `2026-08-12T06:51:53.6019920+07:00`
- duration: `00:11:38.6721553` (implementation artifact creation through verified source push)
- result: deterministic aesthetic hardening completed for all 13 current v0.3.1 winners

## GIT

- starting_sha: `b0d689f05f73e1159dcd1f1d2e38dc8e3ccf7dd3`
- ending_sha: `8ccfec35e311948611d9b62950811e387538da99` (validated implementation checkpoint; this report is committed separately)
- branch: `agent/codex-training-bootstrap`
- push_status: success; `8ccfec3` pushed to `origin/agent/codex-training-bootstrap`

## WHAT CHANGED

- Placeholder presentation: replaced the dominant full-frame X with a thin editable frame, muted single diagonal, small image glyph, and explicit `PHOTO`/`LOGO` caption. No real asset is fabricated.
- Typography: deterministic category mapping now uses bundled/open fallback classes (`DejaVuSerif`, `DejaVuSans`, and `DejaVuSansCondensed`) with stronger headline/body/CTA role contrast.
- CTA: existing CTA copy receives a higher-contrast editable container and restrained depth accent. No CTA copy is invented. Menu contact rows use a quieter footer treatment.
- Campaign styling: sale and grand-opening layouts receive an editable headline panel, campaign edge, ribbon, and stronger headline box while preserving provided dates/offers.
- Menu polish: alternating editable row surfaces, a price rail, right-aligned price typography, and a contact footer improve scanning without inserting prices.
- Signage polish: dark layouts receive bounded edge framing and a softer logo/photo placeholder treatment.
- Other refinements: premium rules/corners and friendly category accents are bounded behind content, remain editable, and do not affect overlap metrics.
- Preview quality: optional deterministic upscaling renders comparison artifacts clearly without changing the default renderer behavior.

## ARTIFACT REPLAY

- 13 prompts replayed: yes
- artifact root: `training/artifacts/benchmarks/20260812_design_v0_3_2_aesthetic_hardening/`
- contact sheet: `training/artifacts/benchmarks/20260812_design_v0_3_2_aesthetic_hardening/contact_sheet_all_13.png`
- HTML index: `training/artifacts/benchmarks/20260812_design_v0_3_2_aesthetic_hardening/index.html`
- per-prompt comparisons: `training/artifacts/benchmarks/20260812_design_v0_3_2_aesthetic_hardening/runs/<prompt_id>/comparison.html`
- model generations used by replay: `0`
- scorer changed: no
- human preference collected: no

## VISUAL SUMMARY

- `business_card`: softer editable logo frame and intentional edge rails improve presentation; identity typography is still generic and source content is minimal.
- `cafe_vintage`: warmer corner/orb accents, cleaner photo frame, and stronger CTA depth improve the social-poster feel; the remaining copy stack is still mechanically centered.
- `cosmetics_clean`: the refined photo placeholder, premium rule, and CTA depth make the layout cleaner; it remains sparse without real product photography.
- `dense_food_menu`: alternating row grouping, consistent price rail, right-aligned prices, and quieter contact footer make scanning materially easier; explicit item/description/price placeholders still limit aesthetic realism.
- `grand_opening`: a framed one-line headline, campaign edge, photo treatment, and bottom ribbon create the clearest campaign improvement; the layout still depends heavily on the missing photo.
- `milk_tea_social`: playful accents, softer product-photo frame, and stronger CTA improve social energy; composition remains simple.
- `nail_pastel`: premium rule, softer photo frame, and CTA depth feel more polished; art direction remains conservative.
- `restaurant_menu`: row rhythm and price alignment are clearer and less spreadsheet-like; placeholder copy still makes it look like a template rather than a finished menu.
- `sale_bold`: headline panel, campaign edge/ribbon, softer photo frame, and CTA depth add campaign energy; large whitespace and missing product art mean it is still a designer draft, not a production ad.
- `salon_black`: subtle framing and the softer photo placeholder make the layout more intentional; the two-text-block source remains visually underdeveloped.
- `signage_wide`: refined dark edge frame and compact logo placeholder improve signboard presentation; with only a headline and missing logo, it remains intentionally minimal.
- `social_banner`: accent rail/orb, softer photo frame, and CTA depth add structure; brand art direction is still generic.
- `spa_luxury`: premium rule/corner, refined photo frame, serif/sans contrast, and CTA depth make the wide composition more presentational; repeated source copy still weakens the result.

## METRICS SUMMARY

The same frozen scorer was applied to re-rendered v0.3.1 and hardened v0.3.2 documents. These heuristic values do not constitute human preference.

| Metric | v0.3.1 | v0.3.2 | Delta |
|---|---:|---:|---:|
| combined | 0.891890 | 0.904944 | +0.013054 |
| technical | 0.979487 | 0.979487 | 0.000000 |
| overlap ratio | 0.000000 | 0.000000 | 0.000000 |
| spacing | 0.942830 | 0.944318 | +0.001488 |
| headline dominance | 0.622927 | 0.755536 | +0.132609 |
| text fit | 1.000000 | 1.000000 | 0.000000 |
| coverage | 0.446677 | 0.451462 | +0.004785 |

Hardening-specific diagnostics:

- placeholder quality: `1.000000`
- CTA prominence: `1.000000` for existing CTAs; absent CTAs were not invented
- menu readability structure: `1.000000`
- decorative balance: `0.897436`

## TECHNICAL SAFETY

- strict schema: `13/13`
- overlap: `0.0` before and after; no regression
- outside canvas: `13/13` safe
- text fit: `13/13` at 100%; unresolved overflow `0`
- hidden truncation: `0`
- Corel compile: `13/13`
- editable output: all introduced frames, panels, rows, labels, and accents compile to editable Corel operations
- fake data safety: no content generated or replaced; missing menu prices/items and campaign values stay explicit placeholders
- placeholder safety: every unavailable asset remains explicitly marked as requiring a real asset

## SMALL FRESH SMOKE

- run: no
- prompts: none
- reason: the requested 13-winner deterministic replay reached the visual and safety checkpoint without loading or retraining Qwen. A fresh generation smoke would not validate the hardening transform more directly and was intentionally left out of this narrow sprint.

## LIMITATIONS

- No real photography, logo, illustration, or proprietary font was introduced, so sparse cases still look like polished designer drafts rather than finished ads.
- Sale remains whitespace-heavy and would benefit most from a customer-supplied product asset; the sprint does not fabricate one.
- Both menu cases remain visibly template-like because all item descriptions and prices are explicit placeholders.
- Typography personality is limited to deterministic open fallback families and does not equal custom brand typography.
- No human preference was collected. The visual-improvement decision is based on direct side-by-side inspection plus frozen heuristic safety metrics.

## FINAL DECISION

- v0.3.2_complete: `true`
- visually_improved_for_human_review: `true`
- technically_safe: `true`
- ready_for_human_review: `true`
- ready_for_v0.4_preference_training: `false`

The checkpoint is complete as a narrow aesthetic-hardening replay: the 13 comparisons are materially more presentational while safety is preserved. It is not evidence of learned aesthetic improvement, and it is not a production-quality asset-complete design system.

## NEXT 3 ACTIONS

1. Collect blinded human choices and short notes for all 13 v0.3.1/v0.3.2 comparison pairs.
2. Replace placeholders in a controlled review copy with customer-authorized sample assets to measure how much remaining weakness is asset-driven.
3. Use the collected human preferences to define, but not yet begin, the separately approved v0.4 preference-training gate.

## TL;DR

- V0.3.2 hardens the existing 13 v0.3.1 winners; it does not retrain Qwen.
- All 13 outputs validate, compile to Corel operations, fit text, and stay inside canvas.
- Overlap remains zero and no content or customer values were fabricated.
- Placeholder X boxes are replaced by softer editable PHOTO/LOGO frames.
- CTA, campaign hierarchy, menu row rhythm, and category accents are visibly stronger.
- Combined heuristic score moved `0.891890 → 0.904944` with the scorer frozen.
- Headline dominance moved `0.622927 → 0.755536`.
- Sale and both menus are improved but still visibly draft/template-like.
- Human preference has not been collected.
- Ready for human review: yes. Ready for v0.4 training: no.
