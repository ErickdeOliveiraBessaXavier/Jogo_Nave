import math
import random
from typing import List

import pygame


class TrailParticle:
    """Partícula simples para efeito de cauda - otimizada."""

    __slots__ = ("x", "y", "size", "life", "alpha")

    def __init__(self, x: float, y: float, size: float):
        self.x = x
        self.y = y
        self.size = size
        self.life = 1.0  # 0.0 a 1.0
        self.alpha = 255


class SquareProjectileBase:
    """Classe base para projéteis e inimigos quadrados com rastro e borda animada."""

    def __init__(self, x: float, y: float, size: float):
        self.x: float = x
        self.y: float = y
        self.base_size: float = size
        self.size: float = size
        self.dead: bool = False

        # Animação
        self.rotation: float = 0.0
        self.border_anim_offset: float = random.uniform(0, 100)

        # Trail particles
        self.trail_particles: List[TrailParticle] = []
        self.trail_spawn_timer: float = 0.0
        self.trail_spawn_interval: float = 0.025
        self.max_trail_particles: int = 18

    def _update_trail(self, dt: float, is_flying: bool) -> None:
        """Atualiza a geração e decaimento das partículas de trail."""
        if is_flying:
            # Spawnar novas partículas
            self.trail_spawn_timer += dt
            if self.trail_spawn_timer >= self.trail_spawn_interval:
                self.trail_spawn_timer = 0.0
                if len(self.trail_particles) < self.max_trail_particles:
                    offset_x = random.uniform(-self.size * 0.3, self.size * 0.3)
                    offset_y = random.uniform(-self.size * 0.3, self.size * 0.3)
                    particle = TrailParticle(
                        self.x + offset_x, self.y + offset_y, self.size * 0.4
                    )
                    self.trail_particles.append(particle)

            # Atualizar partículas existentes
            decay_rate = 2.0
            for p in self.trail_particles:
                p.life -= dt * decay_rate
                p.alpha = int(255 * max(0, p.life))
                p.size *= 0.97

            # Remover partículas mortas
            self.trail_particles = [p for p in self.trail_particles if p.life > 0]
        else:
            self.trail_particles.clear()

    def _draw_animated_border(
        self,
        surface: pygame.Surface,
        corners: list[tuple[float, float]],
        border_color: tuple[int, int, int],
    ) -> None:
        """Desenha borda com efeito de quadradinhos deslizando (otimizado)."""
        pattern = [1, 1, 0, 1, 0]
        pattern_len = 5

        pixel_size = max(2, int(self.size / 8))
        half_pixel = pixel_size // 2

        anim_idx = int(self.border_anim_offset / pixel_size) % pattern_len

        for i in range(4):
            start = corners[i]
            end = corners[(i + 1) % 4]

            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length_sq = dx * dx + dy * dy

            if length_sq < 1:
                continue

            length = math.sqrt(length_sq)
            inv_length = 1.0 / length
            dx *= inv_length
            dy *= inv_length

            num_segments = max(1, int(length / pixel_size))
            inv_segments = 1.0 / num_segments if num_segments > 0 else 0

            for j in range(num_segments):
                idx = (j + anim_idx + i * 2) % pattern_len
                if pattern[idx]:
                    t = j * inv_segments
                    px = int(start[0] + dx * length * t)
                    py = int(start[1] + dy * length * t)
                    pygame.draw.rect(
                        surface,
                        border_color,
                        (px - half_pixel, py - half_pixel, pixel_size, pixel_size),
                    )
