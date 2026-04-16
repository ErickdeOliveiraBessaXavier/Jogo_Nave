from __future__ import annotations

import math
import random

import pygame

from ..core import colors
from ..core.config import config as Config
from .meteor import Meteor


class RockGlider(Meteor):
    """
    Enemy swarm unit: um robo transportador robusto carregando uma rocha.
    Design: olhos laranja, corpo chumbo e thruster vermelho.
    """

    def __init__(
        self,
        size: int | None = None,
        x: float | None = None,
        y: float | None = None,
        vx: float | None = None,
        vy: float | None = None,
    ):
        glider_size = size if size is not None else random.randint(15, 22)
        super().__init__(size=glider_size, x=x, y=y, vx=vx, vy=vy)
        self.reset(size=glider_size, x=x, y=y, vx=vx, vy=vy)

    def reset(
        self,
        size: int | None = None,
        x: float | None = None,
        y: float | None = None,
        vx: float | None = None,
        vy: float | None = None,
    ):
        glider_size = size if size is not None else random.randint(15, 22)
        super().reset(size=glider_size, x=x, y=y, vx=vx, vy=vy)

        self.health = 14
        self._base_speed = random.uniform(160.0, 220.0)
        self._drift_amp = random.uniform(30.0, 50.0)
        self._drift_freq = random.uniform(1.5, 2.5)
        self._phase = random.uniform(0.0, math.tau)
        self._time = 0.0

        if x is None:
            self.x = Config.SCREEN_WIDTH + 40.0
        if y is None:
            self.y = random.randint(100, 500)

        self._spawn_y = self.y

        # Pedra superior (meia lua superior irregular).
        self.rock_pts: list[tuple[float, float]] = []
        for i in range(7):
            angle = math.pi + (i / 6) * math.pi
            distance = self.size * random.uniform(0.8, 1.3)
            self.rock_pts.append(
                (math.cos(angle) * distance * 1.5, math.sin(angle) * distance * 0.8)
            )

        # Medida real da pedra para dimensionar a base pela largura.
        rock_min_x = min(px for px, _ in self.rock_pts)
        rock_max_x = max(px for px, _ in self.rock_pts)
        self._rock_span_w = max(14, int(rock_max_x - rock_min_x))

        # Altura fixa e baixa da base: apenas um pouco maior que os olhos.
        self._eye_size = 4
        self._base_body_h = 8

        # Largura dinamica: sempre um pouco maior que a pedra carregada.
        self._base_body_w = self._rock_span_w + 8

        # Hitbox geral cobre pedra + base.
        self.w = max(int(self.size * 2.4), self._base_body_w)
        self.h = int(self.size * 1.9) + self._base_body_h

        self.vx = -self._base_speed if vx is None else -abs(vx)
        self.vy = 0.0 if vy is None else vy

        self.color_body: tuple[int, int, int] = (30, 30, 30)
        self.color_eye: tuple[int, int, int] = (255, 140, 0)
        self.color_thruster: tuple[int, int, int] = (255, 40, 40)

    def update(self, dt: float, is_side_scroll: bool = False):
        self._time += dt
        self.x += self.vx * dt

        if self.vy != 0.0:
            self._spawn_y += self.vy * dt

        self.y = self._spawn_y + math.sin(self._time * self._drift_freq + self._phase) * self._drift_amp

        if self.x < -100 or self.y < -self.h or self.y > Config.SCREEN_HEIGHT:
            self.dead = True

    def draw(self, screen: pygame.Surface):
        cx = int(self.x + self.size)
        cy = int(self.y + self.size)

        # 1) Pedra no topo
        rock_points = [(int(cx + px), int(cy + py - 5)) for px, py in self.rock_pts]
        pygame.draw.polygon(screen, (100, 90, 85), rock_points)
        pygame.draw.polygon(screen, colors.BLACK, rock_points, 2)

        # 2) Corpo principal (baixo e fixo na altura)
        body_w = self._base_body_w
        body_h = self._base_body_h
        body_rect = pygame.Rect(cx - body_w // 2, cy, body_w, body_h)
        pygame.draw.rect(screen, self.color_body, body_rect)
        pygame.draw.rect(screen, colors.BLACK, body_rect, 2)

        # 3) Bracos/garras laterais
        arm_w = 5
        arm_h = 10
        pygame.draw.rect(screen, self.color_body, (body_rect.left, cy - 8, arm_w, arm_h))
        pygame.draw.rect(
            screen,
            self.color_body,
            (body_rect.right - arm_w, cy - 8, arm_w, arm_h),
        )

        # 4) Olhos laranja quadrados
        eye_size = self._eye_size
        pygame.draw.rect(
            screen,
            self.color_eye,
            (body_rect.centerx - eye_size - 2, body_rect.centery - eye_size // 2, eye_size, eye_size),
        )
        pygame.draw.rect(
            screen,
            self.color_eye,
            (body_rect.centerx + 2, body_rect.centery - eye_size // 2, eye_size, eye_size),
        )

        # 5) Thrusters finos e menores com pequeno tremor
        thruster_y = body_rect.bottom + 2
        for i in range(3):
            width = max(6, (body_w // 2) - (i * 6))
            offset = math.sin(self._time * 15 + i) * 2.0
            thruster_rect = pygame.Rect(
                body_rect.centerx - width // 2,
                int(thruster_y + (i * 4) + offset),
                width,
                2,
            )
            pygame.draw.rect(screen, self.color_thruster, thruster_rect)

    def can_split(self) -> bool:
        return False

    def get_points_value(self) -> int:
        return 14

