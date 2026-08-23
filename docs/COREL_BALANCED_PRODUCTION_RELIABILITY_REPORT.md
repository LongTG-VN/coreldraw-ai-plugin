# Corel Balanced Production Reliability Gate

## RESULT

- Execution date: 2026-08-23 (Asia/Bangkok)
- Gate: `BALANCED_PRODUCTION_RELIABILITY_PARTIAL`
- Planner: deterministic `ControlledInstructionPlanner`; `planner_is_ai=false`
- Real LLM: not configured and not called
- CorelDRAW: 22.0.0.412
- Python: 3.11.9
- Primary conclusion: the Operator safely executes several real editing families, but the balanced production gate does not fully pass because text replacement produced only 11 meaningful executions and MOVE had 2 terminal failures in 25 attempts (8%).

## GIT

- Starting SHA: `5a1b95e16f617f3c8d15fb12dcb1b81c662493df`
- Branch: `codex/corel-balanced-reliability-gate`
- Base checkpoint: `docs(agent): report overnight Corel agent run`
- Reliability regression commit: `9ae1769` (`test(operator): add balanced rollback and command regressions`)
- Final SHA and remote synchronization are reported in the final run output after this document is committed.

## BASELINE

The previous reliability checkpoint reported a 33-file text-replacement cohort with 26 `AUTO_SUCCESS`, one terminal failure, and 27 save/reopen passes. It also reported the deterministic 200-file dry-run as 162 plannable, 16 ambiguous, 21 unsupported, and one inspection failure. This gate preserved those results as historical evidence and ran a new fixed balanced cohort rather than adding more font-size or text-only cases.

## SOURCE SAFETY

- The company archive remained read-only.
- Every mutation used `source -> fresh working copy -> transaction -> output copy`.
- Source guards checked immutable source metadata after each operation.
- Source mutations across 100 balanced tasks, 10 ambiguity controls, 10 rollback controls, and the 200-file dry-run: **0**.
- No source document was accepted as an output, and no output overwrote its source.

## SAMPLE

- Selection seed: `corel-balanced-reliability-v2`
- Census candidate pool: 200 inspected real CDRs; 198 were operator-eligible and two census failures were excluded.
- Eligibility rule: operator-eligible document with at least one object on the canonical page; the operation planner was still allowed to refuse unsafe targets.
- Fixed before execution: 25 rows for each of `TEXT_REPLACE`, `MOVE`, `RESIZE`, and `MULTI_ACTION`.
- Total tasks: 100
- Unique sources: 53
- Deliberate cross-family source reuse: 47 cases
- No failed case was removed or replaced after execution.
- Target resolution reached a transaction for 80 tasks; 19 were refused with `NO_SAFE_TEXT_TARGET`; one resize case timed out before an accepted result. The balanced cohort had no guessed ambiguous target. A separate ambiguity cohort covered ten deliberately ambiguous/vague cases.

## TEXT REPLACE

| Metric | Result |
| --- | ---: |
| Attempted | 25 |
| Executed | 11 |
| Auto success | 10 |
| Success with warning | 0 |
| Needs review | 1 |
| Unsupported | 14 |
| Failed | 0 |
| Save/reopen pass | 11/11 (100%) |
| Auto success among executed | 90.91% |
| Median / p90 / p95, all attempts | 12.51 / 53.78 / 69.89 s |
| Median / p90 / p95, executed | 46.46 / 69.89 / 144.11 s |

All unsupported cases failed closed as `NO_SAFE_TEXT_TARGET`. The single review case preserved an editable output but Visual QA returned `NEEDS_REVIEW`; it was not counted as automatic success. This family meets the percentage goals on the executions it has, but 11 executions are below the requested minimum of 20 meaningful attempts, so the evidence is insufficient for a balanced PASS.

## MOVE

| Metric | Result |
| --- | ---: |
| Attempted | 25 |
| Executed | 22 |
| Auto success | 22 |
| Needs review | 0 |
| Unsupported | 1 |
| Failed | 2 |
| Save/reopen pass | 22/22 (100%) |
| Auto success among executed | 100% |
| Terminal failure rate | 8% |
| Median / p90 / p95, all attempts | 45.49 / 128.85 / 172.50 s |

Both failures were preserved after the second bounded attempt. One detected collateral bounding-box changes in five non-target objects. The other detected a changed object-identity set. Both transactions reported verified rollback, and both sources remained unchanged. The 8% terminal failure rate exceeds the 5% per-family goal.

## RESIZE

| Metric | Result |
| --- | ---: |
| Attempted | 25 |
| Executed | 22 |
| Auto success | 22 |
| Needs review | 0 |
| Unsupported | 2 |
| Failed | 1 |
| Save/reopen pass | 22/22 (100%) |
| Auto success among executed | 100% |
| Terminal failure rate | 4% |
| Median / p90 / p95, all attempts | 44.89 / 64.75 / 69.36 s |
| Median / p90 / p95, executed | 44.89 / 60.70 / 64.75 s |

The one terminal case exceeded the fixed 240-second worker timeout on its second bounded attempt. Recovery closed the active working document safely; the source guard passed. No retry limit was increased.

## MULTI ACTION

| Metric | Result |
| --- | ---: |
| Attempted | 25 |
| Executed | 22 |
| Auto success | 22 |
| Needs review | 0 |
| Unsupported | 2 |
| Failed | 1 |
| Save/reopen pass | 22/22 (100%) |
| Auto success among executed | 100% |
| Terminal failure rate | 4% |
| Median / p90 / p95, all attempts | 41.03 / 69.88 / 86.85 s |
| Median / p90 / p95, executed | 41.10 / 69.88 / 86.85 s |

Each executed case used one transaction containing both MOVE and RESIZE. The terminal failure detected broad collateral changes outside policy, rolled back, produced no accepted output, and left the source unchanged.

## SAFE ROLLBACK CONTROL

- Selection seed: `corel-balanced-gate-rollback-v1`
- Intentional-failure controls: 10
- First action succeeded and second action deliberately targeted a missing object: 10/10
- Transaction reported rollback: 10/10
- Stable snapshot restored: 10/10
- Source unchanged: 10/10
- Classification: `EXPECTED_SAFE_ROLLBACK`, not task failure

## AMBIGUITY CONTROL

- Selection seed: `corel-balanced-gate-ambiguity-v1`
- Ambiguous/vague controls: 10
- Safe refusal as `NEEDS_REVIEW`: 10/10
- Unexpected mutation: 0
- Source mutations: 0

## TARGET RESOLUTION

- Transaction reached with a selected target: 80/100
- Refused because no defensible target existed: 19/100
- Timeout before an accepted resolved result: 1/100
- Guessed targets: 0
- Separate ambiguous-target safety controls passed: 10/10

The cohort was not backfilled with easier replacements after a refusal or failure.

## STRUCTURAL QA

- Accepted outputs preserved page geometry and protected non-target state under the declared operation policy.
- 77/77 accepted outputs saved, closed, reopened, and remained editable.
- Three postcondition failures detected collateral structure changes and were rolled back instead of accepted.
- Dependency-aware validation allows only explicit direct-parent effects; unrelated object changes remain failures.

## VISUAL QA

- `PASS`: 76
- `NEEDS_REVIEW`: 1
- Accepted `FAIL`: 0
- The QA path used the current page-space/canonical implementation and did not resize images merely to force equality.
- Visual QA is an integrity check, not an aesthetic preference label.

## SAVE REOPEN

- Accepted/executed outputs: 77
- Real editable CDR save/reopen pass: 77
- Save/reopen failure: 0
- Pass rate: 100%

## FAILURE ANALYSIS

- Terminal failed cases: 4/100 (4%).
- MOVE: two postcondition failures; collateral object bounding boxes and an object identity-set change.
- RESIZE: one 240-second terminal timeout after bounded retries.
- MULTI_ACTION: one policy failure caused by broad collateral bbox/rotation/text changes.
- Verified rollback among policy/postcondition failures: 3/3.
- Terminal timeout cases: 1; the case consumed both allowed attempts.
- Corel crashes observed: 0.
- COM reconnects observed: 0.
- Unbounded retries: 0.

## MCP REGRESSION

Eight bounded MCP tools remain exposed:

1. `corel_get_document`
2. `corel_build_agent_context`
3. `corel_list_objects`
4. `corel_find_text`
5. `corel_plan_task`
6. `corel_run_task`
7. `corel_execute_plan`
8. `corel_visual_qa`

Regression passed for loopback-only binding, explicit mutation confirmation, plan/dry-run boundaries, and denial of raw COM, VBA, shell, arbitrary paths, and source overwrite.

## AGENT REGRESSION

The full 200-file regression exposed three explicit internal commands that the Vietnamese analyzer incorrectly classified as having no executable action. The analyzer now recognizes bounded forms for phone, price, and object font size. Regression corpus:

- Vietnamese command cases: 27/27 passed (previous 24 cases preserved plus three internal forms).
- Unsafe/vague cases safely refused: 6/6.
- Planner: deterministic; `planner_is_ai=false`.
- Real LLM calls: 0.

The same deterministic 200-file sample and seed were rerun after the fix:

- Plannable: 162
- Ambiguous: 16
- Unsupported: 21
- Failed inspection: 1
- Source mutations: 0

This exactly matches the previous baseline distribution; no causal improvement is claimed.

## PERFORMANCE

- Aggregate median: 41.84 s
- Aggregate p90: 67.24 s
- Aggregate p95: 128.85 s
- MOVE had the highest all-attempt p95 at 172.50 s.
- The resize timeout was the only terminal timeout case.
- Reliability and bounded recovery were prioritized over throughput.

## TESTS

- `python -m compileall -q training tests`: PASS
- `python -m pytest -q`: **434 passed**, one third-party Starlette/httpx deprecation warning
- `git diff --check`: PASS before final commit
- Tests remain hermetic: no Corel, private company data, GPU, model, or network is required in CI.

## PRIVACY

- Public repository changes contain no source CDR/CDT, SQLite database, company path, customer filename, or absolute local path.
- Local real-CDR artifacts remain under ignored workspace paths.
- The sanitized visual package contains 77 comparisons, 21 contact sheets, four manifests, and four summaries.
- Private repository: `LongTG-VN/coreldraw-ai-review-private`, visibility verified private before publishing.
- Private commit: `402ab71f8650bbfe7c5de95e4436bcae016254e0`.
- Workflow run: `32620380383` (success).
- Artifact: `chatgpt-corel-balanced-reliability-gate`, artifact ID `9488194879`, seven-day retention.
- Artifact audit: no CDR/CDT, SQLite/database, absolute Windows paths, or source archive structure.

## BALANCED PRODUCTION GATE

Aggregate gates pass:

- `AUTO_SUCCESS among executed = 76/77 = 98.70%`
- `NEEDS_REVIEW among executed = 1/77 = 1.30%`
- `TERMINAL_FAILED = 4/100 = 4.00%`
- `SAVE_REOPEN = 77/77 = 100%`
- `SOURCE_MUTATIONS = 0`
- ambiguity refusal = 10/10

The overall gate remains **PARTIAL**, not PASS, because balanced evidence must also be credible per operation family:

1. TEXT_REPLACE has only 11 executed cases, below the requested minimum of 20 meaningful executions.
2. MOVE has a terminal failure rate of 8%, above the 5% family goal.

No result class, retry limit, cohort member, or scorer was changed to improve the headline metrics.

## NEXT MISSION

`NEXT_RECOMMENDED_MISSION=DEFENSIBLE_TEXT_TARGET_COVERAGE_AND_MOVE_COLLATERAL_DEPENDENCY_HARDENING`

The next reliability mission should increase safe text-target coverage without guessing and diagnose MOVE collateral/identity changes. Real-LLM supervised integration should wait until those two per-family blockers are closed.
