# Antigravity Design Transactions (v1.6)

Version 1.6 adds an atomic design-plan endpoint so an autonomous agent can send
many CorelDRAW mutations as one undoable command group.

## Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/design/transaction` | Execute up to 200 design operations as one command group |
| `POST` | `/api/v1/design/feedback-context` | Export a preview and return snapshot + deterministic checks |

## Transaction example

```json
{
  "name": "Spa signboard pass 1",
  "rollback_on_error": true,
  "include_feedback": true,
  "preview_path": "storage/previews/spa-pass-1.png",
  "preview_dpi": 150,
  "operations": [
    {
      "op": "page_resize",
      "width": 4000,
      "height": 1200
    },
    {
      "op": "create_rectangle",
      "x": 0,
      "y": 1200,
      "width": 4000,
      "height": 1200,
      "name": "background",
      "color": {"cyan": 5, "magenta": 8, "yellow": 12, "black": 0}
    },
    {
      "op": "create_text",
      "text": "LUMI SPA",
      "x": 600,
      "y": 800,
      "font_name": "Arial",
      "font_size": 240,
      "name": "headline",
      "color": {"cyan": 0, "magenta": 20, "yellow": 60, "black": 20}
    },
    {
      "op": "align",
      "shape_names": ["headline", "background"],
      "horizontal": "center",
      "relative_to": "page"
    }
  ]
}
```

Successful responses contain:

- `status=committed`;
- a unique `transaction_id`;
- one result entry per operation;
- `feedback.snapshot` describing the current canvas;
- `feedback.check` with deterministic layout/print warnings;
- `feedback.preview.file_path` pointing at the generated PNG preview.

## Rollback behavior

The engine wraps mutations with CorelDRAW `BeginCommandGroup` and
`EndCommandGroup`. When an operation fails, it still closes the command group
and then calls one document `Undo`, so all mutations from that transaction are
reverted together when `rollback_on_error=true`.

A failure response uses HTTP 409 and includes:

```json
{
  "status": "rolled_back",
  "transaction_id": "...",
  "completed_operations": 2,
  "failed_index": 2,
  "failed_operation": {"op": "transform", "shape_name": "missing"},
  "error": "...",
  "rolled_back": true,
  "results": []
}
```

If CorelDRAW cannot close the command group or cannot undo, those failures are
returned separately as `end_group_error` and `rollback_error` instead of being
hidden.

## Supported operation names

- `transform`
- `batch_transform`
- `duplicate`
- `fill`
- `typography`
- `order`
- `align`
- `distribute`
- `page_resize`
- `fit_to_frame`
- `delete`
- `import_asset`
- `create_rectangle`
- `create_ellipse`
- `create_text`
- `outline`
- `group`

## Intended autonomous loop

```text
prompt
  -> snapshot / retrieve references
  -> plan operations
  -> POST /design/transaction
  -> inspect feedback preview
  -> critique
  -> send a smaller corrective transaction
  -> repeat until accepted
  -> save CDR + export PDF
```

The preview/check stage happens after the mutation command group is committed.
A preview-export error does not silently undo an otherwise valid design; it is
reported inside the `preview` object so the agent can retry rendering.
