from __future__ import annotations

import sys

import pytest

from training.tools.benchmark_reference_rag_safe import main


def test_safe_benchmark_rejects_legacy_raw_output_reuse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchmark_reference_rag_safe.py",
            "--checkpoint",
            "checkpoint-5",
            "--reference-index",
            "reference_index.jsonl",
            "--output",
            "benchmark-output",
            "--reuse-rag-candidates-from",
            "unsafe-cache",
        ],
    )

    with pytest.raises(ValueError, match="reuse is disabled"):
        main()
