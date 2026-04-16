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

    ROCK_MAX_HP = 3
    BOT_MAX_HP = 2
    ROCK_SCORE = 8
    BOT_SCORE = 6
    # Mesma paleta de terra usada pelos fragmentos de entrada do StoneGolemBoss.
    STONE_FRAGMENT_COLORS = [
        (101, 67, 33),
        (84, 56, 26),
        (65, 65, 65),
        (45, 45, 45),
        (139, 115, 85),
        (160, 82, 45),
    ]

    @classmethod
    def _random_fragment_palette_color(cls) -> tuple[int, int, int]:
        base = random.choice(cls.STONE_FRAGMENT_COLORS)
        jitter = random.randint(-12, 12)
        return (
            max(0, min(255, base[0] + jitter)),
            max(0, min(255, base[1] + jitter)),
            max(0, min(255, base[2] + jitter)),
        )

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

        # Atributos dinamicos definidos aqui para evitar W0201 (attribute-defined-outside-init).
        self._spawn_y = 0.0

        self._base_speed = 0.0
        self._drift_amp = 0.0
        self._drift_freq = 0.0
        self._phase = 0.0
        self._time = 0.0

        self.rock_pts: list[tuple[float, float]] = []
        self._rock_span_w = 0
        self._eye_size = 4
        self._base_body_h = 8
        self._base_margin = 8
        self._base_body_w = 0

        self.color_body: tuple[int, int, int] = (30, 30, 30)
        self.color_eye: tuple[int, int, int] = (255, 140, 0)
        self.color_thruster_hot: tuple[int, int, int] = (255, 220, 120)
        self.color_thruster_mid: tuple[int, int, int] = (255, 120, 70)
        self.color_thruster_cool: tuple[int, int, int] = (210, 60, 50)
        self._rock_color = self._random_fragment_palette_color()

        self._rock_hp = self.ROCK_MAX_HP
        self._bot_hp = self.BOT_MAX_HP
        self._rock_destroyed = False
        self._bot_destroyed = False
        self._fully_destroyed = False

        self._rock_hit_rect = pygame.Rect(0, 0, 1, 1)
        self._bot_hit_rect = pygame.Rect(0, 0, 1, 1)
        self._rock_center: tuple[float, float] = (
            self.x + self.size,
            self.y + self.size,
        )
        self._bot_center: tuple[float, float] = (self.x + self.size, self.y + self.size)

        self._death_particles: list[
            tuple[float, float, float, float, float, float, float, tuple[int, int, int]]
        ] = []
        self._outro_timer = 0.0
        self._rock_falling = False
        self._rock_fall_vy = 0.0
        self._rock_fall_gravity = 620.0
        self._collision_disabled = False

        self._eye_scan_speed = 2.0
        self._eye_scan_offset = 0
        self._eye_blink_timer = 0.0
        self._eye_blink_duration = 0.09
        self._eye_blink_remaining = 0.0
        self._eye_blink_interval = 2.0

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

        # Pedras maiores ficam mais lentas; pedras menores, mais rapidas.
        min_size = 15
        max_size = 22
        size_ratio = (glider_size - min_size) / max(1, (max_size - min_size))
        size_ratio = max(0.0, min(1.0, size_ratio))

        fastest_speed = 230.0  # menor pedra
        slowest_speed = 120.0  # maior pedra
        target_speed = fastest_speed + (slowest_speed - fastest_speed) * size_ratio
        self._base_speed = target_speed + random.uniform(-2.0, 2.0)
        self._drift_amp = random.uniform(30.0, 50.0)
        self._drift_freq = random.uniform(1.5, 2.5)
        self._phase = random.uniform(0.0, math.tau)
        self._time = 0.0

        if x is None:
            self.x = Config.SCREEN_WIDTH + 40.0
        if y is None:
            self.y = random.randint(100, 500)

        self._spawn_y = self.y

        # Pedra superior irregular com base sempre mais larga que o topo.
        top_half_w = self.size * random.uniform(0.75, 1.05)
        base_half_w = self.size * random.uniform(1.35, 1.65)
        if base_half_w <= top_half_w:
            base_half_w = top_half_w + self.size * 0.35

        top_h = self.size * random.uniform(0.65, 0.95)
        bottom_h = self.size * random.uniform(0.55, 0.85)

        base_points: list[tuple[float, float]] = [
            (-top_half_w, -top_h * 0.75),
            (-top_half_w * 0.40, -top_h),
            (top_half_w * 0.35, -top_h * 0.95),
            (top_half_w, -top_h * 0.70),
            (base_half_w * 0.92, -bottom_h * 0.10),
            (base_half_w, bottom_h * 0.58),
            (base_half_w * 0.45, bottom_h * 0.95),
            (-base_half_w * 0.42, bottom_h * 0.98),
            (-base_half_w, bottom_h * 0.60),
            (-base_half_w * 0.90, -bottom_h * 0.12),
        ]

        self.rock_pts: list[tuple[float, float]] = []
        for px, py in base_points:
            jx = random.uniform(-self.size * 0.07, self.size * 0.07)
            jy = random.uniform(-self.size * 0.06, self.size * 0.06)
            self.rock_pts.append((px + jx, py + jy))

        # Medida real da pedra para dimensionar a base pela largura.
        rock_min_x = min(px for px, _ in self.rock_pts)
        rock_max_x = max(px for px, _ in self.rock_pts)
        self._rock_span_w = max(14, int(rock_max_x - rock_min_x))

        # Altura fixa e baixa da base: apenas um pouco maior que os olhos.
        self._eye_size = 4
        self._base_body_h = 8

        # Largura dinamica: sempre um pouco maior que a pedra carregada.
        self._base_margin = 8
        self._base_body_w = self._rock_span_w + self._base_margin

        # Hitbox geral cobre pedra + base.
        self.w = max(int(self.size * 2.4), self._base_body_w)
        self.h = int(self.size * 1.9) + self._base_body_h

        self.vx = -self._base_speed if vx is None else -abs(vx)
        self.vy = 0.0 if vy is None else vy

        self.color_body: tuple[int, int, int] = (30, 30, 30)
        self.color_eye: tuple[int, int, int] = (255, 140, 0)
        self.color_thruster_hot: tuple[int, int, int] = (255, 220, 120)
        self.color_thruster_mid: tuple[int, int, int] = (255, 120, 70)
        self.color_thruster_cool: tuple[int, int, int] = (210, 60, 50)
        self._rock_color = self._random_fragment_palette_color()

        self._rock_hp = self.ROCK_MAX_HP
        self._bot_hp = self.BOT_MAX_HP
        self._rock_destroyed = False
        self._bot_destroyed = False
        self._fully_destroyed = False

        self._rock_hit_rect = pygame.Rect(0, 0, 1, 1)
        self._bot_hit_rect = pygame.Rect(0, 0, 1, 1)
        self._rock_center: tuple[float, float] = (
            self.x + self.size,
            self.y + self.size,
        )
        self._bot_center: tuple[float, float] = (self.x + self.size, self.y + self.size)

        self._death_particles: list[
            tuple[float, float, float, float, float, float, float, tuple[int, int, int]]
        ] = []
        self._outro_timer = 0.0
        self._rock_falling = False
        self._rock_fall_vy = 0.0
        self._rock_fall_gravity = 620.0
        self._collision_disabled = False

        # Personalidade dos olhos do bot: scan lateral, piscadas e expressao.
        self._eye_scan_speed = random.uniform(2.0, 3.4)
        self._eye_scan_offset = 0
        self._eye_blink_timer = 0.0
        self._eye_blink_duration = 0.09
        self._eye_blink_remaining = 0.0
        self._eye_blink_interval = random.uniform(1.6, 3.2)

        self.health = self._rock_hp + self._bot_hp
        self._update_collision_regions()

    def _build_geometry(self) -> tuple[list[tuple[int, int]], pygame.Rect, int, int]:
        cx = int(self.x + self.size)
        cy = int(self.y + self.size)
        rock_points = [(int(cx + px), int(cy + py - 5)) for px, py in self.rock_pts]
        rock_span_screen = max(x for x, _ in rock_points) - min(
            x for x, _ in rock_points
        )
        body_w = max(self._base_body_w, rock_span_screen + self._base_margin)
        body_h = self._base_body_h
        body_rect = pygame.Rect(cx - body_w // 2, cy, body_w, body_h)
        return rock_points, body_rect, cx, cy

    def _update_collision_regions(self) -> None:
        rock_points, body_rect, _cx, cy = self._build_geometry()

        rock_min_x = min(x for x, _ in rock_points)
        rock_max_x = max(x for x, _ in rock_points)
        rock_min_y = min(y for _, y in rock_points)
        rock_max_y = max(y for _, y in rock_points)
        self._rock_hit_rect = pygame.Rect(
            rock_min_x,
            rock_min_y,
            max(1, rock_max_x - rock_min_x),
            max(1, rock_max_y - rock_min_y),
        )

        arm_w = 5
        arm_h = 10
        left_arm = pygame.Rect(body_rect.left, cy - 8, arm_w, arm_h)
        right_arm = pygame.Rect(body_rect.right - arm_w, cy - 8, arm_w, arm_h)
        thruster_zone = pygame.Rect(
            body_rect.left, body_rect.bottom, body_rect.width, 14
        )
        self._bot_hit_rect = (
            body_rect.union(left_arm).union(right_arm).union(thruster_zone)
        )

        self._rock_center = (
            float(self._rock_hit_rect.centerx),
            float(self._rock_hit_rect.centery),
        )
        self._bot_center = (
            float(self._bot_hit_rect.centerx),
            float(self._bot_hit_rect.centery),
        )

    def _spawn_death_particles(self, part: str) -> None:
        if part == "rock":
            count = 18
            colors_cycle = [
                self._random_fragment_palette_color(),
                self._random_fragment_palette_color(),
                self._random_fragment_palette_color(),
                self._random_fragment_palette_color(),
            ]
            center_x, center_y = self._rock_center
            speed_min, speed_max = 70.0, 180.0
            ttl_min, ttl_max = 0.22, 0.42
        else:
            count = 14
            colors_cycle = [(200, 200, 200), (120, 120, 120), (255, 120, 70)]
            center_x, center_y = self._bot_center
            speed_min, speed_max = 60.0, 150.0
            ttl_min, ttl_max = 0.20, 0.36

        for i in range(count):
            ang = random.uniform(0.0, math.tau)
            speed = random.uniform(speed_min, speed_max)
            life = random.uniform(ttl_min, ttl_max)
            self._death_particles.append(
                (
                    center_x,
                    center_y,
                    math.cos(ang) * speed,
                    math.sin(ang) * speed,
                    life,
                    life,
                    random.uniform(2.0, 4.0),
                    colors_cycle[i % len(colors_cycle)],
                )
            )

    def _update_death_particles(self, dt: float) -> None:
        gravity = 210.0
        alive_particles: list[
            tuple[float, float, float, float, float, float, float, tuple[int, int, int]]
        ] = []
        for x, y, vx, vy, ttl, life, size, color in self._death_particles:
            ttl -= dt
            if ttl <= 0.0:
                continue
            vy += gravity * dt
            x += vx * dt
            y += vy * dt
            alive_particles.append((x, y, vx, vy, ttl, life, size, color))
        self._death_particles = alive_particles

    def _draw_death_particles(self, screen: pygame.Surface) -> None:
        for x, y, _vx, _vy, ttl, life, size, color in self._death_particles:
            life_ratio = max(0.0, min(1.0, ttl / max(life, 1e-6)))
            px_size = max(1, int(size * life_ratio + 1))
            px = int(x - px_size * 0.5)
            py = int(y - px_size * 0.5)
            pygame.draw.rect(screen, color, (px, py, px_size, px_size))

    def _resolve_hit_part(self, hit_x: float, hit_y: float) -> str | None:
        point = (int(hit_x), int(hit_y))
        rock_alive = not self._rock_destroyed
        bot_alive = not self._bot_destroyed

        rock_hit = rock_alive and self._rock_hit_rect.collidepoint(point)
        bot_hit = bot_alive and self._bot_hit_rect.collidepoint(point)

        if rock_hit and bot_hit:
            rock_dx = hit_x - self._rock_center[0]
            rock_dy = hit_y - self._rock_center[1]
            bot_dx = hit_x - self._bot_center[0]
            bot_dy = hit_y - self._bot_center[1]
            rock_dist_sq = rock_dx * rock_dx + rock_dy * rock_dy
            bot_dist_sq = bot_dx * bot_dx + bot_dy * bot_dy
            return "rock" if rock_dist_sq <= bot_dist_sq else "bot"

        if rock_hit:
            return "rock"
        if bot_hit:
            return "bot"

        if rock_alive and not bot_alive:
            return "rock"
        if bot_alive and not rock_alive:
            return "bot"
        if not rock_alive and not bot_alive:
            return None

        rock_dx = hit_x - self._rock_center[0]
        rock_dy = hit_y - self._rock_center[1]
        bot_dx = hit_x - self._bot_center[0]
        bot_dy = hit_y - self._bot_center[1]
        rock_dist_sq = rock_dx * rock_dx + rock_dy * rock_dy
        bot_dist_sq = bot_dx * bot_dx + bot_dy * bot_dy
        return "rock" if rock_dist_sq <= bot_dist_sq else "bot"

    def take_part_damage(
        self, hit_x: float, hit_y: float, amount: int = 1
    ) -> tuple[int, bool, bool, tuple[float, float], str | None]:
        self._update_collision_regions()
        target = self._resolve_hit_part(hit_x, hit_y)
        if target is None:
            return 0, False, self._fully_destroyed, (hit_x, hit_y), None

        points = 0
        part_destroyed = False

        if target == "rock" and not self._rock_destroyed:
            self._rock_hp -= amount
            if self._rock_hp <= 0:
                self._rock_hp = 0
                self._rock_destroyed = True
                part_destroyed = True
                points = self.ROCK_SCORE
                self._spawn_death_particles("rock")
        elif target == "bot" and not self._bot_destroyed:
            self._bot_hp -= amount
            if self._bot_hp <= 0:
                self._bot_hp = 0
                self._bot_destroyed = True
                part_destroyed = True
                points = self.BOT_SCORE
                self._spawn_death_particles("bot")
                if not self._rock_destroyed:
                    self._rock_falling = True
                    self._rock_fall_vy = max(0.0, self.vy)

        self.health = self._rock_hp + self._bot_hp
        self._fully_destroyed = self._rock_destroyed and self._bot_destroyed
        if self._fully_destroyed:
            self._collision_disabled = True
            self.w = 0
            self.h = 0
        impact_center = self._rock_center if target == "rock" else self._bot_center
        return points, part_destroyed, self._fully_destroyed, impact_center, target

    def update(self, dt: float, is_side_scroll: bool = False):
        self._time += dt

        if self._fully_destroyed:
            if not self._collision_disabled:
                self._collision_disabled = True
                self.w = 0
                self.h = 0
            self._outro_timer += dt
            self._update_death_particles(dt)
            if self._outro_timer >= 0.35 and not self._death_particles:
                self.dead = True
            return

        self.x += self.vx * dt

        if self._rock_falling and not self._rock_destroyed and self._bot_destroyed:
            self._rock_fall_vy += self._rock_fall_gravity * dt
            self.y += self._rock_fall_vy * dt
            self._spawn_y = self.y
        else:
            if self.vy != 0.0:
                self._spawn_y += self.vy * dt
            self.y = (
                self._spawn_y
                + math.sin(self._time * self._drift_freq + self._phase)
                * self._drift_amp
            )

        self._update_collision_regions()
        self._update_death_particles(dt)

        if self._rock_destroyed and self._bot_destroyed:
            self._fully_destroyed = True
            self._outro_timer = 0.0

        if not self._bot_destroyed:
            # Scan de olho com microvarredura -1/0/+1.
            self._eye_scan_offset = int(
                round(math.sin(self._time * self._eye_scan_speed))
            )
            self._eye_scan_offset = max(-1, min(1, self._eye_scan_offset))

            # Piscada rapida periodica.
            if self._eye_blink_remaining > 0.0:
                self._eye_blink_remaining = max(0.0, self._eye_blink_remaining - dt)
            self._eye_blink_timer += dt
            if self._eye_blink_timer >= self._eye_blink_interval:
                self._eye_blink_timer = 0.0
                self._eye_blink_remaining = self._eye_blink_duration
                self._eye_blink_interval = random.uniform(1.6, 3.2)

        if self.x < -100 or self.y < -self.h or self.y > Config.SCREEN_HEIGHT:
            self.dead = True

    def draw(self, screen: pygame.Surface):
        rock_points, body_rect, _cx, cy = self._build_geometry()

        self._rock_center = (
            float(sum(x for x, _ in rock_points) / len(rock_points)),
            float(sum(y for _, y in rock_points) / len(rock_points)),
        )
        self._bot_center = (float(body_rect.centerx), float(body_rect.centery))

        # 1) Pedra no topo
        if not self._rock_destroyed:
            pygame.draw.polygon(screen, self._rock_color, rock_points)
            pygame.draw.polygon(screen, colors.BLACK, rock_points, 2)

        # 2) Corpo principal (baixo e fixo na altura)
        if not self._bot_destroyed:
            pygame.draw.rect(screen, self.color_body, body_rect)
            pygame.draw.rect(screen, colors.BLACK, body_rect, 2)

            # 3) Bracos/garras laterais
            arm_w = 5
            arm_h = 10
            pygame.draw.rect(
                screen, self.color_body, (body_rect.left, cy - 8, arm_w, arm_h)
            )
            pygame.draw.rect(
                screen,
                self.color_body,
                (body_rect.right - arm_w, cy - 8, arm_w, arm_h),
            )

            # 4) Olhos laranja quadrados
            eye_size = self._eye_size
            eye_h = (
                eye_size if self._eye_blink_remaining <= 0.0 else max(1, eye_size // 3)
            )
            eye_y = body_rect.centery - eye_h // 2

            left_eye_x = body_rect.centerx - eye_size - 2 + self._eye_scan_offset
            right_eye_x = body_rect.centerx + 2 + self._eye_scan_offset

            pygame.draw.rect(
                screen,
                self.color_eye,
                (left_eye_x, eye_y, eye_size, eye_h),
            )
            pygame.draw.rect(
                screen,
                self.color_eye,
                (right_eye_x, eye_y, eye_size, eye_h),
            )

            if eye_h > 1:
                pupil_w = max(1, eye_size // 2)
                pupil_h = max(1, eye_h // 2)
                pygame.draw.rect(
                    screen,
                    colors.BLACK,
                    (
                        left_eye_x + (eye_size - pupil_w) // 2,
                        eye_y + (eye_h - pupil_h) // 2,
                        pupil_w,
                        pupil_h,
                    ),
                )
                pygame.draw.rect(
                    screen,
                    colors.BLACK,
                    (
                        right_eye_x + (eye_size - pupil_w) // 2,
                        eye_y + (eye_h - pupil_h) // 2,
                        pupil_w,
                        pupil_h,
                    ),
                )

            # Sobrancelhas inclinadas para dentro (expressao de foco/agressividade).
            brow_y = eye_y - 2
            pygame.draw.line(
                screen,
                colors.BLACK,
                (left_eye_x - 1, brow_y),
                (left_eye_x + eye_size + 1, brow_y + 1),
                1,
            )
            pygame.draw.line(
                screen,
                colors.BLACK,
                (right_eye_x - 1, brow_y + 1),
                (right_eye_x + eye_size + 1, brow_y),
                1,
            )

            # 5) Dois thrusters de anel (estilo Bot Elemental), compactos nas pontas
            nozzle_w = 3
            nozzle_h = 2
            nozzle_y = body_rect.bottom
            left_nozzle = pygame.Rect(body_rect.left + 1, nozzle_y, nozzle_w, nozzle_h)
            right_nozzle = pygame.Rect(
                body_rect.right - nozzle_w - 1, nozzle_y, nozzle_w, nozzle_h
            )
            pygame.draw.rect(screen, self.color_body, left_nozzle)
            pygame.draw.rect(screen, self.color_body, right_nozzle)

            ring_count = 3
            max_drop = 10
            ring_speed = 2.3

            for cx_ring, side_phase in (
                (left_nozzle.centerx, 0.0),
                (right_nozzle.centerx, 0.5),
            ):
                for i in range(ring_count):
                    phase = (
                        (self._time * ring_speed) + (i / ring_count) + side_phase
                    ) % 1.0
                    ring_w = max(2, int(8 * (1.0 - phase)))
                    ring_h = max(1, int(3 * (1.0 - phase)))
                    ring_y = nozzle_y + nozzle_h + int(phase * max_drop)

                    if phase < 0.2:
                        ring_color = self.color_thruster_hot
                    elif phase < 0.55:
                        ring_color = self.color_thruster_mid
                    else:
                        ring_color = self.color_thruster_cool

                    ring_rect = pygame.Rect(
                        cx_ring - ring_w // 2,
                        ring_y,
                        ring_w,
                        ring_h,
                    )
                    pygame.draw.rect(screen, ring_color, ring_rect, 1)

        self._draw_death_particles(screen)

    def can_split(self) -> bool:
        return False

    def get_points_value(self) -> int:
        return 14
