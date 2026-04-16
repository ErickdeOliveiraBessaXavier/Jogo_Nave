from typing import List

import pygame

from .rock_glider import RockGlider


class RockGliderPool:
    """Object pool para RockGliders, reduzindo alocacao repetida em enxames."""

    def __init__(
        self,
        initial_size: int = 24,
        max_size: int = 60,
        is_side_scroll: bool = False,
    ):
        if max_size < initial_size:
            raise ValueError("max_size must be greater than or equal to initial_size")

        self.initial_size = initial_size
        self.max_size = max_size
        self.is_side_scroll = is_side_scroll

        self.pool: List[RockGlider] = []
        self.active: List[RockGlider] = []

        self.peak_active = 0
        self.total_created = 0
        self.reused_count = 0

        for _ in range(initial_size):
            glider = RockGlider()
            glider.active = False
            glider.dead = True
            self.pool.append(glider)
            self.total_created += 1

    def get(
        self,
        size: int | None = None,
        x: float | None = None,
        y: float | None = None,
        vx: float | None = None,
        vy: float | None = None,
    ) -> RockGlider:
        for glider in self.pool:
            if not glider.active:
                glider.reset(size=size, x=x, y=y, vx=vx, vy=vy)
                self.active.append(glider)
                self.reused_count += 1
                self._update_peak()
                return glider

        if len(self.pool) < self.max_size:
            glider = RockGlider(size=size, x=x, y=y, vx=vx, vy=vy)
            self.pool.append(glider)
            self.active.append(glider)
            self.total_created += 1
            self._update_peak()
            return glider

        if self.active:
            glider = self.active.pop(0)
            glider.reset(size=size, x=x, y=y, vx=vx, vy=vy)
            self.active.append(glider)
            self._update_peak()
            return glider

        return RockGlider(size=size, x=x, y=y, vx=vx, vy=vy)

    def release(self, glider: RockGlider) -> None:
        if glider in self.active:
            glider.active = False
            glider.dead = True
            self.active.remove(glider)

    def update(self, dt: float, is_side_scroll: bool | None = None) -> None:
        if is_side_scroll is not None:
            self.is_side_scroll = is_side_scroll

        for glider in self.active[:]:
            glider.update(dt, self.is_side_scroll)
            if glider.dead:
                self.release(glider)

    def draw(self, screen: pygame.Surface) -> None:
        for glider in self.active:
            glider.draw(screen)

    def clear_active(self) -> None:
        for glider in self.active[:]:
            self.release(glider)

    def get_active_count(self) -> int:
        return len(self.active)

    def get_pool_size(self) -> int:
        return len(self.pool)

    def _update_peak(self) -> None:
        self.peak_active = max(self.peak_active, len(self.active))

    def get_stats(self) -> dict[str, int | float]:
        total = max(1, self.total_created)
        return {
            "active": len(self.active),
            "inactive": len(self.pool) - len(self.active),
            "pool_total": len(self.pool),
            "peak_active": self.peak_active,
            "max_size": self.max_size,
            "total_created": self.total_created,
            "reused": self.reused_count,
            "efficiency_percent": (self.reused_count / total) * 100,
        }
