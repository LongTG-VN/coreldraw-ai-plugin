# Local CorelDRAW Runbook

## Requirements

- Windows 10/11, 64-bit.
- CorelDRAW 2020–2023; the final handoff smoke used CorelDRAW 2020
  `22.0.0.412`.
- Python 3.10+ with the same bitness as CorelDRAW.
- Runtime dependencies from `requirements.txt`, including `pywin32`.
- One local API process and one Corel mutation owner.

## Start API

Open CorelDRAW, then in PowerShell:

```powershell
cd D:\codex\coreldraw-ai-plugin
python -m pip install -r requirements.txt
python main.py
```

The server binds to `127.0.0.1:8001`. Do not expose it publicly.

## Verify API and Corel connection

```powershell
$base = "http://127.0.0.1:8001"
Invoke-RestMethod "$base/health"
Invoke-RestMethod -Method Post "$base/api/v1/corel/connect"
Invoke-RestMethod "$base/api/v1/design/snapshot"
```

`corel/connect` should report `connected=true` and an application version.
The bridge uses the active document, or creates an empty document if Corel has
none. Verify the returned document name before mutating it.

## Create simple editable objects

Use one grouped transaction:

```powershell
$body = @{
  name = "Antigravity simple editable design"
  rollback_on_error = $true
  include_feedback = $false
  operations = @(
    @{op="create_rectangle"; name="ag_background"; x=20; y=250; width=70; height=45; color=@{cyan=0;magenta=80;yellow=70;black=0}},
    @{op="create_ellipse"; name="ag_mark"; x=110; y=245; width=45; height=45; color=@{cyan=70;magenta=0;yellow=30;black=0}},
    @{op="create_text"; name="ag_headline"; text="Editable Design"; x=20; y=170; font_name="Arial"; font_size=28; color=@{cyan=0;magenta=0;yellow=0;black=100}}
  )
} | ConvertTo-Json -Depth 8
Invoke-RestMethod -Method Post "$base/api/v1/design/transaction" `
  -ContentType "application/json" -Body $body
```

Refresh `/api/v1/design/snapshot` and verify all three unique names.

## Check and render preview

Create the output directory yourself; the safe endpoint does not silently
create it.

```powershell
New-Item -ItemType Directory -Force D:\DesignAI\output | Out-Null
Invoke-RestMethod -Method Post "$base/api/v1/design/check" `
  -ContentType "application/json" -Body '{"require_named_objects":true}'
Invoke-RestMethod -Method Post "$base/api/v1/design/export" `
  -ContentType "application/json" `
  -Body '{"format":"png","path":"D:/DesignAI/output/design_001.png","dpi":150,"overwrite":false}'
```

`render-preview` is retained for iterative legacy workflows; the safe
`design/export` route is preferred for handoff file lifecycle because it uses
strict paths and no-overwrite defaults.

## Save editable CDR

First save:

```powershell
Invoke-RestMethod -Method Post "$base/api/v1/design/save-as" `
  -ContentType "application/json" `
  -Body '{"path":"D:/DesignAI/output/design_001.cdr","overwrite":false}'
```

Subsequent save of the already-named active CDR:

```powershell
Invoke-RestMethod -Method Post "$base/api/v1/design/save"
```

The primary `.cdr` keeps text, vectors, groups, and imported assets as separate
objects where Corel supports them.

## Reopen CDR and export PDF

```powershell
Invoke-RestMethod -Method Post "$base/api/v1/design/open" `
  -ContentType "application/json" `
  -Body '{"path":"D:/DesignAI/output/design_001.cdr"}'
Invoke-RestMethod "$base/api/v1/design/snapshot"
Invoke-RestMethod -Method Post "$base/api/v1/design/export" `
  -ContentType "application/json" `
  -Body '{"format":"pdf","path":"D:/DesignAI/output/design_001.pdf","overwrite":false}'
```

Confirm object names/text in the reopened snapshot before claiming editability.

## Undo a transaction

If a successful mutation needs reversal:

```powershell
Invoke-RestMethod -Method Post "$base/api/v1/design/undo" `
  -ContentType "application/json" -Body '{"steps":1}'
```

For HTTP 409, inspect whether the transaction already reports
`rolled_back=true`; do not automatically undo twice.

## Human review service

The separate blinded Phase 1.2 queue is local-only:

```powershell
python -m training.tools.human_review_server `
  --queue v04_phase1_2_category_pilot --port 8004
```

Open `http://127.0.0.1:8004/review`. This service does not control CorelDRAW.

## Shutdown

Finish the current HTTP request, save the CDR, then stop FastAPI with
`Ctrl+C`. Close only the Corel documents you intend to close. Avoid terminating
CorelDRAW while a transaction/export/save is in progress.

## Troubleshooting

| Problem | Check / action |
|---|---|
| Corel not running | Start CorelDRAW, then call `/corel/connect`. The bridge may dispatch Corel when installed, but an explicit visible launch is easier to verify. |
| COM unavailable | Confirm Windows, matching Python/Corel bitness, and `pywin32`; CI intentionally has no COM. |
| Wrong active document | Stop mutations, inspect snapshot/document name, open the intended CDR through `/design/open`. |
| Object ID stale | Refresh snapshot after open/new/delete/undo; use a current unique shape name. |
| Port conflict | Stop the other local process or start the human-review server on another port. Main API is fixed at 8001 in `main.py`. |
| File path rejected | Use an absolute path with no `..`, correct `.cdr`/`.png`/`.pdf` extension, and an existing parent directory. |
| Save target already exists | Choose a new filename. Set `overwrite=true` only with explicit authorization. |
| Untitled save rejected | Use `/api/v1/design/save-as` before `/api/v1/design/save`. |
| Transaction HTTP 409 | Inspect rollback fields, refresh snapshot/check, then decide whether a bounded repair or undo is appropriate. |
| PNG COM type error on old checkout | Update to the handoff checkpoint; it supplies both Corel export option structs required by Corel 2020 pywin32 marshalling. |
