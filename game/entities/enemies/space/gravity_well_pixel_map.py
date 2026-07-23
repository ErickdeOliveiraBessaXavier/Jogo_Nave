"""Gravity Well — pixel-map do corpo (singularidade compacta).

Sóbrio: um **disco escuro colapsado** (quase preto no centro) com um aro frio
fino e sombreamento chapado de baixo contraste — nada de bloom. O anel de
acreção e o telegraph do raio de atração são desenhados no `gravity_well.py`.

Gerado por regra (distância ao centro) e cacheado por `cell` (§7).
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import pygame

from . import space_palette as pal

RGB = Tuple[int, int, int]

PIXEL_COLS = 13
PIXEL_ROWS = 13
_C = (PIXEL_COLS - 1) / 2.0  # centro 6.0
_R = 6.2  # raio do disco (em cells)

_ZONE_COLORS: Dict[str, RGB] = {
    "o": pal.OUTLINE,        # aro externo escuro
    "r": pal.CORE_RIM,       # aro frio (borda iluminada da singularidade)
    "h": pal.HULL_SHADOW,    # manto em sombra
    "d": pal.HULL_DARK,      # manto
    "k": pal.CORE_DARK,      # núcleo colapsado (quase preto)
}


def _build_disc_map() -> List[str]:
    grid = [["." for _ in range(PIXEL_COLS)] for _ in range(PIXEL_ROWS)]
    for y in range(PIXEL_ROWS):
        for x in range(PIXEL_COLS):
            dx = x - _C
            dy = y - _C
            d = math.hypot(dx, dy)
            if d > _R + 0.4:
                continue
            if d > _R - 0.9:
                grid[y][x] = "o"  # contorno
                continue
            if d < _R * 0.34:
                grid[y][x] = "k"  # núcleo colapsado
                continue
            # Aro frio fino logo dentro do contorno; manto chapado no resto,
            # levemente mais escuro embaixo (luz fraca vinda de cima).
            if d > _R - 1.9:
                grid[y][x] = "r"
            elif dy < -0.4:
                grid[y][x] = "d"
            else:
                grid[y][x] = "h"
    return ["".join(row) for row in grid]


PIXEL_MAP: List[str] = _build_disc_map()

CORE_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "k"
]

assert len(PIXEL_MAP) == PIXEL_ROWS and all(len(r) == PIXEL_COLS for r in PIXEL_MAP)
assert CORE_CELLS, "núcleo do poço não foi gerado"

_cache: Dict[int, pygame.Surface] = {}


def build_disc_surface(cell: int) -> pygame.Surface:
    """Surface estática do disco colapsado, cacheada por `cell`."""
    cached = _cache.get(cell)
    if cached is not None:
        return cached
    surface = pygame.Surface((PIXEL_COLS * cell, PIXEL_ROWS * cell), pygame.SRCALPHA)
    for row_i, row in enumerate(PIXEL_MAP):
        for col_i, ch in enumerate(row):
            color = _ZONE_COLORS.get(ch)
            if color is None:
                continue
            surface.fill(color, (col_i * cell, row_i * cell, cell, cell))
    _cache[cell] = surface
    return surface
