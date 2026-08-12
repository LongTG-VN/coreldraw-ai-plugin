"""Advanced CorelDRAW operations: outline, grouping, and export."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Literal, Optional

from corel_bridge import CorelDrawBridge, CorelDrawBridgeError, corel_bridge

ExportFormat = Literal["pdf", "png"]

CDR_PNG = 802
CDR_CURRENT_PAGE = 1
CDR_RGB_COLOR_IMAGE = 4


class ExtendedCorelDrawBridge:
    def __init__(self, bridge: CorelDrawBridge = corel_bridge) -> None:
        self.bridge = bridge

    def set_shape_outline_cmyk(
        self,
        shape_name: str,
        width: float,
        c: int,
        m: int,
        y: int,
        k: int,
    ) -> str:
        with self.bridge.session() as (app, doc):
            shape = self.bridge._find_shape_in_document(doc, shape_name)
            shape.Outline.Width = width
            shape.Outline.Color = self.bridge._create_cmyk_color(app, c, m, y, k)
            return str(shape.Name)

    def group_shapes_by_names(
        self, shape_names: Iterable[str], group_name: Optional[str] = None
    ) -> str:
        names = list(dict.fromkeys(shape_names))
        if len(names) < 2:
            raise CorelDrawBridgeError("Cần ít nhất 2 shape để tạo group.")

        with self.bridge.session() as (app, doc):
            shapes_range = app.CreateShapeRange()
            missing: list[str] = []
            for name in names:
                try:
                    shapes_range.Add(
                        self.bridge._find_shape_in_document(doc, name)
                    )
                except CorelDrawBridgeError:
                    missing.append(name)
            if missing:
                raise CorelDrawBridgeError(
                    "Không tìm thấy shape: " + ", ".join(missing)
                )
            grouped_shape = shapes_range.Group()
            return self.bridge._assign_shape_name(
                grouped_shape, group_name, "group"
            )

    @staticmethod
    def _prepare_export_path(file_path: str, export_format: ExportFormat) -> Path:
        path = Path(file_path).expanduser()
        expected_suffix = f".{export_format}"
        if path.suffix.lower() != expected_suffix:
            path = path.with_suffix(expected_suffix)
        if not path.is_absolute():
            path = Path.cwd() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    def export_document(
        self,
        file_path: str,
        export_format: ExportFormat = "pdf",
        dpi: int = 300,
    ) -> str:
        path = self._prepare_export_path(file_path, export_format)

        with self.bridge.session() as (app, doc):
            if export_format == "pdf":
                doc.PublishToPDF(str(path))
            elif export_format == "png":
                options = app.CreateStructExportOptions()
                palette_options = app.CreateStructPaletteOptions()
                options.ImageType = CDR_RGB_COLOR_IMAGE
                options.Overwrite = True
                options.ResolutionX = dpi
                options.ResolutionY = dpi
                export_filter = doc.ExportEx(
                    str(path),
                    CDR_PNG,
                    CDR_CURRENT_PAGE,
                    options,
                    palette_options,
                )
                export_filter.Finish()
            else:
                raise CorelDrawBridgeError(
                    f"Định dạng export không được hỗ trợ: {export_format}"
                )

        return str(path)

    def export_to_pdf(self, file_path: str) -> bool:
        self.export_document(file_path, "pdf")
        return True


extended_bridge = ExtendedCorelDrawBridge()


if __name__ == "__main__":
    print("Extended CorelDRAW Bridge loaded.")
