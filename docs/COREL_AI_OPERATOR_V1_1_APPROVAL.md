# Corel AI Operator V1.1 — Explicit Medium-Risk Approval

## Result

The V1.1 approval contract is implemented for existing `MOVE` and `RESIZE`
plans. Approval is server-side, limited to medium risk, and bound to the exact
job, plan hash, target object IDs, operation list, and operation arguments.
Changing any bound field, cancelling, rolling back, completing, or replacing
the job invalidates the approval. Low-risk execution and the global mutation
policy remain unchanged.

The four requested real working-copy cases could not be completed on this
machine. CorelDRAW 2020 reports `Trial Expired`; the process can start, but the
read-only MCP inspection fails before planning with COM error `Server execution
failed (-2146959355)`. No mutation was attempted or accepted. This runtime
blocker is kept separate from the passing hermetic approval-contract tests.

## Approval lifecycle

```text
PLANNED
→ WAITING_MEDIUM_RISK_APPROVAL
→ APPROVED
→ EXECUTING
→ PASS | NEEDS_REVIEW | ROLLED_BACK | FAILED

WAITING_MEDIUM_RISK_APPROVAL | APPROVED
→ CANCELLED
```

The normal `Approve` control cannot elevate a medium-risk plan. The separate
`Approve medium-risk change` control submits the exact server-issued binding;
the backend revalidates both policy and binding immediately before execution.
Only `MOVE` and `RESIZE` are eligible. Planner-requested review, ambiguous
targets, unstable selectors, and other operations are not elevated.

## UI verification

The local UI at `http://127.0.0.1:8004/corel-ui` was reloaded and inspected in
the browser. It exposes the separate medium-risk button, keeps it disabled when
there is no eligible exact plan, displays source and execution safety policies,
and produced no browser console errors during the check.

The UI health badge currently detects the Corel process only. It must not be
interpreted as proof that COM is usable; the real MCP inspection attempt is the
authoritative runtime evidence for this report.

## Real-case evidence

```text
MOVE_APPROVED_TEST=BLOCKED_COREL_TRIAL_EXPIRED
RESIZE_APPROVED_TEST=BLOCKED_COREL_TRIAL_EXPIRED
CANCEL_TEST=BLOCKED_REAL_RUNTIME; PASS_HERMETIC
STALE_APPROVAL_TEST=BLOCKED_REAL_RUNTIME; PASS_HERMETIC

MEDIUM_RISK_EXECUTIONS=0
AUTO_SUCCESS=0
NEEDS_REVIEW=0
FAILED=0
PLANNING_BLOCKED=1

SAVE_REOPEN=0/0
SOURCE_MUTATIONS=0
```

The source selected for the attempted smoke retained the same SHA-256, byte
length, and modification timestamp after the failed read-only inspection.

## Verification

```text
TEST_COUNT=457
TEST_STATUS=PASS
COMPILEALL=PASS

FINAL_STATUS=COREL_AI_OPERATOR_V1_1_BLOCKED
BLOCKER=CORELDRAW_2020_TRIAL_EXPIRED_COM_SERVER_EXECUTION_FAILED
```

V1.1 must not be promoted to `COREL_AI_OPERATOR_V1_READY` until the four real
working-copy acceptance cases pass on a licensed, COM-usable CorelDRAW runtime.
