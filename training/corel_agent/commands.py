"""Conservative Vietnamese command analysis before structured planning."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field

from training.corel_operator.models import StrictModel


class VietnameseCommandAnalysisV1(StrictModel):
    disposition: Literal["EXPLICIT", "PLAN_REVIEW_REQUIRED", "OUTPUT_ONLY_UNSUPPORTED"]
    normalized_instruction: str = Field(min_length=1, max_length=2000)
    constraints: list[str] = Field(default_factory=list, max_length=10)
    output_formats: list[Literal["CDR", "PDF", "PNG"]] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


_VAGUE = (
    "làm cho đẹp",
    "sửa hết",
    "xoá mấy cái dư",
    "xóa mấy cái dư",
    "chỉnh đại",
    "tự quyết định",
)
_UNSUPPORTED_OUTPUT_ONLY = ("undo", "hoàn tác", "lưu thành bản mới")


def analyze_vietnamese_command(instruction: str) -> VietnameseCommandAnalysisV1:
    normalized = " ".join(instruction.strip().split())
    folded = normalized.casefold()
    reasons: list[str] = []
    constraints: list[str] = []
    outputs: list[Literal["CDR", "PDF", "PNG"]] = []
    if any(value in folded for value in _VAGUE):
        reasons.append("VAGUE_OR_UNBOUNDED_INTENT")
    if "giữ nguyên mọi thứ khác" in folded:
        constraints.append("PRESERVE_ALL_UNTARGETED_OBJECTS")
    if "đừng sửa logo" in folded or "không sửa logo" in folded:
        constraints.append("PRESERVE_LOGO")
    if "không chắc" in folded and "bỏ qua" in folded:
        constraints.append("SKIP_ON_UNCERTAINTY")
    if re.search(r"\bpdf\b", folded):
        outputs.append("PDF")
    if re.search(r"\bpng\b", folded):
        outputs.append("PNG")
    if re.search(r"\bcdr\b", folded):
        outputs.append("CDR")

    normalized = re.sub(r"\b(?:thay|sửa)\s+sđt\b", "số điện thoại", normalized, flags=re.I)
    normalized = re.sub(r"\bsửa\s+phone\b", "phone", normalized, flags=re.I)
    if reasons:
        disposition = "PLAN_REVIEW_REQUIRED"
    elif any(value in folded for value in _UNSUPPORTED_OUTPUT_ONLY) and not re.search(
        r"(?:đổi|thay|sửa|di chuyển|tăng|resize|move)", folded
    ):
        disposition = "OUTPUT_ONLY_UNSUPPORTED"
        reasons.append("OUTPUT_OR_UNDO_NOT_IN_MUTATION_AUTHORITY")
    else:
        disposition = "EXPLICIT"
    return VietnameseCommandAnalysisV1(
        disposition=disposition,
        normalized_instruction=normalized,
        constraints=list(dict.fromkeys(constraints)),
        output_formats=list(dict.fromkeys(outputs)),
        reasons=reasons,
    )


__all__ = ["VietnameseCommandAnalysisV1", "analyze_vietnamese_command"]
