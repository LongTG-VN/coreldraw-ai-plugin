# Visual QA V2 Review of the Previous 32 Cases

## Result

The 32 Run2 cases previously held only because their preview raster dimensions differed were replayed through the page-anchored Visual QA V2 path using the same deterministic bounded operations. No case was assumed safe merely because page dimensions matched.

| Classification | Count |
| --- | ---: |
| Re-evaluated | 32 |
| `UPGRADED_TO_AUTO_SUCCESS` | 10 |
| `STILL_NEEDS_REVIEW` | 0 |
| `CONFIRMED_REGRESSION` | 0 |
| `QA_EVIDENCE_INSUFFICIENT` | 22 |
| Source mutations | 0 |

## Interpretation

Ten cases produced exact canonical page dimensions and passed structural and target-scoped visual validation. They were upgraded to automatic success.

Twenty-two cases did not produce trustworthy page-anchored evidence. The dominant causes were legacy Corel page-area export failures and target artwork outside the active canonical page. These cases were not classified as success, reviewable visual comparisons, or confirmed regressions; the available visual evidence is insufficient.

## Human-review artifact

No `chatgpt-corel-visual-qa-v2-review` artifact was created because `STILL_NEEDS_REVIEW` is zero. Publishing the 22 evidence-insufficient cases as if they were comparable before/after page images would misrepresent the evidence. A future pasteboard-aware, spatially grounded export path may make those cases reviewable, but content-fit or generically resized previews remain forbidden.

## Safety

- Every replay used a working copy.
- Original size, modification time, and SHA-256 were checked.
- Source mutations: zero.
- No private paths, source binaries, SQLite databases, or customer manifests were published.
