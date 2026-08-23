# Corel Codex UI MVP Report

## Result

UI_START=`python -m training.tools.corel_codex_ui --archive-root "C:\Users\Admin\Downloads\a-20260814T131644Z-1-001\a" --inventory "training\workspace\company_archive\archive.sqlite" --workspace "training\workspace\company_archive\operator_codex_ui" --port 8004`

Local URL: `http://127.0.0.1:8004/corel-ui`

DOCUMENT_INSPECTION=PASS — opaque inventory ID only; 1 page, 17 objects, 4 editable text objects, 9 vectors; CorelDRAW 22.0.0.412.

COMMAND_INPUT=PASS — Vietnamese request: `Đổi nội dung object static_31 thành văn bản benchmark 66K`.

PLAN_PREVIEW=PASS — authenticated Codex CLI completed a read-only `corel_operator` MCP inspection, verified `static_31` and parent `static_28`, and returned a strict `CorelPlanEnvelopeV1`. The server rejected malformed envelopes during preflight and accepted only the schema-valid plan.

APPROVAL_GATE=PASS — no mutation occurred during planning; Approve was enabled only for an accepted `LOW_RISK` plan and the API requires literal `approved=true`. Duplicate/concurrent approval is blocked.

MCP_EXECUTION=PASS — the approved `replace_text` plan ran through `OperatorToolService` on a fresh working copy. The browser never called COM, VBA, shell, or an arbitrary filesystem path.

VISUAL_QA=PASS — no QA reason codes.

BEFORE_AFTER_DIFF=PASS — `working_copy_before.png`, `working_copy_after.png`, and server-generated `working_copy_diff.png` exist and are served through fixed artifact kinds.

CDR_OUTPUT=PASS — real Corel working copy saved and reopened; `working_copy.cdr` is 92,631 bytes and editability verification passed.

PDF_OUTPUT=PASS — `working_copy.pdf` exists (394,888 bytes).

PNG_OUTPUT=PASS — `working_copy_after.png` exists (41,317 bytes).

UNDO_ROLLBACK=SUPPORTED_WITH_LIMITS — Cancel is available before execution and operator failures use transactional automatic rollback. Post-commit destructive undo is intentionally unsupported; the committed working copy is preserved and the UI reports this explicitly.

## Demo evidence

REAL_UI_DEMOS=1

UI_DEMO_SUCCESS=1

SOURCE_MUTATIONS=0

Task ID: `ui-cf41883ddca24a808fe8`

Execution result: `AUTO_SUCCESS`; operation count 1; transaction committed; save true; reopen true; editability true; source unchanged true.

Ignored local evidence root:

`training/workspace/company_archive/operator_codex_ui/runs/ui-cf41883ddca24a808fe8/`

## Verification

Focused UI tests: 6 passed.

TEST_COUNT=447

TEST_STATUS=PASS

`python -m compileall -q training tests`: PASS

`python -m pytest -q`: 447 passed, 1 deprecation warning.

`git diff --check`: PASS

## Final status

FINAL_STATUS=COREL_CODEX_UI_MVP_PASS

NEXT_RECOMMENDED_MISSION=COREL_AI_OPERATOR_V1_PRODUCTIZATION
