import math
import random
from typing import List, Tuple, TypedDict

import pygame

from ..core import colors


class ChargingParticle(TypedDict):
    """Type definition for charging particles."""

    pos: pygame.Vector2
    speed: float
    color: Tuple[int, int, int]
    size: float


class DisappearParticle(TypedDict):
    """Type definition for circle disappear particles."""

    pos: pygame.Vector2
    velocity: pygame.Vector2
    size: float
    color: Tuple[int, int, int]
    lifetime: float
    max_lifetime: float


class BossParticleSystem:
    """Manages all particle effects for the boss."""

    def __init__(self):
        self.charging_particles: List[ChargingParticle] = []
        self.circle_disappear_particles: List[DisappearParticle] = []

    def update_charging_particles(
        self, dt: float, face_x: float, face_y: float
    ) -> None:
        """Update charging particles animation."""
        for particle in self.charging_particles[:]:
            # Move particle towards face center
            direction = pygame.Vector2(face_x, face_y) - particle["pos"]
            if direction.length() > 0:
                direction.normalize_ip()
                particle["pos"] += direction * particle["speed"] * dt

            # Shrink particle as it gets closer
            distance_to_center = (
                pygame.Vector2(face_x, face_y) - particle["pos"]
            ).length()
            if distance_to_center < 10:
                particle["size"] = max(0.5, particle["size"] * 0.95)

            # Remove particles that are too close or too small
            if distance_to_center < 5 or particle["size"] < 1:
                self.charging_particles.remove(particle)

    def generate_charging_particles(self, face_x: float, face_y: float) -> None:
        """Generate new charging particles around the boss face."""
        if len(self.charging_particles) < 20:
            for _ in range(2):
                # Random position around the boss face
                angle = random.uniform(0, 2 * math.pi)
                distance = random.uniform(80, 120)
                pos_x = face_x + math.cos(angle) * distance
                pos_y = face_y + math.sin(angle) * distance

                particle: ChargingParticle = {
                    "pos": pygame.Vector2(pos_x, pos_y),
                    "speed": random.uniform(80, 120),
                    "color": random.choice(
                        [colors.YELLOW, colors.ORANGE, (255, 200, 0), (255, 150, 0)]
                    ),
                    "size": random.uniform(2, 4),
                }
                self.charging_particles.append(particle)

    def create_circle_disappear_particles(
        self, center_x: float, center_y: float, radius: float
    ) -> None:
        """Create particles when charging circle disappears."""
        self.circle_disappear_particles.clear()

        # Create particles along the circle circumference
        num_particles = 20
        for i in range(num_particles):
            angle = (i / num_particles) * 2 * math.pi

            # Position on circle circumference
            start_x = center_x + math.cos(angle) * radius
            start_y = center_y + math.sin(angle) * radius

            # Velocity pointing outward from center
            velocity_x = math.cos(angle) * random.uniform(50, 100)
            velocity_y = math.sin(angle) * random.uniform(50, 100)

            particle: DisappearParticle = {
                "pos": pygame.Vector2(start_x, start_y),
                "velocity": pygame.Vector2(velocity_x, velocity_y),
                "size": random.uniform(2, 4),
                "color": random.choice([colors.YELLOW, colors.ORANGE, (255, 200, 0)]),
                "lifetime": 0.0,
                "max_lifetime": random.uniform(0.5, 1.0),
            }
            self.circle_disappear_particles.append(particle)

    def update_circle_disappear_particles(self, dt: float) -> None:
        """Update circle disappear particles."""
        for particle in self.circle_disappear_particles[:]:
            particle["pos"] += particle["velocity"] * dt
            particle["lifetime"] += dt

            # Fade out and shrink over time
            progress = particle["lifetime"] / particle["max_lifetime"]
            particle["size"] = max(0.5, particle["size"] * (1 - progress * 0.1))

            # Remove expired particles
            if particle["lifetime"] >= particle["max_lifetime"]:
                self.circle_disappear_particles.remove(particle)

    def draw_particles(
        self, surface: pygame.Surface, offset_x: float, offset_y: float
    ) -> None:
        """Draw charging particles."""
        for particle in self.charging_particles:
            pos_x = int(particle["pos"].x + offset_x)
            pos_y = int(particle["pos"].y + offset_y)
            pygame.draw.circle(
                surface, particle["color"], (pos_x, pos_y), int(particle["size"])
            )

    def draw_circle_disappear_particles(
        self, surface: pygame.Surface, offset_x: float, offset_y: float
    ) -> None:
        """Draw circle disappear particles."""
        for particle in self.circle_disappear_particles:
            # Calculate alpha based on lifetime
            progress = particle["lifetime"] / particle["max_lifetime"]
            alpha = int(255 * (1 - progress))

            color_with_alpha = (*particle["color"], alpha)
            pos_x = int(particle["pos"].x + offset_x)
            pos_y = int(particle["pos"].y + offset_y)

            # Draw with alpha (requires creating a surface)
            particle_surface = pygame.Surface(
                (int(particle["size"]) * 2, int(particle["size"]) * 2), pygame.SRCALPHA
            )
            pygame.draw.circle(
                particle_surface,
                color_with_alpha,
                (int(particle["size"]), int(particle["size"])),
                int(particle["size"]),
            )
            surface.blit(
                particle_surface,
                (pos_x - int(particle["size"]), pos_y - int(particle["size"])),
            )

    def clear_all(self) -> None:
        """Clear all particles."""
        self.charging_particles.clear()
        self.circle_disappear_particles.clear()
