import math
import random
from typing import TYPE_CHECKING, Protocol, Sequence

import pygame

from .._shared.zone_base import ZoneBase, ZoneParticle

if TYPE_CHECKING:
    from ...systems.hit_result import HitResult


class Positionable(Protocol):
    """Protocolo para objetos que possuem coordenadas x e y."""

    x: float
    y: float


class _FireParticle(ZoneParticle):
    @property
    def current_size(self) -> float:
        # Cresce rápido e encolhe no final
        if self.progress < 0.2:
            return self.base_size * (self.progress / 0.2)
        return self.base_size * (1.0 - (self.progress - 0.2) / 0.8)

    @property
    def alpha(self) -> int:
        fade_out = max(0.0, 1.0 - self.progress)
        return int(255 * fade_out)


class FireZone(ZoneBase):
    DAMAGE_INTERVAL = 0.15  # Mais rápido que gelo (aprox 6.6 HP/s)

    _SPAWN_INTERVAL = 0.08
    _PARTICLE_LIFETIME_MIN = 0.5
    _PARTICLE_LIFETIME_MAX = 1.0
    _FIRE_COLORS = [
        (255, 60, 0),  # Vermelho fogo
        (255, 150, 0),  # Laranja
        (255, 220, 50),  # Amarelo
    ]
    _LINE_WIDTH = 4

    def __init__(self, x: float, y: float, radius: int, duration: float = 5.0):
        super().__init__(x, y, radius, duration)
        self._particles: list[_FireParticle] = []
        self._surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)

    @property
    def rect(self) -> pygame.Rect:
        r = self.radius
        return pygame.Rect(int(self.x) - r, int(self.y) - r, r * 2, r * 2)

    def _spawn_particle(self) -> None:
        angle = random.uniform(0.0, math.tau)
        dist = self.radius * 0.9 * math.sqrt(random.random())
        px = self.x + math.cos(angle) * dist
        py = self.y + math.sin(angle) * dist
        self._particles.append(
            _FireParticle(
                x=px,
                y=py,
                lifetime=random.uniform(
                    self._PARTICLE_LIFETIME_MIN, self._PARTICLE_LIFETIME_MAX
                ),
                base_size=random.uniform(self.radius * 0.1, self.radius * 0.25),
                rotation=random.uniform(0.0, math.tau),
                rot_speed=random.uniform(-4.0, 4.0),
            )
        )

    @staticmethod
    def is_position_safe(
        x: float,
        y: float,
        radius: float,
        entities: Sequence[Positionable],
        min_dist_mult: float = 2.2,
    ) -> bool:
        """Verifica se a posição (x, y) está a uma distância segura de outras entidades (que tenham x, y)."""
        min_dist = radius * min_dist_mult
        for ent in entities:
            if math.hypot(x - ent.x, y - ent.y) < min_dist:
                return False
        return True

    def draw(self, surface: pygame.Surface) -> None:
        progress = max(0.0, self.timer / self.duration)
        r = self.radius

        s = self._surface
        s.fill((0, 0, 0, 0))

        # Fundo quente
        pygame.draw.circle(s, (255, 60, 0, int(30 * progress)), (r, r), r)
        pygame.draw.circle(s, (255, 140, 0, int(100 * progress)), (r, r), r, 3)

        ox = self.x - r
        oy = self.y - r

        for p in self._particles:
            alpha = p.alpha
            if alpha <= 0:
                continue
            size = p.current_size
            if size < 1.0:
                continue

            color_base = random.choice(self._FIRE_COLORS)
            color = (*color_base, alpha)
            lx = int(p.x - ox)
            ly = int(p.y - oy)

            # Desenha faíscas/chamas como pequenos polígonos ou linhas grossas
            points: list[tuple[float, float]] = []
            for i in range(3):
                ang = p.rotation + i * (math.tau / 3)
                points.append((lx + math.cos(ang) * size, ly + math.sin(ang) * size))
            pygame.draw.polygon(s, color, points)

        surface.blit(s, (int(self.x) - r, int(self.y) - r))

    def on_hit(self, _damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ...systems.hit_result import NO_HIT

        return NO_HIT

    def should_remove(self) -> bool:
        return self.dead
