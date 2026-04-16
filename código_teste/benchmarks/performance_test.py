#!/usr/bin/env python3
"""Automated performance benchmark for the game."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

SCRIPT_DIR = Path(__file__).resolve().parent
COMMON_DIR = SCRIPT_DIR.parent / "common"
ROOT_DIR = SCRIPT_DIR.parents[1]
for path in (ROOT_DIR, COMMON_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from performance_common import (  # noqa: E402
    DifficultyPreset,
    parse_difficulty,
    run_benchmark,
    write_json,
)

DEFAULT_OUTPUT_PATH = SCRIPT_DIR / "performance_results.json"


def print_summary(results: dict[str, object], output_path: Path) -> None:
    print("=" * 78)
    print("PERFORMANCE BENCHMARK")
    print("=" * 78)
    print(f"Duration: {results['duration_seconds']:.2f}s")
    print(f"Frames: {results['total_frames']}")
    print(f"Difficulty: {results['difficulty']}")
    print(f"Starting level: {results['starting_level']}")
    print(f"Average FPS: {results['fps']['average']:.2f}")
    print(f"Frame time avg: {results['frame_time_ms']['average']:.2f} ms")
    print(f"Frame time max: {results['frame_time_ms']['maximum']:.2f} ms")
    print(f"Memory avg: {results['memory_mb']['average']:.2f} MB")
    print(f"Memory peak: {results['memory_mb']['maximum']:.2f} MB")
    print(f"Rating: {results['performance_rating']}")
    print(f"Saved to: {output_path}")
    print("=" * 78)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a game performance benchmark.")
    parser.add_argument(
        "--duration", type=float, default=15.0, help="Benchmark duration in seconds."
    )
    parser.add_argument(
        "--warmup", type=float, default=1.0, help="Warmup time excluded from metrics."
    )
    parser.add_argument(
        "--difficulty",
        type=parse_difficulty,
        default=DifficultyPreset.NORMAL,
        help="Difficulty preset (casual, normal, hardcore, nightmare).",
    )
    parser.add_argument(
        "--starting-level",
        type=int,
        default=1,
        help="1-based level index used to start the benchmark.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Output JSON file path.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.duration <= 0:
        parser.error("--duration must be greater than 0")
    if args.warmup < 0:
        parser.error("--warmup must be 0 or greater")
    if args.starting_level <= 0:
        parser.error("--starting-level must be greater than 0")

    results = run_benchmark(
        duration_seconds=args.duration,
        warmup_seconds=args.warmup,
        difficulty=args.difficulty,
        starting_level=args.starting_level,
    )
    write_json(str(args.output), results)
    print_summary(results, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
