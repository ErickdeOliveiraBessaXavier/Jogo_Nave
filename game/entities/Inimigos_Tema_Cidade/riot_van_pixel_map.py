"""Riot Van (Escudeiro) — Layered Pixel-Map.

Variante "blindada" da linhagem do Police Interceptor: um **furgão de choque**
largo e baixo, com **emissores de escudo** na dianteira (face voltada ao jogador).
Chassi pesado em gunmetal; emissores e núcleo em **electric blue** (a energia do
escudo). O escudo em si é desenhado/animado pela entidade (`riot_van.py`), aqui é
só o corpo.

Builder cacheado por `cell` (§7). Zonas → cor em `_ZONE_COLORS`. Emissores ('e')
e núcleo ('c') recebem glow animado por cima no draw.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

from . import city_palette as pal

RGB = Tuple[int, int, int]

PIXEL_COLS = 17
PIXEL_ROWS = 11

_ZONE_COLORS: Dict[str, RGB] = {
    "o": pal.OUTLINE,
    "a": pal.HULL_LIGHT,
    "l": pal.GUNMETAL,
    "h": pal.HULL_SHADOW,
    "d": pal.DEEP_SLATE,
    "c": pal.ELECTRIC_BLUE_DIM,   # núcleo (glow animado no draw)
    "e": pal.ELECTRIC_BLUE,       # emissores de escudo (glow animado no draw)
}

CORE_NEON: RGB = pal.ELECTRIC_BLUE
CORE_NEON_DIM: RGB = pal.ELECTRIC_BLUE_DIM
EMITTER_NEON: RGB = pal.ELECTRIC_BLUE


def _build_map() -> List[str]:
    """Furgão retangular de cantos arredondados. A frente (coluna 0 = esquerda,
    lado do jogador) carrega os 2 emissores de escudo."""
    cols, rows = PIXEL_COLS, PIXEL_ROWS
    grid = [["." for _ in range(cols)] for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            # Cantos arredondados (remove 1 célula em cada quina).
            corner = (x in (0, cols - 1)) and (y in (0, rows - 1))
            if corner:
                continue
            edge = x in (0, cols - 1) or y in (0, rows - 1)
            if edge:
                grid[y][x] = "o"
            else:
                # Sombreamento top-lit simples por linha.
                if y <= 2:
                    grid[y][x] = "a"
                elif y <= rows - 4:
                    grid[y][x] = "l"
                elif y == rows - 3:
                    grid[y][x] = "h"
                else:
                    grid[y][x] = "d"

    # Núcleo: faixa central (energia do escudo).
    cy = rows // 2
    for x in range(cols // 2 - 1, cols // 2 + 2):
        grid[cy][x] = "c"

    # Emissores de escudo na dianteira (coluna 1, esquerda), em cima e embaixo.
    grid[2][1] = "e"
    grid[rows - 3][1] = "e"
    return ["".join(row) for row in grid]


PIXEL_MAP: List[str] = _build_map()

CORE_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "c"
]
EMITTER_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "e"
]

assert len(PIXEL_MAP) == PIXEL_ROWS and all(len(r) == PIXEL_COLS for r in PIXEL_MAP)
assert CORE_CELLS and len(EMITTER_CELLS) == 2

_cache: Dict[int, pygame.Surface] = {}


def build_van_surface(cell: int) -> pygame.Surface:
    """Surface estática do furgão, cacheada por `cell`."""
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
