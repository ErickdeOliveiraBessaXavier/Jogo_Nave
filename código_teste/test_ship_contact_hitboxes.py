import os
import sys

import pygame

# Permite importar pacote `game` quando rodando direto via pytest no workspace.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.core.spatial_grid import SpatialGrid
from game.entities.rock_glider import RockGlider
from game.systems.collisions import Collisions


class _DummyShip:
    def __init__(self, x: int, y: int, w: int = 24, h: int = 24) -> None:
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.invuln = 0

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(self.x, self.y, self.w, self.h)


class _DummyEntityManager:
    def __init__(self) -> None:
        self.explosions: list[tuple[float, float, int]] = []

    def spawn_explosion(self, x: float, y: float, size: int = 30) -> None:
        self.explosions.append((x, y, size))


class _CustomHitboxEnemy:
    def __init__(self, visual_rect: pygame.Rect, contact_rect: pygame.Rect) -> None:
        self._visual_rect = visual_rect
        self._contact_rect = contact_rect
        self.dead = False
        self.causes_damage = True

    @property
    def rect(self) -> pygame.Rect:
        # Rect propositalmente longe para validar uso da hitbox custom.
        return self._visual_rect

    def get_ship_contact_hitboxes(self) -> tuple[pygame.Rect, ...]:
        return (self._contact_rect,)


def test_ship_vs_enemies_prefers_custom_contact_hitboxes() -> None:
    collisions = Collisions()
    ship = _DummyShip(100, 100, w=20, h=20)
    entity_manager = _DummyEntityManager()

    enemy = _CustomHitboxEnemy(
        visual_rect=pygame.Rect(125, 125, 40, 40),
        contact_rect=pygame.Rect(108, 108, 10, 10),
    )

    grid: SpatialGrid[_CustomHitboxEnemy] = SpatialGrid()
    grid.insert_from_rect(enemy)

    hit = collisions.ship_vs_enemies(ship, grid, entity_manager)

    assert hit is True
    assert enemy.dead is True
    assert len(entity_manager.explosions) == 1


def test_rock_glider_exposes_ship_contact_hitboxes() -> None:
    enemy = RockGlider(x=900.0, y=220.0, vx=120.0, vy=0.0)
    enemy._update_collision_regions()

    hitboxes = enemy.get_ship_contact_hitboxes()

    assert len(hitboxes) == 2
    assert enemy._rock_hit_rect in hitboxes
    assert enemy._bot_hit_rect in hitboxes


def test_rock_glider_rect_is_union_of_alive_parts() -> None:
    enemy = RockGlider(x=900.0, y=220.0, vx=120.0, vy=0.0)
    enemy._update_collision_regions()

    expected = enemy._rock_hit_rect.union(enemy._bot_hit_rect)

    assert enemy.rect == expected


def test_ship_collision_with_rock_glider_applies_part_damage() -> None:
    collisions = Collisions()
    enemy = RockGlider(x=260.0, y=180.0, vx=120.0, vy=0.0)
    enemy._update_collision_regions()

    ship = _DummyShip(
        enemy._rock_hit_rect.centerx - 8, enemy._rock_hit_rect.centery - 8, w=16, h=16
    )
    entity_manager = _DummyEntityManager()

    grid: SpatialGrid[RockGlider] = SpatialGrid()
    grid.insert_from_rect(enemy)

    initial_health = enemy.health
    initial_rock_hp = enemy._rock_hp
    initial_bot_hp = enemy._bot_hp

    hit = collisions.ship_vs_enemies(ship, grid, entity_manager)

    assert hit is True
    assert enemy.dead is False
    assert (enemy._rock_destroyed and not enemy._bot_destroyed) or (
        enemy._bot_destroyed and not enemy._rock_destroyed
    )
    assert enemy.health < initial_health
    assert (enemy._rock_hp < initial_rock_hp) or (enemy._bot_hp < initial_bot_hp)
    assert len(entity_manager.explosions) == 1


def test_invulnerable_ship_is_intangible_to_rock_glider_contact() -> None:
    collisions = Collisions()
    enemy = RockGlider(x=260.0, y=180.0, vx=120.0, vy=0.0)
    enemy._update_collision_regions()

    ship = _DummyShip(
        enemy._rock_hit_rect.centerx - 8,
        enemy._rock_hit_rect.centery - 8,
        w=16,
        h=16,
    )
    ship.invuln = 1000
    entity_manager = _DummyEntityManager()

    grid: SpatialGrid[RockGlider] = SpatialGrid()
    grid.insert_from_rect(enemy)

    initial_health = enemy.health
    initial_rock_hp = enemy._rock_hp
    initial_bot_hp = enemy._bot_hp

    hit = collisions.ship_vs_enemies(ship, grid, entity_manager)

    assert hit is False
    assert enemy.health == initial_health
    assert enemy._rock_hp == initial_rock_hp
    assert enemy._bot_hp == initial_bot_hp
    assert len(entity_manager.explosions) == 0
