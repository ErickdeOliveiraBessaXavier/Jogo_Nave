"""Protocols estruturais para o sistema de colisão.

Contratos que substituem cascatas de isinstance em collisions.py. As
entidades implementam estes métodos; o sistema de colisão apenas chama e
materializa o HitResult retornado.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

import pygame

if TYPE_CHECKING:
    from .hit_result import HitResult


@runtime_checkable
class CollisionGeometry(Protocol):
    """Contrato para extrair geometria circular de colisão."""

    @property
    def rect(self) -> pygame.Rect: ...

    def collision_circle(self) -> tuple[float, float, float]:
        """Retorna (center_x, center_y, radius) para checks de área."""
        ...


@runtime_checkable
class Damageable(Protocol):
    """Contrato para entidades que recebem dano de projéteis ou área.

    `on_hit` decide o que acontece: morre? perde HP? explode em fragmentos?
    O sistema apenas executa o HitResult retornado.
    """

    dead: bool

    @property
    def rect(self) -> pygame.Rect: ...

    def collision_circle(self) -> tuple[float, float, float]: ...

    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> "HitResult": ...


@runtime_checkable
class ShipDamageable(Protocol):
    """Contrato para morte por contato com a nave.

    Semântica diferente de on_hit: dano máximo, sem score, som específico
    de impacto.
    """

    dead: bool

    @property
    def rect(self) -> pygame.Rect: ...

    def on_ship_contact(self, contact_x: float, contact_y: float) -> "HitResult": ...


@runtime_checkable
class Removable(Protocol):
    """Contrato para cleanup customizado no EntityManager."""

    def should_remove(self) -> bool: ...
