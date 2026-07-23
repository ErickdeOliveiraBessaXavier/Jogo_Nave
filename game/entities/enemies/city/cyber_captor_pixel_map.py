"""Cyber-Captor — Layered Pixel-Map (esfera mecânica).

"A Armadilha de Energia" da proposta: uma **esfera mecânica central** (cercada por
**anéis orbitais** desenhados em código no entity). Aqui só o corpo-esfera: orbe
metálico top-lit com um **núcleo azul** emissivo no centro. Gerado por regras
(distância ao centro + sombreamento por luz superior), mantendo o look chunky de
pixel art coeso com os demais inimigos do bioma.

Builder cacheado por `cell` (§7). Zonas → cor em `_ZONE_COLORS`.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

from . import city_palette as pal

RGB = Tuple[int, int, int]

PIXEL_COLS = 15
PIXEL_ROWS = 15
_C = (PIXEL_COLS - 1) / 2.0  # centro 7.0
_R = 7.2  # raio da esfera (em cells)

_ZONE_COLORS: Dict[str, RGB] = {
    "o": pal.OUTLINE,
    "a": pal.HULL_LIGHT,          # face iluminada (topo-esquerda)
    "m": (78, 86, 104),           # metal médio
    "l": pal.GUNMETAL,            # metal base
    "h": pal.HULL_SHADOW,         # sombra
    "d": pal.DEEP_SLATE,          # base em sombra
    "c": pal.ELECTRIC_BLUE_DIM,   # núcleo (glow animado no draw)
}

CORE_NEON: RGB = pal.ELECTRIC_BLUE
CORE_NEON_DIM: RGB = pal.ELECTRIC_BLUE_DIM


def _build_sphere_map() -> List[str]:
    import math

    grid = [["." for _ in range(PIXEL_COLS)] for _ in range(PIXEL_ROWS)]
    for y in range(PIXEL_ROWS):
        for x in range(PIXEL_COLS):
            dx = x - _C
            dy = y - _C
            d = math.hypot(dx, dy)
            if d > _R + 0.4:
                continue
            if d > _R - 1.0:
                grid[y][x] = "o"  # contorno
                continue
            if d < _R * 0.28:
                grid[y][x] = "c"  # núcleo
                continue
            # Sombreamento top-lit (luz vinda do topo-esquerda).
            lit = (-dy - dx * 0.45) / _R  # -1..1 (maior = mais iluminado)
            if lit > 0.45:
                grid[y][x] = "a"
            elif lit > 0.12:
                grid[y][x] = "m"
            elif lit > -0.18:
                grid[y][x] = "l"
            elif lit > -0.5:
                grid[y][x] = "h"
            else:
                grid[y][x] = "d"
    return ["".join(row) for row in grid]


PIXEL_MAP: List[str] = _build_sphere_map()

CORE_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "c"
]

assert len(PIXEL_MAP) == PIXEL_ROWS and all(len(r) == PIXEL_COLS for r in PIXEL_MAP)
assert CORE_CELLS, "núcleo da esfera não foi gerado"

_cache: Dict[int, pygame.Surface] = {}


def build_sphere_surface(cell: int) -> pygame.Surface:
    """Surface estática da esfera, cacheada por `cell`."""
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
