import math
import random
from dataclasses import dataclass

import pygame


@dataclass
class _PlusParticle:
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
        # Cresce rápido no início, depois mantém
        grow = min(1.0, self.progress * 2.5)
        return self.base_size * grow

    @property
    def alpha(self) -> int:
        # Aparece e some suavemente
        fade_in = min(1.0, self.progress * 4.0)
        fade_out = max(0.0, 1.0 - self.progress)
        return int(220 * fade_in * fade_out)


class IcePoisonZone:
    SLOW_FACTOR = 0.4
    DAMAGE_INTERVAL = 0.2   # 1 dano a cada 0.2s = 5 HP/s

    _SPAWN_INTERVAL = 0.12
    _PARTICLE_LIFETIME_MIN = 0.7
    _PARTICLE_LIFETIME_MAX = 1.3
    _PLUS_COLOR = (160, 230, 255)
    _LINE_WIDTH = 3

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
        self._particles: list[_PlusParticle] = []

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

        for p in self._particles:
            p.update(dt)
        self._particles = [p for p in self._particles if p.alive]

        self._spawn_timer += dt
        while self._spawn_timer >= self._SPAWN_INTERVAL:
            self._spawn_timer -= self._SPAWN_INTERVAL
            self._spawn_particle()

    def _spawn_particle(self) -> None:
        # Posição aleatória dentro do raio
        angle = random.uniform(0.0, math.tau)
        dist = random.uniform(0.0, self.radius * 0.85)
        px = self.x + math.cos(angle) * dist
        py = self.y + math.sin(angle) * dist
        self._particles.append(
            _PlusParticle(
                x=px,
                y=py,
                lifetime=random.uniform(self._PARTICLE_LIFETIME_MIN, self._PARTICLE_LIFETIME_MAX),
                base_size=random.uniform(self.radius * 0.06, self.radius * 0.14),
                rotation=random.uniform(0.0, math.tau),
                rot_speed=random.uniform(-2.5, 2.5),
            )
        )

    def in_zone(self, cx: float, cy: float, r: float = 0.0) -> bool:
        return (cx - self.x) ** 2 + (cy - self.y) ** 2 < (self.radius + r) ** 2

    def can_damage(self, entity_id: int) -> bool:
        return entity_id not in self.hit_cooldowns

    def register_hit(self, entity_id: int) -> None:
        self.hit_cooldowns[entity_id] = self.DAMAGE_INTERVAL

    def draw(self, surface: pygame.Surface) -> None:
        progress = max(0.0, self.timer / self.duration)
        r = self.radius

        # Fundo translúcido
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        fill_alpha = int(40 * progress)
        pygame.draw.circle(s, (30, 190, 210, fill_alpha), (r, r), r)
        border_alpha = int(120 * progress)
        pygame.draw.circle(s, (140, 230, 255, border_alpha), (r, r), r, 2)
        surface.blit(s, (int(self.x) - r, int(self.y) - r))

        # Partículas "+"
        for p in self._particles:
            alpha = p.alpha
            if alpha <= 0:
                continue
            size = p.current_size
            if size < 1.0:
                continue

            color = (*self._PLUS_COLOR, alpha)
            cx = int(p.x)
            cy = int(p.y)
            cos_r = math.cos(p.rotation)
            sin_r = math.sin(p.rotation)

            # Braço horizontal do "+"
            ax = cos_r * size
            ay = sin_r * size
            # Braço vertical do "+"
            bx = -sin_r * size
            by = cos_r * size

            ps = pygame.Surface((int(size * 2 + 6), int(size * 2 + 6)), pygame.SRCALPHA)
            oc = (int(size) + 3, int(size) + 3)  # centro local na surface

            pygame.draw.line(
                ps, color,
                (int(oc[0] - ax), int(oc[1] - ay)),
                (int(oc[0] + ax), int(oc[1] + ay)),
                self._LINE_WIDTH,
            )
            pygame.draw.line(
                ps, color,
                (int(oc[0] - bx), int(oc[1] - by)),
                (int(oc[0] + bx), int(oc[1] + by)),
                self._LINE_WIDTH,
            )
            surface.blit(ps, (cx - oc[0], cy - oc[1]))
