"""Splitter Tank — Layered Pixel-Map.

Variante "modular" da linhagem do Cyber Tank: um chassi blindado **segmentado por
uma costura central** (telegrafa que ele se parte ao morrer). Placas de blindagem
em gunmetal, núcleo e costura em **toxic orange** (a "linha de fratura" de energia).
O mesmo mapa serve aos dois tiers — o `cell` muda o tamanho (tier 0 grande, tier 1
pequeno).

Builder cacheado por `cell` (§7). Zonas → cor em `_ZONE_COLORS`. Núcleo ('c')
animado por cima no draw.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

from . import city_palette as pal

RGB = Tuple[int, int, int]

PIXEL_COLS = 15
PIXEL_ROWS = 13

_ZONE_COLORS: Dict[str, RGB] = {
    "o": pal.OUTLINE,
    "a": pal.HULL_LIGHT,
    "l": pal.GUNMETAL,
    "h": pal.HULL_SHADOW,
    "d": pal.DEEP_SLATE,
    "s": pal.TOXIC_ORANGE_DIM,    # costura de fratura
    "c": pal.TOXIC_ORANGE_DIM,    # núcleo (glow animado no draw)
}

CORE_NEON: RGB = pal.TOXIC_ORANGE
CORE_NEON_DIM: RGB = pal.TOXIC_ORANGE_DIM
SEAM_NEON: RGB = pal.TOXIC_ORANGE


def _build_map() -> List[str]:
    cols, rows = PIXEL_COLS, PIXEL_ROWS
    grid = [["." for _ in range(cols)] for _ in range(rows)]
    cx = cols // 2
    cy = rows // 2
    for y in range(rows):
        for x in range(cols):
            corner = (x in (0, cols - 1)) and (y in (0, rows - 1))
            if corner:
                continue
            edge = x in (0, cols - 1) or y in (0, rows - 1)
            if edge:
                grid[y][x] = "o"
            elif y <= 2:
                grid[y][x] = "a"
            elif y <= rows - 4:
                grid[y][x] = "l"
            elif y == rows - 3:
                grid[y][x] = "h"
            else:
                grid[y][x] = "d"

    # Costura de fratura vertical (linha por onde ele se parte).
    for y in range(2, rows - 2):
        grid[y][cx] = "s"
    # Núcleo: bloco central na costura.
    for yy in (cy - 1, cy, cy + 1):
        grid[yy][cx] = "c"
    return ["".join(row) for row in grid]


PIXEL_MAP: List[str] = _build_map()

CORE_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "c"
]

assert len(PIXEL_MAP) == PIXEL_ROWS and all(len(r) == PIXEL_COLS for r in PIXEL_MAP)
assert CORE_CELLS, "núcleo do tank não foi gerado"

_cache: Dict[int, pygame.Surface] = {}


def build_tank_surface(cell: int) -> pygame.Surface:
    """Surface estática do Splitter Tank, cacheada por `cell`."""
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
