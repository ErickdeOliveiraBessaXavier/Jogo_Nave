import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Permite importar pacote `game` quando rodando direto via pytest no workspace.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.core.meta_progression import PlayerProfile, SessionStats


def test_new_profile_without_file_initializes_world_1_unlocked(tmp_path: Path) -> None:
    profile_path = tmp_path / "new_profile.json"

    profile = PlayerProfile(profile_path)

    assert profile.current_checkpoint_world == 1
    assert 1 in profile.world_unlocks
    assert profile.world_unlocks[1].is_unlocked is True
    assert profile.world_unlocks[1].checkpoint_set is True


def test_invalid_checkpoint_world_in_file_falls_back_to_world_1(tmp_path: Path) -> None:
    profile_path = tmp_path / "corrupt_checkpoint_profile.json"
    profile_payload = {
        "version": "1.0",
        "level_stats": {},
        "world_unlocks": {
            "1": {
                "is_unlocked": True,
                "first_accessed_at": None,
                "last_best_score_at_checkpoint": 0,
                "checkpoint_set": True,
            }
        },
        "current_checkpoint_world": 999,
    }
    profile_path.write_text(
        json.dumps(profile_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    profile = PlayerProfile(profile_path)

    assert profile.current_checkpoint_world == 1


def test_reset_to_checkpoint_supports_procedural_world_id(tmp_path: Path) -> None:
    profile_path = tmp_path / "procedural_checkpoint_profile.json"

    profile = PlayerProfile(profile_path)
    profile.current_checkpoint_world = 5  # Setor procedural inicial (46-55)
    profile.current_session = SessionStats(start_time=datetime.now(), score=1234)

    next_level = profile.reset_to_checkpoint()

    assert next_level == 46
    assert profile.current_session.score == 0
    assert profile.current_session.deaths == 1


def test_world_unlocks_with_invalid_type_falls_back_to_world_1(tmp_path: Path) -> None:
    profile_path = tmp_path / "invalid_world_unlocks_type.json"
    profile_payload = {
        "version": "1.0",
        "level_stats": {},
        "world_unlocks": ["bad", "shape"],
        "current_checkpoint_world": 1,
    }
    profile_path.write_text(
        json.dumps(profile_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    profile = PlayerProfile(profile_path)

    assert profile.current_checkpoint_world == 1
    assert 1 in profile.world_unlocks
    assert profile.world_unlocks[1].is_unlocked is True


def test_non_numeric_checkpoint_in_file_falls_back_to_world_1(tmp_path: Path) -> None:
    profile_path = tmp_path / "invalid_checkpoint_type.json"
    profile_payload = {
        "version": "1.0",
        "level_stats": {},
        "world_unlocks": {
            "1": {
                "is_unlocked": True,
                "first_accessed_at": None,
                "last_best_score_at_checkpoint": 0,
                "checkpoint_set": True,
            }
        },
        "current_checkpoint_world": "abc",
    }
    profile_path.write_text(
        json.dumps(profile_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    profile = PlayerProfile(profile_path)

    assert profile.current_checkpoint_world == 1


def test_invalid_json_file_keeps_safe_world_defaults(tmp_path: Path) -> None:
    profile_path = tmp_path / "invalid_json_profile.json"
    profile_path.write_text("{ this is invalid json", encoding="utf-8")

    profile = PlayerProfile(profile_path)

    assert profile.current_checkpoint_world == 1
    assert 1 in profile.world_unlocks
    assert profile.world_unlocks[1].is_unlocked is True
