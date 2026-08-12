"""Build the small, local v0.3 structural reference corpus.

The corpus intentionally combines the existing research-only GenPoster smoke
documents with project-owned generic structural templates. Because a mixed
index contains CC-BY-NC material, the corpus manifest remains research-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.inference.preview import render_preview
from training.retrieval.features import extract_reference_features, summarize_reference
from training.retrieval.models import ReferenceMetadataV1, ReferenceRecordV1
from training.schemas.design import (
    BoundingBox,
    CanvasSpec,
    ColorSpec,
    DesignDocument,
    DesignElement,
    SourceSpec,
    TextSpec,
    VisualSpec,
    normalize_bbox,
)


CATEGORY_FORMATS = {
    "spa": "poster",
    "nail": "poster",
    "salon": "poster",
    "cafe": "poster",
    "tra_sua": "social_post",
    "nha_hang": "menu",
    "my_pham": "poster",
    "poster_sale": "poster",
    "khai_truong": "poster",
    "menu": "menu",
    "card_visit": "business_card",
    "bang_hieu": "signage",
    "banner_social": "banner",
}

CATEGORY_STYLES = {
    "spa": ["luxury", "minimal"],
    "nail": ["youthful"],
    "salon": ["modern"],
    "cafe": ["vintage"],
    "tra_sua": ["youthful"],
    "nha_hang": ["elegant"],
    "poster_sale": ["bold"],
    "khai_truong": ["festive"],
    "my_pham": ["minimal"],
    "bang_hieu": ["bold"],
    "card_visit": ["minimal"],
    "banner_social": ["modern"],
    "menu": ["editorial"],
}

TEMPLATE_VARIANTS = (
    ("centered", ["minimal", "balanced"], ["cream", "gold"]),
    ("split", ["modern", "asymmetric"], ["green", "cream"]),
    ("grid", ["editorial", "structured"], ["red", "white"]),
    ("hero_left", ["bold", "dynamic"], ["blue", "purple"]),
    ("hero_right", ["luxury", "clean"], ["black", "gold"]),
)

PALETTE_HEX = {
    "cream": "#F4EBD9",
    "gold": "#C5A34E",
    "green": "#436B4F",
    "red": "#B7352D",
    "white": "#FFFFFF",
    "blue": "#274C77",
    "purple": "#6A4C93",
    "black": "#161616",
}


def _bbox(canvas: CanvasSpec, x: float, y: float, width: float, height: float) -> BoundingBox:
    return BoundingBox(
        x=float(canvas.width) * x,
        y=float(canvas.height) * y,
        width=float(canvas.width) * width,
        height=float(canvas.height) * height,
    )


def _text_element(
    canvas: CanvasSpec,
    *,
    element_id: str,
    content: str,
    x: float,
    y: float,
    width: float,
    height: float,
    size_ratio: float,
    alignment: str,
    z_index: int,
) -> DesignElement:
    bbox = _bbox(canvas, x, y, width, height)
    return DesignElement(
        id=element_id,
        name=element_id.replace("_", " ").title(),
        type="text",
        bbox=bbox,
        bbox_norm=normalize_bbox(bbox, canvas),
        z_index=z_index,
        layer="typography",
        text=TextSpec(
            content=content,
            font_family="Arial",
            font_size=float(min(canvas.width, canvas.height)) * size_ratio,
            font_weight=700 if element_id in {"headline", "price"} else 400,
            alignment=alignment,  # type: ignore[arg-type]
            line_height=1.15,
        ),
        visual=VisualSpec(fill=ColorSpec(model="hex", values=["#202020"])),
        metadata={"structural_placeholder": True},
    )


def _shape_element(
    canvas: CanvasSpec,
    *,
    element_id: str,
    x: float,
    y: float,
    width: float,
    height: float,
    color: str,
    z_index: int,
) -> DesignElement:
    bbox = _bbox(canvas, x, y, width, height)
    return DesignElement(
        id=element_id,
        name=element_id.replace("_", " ").title(),
        type="rectangle",
        bbox=bbox,
        bbox_norm=normalize_bbox(bbox, canvas),
        z_index=z_index,
        layer="visual",
        visual=VisualSpec(fill=ColorSpec(model="hex", values=[color])),
        metadata={"structural_placeholder": True},
    )


def _template_geometry(variant: str) -> dict[str, tuple[float, float, float, float]]:
    if variant == "centered":
        return {
            "headline": (0.12, 0.09, 0.76, 0.15),
            "subtitle": (0.18, 0.27, 0.64, 0.08),
            "hero": (0.20, 0.39, 0.60, 0.34),
            "body": (0.18, 0.77, 0.64, 0.08),
            "cta": (0.32, 0.88, 0.36, 0.07),
        }
    if variant == "split":
        return {
            "headline": (0.07, 0.10, 0.40, 0.20),
            "subtitle": (0.07, 0.34, 0.36, 0.10),
            "hero": (0.54, 0.08, 0.39, 0.73),
            "body": (0.07, 0.50, 0.38, 0.18),
            "cta": (0.07, 0.76, 0.30, 0.09),
        }
    if variant == "grid":
        return {
            "headline": (0.07, 0.06, 0.86, 0.12),
            "subtitle": (0.07, 0.20, 0.86, 0.06),
            "hero": (0.07, 0.31, 0.40, 0.29),
            "body": (0.53, 0.31, 0.40, 0.45),
            "cta": (0.53, 0.82, 0.26, 0.08),
        }
    hero_left = variant == "hero_left"
    hero_x, text_x = (0.05, 0.53) if hero_left else (0.56, 0.07)
    return {
        "headline": (text_x, 0.12, 0.38, 0.19),
        "subtitle": (text_x, 0.35, 0.36, 0.08),
        "hero": (hero_x, 0.08, 0.39, 0.76),
        "body": (text_x, 0.49, 0.36, 0.17),
        "cta": (text_x, 0.74, 0.28, 0.09),
    }


def _generic_document(category: str, variant: str, colors: list[str]) -> DesignDocument:
    format_name = CATEGORY_FORMATS[category]
    if format_name == "business_card":
        width, height = 900.0, 540.0
    elif format_name in {"signage", "banner"}:
        width, height = 1200.0, 500.0
    elif format_name == "social_post":
        width, height = 1080.0, 1080.0
    else:
        width, height = 1000.0, 1414.0
    canvas = CanvasSpec(
        width=width,
        height=height,
        unit="px",
        background=VisualSpec(fill=ColorSpec(model="hex", values=[PALETTE_HEX[colors[0]]])),
    )
    geometry = _template_geometry(variant)
    background = _shape_element(
        canvas,
        element_id="background",
        x=0,
        y=0,
        width=1,
        height=1,
        color=PALETTE_HEX[colors[0]],
        z_index=0,
    )
    hero = _shape_element(
        canvas,
        element_id="hero_placeholder",
        x=geometry["hero"][0],
        y=geometry["hero"][1],
        width=geometry["hero"][2],
        height=geometry["hero"][3],
        color=PALETTE_HEX[colors[1]],
        z_index=1,
    )
    alignment = "center" if variant == "centered" else "left"
    text_values = {
        "headline": ("PRIMARY MESSAGE", 0.075),
        "subtitle": ("Supporting message", 0.032),
        "body": ("Structured content block with reusable spacing", 0.022),
        "cta": ("ACTION", 0.028),
    }
    elements = [background, hero]
    for index, (role, (content, size)) in enumerate(text_values.items(), start=2):
        x, y, box_width, box_height = geometry[role]
        elements.append(
            _text_element(
                canvas,
                element_id=role,
                content=content,
                x=x,
                y=y,
                width=box_width,
                height=box_height,
                size_ratio=size,
                alignment=alignment,
                z_index=index,
            )
        )
    return DesignDocument(
        sample_id=f"structural-template:{category}:{variant}",
        source=SourceSpec(
            name="synthetic_owned",
            split="reference_templates",
            license_class="production_safe",
            upstream_id=f"{category}:{variant}",
            commercial_allowed=True,
        ),
        canvas=canvas,
        category=category,
        elements=elements,
        assets=[],
        metadata={
            "license": "project_owned",
            "format": format_name,
            "template_variant": variant,
            "no_benchmark_text_or_assets": True,
        },
    )


def _iter_documents(source_dir: Path, limit: int) -> Iterable[DesignDocument]:
    count = 0
    for split in ("train", "validation", "test"):
        path = source_dir / f"{split}.jsonl"
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                yield DesignDocument.model_validate_json(line)
                count += 1
                if count >= limit:
                    return


def _safe_id(value: str) -> str:
    return value.replace(":", "_").replace("/", "_")


def _record_for_document(
    document: DesignDocument,
    *,
    reference_id: str,
    category: str,
    format_name: str,
    style_tags: list[str],
    color_tags: list[str],
    document_path: str,
    preview_path: str,
) -> ReferenceRecordV1:
    features = extract_reference_features(document)
    research_only = not document.source.commercial_allowed
    metadata = ReferenceMetadataV1(
        reference_id=reference_id,
        category=category,
        format=format_name,
        aspect_ratio=float(features.aspect_ratio),
        style_tags=style_tags,
        color_tags=color_tags,
        text_density=features.text_density,
        element_count=features.element_count,
        layout_features={
            "composition": features.composition,
            "alignment": features.dominant_alignment,
            "whitespace": features.whitespace,
            "vertical_rhythm": features.vertical_rhythm,
        },
        design_document_path=document_path,
        preview_path=preview_path,
        source=document.source.name,
        license=str(document.metadata.get("license") or document.source.license_class),
        license_class=document.source.license_class,
        research_only=research_only,
        commercial_allowed=document.source.commercial_allowed,
        provenance={
            "sample_id": document.sample_id,
            "upstream_id": document.source.upstream_id,
            "transform": "DesignDocument -> deterministic structural features v1",
        },
    )
    return ReferenceRecordV1(
        metadata=metadata,
        features=features,
        summary=summarize_reference(metadata, features),
    )


def build_reference_corpus(
    source_dir: Path,
    output_dir: Path,
    *,
    genposter_limit: int = 100,
) -> dict[str, object]:
    if not 1 <= genposter_limit <= 500:
        raise ValueError("genposter_limit must be within [1, 500]")
    output_dir = output_dir.resolve()
    documents_dir = output_dir / "documents"
    previews_dir = output_dir / "previews"
    documents_dir.mkdir(parents=True, exist_ok=True)
    previews_dir.mkdir(parents=True, exist_ok=True)

    records: list[ReferenceRecordV1] = []
    source_documents = list(_iter_documents(source_dir.resolve(), genposter_limit))
    if not source_documents:
        raise ValueError(f"no DesignDocument rows found under {source_dir}")
    for index, document in enumerate(source_documents, start=1):
        reference_id = f"genposter:{index:04d}"
        stem = _safe_id(reference_id)
        document_relpath = f"documents/{stem}.json"
        preview_relpath = f"previews/{stem}.png"
        (output_dir / document_relpath).write_text(
            document.model_dump_json(indent=2, exclude_none=True) + "\n",
            encoding="utf-8",
        )
        render_preview(document, output_dir / preview_relpath, max_dimension=720)
        features = extract_reference_features(document)
        inferred_style = [
            "editorial" if features.text_density == "high" else "minimal",
            features.composition,
        ]
        records.append(
            _record_for_document(
                document,
                reference_id=reference_id,
                category="poster",
                format_name="poster",
                style_tags=inferred_style,
                color_tags=features.dominant_colors[:8],
                document_path=document_relpath,
                preview_path=preview_relpath,
            )
        )

    for category, format_name in CATEGORY_FORMATS.items():
        for variant, styles, colors in TEMPLATE_VARIANTS:
            document = _generic_document(category, variant, list(colors))
            reference_id = f"template:{category}:{variant}"
            stem = _safe_id(reference_id)
            document_relpath = f"documents/{stem}.json"
            preview_relpath = f"previews/{stem}.png"
            (output_dir / document_relpath).write_text(
                document.model_dump_json(indent=2, exclude_none=True) + "\n",
                encoding="utf-8",
            )
            render_preview(document, output_dir / preview_relpath, max_dimension=720)
            records.append(
                _record_for_document(
                    document,
                    reference_id=reference_id,
                    category=category,
                    format_name=format_name,
                    style_tags=list(dict.fromkeys([*CATEGORY_STYLES[category], *styles])),
                    color_tags=list(colors),
                    document_path=document_relpath,
                    preview_path=preview_relpath,
                )
            )

    index_path = output_dir / "reference_index.jsonl"
    with index_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in sorted(records, key=lambda item: item.metadata.reference_id):
            handle.write(record.model_dump_json(exclude_none=True) + "\n")
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reference_count": len(records),
        "source_counts": {
            "genposter100k": len(source_documents),
            "project_owned_structural_templates": len(records) - len(source_documents),
        },
        "sources": [
            {
                "name": "genposter100k",
                "license": "CC-BY-NC-4.0",
                "license_class": "research_only",
                "commercial_allowed": False,
            },
            {
                "name": "project_owned_structural_templates",
                "license": "project_owned",
                "license_class": "production_safe",
                "commercial_allowed": True,
                "contains_benchmark_text_or_assets": False,
            },
        ],
        "license_class": "research_only_mixed_corpus",
        "research_only": True,
        "commercial_allowed": False,
        "index": index_path.name,
        "notes": "The mixed index inherits the most restrictive source license.",
    }
    (output_dir / "corpus_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path("training/data/research/genposter_smoke_100"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("training/artifacts/reference_corpora/design_v0_3"),
    )
    parser.add_argument("--genposter-limit", type=int, default=100)
    return parser


def main() -> int:
    args = _parser().parse_args()
    manifest = build_reference_corpus(
        args.source_dir,
        args.output_dir,
        genposter_limit=args.genposter_limit,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
