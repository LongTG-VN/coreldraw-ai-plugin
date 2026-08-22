"""Hermetic Vietnamese command benchmark for the plan-only agent boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from training.corel_agent.commands import analyze_vietnamese_command


Disposition = Literal["EXPLICIT", "PLAN_REVIEW_REQUIRED", "OUTPUT_ONLY_UNSUPPORTED"]


@dataclass(frozen=True)
class VietnameseCommandCase:
    case_id: str
    instruction: str
    expected_disposition: Disposition
    expected_constraints: tuple[str, ...] = ()
    expected_outputs: tuple[str, ...] = ()
    unsafe_or_vague: bool = False


VIETNAMESE_COMMAND_CASES: tuple[VietnameseCommandCase, ...] = (
    VietnameseCommandCase("phone_long", "đổi số điện thoại thành 0909 111 222", "EXPLICIT"),
    VietnameseCommandCase("phone_short", "thay sđt thành 0909 111 222", "EXPLICIT"),
    VietnameseCommandCase("phone_english", "sửa phone thành 0909 111 222", "EXPLICIT"),
    VietnameseCommandCase("logo_scale", "logo lớn thêm 10%", "EXPLICIT"),
    VietnameseCommandCase("logo_move", "dịch logo qua phải 2mm", "EXPLICIT"),
    VietnameseCommandCase("price_exact", "đổi giá 250k thành 299k", "EXPLICIT"),
    VietnameseCommandCase(
        "phone_with_preserve",
        "đổi số điện thoại thành 0909 111 222, giữ nguyên mọi thứ khác",
        "EXPLICIT",
        expected_constraints=("PRESERVE_ALL_UNTARGETED_OBJECTS",),
    ),
    VietnameseCommandCase(
        "logo_move_with_skip",
        "dịch logo qua trái 2mm, file nào không chắc thì bỏ qua",
        "EXPLICIT",
        expected_constraints=("SKIP_ON_UNCERTAINTY",),
    ),
    VietnameseCommandCase("missing_values", "đổi tên và số điện thoại", "PLAN_REVIEW_REQUIRED"),
    VietnameseCommandCase("constraint_only", "giữ nguyên mọi thứ khác", "PLAN_REVIEW_REQUIRED"),
    VietnameseCommandCase("negative_only", "đừng sửa logo", "PLAN_REVIEW_REQUIRED"),
    VietnameseCommandCase("uncertainty_only", "file nào không chắc thì bỏ qua", "PLAN_REVIEW_REQUIRED"),
    VietnameseCommandCase("vague_pretty", "làm cho đẹp", "PLAN_REVIEW_REQUIRED", unsafe_or_vague=True),
    VietnameseCommandCase("vague_all", "sửa hết", "PLAN_REVIEW_REQUIRED", unsafe_or_vague=True),
    VietnameseCommandCase("vague_delete", "xoá mấy cái dư", "PLAN_REVIEW_REQUIRED", unsafe_or_vague=True),
    VietnameseCommandCase("vague_random", "chỉnh đại", "PLAN_REVIEW_REQUIRED", unsafe_or_vague=True),
    VietnameseCommandCase("vague_decide", "tự quyết định", "PLAN_REVIEW_REQUIRED", unsafe_or_vague=True),
    VietnameseCommandCase(
        "vague_with_output",
        "làm cho đẹp rồi xuất PDF",
        "PLAN_REVIEW_REQUIRED",
        expected_outputs=("PDF",),
        unsafe_or_vague=True,
    ),
    VietnameseCommandCase("output_pdf", "xuất file PDF", "OUTPUT_ONLY_UNSUPPORTED", expected_outputs=("PDF",)),
    VietnameseCommandCase("output_png", "xuất PNG", "OUTPUT_ONLY_UNSUPPORTED", expected_outputs=("PNG",)),
    VietnameseCommandCase("output_cdr", "xuất CDR", "OUTPUT_ONLY_UNSUPPORTED", expected_outputs=("CDR",)),
    VietnameseCommandCase(
        "output_multi",
        "xuất CDR và PDF",
        "OUTPUT_ONLY_UNSUPPORTED",
        expected_outputs=("CDR", "PDF"),
    ),
    VietnameseCommandCase("save_copy", "lưu thành bản mới", "OUTPUT_ONLY_UNSUPPORTED"),
    VietnameseCommandCase("undo", "undo", "OUTPUT_ONLY_UNSUPPORTED"),
)


def run_vietnamese_command_benchmark() -> dict[str, object]:
    """Evaluate deterministic intent gating without touching Corel or source files."""

    rows: list[dict[str, object]] = []
    for case in VIETNAMESE_COMMAND_CASES:
        analysis = analyze_vietnamese_command(case.instruction)
        disposition_ok = analysis.disposition == case.expected_disposition
        constraints_ok = all(value in analysis.constraints for value in case.expected_constraints)
        outputs_ok = all(value in analysis.output_formats for value in case.expected_outputs)
        passed = disposition_ok and constraints_ok and outputs_ok
        rows.append(
            {
                "case_id": case.case_id,
                "expected_disposition": case.expected_disposition,
                "actual_disposition": analysis.disposition,
                "unsafe_or_vague": case.unsafe_or_vague,
                "passed": passed,
                "reasons": analysis.reasons,
            }
        )

    unsafe_rows = [row for row in rows if row["unsafe_or_vague"]]
    return {
        "schema_version": "1.0",
        "benchmark_type": "deterministic_vietnamese_command_boundary",
        "planner_type": "deterministic",
        "planner_provider": "local",
        "planner_model": "vietnamese_command_analyzer_v1",
        "planner_is_ai": False,
        "case_count": len(rows),
        "passed": sum(bool(row["passed"]) for row in rows),
        "unsafe_case_count": len(unsafe_rows),
        "unsafe_refused": sum(
            row["actual_disposition"] == "PLAN_REVIEW_REQUIRED" for row in unsafe_rows
        ),
        "all_passed": all(bool(row["passed"]) for row in rows),
        "rows": rows,
    }


__all__ = [
    "VIETNAMESE_COMMAND_CASES",
    "VietnameseCommandCase",
    "run_vietnamese_command_benchmark",
]
