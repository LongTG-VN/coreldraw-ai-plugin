"""FastAPI server exposing CorelDRAW template and autonomous-agent commands."""

from __future__ import annotations

import os
from typing import Literal, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.requests import Request

from corel_bridge import CorelDrawBridgeError, corel_bridge
from design_bridge import DesignBridge
from extended_bridge import extended_bridge
from template_engine import TemplateEngine, TemplateRegistry, TemplateRegistryError
from template_models import MenuRenderRequest

app = FastAPI(
    title="CorelDRAW AI Agent Plugin Server",
    description=(
        "Local REST API cho phép Docker UI hoặc AI Agent điều khiển CorelDRAW, "
        "inspect canvas, edit objects, fill template, chèn asset và xuất file sản xuất."
    ),
    version="1.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|null)$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

manifest_dir = os.getenv("COREL_TEMPLATE_MANIFEST_DIR", "templates/manifests")
template_registry = TemplateRegistry(manifest_dir)
template_engine = TemplateEngine(template_registry, corel_bridge, extended_bridge)


class CMYKColor(BaseModel):
    cyan: int = Field(default=0, ge=0, le=100)
    magenta: int = Field(default=0, ge=0, le=100)
    yellow: int = Field(default=0, ge=0, le=100)
    black: int = Field(default=0, ge=0, le=100)

    def as_tuple(self) -> tuple[int, int, int, int]:
        return self.cyan, self.magenta, self.yellow, self.black


class BaseShapeRequest(BaseModel):
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)


class CreateRectangleCMYKRequest(BaseShapeRequest):
    color: CMYKColor = Field(
        default_factory=lambda: CMYKColor(
            cyan=0, magenta=100, yellow=100, black=0
        )
    )


class CreateEllipseCMYKRequest(BaseShapeRequest):
    color: CMYKColor = Field(
        default_factory=lambda: CMYKColor(
            cyan=100, magenta=0, yellow=0, black=0
        )
    )


class CreateTextCMYKRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    x: float
    y: float
    font_name: str = Field(default="Arial", min_length=1, max_length=200)
    font_size: float = Field(default=24.0, gt=0, le=2_000)
    color: CMYKColor = Field(
        default_factory=lambda: CMYKColor(
            cyan=0, magenta=0, yellow=0, black=100
        )
    )
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)


class SetOutlineRequest(BaseModel):
    shape_name: str = Field(min_length=1, max_length=120)
    width: float = Field(gt=0, le=100)
    color: CMYKColor = Field(default_factory=lambda: CMYKColor(black=100))


class GroupShapesRequest(BaseModel):
    shape_names: list[str] = Field(min_length=2, max_length=500)
    group_name: Optional[str] = Field(default=None, min_length=1, max_length=120)


class ExportRequest(BaseModel):
    file_path: str = Field(min_length=1, max_length=4_096)
    format: Literal["pdf", "png"] = "pdf"
    dpi: int = Field(default=300, ge=72, le=1_200)


class SaveDocumentRequest(BaseModel):
    file_path: str = Field(min_length=1, max_length=4_096)


class OpenDocumentRequest(BaseModel):
    file_path: str = Field(min_length=1, max_length=4_096)


class SetTextRequest(BaseModel):
    shape_name: str = Field(min_length=1, max_length=120)
    text: str = Field(max_length=20_000)
    max_length: Optional[int] = Field(default=None, ge=1, le=20_000)
    min_font_size: float = Field(default=10, gt=0, le=500)
    max_width: Optional[float] = Field(default=None, gt=0)


class ImportImageSlotRequest(BaseModel):
    image_path: str = Field(min_length=1, max_length=4_096)
    slot_shape_name: str = Field(min_length=1, max_length=120)
    imported_shape_name: Optional[str] = Field(default=None, max_length=120)
    delete_slot: bool = False


class TransformShapeRequest(BaseModel):
    shape_name: str = Field(min_length=1, max_length=120)
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = Field(default=None, gt=0)
    height: Optional[float] = Field(default=None, gt=0)
    rotation: Optional[float] = Field(default=None, ge=-360_000, le=360_000)


class DuplicateShapeRequest(BaseModel):
    shape_name: str = Field(min_length=1, max_length=120)
    offset_x: float = 0
    offset_y: float = 0
    new_name: Optional[str] = Field(default=None, min_length=1, max_length=120)


class FillShapeRequest(BaseModel):
    shape_name: str = Field(min_length=1, max_length=120)
    color: CMYKColor


class DeleteShapeRequest(BaseModel):
    shape_name: str = Field(min_length=1, max_length=120)


class ImportAssetRequest(BaseModel):
    file_path: str = Field(min_length=1, max_length=4_096)
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = Field(default=None, gt=0)
    height: Optional[float] = Field(default=None, gt=0)


class PreviewRequest(BaseModel):
    file_path: str = Field(
        default="storage/previews/agent-preview.png",
        min_length=1,
        max_length=4_096,
    )
    dpi: int = Field(default=150, ge=72, le=600)


class DesignCheckRequest(BaseModel):
    min_font_size: float = Field(default=6.0, gt=0, le=500)
    require_named_objects: bool = False


class UndoRequest(BaseModel):
    steps: int = Field(default=1, ge=1, le=50)


@app.exception_handler(CorelDrawBridgeError)
async def handle_corel_error(
    _request: Request, exc: CorelDrawBridgeError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"status": "error", "detail": str(exc)},
    )


@app.exception_handler(TemplateRegistryError)
async def handle_template_error(
    _request: Request, exc: TemplateRegistryError
) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"status": "error", "detail": str(exc)},
    )


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "coreldraw-ai-plugin",
        "version": app.version,
        "corel_automation_available": corel_bridge.is_available,
        "image_provider": template_engine.image_provider.status,
    }


@app.post("/api/v1/corel/connect")
def connect_corel() -> dict[str, object]:
    info = corel_bridge.connection_info()
    if not info.get("connected"):
        raise CorelDrawBridgeError(str(info.get("error", "Không thể kết nối.")))
    return {"status": "success", **info}


@app.post("/api/v1/corel/document/open")
def open_document(req: OpenDocumentRequest) -> dict[str, str]:
    return {
        "status": "success",
        "file_path": corel_bridge.open_document(req.file_path),
    }


@app.post("/api/v1/corel/document/save")
def save_document(req: SaveDocumentRequest) -> dict[str, str]:
    return {
        "status": "success",
        "file_path": corel_bridge.save_document(req.file_path),
    }


@app.get("/api/v1/corel/shapes")
def list_shapes() -> dict[str, object]:
    names = corel_bridge.list_shape_names()
    return {"status": "success", "count": len(names), "shape_names": names}


@app.post("/api/v1/corel/text/set")
def set_template_text(req: SetTextRequest) -> dict[str, object]:
    result = corel_bridge.set_text_content(
        req.shape_name,
        req.text,
        max_length=req.max_length,
        min_font_size=req.min_font_size,
        max_width=req.max_width,
    )
    return {"status": "success", **result}


@app.post("/api/v1/corel/image/place-in-slot")
def place_image_in_slot(req: ImportImageSlotRequest) -> dict[str, object]:
    result = corel_bridge.import_image_into_slot(
        req.image_path,
        req.slot_shape_name,
        imported_shape_name=req.imported_shape_name,
        delete_slot=req.delete_slot,
    )
    return {"status": "success", **result}


@app.post("/api/v1/corel/shape/rectangle")
def draw_rectangle(req: CreateRectangleCMYKRequest) -> dict[str, str]:
    shape_name = corel_bridge.create_rectangle_cmyk(
        req.x,
        req.y,
        req.width,
        req.height,
        *req.color.as_tuple(),
        shape_name=req.name,
    )
    return {"status": "success", "shape_name": shape_name}


@app.post("/api/v1/corel/shape/ellipse")
def draw_ellipse(req: CreateEllipseCMYKRequest) -> dict[str, str]:
    shape_name = corel_bridge.create_ellipse_cmyk(
        req.x,
        req.y,
        req.width,
        req.height,
        *req.color.as_tuple(),
        shape_name=req.name,
    )
    return {"status": "success", "shape_name": shape_name}


@app.post("/api/v1/corel/text/artistic")
def draw_artistic_text(req: CreateTextCMYKRequest) -> dict[str, str]:
    shape_name = corel_bridge.create_artistic_text_cmyk(
        req.text,
        req.x,
        req.y,
        req.font_name,
        req.font_size,
        *req.color.as_tuple(),
        shape_name=req.name,
    )
    return {"status": "success", "shape_name": shape_name}


@app.post("/api/v1/corel/shape/outline")
def set_outline(req: SetOutlineRequest) -> dict[str, str]:
    shape_name = extended_bridge.set_shape_outline_cmyk(
        req.shape_name,
        req.width,
        *req.color.as_tuple(),
    )
    return {"status": "success", "shape_name": shape_name}


@app.post("/api/v1/corel/shape/group")
def group_shapes(req: GroupShapesRequest) -> dict[str, str]:
    group_name = extended_bridge.group_shapes_by_names(
        req.shape_names, req.group_name
    )
    return {"status": "success", "shape_name": group_name}


@app.post("/api/v1/corel/export")
def export_document(req: ExportRequest) -> dict[str, str]:
    exported_path = extended_bridge.export_document(
        req.file_path, req.format, req.dpi
    )
    return {
        "status": "success",
        "format": req.format,
        "file_path": exported_path,
    }


# Agent-facing design API ----------------------------------------------------

@app.get("/api/v1/design/snapshot")
def design_snapshot() -> dict[str, object]:
    return {"status": "success", **DesignBridge(corel_bridge).snapshot()}


@app.get("/api/v1/design/objects")
def design_objects() -> dict[str, object]:
    snapshot = DesignBridge(corel_bridge).snapshot()
    return {
        "status": "success",
        "count": snapshot["object_count"],
        "objects": snapshot["objects"],
    }


@app.post("/api/v1/design/object/transform")
def design_transform(req: TransformShapeRequest) -> dict[str, object]:
    result = DesignBridge(corel_bridge).transform_shape(
        req.shape_name,
        x=req.x,
        y=req.y,
        width=req.width,
        height=req.height,
        rotation=req.rotation,
    )
    return {"status": "success", "object": result}


@app.post("/api/v1/design/object/duplicate")
def design_duplicate(req: DuplicateShapeRequest) -> dict[str, object]:
    result = DesignBridge(corel_bridge).duplicate_shape(
        req.shape_name,
        offset_x=req.offset_x,
        offset_y=req.offset_y,
        new_name=req.new_name,
    )
    return {"status": "success", "object": result}


@app.post("/api/v1/design/object/fill")
def design_fill(req: FillShapeRequest) -> dict[str, object]:
    result = DesignBridge(corel_bridge).set_fill_cmyk(
        req.shape_name, *req.color.as_tuple()
    )
    return {"status": "success", "object": result}


@app.post("/api/v1/design/object/delete")
def design_delete(req: DeleteShapeRequest) -> dict[str, object]:
    result = DesignBridge(corel_bridge).delete_shape(req.shape_name)
    return {"status": "success", **result}


@app.post("/api/v1/design/asset/import")
def design_import_asset(req: ImportAssetRequest) -> dict[str, object]:
    result = DesignBridge(corel_bridge).import_asset(
        req.file_path,
        name=req.name,
        x=req.x,
        y=req.y,
        width=req.width,
        height=req.height,
    )
    return {"status": "success", "object": result}


@app.post("/api/v1/design/render-preview")
def design_render_preview(req: PreviewRequest) -> dict[str, object]:
    path = extended_bridge.export_document(req.file_path, "png", req.dpi)
    return {
        "status": "success",
        "format": "png",
        "file_path": path,
        "dpi": req.dpi,
    }


@app.post("/api/v1/design/check")
def design_check(req: DesignCheckRequest) -> dict[str, object]:
    return DesignBridge(corel_bridge).check_design(
        min_font_size=req.min_font_size,
        require_named_objects=req.require_named_objects,
    )


@app.post("/api/v1/design/undo")
def design_undo(req: UndoRequest) -> dict[str, object]:
    return {"status": "success", **DesignBridge(corel_bridge).undo(req.steps)}


@app.get("/api/v1/templates")
def list_templates() -> dict[str, object]:
    templates = [registered.public_info() for registered in template_registry.list()]
    return {"status": "success", "count": len(templates), "templates": templates}


@app.get("/api/v1/templates/{template_id}")
def get_template(template_id: str) -> dict[str, object]:
    return {"status": "success", **template_registry.get(template_id).public_info()}


@app.post("/api/v1/templates/{template_id}/render-menu")
def render_menu(
    template_id: str, request: MenuRenderRequest
) -> dict[str, object]:
    return template_engine.render_menu(template_id, request)


@app.get("/api/v1/image-provider/status")
def image_provider_status() -> dict[str, object]:
    return {"status": "success", **template_engine.image_provider.status}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)
