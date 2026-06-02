"""CoreImplosion — efeito de morte "Core Implosion" do Neon Sniper.

Cosmético puro (sem dano — difere do EMP do Cyber-Captor): o núcleo magenta
brilha e **colapsa para dentro**, puxando uma coroa de partículas em direção ao
centro antes de sumir. Inspirado no estado "dying" do `EyeLaser`, mas com
velocidade apontando para o centro em vez de espalhar para fora.

Interface duck-typed dos efeitos do EntityManager: `update(dt)`, `draw(surface)`,
`dead`. Não entra em grid de colisão nem na lista de inimigos — logo não conta
como hostil para a progressão de fase.
"""

from __future__ import annotations

import math
import random
from typing import List

import pygame

from . import city_glow
from . import city_palette as pal

DURATION: float = 0.55
RING_RADIUS: float = 46.0
PARTICLE_COUNT: int = 22


class _Particle:
    __slots__ = ("angle", "r0", "swirl", "size")

    def __init__(self, angle: float, r0: float, swirl: float, size: float) -> None:
        self.angle: float = angle
        self.r0: float = r0
        self.swirl: float = swirl
        self.size: float = size


class CoreImplosion:
    def __init__(self, cx: float, cy: float) -> None:
        self.cx: float = cx
        self.cy: float = cy
        self.t: float = 0.0
        self.dead: bool = False
        self.particles: List[_Particle] = [
            _Particle(
                angle=random.uniform(0.0, math.tau),
                r0=random.uniform(0.65 * RING_RADIUS, RING_RADIUS),
                swirl=random.uniform(1.5, 4.0) * random.choice((-1.0, 1.0)),
                size=random.uniform(2.0, 4.0),
            )
            for _ in range(PARTICLE_COUNT)
        ]

    @property
    def rect(self) -> pygame.Rect:
        r = int(RING_RADIUS)
        return pygame.Rect(int(self.cx) - r, int(self.cy) - r, r * 2, r * 2)

    def update(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self.t += dt
        if self.t >= DURATION:
            self.dead = True

    def _frac(self) -> float:
        return min(1.0, self.t / DURATION)

    def draw(self, surface: pygame.Surface) -> None:
        frac = self._frac()
        # Convergência acelerada para o centro (ease-in quadrático).
        converge = frac * frac
        cx, cy = self.cx, self.cy

        # Núcleo: cresce até ~40% e depois colapsa para 0 — o "flash" da implosão.
        if frac < 0.4:
            core_t = frac / 0.4
        else:
            core_t = 1.0 - (frac - 0.4) / 0.6
        core_r = int(6 + 26 * max(0.0, core_t))
        if core_r > 0:
            color = pal.lerp(pal.CYBER_MAGENTA, (255, 255, 255), core_t)
            glow = city_glow.get_glow(core_r, color)
            surface.blit(
                glow,
                (int(cx) - core_r, int(cy) - core_r),
                special_flags=pygame.BLEND_RGBA_ADD,
            )

        # Partículas convergindo para o centro.
        for p in self.particles:
            radius = p.r0 * (1.0 - converge)
            ang = p.angle + p.swirl * self.t
            px = int(cx + math.cos(ang) * radius)
            py = int(cy + math.sin(ang) * radius)
            size = max(1, int(p.size * (1.0 - frac)))
            pygame.draw.circle(surface, pal.CYBER_MAGENTA, (px, py), size)
