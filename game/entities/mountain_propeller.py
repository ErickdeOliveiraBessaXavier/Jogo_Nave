from __future__ import annotations

import random
from enum import Enum, auto
from typing import TYPE_CHECKING, Final

import pygame

from ..core.config import config as Config

if TYPE_CHECKING:
    from ..systems.hit_result import HitResult


class _PropellerState(Enum):
    ENTERING = auto()
    PATROLLING = auto()
    WIND_UP = auto()
    BLOWING = auto()
    COOLDOWN = auto()


class MountainPropeller:
    WIND_DURATION: Final = 3.5
    WIND_UP_TIME: Final = 1.2
    COOLDOWN_TIME: Final = 3.0

    PUSH_FORCE: Final = 220.0
    SLOW_SPEED_MULT: Final = 0.45
    EDGE_MARGIN: Final = 60
    PIXEL_SCALE: Final = 3

    LERP_FACTOR: Final = 0.12

    PALETTE: Final = {
        "0": None,
        "1": (20, 20, 25),
        "2": (220, 160, 40),
        "3": (170, 110, 20),
        "4": (210, 40, 40),
        "5": (130, 140, 130),
        "6": (90, 100, 90),
    }

    BODY_MAP = [
        "000000111111000000",
        "000011222222110000",
        "000122222222221000",
        "001221122221122100",
        "001214412214412100",
        "001214412214412100",
        "001221122221122100",
        "001222222222233100",
        "001222222222333100",
        "000122222223331000",
        "000011111111110000",
        "000155551155551000",
        "001551100001155100",
        "015510000000015510",
        "015100000000001510",
        "155100000000001551",
    ]

    BLADES_MAP = [
        "000000000111100000000",
        "000000001666611000000",
        "000000016666666100000",
        "000000016666661000000",
        "000000001666610000000",
        "000000000116100000000",
        "000000000000000000000",
        "000000000000000000000",
        "000000000000000000000",
        "000000000000000000000",
        "000000000000000000000",
        "001110000000000000000",
        "016666100000000011100",
        "166666100000000166610",
        "166661000000000166661",
        "016610000000001666661",
        "001100000000000166661",
        "000000000000000011100",
        "000000000000000000000",
        "000000000000000000000",
        "000000000000000000000",
    ]

    HUB_MAP = [
        "000000000000000000000",
        "000000000000000000000",
        "000000000000000000000",
        "000000000000000000000",
        "000000000000000000000",
        "000000000000000000000",
        "000000000000000000000",
        "000000001111100000000",
        "000000016666610000000",
        "000000166666661000000",
        "000000166666661000000",
        "000000166666661000000",
        "000000016666610000000",
        "000000001111100000000",
        "000000000000000000000",
        "000000000000000000000",
        "000000000000000000000",
        "000000000000000000000",
        "000000000000000000000",
        "000000000000000000000",
        "000000000000000000000",
    ]

    def is_blowing(self) -> bool:
        return self.state == _PropellerState.BLOWING

    def get_wind_rect(self) -> pygame.Rect:
        if not self.is_blowing():
            return pygame.Rect(0, 0, 0, 0)
        w_h = 90
        return pygame.Rect(
            0, int(self.prop_curr_y - w_h // 2), int(self.prop_curr_x), w_h
        )

    def __init__(self, y: float | None = None):
        self.body_surf = self._create_surface_from_map(self.BODY_MAP)
        self.blades_surf = self._create_surface_from_map(self.BLADES_MAP)
        self.hub_surf = self._create_surface_from_map(self.HUB_MAP)

        self.BODY_W = self.body_surf.get_width()
        self.BODY_H = self.body_surf.get_height()

        self.x = Config.SCREEN_WIDTH + self.BODY_W
        self.target_x = Config.SCREEN_WIDTH - self.EDGE_MARGIN
        self.y = y if y is not None else random.randint(100, Config.SCREEN_HEIGHT - 100)

        self.prop_curr_x = self.x
        self.prop_curr_y = self.y

        self.health = 6
        self.dead = False
        self.causes_damage = False

        self.state = _PropellerState.ENTERING
        self.timer = 0.0
        self.move_speed = 140.0
        self.move_dir = random.choice([-1, 1])

        self.prop_angle = 0.0
        self.prop_speed = 0.0

        self.wind_streaks: list[dict[str, float]] = []
        self._init_streaks()

    def _create_surface_from_map(self, pixel_map: list[str]) -> pygame.Surface:
        width = len(pixel_map[0]) * self.PIXEL_SCALE
        height = len(pixel_map) * self.PIXEL_SCALE
        surf = pygame.Surface((width, height), pygame.SRCALPHA)
        for row_idx, row in enumerate(pixel_map):
            for col_idx, char in enumerate(row):
                color = self.PALETTE.get(char)
                if color:
                    pygame.draw.rect(
                        surf,
                        color,
                        (
                            col_idx * self.PIXEL_SCALE,
                            row_idx * self.PIXEL_SCALE,
                            self.PIXEL_SCALE,
                            self.PIXEL_SCALE,
                        ),
                    )
        return surf

    def _init_streaks(self) -> None:
        for _ in range(30):
            self.wind_streaks.append(
                {
                    "x": random.uniform(0, Config.SCREEN_WIDTH),
                    "y_offset": random.uniform(-35, 35),
                    "speed": random.uniform(900, 1400),
                    "len": random.uniform(40, 100),
                    "alpha": random.randint(40, 100),
                }
            )

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(
            int(self.x - self.BODY_W // 2),
            int(self.y - self.BODY_H // 2),
            self.BODY_W,
            self.BODY_H,
        )

    def update(self, dt: float) -> None:
        self.timer += dt

        if self.state == _PropellerState.ENTERING:
            self.x -= 180 * dt
            if self.x <= self.target_x:
                self.x = self.target_x
                self.state = _PropellerState.PATROLLING
                self.timer = 0.0
        elif self.state == _PropellerState.PATROLLING:
            self._update_movement(dt)
            self.prop_speed = 250.0
            if self.timer > 1.8:
                self.state = _PropellerState.WIND_UP
                self.timer = 0.0
        elif self.state == _PropellerState.WIND_UP:
            self._update_movement(dt * 0.4)
            progress = self.timer / self.WIND_UP_TIME
            self.prop_speed = 250.0 + (1800.0 * (progress**2))
            if self.timer >= self.WIND_UP_TIME:
                self.state = _PropellerState.BLOWING
                self.timer = 0.0
        elif self.state == _PropellerState.BLOWING:
            self.prop_speed = 2200.0
            self._update_streaks(dt)
            if self.timer >= self.WIND_DURATION:
                self.state = _PropellerState.COOLDOWN
                self.timer = 0.0
        elif self.state == _PropellerState.COOLDOWN:
            self._update_movement(dt)
            progress = self.timer / 1.0
            self.prop_speed = max(250.0, 2200.0 * (1.0 - progress))
            if self.timer >= self.COOLDOWN_TIME:
                self.state = _PropellerState.PATROLLING
                self.timer = 0.0

        self.prop_angle += self.prop_speed * dt

        target_x = self.x
        target_y = self.y + (self.BODY_H // 3)

        self.prop_curr_x += (target_x - self.prop_curr_x) * self.LERP_FACTOR
        self.prop_curr_y += (target_y - self.prop_curr_y) * self.LERP_FACTOR

    def _update_movement(self, dt: float) -> None:
        self.y += self.move_speed * self.move_dir * dt
        if self.y < 100:
            self.y = 100
            self.move_dir = 1
        elif self.y > Config.SCREEN_HEIGHT - 100:
            self.y = Config.SCREEN_HEIGHT - 100
            self.move_dir = -1

    def _update_streaks(self, dt: float) -> None:
        for s in self.wind_streaks:
            s["x"] -= s["speed"] * dt
            if s["x"] + s["len"] < 0:
                s["x"] = self.prop_curr_x - 10
                s["y_offset"] = random.uniform(-35, 35)

    def draw(self, surface: pygame.Surface) -> None:
        if self.state == _PropellerState.BLOWING:
            self._draw_wind_effect(surface)

        body_rect = self.body_surf.get_rect(center=(int(self.x), int(self.y)))
        surface.blit(self.body_surf, body_rect.topleft)

        center_pos = (int(self.prop_curr_x), int(self.prop_curr_y))

        rotated_blades = pygame.transform.rotate(self.blades_surf, -self.prop_angle)
        blades_rect = rotated_blades.get_rect(center=center_pos)
        surface.blit(rotated_blades, blades_rect.topleft)

        hub_rect = self.hub_surf.get_rect(center=center_pos)
        surface.blit(self.hub_surf, hub_rect.topleft)

    def _draw_wind_effect(self, surface: pygame.Surface) -> None:
        w_h = 90
        w_rect = pygame.Rect(
            0, int(self.prop_curr_y - w_h // 2), int(self.prop_curr_x), w_h
        )
        wind_surf = pygame.Surface((w_rect.width, w_rect.height), pygame.SRCALPHA)
        for i in range(5):
            alpha = 10 - (i * 2)
            h = w_rect.height - (i * 15)
            if h > 0:
                pygame.draw.rect(
                    wind_surf,
                    (220, 240, 255, alpha),
                    (0, (w_rect.height - h) // 2, w_rect.width, h),
                )
        surface.blit(wind_surf, (w_rect.x, w_rect.y))
        for s in self.wind_streaks:
            if 0 < s["x"] < self.prop_curr_x:
                pygame.draw.line(
                    surface,
                    (255, 255, 255, int(s["alpha"])),
                    (s["x"], self.prop_curr_y + s["y_offset"]),
                    (s["x"] + s["len"], self.prop_curr_y + s["y_offset"]),
                    1,
                )

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        if self.health <= 0:
            self.dead = True

    def collision_circle(self) -> tuple[float, float, float]:
        r = self.rect
        return r.centerx, r.centery, max(r.width, r.height) / 2

    def on_hit(self, damage: int, _x: float, _y: float) -> "HitResult":
        from ..systems import hit_result, hit_sounds

        self.take_damage(damage)
        return hit_result.HitResult(
            killed=self.dead,
            points=250 if self.dead else 0,
            explosion_size=35 if self.dead else 10,
            sound=hit_sounds.EXPLOSION_ALIEN if self.dead else hit_sounds.BOSS_DAMAGE,
        )

    def on_ship_contact(self, _x: float, _y: float) -> "HitResult":
        from ..systems import hit_result, hit_sounds

        self.dead = True
        return hit_result.HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead
