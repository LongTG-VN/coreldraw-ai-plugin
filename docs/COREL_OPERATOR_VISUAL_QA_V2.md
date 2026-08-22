# Corel Operator Visual QA V2

## Purpose

Visual QA V2 is an integrity check for bounded CorelDRAW mutations. It verifies that the intended object changed within the expected page-space region while page geometry, protected objects, and the remainder of the raster remain stable. It does not judge aesthetics.

## Export-dimension root cause

The Run2 exporter requested a maximum raster box and left `MaintainAspect` enabled. On three reproduced cases, Corel returned content-dependent dimensions even though page width, page height, units, and object count were unchanged. For example, one fixed 102 x 69 mm page changed from 2283 x 1624 pixels to 2385 x 1624 pixels after a text-size mutation. Disabling `MaintainAspect` made the requested dimensions stable, but this is trustworthy only when the export is explicitly anchored to the page area.

The production comparison path therefore uses:

- the active page's verified bounding box as `ExportArea`;
- `MaintainAspect = false`;
- explicit `SizeX` and `SizeY` derived from physical page geometry;
- the current-page export range;
- exact post-export dimension verification.

Corel API references used for the implementation:

- [Document.ExportBitmap](https://community.coreldraw.com/sdk/api/draw/24/m/document.exportbitmap)
- [StructExportOptions.MaintainAspect](https://community.coreldraw.com/sdk/api/draw/22/p/structexportoptions.maintainaspect)
- [StructExportOptions.SizeX](https://community.coreldraw.com/sdk/api/draw/20/p/structexportoptions.sizex?lang=cli)
- [StructExportOptions.ExportArea](https://community.coreldraw.com/sdk/api/draw/22/p/ivgstructexportoptions.exportarea)
- [Page.GetBoundingBox](https://community.coreldraw.com/sdk/api/draw/25/m/page.getboundingbox)

## Canonical page mapping

`training/corel_operator/canonical_export.py` is the single geometry implementation. It:

1. converts the Corel page unit to inches;
2. multiplies by the configured DPI;
3. rounds half-up deterministically;
4. bounds the raster to 2400 pixels on either axis and 8,000,000 total pixels;
5. records unbounded dimensions, bounded dimensions, scale, page origin, DPI, and unit;
6. rejects the evidence if the emitted PNG does not exactly match the expected dimensions.

Portrait, landscape, millimetre, inch, point, pica, centimetre, metre, yard, foot, kilometre, mile, quarter-millimetre, tenth-micron, and pixel mappings are covered by hermetic tests. No generic Pillow resize or crop is used to turn mismatched evidence into a pass.

## Page-geometry provenance

Every `VisualIntegrityQaV2Report` contains:

- page width, height, origin, unit, unit code, and page count before and after;
- expected canonical dimensions;
- actual before and after raster dimensions;
- target IDs and expected change region;
- thresholds and measured difference metrics;
- structural validation errors;
- `aesthetic_judgment: false`.

An unexpected page-geometry change, object-count change, missing target, protected structural change, invalid canonical export, unresolved dimension mismatch, or failed page registration is a structural failure. It is never normalized away.

## Expected change region

The region is the union of each target's normalized bounding box before and after, expanded by one percent of page width and height and clipped to the canonical raster. Multi-action transactions use all resolved target IDs. A target outside the active canonical page is rejected before mutation because the page-anchored preview cannot observe it reliably.

## Metrics and conservative thresholds

The first production profile records:

| Metric | Threshold |
| --- | ---: |
| Per-channel pixel difference | 8 |
| Minimum total changed-pixel ratio | 0.000001 |
| Maximum total changed-pixel ratio | 0.45 |
| Outside-region changed-pixel ratio | 0.0025 |
| Outside fraction of all changed pixels | 0.35 |
| Outside-region ratio promoted to failure | 0.05 |

The outside-scope reason requires both the absolute outside-page ratio and the fraction-of-change threshold. Values above the severe threshold fail; bounded uncertain values require review. The report also stores mean absolute difference and the largest connected changed component ratio.

These thresholds are integrity guardrails derived from the reproduced pilot behavior. They are not an aesthetic score and must not be tuned after seeing a candidate merely to make it pass.

## Reason codes

- `PAGE_GEOMETRY_CHANGED`
- `OBJECT_COUNT_CHANGED`
- `TARGET_MISSING`
- `NON_TARGET_STRUCTURAL_CHANGE`
- `CANONICAL_EXPORT_FAILED`
- `VISUAL_CHANGE_OUT_OF_SCOPE`
- `NO_VISIBLE_TARGET_CHANGE`
- `EXCESSIVE_TARGET_CHANGE`
- `PREVIEW_REGISTRATION_FAILED`
- `PREVIEW_DIMENSION_MISMATCH_UNRESOLVED`

Results are `PASS`, `NEEDS_REVIEW`, or `FAIL`. Canonical export failure is evidence insufficiency, not permission to use a content-fit raster or a synthetic fallback.

## Known Corel limitation

Some legacy documents reject an explicit page-area export, and some company artwork is positioned on the pasteboard outside a blank active page. Visual QA V2 intentionally fails closed for those cases. It does not add a full-page rectangle, mutate the source, export the artwork bounding box, or compare a stretched raster.

## Tests

Hermetic tests cover deterministic unit conversion, portrait and landscape geometry, page-origin mapping, exact-dimension verification, page geometry regression, expected-region union and padding, target-only change, outside-scope change, failure reason codes, and evidence-insufficient classification. CI requires neither CorelDRAW nor private files.
