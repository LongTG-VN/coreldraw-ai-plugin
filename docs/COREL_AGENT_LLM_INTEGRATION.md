# Corel Agent LLM Integration

## Status

The provider-neutral protocol and strict trust boundary are implemented. No authorized OpenAI or Anthropic provider configuration was detected during the overnight run, so no external model was called. `REAL_LLM_STATUS=NOT_CONFIGURED`.

## Provider contract

An adapter implements:

```python
class CorelPlannerProvider(Protocol):
    def plan(
        self,
        request: CorelAgentRequestV1,
        context: CorelPlannerContext,
    ) -> CorelPlanEnvelopeV1: ...
```

Providers receive bounded context and return a proposal. They never receive `OperatorToolService`, COM handles, arbitrary paths, or execution callbacks.

## Adding a provider safely

1. Read credentials only from the provider's supported secret mechanism; never log them.
2. Send the compact context, requested plan schema, and maximum-step bound.
3. Parse raw output through `validate_untrusted_planner_payload`.
4. Apply `validate_agent_plan` independently of the provider.
5. Persist provider/model/provenance and the plan hash.
6. Start with `PLAN_ONLY` evaluation against safe, ambiguous, unsafe, and multi-action cases.
7. Do not enable mutation until a supervised gate explicitly authorizes it.

## Provenance

Real model output must record `planner_type=llm`, a provider name, model identifier, and `planner_is_ai=true`. Deterministic and fixture planners must record `planner_is_ai=false`. Benchmark reports must separate planning, execution, and visual-QA success.

## Required future gate

A supervised LLM pilot must demonstrate schema validity, correct actions and selectors, unsafe refusal, preserved constraints, bounded latency, and zero unapproved execution. Human confirmation remains required for medium-risk actions.
