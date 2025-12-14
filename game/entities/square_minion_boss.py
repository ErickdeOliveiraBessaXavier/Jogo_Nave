"""Square Minion Boss - Common enemy based on boss square projectile."""

import pygame
import math


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
        self.rotation = 0.0
        self.visible = True  # For blinking effect

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

        elif self.state == "charging":
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.rotation += dt * 360  # Rotate while charging

        # Pulsation animation
        self.animation_timer += dt * 5
        pulse_scale = 1.0 + 0.2 * abs(
            pygame.math.Vector2(1, 0).rotate(self.animation_timer * 57.3).x
        )
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
        """Draw the square minion with rotation."""
        if self.dead or not self.visible:
            return

        # Color: Red for enemy
        intensity = int(
            128
            + 127 * abs(pygame.math.Vector2(1, 0).rotate(self.animation_timer * 57.3).x)
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
        pygame.draw.polygon(surface, border_color, rotated_corners, 2)

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
