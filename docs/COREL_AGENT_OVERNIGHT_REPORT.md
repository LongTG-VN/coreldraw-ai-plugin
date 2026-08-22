# Corel Agent Overnight Report

## Result

`COREL_OPERATOR_RELIABILITY_IMPROVED`

The Phase 2.3 gate was partial, so this run selected `OVERNIGHT_MODE=RELIABILITY_HARDENING`. It reduced the primary text-replacement failure mode on the same real-Corel cohort, then added non-executing agent infrastructure, MCP context support, persistent jobs, a Vietnamese safety benchmark, and a 200-file real-Cdr dry run. No real LLM was configured or called.

## Starting evidence

- Phase 2.3 gate: `PRODUCTION_RELIABILITY_GATE_PARTIAL`.
- source mutations: 0.
- save/reopen pass rate for persisted outputs: 100%.
- terminal failure rate: 6.6667%.
- automatic success among executed outputs: 98.9011%.
- text / move / resize / multi-action automatic success: 11 / 26 / 27 / 26 from 30 attempts per lane.
- remaining recorded failures: 9.
- baseline tests: 398 passed.

## Reliability hardening

Text replacement now uses object-local `ReplaceWide` with the original font when available. Benchmark replacements preserve string length and non-target separators; mixed-font targets fail closed. The targeted selector preserves a fixed real-file cohort and denominator.

Same 33-case cohort:

| Metric | v1 | v2 |
| --- | ---: | ---: |
| automatic success | 24 | 26 |
| needs review | 1 | 1 |
| unsupported | 5 | 5 |
| failed | 3 | 1 |
| save/reopen pass | 25 | 27 |
| source mutations | 0 | 0 |
| median seconds | 20.686 | 20.530 |

The remaining failure was an object-identity-set change and was rolled back. The review case had no visible target change. This improves the affected lane but does not replace a complete balanced production gate.

## Plan-only infrastructure

- strict requests, plan envelopes, execution modes, risk, errors, and planner provenance;
- provider-neutral planner protocol plus an explicitly non-AI deterministic adapter;
- compact context capped at 25 text candidates, with text hidden by default;
- semantic rejection of paths, traversal, shell, VBA, raw COM, direct save, delete-all, and unknown mutation actions;
- SQLite jobs, guarded state transitions, source/request/plan fingerprinting, and safe versioned output names;
- eight loopback MCP tools, including read-only compact context;
- deterministic Vietnamese intent benchmark.

## Dry-run scale

The read-only scale run inspected 200 real CDRs sequentially with the existing real Corel runtime. It executed no mutations.

- files: 200;
- plannable: 162;
- ambiguous: 16;
- unsupported: 21;
- failed inspection: 1;
- source mutations: 0;
- median per file: 4.731 seconds;
- total: 1448.113 seconds;
- planner: deterministic, `planner_is_ai=false`.

The single failure was persisted as a failed inspection and did not affect the source. No Corel crash or COM reconnect was observed during this run.

## Vietnamese command benchmark

- cases: 24;
- passed: 24;
- unsafe or vague cases: 6;
- safely refused: 6;
- real model calls: 0.

## Real LLM

Authorized provider configuration detected: none. Therefore:

- `REAL_LLM_STATUS=NOT_CONFIGURED`;
- plan tests: 0;
- valid real-LLM plans: 0;
- real-LLM unsafe rejections: 0;
- real-LLM execution: not tested.

## MCP and security

MCP exposes eight bounded tools on loopback only. Customer text is opt-in, opaque document IDs are mandatory, and mutation still requires explicit execution confirmation. Error sanitization handles repeated slash forms emitted by legacy Corel messages. No raw COM, path, shell, or generic execution endpoint was added.

## Verification

- source compile: pass;
- pytest: 432 passed;
- git diff check: pass;
- third-party warning: one Starlette/httpx deprecation warning;
- Corel version used by real evidence: 22.0.0.412.

## Readiness matrix

| Capability | Status | Evidence |
| --- | --- | --- |
| SOURCE_SAFETY | VERIFIED | Zero mutations in targeted and 200-file runs |
| OPERATOR_RELIABILITY | PARTIAL | Text lane improved; full balanced gate not repeated |
| VISUAL_QA | VERIFIED | Existing V2 evidence retained |
| BALANCED_OPERATIONS | PARTIAL | Phase 2.3 gate remained partial |
| MCP_BOUNDARY | VERIFIED | Eight-tool loopback boundary and tests |
| PLAN_SCHEMA | VERIFIED | Strict contracts and rejection tests |
| LLM_PROVIDER_INTERFACE | VERIFIED | Provider-neutral protocol; deterministic adapter |
| REAL_LLM_PLAN_ONLY | BLOCKED | No authorized provider configuration |
| REAL_LLM_EXECUTION | NOT_TESTED | Intentionally not attempted |
| VIETNAMESE_COMMANDS | VERIFIED | 24/24 deterministic cases |
| JOB_PERSISTENCE | VERIFIED | SQLite, transitions, fingerprint tests |
| BATCH_DRY_RUN | VERIFIED | 200 real CDRs, zero mutation |
| BATCH_EXECUTION | NOT_TESTED | Prohibited during unattended run |
| UNATTENDED_PRODUCTION | BLOCKED | Reliability gate remains partial |

## Final metrics

```text
OVERNIGHT_MODE=RELIABILITY_HARDENING
PHASE23_GATE=PRODUCTION_RELIABILITY_GATE_PARTIAL
SOURCE_MUTATIONS=0
PLANNER_SCHEMA_TESTS=PASS
VIETNAMESE_COMMAND_CASES=24
VIETNAMESE_COMMAND_PASS=24
UNSAFE_COMMAND_CASES=6
UNSAFE_COMMAND_REJECTED=6
MCP_TOOL_COUNT=8
MCP_REGRESSION_STATUS=PASS
DRY_RUN_FILES=200
DRY_RUN_PLANNABLE=162
DRY_RUN_AMBIGUOUS=16
DRY_RUN_UNSUPPORTED=21
DRY_RUN_FAILED=1
REAL_LLM_STATUS=NOT_CONFIGURED
REAL_LLM_PLAN_TESTS=0
REAL_LLM_VALID_PLANS=0
REAL_LLM_UNSAFE_REJECTIONS=0
CONTROLLED_DEMOS=0
CONTROLLED_DEMO_SUCCESS=0
CONTROLLED_DEMO_REVIEW=0
CONTROLLED_DEMO_FAILED=0
COREL_TIMEOUTS=0
COREL_CRASHES=0
COM_RECONNECTS=0
TEST_COUNT=432
TEST_STATUS=PASS
```

The targeted text pilots are reliability validation, not LLM-controlled demos.

## Privacy

Only code, synthetic test fixtures, aggregate metrics, and documentation are tracked. Workspace databases and real-file evidence remain ignored. No customer path, filename, source binary, preview, or content is committed.

## Next recommended mission

`NEXT_RECOMMENDED_MISSION=REPEAT_BALANCED_PRODUCTION_RELIABILITY_GATE`

Repeat a smaller balanced real-Corel gate with the text fixes, then decide whether a supervised real-LLM plan-only pilot is justified. Do not enable unattended execution.
