"""Jammer Node — Layered Pixel-Map (nó de interferência).

"O Glitch" simplificado da linhagem CITY: um **nó octogonal compacto** com um
**núcleo magenta** (identidade de "interferência/glitch") e **4 antenas
emissoras** azuis nas direções cardeais — de onde nasce o campo estático que
suprime os tiros da nave. O corpo reaproveita o sombreamento top-lit dos demais
inimigos do bioma para manter a coesão (Industrial Gritty).

Builder cacheado por `cell` (§7). Zonas → cor em `_ZONE_COLORS`. O núcleo ('c')
e as antenas ('t') são animados por cima no `draw` (glow pulsante).
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import pygame

from . import city_palette as pal

RGB = Tuple[int, int, int]

PIXEL_COLS = 13
PIXEL_ROWS = 13
_C = (PIXEL_COLS - 1) / 2.0  # centro 6.0
_R = 5.3                     # raio do corpo (em cells)
_CORE_R = 1.9                # raio do núcleo magenta

_ZONE_COLORS: Dict[str, RGB] = {
    "o": pal.OUTLINE,
    "a": pal.HULL_LIGHT,          # face iluminada (topo-esquerda)
    "m": (78, 86, 104),           # metal médio
    "l": pal.GUNMETAL,            # metal base
    "h": pal.HULL_SHADOW,         # sombra
    "d": pal.DEEP_SLATE,          # base em sombra
    "c": pal.CYBER_MAGENTA_DIM,   # núcleo glitch (glow animado no draw)
    "t": pal.ELECTRIC_BLUE_DIM,   # antenas emissoras (glow animado no draw)
}

# Cores emissivas expostas para o glow animado do entity.
CORE_NEON: RGB = pal.CYBER_MAGENTA
CORE_NEON_DIM: RGB = pal.CYBER_MAGENTA_DIM
ANTENNA_NEON: RGB = pal.ELECTRIC_BLUE


def _build_node_map() -> List[str]:
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
            if d < _CORE_R:
                grid[y][x] = "c"  # núcleo magenta
                continue
            # Sombreamento top-lit (luz vinda do topo-esquerda).
            lit = (-dy - dx * 0.45) / _R
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

    # Antenas emissoras nas direções cardeais (saem do corpo p/ as bordas).
    mid = int(_C)
    for c, r in ((mid, 0), (mid, PIXEL_ROWS - 1), (0, mid), (PIXEL_COLS - 1, mid)):
        grid[r][c] = "t"
    return ["".join(row) for row in grid]


PIXEL_MAP: List[str] = _build_node_map()

CORE_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "c"
]
ANTENNA_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "t"
]

assert len(PIXEL_MAP) == PIXEL_ROWS and all(len(r) == PIXEL_COLS for r in PIXEL_MAP)
assert CORE_CELLS, "núcleo do nó não foi gerado"
assert len(ANTENNA_CELLS) == 4, "esperadas 4 antenas emissoras"

_cache: Dict[int, pygame.Surface] = {}


def build_node_surface(cell: int) -> pygame.Surface:
    """Surface estática do nó, cacheada por `cell`."""
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
