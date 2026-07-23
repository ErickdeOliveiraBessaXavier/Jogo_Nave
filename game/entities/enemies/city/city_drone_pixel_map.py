"""City Drone — Layered Pixel-Map.

Chassi ultra-leve em formato de disco (saucer) com 4 micro-propulsores nas
diagonais e fiação central visível através de uma grade. O mapa é uma grade
15×15 de letras de zona; cada letra é resolvida para uma cor da paleta do
bioma (`city_palette`). O builder constrói uma Surface escalada e cacheada.

Camadas (conceito da proposta), todas codificadas no mesmo mapa por zona:
  - Base/Chassi  : 'h' hull, 'l' luz, 's' sombra, 'g' grade, 'w' fiação
  - Blindagem    : 'o' contorno externo
  - Glow (Neon)  : 'n' núcleo emissivo  (desenhado/animado por cima)
  - Acessórios   : 't' micro-propulsores (desenhados/animados por cima)

Legenda de zona:
  '.' transparente   'o' contorno      'h' chassi (gunmetal)
  'l' luz do chassi  's' sombra        'g' barra de grade
  'w' fiação         'n' núcleo neon    't' propulsor
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Tuple

import pygame

from . import city_palette as pal

RGB = Tuple[int, int, int]


class DroneVariant(NamedTuple):
    """Conjunto de cores emissivas de uma variante de drone.

    O chassi (gunmetal/slate) é o mesmo em todas para manter a coesão do bioma;
    só mudam os pixels de energia (núcleo neon, fiação e propulsores).
    """

    neon: RGB  # núcleo emissivo (glow pulsante)
    neon_dim: RGB  # cor base do núcleo na surface estática
    wire: RGB  # fiação exposta ('w')
    thruster: RGB  # micro-propulsores ('t')


# 3 variantes coesas, cada uma dominada por um dos acentos da proposta.
DRONE_VARIANTS: List[DroneVariant] = [
    DroneVariant(pal.ELECTRIC_BLUE, pal.ELECTRIC_BLUE_DIM, pal.TOXIC_ORANGE, pal.CYBER_MAGENTA),
    DroneVariant(pal.CYBER_MAGENTA, pal.CYBER_MAGENTA_DIM, pal.ELECTRIC_BLUE, pal.TOXIC_ORANGE),
    DroneVariant(pal.TOXIC_ORANGE, pal.TOXIC_ORANGE_DIM, pal.ELECTRIC_BLUE, pal.CYBER_MAGENTA),
]

# ── Grade 15×15 ─────────────────────────────────────────────────────────────
PIXEL_MAP: List[str] = [
    "...............",
    "...............",
    ".....ooooo.....",
    "...ohhhhhhho...",
    "..ohhlllllhho..",
    "tolllllllllllot",
    ".ohlllggglllho.",
    "ohllllwnwllllho",
    ".oshssgggsshso.",
    "tosssssssssssot",
    "..oshssssshso..",
    "...ossssssso...",
    ".....ooooo.....",
    "...............",
    "...............",
]

PIXEL_COLS = 15
PIXEL_ROWS = 15

# Zonas do chassi (iguais em todas as variantes → coesão do bioma).
_CHASSIS_COLORS: Dict[str, RGB] = {
    "o": pal.OUTLINE,
    "h": pal.GUNMETAL,
    "l": pal.HULL_LIGHT,
    "s": pal.HULL_SHADOW,
    "g": pal.GRID_BAR,
}

# Posições (col, row) consultadas pelo render para o glow animado.
NEON_CELLS: List[Tuple[int, int]] = [
    (c, r)
    for r, row in enumerate(PIXEL_MAP)
    for c, ch in enumerate(row)
    if ch == "n"
]
THRUSTER_CELLS: List[Tuple[int, int]] = [
    (c, r)
    for r, row in enumerate(PIXEL_MAP)
    for c, ch in enumerate(row)
    if ch == "t"
]

# Validação de integridade do mapa (falha cedo se alguém editar errado).
assert len(PIXEL_MAP) == PIXEL_ROWS, "PIXEL_MAP deve ter 15 linhas"
assert all(len(row) == PIXEL_COLS for row in PIXEL_MAP), (
    "Toda linha de PIXEL_MAP deve ter 15 colunas"
)

# Cache de surfaces estáticas por (cell, variante). Spawn em cluster com mesmo
# tamanho/cor reusa a mesma surface — §7: sem alocação repetida por frame.
_surface_cache: Dict[Tuple[int, int], pygame.Surface] = {}


def build_static_surface(cell: int, variant_index: int = 0) -> pygame.Surface:
    """Constrói (ou reusa do cache) a surface estática do chassi + energia.

    `cell` = lado em pixels de cada bloco do pixel-map; `variant_index`
    seleciona o conjunto de cores emissivas (`DRONE_VARIANTS`). A surface
    mede (PIXEL_COLS*cell, PIXEL_ROWS*cell).
    """
    key = (cell, variant_index)
    cached = _surface_cache.get(key)
    if cached is not None:
        return cached

    variant = DRONE_VARIANTS[variant_index]
    zone_colors: Dict[str, RGB] = {
        **_CHASSIS_COLORS,
        "w": variant.wire,
        "n": variant.neon_dim,
        "t": variant.thruster,
    }

    surface = pygame.Surface((PIXEL_COLS * cell, PIXEL_ROWS * cell), pygame.SRCALPHA)
    for row_i, row in enumerate(PIXEL_MAP):
        for col_i, ch in enumerate(row):
            color = zone_colors.get(ch)
            if color is None:
                continue
            surface.fill(color, (col_i * cell, row_i * cell, cell, cell))

    _surface_cache[key] = surface
    return surface
