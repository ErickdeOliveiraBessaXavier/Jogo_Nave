from typing import List

import pygame

from .pool_stats_mixin import PoolStatsMixin
from .rock_glider import RockGlider


class RockGliderPool(PoolStatsMixin):
    """Object pool para RockGliders, reduzindo alocacao repetida em enxames."""

    def __init__(
        self,
        initial_size: int = 24,
        max_size: int = 60,
        is_side_scroll: bool = False,
        aggressiveness_multiplier: float = 1.0,
    ):
        if max_size < initial_size:
            raise ValueError("max_size must be greater than or equal to initial_size")

        self.initial_size = initial_size
        self.max_size = max_size
        self.is_side_scroll = is_side_scroll
        self.aggressiveness_multiplier = aggressiveness_multiplier

        self.pool: List[RockGlider] = []
        self.active: List[RockGlider] = []
        self.free: List[RockGlider] = []

        self.peak_active = 0
        self.total_created = 0
        self.reused_count = 0

        for _ in range(initial_size):
            glider = RockGlider()
            glider.active = False
            glider.dead = True
            self.pool.append(glider)
            self.free.append(glider)
            self.total_created += 1

    def get(
        self,
        size: int | None = None,
        x: float | None = None,
        y: float | None = None,
        vx: float | None = None,
        vy: float | None = None,
    ) -> RockGlider:
        mult = self.aggressiveness_multiplier
        if self.free:
            glider = self.free.pop()
            glider.reset(
                size=size, x=x, y=y, vx=vx, vy=vy,
                aggressiveness_multiplier=mult,
            )
            glider.active = True
            self.active.append(glider)
            self.reused_count += 1
            self._update_peak()
            return glider

        if len(self.pool) < self.max_size:
            glider = RockGlider(size=size, x=x, y=y, vx=vx, vy=vy)
            # RockGlider.__init__ não aceita aggressiveness; aplica via reset
            # imediato para passar pelo super().reset(...) com o multiplicador.
            glider.reset(
                size=size, x=x, y=y, vx=vx, vy=vy,
                aggressiveness_multiplier=mult,
            )
            glider.active = True
            self.pool.append(glider)
            self.active.append(glider)
            self.total_created += 1
            self._update_peak()
            return glider

        if self.active:
            glider = self.active.pop(0)
            glider.reset(
                size=size, x=x, y=y, vx=vx, vy=vy,
                aggressiveness_multiplier=mult,
            )
            glider.active = True
            self.active.append(glider)
            self._update_peak()
            return glider

        glider = RockGlider(size=size, x=x, y=y, vx=vx, vy=vy)
        glider.reset(
            size=size, x=x, y=y, vx=vx, vy=vy,
            aggressiveness_multiplier=mult,
        )
        return glider

    def release(self, glider: RockGlider) -> None:
        try:
            self.active.remove(glider)
        except ValueError:
            return
        glider.active = False
        glider.dead = True
        self.free.append(glider)

    def update(self, dt: float, is_side_scroll: bool | None = None) -> None:
        if is_side_scroll is not None:
            self.is_side_scroll = is_side_scroll

        write = 0
        active = self.active
        for glider in active:
            glider.update(dt, self.is_side_scroll)
            if glider.dead:
                glider.active = False
                self.free.append(glider)
            else:
                active[write] = glider
                write += 1
        del active[write:]

    def draw(self, screen: pygame.Surface) -> None:
        for glider in self.active:
            glider.draw(screen)

    def clear_active(self) -> None:
        for glider in self.active:
            glider.active = False
            glider.dead = True
            self.free.append(glider)
        self.active.clear()
