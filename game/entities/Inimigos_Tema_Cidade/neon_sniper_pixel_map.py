"""Neon Sniper — Layered Pixel-Map.

Drone **alongado** com "rifle" integrado: corpo vertical estreito com a luneta
(núcleo emissivo) na parte superior, estabilizadores laterais (asas mecânicas)
no meio e o cano/boca de disparo apontando para baixo. Mesmo esquema de zonas do
City Drone (`city_drone_pixel_map`): grade 15×15 de letras → cor da paleta do
bioma (`city_palette`). O builder constrói uma Surface escalada e cacheada.

Diferente do City Drone, o Sniper tem **uma** identidade de cor fixa (sem
variantes): chassi gunmetal, núcleo magenta (a luneta que pulsa e implode na
morte) e acentos em azul elétrico (ponta do cano + asas).

Legenda de zona:
  '.' transparente   'o' contorno       'h' chassi (gunmetal)
  'l' luz do chassi  's' sombra         'w' fiação (laranja)
  'n' núcleo neon (magenta)   'm' acento emissivo (azul: boca + asas)
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

from . import city_palette as pal

RGB = Tuple[int, int, int]

# ── Grade 15×15 ─────────────────────────────────────────────────────────────
# Corpo vertical: luneta (n) em cima, asas (m nas pontas) no meio, cano (m boca)
# embaixo. Simétrico em torno da coluna 7.
PIXEL_MAP: List[str] = [
    ".....ooooo.....",
    "....ohhhhho....",
    "....ohlllho....",
    "....ohlnlho....",
    "....ohwnwho....",
    "....ohlnlho....",
    ".oohhlllllhhoo.",
    "mohhlllllllhhom",
    ".oohhssssshhoo.",
    "....ohsssho....",
    "......oho......",
    "......oso......",
    "......oso......",
    "......omo......",
    "......ooo......",
]

PIXEL_COLS = 15
PIXEL_ROWS = 15

# Zonas estáticas resolvidas para cor da paleta.
_ZONE_COLORS: Dict[str, RGB] = {
    "o": pal.OUTLINE,
    "h": pal.GUNMETAL,
    "l": pal.HULL_LIGHT,
    "s": pal.HULL_SHADOW,
    "w": pal.TOXIC_ORANGE,
    "n": pal.CYBER_MAGENTA_DIM,  # núcleo: base escura; o glow vivo é animado no draw
    "m": pal.ELECTRIC_BLUE_DIM,  # acento: idem
}

# Cor "viva" dos cells animados (lidos pelo render para o glow pulsante).
CORE_NEON: RGB = pal.CYBER_MAGENTA
CORE_NEON_DIM: RGB = pal.CYBER_MAGENTA_DIM
ACCENT_NEON: RGB = pal.ELECTRIC_BLUE
ACCENT_NEON_DIM: RGB = pal.ELECTRIC_BLUE_DIM

# Posições (col, row) consultadas pelo render para o glow animado.
NEON_CELLS: List[Tuple[int, int]] = [
    (c, r)
    for r, row in enumerate(PIXEL_MAP)
    for c, ch in enumerate(row)
    if ch == "n"
]
ACCENT_CELLS: List[Tuple[int, int]] = [
    (c, r)
    for r, row in enumerate(PIXEL_MAP)
    for c, ch in enumerate(row)
    if ch == "m"
]
# A boca do cano é o acento mais baixo (maior row) — usado para o flash de disparo.
MUZZLE_CELL: Tuple[int, int] = max(ACCENT_CELLS, key=lambda cr: cr[1])

# Validação de integridade do mapa (falha cedo se alguém editar errado).
assert len(PIXEL_MAP) == PIXEL_ROWS, "PIXEL_MAP deve ter 15 linhas"
assert all(len(row) == PIXEL_COLS for row in PIXEL_MAP), (
    "Toda linha de PIXEL_MAP deve ter 15 colunas"
)

# Cache de surfaces estáticas por `cell` (todos os snipers do mesmo tamanho
# reusam a mesma surface — §7: sem alocação repetida por frame).
_surface_cache: Dict[int, pygame.Surface] = {}


def build_sniper_surface(cell: int) -> pygame.Surface:
    """Constrói (ou reusa do cache) a surface estática do chassi do Sniper.

    `cell` = lado em pixels de cada bloco do pixel-map. A surface mede
    (PIXEL_COLS*cell, PIXEL_ROWS*cell).
    """
    cached = _surface_cache.get(cell)
    if cached is not None:
        return cached

    surface = pygame.Surface((PIXEL_COLS * cell, PIXEL_ROWS * cell), pygame.SRCALPHA)
    for row_i, row in enumerate(PIXEL_MAP):
        for col_i, ch in enumerate(row):
            color = _ZONE_COLORS.get(ch)
            if color is None:
                continue
            surface.fill(color, (col_i * cell, row_i * cell, cell, cell))

    _surface_cache[cell] = surface
    return surface
