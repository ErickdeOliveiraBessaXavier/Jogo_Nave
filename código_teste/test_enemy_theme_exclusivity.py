import os
import sys

# Permite importar pacote `game` quando rodando direto via pytest no workspace.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.core.levels import (
    ACTIVE_ENEMY_TUNING_PROFILE,
    DEFAULT_ENEMY_SPAWN_TIME,
    ENEMY_STAGE_WEIGHT_MULTIPLIERS,
    ENEMY_STAGE_WEIGHT_PROFILES,
    ENEMY_THEME_WEIGHT_MULTIPLIERS,
    ENEMY_THEME_WEIGHT_PROFILES,
    LevelConfig,
    _apply_theme_enemy_eligibility,
    _apply_theme_enemy_rules,
    _get_stage_band,
    _resolve_tuning_profile,
)
from game.core.world_config import get_world_for_level
from game.entities.alien import Alien
from game.entities.bot_elemental import ElementalRobot
from game.entities.eye_enemy import EyeEnemy
from game.entities.meteor import Meteor
from game.entities.rock_glider import RockGlider
from game.entities.stone_sentry import StoneSentry


def test_theme_exclusive_enemies_allowed_in_mountains() -> None:
    config = LevelConfig(
        level_number=1,
        enemy_spawn_config={
            StoneSentry: 1.0,
            ElementalRobot: 1.2,
            Meteor: 2.0,
        },
        enemies_to_clear=120,
    )

    mountains_world = get_world_for_level(1)
    adjusted = _apply_theme_enemy_eligibility(config, mountains_world)

    assert StoneSentry in adjusted.enemy_spawn_config
    assert ElementalRobot in adjusted.enemy_spawn_config
    assert Meteor not in adjusted.enemy_spawn_config
    assert RockGlider in adjusted.enemy_spawn_config


def test_theme_exclusive_enemies_removed_outside_mountains() -> None:
    config = LevelConfig(
        level_number=26,
        enemy_spawn_config={
            StoneSentry: 1.0,
            ElementalRobot: 1.2,
            Meteor: 2.0,
        },
        enemies_to_clear=120,
    )

    city_world = get_world_for_level(26)
    adjusted = _apply_theme_enemy_eligibility(config, city_world)

    assert StoneSentry not in adjusted.enemy_spawn_config
    assert ElementalRobot not in adjusted.enemy_spawn_config
    assert Meteor in adjusted.enemy_spawn_config


def test_starfield_keeps_meteor_and_excludes_rock_glider() -> None:
    config = LevelConfig(
        level_number=11,
        enemy_spawn_config={
            Meteor: 2.0,
            RockGlider: 1.8,
        },
        enemies_to_clear=120,
    )

    starfield_world = get_world_for_level(11)
    adjusted = _apply_theme_enemy_eligibility(config, starfield_world)

    assert Meteor in adjusted.enemy_spawn_config
    assert RockGlider not in adjusted.enemy_spawn_config


def test_theme_exclusive_filter_has_safe_fallback() -> None:
    config = LevelConfig(
        level_number=26,
        enemy_spawn_config={
            StoneSentry: 1.0,
            ElementalRobot: 1.2,
        },
        enemies_to_clear=120,
    )

    city_world = get_world_for_level(26)
    adjusted = _apply_theme_enemy_eligibility(config, city_world)

    assert adjusted.enemy_spawn_config
    assert StoneSentry not in adjusted.enemy_spawn_config
    assert ElementalRobot not in adjusted.enemy_spawn_config

    fallback_type, fallback_spawn = next(iter(adjusted.enemy_spawn_config.items()))
    assert fallback_type in {Alien, EyeEnemy, Meteor}
    assert fallback_spawn > 0


def test_theme_weight_multiplier_increases_mountains_exclusive_frequency() -> None:
    config = LevelConfig(
        level_number=1,
        enemy_spawn_config={
            StoneSentry: 2.0,
            Meteor: 2.0,
        },
        enemies_to_clear=120,
    )

    mountains_world = get_world_for_level(1)
    adjusted = _apply_theme_enemy_rules(config, mountains_world)
    stage_band = _get_stage_band(mountains_world, config.level_number)

    expected_stone = (
        2.0
        / ENEMY_THEME_WEIGHT_MULTIPLIERS[mountains_world.theme][StoneSentry]
        / ENEMY_STAGE_WEIGHT_MULTIPLIERS[mountains_world.theme][stage_band][StoneSentry]
    )
    expected_glider = (
        2.0
        / ENEMY_THEME_WEIGHT_MULTIPLIERS[mountains_world.theme][RockGlider]
        / ENEMY_STAGE_WEIGHT_MULTIPLIERS[mountains_world.theme][stage_band][RockGlider]
    )

    assert abs(adjusted.enemy_spawn_config[StoneSentry] - expected_stone) < 1e-9
    assert Meteor not in adjusted.enemy_spawn_config
    assert abs(adjusted.enemy_spawn_config[RockGlider] - expected_glider) < 1e-9


def test_theme_weight_multiplier_not_applied_when_enemy_removed_by_eligibility() -> (
    None
):
    config = LevelConfig(
        level_number=26,
        enemy_spawn_config={
            StoneSentry: 2.0,
            Meteor: 2.0,
        },
        enemies_to_clear=120,
    )

    city_world = get_world_for_level(26)
    adjusted = _apply_theme_enemy_rules(config, city_world)

    assert StoneSentry not in adjusted.enemy_spawn_config
    expected_meteor = 2.0  # CITY não define peso para Meteor
    assert abs(adjusted.enemy_spawn_config[Meteor] - expected_meteor) < 1e-9


def test_stage_band_mountains_increases_stone_sentry_late_game() -> None:
    base_spawn = 2.0
    early_world = get_world_for_level(1)
    late_world = get_world_for_level(9)

    early_config = LevelConfig(
        level_number=1,
        enemy_spawn_config={StoneSentry: base_spawn},
        enemies_to_clear=120,
    )
    late_config = LevelConfig(
        level_number=9,
        enemy_spawn_config={StoneSentry: base_spawn},
        enemies_to_clear=120,
    )

    adjusted_early = _apply_theme_enemy_rules(early_config, early_world)
    adjusted_late = _apply_theme_enemy_rules(late_config, late_world)

    early_theme = ENEMY_THEME_WEIGHT_MULTIPLIERS[early_world.theme][StoneSentry]
    late_theme = ENEMY_THEME_WEIGHT_MULTIPLIERS[late_world.theme][StoneSentry]
    assert early_theme == late_theme

    early_stage = ENEMY_STAGE_WEIGHT_MULTIPLIERS[early_world.theme]["early"][
        StoneSentry
    ]
    late_stage = ENEMY_STAGE_WEIGHT_MULTIPLIERS[late_world.theme]["late"][StoneSentry]

    expected_early = base_spawn / (early_theme * early_stage)
    expected_late = base_spawn / (late_theme * late_stage)

    assert abs(adjusted_early.enemy_spawn_config[StoneSentry] - expected_early) < 1e-9
    assert abs(adjusted_late.enemy_spawn_config[StoneSentry] - expected_late) < 1e-9
    assert (
        adjusted_late.enemy_spawn_config[StoneSentry]
        < adjusted_early.enemy_spawn_config[StoneSentry]
    )


def test_stage_band_city_progression_for_aliens() -> None:
    base_spawn = 2.0
    city_early_world = get_world_for_level(26)
    city_late_world = get_world_for_level(34)

    assert _get_stage_band(city_early_world, 26) == "early"
    assert _get_stage_band(city_late_world, 34) == "late"

    early_config = LevelConfig(
        level_number=26,
        enemy_spawn_config={Alien: base_spawn},
        enemies_to_clear=120,
    )
    late_config = LevelConfig(
        level_number=34,
        enemy_spawn_config={Alien: base_spawn},
        enemies_to_clear=120,
    )

    adjusted_early = _apply_theme_enemy_rules(early_config, city_early_world)
    adjusted_late = _apply_theme_enemy_rules(late_config, city_late_world)

    assert (
        adjusted_late.enemy_spawn_config[Alien]
        < adjusted_early.enemy_spawn_config[Alien]
    )


def test_tuning_profiles_have_expected_variants() -> None:
    expected = {"conservative", "moderate", "aggressive"}
    assert set(ENEMY_THEME_WEIGHT_PROFILES.keys()) == expected
    assert set(ENEMY_STAGE_WEIGHT_PROFILES.keys()) == expected


def test_active_tuning_profile_is_valid_and_safe() -> None:
    resolved = _resolve_tuning_profile(ACTIVE_ENEMY_TUNING_PROFILE)
    assert resolved in {"conservative", "moderate", "aggressive"}
    # Se profile inválido for configurado, resolve para moderate.
    assert _resolve_tuning_profile("invalid-profile") == "moderate"


def test_rock_glider_profile_ordering_in_mountains_is_monotonic() -> None:
    conservative_theme = ENEMY_THEME_WEIGHT_PROFILES["conservative"][
        get_world_for_level(1).theme
    ][RockGlider]
    moderate_theme = ENEMY_THEME_WEIGHT_PROFILES["moderate"][
        get_world_for_level(1).theme
    ][RockGlider]
    aggressive_theme = ENEMY_THEME_WEIGHT_PROFILES["aggressive"][
        get_world_for_level(1).theme
    ][RockGlider]

    assert conservative_theme < moderate_theme < aggressive_theme

    for stage_band in ("early", "mid", "late"):
        conservative_stage = ENEMY_STAGE_WEIGHT_PROFILES["conservative"][
            get_world_for_level(1).theme
        ][stage_band][RockGlider]
        moderate_stage = ENEMY_STAGE_WEIGHT_PROFILES["moderate"][
            get_world_for_level(1).theme
        ][stage_band][RockGlider]
        aggressive_stage = ENEMY_STAGE_WEIGHT_PROFILES["aggressive"][
            get_world_for_level(1).theme
        ][stage_band][RockGlider]
        assert conservative_stage < moderate_stage < aggressive_stage


def test_mountains_defaults_include_special_enemies() -> None:
    assert RockGlider in DEFAULT_ENEMY_SPAWN_TIME
    assert StoneSentry in DEFAULT_ENEMY_SPAWN_TIME
    assert ElementalRobot in DEFAULT_ENEMY_SPAWN_TIME

    assert DEFAULT_ENEMY_SPAWN_TIME[RockGlider] > 0
    assert DEFAULT_ENEMY_SPAWN_TIME[StoneSentry] > 0
    assert DEFAULT_ENEMY_SPAWN_TIME[ElementalRobot] > 0
