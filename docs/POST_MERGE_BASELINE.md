# Post-Merge Baseline

## Git and host

- Baseline SHA: `8a50d10e3e8a83cfe2cfd5fbf30d5ea521b8a601`
- Stabilization branch: `codex/post-merge-stabilization`
- Python: 3.11.9, 64-bit
- OS: Windows 11, build 26100
- Corel runtime observed: CorelDRAW 27.0.0.121 (evaluation installation)
- Authorized remote planner keys detected: none

The worktree was clean when the branch was created. `origin/main` and local
`main` pointed to the same baseline SHA.

## Verification before changes

- `python -m pytest -q`: **467 passed**, one third-party
  Starlette/httpx deprecation warning, no failures, skips, collection errors,
  or import errors.
- `python -m compileall -q training tests`: PASS.
- Top-level tracked Python modules via `python -m py_compile`: PASS.
- `git diff --check`: PASS.
- Main GitHub Actions run `33458923598`: PASS on the Python 3.10/3.11/3.12
  matrix.

Running `python -m compileall -q .` on this workstation also traverses the
ignored `.venv-training` directory. It reports a Python-3.12-only syntax file
inside the installed Torch test package while the host interpreter is 3.11.
That is not repository source. CI has no local virtualenv and successfully runs
the configured repository-wide command.

## Dependency and import audit

The base runtime is bounded by `requirements.txt`: pywin32 (Windows only),
Pydantic, FastAPI, Uvicorn, Pillow, and MCP. Pytest/httpx are development-only.
Qwen and vision dependencies remain in explicit training requirement files and
are not required by the Corel Operator startup or CI.

The OpenAI planner adapter imports the SDK lazily only after detecting
`OPENAI_API_KEY`. With no key it fails closed as `PROVIDER_NOT_CONFIGURED`.
Anthropic configuration is detected but has no adapter and fails closed as
`PROVIDER_ADAPTER_UNAVAILABLE`. Neither provider is required for local startup,
tests, deterministic planners, or the Codex-hosted UI path.

## Privacy baseline

No tracked CDR/CDT, SQLite/database, model checkpoint, PNG/JPEG/PDF review
artifact, or `.env` file was found. No recognizable committed API token was
found. Strings resembling local customer paths occur only in privacy-guard
deny-lists and documented workspace conventions; no customer source path is
recorded here.
