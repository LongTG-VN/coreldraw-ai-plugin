"""Build and validate the sanitized private mutation-pilot review package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.corel_operator.artifacts import (
    build_mutation_review_artifacts,
    validate_private_artifact,
)
from training.corel_operator.state import OperatorStateDatabase


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-workspace", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--run-id", default="real-mutation-pilot-001")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    state = OperatorStateDatabase(args.state)
    summary = build_mutation_review_artifacts(
        pilot_workspace=args.pilot_workspace,
        output_root=args.output,
        state_rows=state.batch_rows(args.run_id),
    )
    validation = validate_private_artifact(args.output)
    result = {**summary, "validation": validation}
    print(json.dumps(result, indent=2))
    return 0 if validation["forbidden_binary_count"] == 0 and validation["path_leak_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
