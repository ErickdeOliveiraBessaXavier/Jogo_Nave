"""Boss Square Projectile - Indestructible projectile launched by the boss."""

import math
import random
from typing import List

import pygame

from .draw_utils import draw_square_trail_particle, rotated_square_corners


class TrailParticle:
    """Partícula simples para efeito de cauda - otimizada."""

    __slots__ = ("x", "y", "size", "life", "alpha")

    def __init__(self, x: float, y: float, size: float):
        self.x = x
        self.y = y
        self.size = size
        self.life = 1.0  # 0.0 a 1.0
        self.alpha = 255


class BossSquare:
    """
    Indestructible square projectile launched by the boss in frenzy mode.

    Features:
    - Flies towards player with slight inaccuracy
    - Pulsating animation like power-ups
    - Cannot be destroyed by bullets
    - Causes damage on collision with player
    """

    def __init__(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        size: float,
        is_orbital: bool = False,
        orbit_radius: float = 0,
        orbit_angle: float = 0,
        orbit_speed: float = 0,
        speed_var: float = 1.0,
    ):
        """
        Initialize a boss square projectile.

        Args:
            x: Starting x position
            y: Starting y position
            vx: X velocity
            vy: Y velocity
            size: Base size of the square
            is_orbital: Whether this square orbits around the boss
            orbit_radius: Orbital radius if is_orbital
            orbit_angle: Initial orbital angle if is_orbital
            orbit_speed: Orbital speed if is_orbital
            speed_var: Speed variation for lerp if is_orbital
        """
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.base_size = size
        self.size = size
        self.dead = False

        # Orbital attributes
        self.is_orbital = is_orbital
        self.orbit_radius = orbit_radius
        self.orbit_angle = orbit_angle
        self.orbit_speed = orbit_speed
        self.orbit_speed_original = (
            orbit_speed  # Store original speed for frenzy acceleration
        )
        self.speed_var = speed_var
        self.state = "orbiting" if is_orbital else "flying"
        self.prepare_timer = 0.0
        self.frenzy_orbit_multiplier = (
            1.0  # Multiplicador de velocidade de órbita em frenzy
        )

        # Animation
        self.animation_timer = 0.0
        self.animation_offset = random.uniform(
            0, 10
        )  # Offset aleatório para dessincronizar animações
        self.rotation = 0.0  # Rotação contínua

        # Growth effect - aumenta conforme se move
        self.growth_timer = 0.0
        self.max_growth_scale = 4.5  # Crescimento máximo (2.5x do tamanho inicial)
        self.growth_duration = 2.0  # Tempo para atingir tamanho máximo (segundos)

        # Trail particles (otimizado - pool limitado)
        self.trail_particles: List[TrailParticle] = []
        self.trail_spawn_timer = 0.0
        self.trail_spawn_interval = 0.025  # Spawna partícula a cada 25ms
        self.max_trail_particles = 18  # Limite de partículas por quadrado

        # Animação da borda pixelada (compartilha timer com rotation para otimização)
        self.border_anim_offset: float = random.uniform(
            0, 100
        )  # Offset aleatório inicial

    def set_frenzy_mode(self, is_frenzy: bool) -> None:
        """Set frenzy mode and adjust orbital speed.

        Args:
            is_frenzy: True to activate frenzy mode (2x orbital speed), False to deactivate
        """
        if is_frenzy:
            # Acelerar órbita em 2x durante frenzy
            self.frenzy_orbit_multiplier = 2.0
        else:
            self.frenzy_orbit_multiplier = 1.0
        # Atualizar velocidade de órbita baseado no multiplicador
        self.orbit_speed = self.orbit_speed_original * self.frenzy_orbit_multiplier

    def update(
        self, dt: float, screen_width: int = 1600, screen_height: int = 900
    ) -> None:
        """
        Update position and animation.

        Args:
            dt: Delta time
            screen_width: Current screen width (for boundary check)
            screen_height: Current screen height (for boundary check)
        """
        # Move only if not orbital
        if not self.is_orbital:
            self.x += self.vx * dt
            self.y += self.vy * dt

        # Handle rotation based on state
        if self.state == "preparing":
            self.rotation += dt * 720  # Gira 720 graus por segundo
            self.border_anim_offset += dt * 25  # Animação rápida
        elif self.state == "orbiting":
            self.rotation = 0.0  # Sem rotação própria
            self.border_anim_offset += dt * 10  # Animação lenta
        else:
            self.rotation += dt * 360  # Rotação contínua para projéteis
            self.border_anim_offset += dt * 15  # Animação média

        # Efeito de crescimento progressivo (only for projectiles)
        if not self.is_orbital:
            self.growth_timer += dt
            growth_progress = min(self.growth_timer / self.growth_duration, 1.0)
            # Curva de crescimento suave (ease-out)
            growth_scale = 1.0 + (self.max_growth_scale - 1.0) * (
                1.0 - (1.0 - growth_progress) ** 2
            )
        else:
            growth_scale = 1.0  # No growth for orbital

        # Pulsation animation
        self.animation_timer += dt * 5
        if self.state == "preparing":
            pulse_scale = 1.0 + 0.4 * abs(math.sin(self.prepare_timer * 10))
            self.prepare_timer += dt
        else:
            # Usar offset para dessincronizar pulsação entre quadrados
            anim_value = (self.animation_timer + self.animation_offset) * 57.3
            pulse_scale = 1.0 + 0.2 * abs(
                pygame.math.Vector2(1, 0).rotate(anim_value).x
            )

        # Combina crescimento com pulsação
        self.size = self.base_size * growth_scale * pulse_scale

        # Atualizar partículas de trail (apenas para projéteis voando)
        if self.state == "flying":
            # Spawnar novas partículas
            self.trail_spawn_timer += dt
            if self.trail_spawn_timer >= self.trail_spawn_interval:
                self.trail_spawn_timer = 0.0
                # Spawna partícula atrás do quadrado
                if len(self.trail_particles) < self.max_trail_particles:
                    # Pequena variação aleatória na posição
                    offset_x = random.uniform(-self.size * 0.3, self.size * 0.3)
                    offset_y = random.uniform(-self.size * 0.3, self.size * 0.3)
                    particle = TrailParticle(
                        self.x + offset_x,
                        self.y + offset_y,
                        self.size * 0.4,  # Partícula começa menor que o quadrado
                    )
                    self.trail_particles.append(particle)

            # Atualizar partículas existentes
            decay_rate = 2.0  # Velocidade de decay (menor = mais longo)
            for p in self.trail_particles:
                p.life -= dt * decay_rate
                p.alpha = int(255 * max(0, p.life))
                p.size *= 0.97  # Encolhe mais devagar

            # Remover partículas mortas
            self.trail_particles = [p for p in self.trail_particles if p.life > 0]
        else:
            # Limpar partículas quando não está voando
            self.trail_particles.clear()

        # Remove if off-screen (only for projectiles)
        if not self.is_orbital:
            margin = 300  # Aumentado devido ao crescimento
            if (
                self.x < -margin
                or self.x > screen_width + margin
                or self.y < -margin
                or self.y > screen_height + margin
            ):
                self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the square projectile with rotation and trail."""
        if self.dead:
            return

        # Desenhar partículas de trail primeiro (atrás do quadrado)
        for p in self.trail_particles:
            if p.alpha > 0:
                color_intensity = int(128 + 127 * p.life)
                trail_color = (255, color_intensity, int(color_intensity * 0.5))
                draw_square_trail_particle(
                    surface, p.x, p.y, p.size, trail_color, p.alpha
                )

        # Calcular cor com intensidade alternada (usa offset para dessincronizar)
        anim_value = (self.animation_timer + self.animation_offset) * 57.3
        intensity = int(128 + 127 * abs(pygame.math.Vector2(1, 0).rotate(anim_value).x))
        color = (255, intensity, intensity)
        border_color = (255, 255, 255)

        rotated_corners = rotated_square_corners(
            self.x, self.y, self.size / 2, math.radians(self.rotation)
        )
        pygame.draw.polygon(surface, color, rotated_corners)
        self._draw_animated_border(surface, rotated_corners, border_color)

    def _draw_animated_border(
        self,
        surface: pygame.Surface,
        corners: list[tuple[float, float]],
        border_color: tuple[int, int, int],
    ) -> None:
        """Desenha borda com efeito de quadradinhos deslizando (otimizado)."""
        # Padrão simples para otimização
        pattern = [1, 1, 0, 1, 0]  # Padrão menor para quadrados pequenos
        pattern_len = len(pattern)

        # Tamanho do pixel baseado no tamanho do quadrado
        pixel_size = max(2, int(self.size / 8))
        half_pixel = pixel_size // 2

        # Offset animado
        anim_idx = int(self.border_anim_offset / pixel_size) % pattern_len

        # Desenhar cada aresta com padrão animado
        for i in range(4):
            start = corners[i]
            end = corners[(i + 1) % 4]

            # Calcular direção e comprimento da aresta
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length = math.sqrt(dx * dx + dy * dy)

            if length < 1:
                continue

            # Normalizar direção
            dx /= length
            dy /= length

            # Desenhar segmentos ao longo da aresta
            num_segments = max(1, int(length / pixel_size))
            for j in range(num_segments):
                # Alternar visibilidade baseado no padrão animado
                # Cada aresta tem offset diferente para criar efeito de rotação
                idx = (j + anim_idx + i * 2) % pattern_len
                if pattern[idx]:
                    t = j / num_segments
                    px = int(start[0] + dx * length * t)
                    py = int(start[1] + dy * length * t)
                    # Desenhar quadrado ao invés de círculo
                    pygame.draw.rect(
                        surface,
                        border_color,
                        (px - half_pixel, py - half_pixel, pixel_size, pixel_size),
                    )

    def get_rect(self) -> pygame.Rect:
        """Get collision rectangle."""
        half_size = self.size / 2
        return pygame.Rect(self.x - half_size, self.y - half_size, self.size, self.size)
