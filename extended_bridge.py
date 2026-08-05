"""
Module mở rộng cho CorelDRAW AI Bridge.
Cung cấp các hàm vẽ Vector nâng cao, quản lý Layer, Nhóm đối tượng (Grouping),
Cài đặt đường viền Outline CMYK và Xuất file PDF / PNG.
"""
import sys
from typing import Optional, List
from corel_bridge import corel_bridge

class ExtendedCorelDrawBridge:
    def __init__(self, bridge=corel_bridge):
        self.bridge = bridge

    def set_shape_outline_cmyk(self, shape_name: str, width: float, c: int, m: int, y: int, k: int) -> bool:
        """Đổi màu sắc và độ dày đường viền (Outline) chuẩn CMYK cho một đối tượng."""
        if not self.bridge.app or not self.bridge.doc:
            if not self.bridge.connect():
                return False
        try:
            layer = self.bridge.doc.ActivePage.ActiveLayer
            shape = layer.Shapes.Item(shape_name)
            if shape:
                shape.Outline.Width = width
                cmyk_color = self.bridge._create_cmyk_color(c, m, y, k)
                shape.Outline.Color = cmyk_color
                return True
            return False
        except Exception as e:
            print(f"Error setting outline CMYK: {e}")
            return False

    def group_shapes_by_names(self, shape_names: List[str]) -> Optional[str]:
        """Gom nhóm (Group) danh sách các Shape tên chỉ định thành 1 Group duy nhất."""
        if not self.bridge.app or not self.bridge.doc:
            if not self.bridge.connect():
                return None
        try:
            layer = self.bridge.doc.ActivePage.ActiveLayer
            shapes_range = layer.CreateShapeRange()
            for name in shape_names:
                try:
                    s = layer.Shapes.Item(name)
                    if s:
                        shapes_range.Add(s)
                except Exception:
                    pass
            
            if shapes_range.Count > 0:
                grouped_shape = shapes_range.Group()
                return grouped_shape.Name
            return None
        except Exception as e:
            print(f"Error grouping shapes: {e}")
            return None

    def export_to_pdf(self, file_path: str) -> bool:
        """Tự động xuất file thiết kế hiện tại ra định dạng PDF in ấn."""
        if not self.bridge.app or not self.bridge.doc:
            if not self.bridge.connect():
                return False
        try:
            # CorelDRAW ActiveDocument.ExportEx
            pdf_options = self.bridge.app.CreateStructExportOptions()
            pdf_options.FilterID = "PDF"
            self.bridge.doc.Export(file_path, 8, 0, pdf_options) # 8 = cdrPDF
            return True
        except Exception as e:
            print(f"Error exporting PDF: {e}")
            return False

extended_bridge = ExtendedCorelDrawBridge()

if __name__ == "__main__":
    print("Extended CorelDRAW Bridge Loaded Successfully.")
