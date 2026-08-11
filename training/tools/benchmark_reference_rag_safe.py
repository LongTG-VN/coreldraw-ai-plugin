"""Safe v0.3 benchmark entrypoint; fresh unless resume/audited reuse is explicit."""

from __future__ import annotations

import json

from training.tools.benchmark_reference_rag import _parser, run_benchmark


def main() -> int:
    args = _parser().parse_args()
    if args.context_token_budget < 128:
        raise ValueError("context-token-budget must be at least 128")
    if args.reuse_rag_candidates_from is not None:
        raise ValueError(
            "legacy raw RAG candidate reuse is disabled; use fresh generation, "
            "--resume, or --audited-rag-cache-from"
        )
    summary = run_benchmark(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["v0.3_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
