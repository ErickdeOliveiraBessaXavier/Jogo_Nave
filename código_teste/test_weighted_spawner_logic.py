import os
import sys

# Permite importar pacote `game` quando rodando direto via pytest no workspace.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.core.levels import DifficultyConfig, LevelManager
from game.entities.bot_elemental import ElementalRobot
from game.entities.explosive_mine import ExplosiveMine
from game.entities.meteor import Meteor
from game.entities.mountain_geode import MountainGeode
from game.entities.square_minion_boss import SquareMinionBoss
from game.entities.stone_sentry import StoneSentry
from game.systems.spawner import EnemySpawner


class _DummyMeteor:
    def __init__(self) -> None:
        self.health = 1


class DummyMeteorPool:
    def get(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return _DummyMeteor()


class DummyEntityManager:
    def __init__(self) -> None:
        self.enemies = []
        self.formations = []


def _make_spawner() -> EnemySpawner:
    level_manager = LevelManager()
    meteor_pool = DummyMeteorPool()
    return EnemySpawner(level_manager=level_manager, meteor_pool=meteor_pool)


def test_weighted_spawn_penalizes_recent_repetition() -> None:
    spawner = _make_spawner()

    # Força cenário sem caps para analisar apenas a penalidade.
    spawner._count_enemies_by_type = lambda _em: {
        "meteor": 0,
        "alien": 0,
        "eye": 0,
        "square_minion": 0,
        "elemental_robot": 0,
        "stone_sentry": 0,
        "total": 0,
    }

    base_weights = spawner.level_config.get_enemy_spawn_weights()
    meteor_like_type = next(
        (enemy_type for enemy_type in base_weights if issubclass(enemy_type, Meteor)),
        None,
    )
    if meteor_like_type is None:
        raise AssertionError(
            "Config de teste deveria incluir algum tipo derivado de Meteor"
        )

    # Simula repetição recente do mesmo tipo.
    spawner.recent_enemy_types.extend([meteor_like_type, meteor_like_type])
    dynamic = spawner._get_dynamic_enemy_weights(DummyEntityManager())

    expected = base_weights[meteor_like_type] * (
        DifficultyConfig.WEIGHTED_REPEAT_PENALTY**2
    )
    assert meteor_like_type in dynamic
    assert abs(dynamic[meteor_like_type] - expected) < 1e-9


def test_weighted_spawn_filters_hard_capped_type() -> None:
    spawner = _make_spawner()
    meteor_like_type = next(
        (
            enemy_type
            for enemy_type in spawner.level_config.enemy_types
            if issubclass(enemy_type, Meteor)
        ),
        None,
    )
    if meteor_like_type is None:
        raise AssertionError(
            "Config de teste deveria incluir algum tipo derivado de Meteor"
        )

    spawner._count_enemies_by_type = lambda _em: {
        "meteor": 20,  # Simula cap de meteoros no novo sistema (começa em 20)
        "alien": 0,
        "eye": 0,
        "square_minion": 0,
        "elemental_robot": 0,
        "stone_sentry": 0,
        "total": 20,  # Total cap para NORMAL difficulty
    }

    dynamic = spawner._get_dynamic_enemy_weights(DummyEntityManager())
    assert meteor_like_type not in dynamic


def test_spawn_enemy_returns_false_when_square_minion_missing_player_target() -> None:
    spawner = _make_spawner()
    entity_manager = DummyEntityManager()

    did_spawn = spawner._spawn_enemy_of_type(
        SquareMinionBoss,
        entity_manager,
        player_x=None,
        player_y=None,
        is_side_scroll=False,
    )

    assert did_spawn is False
    assert len(entity_manager.enemies) == 0


def test_stone_sentry_min_spawn_gap_is_30_seconds() -> None:
    spawner = _make_spawner()
    gap = spawner._get_min_spawn_gap(StoneSentry)

    expected = (
        DifficultyConfig.MIN_SPAWN_GAP_BY_TYPE["stone_sentry"]
        * DifficultyConfig.DIFFICULTY_SPAWN_GAP_MULTIPLIER[spawner.difficulty_preset]
    )

    assert expected == 30.0
    assert abs(gap - expected) < 1e-9


def test_elemental_robot_respects_level_config_spawn_gap() -> None:
    spawner = _make_spawner()
    spawner.level_config.enemy_spawn_config[ElementalRobot] = 25.0

    gap = spawner._get_min_spawn_gap(ElementalRobot)
    expected = (
        25.0
        * DifficultyConfig.DIFFICULTY_SPAWN_GAP_MULTIPLIER[spawner.difficulty_preset]
    )

    assert abs(gap - expected) < 1e-9


def test_storm_levels_override_total_enemy_cap_to_30() -> None:
    spawner = _make_spawner()

    spawner.level_config.storm_kind = "meteor"
    assert spawner._get_current_enemy_cap() == 30

    spawner.level_config.storm_kind = "rock_glider"
    assert spawner._get_current_enemy_cap() == 30


def test_rock_glider_small_bias_only_in_rock_glider_storm() -> None:
    spawner = _make_spawner()

    spawner.level_config.storm_kind = None
    assert spawner._is_rock_glider_storm_level() is False

    spawner.level_config.storm_kind = "rock_glider"
    assert spawner._is_rock_glider_storm_level() is True


def test_mines_use_mountain_geode_in_cordilheiras() -> None:
    spawner = _make_spawner()
    spawner.current_level_number = 1

    assert spawner._get_theme_mine_type() is MountainGeode


def test_mines_use_explosive_mine_outside_cordilheiras() -> None:
    spawner = _make_spawner()
    spawner.current_level_number = 11

    assert spawner._get_theme_mine_type() is ExplosiveMine
