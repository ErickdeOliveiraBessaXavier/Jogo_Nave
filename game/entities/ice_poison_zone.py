import math
import random

import pygame

from .zone_base import ZoneBase, ZoneParticle


class _PlusParticle(ZoneParticle):
    @property
    def current_size(self) -> float:
        return self.base_size * min(1.0, self.progress * 2.5)

    @property
    def alpha(self) -> int:
        fade_in = min(1.0, self.progress * 4.0)
        fade_out = max(0.0, 1.0 - self.progress)
        return int(220 * fade_in * fade_out)


class IcePoisonZone(ZoneBase):
    SLOW_FACTOR = 0.4
    DAMAGE_INTERVAL = 0.2  # 1 dano a cada 0.2s = 5 HP/s

    _SPAWN_INTERVAL = 0.12
    _PARTICLE_LIFETIME_MIN = 0.7
    _PARTICLE_LIFETIME_MAX = 1.3
    _PLUS_COLOR = (160, 230, 255)
    _LINE_WIDTH = 3

    def __init__(self, x: float, y: float, radius: int, duration: float = 5.0):
        super().__init__(x, y, radius, duration)
        self._particles: list[_PlusParticle] = []
        self._surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)

    def _spawn_particle(self) -> None:
        angle = random.uniform(0.0, math.tau)
        dist = self.radius * 0.85 * math.sqrt(random.random())
        px = self.x + math.cos(angle) * dist
        py = self.y + math.sin(angle) * dist
        self._particles.append(
            _PlusParticle(
                x=px,
                y=py,
                lifetime=random.uniform(
                    self._PARTICLE_LIFETIME_MIN, self._PARTICLE_LIFETIME_MAX
                ),
                base_size=random.uniform(self.radius * 0.06, self.radius * 0.14),
                rotation=random.uniform(0.0, math.tau),
                rot_speed=random.uniform(-2.5, 2.5),
            )
        )

    def draw(self, surface: pygame.Surface) -> None:
        progress = max(0.0, self.timer / self.duration)
        r = self.radius

        # Limpar a surface reutilizável e desenhar tudo nela
        s = self._surface
        s.fill((0, 0, 0, 0))

        # Fundo translúcido
        pygame.draw.circle(s, (30, 190, 210, int(40 * progress)), (r, r), r)
        pygame.draw.circle(s, (140, 230, 255, int(120 * progress)), (r, r), r, 2)

        # Partículas "+" — desenho direto sem surface por partícula
        cr = self._PLUS_COLOR
        lw = self._LINE_WIDTH
        ox = self.x - r  # offset mundo→local
        oy = self.y - r

        for p in self._particles:
            alpha = p.alpha
            if alpha <= 0:
                continue
            size = p.current_size
            if size < 1.0:
                continue

            color = (cr[0], cr[1], cr[2], alpha)
            lx = int(p.x - ox)
            ly = int(p.y - oy)
            cos_r = math.cos(p.rotation)
            sin_r = math.sin(p.rotation)
            ax = cos_r * size
            ay = sin_r * size
            bx = -sin_r * size
            by = cos_r * size

            pygame.draw.line(
                s, color, (int(lx - ax), int(ly - ay)), (int(lx + ax), int(ly + ay)), lw
            )
            pygame.draw.line(
                s, color, (int(lx - bx), int(ly - by)), (int(lx + bx), int(ly + by)), lw
            )

        surface.blit(s, (int(self.x) - r, int(self.y) - r))
