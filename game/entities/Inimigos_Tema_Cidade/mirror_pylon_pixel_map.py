"""Mirror Pylon (Refletor) — Layered Pixel-Map.

Variante da linhagem do Tesla Twin: um **pilar vertical** com uma **face
espelhada** na dianteira (lado do jogador) que **reflete os tiros da nave**. O
chassi é gunmetal; a face espelhada e o núcleo usam um **ciano-branco** brilhante
(superfície refletora). A barra refletora em si é animada pela entidade; aqui é
só o corpo + a coluna de espelho.

Builder cacheado por `cell` (§7). Núcleo ('c') e células de espelho ('m')
recebem glow animado por cima no draw.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

from . import city_palette as pal

RGB = Tuple[int, int, int]

PIXEL_COLS = 11
PIXEL_ROWS = 17

MIRROR: RGB = (200, 240, 255)       # superfície espelhada (ciano-branco)
MIRROR_DIM: RGB = (90, 150, 190)

_ZONE_COLORS: Dict[str, RGB] = {
    "o": pal.OUTLINE,
    "a": pal.HULL_LIGHT,
    "l": pal.GUNMETAL,
    "h": pal.HULL_SHADOW,
    "d": pal.DEEP_SLATE,
    "c": MIRROR_DIM,    # núcleo (glow animado no draw)
    "m": MIRROR,        # coluna espelhada (glow animado no draw)
}

CORE_NEON: RGB = MIRROR
CORE_NEON_DIM: RGB = MIRROR_DIM
MIRROR_NEON: RGB = MIRROR


def _build_map() -> List[str]:
    cols, rows = PIXEL_COLS, PIXEL_ROWS
    grid = [["." for _ in range(cols)] for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            corner = (x in (0, cols - 1)) and (y in (0, rows - 1))
            if corner:
                continue
            edge = x in (0, cols - 1) or y in (0, rows - 1)
            if edge:
                grid[y][x] = "o"
            elif x <= 2:
                grid[y][x] = "a"   # face frontal iluminada (perto do espelho)
            elif x <= cols - 3:
                grid[y][x] = "l"
            else:
                grid[y][x] = "h"

    # Coluna espelhada na dianteira (col 1, lado do jogador), miolo vertical.
    for y in range(2, rows - 2):
        grid[y][1] = "m"
    # Núcleo: bloco central.
    cx, cy = cols // 2, rows // 2
    for yy in (cy - 1, cy, cy + 1):
        grid[yy][cx] = "c"
    return ["".join(row) for row in grid]


PIXEL_MAP: List[str] = _build_map()

CORE_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "c"
]
MIRROR_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "m"
]

assert len(PIXEL_MAP) == PIXEL_ROWS and all(len(r) == PIXEL_COLS for r in PIXEL_MAP)
assert CORE_CELLS and MIRROR_CELLS

_cache: Dict[int, pygame.Surface] = {}


def build_pylon_surface(cell: int) -> pygame.Surface:
    """Surface estática do pilar, cacheada por `cell`."""
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
