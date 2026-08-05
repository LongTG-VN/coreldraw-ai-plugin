"""
FastAPI Server phục vụ các Endpoint thiết kế CorelDRAW màu CMYK cho AI Agent / Codex.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from corel_bridge import corel_bridge

app = FastAPI(
    title="CorelDRAW CMYK AI Plugin Server",
    description="REST API cho phép AI Agent điều khiển CorelDRAW thiết kế Vector CMYK chuẩn in ấn",
    version="1.1.0"
)

class CMYKColor(BaseModel):
    cyan: int = Field(default=0, ge=0, le=100)
    magenta: int = Field(default=0, ge=0, le=100)
    yellow: int = Field(default=0, ge=0, le=100)
    black: int = Field(default=0, ge=0, le=100)

class CreateRectangleCMYKRequest(BaseModel):
    x: float
    y: float
    width: float
    height: float
    color: Optional[CMYKColor] = Field(default_factory=lambda: CMYKColor(cyan=0, magenta=100, yellow=100, black=0))

class CreateEllipseCMYKRequest(BaseModel):
    x: float
    y: float
    width: float
    height: float
    color: Optional[CMYKColor] = Field(default_factory=lambda: CMYKColor(cyan=100, magenta=0, yellow=0, black=0))

class CreateTextCMYKRequest(BaseModel):
    text: str
    x: float
    y: float
    font_name: Optional[str] = "Arial"
    font_size: Optional[float] = 24.0
    color: Optional[CMYKColor] = Field(default_factory=lambda: CMYKColor(cyan=0, magenta=0, yellow=0, black=100))

@app.post("/api/v1/corel/shape/rectangle")
def draw_rectangle(req: CreateRectangleCMYKRequest):
    """Tạo hình chữ nhật / khung bảng hiệu CMYK."""
    c = req.color.cyan
    m = req.color.magenta
    y = req.color.yellow
    k = req.color.black
    shape_name = corel_bridge.create_rectangle_cmyk(req.x, req.y, req.width, req.height, c, m, y, k)
    if not shape_name:
        raise HTTPException(status_code=500, detail="Không thể tạo đối tượng Rectangle CMYK.")
    return {"status": "success", "shape_name": shape_name}

@app.post("/api/v1/corel/shape/ellipse")
def draw_ellipse(req: CreateEllipseCMYKRequest):
    """Tạo hình elip CMYK."""
    c = req.color.cyan
    m = req.color.magenta
    y = req.color.yellow
    k = req.color.black
    shape_name = corel_bridge.create_ellipse_cmyk(req.x, req.y, req.width, req.height, c, m, y, k)
    if not shape_name:
        raise HTTPException(status_code=500, detail="Không thể tạo đối tượng Ellipse CMYK.")
    return {"status": "success", "shape_name": shape_name}

@app.post("/api/v1/corel/text/artistic")
def draw_artistic_text(req: CreateTextCMYKRequest):
    """Tạo văn bản nghệ thuật CMYK."""
    c = req.color.cyan
    m = req.color.magenta
    y = req.color.yellow
    k = req.color.black
    shape_name = corel_bridge.create_artistic_text_cmyk(req.text, req.x, req.y, req.font_name, req.font_size, c, m, y, k)
    if not shape_name:
        raise HTTPException(status_code=500, detail="Không thể tạo đối tượng Text CMYK.")
    return {"status": "success", "shape_name": shape_name}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
