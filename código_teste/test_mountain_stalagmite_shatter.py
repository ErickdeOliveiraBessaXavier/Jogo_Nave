import os
import sys

# Permite importar pacote `game` quando rodando direto via pytest no workspace.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.core.sound import sound_manager
from game.entities.mountain_mage import MountainStalagmite
from game.systems.collisions import Collisions
from game.systems.entity_manager import EntityManager


class _DummyMeteorPool:
    @staticmethod
    def get() -> None:
        return None


class _DummyEntityManager:
    def __init__(self) -> None:
        self.explosions: list[tuple[float, float, int, object]] = []
        self.meteor_pool = _DummyMeteorPool()

    def spawn_explosion(
        self,
        x: float,
        y: float,
        size: int = 30,
        explosion_type: object | None = None,
    ) -> None:
        self.explosions.append((x, y, size, explosion_type))


def test_stalagmite_fatal_hit_enters_shattering_instead_of_instant_dead(
    monkeypatch,
) -> None:
    monkeypatch.setattr(sound_manager, "play_boss_damage", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sound_manager, "play_explosion_asteroid", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        sound_manager, "play_explosion_alien", lambda *args, **kwargs: None
    )

    collisions = Collisions()
    entity_manager = _DummyEntityManager()
    stalagmite = MountainStalagmite(x=320.0, ground_y=721.0, target_y=560.0)
    stalagmite.health = 1

    points, score_event, killed = collisions._destroy_enemy(
        stalagmite,
        [stalagmite],
        entity_manager,
        hit_x=stalagmite.x,
        hit_y=stalagmite.ground_y,
    )

    assert killed is True
    assert points == stalagmite.get_points_value()
    assert score_event is not None
    assert stalagmite.dead is False
    assert stalagmite.health == 0
    assert stalagmite.active is False
    assert len(entity_manager.explosions) == 1

    # A entidade deve permanecer viva por alguns frames para animar os fragmentos.
    stalagmite.update(0.05)
    assert stalagmite.dead is False

    # Depois de tempo suficiente de shatter, ela finalmente é removida.
    for _ in range(40):
        stalagmite.update(0.05)

    assert stalagmite.dead is True


def test_dead_stalagmite_stays_loaded_while_fragments_are_active(monkeypatch) -> None:
    monkeypatch.setattr(sound_manager, "play_boss_damage", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sound_manager, "play_explosion_asteroid", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        sound_manager, "play_explosion_alien", lambda *args, **kwargs: None
    )

    manager = EntityManager(sound_manager=None)
    stalagmite = MountainStalagmite(x=320.0, ground_y=721.0, target_y=560.0)
    stalagmite._state = "shattering"
    stalagmite._spawn_fragments()
    stalagmite.dead = True
    manager.enemies.append(stalagmite)

    manager.cleanup()

    assert stalagmite in manager.enemies
