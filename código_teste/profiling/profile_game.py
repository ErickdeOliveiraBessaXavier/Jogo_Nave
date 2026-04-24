#!/usr/bin/env python3
"""cProfile-based profiling tool for the game."""

from __future__ import annotations

import argparse
import cProfile
import io
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

SCRIPT_DIR = Path(__file__).resolve().parent
COMMON_DIR = SCRIPT_DIR.parent / "common"
ROOT_DIR = SCRIPT_DIR.parents[1]
for path in (ROOT_DIR, COMMON_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from performance_common import (classify_performance,  # noqa: E402
                                parse_difficulty, run_benchmark)

DEFAULT_PROFILE_PATH = SCRIPT_DIR / "profile_game.prof"
DEFAULT_SUMMARY_PATH = SCRIPT_DIR / "profile_summary.txt"


def build_timestamped_path(base_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return base_path.with_name(f"{base_path.stem}_{timestamp}{base_path.suffix}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Profile the game using cProfile.")
    parser.add_argument(
        "--duration", type=float, default=15.0, help="Profiling duration in seconds."
    )
    parser.add_argument(
        "--difficulty",
        type=parse_difficulty,
        default="normal",
        help="Difficulty preset (casual, normal, hardcore, nightmare).",
    )
    parser.add_argument(
        "--starting-level",
        type=int,
        default=1,
        help="1-based level index used to start profiling.",
    )
    parser.add_argument(
        "--warmup",
        type=float,
        default=1.0,
        help="Warmup time excluded from metrics.",
    )
    parser.add_argument(
        "--lines",
        type=int,
        default=25,
        help="Number of lines shown in the pstats summary.",
    )
    parser.add_argument(
        "--sort-by",
        choices=("cumulative", "tottime", "time", "calls"),
        default="cumulative",
        help="Sort key used in the pstats summary.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_PROFILE_PATH,
        help="Binary cProfile output file.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=DEFAULT_SUMMARY_PATH,
        help="Text summary output file.",
    )
    parser.add_argument(
        "--timestamp-output",
        action="store_true",
        help="Append timestamp (YYYYMMDD_HHMMSS) to output filenames.",
    )
    return parser


def run_profile(
    duration_seconds: float,
    warmup_seconds: float,
    difficulty,
    starting_level: int,
) -> tuple[dict[str, object], cProfile.Profile]:
    profiler = cProfile.Profile()
    profiler.enable()
    results = run_benchmark(
        duration_seconds=duration_seconds,
        warmup_seconds=warmup_seconds,
        difficulty=difficulty,
        starting_level=starting_level,
    )
    profiler.disable()
    return results, profiler


def build_summary_text(
    profiler: cProfile.Profile,
    sort_by: str,
    line_count: int,
) -> str:
    stream = io.StringIO()
    stats = cProfile.Profile()
    stats = None
    profile_stats = io.StringIO()
    import pstats

    pstats.Stats(profiler, stream=profile_stats).strip_dirs().sort_stats(
        sort_by
    ).print_stats(line_count)
    return profile_stats.getvalue()


def print_summary(
    results: dict[str, object],
    summary_text: str,
    profile_path: Path,
    summary_path: Path,
) -> None:
    print("=" * 78)
    print("GAME PROFILING REPORT")
    print("=" * 78)
    print(f"Duration: {results['duration_seconds']:.2f}s")
    print(f"Frames: {results['total_frames']}")
    print(f"Average FPS: {results['fps']['average']:.2f}")
    print(f"Frame time avg: {results['frame_time_ms']['average']:.2f} ms")
    print(f"Frame time max: {results['frame_time_ms']['maximum']:.2f} ms")
    print(f"Memory peak: {results['memory_mb']['maximum']:.2f} MB")
    print(
        f"Rating: {results['performance_rating']} ({classify_performance(results['fps']['average'])})"
    )
    print()
    print(summary_text.rstrip())
    print()
    print(f"Profile saved to: {profile_path}")
    print(f"Summary saved to: {summary_path}")
    print("=" * 78)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.duration <= 0:
        parser.error("--duration must be greater than 0")
    if args.warmup < 0:
        parser.error("--warmup must be 0 or greater")
    if args.starting_level <= 0:
        parser.error("--starting-level must be greater than 0")
    if args.lines <= 0:
        parser.error("--lines must be greater than 0")

    output_path = args.output
    summary_output_path = args.summary_output
    if args.timestamp_output:
        output_path = build_timestamped_path(output_path)
        summary_output_path = build_timestamped_path(summary_output_path)

    results, profiler = run_profile(
        duration_seconds=args.duration,
        warmup_seconds=args.warmup,
        difficulty=args.difficulty,
        starting_level=args.starting_level,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    profiler.dump_stats(str(output_path))

    summary_text = build_summary_text(profiler, args.sort_by, args.lines)
    summary_output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_output_path.write_text(summary_text, encoding="utf-8")

    print_summary(results, summary_text, output_path, summary_output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
