from __future__ import annotations

import math
import random

import pygame

from ..core import colors
from ..core.config import config as Config
from .meteor import Meteor


class RockGlider(Meteor):
    """Enemy swarm unit for mountain theme.

    Uses the Meteor contract (rect/dead/health/update/draw) so it plugs into
    existing systems without custom wiring, but visually/behaviorally represents
    gliding rock fragments carried by mountain winds.
    """

    def __init__(
        self,
        size: int | None = None,
        x: float | None = None,
        y: float | None = None,
        vx: float | None = None,
        vy: float | None = None,
    ):
        glider_size = size if size is not None else random.randint(10, 18)
        super().__init__(size=glider_size, x=x, y=y, vx=vx, vy=vy)

        # Swarm role: low HP, faster motion, no fragmentation.
        self.health = 14
        self._base_speed = random.uniform(170.0, 250.0)
        self._drift_amp = random.uniform(35.0, 65.0)
        self._drift_freq = random.uniform(1.8, 3.2)
        self._phase = random.uniform(0.0, math.tau)
        self._time = 0.0
        self._spawn_y = self.y

        # Keep visuals compact and readable.
        self.w = self.h = self.size * 2
        # RockGlider is mountain-only (side-scroll): always travel right -> left.
        self.vx = -self._base_speed if vx is None else -abs(vx)
        self.vy = 0.0 if vy is None else vy

    def update(self, dt: float, is_side_scroll: bool = False):
        self._time += dt

        # Side-scroll behavior is enforced intentionally for this enemy.
        self.x += self.vx * dt
        if self.vy != 0.0:
            self._spawn_y += self.vy * dt

        # Keep a predictable glide arc instead of accumulating drift.
        self.y = (
            self._spawn_y
            + math.sin(self._time * self._drift_freq + self._phase) * self._drift_amp
        )

        if self.x < -self.w or self.y < -self.h or self.y > Config.SCREEN_HEIGHT:
            self.dead = True

        self.rotation += self.rotation_speed * dt

    def draw(self, screen: pygame.Surface):
        cx = int(self.x + self.w * 0.5)
        cy = int(self.y + self.h * 0.5)

        rad = math.radians(self.rotation)
        cr = math.cos(rad)
        sr = math.sin(rad)

        # Compact glider silhouette (diamond + wing shards).
        core = [
            (0, -self.size),
            (self.size, 0),
            (0, self.size),
            (-self.size, 0),
        ]
        wings = [
            (-self.size * 2, -self.size // 2),
            (self.size * 2, -self.size // 2),
            (0, self.size // 3),
        ]

        def rotate(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
            rotated: list[tuple[int, int]] = []
            for px, py in points:
                rx = int(cx + px * cr - py * sr)
                ry = int(cy + px * sr + py * cr)
                rotated.append((rx, ry))
            return rotated

        rock = (92, 78, 64)
        shade = (70, 58, 48)
        highlight = (140, 120, 100)

        wing_pts = rotate(wings)
        core_pts = rotate(core)
        pygame.draw.polygon(screen, shade, wing_pts)
        pygame.draw.polygon(screen, rock, core_pts)
        pygame.draw.polygon(screen, colors.BLACK, core_pts, 1)
        pygame.draw.circle(screen, highlight, (cx, cy), max(2, self.size // 5))

    def can_split(self) -> bool:
        return False

    def get_points_value(self) -> int:
        return 14
