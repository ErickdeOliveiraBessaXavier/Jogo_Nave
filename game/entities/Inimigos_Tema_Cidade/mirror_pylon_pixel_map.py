"""Mirror Pylon (Refletor) — Estrutura Triangular Equilibrada.

Refinamento (§5):
- Grid 32x41: a coluna extra à direita evita que o contorno do Núcleo (centro
  x=24, raio 6 + borda) seja cortado pela borda do grid — sem isso a esfera fica
  assimétrica (incha para a esquerda). Proporções compactas e equilibradas.
- Emiissores (Frontais): Menores (raio 3), mais próximos do núcleo.
- Núcleo (Traseiro): Elemento dominante (raio 6).
- A reflexão é restaurada logicamente nos feixes entre os emissores.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import pygame

from . import city_palette as pal

RGB = Tuple[int, int, int]

PIXEL_COLS = 32
PIXEL_ROWS = 41

# Cores para Emiissores (Metálicos)
EMITTER_LENS: RGB = (100, 220, 255)

# Cores para Núcleo (Energético)
CORE_SHINE: RGB = (255, 255, 255)
CORE_MAIN: RGB = (180, 240, 255)
CORE_DARK: RGB = (60, 140, 190)

_ZONE_COLORS: Dict[str, RGB] = {
    "o": pal.OUTLINE,
    "l": pal.GUNMETAL,      # Emiissor: Corpo
    "h": pal.HULL_SHADOW,   # Emiissor: Sombra
    "a": pal.HULL_LIGHT,    # Emiissor: Brilho metálico
    "e": EMITTER_LENS,      # Emiissor: Lente
    # Núcleo: Energia
    "c": CORE_SHINE,
    "g": CORE_MAIN,
    "k": CORE_DARK,
}

CORE_NEON: RGB = CORE_MAIN
CORE_NEON_DIM: RGB = CORE_DARK
MIRROR_NEON: RGB = EMITTER_LENS

def _build_pylon_map() -> List[str]:
    grid = [["." for _ in range(PIXEL_COLS)] for _ in range(PIXEL_ROWS)]

    def draw_sphere(
        cx: int,
        cy: int,
        radius: int,
        main_ch: str,
        shine_ch: str,
        dark_ch: str,
        outline_ch: str,
        lens_ch: Optional[str] = None,
    ) -> None:
        for y in range(cy - radius - 1, cy + radius + 2):
            for x in range(cx - radius - 1, cx + radius + 2):
                if x < 0 or x >= PIXEL_COLS or y < 0 or y >= PIXEL_ROWS:
                    continue
                d = math.hypot(x - cx, y - cy)
                if d > radius + 0.5:
                    if d <= radius + 1.2:
                        grid[y][x] = outline_ch
                    continue
                
                if lens_ch and d < 1.2:
                    grid[y][x] = lens_ch
                elif d < radius * 0.4:
                    grid[y][x] = shine_ch
                elif d < radius * 0.8:
                    grid[y][x] = main_ch
                else:
                    grid[y][x] = dark_ch

    # 1. Emiissores Frontais (x=11, y=5 e y=35) - Distância aumentada 1.5x
    draw_sphere(11, 5, 3, "l", "a", "h", "o", "e")
    draw_sphere(11, 35, 3, "l", "a", "h", "o", "e")

    # 2. Núcleo Traseiro (x=24, y=20) - Sem borda preta (usa 'k' como outline)
    draw_sphere(24, 20, 6, "g", "c", "k", "k")

    return ["".join(row) for row in grid]

PIXEL_MAP: List[str] = _build_pylon_map()

CORE_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch in ("c", "g")
]
MIRROR_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "e"
]

assert len(PIXEL_MAP) == PIXEL_ROWS and all(len(r) == PIXEL_COLS for r in PIXEL_MAP)

_cache: Dict[int, pygame.Surface] = {}

def build_pylon_surface(cell: int) -> pygame.Surface:
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
