"""Square Minion Boss - Common enemy based on boss square projectile."""

import math
import random
from typing import TYPE_CHECKING

import pygame

from .draw_utils import draw_square_trail_particle, rotated_square_corners
from .square_base import SquareProjectileBase

if TYPE_CHECKING:
    from ..systems.entity_context import EnemyUpdateContext
    from ..systems.hit_result import HitResult


class SquareMinionBoss(SquareProjectileBase):
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
        super().__init__(x, y, size)
        self.health = 1  # Can be destroyed
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
        self.animation_offset = random.uniform(0, 10)
        self.visible = True  # For blinking effect

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt, ctx.screen_width, ctx.screen_height)

    def update(
        self, dt: float, screen_width: int = 1600, screen_height: int = 900
    ) -> None:
        """
        Update position and animation.
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

        self._update_trail(dt, self.state == "charging")

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
        if self.state == "charging" and self.trail_particles:
            for p in self.trail_particles:
                if p.alpha > 0:
                    color_intensity = int(128 + 127 * p.life)
                    trail_color = (255, color_intensity // 2, 0)
                    draw_square_trail_particle(
                        surface, p.x, p.y, p.size, trail_color, p.alpha
                    )

        # Color: Red for enemy
        anim_value = (self.animation_timer + self.animation_offset) * 57.3
        intensity = int(128 + 127 * abs(pygame.math.Vector2(1, 0).rotate(anim_value).x))
        color = (intensity, 0, 0)  # Red pulsating
        border_color = (255, 255, 255)

        rotated_corners = rotated_square_corners(
            self.x, self.y, self.size / 2, math.radians(self.rotation)
        )
        pygame.draw.polygon(surface, color, rotated_corners)

        # Desenhar borda animada (efeito de quadradinhos deslizando)
        self._draw_animated_border(surface, rotated_corners, border_color)

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

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x + self.size / 2, self.y + self.size / 2, self.size / 2

    def on_hit(self, _damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        # Imune — só feedback visual
        return HitResult(explosion_size=20, sound=hit_sounds.BOSS_DAMAGE)

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)
