"""Category-aware density diagnostics independent of learned critics."""

from __future__ import annotations

from training.evaluation.layout_metrics import evaluate_layout
from training.schemas.design import DesignDocument
from training.visual.models import DensityDiagnosticsV1, VisualStyleProfileV1


def evaluate_density(
    document: DesignDocument,
    profile: VisualStyleProfileV1,
) -> DensityDiagnosticsV1:
    actual = float(evaluate_layout(document)["coverage"])
    error = abs(actual - float(profile.density_target))
    if actual < profile.density_min:
        scale = max(float(profile.density_min), 1e-6)
        fit = 1 - (float(profile.density_min) - actual) / scale
    elif actual > profile.density_max:
        scale = max(1 - float(profile.density_max), 1e-6)
        fit = 1 - (actual - float(profile.density_max)) / scale
    else:
        half_range = max(
            float(profile.density_target - profile.density_min),
            float(profile.density_max - profile.density_target),
            1e-6,
        )
        fit = 1 - min(error / half_range, 1) * 0.25
    return DensityDiagnosticsV1(
        actual_coverage=max(0.0, min(actual, 1.0)),
        target_coverage=float(profile.density_target),
        density_min=float(profile.density_min),
        density_max=float(profile.density_max),
        density_error=min(error, 1.0),
        density_fit=max(0.0, min(float(fit), 1.0)),
    )


__all__ = ["evaluate_density"]
