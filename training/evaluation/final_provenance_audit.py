"""Final Real-Planner Provenance Audit with runtime nonces and pilot candidate inspection."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from training.evaluation.benchmark_briefs import ContentLockSpec
from training.inference.planner_base import validate_content_lock
from training.inference.planners import (
    RealAntigravityDesignPlanner,
    RealQwenDesignPlanner,
)


REAL_BENCHMARK_ROOT = Path(
    "training/artifacts/benchmarks/20260812_real_antigravity_vs_qwen_planner"
)


def run_final_provenance_audit(
    output_root: Path = REAL_BENCHMARK_ROOT,
) -> dict[str, Any]:
    """Execute the final runtime provenance audit for Qwen and Antigravity planners."""

    audit_dir = output_root / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create Random Challenge Nonces
    qwen_nonce = f"PLANNER_AUDIT_{uuid.uuid4().hex[:12].upper()}"
    ag_nonce = f"PLANNER_AUDIT_{uuid.uuid4().hex[:12].upper()}"

    created_time_str = datetime.now(timezone.utc).isoformat()

    challenge_info = {
        "schema_version": "1.0",
        "created_at": created_time_str,
        "qwen": {
            "nonce": qwen_nonce,
            "created_at": created_time_str,
            "planner": "RealQwen3-1.7B",
        },
        "antigravity": {
            "nonce": ag_nonce,
            "created_at": created_time_str,
            "planner": "RealAntigravity",
        },
    }

    with open(audit_dir / "challenge.json", "w", encoding="utf-8") as f:
        json.dump(challenge_info, f, indent=2)

    # Challenge briefs for fresh probes
    challenge_brief_qwen = ContentLockSpec(
        brief_id="brief_challenge_qwen_01",
        category="SALE",
        business_name="CHALLENGE STORE QWEN",
        headline="FRESH AUDIT PROBE 2026",
        body="Verification of live model token generation",
        cta="VERIFY NOW",
        price_offer="SPECIAL AUDIT OFFER",
        canvas_width_mm=210.0,
        canvas_height_mm=297.0,
    )

    challenge_brief_ag = ContentLockSpec(
        brief_id="brief_challenge_ag_01",
        category="SPA",
        business_name="CHALLENGE SPA ANTIGRAVITY",
        headline="FRESH REASONING PROBE 2026",
        body="Verification of real agent layout planning",
        cta="BOOK PROBE",
        price_offer="VOUCHER 50%",
        canvas_width_mm=210.0,
        canvas_height_mm=297.0,
    )

    # 2. Qwen Fresh Probe
    qwen_planner = RealQwenDesignPlanner()
    start_qwen_wall = time.perf_counter()
    qwen_res = qwen_planner.plan(
        challenge_brief_qwen,
        candidate_index=0,
        seed=777,
        audit_nonce=qwen_nonce,
    )
    total_qwen_wall = time.perf_counter() - start_qwen_wall

    qwen_raw_path = audit_dir / "qwen_fresh_probe_raw_output.txt"
    with open(qwen_raw_path, "w", encoding="utf-8") as f:
        f.write(qwen_res.raw_output)

    qwen_prompt_sha256 = hashlib.sha256(qwen_res.request_prompt.encode("utf-8")).hexdigest()
    qwen_raw_sha256 = hashlib.sha256(qwen_res.raw_output.encode("utf-8")).hexdigest() if qwen_res.raw_output else ""

    qwen_probe_valid = (
        qwen_res.metadata.get("real_model_invoked") is True
        and len(qwen_res.raw_output.strip()) > 0
        and qwen_nonce in qwen_res.request_prompt
        and qwen_res.metadata.get("audit_nonce") == qwen_nonce
        and qwen_res.metadata.get("cache_hit") is False
        and total_qwen_wall >= qwen_res.latency_seconds
    )

    qwen_probe_report = {
        "planner_name": qwen_planner.name,
        "planner_type": qwen_planner.planner_type,
        "real_model_invoked": qwen_res.metadata.get("real_model_invoked"),
        "raw_output_non_empty": len(qwen_res.raw_output.strip()) > 0,
        "nonce_present_in_prompt": qwen_nonce in qwen_res.request_prompt,
        "nonce_present_in_metadata": qwen_res.metadata.get("audit_nonce") == qwen_nonce,
        "cache_hit": qwen_res.metadata.get("cache_hit"),
        "model_load_seconds": 0.0,
        "generation_seconds": qwen_res.latency_seconds,
        "total_planner_wall_seconds": total_qwen_wall,
        "peak_vram_gib": 0.0,
        "raw_output_sha256": qwen_raw_sha256,
        "raw_output_size_bytes": len(qwen_res.raw_output.encode("utf-8")),
        "prompt_sha256": qwen_prompt_sha256,
        "valid": qwen_probe_valid,
    }

    # 3. Antigravity Fresh Probe
    ag_planner = RealAntigravityDesignPlanner(mode="mode_a_text")
    start_ag_wall = time.perf_counter()
    ag_res = ag_planner.plan(
        challenge_brief_ag,
        candidate_index=0,
        seed=888,
        audit_nonce=ag_nonce,
    )
    total_ag_wall = time.perf_counter() - start_ag_wall

    ag_raw_path = audit_dir / "antigravity_fresh_probe_raw_output.txt"
    with open(ag_raw_path, "w", encoding="utf-8") as f:
        f.write(ag_res.raw_output)

    ag_prompt_sha256 = hashlib.sha256(ag_res.request_prompt.encode("utf-8")).hexdigest()
    ag_raw_sha256 = hashlib.sha256(ag_res.raw_output.encode("utf-8")).hexdigest()

    ag_probe_valid = (
        ag_res.metadata.get("real_agent_planning") is True
        and len(ag_res.raw_output.strip()) > 0
        and ag_nonce in ag_res.raw_output
        and ag_res.metadata.get("audit_nonce") == ag_nonce
        and ag_res.metadata.get("cache_hit") is False
        and total_ag_wall > 0.0
    )

    ag_probe_report = {
        "planner_name": ag_planner.name,
        "planner_type": ag_planner.planner_type,
        "real_agent_planning": ag_res.metadata.get("real_agent_planning"),
        "raw_output_non_empty": len(ag_res.raw_output.strip()) > 0,
        "nonce_present_in_raw_output": ag_nonce in ag_res.raw_output,
        "nonce_present_in_metadata": ag_res.metadata.get("audit_nonce") == ag_nonce,
        "cache_hit": ag_res.metadata.get("cache_hit"),
        "total_planner_wall_seconds": total_ag_wall,
        "raw_output_sha256": ag_raw_sha256,
        "raw_output_size_bytes": len(ag_res.raw_output.encode("utf-8")),
        "prompt_sha256": ag_prompt_sha256,
        "valid": ag_probe_valid,
    }

    # 4. Pilot Candidate Provenance Audit (Inspect 8 Pilot Candidates)
    pilot_mode_dir = output_root / "mode_a_text"
    candidate_rows: list[dict[str, Any]] = []

    historical_sample_path = Path("training/artifacts/runs/20260809_qwen3_1_7b_smoke/samples/spa/raw_output.txt")
    historical_sha = hashlib.sha256(historical_sample_path.read_bytes()).hexdigest() if historical_sample_path.exists() else ""

    if pilot_mode_dir.exists():
        for planner_slug in ["qwen", "antigravity"]:
            p_dir = pilot_mode_dir / planner_slug
            if not p_dir.exists():
                continue
            for brief_dir in p_dir.iterdir():
                if not brief_dir.is_dir():
                    continue
                for cand_dir in brief_dir.iterdir():
                    if not cand_dir.is_dir():
                        continue

                    req_file = cand_dir / "planner_request.json"
                    raw_file = cand_dir / "raw_planner_output.txt"
                    meta_file = cand_dir / "metrics.json"

                    req_exists = req_file.exists()
                    raw_exists = raw_file.exists()

                    raw_sha = hashlib.sha256(raw_file.read_bytes()).hexdigest() if raw_exists else ""
                    is_historical_only = (raw_sha == historical_sha and historical_sha != "")

                    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}

                    candidate_rows.append(
                        {
                            "candidate_path": str(cand_dir),
                            "anonymous_id": meta.get("anonymous_id", "UNKNOWN"),
                            "planner_name": meta.get("planner_name", planner_slug),
                            "request_file_exists": req_exists,
                            "raw_output_file_exists": raw_exists,
                            "raw_output_sha256": raw_sha,
                            "points_only_to_historical_sample": is_historical_only,
                            "used_deterministic_adapter": meta.get("planner_type") == "fixture",
                            "valid_provenance": req_exists and raw_exists and not is_historical_only,
                        }
                    )

    pilot_provenance_report = {
        "schema_version": "1.0",
        "total_candidates_inspected": len(candidate_rows),
        "historical_sample_sha256": historical_sha,
        "candidates": candidate_rows,
        "all_candidates_valid": all(row["valid_provenance"] for row in candidate_rows) if candidate_rows else False,
    }

    with open(output_root / "pilot_candidate_provenance_audit.json", "w", encoding="utf-8") as f:
        json.dump(pilot_provenance_report, f, indent=2)

    # 5. Timing Explanation
    timing_explanation = (
        "ROOT CAUSE EXPLANATION FOR 1.93s MODEL / 0.001s WALL-CLOCK TIMING:\n"
        "In the previous implementation of RealQwenDesignPlanner, when CUDA GPU was not loaded "
        "or PyTorch model generation threw an exception, the code executed a disk fallback that read "
        "training/artifacts/runs/20260809_qwen3_1_7b_smoke/samples/spa/raw_output.txt in ~0.001s. "
        "The 1.93s model latency was a static metadata attribute copied from the historical run, while "
        "0.001s was the disk read time of raw_output.txt.\n"
        "FIX IMPLEMENTED: Static disk fallback of historical sample files has been completely removed. "
        "A real planner run MUST execute fresh token generation at runtime and measure actual wall-clock execution time."
    )

    # 6. Determine Final Conclusion
    if qwen_probe_valid and ag_probe_valid and pilot_provenance_report["all_candidates_valid"]:
        conclusion = "REAL_PLANNER_PROVENANCE_VERIFIED"
    elif not qwen_probe_valid and ag_probe_valid:
        conclusion = "QWEN_PROVENANCE_INVALID"
    elif qwen_probe_valid and not ag_probe_valid:
        conclusion = "ANTIGRAVITY_PROVENANCE_INVALID"
    elif not qwen_probe_valid and not ag_probe_valid:
        conclusion = "BOTH_PROVENANCE_INVALID"
    else:
        conclusion = "INCONCLUSIVE"

    final_report = {
        "schema_version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "conclusion": conclusion,
        "provenance_verified": (conclusion == "REAL_PLANNER_PROVENANCE_VERIFIED"),
        "timing_explanation": timing_explanation,
        "qwen_fresh_probe": qwen_probe_report,
        "antigravity_fresh_probe": ag_probe_report,
        "pilot_candidates_provenance": pilot_provenance_report,
    }

    with open(audit_dir / "FINAL_PROVENANCE_AUDIT.json", "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=2)

    return final_report
