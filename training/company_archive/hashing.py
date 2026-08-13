"""Staged, streaming fingerprints for large immutable archives."""

from __future__ import annotations

import hashlib
from pathlib import Path


FAST_SAMPLE_BYTES = 64 * 1024


def fast_fingerprint(path: Path, *, sample_bytes: int = FAST_SAMPLE_BYTES) -> str:
    size = path.stat().st_size
    digest = hashlib.blake2b(digest_size=16)
    digest.update(size.to_bytes(8, "little", signed=False))
    with path.open("rb") as handle:
        head = handle.read(sample_bytes)
        digest.update(head)
        if size > sample_bytes:
            handle.seek(max(0, size - sample_bytes))
            digest.update(handle.read(sample_bytes))
    return digest.hexdigest()


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()

