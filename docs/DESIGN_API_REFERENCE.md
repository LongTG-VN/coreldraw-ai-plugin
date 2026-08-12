# Design API Reference

This is the source-of-truth inventory for the FastAPI application in
`main.py`. The service is local-only at `http://127.0.0.1:8001`; interactive
OpenAPI documentation is available at `/docs`.

## Response and failure conventions

- Successful Corel/design mutations normally return `{"status":"success", ...}`.
- Pydantic request failures return HTTP 422.
- Corel connection, object, file, and automation failures return HTTP 503 as
  `{"status":"error","detail":"..."}`.
- A failed grouped transaction returns HTTP 409 with the transaction report.
- Trained-planner unavailable/generation failures return HTTP 503/500 with a
  stable error code.
- Every sync Corel operation is serialized by the singleton
  `CorelDrawBridge`. Individual mutation routes are undoable Corel commands;
  only `/api/v1/design/transaction` creates an explicit grouped transaction.

## Safe document lifecycle

These are the preferred Antigravity endpoints. Paths must be absolute. The
extension is never silently rewritten, the parent directory must exist, `..`
is rejected, and save-as/export default to `overwrite=false`.

| Method/path | Request | Response | Mutation / transaction |
|---|---|---|---|
| `POST /api/v1/design/save` | none | action, absolute `file_path`, `format=cdr`, `editable=true` | Saves the already-named active CDR; single Corel command. Rejects Untitled/non-CDR documents. |
| `POST /api/v1/design/save-as` | `path`, optional `overwrite=false` | action, path, format, overwrite, editable | Saves active document as editable CDR; single command. Only `.cdr`. |
| `POST /api/v1/design/open` | `path` | action, path, format, editable | Opens an existing `.cdr`; document-state mutation, not a grouped transaction. |
| `POST /api/v1/design/export` | `format: pdf|png`, `path`, optional `dpi=300`, `overwrite=false` | action, path, format, dpi, editable=false | Produces a derivative; does not flatten or replace the active CDR. |

PowerShell examples:

```powershell
$base = "http://127.0.0.1:8001"

Invoke-RestMethod -Method Post "$base/api/v1/design/save-as" `
  -ContentType "application/json" `
  -Body '{"path":"D:/DesignAI/output/design_001.cdr","overwrite":false}'

Invoke-RestMethod -Method Post "$base/api/v1/design/export" `
  -ContentType "application/json" `
  -Body '{"format":"png","path":"D:/DesignAI/output/design_001.png","dpi":150,"overwrite":false}'
```

The older `/api/v1/corel/document/open`, `/api/v1/corel/document/save`, and
`/api/v1/corel/export` routes remain for backward compatibility. They normalize
extensions/create parent directories and can overwrite; new agents should not
use them for routine file lifecycle work.

## Inspection, edit, and safety routes

`color` below means `{cyan, magenta, yellow, black}`, each in `0..100`.
Object responses contain the stable Corel shape `name`, type, geometry, child
count, and text/font metadata when applicable.

| Method/path | Purpose | Request fields | Response | Mutation / transaction |
|---|---|---|---|---|
| `GET /health` | Process/provider health | none | service version, Corel automation availability, provider status | No / none |
| `POST /api/v1/corel/connect` | Probe live Corel COM | none | connected, Corel version/document or error | May create an empty doc if none exists / serialized |
| `GET /api/v1/design/snapshot` | Inspect page and recursive objects | none | page metadata and `objects` | No / serialized read |
| `GET /api/v1/design/objects` | Compact object list | none | count and objects | No / serialized read |
| `POST /api/v1/design/object/transform` | Position/size/rotate one object | `shape_name`; optional x,y,width,height,rotation | changed object snapshot | Yes / single |
| `POST /api/v1/design/objects/batch-transform` | Apply bounded transforms | `operations[]` | changed objects | Yes / method-level rollback of applied transforms on failure |
| `POST /api/v1/design/object/duplicate` | Duplicate object | `shape_name`; offsets, `new_name` optional | duplicate snapshot | Yes / single |
| `POST /api/v1/design/object/fill` | Uniform CMYK fill | `shape_name`, `color` | object snapshot | Yes / single |
| `POST /api/v1/design/object/typography` | Change text/font/size | `shape_name`; text/font_name/font_size optional | object snapshot | Yes / single |
| `POST /api/v1/design/object/order` | Change z-order | `shape_name`, mode, optional `relative_to` | object snapshot | Yes / single |
| `POST /api/v1/design/objects/align` | Align named shapes | `shape_names`; horizontal/vertical; `relative_to=selection|page` | object snapshots | Yes / single route |
| `POST /api/v1/design/objects/distribute` | Distribute 3+ shapes | `shape_names`, `axis`, optional `mode=gaps|centers` | object snapshots | Yes / single route |
| `POST /api/v1/design/page/resize` | Set page millimetres | `width`, `height` | page dimensions | Yes / single |
| `POST /api/v1/design/object/fit-to-frame` | Contain/cover or PowerClip | `shape_name`, `frame_shape_name`; mode, powerclip, lock_contents | object/frame result | Yes / single |
| `POST /api/v1/design/object/delete` | Delete named shape | `shape_name` | deleted name | Yes / single |
| `POST /api/v1/design/asset/import` | Import local SVG/vector/raster/PDF | `file_path`; optional name,x,y,width,height | imported object snapshot | Yes / single |
| `POST /api/v1/design/render-preview` | Corel PNG preview | optional `file_path`, `dpi` | PNG path and dpi | Derivative export / serialized |
| `POST /api/v1/design/check` | Deterministic document checks | `min_font_size`, `require_named_objects` optional | validity, issues, snapshot-derived facts | No / serialized read |
| `POST /api/v1/design/undo` | Undo 1–50 commands | optional `steps=1` | undone step count | Yes / Corel undo |
| `POST /api/v1/design/feedback-context` | Snapshot + check + preview | output/check options | snapshot, check, preview/error | Preview derivative; no design mutation |

Typical bounded edit:

```json
{
  "shape_name": "hero_image",
  "x": 105,
  "y": 285,
  "width": 92,
  "height": 130
}
```

Names are the targeting identifiers. Explicitly supplied names are preserved;
otherwise names use `ai_<role>_<8 hex>`. Names are scoped to the active
document, may become stale after delete/open/new document, and are not a
cross-document database ID. Agents must refresh the snapshot after document
lifecycle changes and should assign unique names.

## Grouped transaction

`POST /api/v1/design/transaction` accepts:

```json
{
  "name": "Refine hero and CTA",
  "rollback_on_error": true,
  "include_feedback": true,
  "operations": [
    {"op":"transform","shape_name":"hero","width":100,"height":130},
    {"op":"transform","shape_name":"copy","x":18},
    {"op":"order","shape_name":"cta","mode":"front"}
  ]
}
```

Supported `op` values are `transform`, `batch_transform`, `duplicate`, `fill`,
`typography`, `order`, `align`, `distribute`, `page_resize`, `fit_to_frame`,
`delete`, `import_asset`, `create_rectangle`, `create_ellipse`, `create_text`,
`outline`, and `group`.

The engine calls Corel `BeginCommandGroup`, executes at most 200 operations,
then `EndCommandGroup`. If an operation fails and the group can be ended, it
calls one Corel `Undo`; HTTP 409 reports `rolled_back`, completed operations,
failed index/operation, and any end-group/undo error. Rollback cannot be
guaranteed if Corel itself fails to end or undo the group, so the agent must
inspect the report and refresh the snapshot before proceeding.

## Primitive and legacy Corel routes

| Method/path | Purpose | Request fields | Response / behavior |
|---|---|---|---|
| `GET /api/v1/corel/shapes` | List active-page shapes | none | status, count, shape summaries |
| `POST /api/v1/corel/text/set` | Replace named template text with fitting | shape_name,text; optional max_length,min_font_size,max_width | updated text/shape data |
| `POST /api/v1/corel/image/place-in-slot` | Import image into named slot | image_path,slot_shape_name; optional imported_shape_name,delete_slot | placed object data |
| `POST /api/v1/corel/shape/rectangle` | Create CMYK vector rectangle | x,y,width,height; optional name,color | shape_name |
| `POST /api/v1/corel/shape/ellipse` | Create CMYK vector ellipse | x,y,width,height; optional name,color | shape_name |
| `POST /api/v1/corel/text/artistic` | Create editable artistic text | text,x,y; optional font_name,font_size,color,name | shape_name |
| `POST /api/v1/corel/shape/outline` | Apply CMYK outline | shape_name,width,color | shape_name |
| `POST /api/v1/corel/shape/group` | Group named objects | shape_names (2+), optional group_name | group shape_name |
| `POST /api/v1/corel/document/open` | Legacy template open | `file_path` | opened path; use safe design/open for agents |
| `POST /api/v1/corel/document/save` | Legacy save-as | `file_path` | CDR path; overwrite behavior is legacy |
| `POST /api/v1/corel/export` | Legacy PDF/PNG export | file_path, format, dpi | exported path; overwrite behavior is legacy |

## Planner, templates, and provider routes

| Method/path | Purpose | Request / response |
|---|---|---|
| `POST /api/v1/design/generate` and `POST /design/generate` | Deterministic structured baseline | `DesignGenerateRequest` → `DesignGenerateResponse`; `trained_model=false` |
| `GET /api/v1/design/model/status` | Lazy local Qwen readiness | pinned identity, paths/status, loaded state, research/license flags |
| `POST /api/v1/design/generate-trained` | Qwen3 LoRA best-of-N planner | prompt,width_mm,height_mm; optional candidates,seed,top_k → canonical design, references, ranking, Corel operations; research-only |
| `GET /api/v1/templates` | List template manifests | count and public metadata |
| `GET /api/v1/templates/{template_id}` | Inspect one manifest | public manifest metadata or HTTP 404 |
| `POST /api/v1/templates/{template_id}/render-menu` | Fill/open/save/export a menu template | strict `MenuRenderRequest` → render report |
| `GET /api/v1/image-provider/status` | Inspect optional provider | enabled/configuration status; no generation |

The trained endpoint does not mutate CorelDRAW. It returns deterministic
`corel_operations`; Antigravity must validate and submit those through the
transaction route, inspect/check/render, and then save the editable CDR.
