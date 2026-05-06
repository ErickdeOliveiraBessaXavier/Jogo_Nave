from abc import ABC, abstractmethod


class ZoneBase(ABC):
    DAMAGE_INTERVAL: float
    _SPAWN_INTERVAL: float

    # Subclass __init__ must set these before update() is called
    x: float
    y: float
    radius: int
    duration: float
    timer: float
    dead: bool
    hit_cooldowns: dict[int, float]
    anim_timer: float
    _spawn_timer: float
    _particles: list

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
