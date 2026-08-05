"""
Module kết nối và tương tác tự động hóa với CorelDRAW ứng dụng VBA / COM Automation Interface (win32com.client).
Hỗ trợ màu sắc CMYK chuẩn in ấn quảng cáo và các hình khối Vector cơ bản.
"""
import sys
from typing import Dict, Any, Optional, List

try:
    import win32com.client
except ImportError:
    win32com = None

class CorelDrawBridge:
    def __init__(self):
        self.app = None
        self.doc = None

    def connect(self) -> bool:
        """Kết nối tới tiến trình CorelDRAW đang mở trên Windows."""
        if win32com is None:
            print("Error: pywin32 library is not installed.")
            return False
        try:
            self.app = win32com.client.Dispatch("CorelDRAW.Application")
            self.app.Visible = True
            if self.app.Documents.Count == 0:
                self.doc = self.app.CreateDocument()
            else:
                self.doc = self.app.ActiveDocument
            return True
        except Exception as e:
            print(f"Failed to connect to CorelDRAW: {e}")
            return False

    def _create_cmyk_color(self, c: int, m: int, y: int, k: int):
        """Khởi tạo màu sắc CMYK chuẩn in ấn."""
        return self.app.CreateCMYKColor(c, m, y, k)

    def create_rectangle_cmyk(self, x: float, y: float, width: float, height: float, c: int, m: int, y_col: int, k: int) -> Optional[str]:
        """Tạo hình chữ nhật / khung bảng hiệu với màu tô CMYK."""
        if not self.app or not self.doc:
            if not self.connect():
                return None
        try:
            layer = self.doc.ActivePage.ActiveLayer
            shape = layer.CreateRectangle(x, y, x + width, y - height)
            cmyk_color = self._create_cmyk_color(c, m, y_col, k)
            shape.Fill.ApplyUniformFill(cmyk_color)
            return shape.Name
        except Exception as e:
            print(f"Error creating rectangle CMYK: {e}")
            return None

    def create_ellipse_cmyk(self, x: float, y: float, width: float, height: float, c: int, m: int, y_col: int, k: int) -> Optional[str]:
        """Tạo hình elip / hình tròn Vector với màu CMYK."""
        if not self.app or not self.doc:
            if not self.connect():
                return None
        try:
            layer = self.doc.ActivePage.ActiveLayer
            shape = layer.CreateEllipse(x, y, x + width, y - height)
            cmyk_color = self._create_cmyk_color(c, m, y_col, k)
            shape.Fill.ApplyUniformFill(cmyk_color)
            return shape.Name
        except Exception as e:
            print(f"Error creating ellipse CMYK: {e}")
            return None

    def create_artistic_text_cmyk(self, text_content: str, x: float, y: float, font_name: str = "Arial", font_size: float = 24.0, c: int = 0, m: int = 0, y_col: int = 0, k: int = 100) -> Optional[str]:
        """Chèn văn bản nghệ thuật với màu CMYK chỉ định."""
        if not self.app or not self.doc:
            if not self.connect():
                return None
        try:
            layer = self.doc.ActivePage.ActiveLayer
            shape = layer.CreateArtisticText(x, y, text_content)
            shape.Text.FontProperties.Name = font_name
            shape.Text.FontProperties.Size = font_size
            cmyk_color = self._create_cmyk_color(c, m, y_col, k)
            shape.Fill.ApplyUniformFill(cmyk_color)
            return shape.Name
        except Exception as e:
            print(f"Error creating artistic text CMYK: {e}")
            return None

corel_bridge = CorelDrawBridge()

if __name__ == "__main__":
    print("CorelDRAW CMYK Automation Bridge Initialized.")
