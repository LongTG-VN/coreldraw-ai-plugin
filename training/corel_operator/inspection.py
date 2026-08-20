"""Read-only object queries and deterministic geometry checks for operator plans."""

from __future__ import annotations

import re
from dataclasses import dataclass

from training.company_archive.models import CdrInspectionV1, CdrObjectV1


@dataclass(frozen=True)
class Collision:
    object_a: str
    object_b: str
    overlap_area: float


class OperatorDocumentView:
    def __init__(self, inspection: CdrInspectionV1) -> None:
        self.inspection = inspection
        self._objects = {item.object_id: item for item in inspection.objects}

    def list_pages(self) -> list[dict[str, int | float | bool]]:
        """List known pages without pretending uninspected pages have object data."""

        return [
            {
                "page": index,
                "width": self.inspection.page_width if index == 1 else 0.0,
                "height": self.inspection.page_height if index == 1 else 0.0,
                "objects_inspected": index == 1,
            }
            for index in range(1, self.inspection.page_count + 1)
        ]

    def list_objects(self, *, object_type: str | None = None) -> list[CdrObjectV1]:
        values = list(self.inspection.objects)
        if object_type is not None:
            values = [item for item in values if item.object_type == object_type]
        return values

    def get_object(self, object_id: str) -> CdrObjectV1:
        try:
            return self._objects[object_id]
        except KeyError as exc:
            raise KeyError(f"unknown operator object ID: {object_id}") from exc

    def find_text(
        self,
        value: str,
        *,
        case_sensitive: bool = True,
        regex: bool = False,
    ) -> list[CdrObjectV1]:
        if regex and len(value) > 200:
            raise ValueError("regex query exceeds 200 characters")
        result: list[CdrObjectV1] = []
        for item in self.inspection.objects:
            if item.text is None:
                continue
            if regex:
                flags = 0 if case_sensitive else re.IGNORECASE
                try:
                    matched = re.search(value, item.text, flags=flags) is not None
                except re.error as exc:
                    raise ValueError(f"invalid regex: {exc}") from exc
            elif case_sensitive:
                matched = value in item.text
            else:
                matched = value.casefold() in item.text.casefold()
            if matched:
                result.append(item)
        return result

    def outside_canvas(self) -> list[str]:
        return [
            item.object_id
            for item in self.inspection.objects
            if bool(item.metadata.get("bbox_clipped_to_page"))
        ]

    def collisions(self, *, include_parent_child: bool = False) -> list[Collision]:
        items = self.inspection.objects
        collisions: list[Collision] = []
        for left_index, left in enumerate(items):
            for right in items[left_index + 1 :]:
                if not include_parent_child and (
                    left.parent_id == right.object_id or right.parent_id == left.object_id
                ):
                    continue
                left_x2 = left.bbox["x"] + left.bbox["width"]
                left_y2 = left.bbox["y"] + left.bbox["height"]
                right_x2 = right.bbox["x"] + right.bbox["width"]
                right_y2 = right.bbox["y"] + right.bbox["height"]
                width = min(left_x2, right_x2) - max(left.bbox["x"], right.bbox["x"])
                height = min(left_y2, right_y2) - max(left.bbox["y"], right.bbox["y"])
                if width > 0 and height > 0:
                    collisions.append(
                        Collision(
                            object_a=left.object_id,
                            object_b=right.object_id,
                            overlap_area=width * height,
                        )
                    )
        return collisions
