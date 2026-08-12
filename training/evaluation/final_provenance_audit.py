"""Final provenance wrapper for the quarantined planner shootout.

Historical nonce probes were insufficient because a local deterministic adapter
could echo a nonce and manufacture a reasoning-looking JSON response. The final
audit now delegates to the stricter v2 planner provenance gate and defaults to no
execution. It cannot certify a planner merely from non-empty output or timing.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from training.evaluation.real_planner_audit import perform_real_planner_audit


REAL_BENCHMARK_ROOT = Path(
    "training/artifacts/benchmarks/20260812_real_antigravity_vs_qwen_planner"
)


def run_final_provenance_audit(
    output_root: Path = REAL_BENCHMARK_ROOT,
    *,
    execute: bool = False,
) -> dict[str, Any]:
    """Run the strict v2 planner provenance gate and record a final audit artifact.

    ``execute=False`` is deliberate. Codex must explicitly opt into a live audit
    once a genuine Antigravity execution bridge and an AI-output-derived Qwen plan
    path exist. Historical candidate files are not accepted as proof of a new run.
    """
    audit_dir = output_root / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    planner_audit = perform_real_planner_audit(execute=execute)
    verified = planner_audit.get("conclusion") == "REAL_PLANNER_SHOOTOUT_VALID"

    report = {
        "schema_version": "2.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "conclusion": (
            "REAL_PLANNER_PROVENANCE_VERIFIED"
            if verified
            else "PLANNER_PROVENANCE_NOT_VERIFIED"
        ),
        "provenance_verified": verified,
        "execution_requested": execute,
        "planner_audit": planner_audit,
        "historical_nonce_probe_policy": "NOT_SUFFICIENT_EVIDENCE",
        "historical_candidate_outputs_accepted_as_fresh_proof": False,
        "requirements": {
            "qwen": [
                "fresh real model invocation",
                "non-empty fresh raw output",
                "DesignPlanV2 derived from that AI output",
                "no fixture or historical fallback",
                "content lock valid",
            ],
            "antigravity": [
                "fresh externally verified agent/model execution",
                "non-empty captured output",
                "DesignPlanV2 derived from that AI output",
                "no synthetic reasoning trace",
                "content lock valid",
            ],
        },
    }

    (audit_dir / "FINAL_PROVENANCE_AUDIT.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report
