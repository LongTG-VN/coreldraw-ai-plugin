"""Calibrate the local critic on blinded v0.3.2 placeholder vs v0.3.3 assets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import mean, pvariance

from training.schemas.design import DesignDocument
from training.vision.critic import TransformersQwenVisionCritic
from training.vision.models import VisionCriticConfig
from training.visual.profiles import normalize_visual_category


CASES = ("spa", "cafe", "sale", "menu", "signage")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: object) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def blinded_order(case_id: str, old: Path, new: Path) -> tuple[Path, Path, dict[str, str]]:
    swap = int(hashlib.sha256(case_id.encode("utf-8")).hexdigest()[-1], 16) % 2 == 1
    if swap:
        return new, old, {"A": "v0.3.3", "B": "v0.3.2"}
    return old, new, {"A": "v0.3.2", "B": "v0.3.3"}


def _asset_roles(manifest: dict) -> list[str]:
    return sorted({str(row["role"]) for row in manifest.get("assets", [])})


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left | right else 1.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--benchmark-config", type=Path, required=True)
    parser.add_argument("--critic-config", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    config = VisionCriticConfig.model_validate(_read(args.critic_config.resolve()))
    critic = TransformersQwenVisionCritic(config, local_model_path=args.model_path.resolve())
    prompts = {row["id"]: row for row in _read(args.benchmark_config.resolve())["prompts"]}
    rows = []
    repeat_results = []
    for case_id in CASES:
        print(f"calibrating {case_id}: absolute critiques", flush=True)
        root = source / "runs" / case_id
        case = _read(root / "case.json")
        manifest = _read(root / "asset_manifest.json")
        prompt = prompts[case["source_prompt_id"]]["prompt"]
        category = normalize_visual_category(case_id)
        old_doc = DesignDocument.model_validate_json((root / "baseline" / "design.json").read_text(encoding="utf-8"))
        new_doc = DesignDocument.model_validate_json((root / "asset_aware" / "design.json").read_text(encoding="utf-8"))
        roles = _asset_roles(manifest)
        old = critic.critique(
            preview_path=root / "baseline" / "preview.png", brief=prompt,
            category=category, business_content=case, asset_roles=roles, document=old_doc,
        )
        new = critic.critique(
            preview_path=root / "asset_aware" / "preview.png", brief=prompt,
            category=category, business_content=case, asset_roles=roles, document=new_doc,
        )
        case_dir = output / case_id
        _write(case_dir / "v032_critique.json", old)
        _write(case_dir / "v033_critique.json", new)
        image_a, image_b, mapping = blinded_order(
            case_id, root / "baseline" / "preview.png", root / "asset_aware" / "preview.png"
        )
        pairwise = critic.compare(
            image_a=image_a, image_b=image_b, brief=prompt, category=category
        )
        print(f"calibrating {case_id}: pairwise complete", flush=True)
        preferred_version = mapping.get(pairwise.preferred, "tie")
        _write(case_dir / "pairwise.json", pairwise)
        _write(case_dir / "pairwise_private_mapping.json", mapping)
        rows.append(
            {
                "case_id": case_id,
                "v032_score": old.overall.quality_score,
                "v033_score": new.overall.quality_score,
                "score_delta": new.overall.quality_score - old.overall.quality_score,
                "pairwise_preferred": preferred_version,
                "pairwise_confidence": pairwise.confidence,
                "v032_issues": [item.issue_type for item in old.issues],
                "v033_issues": [item.issue_type for item in new.issues],
            }
        )
        if case_id == "sale":
            repeat_results.append(new)
            for index in range(2):
                print(f"calibrating sale: consistency repeat {index + 2}/3", flush=True)
                repeated = critic.critique(
                    preview_path=root / "asset_aware" / "preview.png", brief=prompt,
                    category=category, business_content=case, asset_roles=roles,
                    document=new_doc,
                )
                repeat_results.append(repeated)
                _write(case_dir / f"repeat_{index + 2}.json", repeated)
    scores = [float(item.overall.quality_score) for item in repeat_results]
    issue_sets = [{item.issue_type for item in result.issues} for result in repeat_results]
    top_issues = [result.issues[0].issue_type if result.issues else None for result in repeat_results]
    summary = {
        "schema_version": "1.0",
        "known_comparison_count": len(rows),
        "v033_absolute_score_preferred_count": sum(row["score_delta"] > 0 for row in rows),
        "pairwise_v033_preferred_count": sum(row["pairwise_preferred"] == "v0.3.3" for row in rows),
        "pairwise_v032_preferred_count": sum(row["pairwise_preferred"] == "v0.3.2" for row in rows),
        "pairwise_tie_count": sum(row["pairwise_preferred"] == "tie" for row in rows),
        "mean_score_delta": mean(row["score_delta"] for row in rows),
        "repeat_count": len(repeat_results),
        "score_variance": pvariance(scores),
        "issue_agreement": mean(
            _jaccard(issue_sets[0], current) for current in issue_sets[1:]
        ),
        "top_issue_stability": mean(top == top_issues[0] for top in top_issues[1:]),
        "critic_load_seconds": critic.load_duration_seconds,
        "peak_vram_gib": critic.peak_memory_gib,
        "rows": rows,
    }
    summary["calibration_credible"] = bool(
        summary["pairwise_v033_preferred_count"] >= 3
        and summary["pairwise_v032_preferred_count"] <= 2
        and summary["score_variance"] <= .02
        and summary["top_issue_stability"] >= .5
    )
    _write(output / "calibration_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["calibration_credible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
