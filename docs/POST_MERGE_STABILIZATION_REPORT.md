# Post-Merge Stabilization Report

# RESULT

`POST_MERGE_STABLE_WITH_DOCUMENTED_LIMITATIONS`

The consolidation is complete, tests/CI are green, the canonical operator path
is coherent, and a bounded real-Corel smoke passed without source mutation. No
runtime code change was justified; this branch only adds current-state audit
and handoff documentation.

# GIT

- Starting SHA: `8a50d10e3e8a83cfe2cfd5fbf30d5ea521b8a601`
- Source branch: `main`
- Stabilization branch: `codex/post-merge-stabilization`
- Consolidated remote branches with unique commits outside main: 0 of 18
- Merge/cherry-pick performed: no

# BASELINE

- Python: 3.11.9
- Corel runtime: 27.0.0.121
- Pre-change pytest: 467 passed
- Source compile: PASS
- Diff check: PASS
- Main CI run 33458923598: PASS (Python 3.10/3.11/3.12)

Repository-wide local compile traversed an ignored training virtualenv and hit
a Python-3.12-only Torch test helper under a Python 3.11 interpreter. The
tracked source-only compile and clean-checkout CI compile passed.

# BRANCH AUDIT

Every remote feature, research, reliability, UI, and stabilization branch is an
ancestor of the consolidation commit. No orphaned product fix was found. See
`POST_MERGE_BRANCH_AUDIT.md`.

# ARCHITECTURE

The canonical supervised path is launcher -> loopback UI -> Codex structured
plan -> strict schema/policy -> approval -> serialized tool service -> fresh
working copy -> Corel transaction -> structural/visual QA -> save/reopen ->
versioned editable outputs. `main.py` remains a lower-level Design API surface,
not an approval bypass. See `CANONICAL_EXECUTION_PATH.md`.

# STARTUP AND HEALTH

The canonical preflight returned:

```text
COREL=READY
MCP=READY
OPERATOR=READY
CODEX=READY
```

MCP registration is enabled and local. The startup path does not require an
external LLM credential. `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` were absent.

# SAFETY AND PRIVACY

- Source policy: read-only; all mutations on new working copies.
- Corel ownership: serialized in `OperatorToolService`.
- Approval: low-risk explicit approval; medium-risk job/plan/target/argument
  binding.
- Failures: transaction rollback or fail closed; structured COM diagnostics.
- Tracked source CDR/CDT/database/model/review binaries: 0.
- Recognizable committed credentials: 0.
- Customer/local source paths added by this stabilization: 0.

# REAL COREL SMOKE

One opaque inventory document was used for three bounded checks; no source path
or customer filename is recorded.

| Check | Result |
| --- | --- |
| Read-only inspect | PASS; 1 page, 17 objects, source policy READ_ONLY |
| Text replace on stable text object | AUTO_SUCCESS; transaction/QA/save/reopen/editability PASS |
| MOVE +1 mm on stable vector object | exact-plan medium-risk approval; AUTO_SUCCESS; transaction/QA/save/reopen/editability PASS |
| Source mutations | 0 |

Artifacts remain in the ignored local operator workspace. No private artifact
was committed.

# PROVIDERS AND RESEARCH ISOLATION

The optional OpenAI adapter imports lazily, produces only strict host-bound
plans, and fails closed without configuration. Anthropic has no adapter and
fails closed. Qwen remains preserved. Failed v0.3.4 visual retrieval and v0.3.5
vision critic research remain disabled; no training or research run occurred.

# TESTS

The suite map is documented in `TEST_SUITE_MAP.md`. Final verification is
467/467 passing locally. GitHub Actions run `33476459405` verified stabilization
commit `50d34da` on Python 3.10, 3.11, and 3.12; compile and pytest passed in all
three jobs. The runner emitted a non-failing notice that v4/v5 GitHub actions
are being forced from deprecated Node.js 20 to Node.js 24.

# LIMITATIONS

1. Corel COM remains a stateful desktop dependency; transient failures are
   diagnosed and fail closed rather than hidden.
2. Some legacy or pasteboard-heavy documents may lack trustworthy canonical
   visual evidence and require review.
3. Visual QA is integrity QA, not aesthetic judgment.
4. Local `compileall .` should run in a clean checkout or exclude ignored
   virtualenvs; CI already provides the clean-checkout result.

# FINAL STATUS

```text
CANONICAL_PATH=VERIFIED
STARTUP_PREFLIGHT=READY
MCP=READY
REAL_COREL_SMOKE=PASS
SOURCE_MUTATIONS=0
PROVIDER_REQUIRED=false
REAL_LLM_CONFIGURED=false
RESEARCH_DEFAULT_ENABLED=false
PRODUCTION_SCOPE=SUPERVISED_LOCAL_V1
FINAL_STATUS=POST_MERGE_STABLE_WITH_DOCUMENTED_LIMITATIONS
```
