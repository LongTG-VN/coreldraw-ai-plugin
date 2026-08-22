# Corel Operator Failure Reduction

## Previous failure census

All 11 terminal Run2 failures were analyzed without substituting easier files.

| Root-cause cluster | Count |
| --- | ---: |
| Collateral bounding-box policy | 6 |
| Corel TextRange / COM | 4 |
| Worker runtime | 1 |

The sanitized local aggregate records stage, attempts, rollback evidence, source immutability, reproducibility, and a bounded fix candidate. Customer paths and content are excluded.

## Dependency-aware postconditions

The validator was not weakened globally. A plan may declare only narrow relationships:

- `DIRECT_TARGET`: the resolved object and operation-specific properties;
- `DEPENDENT_CONTAINER`: only the target's direct parent, with bounded allowed properties;
- `DEPENDENT_TEXT_FRAME`: only the same text object when text-frame behavior is relevant;
- unrelated objects remain protected.

The service verifies that declared container dependencies are the target's actual direct parent. Unknown dependency IDs, arbitrary related shapes, and unrelated changes fail validation. Multi-action plans merge only the explicitly allowed properties. A resize followed by a move of the same object is validated as one intended compound mutation, not as collateral drift.

## TextRange hardening

Text mutation now uses a narrow bounded retry:

1. resolve the stable Corel object ID;
2. reacquire the live shape before each attempt;
3. apply the TextRange operation;
4. retry only recognized TextRange COM failures;
5. stop after the configured bounded attempt count;
6. verify the exact text postcondition or rollback.

The implementation relies on Corel's stable shape targeting and text APIs rather than cached COM objects. Relevant references include [Shape.StaticID](https://community.coreldraw.com/sdk/api/draw/17/p/shape.staticid?lang=cli), [Layer.FindShape](https://community.coreldraw.com/sdk/api/draw/22/m/Layer.FindShape?lang=cs), [TextRange.ReplaceWide](https://community.coreldraw.com/sdk/api/draw/22/m/textrange.replacewide), and [Page.TextReplace](https://community.coreldraw.com/sdk/api/draw/24/m/page.textreplace?lang=cli).

Real investigation also found artistic numeric display texts for which `TextRange.Text`, `ReplaceWide`, page replacement, character-range replacement, and wide-text assignment returned without an exception but did not change the text. The postcondition correctly detected the no-op and rollback succeeded. The operator does not introduce a global page-wide replacement fallback. Numeric-only legacy display text with values that resemble font sizes is excluded from the deterministic replacement selector until a safer object-local mechanism is proven.

## Exact replay of the 11 failures

The hardened operator replayed each previous deterministic task using its recorded target and operation. It did not generate replacement tasks when the prior evidence could not reconstruct one.

| Replay result | Count |
| --- | ---: |
| Fixed | 2 |
| Needs review | 6 |
| Still failed | 2 |
| Not replayable | 1 |
| Source mutations | 0 |

The six review results were held because their targets were outside the canonical active page. Of the two remaining failures, one retained the TextRange COM/no-op limitation and one changed the inspected object identity set. The old worker failure had no resolved target or operation evidence, so it was marked not replayable instead of being replaced by an easier plan.

Accordingly:

- failures reanalyzed: 11;
- failures fixed: 2;
- failures remaining or unresolved: 9.

## Remaining failure modes

1. Some legacy text objects accept COM calls without producing the required object-local text change.
2. Linked effects, containers, or inspection identity changes can produce collateral state not covered by a proven dependency relationship.
3. Pasteboard targets and legacy page export failures prevent trustworthy page-anchored visual evidence.

Each remains fail-closed. Unsupported or review-held cases are not counted as successful.
