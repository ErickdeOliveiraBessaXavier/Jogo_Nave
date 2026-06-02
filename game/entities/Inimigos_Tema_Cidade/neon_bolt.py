"""NeonBolt — projétil mirado do Neon Sniper.

Bolt neon que **viaja** (esquivável após o disparo, diferente de um feixe
hitscan), com núcleo brilhante e halo aditivo. Interface duck-typed igual aos
demais projéteis inimigos (`AlienBullet`, `SerpentRockBullet`): `rect`,
`update(dt)`, `draw(surface)`, `dead` — flui pelos mesmos `enemy_projectile_grid`
e colisão genérica (`enemy_projectiles_vs_ship`) sem fiação nova.
"""

from __future__ import annotations

import pygame

from ...core.config import config as Config
from . import city_glow
from . import city_palette as pal

# Núcleo magenta com halo azul elétrico — coeso com o chassi do Sniper.
_CORE: pal.RGB = (255, 230, 255)
_GLOW: pal.RGB = pal.CYBER_MAGENTA
RADIUS: int = 4
GLOW_RADIUS: int = 11


class NeonBolt:
    def __init__(self, x: float, y: float, vx: float, vy: float) -> None:
        self.x: float = x
        self.y: float = y
        self.vx: float = vx
        self.vy: float = vy
        self.dead: bool = False
        # Cauda curta para leitura do movimento (posição anterior, atualizada no update).
        self.trail_x: float = x
        self.trail_y: float = y

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x) - RADIUS, int(self.y) - RADIUS, RADIUS * 2, RADIUS * 2)

    def update(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self.trail_x = self.x
        self.trail_y = self.y
        self.x += self.vx * dt
        self.y += self.vy * dt

        margin = 48
        if (
            self.x < -margin
            or self.x > Config.SCREEN_WIDTH + margin
            or self.y < -margin
            or self.y > Config.SCREEN_HEIGHT + margin
        ):
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x), int(self.y)
        # Halo aditivo (reusa o cache de glow do bioma — §7).
        glow = city_glow.get_glow(GLOW_RADIUS, _GLOW)
        surface.blit(
            glow,
            (cx - GLOW_RADIUS, cy - GLOW_RADIUS),
            special_flags=pygame.BLEND_RGBA_ADD,
        )
        # Trilha: linha curta da posição anterior ao núcleo.
        pygame.draw.line(
            surface, pal.CYBER_MAGENTA, (int(self.trail_x), int(self.trail_y)), (cx, cy), 2
        )
        # Núcleo brilhante.
        pygame.draw.circle(surface, _CORE, (cx, cy), RADIUS)
