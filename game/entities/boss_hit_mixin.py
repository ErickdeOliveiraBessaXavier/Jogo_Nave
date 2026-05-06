from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..systems.hit_result import HitResult


class BossHitMixin:
    dead: bool

    def take_damage(self, _amount: int) -> None: ...

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
