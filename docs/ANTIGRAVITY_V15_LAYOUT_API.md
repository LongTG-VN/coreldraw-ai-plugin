# Antigravity Layout API v1.5

Version 1.5 extends the agent-facing CorelDRAW API from primitive object edits to deterministic layout composition.

## New endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/design/objects/batch-transform` | Move/resize/rotate many objects in one serialized COM session |
| POST | `/api/v1/design/object/typography` | Update text, font family and font size |
| POST | `/api/v1/design/object/order` | Move an object front/back or relative to another object |
| POST | `/api/v1/design/objects/align` | Align objects to selection bounds or page bounds |
| POST | `/api/v1/design/objects/distribute` | Distribute objects evenly by gaps or centers |
| POST | `/api/v1/design/page/resize` | Resize the active CorelDRAW page |
| POST | `/api/v1/design/object/fit-to-frame` | Aspect contain/cover an object into a named frame, optionally using PowerClip |

## Recommended Antigravity loop

```text
snapshot
  -> create/import assets
  -> batch-transform
  -> typography
  -> align/distribute
  -> fit-to-frame / PowerClip
  -> z-order
  -> render-preview
  -> critique
  -> design-check
  -> refine or undo
  -> save CDR/PDF
```

## Examples

### Batch transform

```json
POST /api/v1/design/objects/batch-transform
{
  "operations": [
    {"shape_name": "headline", "x": 15, "y": 120, "width": 150},
    {"shape_name": "logo", "x": 170, "y": 125, "width": 25, "height": 25}
  ]
}
```

### Typography

```json
POST /api/v1/design/object/typography
{
  "shape_name": "headline",
  "text": "KHA THUAN",
  "font_name": "Arial",
  "font_size": 32
}
```

### Align to page

```json
POST /api/v1/design/objects/align
{
  "shape_names": ["headline", "subtitle"],
  "horizontal": "center",
  "relative_to": "page"
}
```

### Distribute cards

```json
POST /api/v1/design/objects/distribute
{
  "shape_names": ["card_1", "card_2", "card_3", "card_4"],
  "axis": "horizontal",
  "mode": "gaps"
}
```

### Aspect cover + PowerClip

```json
POST /api/v1/design/object/fit-to-frame
{
  "shape_name": "hero_photo",
  "frame_shape_name": "hero_frame",
  "mode": "cover",
  "powerclip": true,
  "lock_contents": true
}
```

`cover` preserves aspect ratio and fills the frame before adding the content to PowerClip. `contain` preserves the entire source inside the frame without cropping.

## Design notes

Alignment and distribution are calculated in Python from CorelDRAW object bounds. This keeps agent behavior deterministic and avoids coupling requests to CorelDRAW enum values. Z-order, page sizing and PowerClip use native CorelDRAW COM methods.
