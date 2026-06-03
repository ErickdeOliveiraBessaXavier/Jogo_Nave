"""Sapper Drone (Rebocador) — Layered Pixel-Map.

Variante de suporte da linhagem do City Drone: um nó-reboque compacto com um
**núcleo verde-ciano** (energia de reparo) e duas **garras** laterais (de onde
sai o cabo que blinda um aliado). Octógono pequeno, no mesmo molde dos demais
nós do bioma.

Builder cacheado por `cell` (§7). Núcleo ('c') e garras ('g') animados no draw.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import pygame

from . import city_palette as pal

RGB = Tuple[int, int, int]

PIXEL_COLS = 13
PIXEL_ROWS = 13
_C = (PIXEL_COLS - 1) / 2.0
_R = 5.0
_CORE_R = 2.0

# Verde-ciano de reparo (não existe na paleta base — derivado, coeso com o tema).
REPAIR: RGB = (60, 235, 170)
REPAIR_DIM: RGB = (24, 110, 86)

_ZONE_COLORS: Dict[str, RGB] = {
    "o": pal.OUTLINE,
    "a": pal.HULL_LIGHT,
    "m": (78, 86, 104),
    "l": pal.GUNMETAL,
    "h": pal.HULL_SHADOW,
    "d": pal.DEEP_SLATE,
    "c": REPAIR_DIM,    # núcleo de reparo (glow animado no draw)
    "g": REPAIR,        # garras emissoras (glow animado no draw)
}

CORE_NEON: RGB = REPAIR
CORE_NEON_DIM: RGB = REPAIR_DIM
CLAW_NEON: RGB = REPAIR


def _build_map() -> List[str]:
    grid = [["." for _ in range(PIXEL_COLS)] for _ in range(PIXEL_ROWS)]
    for y in range(PIXEL_ROWS):
        for x in range(PIXEL_COLS):
            dx = x - _C
            dy = y - _C
            d = math.hypot(dx, dy)
            if d > _R + 0.4:
                continue
            if d > _R - 1.0:
                grid[y][x] = "o"
                continue
            if d < _CORE_R:
                grid[y][x] = "c"
                continue
            lit = (-dy - dx * 0.45) / _R
            if lit > 0.4:
                grid[y][x] = "a"
            elif lit > 0.0:
                grid[y][x] = "m"
            elif lit > -0.35:
                grid[y][x] = "l"
            else:
                grid[y][x] = "h"
    # Garras laterais (esquerda/direita, na linha do centro).
    mid = int(_C)
    grid[mid][0] = "g"
    grid[mid][PIXEL_COLS - 1] = "g"
    return ["".join(row) for row in grid]


PIXEL_MAP: List[str] = _build_map()

CORE_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "c"
]
CLAW_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "g"
]

assert len(PIXEL_MAP) == PIXEL_ROWS and all(len(r) == PIXEL_COLS for r in PIXEL_MAP)
assert CORE_CELLS and len(CLAW_CELLS) == 2

_cache: Dict[int, pygame.Surface] = {}


def build_sapper_surface(cell: int) -> pygame.Surface:
    """Surface estática do Rebocador, cacheada por `cell`."""
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
