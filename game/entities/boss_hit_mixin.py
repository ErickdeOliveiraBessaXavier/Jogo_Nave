from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from ..systems.hit_result import HitResult


class BossHitMixin:
    dead: bool
    is_boss: bool = True

    @property
    def rect(self) -> pygame.Rect:
        raise NotImplementedError

    def take_damage(self, _amount: int) -> None: ...

    def collision_circle(self) -> tuple[float, float, float]:
        """Fallback baseado em rect — bosses com geometria custom devem override.

        Sem isso, sistemas que iteram todos os candidates (chain_shot, AoE)
        e topam com um boss sem implementação explícita quebram silenciosamente.
        """
        r = self.rect
        return float(r.centerx), float(r.centery), float(max(r.width, r.height) / 2)

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ..core.config import config as cfg
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=cfg.BOSS_DEFEAT_SCORE,
                explosion_size=100,
                sound=hit_sounds.EXPLOSION_BOSS,
            )
        return HitResult(explosion_size=15, sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool:
        return self.dead
