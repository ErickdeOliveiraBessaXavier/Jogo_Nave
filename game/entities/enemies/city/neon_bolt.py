"""NeonBolt — projétil neon viajante do bioma CITY (projétil compartilhado).

Bolt neon que **viaja** (esquivável após o disparo, diferente de um feixe
hitscan), com núcleo brilhante e halo aditivo. Interface duck-typed igual aos
demais projéteis inimigos (`AlienBullet`, `SerpentRockBullet`): `rect`,
`update(dt)`, `draw(surface)`, `dead` — flui pelos mesmos `enemy_projectile_grid`
e colisão genérica (`enemy_projectiles_vs_ship`) sem fiação nova.

Cor/tamanho são **parametrizáveis por instância** (defaults = bolt magenta do
Neon Sniper). Assim outros inimigos do tema reusam o mesmo projétil/fiação com
identidade própria — ex.: o `CyberTank` dispara "plasma" laranja maior e mais
lento pelas torres.
"""

from __future__ import annotations

import math
import random

import pygame

from ....core.config import config as Config
from . import city_glow
from . import city_palette as pal

# Defaults: núcleo claro com halo magenta — coeso com o chassi do Sniper.
_CORE: pal.RGB = (255, 230, 255)
_GLOW: pal.RGB = pal.CYBER_MAGENTA
RADIUS: int = 4
GLOW_RADIUS: int = 11


class NeonBolt:
    def __init__(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        core: pal.RGB = _CORE,
        glow: pal.RGB = _GLOW,
        radius: int = RADIUS,
        glow_radius: int = GLOW_RADIUS,
        pulse: bool = False,
    ) -> None:
        self.x: float = x
        self.y: float = y
        self.vx: float = vx
        self.vy: float = vy
        self.dead: bool = False
        self.core: pal.RGB = core
        self.glow: pal.RGB = glow
        self.radius: int = radius
        self.glow_radius: int = glow_radius
        # Pulso opt-in (energia "em movimento"): off por padrão → bolts da City
        # inalterados. Fase própria avançada no update (draw só lê — §3).
        self.pulse: bool = pulse
        self._pulse_t: float = random.uniform(0.0, math.tau) if pulse else 0.0
        # Cauda curta para leitura do movimento (posição anterior, atualizada no update).
        self.trail_x: float = x
        self.trail_y: float = y

    @property
    def rect(self) -> pygame.Rect:
        r = self.radius
        return pygame.Rect(int(self.x) - r, int(self.y) - r, r * 2, r * 2)

    def update(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self.trail_x = self.x
        self.trail_y = self.y
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.pulse:
            self._pulse_t += dt

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
        gr = self.glow_radius
        core_r = self.radius
        core_col = self.core
        if self.pulse:
            # Pulsação: halo/núcleo respiram e o núcleo cintila em direção ao
            # branco — "esfera de energia" viva em vez de disco estático.
            s = math.sin(self._pulse_t * 9.0)
            gr = max(1, int(self.glow_radius * (1.0 + 0.16 * s)))
            core_r = max(1, int(self.radius * (1.0 + 0.22 * s)))
            k = 0.30 * (0.5 + 0.5 * s)
            core_col = (
                min(255, int(self.core[0] + (255 - self.core[0]) * k)),
                min(255, int(self.core[1] + (255 - self.core[1]) * k)),
                min(255, int(self.core[2] + (255 - self.core[2]) * k)),
            )
        # Halo aditivo (reusa o cache de glow do bioma — §7).
        glow = city_glow.get_glow(gr, self.glow)
        surface.blit(
            glow,
            (cx - gr, cy - gr),
            special_flags=pygame.BLEND_RGBA_ADD,
        )
        # Trilha: linha curta da posição anterior ao núcleo.
        pygame.draw.line(
            surface, self.glow, (int(self.trail_x), int(self.trail_y)), (cx, cy), 2
        )
        # Núcleo brilhante.
        pygame.draw.circle(surface, core_col, (cx, cy), core_r)
