# CorelDRAW AI Template Plugin

> New agent/operator: start with
> [`docs/ANTIGRAVITY_HANDOFF.md`](docs/ANTIGRAVITY_HANDOFF.md), then read the
> linked agent rules, API reference, and local Corel runbook.

Local Windows service that lets a CorelDRAW Docker UI or AI Agent automate
CorelDRAW through Win32 COM. The current agent API adds canvas inspection,
layout composition, typography, z-order, asset fitting/PowerClip and iterative
preview/check/undo controls on top of the existing template workflow.

## What the MVP can do

- Connect to CorelDRAW and serialize COM operations.
- Create CMYK rectangles, ellipses and artistic text.
- Open an existing `.cdr` template and find named shapes.
- Replace editable text placeholders.
- Import a local or generated bitmap into a named image slot.
- Save an editable `.cdr` output.
- Export PDF for production and PNG for preview.
- Load JSON template manifests and render menu data in one API call.
- Expose an HTML UI suitable for adapting into a CorelDRAW Docker panel.
- Optionally call a TikNow-compatible submit/status image API through an
  environment-configured adapter. No third-party endpoint or token is embedded.
- Expose agent-facing design controls for snapshot, transform, batch transform,
  typography, z-order, alignment, distribution, page resize, aspect fitting,
  PowerClip, preview, deterministic checks and undo.

## Architecture

```text
CorelDRAW HTML Docker / AI Agent
              │ HTTP on 127.0.0.1
              ▼
       FastAPI orchestration
              │
      ┌───────┼──────────────┐
      │       │              │
Template   Image provider   Agent design API
registry   adapter          layout / preview / undo
      │       │              │
      └───────┴──────┬───────┘
                     ▼
             CorelDRAW COM bridge
                     ▼
                  CorelDRAW
```

Python is the only owner of CorelDRAW COM state. The HTML panel and AI agents
send HTTP commands and do not edit the document through `window.external`,
preventing two controllers from fighting over the same active document.

## Requirements

- Windows 10/11 64-bit.
- CorelDRAW 2020-2023 for the currently targeted COM behavior.
- Python 3.10+ with the same bitness as CorelDRAW.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

Open CorelDRAW before rendering a job.

- API: `http://127.0.0.1:8001`
- Swagger: `http://127.0.0.1:8001/docs`
- Health: `http://127.0.0.1:8001/health`

The server binds only to localhost. Do not expose it publicly without adding
authentication and an explicit filesystem security model.

## Antigravity / autonomous design

The recommended agent loop is:

```text
snapshot
  -> create/import assets
  -> batch transform
  -> typography + align/distribute + z-order
  -> aspect-fit/PowerClip images
  -> render PNG preview
  -> visual critique
  -> deterministic check
  -> refine or undo
  -> save CDR + export PDF
```

See `docs/ANTIGRAVITY_DESIGN_API.md` and
`docs/ANTIGRAVITY_V15_LAYOUT_API.md` for endpoint details and examples.

## Template contract

A designer creates the `.cdr` template and names objects consistently:

```text
placeholder_title
placeholder_subtitle
placeholder_address
placeholder_phone
placeholder_item_1_name
placeholder_item_1_price
placeholder_item_1_description
placeholder_item_1_image
...
```

A JSON manifest describes those names. See
[`templates/manifests/menu_a4_demo.json`](templates/manifests/menu_a4_demo.json).
The sample manifest points to a placeholder CDR path because binary design
files are not committed. During rendering, either place your template at the
configured path or pass `template_path_override`.

## Render a menu

```powershell
curl.exe -X POST `
  "http://127.0.0.1:8001/api/v1/templates/menu_a4_demo/render-menu" `
  -H "Content-Type: application/json" `
  -d '@menu-job.json'
```

Example `menu-job.json`:

```json
{
  "template_path_override": "D:\\Templates\\menu_a4_demo.cdr",
  "title": "MENU QUÁN NHÀ LONG",
  "subtitle": "Ngon mỗi ngày",
  "address": "Cần Thơ",
  "phone": "0900 000 000",
  "sections": [
    {
      "name": "Món chính",
      "items": [
        {
          "name": "Cơm tấm sườn",
          "price": "35.000",
          "description": "Sườn nướng, trứng và đồ chua",
          "image_path": "D:\\Images\\com-tam.png"
        },
        {
          "name": "Bún bò",
          "price": "40.000",
          "image_prompt": "Vietnamese bun bo Hue food photography, clean menu image"
        }
      ]
    }
  ],
  "output_dir": "D:\\CorelAI\\output",
  "file_stem": "menu-quan-nha-long",
  "generate_missing_images": false,
  "export_pdf": true,
  "export_png": true,
  "preview_dpi": 150
}
```

Output:

```text
output/
├── menu-quan-nha-long.cdr
├── menu-quan-nha-long.pdf
└── menu-quan-nha-long-preview.png
```

When `generate_missing_images` is false, items with `image_prompt` are returned
in `pending_image_prompts`. This lets a user approve prompts before spending
credits. When it is true, a configured image provider generates and inserts the
image automatically.

## Optional image generation

The adapter follows the public submit/status contract used by TikNow-style
plugins, but is configured generically:

```powershell
$env:IMAGE_API_BASE_URL="https://your-provider.example"
$env:IMAGE_API_TOKEN="..."
$env:IMAGE_MODEL="your-image-model"
$env:IMAGE_TIMEOUT_SECONDS="180"
python main.py
```

Expected endpoints:

```text
POST /api/generate/submit
GET  /api/generate/status/{taskId}
```

Without these variables, image generation is disabled and existing local image
paths still work.

## Docker UI

`docker_ui/` contains a lightweight form that calls the local API. Start the
server and open `docker_ui/index.html` for testing. Registering a true CorelDRAW
HTML Docker requires an `AppUI.xslt` matching the exact CorelDRAW version; see
`docker_ui/README.md`.

## Main endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Service and provider status |
| `POST` | `/api/v1/corel/connect` | Verify CorelDRAW COM |
| `POST` | `/api/v1/corel/document/open` | Open a CDR template |
| `POST` | `/api/v1/corel/document/save` | Save editable CDR |
| `GET` | `/api/v1/corel/shapes` | List named shapes |
| `POST` | `/api/v1/corel/text/set` | Replace template text |
| `POST` | `/api/v1/corel/image/place-in-slot` | Fit bitmap to named slot |
| `POST` | `/api/v1/corel/export` | Export PDF or PNG |
| `POST` | `/api/v1/design/save` | Safely save an already named editable CDR |
| `POST` | `/api/v1/design/save-as` | Safely save-as CDR; no overwrite by default |
| `POST` | `/api/v1/design/open` | Safely open an existing CDR |
| `POST` | `/api/v1/design/export` | Safely export PNG/PDF; no overwrite by default |
| `GET` | `/api/v1/design/snapshot` | Inspect active page and objects |
| `POST` | `/api/v1/design/objects/batch-transform` | Batch layout transforms |
| `POST` | `/api/v1/design/object/typography` | Edit text/font/size |
| `POST` | `/api/v1/design/object/order` | Change stacking order |
| `POST` | `/api/v1/design/objects/align` | Align selected objects |
| `POST` | `/api/v1/design/objects/distribute` | Distribute selected objects |
| `POST` | `/api/v1/design/page/resize` | Resize active page |
| `POST` | `/api/v1/design/object/fit-to-frame` | Aspect fit/cover + optional PowerClip |
| `POST` | `/api/v1/design/render-preview` | Export agent preview |
| `POST` | `/api/v1/design/check` | Run deterministic guardrails |
| `POST` | `/api/v1/design/undo` | Undo mutations |
| `GET` | `/api/v1/templates` | List manifests |
| `POST` | `/api/v1/templates/{id}/render-menu` | Produce menu outputs |
| `GET` | `/api/v1/image-provider/status` | Image adapter status |

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The test suite uses COM mocks and runs without CorelDRAW. A real Windows smoke
test is still required for each supported CorelDRAW version, especially bitmap
import positioning, PowerClip behavior, stacking order, page sizing and PDF/PNG
export profiles.
