"""Map bounded vision issues to deterministic, reversible DesignDocument edits."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable

from training.evaluation.critics import TechnicalCritic
from training.inference.corel_compiler import CorelCompileError, compile_corel_operations
from training.schemas.design import BoundingBox, ColorSpec, DesignDocument, DesignElement, normalize_bbox
from training.typography.fitting import fit_design_typography, infer_text_role
from training.vision.models import (
    DesignIssueV1,
    RefinementOperationReportV1,
    RefinementOperationV1,
    RefinementPlanV1,
    TechnicalValidationV1,
    VisionCritiqueV1,
)
from training.visual.profiles import get_visual_profile


ISSUE_OPERATION = {
    "weak_focal_point": "scale_role",
    "hero_too_small": "scale_role",
    "hero_too_large": "scale_role",
    "weak_headline": "emphasize_text",
    "headline_too_small": "emphasize_text",
    "headline_too_large": "emphasize_text",
    "weak_cta": "emphasize_cta",
    "cta_too_small": "emphasize_cta",
    "cta_too_large": "emphasize_cta",
    "poor_visual_balance": "shift_role",
    "excessive_whitespace": "scale_role",
    "insufficient_whitespace": "scale_role",
    "uneven_spacing": "shift_role",
    "weak_hierarchy": "emphasize_text",
    "flat_typography": "emphasize_text",
    "poor_text_grouping": "shift_role",
    "poor_image_text_balance": "scale_role",
    "low_contrast": "adjust_contrast",
    "palette_incoherence": "adjust_contrast",
    "too_much_decoration": "adjust_decoration",
    "too_little_decoration": "adjust_decoration",
    "menu_spreadsheet_feel": "improve_menu_grouping",
    "menu_grouping_weak": "improve_menu_grouping",
    "campaign_energy_low": "adjust_decoration",
    "logo_too_small": "scale_role",
    "logo_too_large": "scale_role",
    "logo_competes_with_headline": "scale_role",
    "asset_crop_awkward": "scale_role",
}


def _semantic_text(value: str) -> str:
    # Wrapping may insert line breaks, but no lexical/business character may change.
    return re.sub(r"\s+", "", value)


def business_content(document: DesignDocument) -> dict[str, str]:
    return {
        element.id: _semantic_text(element.text.content)
        for element in document.elements
        if element.text is not None
        and not element.metadata.get("placeholder_label")
        and not element.metadata.get("placeholder_for")
    }


def _role(element: DesignElement, largest_font: float) -> str:
    explicit = element.metadata.get("asset_role") or element.metadata.get("role")
    if explicit:
        return str(explicit).casefold()
    if element.text is not None:
        return infer_text_role(element, largest_font=largest_font)
    return ""


def _targets(document: DesignDocument, role: str) -> list[DesignElement]:
    fonts = [float(item.text.font_size or 0) for item in document.elements if item.text]
    largest = max(fonts, default=0)
    aliases = {
        "hero": {"hero", "product"},
        "layout": {"hero", "product", "headline"},
        "typography": {"headline", "subtitle", "body"},
        "menu": {"menu_item", "price"},
    }
    wanted = aliases.get(role, {role})
    return [item for item in document.elements if _role(item, largest) in wanted]


def _set_norm(document: DesignDocument, element: DesignElement, values: tuple[float, float, float, float]) -> None:
    x, y, width, height = values
    margin = .025
    width = min(max(width, .02), 1 - margin * 2)
    height = min(max(height, .02), 1 - margin * 2)
    x = min(max(x, margin), 1 - margin - width)
    y = min(max(y, margin), 1 - margin - height)
    absolute = BoundingBox(
        x=x * float(document.canvas.width), y=y * float(document.canvas.height),
        width=width * float(document.canvas.width), height=height * float(document.canvas.height),
    )
    element.bbox = absolute
    element.bbox_norm = normalize_bbox(absolute, document.canvas)


def _scale(document: DesignDocument, element: DesignElement, factor: float) -> dict[str, float]:
    box = element.bbox_norm
    old_w, old_h = float(box.width), float(box.height)
    new_w = min(old_w * factor, old_w + .08)
    new_h = min(old_h * factor, old_h + .08)
    if factor < 1:
        new_w = max(old_w * factor, old_w - .08)
        new_h = max(old_h * factor, old_h - .08)
    center_x = float(box.x) + old_w / 2
    center_y = float(box.y) + old_h / 2
    _set_norm(document, element, (center_x - new_w / 2, center_y - new_h / 2, new_w, new_h))
    return {"factor": factor, "width": new_w, "height": new_h}


def _hex(value: str) -> ColorSpec:
    return ColorSpec(model="hex", values=[value.upper()])


class CritiqueToRefinementPlanner:
    """Convert only known issue types to bounded operations."""

    def __init__(self, *, max_operations: int = 3, repeated_issue_limit: int = 2) -> None:
        self.max_operations = max_operations
        self.repeated_issue_limit = repeated_issue_limit

    def plan(
        self,
        critique: VisionCritiqueV1,
        *,
        issue_attempts: Counter[str] | None = None,
    ) -> RefinementPlanV1:
        attempts = Counter(issue_attempts or {})
        operations: list[RefinementOperationV1] = []
        stalled = []
        ordered = sorted(
            critique.issues,
            key=lambda item: ({"high": 0, "medium": 1, "low": 2}[item.severity], -float(item.confidence), item.issue_type),
        )
        for issue in ordered:
            if attempts[issue.issue_type] >= self.repeated_issue_limit:
                stalled.append(issue.issue_type)
                continue
            if len(operations) >= self.max_operations:
                continue
            operation_type = ISSUE_OPERATION[issue.issue_type]
            direction = "decrease" if issue.issue_type in {
                "hero_too_large", "headline_too_large", "cta_too_large",
                "insufficient_whitespace", "logo_too_large", "logo_competes_with_headline",
                "too_much_decoration",
            } else "increase"
            operations.append(
                RefinementOperationV1(
                    operation_id=f"op_{len(operations) + 1:02d}",
                    operation_type=operation_type,
                    target_role=issue.target_role,
                    source_issue=issue.issue_type,
                    magnitude=issue.magnitude,
                    parameters={"direction": direction},
                    constraint_applied=(
                        "movement <= 5% canvas; bbox delta <= 8%; scale <= 12%; "
                        "font delta <= 12%; content immutable"
                    ),
                )
            )
        return RefinementPlanV1(operations=operations, stalled_issues=stalled)


def _apply_operation(document: DesignDocument, operation: RefinementOperationV1) -> tuple[dict[str, Any], dict[str, Any]]:
    targets = _targets(document, operation.target_role)
    if not targets:
        raise ValueError(f"no element matches role {operation.target_role}")
    before = {item.id: item.bbox_norm.model_dump() for item in targets}
    direction = str(operation.parameters.get("direction", "increase"))
    factor_delta = .07 if operation.magnitude == "small" else .12
    factor = 1 - factor_delta if direction == "decrease" else 1 + factor_delta
    if operation.operation_type == "scale_role":
        for target in targets[:2]:
            _scale(document, target, factor)
    elif operation.operation_type == "shift_role":
        for target in targets[:3]:
            box = target.bbox_norm
            center = float(box.x + box.width / 2)
            shift = min(.05, .025 if operation.magnitude == "small" else .04)
            shift = shift if center < .5 else -shift
            _set_norm(
                document, target,
                (float(box.x) + shift, float(box.y), float(box.width), float(box.height)),
            )
    elif operation.operation_type == "emphasize_text":
        for target in targets[:2]:
            if target.text is None:
                continue
            target.text.font_size = max(4, float(target.text.font_size or 12) * factor)
            target.text.font_weight = 800 if direction == "increase" else 600
            _scale(document, target, 1 + (factor_delta / 2 if direction == "increase" else -factor_delta / 2))
    elif operation.operation_type == "emphasize_cta":
        profile = get_visual_profile(document.category)
        for target in targets[:2]:
            _scale(document, target, factor)
            if target.text:
                target.text.font_weight = 800
                target.visual.fill = _hex(profile.palette_roles.cta_text)
        for element in document.elements:
            if element.metadata.get("decorative_role") == "cta_container":
                element.visual.fill = _hex(profile.palette_roles.cta_background)
                element.visual.opacity = 1
    elif operation.operation_type == "adjust_contrast":
        profile = get_visual_profile(document.category)
        for target in targets:
            if target.text:
                target.visual.fill = _hex(profile.palette_roles.headline if operation.target_role == "headline" else profile.palette_roles.body)
    elif operation.operation_type == "adjust_decoration":
        decorations = [item for item in document.elements if item.metadata.get("decorative_role")]
        if not decorations:
            raise ValueError("no existing decoration can be adjusted safely")
        for target in decorations[:4]:
            target.visual.opacity = min(1.0, float(target.visual.opacity) + .12) if direction == "increase" else max(.2, float(target.visual.opacity) - .15)
    elif operation.operation_type == "improve_menu_grouping":
        grouping = [
            item for item in document.elements
            if item.metadata.get("decorative_role") in {"menu_row_band", "menu_divider", "menu_price_rail"}
        ]
        if not grouping:
            raise ValueError("menu grouping surfaces are unavailable")
        for target in grouping:
            target.visual.opacity = min(1.0, float(target.visual.opacity) + .12)
    else:
        raise ValueError(f"unsupported bounded operation {operation.operation_type}")
    after = {item.id: item.bbox_norm.model_dump() for item in targets}
    return before, after


def validate_refinement(
    document: DesignDocument,
    *,
    original_content: dict[str, str],
    maximum_overlap: float,
) -> TechnicalValidationV1:
    violations: list[str] = []
    try:
        validated = DesignDocument.model_validate(document.model_dump())
        schema_valid = True
    except Exception as exc:
        return TechnicalValidationV1(
            schema_valid=False, hard_failure=True, outside_canvas_rate=1,
            overlap_ratio=1, text_fit_rate=0, truncation_count=0,
            corel_compile_valid=False, asset_aspect_preserved=False,
            logo_aspect_preserved=False, business_content_immutable=False,
            violations=[f"schema:{type(exc).__name__}"],
        )
    technical = TechnicalCritic().score(validated)
    outside = float(technical.metrics.get("outside_canvas_rate", 0))
    overlap = float(technical.metrics.get("overlap_ratio", 0))
    text_fit = float(technical.metrics.get("text_fit_rate", 1))
    truncation = sum(
        bool(item.metadata.get("typography_fit", {}).get("truncated"))
        for item in validated.elements
    )
    current_content = business_content(validated)
    immutable = current_content == original_content
    asset_elements = [item for item in validated.elements if item.type in {"image", "svg"}]
    aspect_safe = all(
        not isinstance(item.metadata.get("asset_fit"), dict)
        or item.metadata["asset_fit"].get("aspect_ratio_preserved") is not False
        for item in asset_elements
    )
    logos = [item for item in asset_elements if item.metadata.get("asset_role") == "logo"]
    logo_safe = all(
        not isinstance(item.metadata.get("asset_fit"), dict)
        or item.metadata["asset_fit"].get("aspect_ratio_preserved") is not False
        for item in logos
    )
    try:
        compile_corel_operations(
            validated,
            width_mm=float(validated.canvas.width),
            height_mm=float(validated.canvas.height),
        )
        corel_valid = True
    except CorelCompileError as exc:
        corel_valid = False
        violations.append(f"corel:{exc}")
    if technical.hard_failure:
        violations.append("technical_hard_failure")
    if outside > 0:
        violations.append("outside_canvas")
    if overlap > maximum_overlap + 1e-6:
        violations.append("overlap_regression")
    if text_fit < .95:
        violations.append("text_fit_below_0.95")
    if truncation:
        violations.append("text_truncation")
    if not immutable:
        violations.append("business_content_mutated")
    if not aspect_safe:
        violations.append("asset_aspect_changed")
    if not logo_safe:
        violations.append("logo_aspect_changed")
    hard_failure = bool(violations)
    return TechnicalValidationV1(
        schema_valid=schema_valid,
        hard_failure=hard_failure,
        outside_canvas_rate=outside,
        overlap_ratio=overlap,
        text_fit_rate=text_fit,
        truncation_count=truncation,
        corel_compile_valid=corel_valid,
        asset_aspect_preserved=aspect_safe,
        logo_aspect_preserved=logo_safe,
        business_content_immutable=immutable,
        violations=violations,
    )


def apply_refinement_plan(
    document: DesignDocument,
    plan: RefinementPlanV1,
) -> tuple[DesignDocument, list[RefinementOperationReportV1], TechnicalValidationV1]:
    working = document.model_copy(deep=True)
    original_content = business_content(document)
    baseline = TechnicalCritic().score(document)
    maximum_overlap = float(baseline.metrics.get("overlap_ratio", 0))
    reports: list[RefinementOperationReportV1] = []
    last_validation = validate_refinement(
        working, original_content=original_content, maximum_overlap=maximum_overlap
    )
    for operation in plan.operations:
        candidate = working.model_copy(deep=True)
        try:
            before, after = _apply_operation(candidate, operation)
            candidate, _ = fit_design_typography(candidate, allow_expand=False)
            validation = validate_refinement(
                candidate,
                original_content=original_content,
                maximum_overlap=maximum_overlap,
            )
            accepted = not validation.hard_failure
            reason = "accepted_after_all_technical_gates" if accepted else ";".join(validation.violations)
            if accepted:
                working = candidate
                last_validation = validation
        except Exception as exc:
            before, after = {}, {}
            accepted = False
            reason = f"bounded_operation_rejected:{type(exc).__name__}:{exc}"
        reports.append(
            RefinementOperationReportV1(
                operation_id=operation.operation_id,
                source_issue=operation.source_issue,
                accepted=accepted,
                reason=reason,
                before=before,
                after=after,
                constraint_applied=operation.constraint_applied,
            )
        )
    return DesignDocument.model_validate(working.model_dump()), reports, last_validation


__all__ = [
    "CritiqueToRefinementPlanner", "apply_refinement_plan", "business_content",
    "validate_refinement",
]
