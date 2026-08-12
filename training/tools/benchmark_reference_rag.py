"""Safe public entrypoint for the v0.3 fair RAG benchmark.

Fresh generation remains the default. The unsafe legacy reuse flag stays
blocked; explicit audited cache and resume modes use GenerationIdentityV1.
"""

from __future__ import annotations

import json
from typing import Any

from training.tools._benchmark_reference_rag_impl import (
    DEFAULT_BENCHMARK_CONFIG,
    DEFAULT_MODEL_CONFIG,
    DEFAULT_SCORE_CONFIG,
    DEFAULT_V02_BENCHMARK,
    SUCCESS_SCORE_IMPROVEMENT_PERCENT,
    _parser as _impl_parser,
    load_v03_scorer,
    replay_v02_prompt,
    run_benchmark as _impl_run_benchmark,
    summarize_comparison,
)

UNSAFE_REUSE_ERROR = (
    "legacy raw RAG candidate reuse is disabled; use fresh generation, --resume, "
    "or --audited-rag-cache-from with GenerationIdentityV1 verification"
)


def _parser() -> Any:
    """Return the backwards-compatible parser used by the implementation."""

    return _impl_parser()


def run_benchmark(args: Any) -> dict[str, Any]:
    """Run the fair benchmark while rejecting the unsafe legacy reuse path."""

    if getattr(args, "reuse_rag_candidates_from", None) is not None:
        raise ValueError(UNSAFE_REUSE_ERROR)
    return _impl_run_benchmark(args)


def main() -> int:
    args = _parser().parse_args()
    if args.context_token_budget < 128:
        raise ValueError("context-token-budget must be at least 128")
    summary = run_benchmark(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["v0.3_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_BENCHMARK_CONFIG",
    "DEFAULT_MODEL_CONFIG",
    "DEFAULT_SCORE_CONFIG",
    "DEFAULT_V02_BENCHMARK",
    "SUCCESS_SCORE_IMPROVEMENT_PERCENT",
    "UNSAFE_REUSE_ERROR",
    "load_v03_scorer",
    "replay_v02_prompt",
    "run_benchmark",
    "summarize_comparison",
]
