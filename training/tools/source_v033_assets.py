"""Verify, download, and normalize the licensed v0.3.3 asset benchmark."""

from __future__ import annotations

import argparse
import html
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from training.visual.asset_contracts import (
    AssetInputV1,
    AssetManifestV1,
    inspect_asset_file,
    sha256_file,
    validate_asset_manifest,
)


USER_AGENT = "CorelDrawDesignAI-Research/0.3.3 (licensed asset benchmark)"
LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
CASE_CONTENT: dict[str, dict[str, Any]] = {
    "spa": {
        "source_prompt_id": "spa_luxury",
        "headline": "SPA AN NHIÊN",
        "subheadline": "Chăm sóc da chuyên sâu",
        "body": "Không gian thư giãn và chăm sóc da",
        "cta": "Đặt lịch hôm nay",
        "benchmark_sample_data": False,
        "logo": {"text": "SPA AN NHIÊN", "mark": "lotus", "colors": ["#3D2B24", "#C49A52"]},
    },
    "cafe": {
        "source_prompt_id": "cafe_vintage",
        "headline": "MỘC CAFE",
        "subheadline": "Cà phê mỗi ngày",
        "body": "Không gian nhỏ, vị cà phê thật",
        "cta": "Ghé quán hôm nay",
        "benchmark_sample_data": False,
        "logo": {"text": "MỘC CAFE", "mark": "bean", "colors": ["#39231B", "#C67C3B"]},
    },
    "sale": {
        "source_prompt_id": "sale_bold",
        "headline": "MEGA SALE",
        "offer": "GIẢM 30%",
        "cta": "MUA NGAY",
        "benchmark_sample_data": True,
        "customer_provided": False,
        "logo": {"text": "NOVA MARKET", "mark": "spark", "colors": ["#6E1020", "#F5C542"]},
    },
    "menu": {
        "source_prompt_id": "dense_food_menu",
        "headline": "BẾP NHÀ",
        "subheadline": "Món Việt mỗi ngày",
        "cta": "Đặt món tại quầy",
        "items": [
            {"name": "Cơm gà nướng", "description": "Gà nướng, rau và cơm", "price": "45K"},
            {"name": "Cơm bò xào", "description": "Bò xào rau củ", "price": "55K"},
            {"name": "Cơm sườn", "description": "Sườn nướng và cơm", "price": "49K"},
            {"name": "Mì xào bò", "description": "Mì, bò và rau", "price": "50K"},
            {"name": "Gà sốt cay", "description": "Gà sốt và rau", "price": "52K"},
        ],
        "benchmark_sample_data": True,
        "customer_provided": False,
        "logo": {"text": "BẾP NHÀ", "mark": "bowl", "colors": ["#12352D", "#D8A84E"]},
    },
    "signage": {
        "source_prompt_id": "signage_wide",
        "headline": "PHỞ GIA TRUYỀN",
        "subheadline": "Hương vị Việt",
        "benchmark_sample_data": False,
        "logo": {"text": "PHỞ GIA TRUYỀN", "mark": "bowl", "colors": ["#F7F2E8", "#F2C14E"]},
    },
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _request_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def _download(url: str, destination: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(4):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                destination.write_bytes(response.read())
            return
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 429 or attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(f"asset download failed: {url}") from last_error


def _commons_info(title: str) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": 1600,
            "titles": title,
        }
    )
    payload = _request_json(f"https://commons.wikimedia.org/w/api.php?{query}")
    page = next(iter(payload["query"]["pages"].values()))
    if "imageinfo" not in page:
        raise RuntimeError(f"Commons file not found: {title}")
    return page["imageinfo"][0]


def _license_value(info: dict[str, Any], field: str) -> str:
    value = info.get("extmetadata", {}).get(field, {}).get("value")
    return str(value or "").strip()


def _font(size: int, *, serif: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        ["arialbd.ttf", "DejaVuSerif-Bold.ttf", "DejaVuSerif.ttf"]
        if serif
        else ["arialbd.ttf", "DejaVuSansCondensed-Bold.ttf", "DejaVuSans-Bold.ttf"]
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _project_logo(case_id: str, destination: Path, preview: Path) -> AssetInputV1:
    spec = CASE_CONTENT[case_id]["logo"]
    primary, accent = spec["colors"]
    text = str(spec["text"])
    width, height = 1200, 300
    safe_text = html.escape(text)
    mark = str(spec["mark"])
    if mark == "bean":
        mark_svg = f'<ellipse cx="115" cy="150" rx="62" ry="90" fill="none" stroke="{accent}" stroke-width="18" transform="rotate(28 115 150)"/><path d="M78 214 Q118 150 150 82" fill="none" stroke="{accent}" stroke-width="13"/>'
    elif mark == "bowl":
        mark_svg = f'<path d="M38 126 H194 Q180 230 116 230 Q52 230 38 126 Z" fill="none" stroke="{accent}" stroke-width="16"/><path d="M66 93 Q82 54 98 93 M122 93 Q138 54 154 93" fill="none" stroke="{accent}" stroke-width="12"/>'
    elif mark == "spark":
        mark_svg = f'<path d="M116 32 L138 112 L218 134 L138 156 L116 236 L94 156 L14 134 L94 112 Z" fill="{accent}"/>'
    else:
        mark_svg = f'<path d="M116 226 C38 188 42 102 116 64 C190 102 194 188 116 226 Z M116 200 C92 164 92 118 116 84 C140 118 140 164 116 200 Z" fill="none" stroke="{accent}" stroke-width="13"/>'
    destination.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'{mark_svg}<text x="250" y="188" font-family="DejaVu Sans" font-size="96" font-weight="700" fill="{primary}" letter-spacing="3">{safe_text}</text>'
        "</svg>\n",
        encoding="utf-8",
    )
    image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    accent_rgb = tuple(int(accent[index : index + 2], 16) for index in (1, 3, 5))
    primary_rgb = tuple(int(primary[index : index + 2], 16) for index in (1, 3, 5))
    draw.ellipse((42, 55, 196, 245), outline=accent_rgb, width=14)
    draw.line((116, 62, 116, 238), fill=accent_rgb, width=9)
    draw.text((250, 72), text, font=_font(118, serif=case_id == "spa"), fill=primary_rgb)
    image.save(preview, format="PNG", optimize=True)
    mime, actual_width, actual_height, has_alpha = inspect_asset_file(destination)
    return AssetInputV1(
        asset_id=f"{case_id}_logo_01",
        role="logo",
        path=destination.name,
        preview_path=preview.name,
        mime_type=mime,
        sha256=sha256_file(destination),
        width_px=actual_width,
        height_px=actual_height,
        aspect_ratio=actual_width / actual_height,
        has_alpha=has_alpha,
        source_type="project_owned",
        source_url=None,
        source_original_url=None,
        source_page=None,
        license_name="Project-owned original benchmark asset",
        license_url=None,
        commercial_allowed=True,
        modification_allowed=True,
        research_only=False,
        benchmark_only=True,
        project_owned=True,
        fit_mode="contain",
        palette_hint=[primary, accent],
    )


def _project_product(destination: Path, preview: Path) -> AssetInputV1:
    width, height = 600, 900
    destination.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        '<defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#7B3760"/><stop offset="1" stop-color="#D77A86"/></linearGradient></defs>'
        '<rect x="205" y="55" width="190" height="95" rx="24" fill="#2A2430"/>'
        '<rect x="145" y="135" width="310" height="650" rx="78" fill="url(#g)"/>'
        '<rect x="175" y="225" width="250" height="310" rx="26" fill="#FFF5EE" opacity="0.92"/>'
        '<circle cx="300" cy="330" r="58" fill="none" stroke="#F5C542" stroke-width="14"/>'
        '<path d="M265 330 L300 280 L335 330 L300 380 Z" fill="#F5C542"/>'
        '<text x="300" y="455" text-anchor="middle" font-family="DejaVu Sans" font-size="42" font-weight="700" fill="#6E1020">NOVA</text>'
        '<text x="300" y="505" text-anchor="middle" font-family="DejaVu Sans" font-size="24" fill="#6E1020">BENCHMARK PRODUCT</text>'
        '<ellipse cx="300" cy="810" rx="190" ry="34" fill="#381E2B" opacity="0.18"/>'
        "</svg>\n",
        encoding="utf-8",
    )
    image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((145, 135, 455, 785), radius=78, fill="#A94D73")
    draw.rounded_rectangle((205, 55, 395, 150), radius=24, fill="#2A2430")
    draw.rounded_rectangle((175, 225, 425, 535), radius=26, fill="#FFF5EE")
    draw.ellipse((242, 272, 358, 388), outline="#F5C542", width=14)
    draw.text((240, 410), "NOVA", font=_font(44), fill="#6E1020")
    image.save(preview, format="PNG", optimize=True)
    mime, actual_width, actual_height, has_alpha = inspect_asset_file(destination)
    return AssetInputV1(
        asset_id="sale_product_01",
        role="product",
        path=destination.name,
        preview_path=preview.name,
        mime_type=mime,
        sha256=sha256_file(destination),
        width_px=actual_width,
        height_px=actual_height,
        aspect_ratio=actual_width / actual_height,
        has_alpha=has_alpha,
        source_type="project_owned",
        license_name="Project-owned original benchmark asset",
        commercial_allowed=True,
        modification_allowed=True,
        research_only=False,
        benchmark_only=True,
        project_owned=True,
        fit_mode="contain",
        palette_hint=["#6E1020", "#A94D73", "#F5C542"],
    )
def _public_asset(case_id: str, spec: dict[str, Any], case_dir: Path) -> AssetInputV1:
    existing_manifest = case_dir / "asset_manifest.json"
    if existing_manifest.is_file():
        payload = _read_json(existing_manifest)
        for item in payload.get("assets", []):
            if (
                item.get("asset_id") == spec["asset_id"]
                and item.get("source_page") == spec["source_page"]
            ):
                existing = AssetInputV1.model_validate(item)
                existing_path = case_dir / existing.path
                if existing_path.is_file() and sha256_file(existing_path) == existing.sha256:
                    mime, width, height, has_alpha = inspect_asset_file(existing_path)
                    return AssetInputV1.model_validate(
                        {
                            **existing.model_dump(mode="json"),
                            "mime_type": mime,
                            "width_px": width,
                            "height_px": height,
                            "aspect_ratio": width / height,
                            "has_alpha": has_alpha,
                        }
                    )
    info = _commons_info(str(spec["commons_title"]))
    license_short = _license_value(info, "LicenseShortName").casefold()
    license_url = _license_value(info, "LicenseUrl").replace("http://", "https://")
    if license_short != "cc0" or "creativecommons.org/publicdomain/zero/1.0" not in license_url:
        raise RuntimeError(f"license gate failed for {spec['commons_title']}: {license_short} {license_url}")
    suffix = ".png" if info["mime"] == "image/png" else ".jpg"
    destination = case_dir / f"{spec['role']}{suffix}"
    # Commons asks automated clients to use listed thumbnail sizes rather than
    # repeatedly fetching multi-megabyte originals. Keep the original URL in
    # provenance and use the deterministic 960px derivative as local input.
    download_url = str(info.get("thumburl") or info["url"]).replace(
        "/1920px-", "/960px-"
    )
    _download(download_url, destination)
    mime, width, height, has_alpha = inspect_asset_file(destination)
    return AssetInputV1(
        asset_id=str(spec["asset_id"]),
        role=str(spec["role"]),
        path=destination.name,
        mime_type=mime,
        sha256=sha256_file(destination),
        width_px=width,
        height_px=height,
        aspect_ratio=width / height,
        has_alpha=has_alpha,
        source_type="public_asset",
        source_url=download_url,
        source_original_url=str(info["url"]),
        source_page=str(spec["source_page"]),
        license_name="CC0 1.0",
        license_url=LICENSE_URL,
        commercial_allowed=True,
        modification_allowed=True,
        research_only=False,
        benchmark_only=True,
        project_owned=False,
        downloaded_at=datetime.now(timezone.utc).isoformat(),
        fit_mode=str(spec["fit_mode"]),
        focal_x=float(spec["focal_x"]),
        focal_y=float(spec["focal_y"]),
    )


def source_assets(*, config_path: Path, output_root: Path) -> dict[str, Any]:
    config = _read_json(config_path.resolve())
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {"cases": {}, "license_gate": "CC0_or_project_owned"}
    public_specs = config["public_assets"]
    for case_id, content in CASE_CONTENT.items():
        case_dir = output_root / case_id
        case_dir.mkdir(exist_ok=True)
        assets: list[AssetInputV1] = []
        if case_id in public_specs:
            assets.append(_public_asset(case_id, public_specs[case_id], case_dir))
        elif case_id == "sale":
            assets.append(_project_product(case_dir / "product.svg", case_dir / "product.png"))
        assets.append(_project_logo(case_id, case_dir / "logo.svg", case_dir / "logo.png"))
        manifest = AssetManifestV1(
            case_id=case_id,
            benchmark_sample_data=bool(content["benchmark_sample_data"]),
            customer_provided=False,
            assets=assets,
        )
        validate_asset_manifest(manifest, base_dir=case_dir)
        case_payload = {
            **{key: value for key, value in content.items() if key != "logo"},
            "case_id": case_id,
            "benchmark_name": "design_ai_v0.3.3_real_assets",
            "customer_provided": False,
            "project_owned_copy": True,
        }
        _write_json(case_dir / "case.json", case_payload)
        _write_json(case_dir / "asset_manifest.json", manifest.model_dump(mode="json"))
        source_lines = [f"# Sources — {case_id}", "", "All assets are benchmark-only local inputs.", ""]
        for asset in assets:
            source_lines.extend(
                [
                    f"## {asset.asset_id}",
                    "",
                    f"- Role: `{asset.role}`",
                    f"- Source type: `{asset.source_type}`",
                    f"- Source page: {asset.source_page or 'project-owned; no external page'}",
                    f"- License: {asset.license_name}",
                    f"- License URL: {asset.license_url or 'not applicable'}",
                    f"- Commercial allowed: `{str(asset.commercial_allowed).lower()}`",
                    f"- Modification allowed: `{str(asset.modification_allowed).lower()}`",
                    f"- SHA-256: `{asset.sha256}`",
                    "",
                ]
            )
        (case_dir / "SOURCES.md").write_text("\n".join(source_lines), encoding="utf-8")
        summary["cases"][case_id] = {
            "asset_count": len(assets),
            "commercial_asset_count": sum(asset.commercial_allowed for asset in assets),
            "manifest": str(case_dir / "asset_manifest.json"),
        }
    _write_json(output_root / "source_summary.json", summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("training/config/assets/v033_sources.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("training/data/local_real_asset_benchmark/v033"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    print(json.dumps(source_assets(config_path=args.config, output_root=args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
