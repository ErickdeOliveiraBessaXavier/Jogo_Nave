"""Police Interceptor — Layered Pixel-Map.

"O Perseguidor" da proposta: viatura aérea pesada e aerodinâmica, **vista de
cima** (coerente com o side-scroll do bioma CITY — o mundo entra pela direita e
a unidade aponta o nariz para a esquerda, em direção ao jogador). Por ser uma
silhueta top-down, o chassi é **simétrico no eixo vertical** (espelhado em torno
da linha do meio), como o disco do City Drone.

Camadas (mesmo esquema de zonas dos irmãos `city_drone_pixel_map` /
`neon_sniper_pixel_map`): grade de letras → cor da paleta do bioma
(`city_palette`); o builder constrói uma Surface escalada e cacheada (§7).

Identidade de cor fixa: chassi gunmetal aerodinâmico, **uma turbina-foguete
central** na traseira com brilho **laranja tóxico** (a assinatura visual: um
bocal único que cospe um rastro de chama, mais longo no dash) e uma **barra de
luzes azul** central que pisca (estrobo de patrulha).

Legenda de zona:
  '.' transparente   'o' contorno       'h' chassi (gunmetal)
  'l' luz do chassi  's' sombra         'w' fiação (laranja, estática)
  't' bocal do foguete (laranja: glow/plume animado)   'b' barra de luz (azul: animada)
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

from . import city_palette as pal

RGB = Tuple[int, int, int]

# ── Grade 19×11 ─────────────────────────────────────────────────────────────
# Nariz em cunha ultra-aerodinâmico apontando para a ESQUERDA (cols 0-2),
# corpo alongado e bocal-foguete (t) na traseira-centro (cols 17-18).
# Simétrica em torno da linha 5.
PIXEL_MAP: List[str] = [
    "...........oooo....",
    ".........oohhhho...",
    ".......oohhhhhhho..",
    ".....oohhlllllllho.",
    "...oohhhllbbbbllhht",
    "oohhhhwwbbbbbbwwltt",
    "...oohhhllbbbbllhht",
    ".....oohhlllllllho.",
    ".......oohhhhhhho..",
    ".........oohhhho...",
    "...........oooo....",
]

PIXEL_COLS = 19
PIXEL_ROWS = 11

# Zonas estáticas resolvidas para cor da paleta.
_ZONE_COLORS: Dict[str, RGB] = {
    "o": pal.OUTLINE,
    "h": pal.GUNMETAL,
    "l": pal.HULL_LIGHT,
    "s": pal.HULL_SHADOW,
    "w": pal.TOXIC_ORANGE,
    "t": pal.TOXIC_ORANGE_DIM,  # turbina: base escura; o glow vivo é animado no draw
    "b": pal.ELECTRIC_BLUE_DIM,  # barra de luz: idem
}

# Cor "viva" dos cells animados (lidos pelo render para o glow pulsante).
TURBINE_NEON: RGB = pal.TOXIC_ORANGE
TURBINE_NEON_DIM: RGB = pal.TOXIC_ORANGE_DIM
LIGHT_NEON: RGB = pal.ELECTRIC_BLUE
LIGHT_NEON_DIM: RGB = pal.ELECTRIC_BLUE_DIM

# Posições (col, row) consultadas pelo render para o glow animado.
TURBINE_CELLS: List[Tuple[int, int]] = [
    (c, r)
    for r, row in enumerate(PIXEL_MAP)
    for c, ch in enumerate(row)
    if ch == "t"
]
LIGHT_CELLS: List[Tuple[int, int]] = [
    (c, r)
    for r, row in enumerate(PIXEL_MAP)
    for c, ch in enumerate(row)
    if ch == "b"
]

# Validação de integridade do mapa (falha cedo se alguém editar errado).
assert len(PIXEL_MAP) == PIXEL_ROWS, "PIXEL_MAP deve ter 11 linhas"
assert all(len(row) == PIXEL_COLS for row in PIXEL_MAP), (
    f"Toda linha de PIXEL_MAP deve ter {PIXEL_COLS} colunas"
)

# Cache de surfaces estáticas por `cell` (§7: sem alocação repetida por frame).
_surface_cache: Dict[int, pygame.Surface] = {}


def build_interceptor_surface(cell: int) -> pygame.Surface:
    """Constrói (ou reusa do cache) a surface estática do chassi do Interceptor.

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
