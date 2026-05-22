from abc import ABC, abstractmethod
from typing import Any, ClassVar
from dataclasses import dataclass


@dataclass
class ZoneParticle:
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
        return self.base_size

    @property
    def alpha(self) -> int:
        return 255


class ZoneBase(ABC):
    DAMAGE_INTERVAL: ClassVar[float]
    _SPAWN_INTERVAL: ClassVar[float]

    def __init__(self, x: float, y: float, radius: int, duration: float) -> None:
        self.x = x
        self.y = y
        self.radius = radius
        self.duration = duration
        self.timer = duration
        self.dead = False
        self.hit_cooldowns: dict[int, float] = {}
        self.anim_timer = 0.0
        self._spawn_timer = 0.0
        self._particles: list[Any] = []

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

    @abstractmethod
    def _spawn_particle(self) -> None: ...

    def in_zone(self, cx: float, cy: float, r: float = 0.0) -> bool:
        return (cx - self.x) ** 2 + (cy - self.y) ** 2 < (self.radius + r) ** 2

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x, self.y, float(self.radius)

    def can_damage(self, entity_id: int) -> bool:
        return entity_id not in self.hit_cooldowns

    def register_hit(self, entity_id: int) -> None:
        self.hit_cooldowns[entity_id] = self.DAMAGE_INTERVAL
