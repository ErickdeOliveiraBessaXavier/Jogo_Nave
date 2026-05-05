import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from ..systems.hit_result import HitResult


@dataclass
class _FireParticle:
    x: float
    y: float
    age: float = 0.0
    lifetime: float = 0.0
    base_size: float = 0.0
    rotation: float = 0.0
    rot_speed: float = 0.0

    def update(self, dt: float) -> None:
        self.age += dt
        self.rotation += self.rot_speed * dt

    @property
    def alive(self) -> bool:
        return self.age < self.lifetime

    @property
    def progress(self) -> float:
        return self.age / self.lifetime

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


class FireZone:
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
        self.x = x
        self.y = y
        self.radius = radius
        self.duration = duration
        self.timer = duration
        self.dead = False
        self.hit_cooldowns: dict[int, float] = {}
        self.anim_timer = 0.0
        self._spawn_timer = 0.0
        self._particles: list[_FireParticle] = []
        self._surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)

    @property
    def rect(self) -> pygame.Rect:
        r = self.radius
        return pygame.Rect(int(self.x) - r, int(self.y) - r, r * 2, r * 2)

    def update(self, dt: float) -> None:
        if self.dead:
            return
        self.timer -= dt
        self.anim_timer += dt
        if self.timer <= 0:
            self.dead = True
            return

        for eid in list(self.hit_cooldowns):
            self.hit_cooldowns[eid] -= dt
            if self.hit_cooldowns[eid] <= 0:
                del self.hit_cooldowns[eid]

        i = len(self._particles) - 1
        while i >= 0:
            p = self._particles[i]
            p.update(dt)
            if not p.alive:
                self._particles.pop(i)
            i -= 1

        self._spawn_timer += dt
        while self._spawn_timer >= self._SPAWN_INTERVAL:
            self._spawn_timer -= self._SPAWN_INTERVAL
            self._spawn_particle()

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

    def in_zone(self, cx: float, cy: float, r: float = 0.0) -> bool:
        return (cx - self.x) ** 2 + (cy - self.y) ** 2 < (self.radius + r) ** 2

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x, self.y, float(self.radius)

    def can_damage(self, entity_id: int) -> bool:
        return entity_id not in self.hit_cooldowns

    def register_hit(self, entity_id: int) -> None:
        self.hit_cooldowns[entity_id] = self.DAMAGE_INTERVAL

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

    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> "HitResult":
        from ..systems.hit_result import NO_HIT

        return NO_HIT

    def should_remove(self) -> bool:
        return self.dead
