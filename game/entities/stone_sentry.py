import math
import random
from typing import List, Tuple

import pygame

from ..core import colors
from ..core.config import config as Config
from ..entities.alien_bullet import AlienBullet


class StoneShardBullet(AlienBullet):
    """Projétil de pedra da Stone Sentry, com textura mais granular."""

    STONE_BULLET_COLORS = [
        (78, 60, 46),
        (112, 88, 66),
        (142, 118, 92),
        (60, 56, 54),
    ]

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
        self.min_radius = 10
        self.max_radius = 10
        self.current_radius = 10
        self.hit_radius = 12
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

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.spin += self.spin_speed * dt

        if self.y > self.screen_h + 80 or self.x < -80 or self.x > self.screen_w + 80:
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        diameter = max(16, int(self.current_radius) * 2)
        rock_surface = pygame.transform.rotate(self._surface_cache, self.spin)
        scaled_surface = pygame.transform.scale(rock_surface, (diameter, diameter))
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
    Flutua até uma posição e dispara projéteis contra o jogador.
    """

    # Cores de pedra (baseadas no Stone Golem Boss)
    STONE_COLORS = [
        (70, 52, 38),    # Basalto quente
        (95, 72, 52),    # Rocha marrom
        (125, 98, 70),   # Argila escura
        (150, 124, 98),  # Pedra iluminada
        (82, 82, 82),    # Cinza ardosia
    ]
    ACCENT_COLORS = [
        (185, 108, 68),
        (206, 126, 74),
        (230, 160, 104),
    ]
    
    EXPLOSION_COLORS = [(130, 110, 80), (100, 100, 100), (255, 60, 60)]
    LOW_RES_SIZE = 20

    def __init__(self):
        # Dimensões
        self.w = 40
        self.h = 40
        
        # Posição inicial (entra pelo topo)
        self.x = random.randint(50, Config.SCREEN_WIDTH - 50 - self.w)
        self.y = -self.h
        
        # Alvo de repouso (parte superior da tela)
        self.target_y = random.randint(50, 200)
        self.speed_y = 150.0
        self.float_amplitude = 10.0
        self.float_frequency = 2.0
        self.float_offset = 0.0
        self._entry_done = False
        
        # Estado
        self.dead = False
        self.health = 30 # Mais resistente que um alien comum
        self.active = True
        self.hit_timer = 0.0
        
        # Timers de tiro
        self.shoot_timer = random.uniform(2.0, 4.0)
        self._shoot_cycle = self.shoot_timer
        
        # Visual
        self.rotation = 0.0
        self.rotation_speed = random.uniform(-30, 30)
        self.points = self._generate_stone_shape()
        self.color = random.choice(self.STONE_COLORS)
        self.eye_color = colors.RED
        self.accent_color = random.choice(self.ACCENT_COLORS)
        self.pulse_timer = 0.0
        self._shape_scale = (self.LOW_RES_SIZE - 2) / self.w
        self._low_res_surface = pygame.Surface(
            (self.LOW_RES_SIZE, self.LOW_RES_SIZE), pygame.SRCALPHA
        )
        self._particles: list[list[float]] = []
        self._crack_paths = self._generate_crack_paths()
        self._arm_phase = random.uniform(0.0, math.tau)
        self._arm_sway = random.uniform(0.65, 1.0)
        self._next_shot_left = random.choice([True, False])

    def _generate_stone_shape(self) -> List[Tuple[float, float]]:
        """Gera um formato de pedra irregular (octaedro imperfeito)."""
        pts: List[Tuple[float, float]] = []
        num_points = 8
        size = self.w // 2
        for i in range(num_points):
            ang = (2 * math.pi * i) / num_points
            # Irregularidade
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

    def _get_claw_tips(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Retorna as posições das pontas das garras (esquerda, direita)."""
        body_cx = self.x + self.w / 2
        body_bottom = self.y + self.h * 0.55
        sway = math.sin(self.pulse_timer * 1.6 + self._arm_phase) * 4.0 * self._arm_sway

        left_base_x = body_cx - self.w * 0.28
        right_base_x = body_cx + self.w * 0.28
        base_y = body_bottom + 2

        arm_len = self.h * 0.95

        left_tip = (left_base_x - 4 + sway, base_y + arm_len)
        right_tip = (right_base_x + 4 - sway, base_y + arm_len)
        return left_tip, right_tip

    def _draw_stone_arms(self, screen: pygame.Surface) -> None:
        body_cx = self.x + self.w / 2
        body_bottom = self.y + self.h * 0.55
        sway = math.sin(self.pulse_timer * 1.6 + self._arm_phase) * 4.0 * self._arm_sway

        left_base = (body_cx - self.w * 0.28, body_bottom + 2)
        right_base = (body_cx + self.w * 0.28, body_bottom + 2)

        left_joint = (left_base[0] - 4 + sway * 0.5, left_base[1] + self.h * 0.45)
        right_joint = (right_base[0] + 4 - sway * 0.5, right_base[1] + self.h * 0.45)

        left_tip, right_tip = self._get_claw_tips()

        arm_col = tuple(max(0, c - 22) for c in self.color)
        arm_high = tuple(min(255, c + 18) for c in self.color)

        pygame.draw.line(screen, arm_col, left_base, left_joint, 6)
        pygame.draw.line(screen, arm_col, left_joint, left_tip, 6)
        pygame.draw.line(screen, arm_col, right_base, right_joint, 6)
        pygame.draw.line(screen, arm_col, right_joint, right_tip, 6)

        pygame.draw.line(screen, arm_high, left_base, left_joint, 2)
        pygame.draw.line(screen, arm_high, right_base, right_joint, 2)

        # Garras estilo caranguejo: duas pinças por braço, abertas para fora.
        left_pincer_a = (left_tip[0] - 8, left_tip[1] - 5)
        left_pincer_b = (left_tip[0] - 9, left_tip[1] + 5)
        right_pincer_a = (right_tip[0] + 8, right_tip[1] - 5)
        right_pincer_b = (right_tip[0] + 9, right_tip[1] + 5)

        pygame.draw.line(screen, arm_col, left_tip, left_pincer_a, 5)
        pygame.draw.line(screen, arm_col, left_tip, left_pincer_b, 5)
        pygame.draw.line(screen, arm_col, right_tip, right_pincer_a, 5)
        pygame.draw.line(screen, arm_col, right_tip, right_pincer_b, 5)

        pygame.draw.line(screen, self.accent_color, left_tip, left_pincer_a, 2)
        pygame.draw.line(screen, self.accent_color, right_tip, right_pincer_a, 2)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float, player_pos: Tuple[float, float] | None = None) -> List[AlienBullet] | None:
        # Movimento de entrada
        if not self._entry_done:
            self.y += self.speed_y * dt
            if self.y >= self.target_y:
                self.y = float(self.target_y)
                self._entry_done = True
                self.float_offset = 0.0
        else:
            # Flutuação senoidal com suavização para evitar tremor visual.
            self.pulse_timer += dt
            target_offset = math.sin(self.pulse_timer * self.float_frequency) * self.float_amplitude
            self.float_offset += (target_offset - self.float_offset) * min(1.0, 8.0 * dt)
            self.y = self.target_y + self.float_offset
            
        # Rotação lenta
        self.rotation += self.rotation_speed * dt

        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        self._emit_particles(dt)
        self._update_particles(dt)
        
        # Atirar
        self.shoot_timer -= dt
        bullets = None
        if self.shoot_timer <= 0 and not self.dead:
            bullets = self._shoot(player_pos)
            self.shoot_timer = random.uniform(2.5, 4.5)
            self._shoot_cycle = self.shoot_timer
            
        return bullets

    def _emit_particles(self, dt: float) -> None:
        if self.y >= self.target_y:
            return

        if random.random() > min(0.55, dt * 8.0):
            return

        px = self.x + self.w / 2 + random.uniform(-6, 6)
        py = self.y + self.h - 4
        self._particles.append(
            [
                px,
                py,
                random.uniform(-10, 10),
                random.uniform(60, 120),
                random.randint(2, 3),
                random.uniform(0.25, 0.5),
            ]
        )

    def _update_particles(self, dt: float) -> None:
        updated_particles: list[list[float]] = []
        for particle in self._particles:
            particle[0] += particle[2] * dt
            particle[1] += particle[3] * dt
            particle[5] -= dt
            if particle[5] > 0 and particle[1] < Config.SCREEN_HEIGHT + 20:
                updated_particles.append(particle)
        self._particles = updated_particles

    def _shoot(self, player_pos: Tuple[float, float] | None) -> List[AlienBullet]:
        """Dispara um projétil na direção do jogador ou para baixo."""
        left_tip, right_tip = self._get_claw_tips()
        if self._next_shot_left:
            bx, by = left_tip
        else:
            bx, by = right_tip
        self._next_shot_left = not self._next_shot_left
        
        bullet = StoneShardBullet(bx, by)
        
        if player_pos:
            # Mirar no jogador
            dx = player_pos[0] - bx
            dy = player_pos[1] - by
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > 0:
                bullet.vx = (dx / dist) * 300.0
                bullet.vy = (dy / dist) * 300.0
        else:
            bullet.vx = 0.0
            bullet.vy = 350.0
            
        return [bullet]

    def draw(self, screen: pygame.Surface):
        # Calcular pontos rotacionados
        rad = math.radians(self.rotation)
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

        self._low_res_surface.fill((0, 0, 0, 0))

        draw_color = colors.WHITE if self.hit_timer > 0.0 else self.color
        outline_color = colors.WHITE if self.hit_timer > 0.0 else colors.BLACK

        # Corpo em baixa resolução para obter bordas blocky ao escalar
        pygame.draw.polygon(self._low_res_surface, draw_color, rotated_pts)
        pygame.draw.polygon(self._low_res_surface, outline_color, rotated_pts, 1)

        inner_pts = [
            (px * 0.88 + cx * 0.12, py * 0.88 + cy * 0.12)
            for px, py in rotated_pts
        ]
        pygame.draw.polygon(
            self._low_res_surface,
            tuple(max(0, c - 12) for c in draw_color),
            inner_pts,
            0,
        )
        pygame.draw.line(self._low_res_surface, self.accent_color, (6, 6), (13, 5), 1)
        pygame.draw.line(self._low_res_surface, self.accent_color, (7, 11), (14, 9), 1)

        eye_cx, eye_cy = int(cx), int(cy)
        if self.shoot_timer < 0.5:
            eye_radius = 7
            eye_fill = (255, 246, 210)
            eye_ring = (255, 197, 120)
        else:
            eye_pulse = (math.sin(self.pulse_timer * 5) + 1) / 2 # 0 a 1
            if self._shoot_cycle > 0:
                charge_ratio = 1.0 - max(0.0, min(1.0, self.shoot_timer / self._shoot_cycle))
            else:
                charge_ratio = 0.0
            intensity = 0.5 + 0.5 * eye_pulse
            if self.shoot_timer < 1.0:
                intensity = min(1.0, intensity + charge_ratio * 0.4)
            eye_fill = (
                int(190 + 55 * intensity),
                int(80 + 120 * intensity),
                int(60 + 80 * intensity),
            )
            eye_ring = (255, 220, 170)
            eye_radius = 5

        pygame.draw.circle(self._low_res_surface, eye_fill, (eye_cx, eye_cy), eye_radius)
        pygame.draw.circle(self._low_res_surface, eye_ring, (eye_cx, eye_cy), 2)
        pygame.draw.circle(self._low_res_surface, (255, 255, 255), (eye_cx, eye_cy), 1)

        if self.health < 15:
            crack_col = colors.BLACK if self.hit_timer <= 0.0 else colors.WHITE
            crack_count = 2 if self.health >= 9 else 4
            for path in self._crack_paths[:crack_count]:
                pygame.draw.lines(self._low_res_surface, crack_col, False, path, 1)
                if self.health < 9:
                    glow = (205, 120, 70) if self.hit_timer <= 0.0 else (255, 220, 190)
                    pygame.draw.lines(self._low_res_surface, glow, False, path, 1)

        scaled_surface = pygame.transform.scale(self._low_res_surface, (self.w, self.h))
        screen.blit(scaled_surface, (int(self.x), int(self.y)))

        self._draw_stone_arms(screen)

        for px, py, _, _, size, alpha in self._particles:
            particle_surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            pygame.draw.rect(
                particle_surf,
                (*self.color, int(255 * alpha)),
                (0, 0, size * 2, size * 2),
            )
            screen.blit(particle_surf, (int(px) - size, int(py) - size))

    def get_points_value(self) -> int:
        return 250

    def take_damage(self, amount: int):
        """Aplica dano à sentinela."""
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self.dead = True
