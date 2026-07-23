"""Mortar Drone (Artilheiro) — Layered Pixel-Map.

Variante "de cerco" da linhagem do Neon Sniper: um corpo-esfera blindado com um
**barril de morteiro** curto no topo. Diferente do sniper (acento magenta) e do
Captor (núcleo azul), o Artilheiro usa o acento **laranja tóxico** (TOXIC_ORANGE)
para o núcleo e o barril — sua "assinatura" de cor no bioma.

Builder cacheado por `cell` (§7). Zonas → cor em `_ZONE_COLORS`. Núcleo ('c') e
boca do barril ('b') animados por cima no `draw`.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import pygame

from . import city_palette as pal

RGB = Tuple[int, int, int]

PIXEL_COLS = 15
PIXEL_ROWS = 15
_CX = (PIXEL_COLS - 1) / 2.0  # 7.0
_BODY_CY = 8.6                # corpo deslocado p/ baixo (barril ocupa o topo)
_BODY_R = 5.4
_CORE_R = 1.9

_ZONE_COLORS: Dict[str, RGB] = {
    "o": pal.OUTLINE,
    "a": pal.HULL_LIGHT,
    "m": (78, 86, 104),
    "l": pal.GUNMETAL,
    "h": pal.HULL_SHADOW,
    "d": pal.DEEP_SLATE,
    "c": pal.TOXIC_ORANGE_DIM,   # núcleo (glow animado no draw)
    "b": pal.TOXIC_ORANGE,       # boca do barril (glow animado no draw)
}

CORE_NEON: RGB = pal.TOXIC_ORANGE
CORE_NEON_DIM: RGB = pal.TOXIC_ORANGE_DIM
BARREL_NEON: RGB = pal.TOXIC_ORANGE


def _build_map() -> List[str]:
    grid = [["." for _ in range(PIXEL_COLS)] for _ in range(PIXEL_ROWS)]

    # Corpo-esfera blindado (top-lit), igual ao molde do Captor.
    for y in range(PIXEL_ROWS):
        for x in range(PIXEL_COLS):
            dx = x - _CX
            dy = y - _BODY_CY
            d = math.hypot(dx, dy)
            if d > _BODY_R + 0.4:
                continue
            if d > _BODY_R - 1.0:
                grid[y][x] = "o"
                continue
            if d < _CORE_R:
                grid[y][x] = "c"
                continue
            lit = (-dy - dx * 0.45) / _BODY_R
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

    # Barril de morteiro: coluna curta de 3 de largura saindo do topo do corpo.
    cx = int(_CX)
    for r in range(0, 5):
        for c in (cx - 1, cx, cx + 1):
            grid[r][c] = "h"
        # contorno lateral do barril
        grid[r][cx - 2] = "o"
        grid[r][cx + 2] = "o"
    # Boca do barril (topo) + tampa de contorno.
    for c in (cx - 1, cx, cx + 1):
        grid[0][c] = "b"
    return ["".join(row) for row in grid]


PIXEL_MAP: List[str] = _build_map()

CORE_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "c"
]
BARREL_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "b"
]
# Boca do barril (origem do flash de disparo): célula 'b' mais alta, ao centro.
MUZZLE_CELL: Tuple[int, int] = (int(_CX), 0)

assert len(PIXEL_MAP) == PIXEL_ROWS and all(len(r) == PIXEL_COLS for r in PIXEL_MAP)
assert CORE_CELLS, "núcleo do morteiro não foi gerado"
assert BARREL_CELLS, "boca do barril não foi gerada"

_cache: Dict[int, pygame.Surface] = {}


def build_mortar_surface(cell: int) -> pygame.Surface:
    """Surface estática do Artilheiro, cacheada por `cell`."""
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
