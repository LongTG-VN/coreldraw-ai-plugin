"""Launch the local-only Design AI v0.4 blinded human review UI."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from training.preference.v04.review_app import create_review_app
from training.preference.v04.store import ReviewStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("training/data/human_preferences/v0_4"))
    parser.add_argument(
        "--queue", type=Path,
        default=Path("training/artifacts/preference/v0_4_initial_pool/review_queue/review_queue.jsonl"),
    )
    parser.add_argument(
        "--artifact-root", type=Path, action="append",
        default=[Path("training/artifacts")],
        help="Approved preview/design root; may be repeated.",
    )
    parser.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "localhost"])
    parser.add_argument("--port", type=int, default=8002)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    store = ReviewStore(data_root=args.data_root, queue_path=args.queue, approved_roots=args.artifact_root)
    app = create_review_app(store)
    print(f"Open:\nhttp://127.0.0.1:{args.port}/review")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
