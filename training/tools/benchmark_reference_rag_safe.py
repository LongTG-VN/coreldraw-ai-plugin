"""Safe v0.3 benchmark entrypoint.

The legacy benchmark supports raw-output reuse for long local runs. Its current
reuse cache is not prompt-aware, so prompts that share dimensions, seed and
max_new_tokens can collide. Until that cache is migrated, this entrypoint
intentionally disables reuse and requires fresh model generations.
"""

from __future__ import annotations

import json

from training.tools.benchmark_reference_rag import _parser, run_benchmark


def main() -> int:
    args = _parser().parse_args()
    if args.context_token_budget < 128:
        raise ValueError("context-token-budget must be at least 128")
    if args.reuse_rag_candidates_from is not None:
        raise ValueError(
            "raw RAG candidate reuse is temporarily disabled because the legacy "
            "cache key is not prompt/context-aware; run a fresh benchmark instead"
        )
    summary = run_benchmark(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["v0.3_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
