import random
from typing import Any, Final

import pygame

from ..core import colors
from ..core.config import config as Config


class MountainSerpentBoss:
    """Boss serpente de pedra exclusivo das Cordilheiras."""

    HEAD_RADIUS: Final[int] = 30
    SEGMENT_RADIUS: Final[int] = 24
    SEGMENT_COUNT: Final[int] = 5
    SIDE_MARGIN: Final[int] = 52
    SIDE_GAP_Y: Final[int] = 82
    HEAD_Y: Final[int] = 88
    HEAD_SPEED: Final[float] = 24.0

    def __init__(
        self,
        x: float | None = None,
        y: float | None = None,
        health: int | None = None,
    ) -> None:
        self.head_x: float = float(x if x is not None else Config.SCREEN_WIDTH / 2)
        self.head_y: float = float(y if y is not None else self.HEAD_Y)
        self.direction: int = random.choice((-1, 1))
        self.speed: float = self.HEAD_SPEED
        self.hit_flash: float = 0.0

        self.left_x: float = float(self.SIDE_MARGIN)
        self.right_x: float = float(Config.SCREEN_WIDTH - self.SIDE_MARGIN)
        self.segment_ys: list[float] = [
            float(self.head_y + 80 + i * self.SIDE_GAP_Y)
            for i in range(self.SEGMENT_COUNT)
        ]

        self.health: int = health if health is not None else 320
        self.max_health: int = self.health
        self.dead: bool = False
        self.floating_squares: list[Any] = []

        self._recalc_bounds()

    def _recalc_bounds(self) -> None:
        top = int(self.head_y - self.HEAD_RADIUS)
        bottom = int(self.segment_ys[-1] + self.SEGMENT_RADIUS)
        left = int(self.left_x - self.SEGMENT_RADIUS)
        right = int(self.right_x + self.SEGMENT_RADIUS)

        self.x = float(left)
        self.y = float(top)
        self.w = max(1, right - left)
        self.h = max(1, bottom - top)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def get_points_value(self) -> int:
        return 850

    def get_ship_contact_hitboxes(self) -> tuple[pygame.Rect, ...]:
        if self.dead:
            return ()

        hitboxes: list[pygame.Rect] = []
        head_rect = pygame.Rect(
            int(self.head_x - self.HEAD_RADIUS),
            int(self.head_y - self.HEAD_RADIUS),
            self.HEAD_RADIUS * 2,
            self.HEAD_RADIUS * 2,
        )
        hitboxes.append(head_rect)

        for y in self.segment_ys:
            hitboxes.append(
                pygame.Rect(
                    int(self.left_x - self.SEGMENT_RADIUS),
                    int(y - self.SEGMENT_RADIUS),
                    self.SEGMENT_RADIUS * 2,
                    self.SEGMENT_RADIUS * 2,
                )
            )
            hitboxes.append(
                pygame.Rect(
                    int(self.right_x - self.SEGMENT_RADIUS),
                    int(y - self.SEGMENT_RADIUS),
                    self.SEGMENT_RADIUS * 2,
                    self.SEGMENT_RADIUS * 2,
                )
            )

        return tuple(hitboxes)

    def take_damage(self, amount: int) -> None:
        if self.dead:
            return
        self.health -= amount
        self.hit_flash = 0.2
        if self.health <= 0:
            self.health = 0
            self.dead = True

    def update(
        self, dt: float, player_x: float, player_y: float
    ) -> tuple[list[Any], list[Any]]:
        if self.dead:
            return [], []

        self.hit_flash = max(0.0, self.hit_flash - dt)
        self.head_x += self.direction * self.speed * dt

        if self.head_x <= self.left_x + self.HEAD_RADIUS:
            self.head_x = self.left_x + self.HEAD_RADIUS
            self.direction = 1
        elif self.head_x >= self.right_x - self.HEAD_RADIUS:
            self.head_x = self.right_x - self.HEAD_RADIUS
            self.direction = -1

        self._recalc_bounds()
        return [], []

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        body_color = (106, 76, 125)
        edge_color = (42, 24, 55)
        highlight_color = (224, 126, 116)
        glow_color = (255, 205, 125)

        if self.hit_flash > 0.0:
            body_color = tuple(
                min(255, int(c + (255 - c) * self.hit_flash)) for c in body_color
            )

        # Desenhar laterais
        for y in self.segment_ys:
            pygame.draw.circle(
                surface,
                edge_color,
                (int(self.left_x), int(y)),
                self.SEGMENT_RADIUS + 3,
            )
            pygame.draw.circle(
                surface, body_color, (int(self.left_x), int(y)), self.SEGMENT_RADIUS
            )
            pygame.draw.circle(
                surface,
                highlight_color,
                (int(self.left_x), int(y)),
                self.SEGMENT_RADIUS // 2,
            )

            pygame.draw.circle(
                surface,
                edge_color,
                (int(self.right_x), int(y)),
                self.SEGMENT_RADIUS + 3,
            )
            pygame.draw.circle(
                surface, body_color, (int(self.right_x), int(y)), self.SEGMENT_RADIUS
            )
            pygame.draw.circle(
                surface,
                highlight_color,
                (int(self.right_x), int(y)),
                self.SEGMENT_RADIUS // 2,
            )

        # Desenhar cabeça
        head_center = (int(self.head_x), int(self.head_y))
        pygame.draw.circle(surface, edge_color, head_center, self.HEAD_RADIUS + 4)
        pygame.draw.circle(surface, body_color, head_center, self.HEAD_RADIUS)
        pygame.draw.circle(surface, glow_color, head_center, self.HEAD_RADIUS // 2)

        # Olhos
        pygame.draw.circle(
            surface,
            colors.YELLOW,
            (int(self.head_x - 10), int(self.head_y - 6)),
            5,
        )
        pygame.draw.circle(
            surface,
            colors.YELLOW,
            (int(self.head_x + 10), int(self.head_y - 6)),
            5,
        )
        pygame.draw.circle(
            surface,
            colors.BLACK,
            (int(self.head_x - 10), int(self.head_y - 6)),
            2,
        )
        pygame.draw.circle(
            surface,
            colors.BLACK,
            (int(self.head_x + 10), int(self.head_y - 6)),
            2,
        )

        # Barra de vida
        bar_w = 140
        bar_h = 8
        bar_x = int(self.head_x - bar_w / 2)
        bar_y = int(self.head_y - self.HEAD_RADIUS - 18)
        pygame.draw.rect(surface, colors.DARK_GRAY, (bar_x, bar_y, bar_w, bar_h))
        if self.max_health > 0:
            life_w = int(bar_w * (self.health / self.max_health))
            pygame.draw.rect(surface, glow_color, (bar_x, bar_y, life_w, bar_h))
            pygame.draw.rect(surface, colors.WHITE, (bar_x, bar_y, bar_w, bar_h), 2)
