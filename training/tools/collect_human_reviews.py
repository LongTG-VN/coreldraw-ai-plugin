"""Collect completed manual reviews into a validated PreferencePairV1 JSONL."""

from __future__ import annotations

import argparse
from pathlib import Path

from training.preference.human_review import build_preference_pair


def _review_paths(values: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        resolved = value.resolve()
        if resolved.is_dir():
            paths.extend(resolved.rglob("manual_review.completed.json"))
        elif resolved.is_file():
            paths.append(resolved)
        else:
            raise FileNotFoundError(f"review input does not exist: {resolved}")
    return sorted(set(paths))


def collect(review_inputs: list[Path], output: Path) -> tuple[Path, int]:
    reviews = _review_paths(review_inputs)
    if not reviews:
        raise ValueError("no completed human review files found")
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite preference dataset: {output}")
    pairs = []
    pair_ids: set[str] = set()
    for review_path in reviews:
        comparison_path = review_path.parent / "comparison.json"
        if not comparison_path.is_file():
            raise FileNotFoundError(f"comparison.json missing beside review: {review_path}")
        pair = build_preference_pair(
            review_path=review_path,
            comparison_path=comparison_path,
        )
        if pair.pair_id in pair_ids:
            raise ValueError(f"duplicate preference pair: {pair.pair_id}")
        pair_ids.add(pair.pair_id)
        pairs.append(pair)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(pair.model_dump_json() + "\n" for pair in pairs),
        encoding="utf-8",
    )
    return output, len(pairs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reviews", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output, count = collect(args.reviews, args.output)
    print(f"collected={count} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
