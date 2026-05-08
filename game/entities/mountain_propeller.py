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

    PALETTE: Final[dict[str, tuple[int, int, int] | None]] = {
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
        "001222222222222100",
        "001222222222222100",
        "001222222222222100",
        "001222222222222100",
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

    EYES_OPEN_MAP = [
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000001100001100000",
        "000014410014410000",
        "000014410014410000",
        "000001100001100000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
    ]

    EYES_LEFT_MAP = [
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000001100001100000",
        "000044100044100000",
        "000044100044100000",
        "000001100001100000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
    ]

    EYES_RIGHT_MAP = [
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000001100001100000",
        "000001440001440000",
        "000001440001440000",
        "000001100001100000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
    ]

    EYES_CLOSED_MAP = [
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000011000000110000",
        "000001100001100000",
        "000011000000110000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
        "000000000000000000",
    ]

    BLADES_MAP = [
        "000000000111100000000",
        "000000001666661000000",
        "000000016666666100000",
        "000000016666661000000",
        "000000001666610000000",
        "000000000166100000000",
        "000000000011000000000",
        "000000000000000000000",
        "000000000000000000000",
        "000000000000000000000",
        "000111000000000000000",
        "001666100000000111000",
        "016666100000000166100",
        "166666100000001666610",
        "166661000000001666661",
        "016610000000001666661",
        "001100000000000166661",
        "000000000000000011110",
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
        "000000000111000000000",
        "000000001555100000000",
        "000000016555510000000",
        "000000016665510000000",
        "000000016666610000000",
        "000000001666100000000",
        "000000000111000000000",
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
        self.eyes_open_surf = self._create_surface_from_map(self.EYES_OPEN_MAP)
        self.eyes_left_surf = self._create_surface_from_map(self.EYES_LEFT_MAP)
        self.eyes_right_surf = self._create_surface_from_map(self.EYES_RIGHT_MAP)
        self.eyes_closed_surf = self._create_surface_from_map(self.EYES_CLOSED_MAP)
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

        # Animation states
        self.blink_timer = random.uniform(2.0, 5.0)
        self.is_blinking = False
        self.blink_duration = 0.15
        self.look_state = "center"
        self.look_timer = random.uniform(1.0, 3.0)

        self.wind_streaks: list[dict[str, float]] = []
        self.sweat_particles: list[dict[str, float]] = []
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

        self._update_animations(dt)
        self._update_particles(dt)

    def _update_animations(self, dt: float) -> None:
        if self.is_blinking:
            self.blink_timer -= dt
            if self.blink_timer <= 0:
                self.is_blinking = False
                self.blink_timer = random.uniform(2.0, 5.0)
        else:
            self.blink_timer -= dt
            if self.blink_timer <= 0:
                self.is_blinking = True
                self.blink_timer = self.blink_duration

        self.look_timer -= dt
        if self.look_timer <= 0:
            self.look_state = random.choices(
                ["center", "left", "right"], weights=[0.6, 0.2, 0.2]
            )[0]
            self.look_timer = random.uniform(1.0, 3.0)

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

    def _update_particles(self, dt: float) -> None:
        is_effort = self.state in (_PropellerState.WIND_UP, _PropellerState.BLOWING)
        if is_effort and random.random() < 15 * dt:
            self.sweat_particles.append(
                {
                    "x": self.x + random.uniform(-20, 20),
                    "y": self.y - self.BODY_H // 3,
                    "vx": random.uniform(-180, 180),
                    "vy": random.uniform(-300, -100),
                    "life": random.uniform(0.3, 0.7),
                }
            )

        for p in self.sweat_particles[:]:
            p["vy"] += 800 * dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["life"] -= dt
            if p["life"] <= 0:
                self.sweat_particles.remove(p)

    def draw(self, surface: pygame.Surface) -> None:
        if self.state == _PropellerState.BLOWING:
            self._draw_wind_effect(surface)

        shake_x, shake_y = 0, 0
        is_effort = self.state in (_PropellerState.WIND_UP, _PropellerState.BLOWING)
        if is_effort:
            shake_x = random.randint(-2, 2)
            shake_y = random.randint(-2, 2)

        body_rect = self.body_surf.get_rect(
            center=(int(self.x) + shake_x, int(self.y) + shake_y)
        )
        surface.blit(self.body_surf, body_rect.topleft)

        if is_effort or self.is_blinking:
            eye_surf = self.eyes_closed_surf
        else:
            if self.look_state == "left":
                eye_surf = self.eyes_left_surf
            elif self.look_state == "right":
                eye_surf = self.eyes_right_surf
            else:
                eye_surf = self.eyes_open_surf

        surface.blit(eye_surf, body_rect.topleft)

        for p in self.sweat_particles:
            pygame.draw.rect(surface, (20, 20, 25), (int(p["x"]), int(p["y"]), 4, 4))

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
