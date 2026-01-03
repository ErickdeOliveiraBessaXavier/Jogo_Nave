"""Boss Square Projectile - Indestructible projectile launched by the boss."""

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
        elif self.state == "orbiting":
            self.rotation = 0.0  # Sem rotação própria
        else:
            self.rotation += dt * 360  # Rotação contínua para projéteis

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
            pulse_scale = 1.0 + 0.2 * abs(
                pygame.math.Vector2(1, 0).rotate(self.animation_timer * 57.3).x
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
                        self.size * 0.4  # Partícula começa menor que o quadrado
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
                # Cor vermelha/laranja com alpha baseado na vida
                color_intensity = int(128 + 127 * p.life)
                trail_color = (255, color_intensity, int(color_intensity * 0.5))
                # Criar superfície com alpha
                particle_size = max(2, int(p.size))
                if particle_size > 0:
                    # Desenhar partícula quadrada com alpha
                    particle_surf = pygame.Surface(
                        (particle_size, particle_size), pygame.SRCALPHA
                    )
                    particle_surf.fill((*trail_color, p.alpha))
                    surface.blit(
                        particle_surf,
                        (p.x - particle_size // 2, p.y - particle_size // 2),
                    )

        # Calcular cor com intensidade alternada
        intensity = int(
            128
            + 127 * abs(pygame.math.Vector2(1, 0).rotate(self.animation_timer * 57.3).x)
        )
        color = (255, intensity, intensity)
        border_color = (255, 255, 255)

        # Desenhar quadrado rotacionado
        center_x = self.x
        center_y = self.y
        angle_rad = math.radians(self.rotation)

        # Calcular os 4 cantos do quadrado rotacionado
        half_size = self.size / 2
        corners = [
            (-half_size, -half_size),
            (half_size, -half_size),
            (half_size, half_size),
            (-half_size, half_size),
        ]

        # Rotacionar cada canto
        rotated_corners: list[tuple[float, float]] = []
        for cx, cy in corners:
            # Aplicar rotação
            rx = cx * math.cos(angle_rad) - cy * math.sin(angle_rad)
            ry = cx * math.sin(angle_rad) + cy * math.cos(angle_rad)
            rotated_corners.append((center_x + rx, center_y + ry))

        # Desenhar polígono preenchido
        pygame.draw.polygon(surface, color, rotated_corners)

        # Desenhar borda
        pygame.draw.polygon(surface, border_color, rotated_corners, 2)

    def get_rect(self) -> pygame.Rect:
        """Get collision rectangle."""
        half_size = self.size / 2
        return pygame.Rect(self.x - half_size, self.y - half_size, self.size, self.size)
