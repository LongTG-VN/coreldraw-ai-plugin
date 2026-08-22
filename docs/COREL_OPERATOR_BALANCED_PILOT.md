# Corel Operator Balanced Real-CDR Pilot

## Design

The pilot uses `ControlledInstructionPlanner` with `planner_is_ai=false`. Selection is deterministic with seed `corel-balanced-reliability-v2`. It runs 30 tasks in each operation family:

- text replacement;
- 1 mm move;
- 1% resize;
- one multi-action move-plus-resize transaction.

The final set contains 120 tasks over 53 unique source documents; 67 tasks transparently reuse a source in another operation lane. Eligibility is capability-based, not an aesthetic filter. Unsupported targets and failures remain in the denominator.

Every mutation uses a working copy and follows inspection, target resolution, policy validation, transaction, postcondition validation, canonical preview, Visual QA V2, save, close, reopen, editability verification, and source SHA verification. Failed committed mutations are rolled back before any persisted output is counted.

## Aggregate result

| Result | Count |
| --- | ---: |
| Tasks | 120 |
| `AUTO_SUCCESS` | 90 |
| `SUCCESS_WITH_WARNING` | 0 |
| `NEEDS_REVIEW` | 1 |
| `UNSUPPORTED` | 21 |
| `FAILED` | 8 |
| Persisted executed outputs | 91 |
| Transactions started | 97 |
| Save/reopen pass | 91 |
| Save/reopen fail | 0 |
| Source mutations | 0 |

The executed denominator contains only persisted automatic success, warning, or review outputs. Transactions that later failed validation and were rolled back are tracked separately and are not represented as saved/reopened output.

## Text replacement

| Metric | Count |
| --- | ---: |
| Attempted | 30 |
| Automatic success | 11 |
| Needs review | 1 |
| Unsupported | 15 |
| Failed | 3 |
| Persisted/save-reopen pass | 12 |

Text replacement did not reach the target of 20 successful real samples. The largest constraint is defensible unique object-local target selection, followed by legacy TextRange no-ops and policy failures. Synthetic benchmark replacements were applied only to working copies and exact content postconditions were required.

## Move

| Metric | Count |
| --- | ---: |
| Attempted | 30 |
| Automatic success | 26 |
| Needs review | 0 |
| Unsupported | 1 |
| Failed | 3 |
| Persisted/save-reopen pass | 26 |

Corel `Shape.Move` is relative, so the runtime applies the requested delta; absolute target coordinates are preserved in the plan and verified after inspection. Two failures were collateral-policy failures and one was a bounded worker timeout.

## Resize

| Metric | Count |
| --- | ---: |
| Attempted | 30 |
| Automatic success | 27 |
| Needs review | 0 |
| Unsupported | 2 |
| Failed | 1 |
| Persisted/save-reopen pass | 27 |

The single failure was a bounded timeout. Size, anchor behavior, non-mirroring, page geometry, unrelated objects, and reopen editability were validated.

## Multi-action transaction

| Metric | Count |
| --- | ---: |
| Attempted | 30 |
| Automatic success | 26 |
| Needs review | 0 |
| Unsupported | 3 |
| Failed | 1 |
| Persisted/save-reopen pass | 26 |

Each plan resizes and moves one resolved object in one transaction. Resize runs before move so the absolute target position is deterministic. If either action or any postcondition fails, the logical mutation rolls back. The one final failure was a protected collateral-change violation.

## Ambiguity controls

Five deliberately nonunique text-selector controls were executed separately. All five were safely refused before a transaction started. There were no unexpected automatic mutations and no source mutations.

## Performance and stability

- median: 24.100390 seconds per task;
- p90: 57.700140 seconds;
- p95: 76.985266 seconds;
- Corel crashes: 0;
- COM reconnects: 0;
- worker timeouts: 2.

One controlled runtime recovery path was sufficient for the run to continue; there was no restart loop.

## Sanitized review evidence

The private package contains 91 same-scale `BEFORE | AFTER | DIFF` comparisons and 24 contact sheets grouped by operation:

- replace: 12 comparisons, 3 sheets;
- move: 26 comparisons, 7 sheets;
- resize: 27 comparisons, 7 sheets;
- multi-action: 26 comparisons, 7 sheets.

GitHub Actions artifact:

- name: `chatgpt-corel-production-reliability-001`;
- workflow run: `32595627910`;
- artifact ID: `9481456933`;
- retention: 7 days.

The workflow validates exactly 91 comparisons, 24 sheets, four manifests, and four summaries. It excludes source documents, databases, absolute paths, and archive structure.
