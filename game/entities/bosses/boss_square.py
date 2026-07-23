"""Boss Square Projectile - Indestructible projectile launched by the boss."""

import math
import random

import pygame

from .._shared.draw_utils import draw_square_trail_particle, rotated_square_corners
from .square_base import SquareProjectileBase


class BossSquare(SquareProjectileBase):
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
        palette: dict[str, tuple[int, int, int]] | None = None,
    ):
        super().__init__(x, y, size)
        self.vx = vx
        self.vy = vy

        # Palette support
        self.palette = palette

        # Orbital attributes
        self.is_orbital = is_orbital
        self.orbit_radius = orbit_radius
        self.orbit_angle = orbit_angle
        self.orbit_speed = orbit_speed
        self.orbit_speed_original = orbit_speed
        self.speed_var = speed_var
        self.state = "orbiting" if is_orbital else "flying"
        self.prepare_timer = 0.0
        self.frenzy_orbit_multiplier = 1.0

        # Animation
        self.animation_timer = 0.0
        self.animation_offset = random.uniform(0, 10)

        # Growth effect - aumenta conforme se move
        self.growth_timer = 0.0
        self.max_growth_scale = 4.5
        self.growth_duration = 2.0

    def set_frenzy_mode(self, is_frenzy: bool) -> None:
        """Set frenzy mode and adjust orbital speed."""
        if is_frenzy:
            self.frenzy_orbit_multiplier = 2.0
        else:
            self.frenzy_orbit_multiplier = 1.0
        self.orbit_speed = self.orbit_speed_original * self.frenzy_orbit_multiplier

    def update(
        self, dt: float, screen_width: int = 1600, screen_height: int = 900
    ) -> None:
        """Update position and animation."""
        # Move only if not orbital
        if not self.is_orbital:
            self.x += self.vx * dt
            self.y += self.vy * dt

        # Handle rotation based on state
        if self.state == "preparing":
            self.rotation += dt * 720
            self.border_anim_offset += dt * 25
        elif self.state == "orbiting":
            self.rotation = 0.0
            self.border_anim_offset += dt * 10
        else:
            self.rotation += dt * 360
            self.border_anim_offset += dt * 15

        # Efeito de crescimento progressivo (only for projectiles)
        if not self.is_orbital:
            self.growth_timer += dt
            growth_progress = min(self.growth_timer / self.growth_duration, 1.0)
            growth_scale = 1.0 + (self.max_growth_scale - 1.0) * (
                1.0 - (1.0 - growth_progress) ** 2
            )
        else:
            growth_scale = 1.0

        # Pulsation animation
        self.animation_timer += dt * 5
        if self.state == "preparing":
            pulse_scale = 1.0 + 0.4 * abs(math.sin(self.prepare_timer * 10))
            self.prepare_timer += dt
        else:
            anim_value = self.animation_timer + self.animation_offset
            pulse_scale = 1.0 + 0.2 * abs(math.cos(anim_value))

        # Combina crescimento com pulsação
        self.size = self.base_size * growth_scale * pulse_scale

        # Atualizar partículas de trail da classe base
        self._update_trail(dt, self.state == "flying")

        # Remove if off-screen (only for projectiles)
        if not self.is_orbital:
            margin = 300
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

        # Paleta de cores dinâmica
        from .boss_pixel_map import PROJECTILE_COLOR_KEY, PROJECTILE_HIGHLIGHT_KEY, TRAIL_COLOR_KEY
        
        # Cores padrão caso não haja paleta
        hull_color = (255, 0, 0)
        energy_color = (255, 255, 100)
        trail_base = (255, 50, 0)
        
        if self.palette:
            hull_color = self.palette.get(PROJECTILE_COLOR_KEY, hull_color)
            energy_color = self.palette.get(PROJECTILE_HIGHLIGHT_KEY, energy_color)
            trail_base = self.palette.get(TRAIL_COLOR_KEY, trail_base)

        # Desenhar partículas de trail primeiro (atrás do quadrado)
        for p in self.trail_particles:
            if p.alpha > 0:
                # Interpola a cor da trilha baseada na vida da partícula
                r = int(trail_base[0] * p.life + 255 * (1 - p.life))
                g = int(trail_base[1] * p.life + 100 * (1 - p.life))
                b = int(trail_base[2] * p.life)
                draw_square_trail_particle(
                    surface, p.x, p.y, p.size, (r, g, b), p.alpha
                )

        # Calcular cor com intensidade alternada (usa offset para dessincronizar)
        anim_value = self.animation_timer + self.animation_offset
        cos_val = abs(math.cos(anim_value))
        
        # Interpola entre hull_color e energy_color para efeito pulsante
        r = int(hull_color[0] + (energy_color[0] - hull_color[0]) * cos_val * 0.3)
        g = int(hull_color[1] + (energy_color[1] - hull_color[1]) * cos_val * 0.3)
        b = int(hull_color[2] + (energy_color[2] - hull_color[2]) * cos_val * 0.3)
        color = (r, g, b)
        
        border_color = energy_color

        rotated_corners = rotated_square_corners(
            self.x, self.y, self.size / 2, math.radians(self.rotation)
        )
        pygame.draw.polygon(surface, color, rotated_corners)
        self._draw_animated_border(surface, rotated_corners, border_color)

    def get_rect(self) -> pygame.Rect:
        """Get collision rectangle."""
        half_size = self.size / 2
        return pygame.Rect(self.x - half_size, self.y - half_size, self.size, self.size)
