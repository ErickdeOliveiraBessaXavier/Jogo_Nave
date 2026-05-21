from typing import Tuple, TypedDict

import pygame


class DeathParticle(TypedDict):
    """Type definition for laser death particles."""

    pos: pygame.Vector2
    vel: pygame.Vector2
    size: float
    color: Tuple[int, int, int]
    lifespan: float


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


class ParticleDict(TypedDict):
    x: float
    y: float
    vx: float
    vy: float
    lifetime: float
    size: float
    color: Tuple[int, int, int]
