# Antigravity Design API

Version 1.4 adds an agent-facing API for iterative CorelDRAW design work. The
intended loop is:

```text
inspect canvas -> edit objects -> render preview -> critique/check -> refine -> save
```

The service still binds to `127.0.0.1`; Python remains the single owner of
CorelDRAW COM state.

## Agent endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/design/snapshot` | Read page metadata and recursive object snapshots |
| `GET` | `/api/v1/design/objects` | Read current objects only |
| `POST` | `/api/v1/design/object/transform` | Move, resize, or rotate a named object |
| `POST` | `/api/v1/design/object/duplicate` | Duplicate and offset a named object |
| `POST` | `/api/v1/design/object/fill` | Apply a uniform CMYK fill |
| `POST` | `/api/v1/design/object/delete` | Delete a named object |
| `POST` | `/api/v1/design/asset/import` | Import an SVG/vector/bitmap asset |
| `POST` | `/api/v1/design/render-preview` | Export the active page to PNG |
| `POST` | `/api/v1/design/check` | Run deterministic layout/print guardrails |
| `POST` | `/api/v1/design/undo` | Undo one or more CorelDRAW operations |

Existing primitive endpoints for rectangles, ellipses, artistic text, outline,
grouping, saving, PDF export and template rendering remain available.

## Example autonomous loop

1. `GET /api/v1/design/snapshot`
2. Create or import the required artwork.
3. Use `/object/transform` and `/object/fill` to refine composition.
4. `POST /api/v1/design/render-preview`.
5. Let the visual agent inspect the PNG.
6. `POST /api/v1/design/check` for deterministic guardrails.
7. Refine again or call `/api/v1/design/undo` when a mutation is bad.
8. Save the editable CDR and export the final PDF.

## Transform example

```json
{
  "shape_name": "headline",
  "x": 20,
  "y": 130,
  "width": 160,
  "height": 24,
  "rotation": 0
}
```

Coordinates and sizes use the active CorelDRAW document unit. The current COM
bridge enforces millimeters when possible.

## Import example

```json
{
  "file_path": "D:\\CorelAI\\assets\\logo.svg",
  "name": "brand_logo",
  "x": 15,
  "y": 180,
  "width": 35,
  "height": 35
}
```

The v1 allow-list is SVG, EPS, PDF, AI, CMX, PNG, JPG/JPEG, WEBP and BMP. Import
uses CorelDRAW's native auto-sense import instead of parsing vector files in
Python.

## Design check

The initial deterministic checker reports:

- invalid zero/negative object size;
- objects outside the active page bounds;
- text below a configurable minimum font size;
- unnamed objects when `require_named_objects=true`.

This checker is intentionally simple. It is designed to be combined later with
a visual critic/reward model rather than pretending deterministic rules can
judge aesthetics.

## Safety notes

The API can open/import/save files from the local machine. Keep the service on
localhost. Before exposing it to another machine, add authentication and a
filesystem sandbox/allow-list for readable and writable directories.
