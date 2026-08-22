# Corel Agent Plan Schema

## Request

`CorelAgentRequestV1` accepts:

- `request_id`: bounded stable identifier;
- `document_id`: opaque `file:<32 lowercase hex>` inventory ID;
- `instruction`: 1–2000 characters;
- `execution_mode`: `PLAN_ONLY`, `DRY_RUN`, or `EXECUTE_CONFIRMED`;
- `max_planning_steps`: 1–10.

Paths are not document identifiers.

## Plan envelope

`CorelPlanEnvelopeV1` binds:

- the request and document IDs;
- a strict existing `MutationPlanV1`;
- constraints and safe output intents;
- confidence and review requirement;
- planner provenance.

The embedded `plan_id` must equal `request_id`. Extra fields fail Pydantic validation. A plan with `source=llm` must have `planner_type=llm` and `planner_is_ai=true`; deterministic and fixture outputs cannot claim AI provenance.

## Current mutation authority

Allowed action vocabulary is inherited from the bounded operator. Agent policy currently classifies:

| Action | Risk | Notes |
| --- | --- | --- |
| unique `REPLACE_TEXT` | LOW | Stable object, exact text, phone, or price selector |
| `MOVE` | MEDIUM | Bounded geometry; review required |
| `RESIZE` | MEDIUM | Bounded geometry; review required |
| `ROTATE` | MEDIUM | Bounded geometry; review required |
| `SET_FONT` | MEDIUM | Stable text target; review required |
| `SET_FONT_SIZE` | MEDIUM | Stable text target; review required |
| unknown or broader mutation | DISALLOWED | Rejected before execution |

Output requests are limited to `CDR`, `PDF`, and `PNG`, target only the job workspace, and cannot overwrite. They are intents, not planner-granted filesystem authority.

## Example

```json
{
  "schema_version": "1.0",
  "request_id": "job-001",
  "goal": "Đổi số điện thoại thành giá trị đã cung cấp",
  "document_id": "file:00000000000000000000000000000000",
  "plan": {
    "schema_version": "1.0",
    "plan_id": "job-001",
    "source": "deterministic",
    "intent": "replace one unique phone target",
    "actions": []
  },
  "constraints": ["PRESERVE_ALL_UNTARGETED_OBJECTS"],
  "output_requests": [],
  "confidence": 1.0,
  "requires_review": false,
  "provenance": {
    "schema_version": "1.0",
    "planner_type": "deterministic",
    "planner_provider": "local",
    "planner_model": "controlled_instruction_v1",
    "planner_is_ai": false
  }
}
```

The empty `actions` list above is documentation-only and is rejected by the actual mutation-plan contract. Runtime plans must contain at least one valid action.

## Validation order

1. Strict JSON/schema parse.
2. Request/document binding.
3. Maximum action count.
4. Unsafe text/path/code scan.
5. Action and selector allowlist.
6. Risk classification and review decision.
7. Execution-mode check.

Schema-valid does not imply execution-authorized.
