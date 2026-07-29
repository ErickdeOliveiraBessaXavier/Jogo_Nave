"""Visual do tiro EXPLOSIVO: a granada com pavio e faíscas.

O corpo (outer + body) vem de cache estático; só o núcleo pulsante e as faíscas
são desenhados por frame. O dano em área não está aqui — ele é do
`ExplosiveEffect`, criado pelo sistema de colisão.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Dict, Tuple

import pygame

from ....core.player_tint import player_shot_color
from ....core.upgrades_config import giant_visual_scale

if TYPE_CHECKING:
    from ..bullet import Bullet


# Cache estático do corpo do tiro explosivo (outer + body sem o core pulsante).
# Chave: (low_ammo_blink_on, player_index, radius). O `radius` cresce com o
# Giant Shot (combinação explosivo + tiro aumentado); o core e os sparks ficam
# dinâmicos.
_EXPLOSIVE_BODY_CACHE: Dict[Tuple[bool, int, int], pygame.Surface] = {}


def _build_explosive_body_surface(
    low_ammo_blink_on: bool, player_index: int, radius: int = 5
) -> pygame.Surface:
    surf_size = (radius + 1) * 2 + 2
    center = surf_size // 2
    surf = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
    if low_ammo_blink_on:
        outer_color = (200, 20, 0)
        body_color = (255, 60, 0)
    else:
        outer_color = (180, 50, 0)
        body_color = (255, 120, 0)
    pygame.draw.circle(
        surf, player_shot_color(outer_color, player_index), (center, center), radius + 1
    )
    pygame.draw.circle(
        surf, player_shot_color(body_color, player_index), (center, center), radius
    )
    try:
        surf = surf.convert_alpha()
    except pygame.error:
        pass
    return surf


def _get_explosive_body(
    low_ammo_blink_on: bool, player_index: int, radius: int = 5
) -> pygame.Surface:
    key = (low_ammo_blink_on, player_index, radius)
    cached = _EXPLOSIVE_BODY_CACHE.get(key)
    if cached is None:
        cached = _build_explosive_body_surface(low_ammo_blink_on, player_index, radius)
        _EXPLOSIVE_BODY_CACHE[key] = cached
    return cached



def draw(bullet: "Bullet", surface: pygame.Surface) -> None:
    """Desenha o tiro explosivo com visual de granada/bomba.
    Outer+body vêm de cache estático; só core e sparks ficam dinâmicos."""
    center_x = bullet.x + bullet.w / 2
    center_y = bullet.y + bullet.h / 2
    cx_int = int(center_x)
    cy_int = int(center_y)
    # Giant Shot engorda o hitbox (~3x); a granada acompanha pela raiz para
    # crescer visível sem virar um borrão. `scale = 1.0` (sem Giant Shot)
    # mantém o raio 5 original.
    scale = giant_visual_scale(bullet.size_multiplier)
    radius = max(1, round(5 * scale))

    ticks = pygame.time.get_ticks()  # 1 chamada em vez de 3
    tint = bullet.player_index

    pulse_speed = 0.02 if bullet.low_ammo else 0.01
    pulse = abs(math.sin(ticks * pulse_speed)) * 0.3 + 0.7

    if bullet.low_ammo:
        blink_on = (int(ticks * 0.008) % 2) == 0
        if blink_on:
            core_color = (255, 150, 50)
        else:
            core_color = (255, int(200 * pulse) + 55, 0)
        body_surf = _get_explosive_body(blink_on, tint, radius)
    else:
        core_color = (255, int(200 * pulse) + 55, 0)
        body_surf = _get_explosive_body(False, tint, radius)

    # 1 blit em vez de 2 draw.circle (outer + body).
    bw, bh = body_surf.get_size()
    surface.blit(body_surf, (cx_int - bw // 2, cy_int - bh // 2))

    # Núcleo pulsante (dinâmico — fica fora do cache).
    pygame.draw.circle(
        surface,
        player_shot_color(core_color, tint),
        (cx_int, cy_int),
        max(1, radius - 2),
    )

    # Sparks: posição dinâmica, mantém draw.circle.
    num_sparks = 6 if bullet.low_ammo else 4
    spark_radius = radius + 3
    time_offset = ticks * 0.003
    spark_color = player_shot_color(
        (255, 100, 100) if bullet.low_ammo else (255, 255, 100), tint
    )
    angle_step = 2 * math.pi / num_sparks
    spark_dot = max(1, round(scale))
    cos = math.cos
    sin = math.sin
    for i in range(num_sparks):
        angle = time_offset + i * angle_step
        spark_x = center_x + cos(angle) * spark_radius
        spark_y = center_y + sin(angle) * spark_radius
        pygame.draw.circle(
            surface, spark_color, (int(spark_x), int(spark_y)), spark_dot
        )
