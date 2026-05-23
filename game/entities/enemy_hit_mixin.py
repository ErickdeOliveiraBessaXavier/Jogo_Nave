from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from ..systems.hit_result import HitResult


class EnemyHitMixin:
    """Mixin para entidades inimigas comuns.
    Lida com colisão circular padrão (baseada em rect) e on_hit parametrizado.
    """

    dead: bool

    # Defaults
    _explosion_size_killed: int = 35
    _explosion_size_hit: int = 10

    @property
    def rect(self) -> pygame.Rect:
        raise NotImplementedError

    def take_damage(self, amount: int) -> None:
        raise NotImplementedError

    def get_points_value(self) -> int:
        raise NotImplementedError

    def collision_circle(self) -> tuple[float, float, float]:
        r = self.rect
        return r.centerx, r.centery, max(r.width, r.height) / 2

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=self._explosion_size_killed,
                sound=hit_sounds.EXPLOSION_ALIEN,
            )
        return HitResult(
            explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems.hit_result import HitResult

        return HitResult()  # default implementation can be empty or custom
