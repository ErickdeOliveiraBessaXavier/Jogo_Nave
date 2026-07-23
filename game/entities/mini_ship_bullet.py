from typing import Any, Optional

import pygame

from ..core import colors
from ..core.config import config as Config


class MiniShipBullet:
    def __init__(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        damage: int = Config.MINI_SHIP_BULLET_DAMAGE,
        piercing: bool = False,
        owner_ship: Optional[Any] = None,
        boss_damage_mult: float = 1.0,
    ):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.w = 4
        self.h = 4
        self.damage = damage
        self.dead = False
        self.piercing = piercing  # Now configurable
        # Cargas de perfuração limitada (ver `Bullet.pierce_remaining` e
        # `Collisions._process_projectile_hit`). O tiro de escolta não herda a
        # perfuração da nave — fica em 0 —, mas o atributo existe para que os
        # dois tipos de projétil tenham o mesmo contrato: o sistema de colisão
        # trata a família inteira sem distinguir quem é quem.
        self.pierce_remaining = 0
        # Multiplicador extra aplicado SÓ contra bosses (1.0 = sem efeito).
        # Usado pelo Wingman, que tem cadência alta e some várias unidades —
        # sem isso o DPS dele em boss fica desproporcional.
        self.boss_damage_mult = boss_damage_mult
        # Nave que controlou o mini ship/wingman que disparou — para
        # atribuição de kill ao Reverberador certo em coop.
        self.owner_ship: Optional[Any] = owner_ship

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float):
        self.x += self.vx * dt
        self.y += self.vy * dt
        if (
            self.y + self.h < 0
            or self.y > Config.SCREEN_HEIGHT
            or self.x + self.w < 0
            or self.x > Config.SCREEN_WIDTH
        ):
            self.dead = True

    def draw(self, surface: pygame.Surface):
        bullet_color: tuple[int, int, int] = colors.CYAN
        pygame.draw.rect(surface, bullet_color, self.rect)
