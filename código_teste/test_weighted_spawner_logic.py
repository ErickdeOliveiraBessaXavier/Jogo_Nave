import os
import sys

# Permite importar pacote `game` quando rodando direto via pytest no workspace.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.core.levels import DifficultyConfig, LevelManager
from game.entities.meteor import Meteor
from game.entities.square_minion_boss import SquareMinionBoss
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

    base_weights = spawner.config.get_enemy_spawn_weights()
    if Meteor not in base_weights:
        raise AssertionError("Config de teste deveria incluir Meteor")

    # Simula repetição recente do mesmo tipo.
    spawner.recent_enemy_types.extend([Meteor, Meteor])
    dynamic = spawner._get_dynamic_enemy_weights(DummyEntityManager())

    expected = base_weights[Meteor] * (DifficultyConfig.WEIGHTED_REPEAT_PENALTY**2)
    assert Meteor in dynamic
    assert abs(dynamic[Meteor] - expected) < 1e-9


def test_weighted_spawn_filters_hard_capped_type() -> None:
    spawner = _make_spawner()

    spawner._count_enemies_by_type = lambda _em: {
        "meteor": DifficultyConfig.MAX_METEORS_ON_SCREEN,
        "alien": 0,
        "eye": 0,
        "square_minion": 0,
        "elemental_robot": 0,
        "stone_sentry": 0,
        "total": 1,
    }

    dynamic = spawner._get_dynamic_enemy_weights(DummyEntityManager())
    assert Meteor not in dynamic


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
