"""Square Minion Boss - Common enemy based on boss square projectile."""

import pygame
import math
import random
from typing import List


class TrailParticle:
    """Partícula simples para efeito de cauda - otimizada."""
    __slots__ = ('x', 'y', 'size', 'life', 'alpha')
    
    def __init__(self, x: float, y: float, size: float):
        self.x = x
        self.y = y
        self.size = size
        self.life = 1.0  # 0.0 a 1.0
        self.alpha = 255


class SquareMinionBoss:
    """
    Common enemy that spawns at the top, blinks for a while, then charges towards the player.

    Features:
    - Spawns at top of screen
    - Blinks during preparation phase
    - Charges in a straight line towards player (not guided)
    - Can be destroyed by bullets
    - Causes damage on collision with player
    """

    def __init__(
        self,
        x: float,
        y: float,
        player_x: float,
        player_y: float,
        speed: float = 200.0,
        size: float = 30.0,
    ):
        """
        Initialize square minion boss.

        Args:
            x: Starting x position
            y: Starting y position
            player_x: Player's current x position
            player_y: Player's current y position
            speed: Movement speed
            size: Base size of the square
        """
        self.x = x
        self.y = y
        self.base_size = size
        self.size = size
        self.dead = False
        self.health = 1  # Can be destroyed

        # Properties for compatibility
        self.w = size
        self.h = size

        # Calculate direction towards player at spawn
        dx = player_x - x
        dy = player_y - y
        distance = math.sqrt(dx**2 + dy**2)
        if distance > 0:
            self.vx = (dx / distance) * speed
            self.vy = (dy / distance) * speed
        else:
            self.vx = 0
            self.vy = speed  # Default down

        # States: preparing, charging
        self.state = "preparing"
        self.prepare_timer = 0.0
        self.prepare_duration = 2.0  # Blink for 2 seconds

        # Animation
        self.animation_timer = 0.0
        self.animation_offset = random.uniform(0, 10)  # Offset aleatório para dessincronizar
        self.rotation = 0.0
        self.visible = True  # For blinking effect

        # Trail particles (otimizado - pool limitado)
        self.trail_particles: List[TrailParticle] = []
        self.trail_spawn_timer = 0.0
        self.trail_spawn_interval = 0.025  # Spawna partícula a cada 25ms
        self.max_trail_particles = 18  # Limite de partículas

        # Animação da borda pixelada
        self.border_anim_offset: float = random.uniform(0, 100)

    def update(
        self, dt: float, screen_width: int = 1600, screen_height: int = 900
    ) -> None:
        """
        Update position and animation.

        Args:
            dt: Delta time
            screen_width: Current screen width
            screen_height: Current screen height
        """
        if self.state == "preparing":
            self.prepare_timer += dt
            if self.prepare_timer >= self.prepare_duration:
                self.state = "charging"
                self.visible = True  # Ensure visible when charging

            # Blink effect during preparation
            blink_rate = 5  # Blinks per second
            self.visible = (self.prepare_timer * blink_rate) % 1 < 0.5

            # Rotação rápida durante preparação
            self.rotation += dt * 720
            self.border_anim_offset += dt * 25

        elif self.state == "charging":
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.rotation += dt * 360  # Rotate while charging
            self.border_anim_offset += dt * 15

            # Atualizar partículas de trail
            self.trail_spawn_timer += dt
            if self.trail_spawn_timer >= self.trail_spawn_interval:
                self.trail_spawn_timer = 0.0
                if len(self.trail_particles) < self.max_trail_particles:
                    offset_x = random.uniform(-self.size * 0.3, self.size * 0.3)
                    offset_y = random.uniform(-self.size * 0.3, self.size * 0.3)
                    particle = TrailParticle(
                        self.x + offset_x,
                        self.y + offset_y,
                        self.size * 0.4
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
            self.border_anim_offset += dt * 10

        # Pulsation animation
        self.animation_timer += dt * 5
        if self.state == "preparing":
            pulse_scale = 1.0 + 0.4 * abs(math.sin(self.prepare_timer * 10))
        else:
            anim_value = (self.animation_timer + self.animation_offset) * 57.3
            pulse_scale = 1.0 + 0.2 * abs(
                pygame.math.Vector2(1, 0).rotate(anim_value).x
            )

        # Aplicar apenas pulsação
        self.size = self.base_size * pulse_scale

        # Remove if off-screen
        margin = 100
        if (
            self.x < -margin
            or self.x > screen_width + margin
            or self.y < -margin
            or self.y > screen_height + margin
        ):
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the square minion with rotation and trail."""
        if self.dead or not self.visible:
            return

        # Desenhar partículas de trail primeiro (apenas em charging)
        if self.state == "charging":
            for p in self.trail_particles:
                if p.alpha > 0:
                    # Cor vermelha/laranja com alpha
                    color_intensity = int(128 + 127 * p.life)
                    trail_color = (255, color_intensity // 2, 0)
                    particle_size = max(2, int(p.size))
                    if particle_size > 0:
                        particle_surf = pygame.Surface(
                            (particle_size, particle_size), pygame.SRCALPHA
                        )
                        particle_surf.fill((*trail_color, p.alpha))
                        surface.blit(
                            particle_surf,
                            (p.x - particle_size // 2, p.y - particle_size // 2),
                        )

        # Color: Red for enemy
        anim_value = (self.animation_timer + self.animation_offset) * 57.3
        intensity = int(
            128 + 127 * abs(pygame.math.Vector2(1, 0).rotate(anim_value).x)
        )
        color = (intensity, 0, 0)  # Red pulsating
        border_color = (255, 255, 255)

        # Draw rotated square
        center_x = self.x
        center_y = self.y
        angle_rad = math.radians(self.rotation)

        half_size = self.size / 2
        corners = [
            (-half_size, -half_size),
            (half_size, -half_size),
            (half_size, half_size),
            (-half_size, half_size),
        ]

        rotated_corners: list[tuple[float, float]] = []
        for cx, cy in corners:
            rx = cx * math.cos(angle_rad) - cy * math.sin(angle_rad)
            ry = cx * math.sin(angle_rad) + cy * math.cos(angle_rad)
            rotated_corners.append((center_x + rx, center_y + ry))

        pygame.draw.polygon(surface, color, rotated_corners)

        # Desenhar borda animada (efeito de quadradinhos deslizando)
        self._draw_animated_border(surface, rotated_corners, border_color)

    def _draw_animated_border(
        self,
        surface: pygame.Surface,
        corners: list[tuple[float, float]],
        border_color: tuple[int, int, int],
    ) -> None:
        """Desenha borda com efeito de quadradinhos deslizando (otimizado)."""
        # Padrão simples para otimização
        pattern = [1, 1, 0, 1, 0]
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

    @property
    def rect(self) -> pygame.Rect:
        """Get collision rectangle."""
        return pygame.Rect(int(self.x), int(self.y), int(self.size), int(self.size))

    def take_damage(self, damage: int = 1) -> None:
        """Take damage and check if dead."""
        self.health -= damage
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        """Return points awarded for destroying this enemy."""
        return 50  # Similar to other enemies
