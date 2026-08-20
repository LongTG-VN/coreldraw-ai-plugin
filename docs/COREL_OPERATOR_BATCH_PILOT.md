# Corel Operator Batch Pilot

## Batch architecture

The batch runner provides per-file isolation, SQLite resume state, hard subprocess timeouts for real Corel work, bounded attempts, sanitized progress, and source-stat verification. A failed file cannot silently disappear from the denominator or terminate the remaining batch.

The generic engine supports resumable structured tasks. Real Corel census and mutation commands use one subprocess per file because a blocked COM call cannot be safely cancelled by a cooperative Python timeout.

## Non-destructive operational batch

The coverage census served as a 200-file non-destructive batch—larger than the requested 50–100-file dry run—with this flow:

```text
open source -> inspect -> snapshot -> save working copy -> close/reopen
-> export PNG -> export PDF -> close -> verify source unchanged
```

| Metric | Result |
| --- | ---: |
| Files attempted | 200 |
| Operational `AUTO_SUCCESS` | 198 |
| `NEEDS_REVIEW` | 0 |
| `UNSUPPORTED` | 0 |
| `FAILED` | 2 |
| Median completed-file time | 15.440 s |
| p95 completed-file time | 55.958 s |
| Initial timed-out entries | 5 |
| Recovered by one explicit retry wave | 3 |
| Final timeouts | 2 |
| Automatic Corel process kills/restarts | 0 |
| Source mutations | 0 |

The two final failures remained `TIMEOUT` after 300 seconds. CorelDRAW itself was not killed because that could destroy unrelated unsaved user work.

## Actual mutation batches

Mutation was capability-driven and limited to working copies. The primary batch attempted 20 real CDRs and produced 12 automatic successes, 3 unsupported records, and 5 failures. Bounded backfill and targeted probes raised the evidence set to 20 unique automatically successful, editable-reopen CDRs.

Across all 70 mutation-attempt records: 26 completed, 36 were unsupported, and 8 failed. Unsupported and failed records were persisted, not replaced in aggregate reporting.

## Resume and failure isolation

- A stable source token is the only source identity emitted into sanitized reports.
- An attempt row is persisted after every worker completion or timeout.
- `--retry-failures` is explicit; completed files are not rerun by default.
- A timeout terminates only the Python worker. It does not kill CorelDRAW.
- Recovery may close a proven working copy or the exact timed-out source without saving; it never closes an unrelated document.
- Source stat guards are evaluated after each attempt, including failed attempts.

## Top failure categories

Mutation attempts recorded:

- no safe unique target: 36 unsupported;
- Corel runtime failure: 3 failed;
- policy or postcondition validation: 3 failed;
- hard timeout: 1 failed;
- worker failure: 1 failed.

The failure distribution supports a partial-but-usable status: batch infrastructure and preservation behavior are reliable, while automatic target/capability coverage needs expansion.

## Local evidence

Detailed batch SQLite databases, working CDRs, previews, PDFs, and source-token maps remain under ignored `training/workspace/company_archive/`. They are not committed to the public repository.
