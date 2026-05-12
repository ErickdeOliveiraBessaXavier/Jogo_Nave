import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pygame

# Permite importar pacote `game` quando rodando direto via pytest no workspace.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.core.meta_progression import PlayerProfile, SessionStats
from game.core.upgrades_config import UPGRADE_SLOT_COUNT


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


def test_unlock_next_world_uses_explicit_world_id(tmp_path: Path) -> None:
    profile_path = tmp_path / "explicit_unlock_world_id.json"
    profile = PlayerProfile(profile_path)

    # Simula checkpoint já adiantado por outro fluxo, mas desbloqueio precisa seguir world_id informado.
    profile.current_checkpoint_world = 4

    profile.unlock_next_world(1)

    assert 2 in profile.world_unlocks
    assert profile.world_unlocks[2].is_unlocked is True
    assert profile.current_checkpoint_world == 2


def test_unlock_next_world_respects_max_named_world(tmp_path: Path) -> None:
    profile_path = tmp_path / "max_named_world_unlock.json"
    profile = PlayerProfile(profile_path)

    profile.current_checkpoint_world = 4
    existing_world_unlocks = set(profile.world_unlocks.keys())

    profile.unlock_next_world(4)

    # Não deve desbloquear além do mundo 4 nomeado.
    assert set(profile.world_unlocks.keys()) == existing_world_unlocks
    assert profile.current_checkpoint_world == 4


def test_upgrade_keybindings_load_independently_from_upgrades(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile_with_custom_keybindings.json"
    defaults_all = [
        pygame.K_1,
        pygame.K_2,
        pygame.K_3,
        pygame.K_4,
        pygame.K_5,
        pygame.K_6,
        pygame.K_7,
        pygame.K_8,
        pygame.K_9,
        pygame.K_0,
        pygame.K_MINUS,
        pygame.K_EQUALS,
    ]
    custom_keys = [
        pygame.K_q,
        pygame.K_w,
        pygame.K_e,
        pygame.K_r,
        pygame.K_t,
        pygame.K_y,
        pygame.K_u,
        pygame.K_i,
        pygame.K_o,
        pygame.K_p,
        pygame.K_a,
        pygame.K_s,
    ][:UPGRADE_SLOT_COUNT]

    profile_payload = {
        "version": "1.0",
        "level_stats": {},
        "unlocked_upgrades": [],
        "upgrade_loadout": [None] * UPGRADE_SLOT_COUNT,
        "upgrade_keybindings": custom_keys,
        "world_unlocks": {
            "1": {
                "is_unlocked": True,
                "first_accessed_at": None,
                "last_best_score_at_checkpoint": 0,
                "checkpoint_set": True,
            }
        },
        "current_checkpoint_world": 1,
    }
    profile_path.write_text(
        json.dumps(profile_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    profile = PlayerProfile(profile_path)

    assert profile.upgrade_keybindings == custom_keys
    assert profile.upgrade_keybindings != defaults_all[:UPGRADE_SLOT_COUNT]
