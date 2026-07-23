import math

import pygame


def rotated_square_corners(
    center_x: float,
    center_y: float,
    half_size: float,
    angle_rad: float,
) -> list[tuple[float, float]]:
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    base = [
        (-half_size, -half_size),
        (half_size, -half_size),
        (half_size, half_size),
        (-half_size, half_size),
    ]
    return [
        (center_x + cx * cos_a - cy * sin_a, center_y + cx * sin_a + cy * cos_a)
        for cx, cy in base
    ]


def draw_square_trail_particle(
    surface: pygame.Surface,
    x: float,
    y: float,
    size: float,
    color: tuple[int, int, int],
    alpha: int,
) -> None:
    particle_size = max(2, int(size))
    if particle_size > 0:
        surf = pygame.Surface((particle_size, particle_size), pygame.SRCALPHA)
        surf.fill((*color, alpha))
        surface.blit(surf, (int(x) - particle_size // 2, int(y) - particle_size // 2))
