import os
import sys

# Permite importar pacote `game` quando rodando direto via pytest no workspace.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.core.world_config import (
    WorldTheme,
    get_world_for_level,
    get_world_for_level_by_id,
)


def test_world_mapping_keeps_fixed_worlds_until_level_45() -> None:
    world_45 = get_world_for_level(45)

    assert world_45.world_id == 4
    assert world_45.start_level == 36
    assert world_45.end_level == 45
    assert world_45.theme == WorldTheme.VOLCANIC


def test_procedural_sector_starts_at_level_46() -> None:
    world_46 = get_world_for_level(46)

    assert world_46.world_id == 5
    assert world_46.start_level == 46
    assert world_46.end_level == 55
    assert world_46.theme == WorldTheme.MOUNTAINS


def test_levels_50_and_51_stay_in_first_procedural_sector() -> None:
    world_50 = get_world_for_level(50)
    world_51 = get_world_for_level(51)

    assert world_50.world_id == 5
    assert world_50.start_level == 46
    assert world_50.end_level == 55
    assert world_50.theme == WorldTheme.MOUNTAINS

    assert world_51.world_id == 5
    assert world_51.start_level == 46
    assert world_51.end_level == 55
    assert world_51.theme == WorldTheme.MOUNTAINS


def test_level_60_maps_to_second_procedural_sector() -> None:
    world_60 = get_world_for_level(60)

    assert world_60.world_id == 6
    assert world_60.start_level == 56
    assert world_60.end_level == 65
    assert world_60.theme == WorldTheme.STARFIELD


def test_get_world_for_level_by_id_supports_procedural_ids() -> None:
    world_5 = get_world_for_level_by_id(5)
    world_6 = get_world_for_level_by_id(6)

    assert world_5 is not None
    assert world_5.world_id == 5
    assert world_5.start_level == 46
    assert world_5.end_level == 55
    assert world_5.theme == WorldTheme.MOUNTAINS

    assert world_6 is not None
    assert world_6.world_id == 6
    assert world_6.start_level == 56
    assert world_6.end_level == 65
    assert world_6.theme == WorldTheme.STARFIELD
