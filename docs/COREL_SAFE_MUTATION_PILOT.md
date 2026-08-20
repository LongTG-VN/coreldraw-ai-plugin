# Safe Real-CDR Mutation Pilot

## Purpose

The pilot tests whether the operator can make a bounded edit to a Corel-created working copy, verify the intended property change, preserve all tracked non-target state, save/reopen the CDR, and prove the source archive file remained unchanged.

No Gold selection, aesthetic judgment, model training, or full-document reconstruction occurs.

## Safety flow

```text
source stat/hash evidence
        -> Corel SaveAs working copy
        -> snapshot
        -> resolve exactly one target
        -> begin Corel command group
        -> bounded mutation
        -> structural/property validation
        -> commit or Undo
        -> save/reopen editable CDR
        -> PNG/PDF export
        -> source guard
```

Unknown and unsupported objects stay inside the Corel document unchanged. A target ambiguity returns `UNSUPPORTED` or review evidence; it is never resolved by choosing the first match.

## Result classes

- `AUTO_SUCCESS`: mutation, validation, save/reopen, editability, exports, and source guard passed automatically.
- `SUCCESS_WITH_WARNING`: the safe operation completed but retained a non-critical warning.
- `NEEDS_REVIEW`: safety passed but an unresolved condition requires a person.
- `UNSUPPORTED`: no safe unique target or allowed capability existed; no mutation was committed.
- `FAILED`: runtime, timeout, worker, policy, or validation failure; the working copy was rolled back/abandoned and the source guard still had to pass.

## Primary 20-file pilot

| Result | Count |
| --- | ---: |
| Files attempted | 20 |
| `AUTO_SUCCESS` | 12 |
| `SUCCESS_WITH_WARNING` | 0 |
| `NEEDS_REVIEW` | 0 |
| `UNSUPPORTED` | 3 |
| `FAILED` | 5 |
| Editable reopen verified | 12 |
| Source mutations | 0 |

The primary run exposed the stable-target issue in real CDRs: many objects have no Corel name. The fix maps the inspector's stable operator ID to the live Corel object without renaming it.

## Capability-driven extension

The run continued with bounded backfill and operation-specific probes rather than hiding primary-pilot failures. Across 70 persisted attempted records:

| Result | Count |
| --- | ---: |
| `AUTO_SUCCESS` / complete | 26 |
| `SUCCESS_WITH_WARNING` | 0 |
| `NEEDS_REVIEW` | 0 |
| `UNSUPPORTED` | 36 |
| `FAILED` | 8 |

The 36 unsupported records had no safe unique target for the requested capability. The eight failures comprised three Corel runtime failures, three policy/postcondition failures, one hard timeout, and one worker failure.

Successful operation evidence across all capability probes:

| Operation | Automatic successes |
| --- | ---: |
| Font size +5% | 20 |
| Move 1 mm | 3 |
| Resize non-text object +1% | 2 |
| Replace price-like text | 1 |

The replacement used explicit synthetic benchmark content and is tagged `benchmark_sample_data: true`; it is not represented as customer-supplied data.

Twenty unique successful source tokens were selected for the private visual package. Every selected result preserved object count, reopened as editable Corel content, and passed the source guard.

## Real rollback verification

One real working-copy transaction intentionally failed. Corel reported rollback, the pre-transaction snapshot was restored, object count remained 15, and the source file remained unchanged. Result: `VERIFIED`.

Policy/postcondition failures are useful evidence: for example, a text resize that changed font size outside the declared property scope was rejected and rolled back, and an unexpected non-target bounding-box change also triggered rollback.

## Private visual evidence

- Private repository: `LongTG-VN/coreldraw-ai-review-private`
- Private commit: `53cdc567921621b11bd9f943cd34917a18aec72e`
- Actions run: `32335503616`
- Artifact ID: `9394492395`
- Artifact: `chatgpt-corel-operator-mutation-pilot-001`
- Contents: 20 same-scale before/after comparisons, 5 contact sheets, sanitized manifest, summary, and README
- Retention: 7 days
- CDR/CDT/SQLite files: 0
- Local path leaks: 0
- Human preference: not collected
- Gold certification: none

## Conclusion

Bounded real-CDR mutation is practical for uniquely targetable objects, but capability breadth is still limited. The high unsupported count is intentionally preserved: the operator fails closed instead of guessing.
