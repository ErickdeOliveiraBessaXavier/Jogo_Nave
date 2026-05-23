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


def step_particle(
    p: ParticleDict,
    dt: float,
    size_shrink_rate: float = 0.0,
    velocity_damping: float = 1.0,
) -> ParticleDict:
    """Avança uma partícula no tempo. Função pura (não muta a entrada).

    `size_shrink_rate=0` mantém tamanho constante. `velocity_damping=1.0`
    desliga drag. O filtro de morte (lifetime/size > 0) fica a cargo do
    call site para preservar regras locais.
    """
    return ParticleDict(
        x=p["x"] + p["vx"] * dt,
        y=p["y"] + p["vy"] * dt,
        vx=p["vx"] * velocity_damping,
        vy=p["vy"] * velocity_damping,
        lifetime=p["lifetime"] - dt,
        size=max(0.0, p["size"] - dt * size_shrink_rate),
        color=p["color"],
    )
