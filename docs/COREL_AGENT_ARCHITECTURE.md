# Corel Agent Architecture

## Scope

The Corel agent is a bounded planning layer above the existing deterministic Corel Operator. It does not grant a language model direct COM, filesystem, shell, VBA, or source-document authority.

```text
Vietnamese request
  -> compact read-only document context
  -> planner provider
  -> strict CorelPlanEnvelopeV1
  -> semantic policy validator
  -> persistent CorelOperatorJobV1
  -> existing OperatorToolService / MCP boundary
  -> working-copy transaction
  -> structural and visual QA
  -> versioned CDR/PDF/PNG output
```

The overnight checkpoint implements the first six stages and validates the existing operator with a targeted real-Corel working-copy pilot. Real LLM planning and LLM-originated execution were not run because no authorized provider configuration was present.

## Components

- `training/corel_agent/models.py`: strict provider-neutral requests, envelopes, risk, validation, and job contracts.
- `training/corel_agent/context.py`: bounded document summaries; customer text is opt-in and capped.
- `training/corel_agent/commands.py`: conservative Vietnamese intent and constraint analysis.
- `training/corel_agent/provider.py`: planner protocol, deterministic adapter, and strict untrusted-payload parser.
- `training/corel_agent/policy.py`: semantic trust boundary and execution-mode enforcement.
- `training/corel_agent/jobs.py`: SQLite job persistence, fingerprints, state transitions, and safe output naming.
- `training/corel_agent/evaluation.py`: hermetic Vietnamese command-boundary benchmark.
- `training/corel_operator/tools.py`: approved read, plan, execute, and QA services using opaque inventory IDs.
- `training/corel_operator/mcp_server.py`: loopback-only MCP transport with eight bounded tools.

## Context strategy

`DocumentContextV1` includes page geometry, aggregate object counts, capability counts, and at most 25 relevant text candidates. Text values are hidden by default. A caller may request text explicitly for a bounded planning operation. Arbitrary object dumps are not part of the default context.

## Agent loop

1. Resolve an opaque `file:<hash>` inventory identifier.
2. Inspect the source read-only and build compact context.
3. Ask a provider for a structured plan only.
4. Parse with a schema that rejects extra fields.
5. Apply semantic policy and target resolution.
6. Persist the request, plan hash, source-bound fingerprint, risk, and review state.
7. In `PLAN_ONLY` or `DRY_RUN`, stop without mutation.
8. Only a separate explicit-confirmation path may call the existing working-copy operator.

## Current autonomy

- Level 0, inspect only: verified.
- Level 1, plan and dry-run: verified on 200 real CDRs.
- Level 2, human-confirmed bounded mutation: existing operator path, partially reliable by operation family.
- Level 3, automatic low-risk mutation: not enabled for LLM plans.
- Level 4, bounded batch mutation: not verified.
- Level 5, arbitrary autonomous editing: prohibited.

## Non-goals

This layer is not an aesthetic agent, does not select Gold designs, does not train models, and does not overwrite source CDRs. `planner_is_ai=false` is mandatory for deterministic fixtures and current benchmark results.
