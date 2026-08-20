"""Single real-CDR mutation worker for the safe pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.company_archive.inspector import CompanyCdrInspector
from training.corel_operator.models import OperatorExecutionResultV1, OperatorResultClass
from training.corel_operator.planner import DeterministicMutationPilotPlanner
from training.corel_operator.policy import source_token
from training.corel_operator.service import SafeCorelOperator
from training.corel_operator.visual_qa import compare_operator_previews


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    row = request["row"]
    attempt = int(request["attempt"])
    source = Path(str(row["absolute_path"])).resolve()
    token = source_token(source, args.archive_root)
    inspection = CompanyCdrInspector().inspect(source, archive_root=args.archive_root)
    plan = DeterministicMutationPilotPlanner(
        preferred_mode=str(request.get("planner_mode", "auto"))
    ).plan(inspection, source_token=token)
    if plan is None:
        result = OperatorExecutionResultV1(
            result=OperatorResultClass.UNSUPPORTED,
            plan_id="none-" + token.removeprefix("source:")[:24],
            source_token=token,
            source_unchanged=True,
            error_code="NO_SAFE_TEXT_TARGET",
        )
    else:
        attempt_root = (
            args.workspace
            / "artifacts"
            / token.removeprefix("source:")
            / f"attempt_{attempt}"
        )
        result = SafeCorelOperator().execute(
            source_path=source,
            archive_root=args.archive_root,
            workspace=args.workspace,
            working_copy_path=attempt_root / "working_copy.cdr",
            plan=plan,
        )
        result.metadata["planner"] = plan.metadata
        if (
            result.result == OperatorResultClass.AUTO_SUCCESS
            and result.preview_before
            and result.preview_after
        ):
            visual_qa = compare_operator_previews(
                Path(result.preview_before),
                Path(result.preview_after),
                workspace=args.workspace,
            )
            result.metadata["visual_qa"] = visual_qa.model_dump(mode="json")
            if visual_qa.status == "NEEDS_REVIEW":
                result.result = OperatorResultClass.NEEDS_REVIEW
                result.warnings.extend(visual_qa.issues)
    args.response.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
