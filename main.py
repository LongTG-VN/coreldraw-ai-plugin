"""FastAPI server exposing CorelDRAW CMYK automation commands."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.requests import Request

from corel_bridge import CorelDrawBridgeError, corel_bridge
from extended_bridge import extended_bridge

app = FastAPI(
    title="CorelDRAW CMYK AI Plugin Server",
    description=(
        "Local REST API cho phép AI Agent điều khiển CorelDRAW và tạo "
        "vector CMYK chuẩn in ấn."
    ),
    version="1.2.0",
)


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


@app.exception_handler(CorelDrawBridgeError)
async def handle_corel_error(
    _request: Request, exc: CorelDrawBridgeError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"status": "error", "detail": str(exc)},
    )


@app.get("/health")
def health() -> dict[str, object]:
    """Check the HTTP service without launching CorelDRAW."""

    return {
        "status": "ok",
        "service": "coreldraw-ai-plugin",
        "version": app.version,
        "corel_automation_available": corel_bridge.is_available,
    }


@app.post("/api/v1/corel/connect")
def connect_corel() -> dict[str, object]:
    """Verify the COM connection and create a document when none is open."""

    info = corel_bridge.connection_info()
    if not info.get("connected"):
        raise CorelDrawBridgeError(str(info.get("error", "Không thể kết nối.")))
    return {"status": "success", **info}


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)
