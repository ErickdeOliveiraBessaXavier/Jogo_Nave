import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List, Tuple

import pygame

from ..core import colors
from ..core.config import config as Config
from ..core.sound import sound_manager
from ..entities.alien_bullet import AlienBullet

if TYPE_CHECKING:
    from ..systems.hit_result import HitResult


@dataclass
class Particle:
    """Partícula de pedra flutuante."""

    x: float
    y: float
    vx: float
    vy: float
    size: int
    lifetime: float


class StoneShardBullet(AlienBullet):
    """Projétil de pedra da Stone Sentry, com textura mais granular."""

    STONE_BULLET_COLORS = [
        (78, 60, 46),
        (112, 88, 66),
        (142, 118, 92),
        (60, 56, 54),
    ]
    _render_cache: dict[tuple[tuple[int, int, int], int, int], pygame.Surface] = {}
    _render_cache_limit = 256

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.x: float = x
        self.y: float = y
        self.spin: float = random.uniform(0.0, 360.0)
        self.spin_speed: float = random.uniform(180.0, 360.0) * random.choice([-1, 1])
        self.screen_w: int = Config.SCREEN_WIDTH
        self.screen_h: int = Config.SCREEN_HEIGHT
        self.color_1 = random.choice(self.STONE_BULLET_COLORS)
        self.color_2 = random.choice(self.STONE_BULLET_COLORS)
        self.current_color = self.color_1
        self.min_radius = 14
        self.max_radius = 14
        self.current_radius = 14
        self.hit_radius = 16
        self.pulse_speed = 0.0
        self._base_surface = pygame.Surface((22, 22), pygame.SRCALPHA)
        self._shard_points = [
            (11, 1),
            (16, 4),
            (20, 9),
            (17, 15),
            (11, 20),
            (5, 18),
            (1, 12),
            (3, 6),
        ]
        self._surface_cache = self._build_surface()

    def _build_surface(self) -> pygame.Surface:
        self._base_surface.fill((0, 0, 0, 0))

        rock = self.current_color
        shade = tuple(max(0, c - 28) for c in rock)
        highlight = tuple(min(255, c + 32) for c in rock)

        body_points = self._shard_points
        inner_points = [(9, 3), (15, 5), (18, 9), (15, 15), (9, 18), (4, 13), (5, 6)]
        pygame.draw.polygon(self._base_surface, shade, body_points)
        pygame.draw.polygon(self._base_surface, rock, body_points)
        pygame.draw.polygon(self._base_surface, colors.BLACK, body_points, 1)
        pygame.draw.polygon(self._base_surface, highlight, inner_points, 0)
        pygame.draw.line(self._base_surface, highlight, (6, 7), (13, 6), 1)
        pygame.draw.line(self._base_surface, highlight, (7, 12), (14, 10), 1)
        pygame.draw.rect(self._base_surface, (220, 140, 92), (11, 8, 2, 2))
        pygame.draw.line(self._base_surface, colors.BLACK, (6, 8), (12, 13), 1)
        pygame.draw.line(self._base_surface, colors.BLACK, (12, 5), (16, 11), 1)
        pygame.draw.line(self._base_surface, colors.BLACK, (8, 15), (14, 17), 1)
        return self._base_surface

    def get_render_surface(self) -> pygame.Surface:
        """Retorna a superfície base usada para renderização rotacionada."""
        return self._surface_cache

    def _get_rendered_surface(self, diameter: int) -> pygame.Surface:
        angle_bucket = int(self.spin / 5.0) * 5 % 360
        cache_key = (self.current_color, angle_bucket, diameter)
        cached_surface = self._render_cache.get(cache_key)
        if cached_surface is None:
            rotated_surface = pygame.transform.rotate(self._surface_cache, angle_bucket)
            cached_surface = pygame.transform.scale(
                rotated_surface,
                (diameter, diameter),
            )
            if len(self._render_cache) >= self._render_cache_limit:
                self._render_cache.clear()
            self._render_cache[cache_key] = cached_surface
        return cached_surface

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.spin += self.spin_speed * dt

        if self.y > self.screen_h + 80 or self.x < -80 or self.x > self.screen_w + 80:
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        diameter = max(16, int(self.current_radius) * 2)
        scaled_surface = self._get_rendered_surface(diameter)
        surface.blit(
            scaled_surface,
            (int(self.x) - diameter // 2, int(self.y) - diameter // 2),
        )

    @property
    def rect(self) -> pygame.Rect:
        hit_radius = max(self.hit_radius, int(self.current_radius))
        return pygame.Rect(
            int(self.x) - hit_radius,
            int(self.y) - hit_radius,
            hit_radius * 2,
            hit_radius * 2,
        )


class StoneSentry:
    """
    Inimigo Sentinela de Pedra - Tema de Montanha.
    Flutua até uma posição, persegue o jogador lentamente e dispara um pedregulho central.
    """

    STONE_COLORS = [
        (42, 31, 22),
        (56, 41, 29),
        (72, 54, 38),
        (88, 68, 48),
        (54, 54, 54),
    ]
    ACCENT_COLORS = [(185, 108, 68), (206, 126, 74), (230, 160, 104)]
    EXPLOSION_COLORS = [(130, 110, 80), (100, 100, 100), (255, 60, 60)]
    LOW_RES_SIZE = 20

    # Constantes de movimento e física
    EDGE_MARGIN = 20.0
    REPULSION_RADIUS = 90.0
    REPULSION_FORCE = 160.0
    MAX_FALL_VELOCITY = 600.0
    BOUNCE_DAMPING_HORIZONTAL = 0.82
    BOUNCE_DAMPING_VERTICAL = 0.72
    BOUNCE_DAMPING_BOTTOM = 0.52
    MIN_BOUNCE_VELOCITY = 140.0
    SUPER_PROJECTILE_CHANCE = 0.10
    SUPER_PROJECTILE_SCALE = 3.0
    _eye_sprite_cache: dict[
        tuple[tuple[int, int, int], tuple[int, int, int]], pygame.Surface
    ] = {}
    _particle_surface_cache: dict[
        tuple[tuple[int, int, int], int, int], pygame.Surface
    ] = {}
    _particle_alpha_step = 32

    def __init__(self):
        self.w = 40
        self.h = 40
        self.x = random.randint(50, Config.SCREEN_WIDTH - 50 - self.w)
        self.y = -self.h
        self.target_y = random.randint(50, 200)
        self.speed_y = 150.0

        self.float_amplitude = 10.0
        self.float_frequency = 2.0
        self.float_offset = 0.0
        self._entry_done = False

        # Cache de garras por frame
        self._claw_tips: Tuple[Tuple[float, float], Tuple[float, float]] | None = None

        self.dead = False
        self.health = 80
        self.active = True
        self.hit_timer = 0.0

        self.shoot_timer = random.uniform(2.7, 4.7)
        self._shoot_cycle = self.shoot_timer
        self.charge_duration = 1.45

        self.rotation = 0.0
        self.rotation_speed = random.uniform(-15, 15)
        self.points = self._generate_stone_shape()
        self.color = random.choice(self.STONE_COLORS)
        self.eye_color = colors.RED
        self.accent_color = random.choice(self.ACCENT_COLORS)
        self.pulse_timer = 0.0
        self._eye_rotation = random.uniform(0.0, 360.0)
        self._eye_spin_speed = random.uniform(45.0, 80.0)
        self._eye_spin_boost = 0.0
        self._shape_scale = (self.LOW_RES_SIZE - 2) / self.w
        self._low_res_surface = pygame.Surface(
            (self.LOW_RES_SIZE, self.LOW_RES_SIZE), pygame.SRCALPHA
        )
        self._body_surface_cache: dict[tuple[bool, int], pygame.Surface] = {}
        self._particles: list[Particle] = []
        self._crack_paths = self._generate_crack_paths()

        self._arm_phase = random.uniform(0.0, math.tau)
        self._arm_sway = random.uniform(0.65, 1.0)
        self._arm_open_progress = 0.0
        self._arm_anim_speed = 3.8
        self._arms_animating = False
        self._arm_dyn_x = 0.0
        self._arm_dyn_y = 0.0
        self._arm_dyn_vx = 0.0
        self._arm_dyn_vy = 0.0
        self._arm_impulse_stretch = 0.0
        self._was_jumping = False
        self._prev_jump_vy = 0.0

        self._recoil_left = 0.0
        self._recoil_right = 0.0
        self.shake_offset_x = 0.0
        self.shake_offset_y = 0.0

        # Movimento estilo Primal Aspid: pulos erráticos em direção ao jogador
        self._player_last_pos: Tuple[float, float] | None = None
        self._player_velocity: Tuple[float, float] = (0.0, 0.0)

        # Estado do pulo
        self._jump_vx: float = 0.0
        self._jump_vy: float = 0.0
        self._jump_gravity: float = 300.0
        self._is_jumping: bool = False
        self._land_y: float = float(self.target_y)
        self._land_timer: float = 0.0
        self._land_duration: float = random.uniform(5.0, 8.0)
        self._jump_count: int = 0

        # NOVO: Guarda a instância do projétil que está sendo carregado
        self._charging_bullet: StoneShardBullet | None = None
        self._is_super_bullet: bool = False

    @property
    def charge_ratio(self) -> float:
        if not self._arms_animating and 0 < self.shoot_timer <= self.charge_duration:
            return 1.0 - (self.shoot_timer / self.charge_duration)
        return 0.0

    def _generate_stone_shape(self) -> List[Tuple[float, float]]:
        pts: List[Tuple[float, float]] = []
        num_points = 8
        size = self.w // 2
        for i in range(num_points):
            ang = (2 * math.pi * i) / num_points
            r = size * random.uniform(0.8, 1.2)
            pts.append((r * math.cos(ang), r * math.sin(ang)))
        return pts

    def _generate_crack_paths(self) -> list[list[tuple[int, int]]]:
        paths: list[list[tuple[int, int]]] = []
        rng = random.Random()
        rng.seed(random.randint(0, 999999))
        for _ in range(4):
            x = rng.randint(5, 14)
            y = rng.randint(3, 8)
            path = [(x, y)]
            segments = rng.randint(3, 5)
            for _ in range(segments):
                x = max(2, min(17, x + rng.randint(-2, 2)))
                y = max(2, min(18, y + rng.randint(1, 3)))
                path.append((x, y))
            paths.append(path)
        return paths

    def _get_body_surface(self, angle_bucket: int, hit_active: bool) -> pygame.Surface:
        cache_key = (hit_active, angle_bucket)
        cached_surface = self._body_surface_cache.get(cache_key)
        if cached_surface is None:
            cached_surface = pygame.Surface(
                (self.LOW_RES_SIZE, self.LOW_RES_SIZE), pygame.SRCALPHA
            )
            rad = math.radians(angle_bucket)
            cr = math.cos(rad)
            sr = math.sin(rad)
            cx = self.LOW_RES_SIZE / 2
            cy = self.LOW_RES_SIZE / 2

            rotated_pts = [
                (
                    cx + (px * cr - py * sr) * self._shape_scale,
                    cy + (px * sr + py * cr) * self._shape_scale,
                )
                for px, py in self.points
            ]

            draw_color = colors.WHITE if hit_active else self.color
            outline_color = colors.WHITE if hit_active else colors.BLACK

            pygame.draw.polygon(cached_surface, draw_color, rotated_pts)
            pygame.draw.polygon(cached_surface, outline_color, rotated_pts, 1)

            inner_pts = [
                (px * 0.88 + cx * 0.12, py * 0.88 + cy * 0.12) for px, py in rotated_pts
            ]
            pygame.draw.polygon(
                cached_surface,
                tuple(max(0, c - 12) for c in draw_color),
                inner_pts,
                0,
            )

            if len(self._body_surface_cache) >= 120:
                self._body_surface_cache.clear()
            self._body_surface_cache[cache_key] = cached_surface

        return cached_surface

    @classmethod
    def _get_eye_sprite(
        cls,
        eye_fill: tuple[int, int, int],
        eye_ring: tuple[int, int, int],
    ) -> pygame.Surface:
        cache_key = (eye_fill, eye_ring)
        cached_sprite = cls._eye_sprite_cache.get(cache_key)
        if cached_sprite is None:
            cached_sprite = pygame.Surface((12, 12), pygame.SRCALPHA)
            pygame.draw.rect(cached_sprite, eye_ring, (2, 5, 8, 2))
            pygame.draw.rect(cached_sprite, eye_ring, (5, 2, 2, 8))
            pygame.draw.rect(cached_sprite, eye_fill, (3, 5, 6, 2))
            pygame.draw.rect(cached_sprite, eye_fill, (5, 3, 2, 6))
            pygame.draw.rect(cached_sprite, (255, 255, 255), (5, 5, 2, 2))
            cls._eye_sprite_cache[cache_key] = cached_sprite
        return cached_sprite

    @classmethod
    def _get_particle_surface(
        cls,
        color: tuple[int, int, int],
        size: int,
        alpha: float,
    ) -> pygame.Surface:
        alpha_value = max(0, min(255, int(255 * alpha)))
        alpha_bucket = (
            alpha_value // cls._particle_alpha_step
        ) * cls._particle_alpha_step
        cache_key = (color, size, alpha_bucket)
        cached_surface = cls._particle_surface_cache.get(cache_key)
        if cached_surface is None:
            cached_surface = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            pygame.draw.rect(
                cached_surface,
                (*color, alpha_bucket),
                (0, 0, size * 2, size * 2),
            )
            cls._particle_surface_cache[cache_key] = cached_surface
        return cached_surface

    def _update_player_tracking(
        self, dt: float, player_pos: Tuple[float, float]
    ) -> None:
        """Estimativa simples de velocidade do jogador para mira preditiva."""
        if dt <= 0.0:
            return

        if self._player_last_pos is None:
            self._player_last_pos = player_pos
            self._player_velocity = (0.0, 0.0)
            return

        vx = (player_pos[0] - self._player_last_pos[0]) / dt
        vy = (player_pos[1] - self._player_last_pos[1]) / dt

        # Evita saltos absurdos de estimativa por variação de frame.
        max_speed = 520.0
        vx = max(-max_speed, min(max_speed, vx))
        vy = max(-max_speed, min(max_speed, vy))

        self._player_velocity = (vx, vy)
        self._player_last_pos = player_pos

    def _launch_jump(self, player_pos: Tuple[float, float]) -> None:
        """Lança uma parábola simples em direção a qualquer ponto da tela."""
        self._jump_count += 1
        min_y = 30.0
        max_y = Config.SCREEN_HEIGHT - self.h - 30.0
        min_x = 20.0
        max_x = Config.SCREEN_WIDTH - self.w - 20.0

        follow = random.random() < (0.55 if self._jump_count % 4 != 0 else 0.25)
        if follow and player_pos:
            land_x = player_pos[0] + random.uniform(-100.0, 100.0)
            land_y = player_pos[1] + random.uniform(-80.0, 80.0)
        else:
            land_x = random.uniform(min_x, max_x)
            land_y = random.uniform(min_y, max_y)

        cx = self.x + self.w / 2
        cy = self.y + self.h / 2

        land_x = max(min_x, min(max_x, land_x))
        land_y = max(min_y, min(max_y, land_y))

        # Reduz 25% da distância do salto para evitar parábolas muito longas.
        land_x = cx + (land_x - cx) * 0.75
        land_y = cy + (land_y - cy) * 0.75
        land_x = max(min_x, min(max_x, land_x))
        land_y = max(min_y, min(max_y, land_y))
        self._land_y = land_y

        dx = land_x - cx
        dy = land_y - cy
        dist = math.sqrt(dx * dx + dy * dy)
        flight_time = max(0.4, dist / random.uniform(300.0, 520.0))

        self._jump_gravity = random.uniform(260.0, 420.0)

        # vy inicial: resolve dy = vy*t + 0.5*g*t^2
        self._jump_vy = (
            dy - 0.5 * self._jump_gravity * flight_time * flight_time
        ) / flight_time
        self._jump_vx = dx / flight_time

        self._is_jumping = True
        self._land_duration = random.uniform(5.0, 8.0)

    def _update_combat_movement(
        self,
        dt: float,
        player_pos: Tuple[float, float],
        nearby_enemies: list[Any] | None = None,
    ) -> None:
        """Movimento de parábola simples com pouso no alvo."""
        min_y = 30.0
        max_y = Config.SCREEN_HEIGHT - self.h - 30.0

        if self._is_jumping:
            self._jump_vy += self._jump_gravity * dt
            self._jump_vy = min(self._jump_vy, self.MAX_FALL_VELOCITY)

            self.x += self._jump_vx * dt
            self.y += self._jump_vy * dt

            if self.x < self.EDGE_MARGIN:
                self.x = self.EDGE_MARGIN
                self._jump_vx = abs(self._jump_vx) * self.BOUNCE_DAMPING_HORIZONTAL
            elif self.x + self.w > Config.SCREEN_WIDTH - self.EDGE_MARGIN:
                self.x = Config.SCREEN_WIDTH - self.EDGE_MARGIN - self.w
                self._jump_vx = -abs(self._jump_vx) * self.BOUNCE_DAMPING_HORIZONTAL

            if self.y < min_y:
                self.y = min_y
                self._jump_vy = abs(self._jump_vy) * self.BOUNCE_DAMPING_VERTICAL

            # Pouso: está descendo e cruzou o alvo
            if self._jump_vy > 0 and self.y >= self._land_y:
                self.y = self._land_y
                self._jump_vx = 0.0
                self._jump_vy = 0.0
                self._is_jumping = False
                self._land_timer = 0.0

            # Failsafe: chegou no fundo sem pousar
            if self.y >= max_y:
                self.y = max_y
                self._jump_vx = 0.0
                self._jump_vy = 0.0
                self._is_jumping = False
                self._land_timer = 0.0
        else:
            self._land_timer += dt
            # Só permite salto se não estiver ativamente carregando/disparando
            # Carregamento acontece quando: 0 < shoot_timer <= charge_duration
            if self._land_timer >= self._land_duration and not (
                0 < self.shoot_timer <= self.charge_duration
            ):
                self._launch_jump(player_pos)

        # Repulsão entre StoneSentry próximos
        if nearby_enemies:
            center_x = self.x + self.w / 2
            center_y = self.y + self.h / 2
            for other in nearby_enemies:
                if other is self or not isinstance(other, StoneSentry):
                    continue
                other_cx = other.x + other.w / 2
                other_cy = other.y + other.h / 2
                dist_x = other_cx - center_x
                dist_y = other_cy - center_y
                dist = math.sqrt(dist_x * dist_x + dist_y * dist_y)
                if 0 < dist < self.REPULSION_RADIUS:
                    force = (1.0 - dist / self.REPULSION_RADIUS) * self.REPULSION_FORCE
                    self.x -= (dist_x / dist) * force * dt
                    self.y -= (dist_y / dist) * force * dt

        self.x = max(8.0, min(Config.SCREEN_WIDTH - self.w - 8.0, self.x))
        self.y = max(min_y, min(max_y, self.y))

    def _get_claw_tips(self) -> tuple[tuple[float, float], tuple[float, float]]:
        body_cx = self.x + self.w / 2 + self.shake_offset_x
        body_bottom = self.y + self.h * 0.55 + self.shake_offset_y
        sway = math.sin(self.pulse_timer * 1.6 + self._arm_phase) * 4.0 * self._arm_sway

        c_ratio = self.charge_ratio
        arm_open = self._arm_open_progress
        arm_stretch = self._arm_impulse_stretch
        flex_x = c_ratio * 8.0 + arm_open * 15.0 + abs(self._arm_dyn_x) * 0.8
        flex_y = c_ratio * 12.0 + arm_open * 4.0

        left_base_x = body_cx - self.w * 0.28 - flex_x + self._arm_dyn_x
        right_base_x = body_cx + self.w * 0.28 + flex_x + self._arm_dyn_x
        base_y = body_bottom + 2 + self._arm_dyn_y

        arm_len = self.h * (0.95 + 0.48 * arm_open + 0.30 * arm_stretch)

        left_tip = (
            left_base_x - (4 + arm_open * 11.0 + arm_stretch * 6.0) + sway,
            base_y + arm_len - self._recoil_left - flex_y,
        )
        right_tip = (
            right_base_x + (4 + arm_open * 11.0 + arm_stretch * 6.0) - sway,
            base_y + arm_len - self._recoil_right - flex_y,
        )
        return left_tip, right_tip

    def _draw_stone_arms(self, screen: pygame.Surface) -> None:
        body_cx = self.x + self.w / 2 + self.shake_offset_x
        body_bottom = self.y + self.h * 0.55 + self.shake_offset_y
        sway = math.sin(self.pulse_timer * 1.6 + self._arm_phase) * 4.0 * self._arm_sway

        c_ratio = self.charge_ratio
        arm_open = self._arm_open_progress
        arm_stretch = self._arm_impulse_stretch
        flex_x = c_ratio * 8.0 + arm_open * 15.0 + abs(self._arm_dyn_x) * 0.8

        left_base = (
            body_cx - self.w * 0.28 - flex_x + self._arm_dyn_x,
            body_bottom + 2 + self._arm_dyn_y,
        )
        right_base = (
            body_cx + self.w * 0.28 + flex_x + self._arm_dyn_x,
            body_bottom + 2 + self._arm_dyn_y,
        )

        left_tip, right_tip = self._get_claw_tips()

        # Quanto mais aberto, menor a curvatura: braço quase em linha reta.
        bend = 8.0 * (1.0 - arm_open) + 1.2
        left_joint = (
            left_base[0] * 0.45 + left_tip[0] * 0.55 - bend + sway * 0.25,
            left_base[1] * 0.45
            + left_tip[1] * 0.55
            - (6.0 * (1.0 - arm_open))
            - arm_stretch * 2.0,
        )
        right_joint = (
            right_base[0] * 0.45 + right_tip[0] * 0.55 + bend - sway * 0.25,
            right_base[1] * 0.45
            + right_tip[1] * 0.55
            - (6.0 * (1.0 - arm_open))
            - arm_stretch * 2.0,
        )

        # Paleta: braços mais claros, garras na cor base da sentinela.
        arm_col = tuple(min(255, c + 24) for c in self.color)
        arm_high = tuple(min(255, c + 44) for c in self.color)
        claw_col = self.color
        claw_high = tuple(min(255, c + 22) for c in self.color)

        # Função auxiliar para desenhar um único braço flutuante
        def draw_floating_arm(
            base: tuple[float, float],
            joint: tuple[float, float],
            tip: tuple[float, float],
            is_left: bool,
        ) -> None:
            border_w = 2

            def draw_rock(cx: float, cy: float, size: float, phase: float) -> None:
                wobble_x = math.sin(self.pulse_timer * 3.5 + phase) * 0.9
                wobble_y = math.cos(self.pulse_timer * 3.0 + phase * 0.8) * 0.8
                w = max(
                    3, int(size * (1.55 + 0.14 * math.sin(phase + self.pulse_timer)))
                )
                h = max(
                    3,
                    int(
                        size * (1.35 + 0.16 * math.cos(phase * 0.7 + self.pulse_timer))
                    ),
                )
                rect = pygame.Rect(
                    int(cx + wobble_x - w / 2), int(cy + wobble_y - h / 2), w, h
                )
                pygame.draw.ellipse(screen, arm_col, rect)
                pygame.draw.ellipse(screen, colors.BLACK, rect, border_w)
                inner_rect = rect.inflate(-2, -2)
                if inner_rect.width > 0 and inner_rect.height > 0:
                    pygame.draw.ellipse(screen, arm_high, inner_rect, 1)

            # 1) Desenhar garras primeiro (ficam atrás do braço)
            # Núcleo da garra em tom de pedra levemente diferente
            claw_w = 14
            claw_h = 12
            claw_base = pygame.Rect(
                int(tip[0] - claw_w / 2),
                int(tip[1] - claw_h / 2),
                claw_w,
                claw_h,
            )
            pygame.draw.ellipse(screen, claw_col, claw_base)
            pygame.draw.ellipse(screen, colors.BLACK, claw_base, border_w)
            claw_high_rect = claw_base.inflate(-4, -4)
            if claw_high_rect.width > 0 and claw_high_rect.height > 0:
                pygame.draw.ellipse(screen, claw_high, claw_high_rect, 1)

            # Desenhar as pinças formando o "C" virado para dentro
            dir_mod = 1 if is_left else -1
            claw_open = 2.0 + 9.0 * arm_open + 3.0 * arm_stretch

            # Ponto superior e inferior da pinça
            p1: tuple[float, float] = (
                tip[0] + dir_mod * (10 + claw_open),
                tip[1] - 8 - arm_open * 2.0,
            )
            p2: tuple[float, float] = (
                tip[0] + dir_mod * (12 + claw_open),
                tip[1] + 10 + arm_open * 2.0,
            )

            # Pinças segmentadas em pedras (irregulares) com cor própria
            upper_mid = (
                tip[0] + dir_mod * (5.5 + claw_open * 0.5),
                tip[1] - 4.0 - arm_open,
            )
            lower_mid = (
                tip[0] + dir_mod * (6.0 + claw_open * 0.5),
                tip[1] + 5.0 + arm_open,
            )
            for idx, node in enumerate((upper_mid, p1)):
                seg = pygame.Rect(int(node[0] - 3.0), int(node[1] - 2.5), 6, 5)
                pygame.draw.ellipse(screen, claw_col, seg)
                pygame.draw.ellipse(screen, colors.BLACK, seg, border_w)
                seg_high = seg.inflate(-2, -2)
                if seg_high.width > 0 and seg_high.height > 0:
                    pygame.draw.ellipse(screen, claw_high, seg_high, 1)
                if idx == 0:
                    pygame.draw.line(screen, claw_col, tip, node, 4)
                    pygame.draw.line(screen, colors.BLACK, tip, node, border_w)
                    pygame.draw.line(screen, claw_high, tip, node, 1)
            for idx, node in enumerate((lower_mid, p2)):
                seg = pygame.Rect(int(node[0] - 3.0), int(node[1] - 2.5), 6, 5)
                pygame.draw.ellipse(screen, claw_col, seg)
                pygame.draw.ellipse(screen, colors.BLACK, seg, border_w)
                seg_high = seg.inflate(-2, -2)
                if seg_high.width > 0 and seg_high.height > 0:
                    pygame.draw.ellipse(screen, claw_high, seg_high, 1)
                if idx == 0:
                    pygame.draw.line(screen, claw_col, tip, node, 4)
                    pygame.draw.line(screen, colors.BLACK, tip, node, border_w)
                    pygame.draw.line(screen, claw_high, tip, node, 1)

            # 2) Desenhar as pedras do braço por cima
            # Vamos colocar 3 fragmentos entre a base e a ponta
            pts: list[tuple[float, float]] = [
                (
                    base[0] * 0.65 + joint[0] * 0.35,
                    base[1] * 0.65 + joint[1] * 0.35,
                ),  # Perto do corpo
                (joint[0], joint[1]),  # O "cotovelo"
                (
                    joint[0] * 0.35 + tip[0] * 0.65,
                    joint[1] * 0.35 + tip[1] * 0.65,
                ),  # Perto da garra
            ]

            # 2. Desenhar as pedras flutuantes com oscilação independente
            for i, (px, py) in enumerate(pts):
                # Magia matemática: cada pedra flutua um pouco diferente da outra
                float_y = math.sin(self.pulse_timer * 4.0 + i * 1.5) * 2.5
                float_x = math.cos(self.pulse_timer * 3.0 + i * 1.5) * 1.5

                # A pedra do meio (cotovelo) é ligeiramente maior
                size = 5 if i == 1 else 4
                draw_rock(px + float_x, py + float_y, size, i * 1.7)

        # Renderizar braço esquerdo e direito
        draw_floating_arm(left_base, left_joint, left_tip, is_left=True)
        draw_floating_arm(right_base, right_joint, right_tip, is_left=False)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(
        self,
        dt: float,
        player_pos: Tuple[float, float] | None = None,
        nearby_enemies: list[Any] | None = None,
    ) -> List[AlienBullet]:
        if not self._entry_done:
            self.y += self.speed_y * dt
            if self.y >= self.target_y:
                self.y = float(self.target_y)
                self._entry_done = True
                self.float_offset = 0.0
        else:
            self.pulse_timer += dt

            if player_pos:
                self._update_player_tracking(dt, player_pos)
                self._update_combat_movement(dt, player_pos, nearby_enemies)
            else:
                # Sem jogador: flutua suavemente no lugar
                target_offset = (
                    math.sin(self.pulse_timer * self.float_frequency)
                    * self.float_amplitude
                )
                self.float_offset += (target_offset - self.float_offset) * min(
                    1.0, 8.0 * dt
                )
                self.y = self.target_y + self.float_offset

        # Fisica secundaria dos bracos: impulso, queda com balanco e retorno rapido no pouso.
        jump_started = self._is_jumping and not self._was_jumping
        jump_landed = (not self._is_jumping) and self._was_jumping

        if jump_started:
            self._arm_impulse_stretch = 1.0
            self._arm_dyn_vy += 140.0
            self._arm_dyn_vx += random.uniform(-90.0, 90.0)

        if jump_landed:
            self._arm_dyn_vy = -self._arm_dyn_vy * 0.45
            self._arm_dyn_vx *= 0.45

        if dt > 0.0:
            jump_accel = (
                (self._jump_vy - self._prev_jump_vy) / dt if self._is_jumping else 0.0
            )
            inertial_push = -jump_accel * 0.020

            if self._is_jumping and self._jump_vy > 0.0:
                # Na queda: bracos sobem e balancam.
                target_y = (
                    -14.0 + math.sin(self.pulse_timer * 7.5 + self._arm_phase) * 2.2
                )
                target_x = math.sin(self.pulse_timer * 9.0 + self._arm_phase) * 5.0
                settle_k = 26.0
                damping = 7.8
            elif self._is_jumping:
                # Subida/impulso: estica e desce levemente antes do follow-through.
                target_y = 7.5
                target_x = math.sin(self.pulse_timer * 6.0 + self._arm_phase) * 2.0
                settle_k = 20.0
                damping = 6.4
            else:
                # Pouso: retorno rapido para pose padrao.
                target_y = 0.0
                target_x = 0.0
                settle_k = 38.0
                damping = 10.5

            ay = (
                (target_y - self._arm_dyn_y) * settle_k
                - self._arm_dyn_vy * damping
                + inertial_push
            )
            ax = (target_x - self._arm_dyn_x) * (settle_k * 0.70) - self._arm_dyn_vx * (
                damping * 0.90
            )

            self._arm_dyn_vy += ay * dt
            self._arm_dyn_vx += ax * dt
            self._arm_dyn_y += self._arm_dyn_vy * dt
            self._arm_dyn_x += self._arm_dyn_vx * dt

        self._arm_dyn_y = max(-20.0, min(14.0, self._arm_dyn_y))
        self._arm_dyn_x = max(-10.0, min(10.0, self._arm_dyn_x))
        self._arm_impulse_stretch = max(0.0, self._arm_impulse_stretch - dt * 2.3)

        self._prev_jump_vy = self._jump_vy
        self._was_jumping = self._is_jumping

        target_open = 1.0 if self._is_jumping else 0.0
        delta_open = target_open - self._arm_open_progress
        max_step = self._arm_anim_speed * dt
        if abs(delta_open) <= max_step:
            self._arm_open_progress = target_open
        elif delta_open > 0:
            self._arm_open_progress += max_step
        else:
            self._arm_open_progress -= max_step

        self._arms_animating = (
            abs(self._arm_open_progress - target_open) > 0.001
            or abs(self._arm_dyn_y) > 0.35
            or abs(self._arm_dyn_x) > 0.35
            or abs(self._arm_dyn_vy) > 4.0
            or abs(self._arm_dyn_vx) > 4.0
            or self._arm_impulse_stretch > 0.03
        )
        self._claw_tips = self._get_claw_tips()

        self.rotation += self.rotation_speed * dt

        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        charge_boost = self.charge_ratio * 220.0
        target_spin_speed = 55.0 + charge_boost + self._eye_spin_boost
        self._eye_spin_speed += (target_spin_speed - self._eye_spin_speed) * min(
            1.0, 10.0 * dt
        )
        self._eye_rotation = (self._eye_rotation + self._eye_spin_speed * dt) % 360.0
        self._eye_spin_boost = max(0.0, self._eye_spin_boost - 260.0 * dt)

        self._recoil_left = max(0.0, self._recoil_left - 40.0 * dt)
        self._recoil_right = max(0.0, self._recoil_right - 40.0 * dt)

        bullets: List[AlienBullet] = []

        # Só inicia charging/disparo quando estiver pousado e com animacao dos bracos encerrada.
        if self._is_jumping or self._arms_animating:
            self._charging_bullet = None
        else:
            # Gerenciamento da criação do projétil enquanto carrega
            if 0 < self.shoot_timer <= self.charge_duration:
                if self._charging_bullet is None:
                    self._charging_bullet = StoneShardBullet(0, 0)
                    # Decide if super bullet (10% chance) na criação
                    self._is_super_bullet = (
                        random.random() < self.SUPER_PROJECTILE_CHANCE
                    )
                    if self._is_super_bullet:
                        scale = self.SUPER_PROJECTILE_SCALE
                        self._charging_bullet.current_radius = int(
                            self._charging_bullet.current_radius * scale
                        )
                        self._charging_bullet.min_radius = int(
                            self._charging_bullet.min_radius * scale
                        )
                        self._charging_bullet.max_radius = int(
                            self._charging_bullet.max_radius * scale
                        )
                        self._charging_bullet.hit_radius = int(
                            self._charging_bullet.hit_radius * scale
                        )

                # Gira o projétil enquanto ele é carregado para dar vida!
                self._charging_bullet.spin += self._charging_bullet.spin_speed * dt
            elif self.shoot_timer > self.charge_duration:
                self._charging_bullet = None
                self._is_super_bullet = False

            self.shoot_timer -= dt
            if self.shoot_timer <= 0 and not self.dead:
                bullets = self._shoot(player_pos)
                self.shoot_timer = random.uniform(3.2, 5.2)
                self._shoot_cycle = self.shoot_timer

        if self.charge_ratio > 0.6:
            intensity = (self.charge_ratio - 0.6) * 15
            self.shake_offset_x = random.uniform(-intensity, intensity)
            self.shake_offset_y = random.uniform(-intensity, intensity)
        else:
            self.shake_offset_x = 0.0
            self.shake_offset_y = 0.0

        self._emit_particles(dt)
        self._update_particles(dt)

        return bullets

    def _emit_particles(self, dt: float) -> None:
        if random.random() > min(0.65, dt * 10.0):
            return

        px = self.x + self.w / 2 + random.uniform(-10, 10) + self.shake_offset_x
        py = self.y + self.h - 4 + self.shake_offset_y
        self._particles.append(
            Particle(
                x=px,
                y=py,
                vx=random.uniform(-15, 15),
                vy=random.uniform(60, 120),
                size=random.randint(2, 4),
                lifetime=random.uniform(0.3, 0.7),
            )
        )

    def _update_particles(self, dt: float) -> None:
        updated_particles: list[Particle] = []
        for particle in self._particles:
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            particle.lifetime -= dt
            if particle.lifetime > 0 and particle.y < Config.SCREEN_HEIGHT + 20:
                updated_particles.append(particle)
        self._particles = updated_particles

    def _shoot(self, player_pos: Tuple[float, float] | None) -> List[AlienBullet]:
        left_tip, right_tip = self._claw_tips or self._get_claw_tips()

        bx = (left_tip[0] + right_tip[0]) / 2
        by = (left_tip[1] + right_tip[1]) / 2

        self._recoil_left = 25.0
        self._recoil_right = 25.0
        self._eye_spin_boost = max(self._eye_spin_boost, 220.0)

        sound_manager.play_shot()

        # Pega a instância que estava sendo carregada (ou cria uma emergencial)
        if self._charging_bullet:
            bullet = self._charging_bullet
            self._charging_bullet = None
        else:
            bullet = StoneShardBullet(bx, by)

        if random.random() < self.SUPER_PROJECTILE_CHANCE:
            scale = self.SUPER_PROJECTILE_SCALE
            bullet.current_radius = int(bullet.current_radius * scale)
            bullet.min_radius = int(bullet.min_radius * scale)
            bullet.max_radius = int(bullet.max_radius * scale)
            bullet.hit_radius = int(bullet.hit_radius * scale)

        bullet.x = bx
        bullet.y = by

        if player_pos:
            lead_time = 0.24
            target_x = player_pos[0] + self._player_velocity[0] * lead_time
            target_y = player_pos[1] + self._player_velocity[1] * lead_time
            target_x = max(0.0, min(float(Config.SCREEN_WIDTH), target_x))
            target_y = max(0.0, min(float(Config.SCREEN_HEIGHT), target_y))

            dx = target_x - bx
            dy = target_y - by
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > 0:
                bullet.vx = (dx / dist) * 290.0
                bullet.vy = (dy / dist) * 290.0
        else:
            bullet.vx = 0.0
            bullet.vy = 330.0

        return [bullet]

    def draw(self, screen: pygame.Surface):
        angle_bucket = int(self.rotation / 6.0) * 6 % 360
        body_surface = self._get_body_surface(angle_bucket, self.hit_timer > 0.0)
        self._low_res_surface.fill((0, 0, 0, 0))
        self._low_res_surface.blit(body_surface, (0, 0))

        eye_cx, eye_cy = self.LOW_RES_SIZE // 2, self.LOW_RES_SIZE // 2
        if self.hit_timer > 0.0:
            eye_fill = (255, 0, 0)
            eye_ring = (255, 255, 255)
        else:
            c_ratio = self.charge_ratio
            if c_ratio > 0:
                eye_fill = (
                    int(190 + 65 * c_ratio),
                    int(80 + 100 * c_ratio),
                    int(60 + 60 * c_ratio),
                )
                eye_ring = (255, 220, 170)
            else:
                eye_fill = (255, 246, 210)
                eye_ring = (255, 197, 120)

        eye_sprite = self._get_eye_sprite(eye_fill, eye_ring)
        rotated_eye = pygame.transform.rotate(eye_sprite, self._eye_rotation)
        eye_rect = rotated_eye.get_rect(center=(eye_cx, eye_cy))
        self._low_res_surface.blit(rotated_eye, eye_rect)

        if self.health < 15:
            crack_col = colors.BLACK if self.hit_timer <= 0.0 else colors.WHITE
            crack_count = 2 if self.health >= 9 else 4
            for path in self._crack_paths[:crack_count]:
                pygame.draw.lines(self._low_res_surface, crack_col, False, path, 1)
                if self.health < 9:
                    glow = (205, 120, 70) if self.hit_timer <= 0.0 else (255, 220, 190)
                    pygame.draw.lines(self._low_res_surface, glow, False, path, 1)

        scaled_surface = pygame.transform.scale(self._low_res_surface, (self.w, self.h))
        draw_x = int(self.x + self.shake_offset_x)
        draw_y = int(self.y + self.shake_offset_y)
        screen.blit(scaled_surface, (draw_x, draw_y))

        self._draw_stone_arms(screen)

        # Desenha O MESMO PROJÉTIL crescendo e tremendo entre as garras
        c_ratio = self.charge_ratio
        if c_ratio > 0.1 and self._charging_bullet:
            left_tip, right_tip = self._get_claw_tips()

            # Tremor específico do projétil durante o charging (maior para super)
            rock_shake = c_ratio * (8.0 if self._is_super_bullet else 4.0)
            rock_cx = (left_tip[0] + right_tip[0]) / 2 + random.uniform(
                -rock_shake, rock_shake
            )
            rock_cy = (left_tip[1] + right_tip[1]) / 2 + random.uniform(
                -rock_shake, rock_shake
            )

            # Rotaciona a superfície base do projétil em tempo real
            rock_surf = pygame.transform.rotate(
                self._charging_bullet.get_render_surface(), self._charging_bullet.spin
            )

            # Calcula o tamanho atual baseado no charge_ratio (mais rápido para super)
            final_diameter = max(16, int(self._charging_bullet.current_radius) * 2)
            if self._is_super_bullet:
                # For super bullets: start appearing at 50% charge, fill by 100%
                current_diameter = max(2, int(final_diameter * (0.5 + 0.5 * c_ratio)))
            else:
                # Normal bullets: linear growth from 0% to 100%
                current_diameter = max(2, int(final_diameter * c_ratio))

            # Redimensiona e desenha a textura real
            scaled_rock = pygame.transform.scale(
                rock_surf, (current_diameter, current_diameter)
            )
            screen.blit(
                scaled_rock,
                (
                    int(rock_cx) - current_diameter // 2,
                    int(rock_cy) - current_diameter // 2,
                ),
            )

        for particle in self._particles:
            # Calcula alpha como proporção de lifetime restante
            alpha = min(
                1.0, particle.lifetime / 0.7
            )  # Normaliza para lifetime máx de 0.7s
            particle_surf = self._get_particle_surface(self.color, particle.size, alpha)
            screen.blit(
                particle_surf,
                (int(particle.x) - particle.size, int(particle.y) - particle.size),
            )

    def get_points_value(self) -> int:
        return 250

    def take_damage(self, amount: int):
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self.dead = True

    def collision_circle(self) -> tuple[float, float, float]:
        r = self.rect
        return r.centerx, r.centery, max(r.width, r.height) / 2

    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=45,
                sound=hit_sounds.EXPLOSION_ALIEN,
            )
        return HitResult(explosion_size=10, sound=hit_sounds.BOSS_DAMAGE)

    def on_ship_contact(self, contact_x: float, contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead
