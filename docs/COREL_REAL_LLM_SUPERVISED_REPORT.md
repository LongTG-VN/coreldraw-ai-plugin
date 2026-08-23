# Corel Real LLM Supervised Integration

## Result

The existing Corel Operator safety boundary remains unchanged. A planning-only
OpenAI adapter is implemented against the existing `CorelPlannerProvider`
protocol, but no authorized provider credential is configured on this host.
Consequently no real-model request and no Corel mutation demo were run.

`FINAL_STATUS=REAL_LLM_NOT_CONFIGURED`

## Baseline and scope

- Branch: `codex/corel-real-llm-supervised`
- Starting SHA: `ed0b2e82eae6335347fac1b1afed37f2b8debfb8`
- Baseline gate: `BALANCED_PRODUCTION_RELIABILITY_PASS`
- Operator reliability was not benchmarked again.
- Gold Grammar, model training, and unattended mutation remain out of scope.

## Existing safety architecture audited

The real control path remains:

```text
Vietnamese request
-> planner provider
-> CorelPlanEnvelopeV1 / MutationPlanV1
-> strict payload validation
-> policy validation
-> target resolution
-> explicit execution confirmation
-> loopback-only MCP
-> serialized Corel Operator
-> transaction / QA / save-reopen / source integrity
```

The LLM has no reference to the Corel COM adapter, VBA, shell, filesystem
operations, or MCP execution methods. It receives only the bounded
`DocumentContextV1` summary, never the full inspection or source path.

## Provider adapter

- Preferred provider detection: OpenAI, then Anthropic.
- Detected OpenAI credential: absent.
- Detected Anthropic credential: absent.
- Installed OpenAI SDK: `2.44.0`.
- OpenAI adapter default: `gpt-5.6-sol`, configurable through
  `COREL_AGENT_OPENAI_MODEL`.
- API surface: Responses API `responses.parse` with a Pydantic structured-output
  schema and `store=false`.
- Model tools: none supplied.
- Secret values are neither read into reports nor logged.

The provider-specific response DTO contains no arbitrary JSON maps. It converts
deterministically into the canonical mutation plan. Host-owned request ID,
document ID, goal, constraints, output requests, provenance, and planning-step
limit are verified after parsing. Any mismatch fails closed.

## Plan-only gate

Real-model plan tests were not started because neither authorized provider is
configured. This is a required stop condition, not a model failure.

The local pre-network Vietnamese safety preflight covered five requested cases:

- Three explicit bounded requests were eligible for future model planning.
- `Đổi tên cửa hàng và số điện thoại` was refused with
  `MISSING_EXPLICIT_BUSINESS_VALUES`.
- `Đổi tất cả cho đẹp hơn` was refused with
  `VAGUE_OR_UNBOUNDED_INTENT`.

These local refusals are not reported as real-model results.

## Supervised demonstrations

No working-copy demo ran because the real PLAN_ONLY gate could not run. Therefore
there was no execution confirmation, no mutation, no save/reopen result, and no
source-file exposure. `SOURCE_MUTATIONS=0` means no source was touched during this
mission; it is not evidence from a mutation cohort.

## Verification

- Focused provider and agent tests: `36 passed`
- Full test suite: `449 passed`, one third-party deprecation warning
- Compile: `python -m compileall -q training tests` passed
- Structured-output schema free-form map audit: passed
- `git diff --check`: passed before final commit

## Required metrics

```text
REAL_LLM_STATUS=NOT_CONFIGURED
PROVIDER=NONE
MODEL=NOT_CONFIGURED
ADAPTER_DEFAULT_MODEL=gpt-5.6-sol

PLAN_TESTS=0
VALID_PLANS=0
UNSAFE_REQUESTS=2
UNSAFE_REFUSED=2
UNSAFE_REFUSAL_SOURCE=LOCAL_PRE_NETWORK_GUARD

SUPERVISED_DEMOS=0
AUTO_SUCCESS=0
NEEDS_REVIEW=0
FAILED=0

SAVE_REOPEN_PASS_RATE=NOT_RUN
SOURCE_MUTATIONS=0

TEST_COUNT=449
TEST_STATUS=PASS

FINAL_STATUS=REAL_LLM_NOT_CONFIGURED
NEXT_RECOMMENDED_MISSION=CONFIGURE_ONE_AUTHORIZED_PROVIDER_THEN_RERUN_PLAN_ONLY_GATE
```

No `COREL_AI_OPERATOR_MVP` claim is made because the real-model PLAN_ONLY gate did
not execute.
