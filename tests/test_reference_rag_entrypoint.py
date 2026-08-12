from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from training.tools.benchmark_reference_rag import UNSAFE_REUSE_ERROR, run_benchmark


def test_primary_v03_benchmark_rejects_raw_output_reuse() -> None:
    args = argparse.Namespace(reuse_rag_candidates_from=Path("unsafe-cache"))

    with pytest.raises(ValueError, match="reuse is disabled") as exc_info:
        run_benchmark(args)

    assert str(exc_info.value) == UNSAFE_REUSE_ERROR
