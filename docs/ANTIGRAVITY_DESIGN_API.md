# CorelDRAW Antigravity Design API

The agent-facing API lets Antigravity inspect and iteratively edit an active CorelDRAW document through the local FastAPI service. Python remains the single owner of CorelDRAW COM state.

```text
inspect -> compose -> preview -> critique -> check -> refine -> save
```

## Core agent endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/design/snapshot` | Read page metadata and recursive object snapshots |
| GET | `/api/v1/design/objects` | Read current objects |
| POST | `/api/v1/design/object/transform` | Move, resize or rotate one object |
| POST | `/api/v1/design/objects/batch-transform` | Transform many objects in one serialized COM session |
| POST | `/api/v1/design/object/duplicate` | Duplicate an object |
| POST | `/api/v1/design/object/fill` | Apply uniform CMYK fill |
| POST | `/api/v1/design/object/typography` | Update text, font and font size |
| POST | `/api/v1/design/object/order` | Front/back/relative stacking order |
| POST | `/api/v1/design/objects/align` | Align objects to selection or page |
| POST | `/api/v1/design/objects/distribute` | Distribute objects by gaps or centers |
| POST | `/api/v1/design/page/resize` | Resize the active page |
| POST | `/api/v1/design/asset/import` | Import SVG/vector/bitmap assets |
| POST | `/api/v1/design/object/fit-to-frame` | Aspect contain/cover into a frame, optionally PowerClip |
| POST | `/api/v1/design/object/delete` | Delete an object |
| POST | `/api/v1/design/render-preview` | Export current page to PNG for visual critique |
| POST | `/api/v1/design/check` | Run deterministic guardrails |
| POST | `/api/v1/design/undo` | Undo recent CorelDRAW operations |

Existing primitive endpoints for rectangles, ellipses, artistic text, outline, grouping, saving, PDF export and template rendering remain available.

See `ANTIGRAVITY_V15_LAYOUT_API.md` for request examples.

## Recommended loop

1. Call `/snapshot`.
2. Create primitive Corel shapes or import SVG/images.
3. Use batch transforms instead of many tiny HTTP calls.
4. Apply typography, alignment, distribution and z-order.
5. Use `fit-to-frame` with `cover + powerclip` for hero/product images.
6. Render a PNG preview.
7. Let the vision agent critique the preview.
8. Apply corrections and call `/design/check`.
9. Undo bad mutations when necessary.
10. Save editable CDR and export PDF when accepted.

## Deterministic checks

The current checker reports invalid object size, objects outside page bounds, text below a configurable minimum size, and unnamed objects when requested. A future visual critic/reward model should handle aesthetics; deterministic checks should remain focused on measurable production constraints.

## Safety

The service binds to localhost. Do not expose the API publicly without authentication and a filesystem sandbox. File import paths are local machine paths and should be treated as privileged input.
