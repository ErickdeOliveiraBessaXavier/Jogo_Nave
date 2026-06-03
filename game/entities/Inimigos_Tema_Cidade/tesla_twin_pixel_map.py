"""Tesla Twin — Layered Pixel-Map (torre vertical com bobina de cobre).

"A Barreira Vertical" da proposta: uma **unidade vertical** com uma grande
**bobina de cobre** numa das pontas (o emissor do arco) e um **núcleo azul**
emissivo no corpo. O sprite é desenhado com a bobina na parte de baixo (gêmeo
do topo, arco descendo); o gêmeo da base usa o mesmo sprite **espelhado na
vertical** (`pygame.transform.flip`), com a bobina apontando para cima.

Builder cacheado por `cell` (§7). Zonas → cor em `_ZONE_COLORS`.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

from . import city_palette as pal

RGB = Tuple[int, int, int]

PIXEL_COLS = 9
PIXEL_ROWS = 15
_CX = (PIXEL_COLS - 1) / 2.0  # 4.0
_COIL_START = 10  # linhas 10..14 = bobina emissora (windings de cobre)

_ZONE_COLORS: Dict[str, RGB] = {
    "o": pal.OUTLINE,
    "a": pal.HULL_LIGHT,         # face iluminada (topo-esquerda)
    "g": pal.GUNMETAL,           # corpo
    "h": pal.HULL_SHADOW,        # sombra
    "d": pal.DEEP_SLATE,         # base em sombra
    "c": pal.ELECTRIC_BLUE_DIM,  # núcleo (glow animado no draw)
    "w": pal.TOXIC_ORANGE,       # cobre brilhante (winding)
    "k": pal.TOXIC_ORANGE_DIM,   # cobre escuro (winding)
}

CORE_NEON: RGB = pal.ELECTRIC_BLUE
CORE_NEON_DIM: RGB = pal.ELECTRIC_BLUE_DIM
COIL_NEON: RGB = pal.TOXIC_ORANGE


def _half_width(y: int) -> float:
    """Meia-largura (em cells) do perfil da torre por linha."""
    if y == 0:
        return 2.0
    if y == 1:
        return 2.8
    if y < _COIL_START:
        return 3.2  # corpo reto
    # Bobina: bandas alternadas (mais larga / mais estreita) → look de windings.
    return 4.0 if (y - _COIL_START) % 2 == 0 else 3.3


def _build_map() -> List[str]:
    grid = [["." for _ in range(PIXEL_COLS)] for _ in range(PIXEL_ROWS)]
    for y in range(PIXEL_ROWS):
        half = _half_width(y)
        for x in range(PIXEL_COLS):
            d = abs(x - _CX)
            if d > half + 0.25:
                continue
            outline = d > half - 0.8
            if y >= _COIL_START:
                # Bobina de cobre: windings claros/escuros alternados.
                grid[y][x] = "o" if outline else (
                    "w" if (y - _COIL_START) % 2 == 0 else "k"
                )
                continue
            if outline:
                grid[y][x] = "o"
                continue
            # Núcleo azul (indicador de estado) no meio do corpo.
            if 4 <= y <= 7 and d <= 1.1:
                grid[y][x] = "c"
                continue
            # Sombreamento top-lit (luz vinda da esquerda).
            rel = x - _CX
            if rel <= -1.5:
                grid[y][x] = "a"
            elif rel <= 0.5:
                grid[y][x] = "g"
            elif rel <= 1.8:
                grid[y][x] = "h"
            else:
                grid[y][x] = "d"
    return ["".join(row) for row in grid]


PIXEL_MAP: List[str] = _build_map()

CORE_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "c"
]
COIL_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "w"
]

assert len(PIXEL_MAP) == PIXEL_ROWS and all(len(r) == PIXEL_COLS for r in PIXEL_MAP)
assert CORE_CELLS and COIL_CELLS, "núcleo/bobina da torre não foram gerados"

_cache: Dict[int, pygame.Surface] = {}


def build_tower_surface(cell: int) -> pygame.Surface:
    """Surface estática da torre (bobina embaixo), cacheada por `cell`."""
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
