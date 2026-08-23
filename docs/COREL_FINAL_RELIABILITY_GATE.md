# Corel Final Reliability Gate

## Result

`FINAL_STATUS=BALANCED_PRODUCTION_RELIABILITY_PASS`

This micro-gate addressed only the two blockers recorded at SHA
`32c66fa7a3bac24d72800d339baf7d5f68803b48`. No LLM, training, Gold Grammar,
full census, or full 100-case balanced rerun was used.

## Text target coverage

The 14 previous `NO_SAFE_TEXT_TARGET` cases were inspected and rerun without
exposing customer text:

- `TARGET_NOT_FOUND`: 12
- `MULTIPLE_MATCHES`: 0
- `MIXED_FONT`: 0
- `UNSUPPORTED_TEXT_TYPE`: 0
- `SELECTOR_TOO_STRICT`: 2
- `OTHER`: 0

The two strict-selector cases contained stable, uniquely addressable text with
stable font metadata at 50 pt and 56.74 pt. The planner now uses the existing
72 pt bounded typography ceiling instead of rejecting all display text above
36 pt. Both cases saved, reopened, and remained editable. The 12 documents with
no defensible text target remain `UNSUPPORTED`.

Ten additional text-capable cases were selected deterministically from outside
the original 25-case text cohort using seed
`corel-final-gate-additional-text-v1`; all ten completed. Rerun results replaced
their prior outcomes by stable source token and were not double-counted.

Final text evidence:

```text
TEXT_REPLACE_ATTEMPTED=35
TEXT_REPLACE_EXECUTED=23
TEXT_REPLACE_AUTO_SUCCESS=22
TEXT_REPLACE_NEEDS_REVIEW=1
TEXT_REPLACE_UNSUPPORTED=12
TEXT_REPLACE_FAILED=0
TEXT_REPLACE_SAVE_REOPEN_PASS_RATE=100.0000%
```

## Move failure

Both previous failures targeted text objects:

1. one caused collateral bounding-box changes in five non-target objects;
2. one caused object-identity drift.

Rollback was verified in both original failures. The same documents had seven
and five safe non-text alternatives respectively. Across the previous balanced
cohort, non-text MOVE had 14 successes and zero failures. The planner therefore
now prefers a non-text top-level object when one exists, while retaining text as
a fallback. It does not weaken scope validation, collateral protection, retry
limits, or the bounded 1 mm move.

Both exact failed documents reran successfully using vector targets, saved,
reopened, remained editable, and left their sources unchanged.

```text
MOVE_ATTEMPTED=25
MOVE_EXECUTED=24
MOVE_AUTO_SUCCESS=24
MOVE_UNSUPPORTED=1
MOVE_FAILED=0
MOVE_FAILED_RATE=0.0000%
MOVE_SAVE_REOPEN_PASS_RATE=100.0000%
```

## Safety and regression

- Targeted real cases: 14 prior text refusals + 2 prior MOVE failures + 10
  additional text cases.
- New source mutations: 0.
- Ambiguity controls preserved: 10/10 safe refusals; no ambiguity rule changed.
- Transaction rollback contract preserved; targeted rollback tests pass.
- MCP remains loopback-only with explicit mutation confirmation and eight
  bounded tools.
- Vietnamese command benchmark remains 27/27; unsafe/vague refusal remains 6/6.
- Full census and full balanced cohort were not rerun.

## Verification

```text
SOURCE_MUTATIONS=0
AMBIGUITY_CONTROL_CASES=10
AMBIGUITY_SAFE_REFUSAL=10
TEST_COUNT=441
TEST_STATUS=PASS
COMPILEALL=PASS
GIT_DIFF_CHECK=PASS
```

All final gate requirements pass: text executions are at least 20, text and
MOVE save/reopen rates exceed 95%, MOVE failure rate is at most 5%, source
mutations are zero, and ambiguity refusal remains 100%.

`NEXT_RECOMMENDED_MISSION=REAL_LLM_SUPERVISED_INTEGRATION`
