# Corel Working-Copy Diagnostic

## Result

The single authorized diagnostic MOVE did not reproduce the prior
`COREL_RUNTIME_FAILURE`. The exact medium-risk approval was bound to job
`ui-47f024404a904f4cbd51`, plan hash
`ad83bb901d8b8cf8bc071e576d6082be5e61b716c4bbe6dc6af2d061f2f39624`,
target `static_36`, operation `move`, and the server-issued position arguments.
The working-copy transaction committed one operation, Visual QA passed, the
editable CDR saved and reopened, and the source SHA-256, size, and timestamp
remained unchanged.

No RESIZE or additional real Corel attempt was run.

## Diagnostic instrumentation

Fail-closed Corel runtime errors now retain a structured, sanitized diagnostic
cause containing the current stage, failing runtime function, HRESULT when
available in the exception chain, COM exception type, message, attempt number,
Corel process state, working-copy existence, transaction-started state, and
final source-integrity result. The diagnostic is returned by the existing task
API and persisted with the local UI job record. Existing response fields and
approval behavior are unchanged.

Absolute archive and operator-workspace roots are redacted from diagnostic
messages. Hermetic tests prove exception-chain preservation, redaction, job
persistence, and compatibility of successful API responses.

## Required metric block

```text
DIAGNOSTIC_RUN=PASS_NOT_REPRODUCED
FAILING_STAGE=NOT_REPRODUCED
FAILING_CALL=NOT_REPRODUCED
HRESULT=NOT_REPRODUCED
EXCEPTION_TYPE=NOT_REPRODUCED
SANITIZED_MESSAGE=NONE
TRANSACTION_STARTED=true
SOURCE_MUTATIONS=0
TEST_COUNT=459
TEST_STATUS=PASS

FINAL_STATUS=COREL_FAILURE_NOT_REPRODUCED
```

The earlier failure remains valid historical evidence, but this one-run mission
does not provide evidence for a deterministic failing COM call. If it recurs,
the persisted structured diagnostic will identify the exact stage and retain
the sanitized underlying COM cause without another code-instrumentation change.
