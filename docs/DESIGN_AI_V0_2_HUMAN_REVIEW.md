# Design AI v0.2 — Manual visual sanity review

## Review boundary

This is a manual visual inspection of representative static contact sheets,
separate from the numeric heuristic. It is an engineering-agent review, not a
human designer approval, and it does not create `human_preference` labels.

Reviewed benchmark:
`training/artifacts/benchmarks/20260809_design_v0_2_best_of_4_final_v7`.

## Representative findings

### Restaurant menu

`restaurant_menu/contact_sheet.png` makes the ranking easy to audit. Selected
`candidate_01` has the clearest title-to-menu hierarchy and least visible text
collision. The other three candidates visibly stack multiple lines near the
top. Selection is directionally correct, though the chosen layout is sparse
and lacks realistic menu prices/assets.

### Dense food menu

Selected `candidate_02` is clearly stronger than the other three: headline,
description, item-count line, and hotline occupy separate regions. The other
candidates collapse most content into a dense top cluster. This is a strong
best-of-4 win, but it still does not satisfy the requested ten-item information
density.

### Sale poster

No candidate is professionally usable. Large glyphs overflow their declared
text boxes and collide despite valid schema geometry. The first scoring pass
overrated this family because it measured element bboxes rather than estimated
rendered text. Critic v0.2.3 now records text-fit/overflow and penalizes
truncated-prefix outputs; that restores the complete `candidate_01` as winner,
but the preview remains poor. This is an upstream generation-quality failure,
not something best-of-4 can manufacture away.

## Sanity conclusion

Best-of-4 is useful as a local rejection/ranking layer: it substantially lowers
geometric overlap and improves spacing/text-fit averages. It is not yet a
professional aesthetic judge. Important remaining gaps are:

- fallback fonts and simple preview rendering differ from final Corel text;
- the model often emits text boxes too small for its font/content;
- prompt completeness is weak on dense designs;
- average hierarchy score regressed even while total score improved;
- there is no learned vision critic or designer-labeled calibration set.

The next checkpoint should use a small, license-safe design retrieval/reference
layer plus designer-reviewed comparisons to calibrate ranking. Auto preferences
from this research-only checkpoint must remain distinct from any future human
labels.
