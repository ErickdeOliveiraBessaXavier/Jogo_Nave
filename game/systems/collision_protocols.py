"""Protocols estruturais para o sistema de colisão.

Contratos que substituem cascatas de isinstance em collisions.py. As
entidades implementam estes métodos; o sistema de colisão apenas chama e
materializa o HitResult retornado.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

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


@runtime_checkable
class Scoreable(Protocol):
    """Contrato para entidades que geram pontos ao serem destruídas."""

    def get_points_value(self) -> int: ...


@runtime_checkable
class Enemy(Protocol):
    """Contrato estrutural para inimigos comuns do jogo.

    **`position_locked` (class attribute, default `False`)** — o inimigo NÃO
    pode ser deslocado de fora. `x`/`y` aqui são só de leitura no protocolo, e
    algumas entidades levam isso a sério: `MountainStalagmite` e
    `MountainStalactite` derivam `y` da ancoragem no chão/teto com uma property
    sem setter, e o `rect` delas vem de um mask recalculado por frame — escrever
    `enemy.y += ...` estoura `AttributeError` e empurrar só o `rect`
    dessincronizaria colisão e desenho.

    Todo sistema que MOVE inimigos alheios (buraco negro, tremor da parada do
    tempo) consulta `getattr(en, "position_locked", False)` e pula (§5:
    class attribute, não `isinstance` nem `hasattr`). `hasattr(en, "y")` NÃO
    serve para isso — é verdadeiro para property somente-leitura.

    Não confundir com `pullable_by_black_hole`, que é imunidade específica
    daquele efeito (um boss é móvel, mas não é arrastado).
    """

    @property
    def x(self) -> float: ...

    @property
    def y(self) -> float: ...

    @property
    def rect(self) -> pygame.Rect: ...

    dead: bool
    health: int

    def collision_circle(self) -> tuple[float, float, float]: ...
    def get_points_value(self) -> int: ...
    def update(self, dt: float, *args: Any, **kwargs: Any) -> Any: ...
