"""Template registry and menu rendering orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from corel_bridge import CorelDrawBridge, CorelDrawBridgeError, corel_bridge
from extended_bridge import ExtendedCorelDrawBridge, extended_bridge
from image_providers import (
    ImageGenerationProvider,
    ImageProviderError,
    build_image_provider,
)
from template_models import (
    MenuItem,
    MenuRenderRequest,
    PlaceholderKind,
    TemplateManifest,
)


class TemplateRegistryError(RuntimeError):
    """Raised when a manifest cannot be found or parsed."""


@dataclass(frozen=True)
class RegisteredTemplate:
    manifest: TemplateManifest
    manifest_path: Path

    @property
    def default_cdr_path(self) -> Path:
        return self.manifest.resolve_cdr_path(self.manifest_path)

    def public_info(self) -> dict[str, Any]:
        return {
            **self.manifest.model_dump(),
            "manifest_path": str(self.manifest_path),
            "resolved_cdr_path": str(self.default_cdr_path),
            "template_exists": self.default_cdr_path.is_file(),
        }


class TemplateRegistry:
    def __init__(self, root: str | Path = "templates/manifests") -> None:
        self.root = Path(root).expanduser().resolve()

    def _manifest_files(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        return sorted(self.root.glob("*.json"))

    @staticmethod
    def _load(path: Path) -> RegisteredTemplate:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            manifest = TemplateManifest.model_validate(payload)
        except Exception as exc:
            raise TemplateRegistryError(
                f"Manifest không hợp lệ '{path}': {exc}"
            ) from exc
        return RegisteredTemplate(manifest=manifest, manifest_path=path)

    def list(self) -> list[RegisteredTemplate]:
        return [self._load(path) for path in self._manifest_files()]

    def get(self, template_id: str) -> RegisteredTemplate:
        for registered in self.list():
            if registered.manifest.template_id == template_id:
                return registered
        raise TemplateRegistryError(f"Không tìm thấy template '{template_id}'.")


class TemplateEngine:
    """Render structured business data into editable CorelDRAW templates."""

    def __init__(
        self,
        registry: TemplateRegistry,
        bridge: CorelDrawBridge = corel_bridge,
        advanced_bridge: ExtendedCorelDrawBridge = extended_bridge,
        image_provider: ImageGenerationProvider | None = None,
    ) -> None:
        self.registry = registry
        self.bridge = bridge
        self.advanced_bridge = advanced_bridge
        self.image_provider = image_provider or build_image_provider()

    @staticmethod
    def _fixed_values(request: MenuRenderRequest) -> dict[str, str]:
        return {
            "title": request.title,
            "subtitle": request.subtitle,
            "address": request.address,
            "phone": request.phone,
        }

    @staticmethod
    def _item_value(item: MenuItem, field_name: str) -> str:
        value = getattr(item, field_name, "")
        return "" if value is None else str(value)

    @staticmethod
    def _resolve_template_path(
        registered: RegisteredTemplate, request: MenuRenderRequest
    ) -> Path:
        if request.template_path_override:
            path = Path(request.template_path_override).expanduser().resolve()
        else:
            path = registered.default_cdr_path
        if not path.is_file():
            raise CorelDrawBridgeError(
                "Không tìm thấy file .cdr. Hãy truyền template_path_override hoặc "
                f"đặt file tại: {path}"
            )
        return path

    def _apply_fixed_placeholders(
        self,
        manifest: TemplateManifest,
        request: MenuRenderRequest,
        report: dict[str, Any],
    ) -> None:
        values = self._fixed_values(request)
        for spec in manifest.placeholders:
            value = values.get(spec.key, "")
            if spec.kind == PlaceholderKind.IMAGE:
                report["warnings"].append(
                    f"Fixed image placeholder '{spec.key}' is not mapped by MenuRenderRequest"
                )
                continue
            if spec.required and not value:
                raise CorelDrawBridgeError(
                    f"Thiếu dữ liệu bắt buộc cho placeholder '{spec.key}'."
                )
            try:
                result = self.bridge.set_text_content(
                    spec.shape_name,
                    value,
                    max_length=spec.max_length,
                    min_font_size=spec.min_font_size,
                    max_width=spec.max_width,
                )
                report["text_updates"].append(result)
            except CorelDrawBridgeError as exc:
                if spec.required:
                    raise
                report["warnings"].append(str(exc))

    def _resolve_item_image(
        self,
        item: MenuItem,
        request: MenuRenderRequest,
        generated_dir: Path,
    ) -> Path | None:
        if item.image_path:
            image_path = Path(item.image_path).expanduser().resolve()
            if not image_path.is_file():
                raise CorelDrawBridgeError(f"Ảnh món không tồn tại: {image_path}")
            return image_path
        if request.generate_missing_images and item.image_prompt:
            try:
                return self.image_provider.generate(
                    item.image_prompt,
                    generated_dir,
                    model=request.image_model,
                    aspect_ratio=request.image_aspect_ratio,
                )
            except ImageProviderError as exc:
                raise CorelDrawBridgeError(str(exc)) from exc
        return None

    def _apply_repeater(
        self,
        manifest: TemplateManifest,
        request: MenuRenderRequest,
        output_dir: Path,
        report: dict[str, Any],
    ) -> None:
        items = request.flattened_items()
        generated_dir = output_dir / "generated-images"

        for repeater in manifest.repeaters:
            if len(items) > repeater.max_items:
                raise CorelDrawBridgeError(
                    f"Template chỉ chứa {repeater.max_items} món nhưng dữ liệu có "
                    f"{len(items)} món."
                )

            for offset in range(repeater.max_items):
                index = repeater.start_index + offset
                item = items[offset] if offset < len(items) else None
                for field_name, pattern in repeater.fields.items():
                    shape_name = pattern.format(index=index)
                    if field_name == "image":
                        if item is None:
                            continue
                        image_path = self._resolve_item_image(
                            item, request, generated_dir
                        )
                        if image_path is None:
                            if item.image_prompt:
                                report["pending_image_prompts"].append(
                                    {
                                        "item": item.name,
                                        "slot_shape_name": shape_name,
                                        "prompt": item.image_prompt,
                                    }
                                )
                            continue
                        result = self.bridge.import_image_into_slot(
                            str(image_path),
                            shape_name,
                            imported_shape_name=f"ai_menu_image_{index}",
                            delete_slot=False,
                        )
                        report["image_updates"].append(result)
                        continue

                    value = ""
                    if item is not None:
                        value = self._item_value(item, field_name)
                    elif not repeater.clear_unused:
                        continue

                    try:
                        result = self.bridge.set_text_content(shape_name, value)
                        report["text_updates"].append(result)
                    except CorelDrawBridgeError as exc:
                        if item is None:
                            report["warnings"].append(str(exc))
                        else:
                            raise

    def render_menu(
        self, template_id: str, request: MenuRenderRequest
    ) -> dict[str, Any]:
        registered = self.registry.get(template_id)
        template_path = self._resolve_template_path(registered, request)
        output_dir = Path(request.output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        report: dict[str, Any] = {
            "template_id": template_id,
            "template_path": str(template_path),
            "text_updates": [],
            "image_updates": [],
            "pending_image_prompts": [],
            "warnings": [],
            "outputs": {},
        }

        self.bridge.open_document(str(template_path))
        self._apply_fixed_placeholders(registered.manifest, request, report)
        self._apply_repeater(
            registered.manifest, request, output_dir, report
        )

        cdr_path = self.bridge.save_document(
            str(output_dir / f"{request.file_stem}.cdr")
        )
        report["outputs"]["cdr"] = cdr_path

        if request.export_png:
            report["outputs"]["png"] = self.advanced_bridge.export_document(
                str(output_dir / f"{request.file_stem}-preview.png"),
                "png",
                request.preview_dpi,
            )
        if request.export_pdf:
            report["outputs"]["pdf"] = self.advanced_bridge.export_document(
                str(output_dir / f"{request.file_stem}.pdf"), "pdf"
            )

        report["status"] = (
            "completed_with_pending_images"
            if report["pending_image_prompts"]
            else "completed"
        )
        return report
