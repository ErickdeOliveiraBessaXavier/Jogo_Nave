"""Dreadnought — pixel-map do casco (nave-capital pesada) + canhão.

Sóbrio: um **casco em cunha** (nariz à esquerda, bloco de motores à direita)
visto de cima, chapa metálica fosca com sombreamento top-lit e contorno escuro.
Poucos acentos frios (ponte de comando + luzes de posição). Sem bloom.

Dois builders cacheados por `cell` (§7): o casco estático e o cano do canhão
(aponta para +x, rotacionado no encaixe pela torre). O corpo NÃO gira (o giro de
metades era um maneirismo da CITY); aqui só as torres miram.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

from . import space_palette as pal

RGB = Tuple[int, int, int]

PIXEL_COLS = 27
PIXEL_ROWS = 15
_CR = (PIXEL_ROWS - 1) / 2.0  # linha central 7.0

# Encaixe das duas torres (fração de w/h a partir do centro): flancos superior e
# inferior, recuadas do nariz. Usadas pelo entity para posicionar/orbitar mira.
MOUNT_OFFSET_X: float = 0.06   # levemente à frente do centro
MOUNT_OFFSET_Y: float = 0.30   # afastadas do eixo (flancos)
CANNON_BARREL_CELLS: float = 3.4  # comprimento do cano em cells (p/ boca do tiro)

_ZONE_COLORS: Dict[str, RGB] = {
    "o": pal.OUTLINE,
    "s": pal.HULL_SHADOW,
    "d": pal.HULL_DARK,
    "b": pal.HULL_BASE,
    "l": pal.HULL_LIGHT,
    "H": pal.HULL_HILIGHT,
    "e": pal.VOID,            # vãos dos motores (escuro)
    "c": pal.ACCENT_COLD_DIM, # ponte/luzes (glow vivo animado no entity)
}


def _build_hull_map() -> List[str]:
    """Casco em cunha gerado por regra: para cada linha, calcula a faixa
    horizontal do casco (nariz pontudo à esquerda no centro, bloco de motores
    reto à direita) e aplica sombreamento top-lit chapado."""
    grid = [["." for _ in range(PIXEL_COLS)] for _ in range(PIXEL_ROWS)]
    x_right = PIXEL_COLS - 3  # ré (bloco de motores)
    for y in range(PIXEL_ROWS):
        dy = abs(y - _CR) / _CR  # 0 no eixo .. 1 nas bordas
        if dy > 1.0:
            continue
        # Nariz pontudo: o eixo central alcança mais à esquerda; as bordas recuam.
        x_left = int(round(1 + dy * dy * 9))
        # Ré levemente chanfrada nas linhas extremas.
        xr = x_right - int(round(dy * 2))
        for x in range(x_left, xr + 1):
            if x < 0 or x >= PIXEL_COLS:
                continue
            # Contorno.
            if x == x_left or x == xr or dy > 0.86:
                grid[y][x] = "o"
                continue
            # Bloco de motores (ré): vãos escuros intercalados.
            if x >= x_right - 2:
                grid[y][x] = "e" if (y % 2 == 0) else "s"
                continue
            # Sombreamento top-lit chapado (metade de cima mais clara).
            rel = (y - _CR) / _CR  # -1 (topo) .. +1 (base)
            if rel < -0.55:
                grid[y][x] = "H"
            elif rel < -0.15:
                grid[y][x] = "l"
            elif rel < 0.25:
                grid[y][x] = "b"
            elif rel < 0.6:
                grid[y][x] = "d"
            else:
                grid[y][x] = "s"
    # Ponte de comando (acento frio) — um bloco pequeno perto do nariz-centro.
    for yy in (int(_CR), int(_CR) - 1, int(_CR) + 1):
        for xx in (6, 7, 8):
            if 0 <= yy < PIXEL_ROWS and grid[yy][xx] not in (".", "o"):
                grid[yy][xx] = "c"
    return ["".join(row) for row in grid]


PIXEL_MAP: List[str] = _build_hull_map()

BRIDGE_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "c"
]

assert len(PIXEL_MAP) == PIXEL_ROWS and all(len(r) == PIXEL_COLS for r in PIXEL_MAP)
assert BRIDGE_CELLS, "ponte de comando não foi gerada"

_hull_cache: Dict[int, pygame.Surface] = {}
_cannon_cache: Dict[int, pygame.Surface] = {}


def build_hull_surface(cell: int) -> pygame.Surface:
    """Surface estática do casco, cacheada por `cell`."""
    cached = _hull_cache.get(cell)
    if cached is not None:
        return cached
    surface = pygame.Surface((PIXEL_COLS * cell, PIXEL_ROWS * cell), pygame.SRCALPHA)
    for row_i, row in enumerate(PIXEL_MAP):
        for col_i, ch in enumerate(row):
            color = _ZONE_COLORS.get(ch)
            if color is None:
                continue
            surface.fill(color, (col_i * cell, row_i * cell, cell, cell))
    _hull_cache[cell] = surface
    return surface


# ── Canhão (cano curto apontando +x, rotacionado no encaixe) ─────────────────
_CANNON_COLS, _CANNON_ROWS = 6, 4


def build_cannon_surface(cell: int) -> pygame.Surface:
    """Cano de canhão sóbrio (retângulo metálico com boca), aponta para +x.
    Cacheado por `cell`. Pivô = centro do sprite (o entity aplica recuo/mira)."""
    cached = _cannon_cache.get(cell)
    if cached is not None:
        return cached
    surf = pygame.Surface((_CANNON_COLS * cell, _CANNON_ROWS * cell), pygame.SRCALPHA)
    mid = _CANNON_ROWS // 2
    for c in range(_CANNON_COLS):
        for r in range(_CANNON_ROWS):
            # Base larga atrás, cano fino à frente.
            is_breech = c <= 1
            thick = _CANNON_ROWS if is_breech else 2
            if abs(r - mid) * 2 >= thick and not is_breech:
                continue
            if r == 0 or r == _CANNON_ROWS - 1 or c == _CANNON_COLS - 1:
                col = pal.OUTLINE
            elif r <= mid:
                col = pal.HULL_LIGHT
            else:
                col = pal.HULL_DARK
            surf.fill(col, (c * cell, r * cell, cell, cell))
    _cannon_cache[cell] = surf
    return surf
