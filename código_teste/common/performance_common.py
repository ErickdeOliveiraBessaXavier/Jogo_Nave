from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tracemalloc
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from game.core.difficulty import DifficultyPreset


def _prepare_pygame_runtime() -> None:
    # Hide pygame banner and silence setuptools deprecation warning emitted by pygame.
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    warnings.filterwarnings(
        "ignore",
        message="pkg_resources is deprecated as an API.*",
        category=UserWarning,
    )


def _ensure_project_root_on_path() -> None:
    root_dir = Path(__file__).resolve().parents[2]
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))


def parse_difficulty(value: str) -> "DifficultyPreset":
    _ensure_project_root_on_path()
    from game.core.difficulty import DifficultyPreset

    normalized = value.strip().lower()
    for preset in DifficultyPreset:
        if preset.value == normalized or preset.name.lower() == normalized:
            return preset
    valid_values = ", ".join(preset.value for preset in DifficultyPreset)
    raise argparse.ArgumentTypeError(
        f"Unknown difficulty '{value}'. Use one of: {valid_values}."
    )


def classify_performance(average_fps: float) -> str:
    if average_fps >= 90.0:
        return "excellent"
    if average_fps >= 60.0:
        return "very_good"
    if average_fps >= 45.0:
        return "good"
    if average_fps >= 30.0:
        return "fair"
    return "poor"


def build_scene(
    difficulty: "DifficultyPreset",
    starting_level: int,
):
    _ensure_project_root_on_path()
    from game.app import GameApp
    from game.scenes.playing import PlayingScene

    app = GameApp()
    scene = PlayingScene(
        app,
        app.level_manager,
        difficulty_preset=difficulty,
        starting_level=starting_level,
    )
    scene._begin_playing_state()
    return app, scene


def summarize_frames(frame_times: list[float]) -> dict[str, float]:
    if not frame_times:
        return {
            "average": 0.0,
            "minimum": 0.0,
            "maximum": 0.0,
        }

    average = sum(frame_times) / len(frame_times)
    return {
        "average": average * 1000.0,
        "minimum": min(frame_times) * 1000.0,
        "maximum": max(frame_times) * 1000.0,
    }


def summarize_memory(memory_samples: list[int]) -> dict[str, float]:
    if not memory_samples:
        return {
            "average": 0.0,
            "maximum": 0.0,
            "current": 0.0,
        }

    sample_count = len(memory_samples)
    return {
        "average": sum(memory_samples) / sample_count,
        "maximum": max(memory_samples),
        "current": memory_samples[-1],
    }


def run_benchmark(
    duration_seconds: float,
    warmup_seconds: float,
    difficulty: "DifficultyPreset",
    starting_level: int,
) -> dict[str, Any]:
    _prepare_pygame_runtime()
    _ensure_project_root_on_path()
    import pygame

    from game.core.config import config as Config

    app, scene = build_scene(difficulty, starting_level)

    frame_times: list[float] = []
    memory_samples: list[int] = []
    total_frames = 0

    tracemalloc.start()
    start_time = time.perf_counter()
    end_time = start_time + duration_seconds
    warmup_end = start_time + min(max(0.0, warmup_seconds), duration_seconds)

    try:
        while True:
            now = time.perf_counter()
            if now >= end_time:
                break

            frame_start = now
            pygame.event.pump()
            scene.update(1.0 / Config.FPS)
            scene.render(app.screen)
            pygame.display.flip()

            frame_elapsed = time.perf_counter() - frame_start
            total_frames += 1

            if time.perf_counter() >= warmup_end:
                frame_times.append(frame_elapsed)
                current_memory, _peak_memory = tracemalloc.get_traced_memory()
                memory_samples.append(int(current_memory))
    finally:
        tracemalloc.stop()
        pygame.quit()

    actual_duration = time.perf_counter() - start_time
    measured_duration = sum(frame_times)
    average_fps = len(frame_times) / measured_duration if measured_duration > 0 else 0.0
    frame_time_stats = summarize_frames(frame_times)
    memory_stats_bytes = summarize_memory(memory_samples)

    results = {
        "duration_seconds": round(actual_duration, 3),
        "total_frames": total_frames,
        "warmup_seconds": round(min(max(0.0, warmup_seconds), duration_seconds), 3),
        "difficulty": difficulty.value,
        "starting_level": starting_level,
        "fps": {
            "average": round(average_fps, 2),
            "minimum": round(
                1000.0 / frame_time_stats["maximum"]
                if frame_time_stats["maximum"] > 0
                else 0.0,
                2,
            ),
            "maximum": round(
                1000.0 / frame_time_stats["minimum"]
                if frame_time_stats["minimum"] > 0
                else 0.0,
                2,
            ),
        },
        "frame_time_ms": frame_time_stats,
        "memory_mb": {
            "average": round(memory_stats_bytes["average"] / (1024.0 * 1024.0), 2),
            "maximum": round(memory_stats_bytes["maximum"] / (1024.0 * 1024.0), 2),
            "current": round(memory_stats_bytes["current"] / (1024.0 * 1024.0), 2),
        },
        "performance_rating": classify_performance(average_fps),
    }
    return results


def write_json(output_path: str, data: dict[str, Any]) -> None:
    with open(output_path, "w", encoding="utf-8") as file_handle:
        json.dump(data, file_handle, indent=2, ensure_ascii=False)
