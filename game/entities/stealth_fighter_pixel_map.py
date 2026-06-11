"""Sentinela Aranha (StealthFighter) — Pixel-Map em camadas.

Pequena sentinela tecnológica do bioma STARFIELD: uma **gema energética**
central (o canhão de laser) sustentada por um chassi mecânico, com **patas
superiores e inferiores** que a fazem "escalar" as bordas da arena. As patas
são camadas independentes para animar caminhada e a "abertura" das estruturas
durante o carregamento do laser; a gema pulsa por glow animado no render.

Grade 15×15 de zonas (mesma convenção dos demais pixel-maps: letra → cor da
paleta). O builder constrói **uma surface por camada** (cacheada por `cell`),
para que o render componha o bicho com offsets próprios sem alocar por frame
(§7). A máscara de colisão é derivada da silhueta completa (gema + chassi +
patas em pose neutra), respeitando o formato visual em vez de uma hitbox
genérica (§8).

Legenda de zona:
  '.' transparente   'o' contorno          'h' chassi
  'l' luz do chassi  's' sombra do chassi   'u' pata superior   'd' pata inferior
  'm' ponta de pata (acento emissivo)       'n' gema (base)      'c' núcleo da gema
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

RGB = Tuple[int, int, int]

# ── Grade 15×15 (simétrica em torno da coluna 7) ────────────────────────────
PIXEL_MAP: List[str] = [
    "...m.......m...",
    "...u.......u...",
    "...u.......u...",
    "...uu.....uu...",
    "....uo...ou....",
    ".....ohhho.....",
    "....ohnnnho....",
    "....ohncnho....",
    "....ohnnnho....",
    ".....ohhho.....",
    "....do...od....",
    "...dd.....dd...",
    "...d.......d...",
    "...d.......d...",
    "...m.......m...",
]

PIXEL_COLS = 15
PIXEL_ROWS = 15

# ── Paleta ──────────────────────────────────────────────────────────────────
OUTLINE: RGB = (18, 14, 30)
CHASSIS: RGB = (66, 60, 100)
CHASSIS_LIGHT: RGB = (104, 96, 150)
CHASSIS_SHADOW: RGB = (40, 36, 64)
LEG: RGB = (84, 78, 124)
LEG_TIP: RGB = (120, 224, 255)   # acento ciano (base; o glow vivo é animado)
GEM_BASE: RGB = (120, 56, 200)   # gema roxa (base dim)
GEM_CORE: RGB = (196, 150, 255)  # núcleo claro

# Cores "vivas" para o glow animado lido pelo render.
GEM_GLOW: RGB = (180, 90, 255)
GEM_GLOW_DIM: RGB = (92, 42, 150)
ACCENT_GLOW: RGB = (150, 232, 255)

_ZONE_COLORS: Dict[str, RGB] = {
    "o": OUTLINE,
    "h": CHASSIS,
    "l": CHASSIS_LIGHT,
    "s": CHASSIS_SHADOW,
    "u": LEG,
    "d": LEG,
    "m": LEG_TIP,
    "n": GEM_BASE,
    "c": GEM_CORE,
}

# Cada célula vai para uma camada de render independente. Pontas 'm' acompanham
# a pata do seu lado (acima/abaixo da linha central, row 7).
_CHASSIS_CHARS = frozenset("ohls")
_MID_ROW = PIXEL_ROWS // 2  # 7


def _layer_of(ch: str, row: int) -> str | None:
    if ch == ".":
        return None
    if ch in _CHASSIS_CHARS:
        return "chassis"
    if ch in ("n", "c"):
        return "gem"
    if ch == "u" or (ch == "m" and row < _MID_ROW):
        return "upper_legs"
    if ch == "d" or (ch == "m" and row > _MID_ROW):
        return "lower_legs"
    return None


# Posições (col, row) consultadas pelo render para o glow animado.
GEM_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch in ("n", "c")
]
CORE_CELL: Tuple[int, int] = next(
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "c"
)
ACCENT_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "m"
]

# Validação de integridade (falha cedo se alguém editar errado).
assert len(PIXEL_MAP) == PIXEL_ROWS, "PIXEL_MAP deve ter 15 linhas"
assert all(len(row) == PIXEL_COLS for row in PIXEL_MAP), (
    "Toda linha de PIXEL_MAP deve ter 15 colunas"
)

# ── Caches (§7: construído uma vez por `cell`) ──────────────────────────────
_layers_cache: Dict[int, Dict[str, pygame.Surface]] = {}
_mask_cache: Dict[int, pygame.mask.Mask] = {}
_glow_cache: Dict[Tuple[int, RGB], pygame.Surface] = {}

_LAYER_ORDER = ("lower_legs", "upper_legs", "chassis", "gem")


def build_layers(cell: int) -> Dict[str, pygame.Surface]:
    """Constrói (ou reusa do cache) as surfaces por camada do bicho.

    Retorna um dict {nome_da_camada: Surface}, cada uma do tamanho do canvas
    inteiro (PIXEL_COLS*cell, PIXEL_ROWS*cell), com apenas as células daquela
    camada preenchidas — assim o render blita cada uma com seu próprio offset.
    """
    cached = _layers_cache.get(cell)
    if cached is not None:
        return cached

    size = (PIXEL_COLS * cell, PIXEL_ROWS * cell)
    layers = {name: pygame.Surface(size, pygame.SRCALPHA) for name in _LAYER_ORDER}
    for row_i, row in enumerate(PIXEL_MAP):
        for col_i, ch in enumerate(row):
            layer = _layer_of(ch, row_i)
            if layer is None:
                continue
            color = _ZONE_COLORS[ch]
            layers[layer].fill(color, (col_i * cell, row_i * cell, cell, cell))

    _layers_cache[cell] = layers
    return layers


def build_collision_mask(cell: int) -> pygame.mask.Mask:
    """Máscara pixel-perfect da silhueta completa (pose neutra), cacheada."""
    cached = _mask_cache.get(cell)
    if cached is not None:
        return cached

    surface = pygame.Surface((PIXEL_COLS * cell, PIXEL_ROWS * cell), pygame.SRCALPHA)
    for row_i, row in enumerate(PIXEL_MAP):
        for col_i, ch in enumerate(row):
            if ch == ".":
                continue
            surface.fill((255, 255, 255, 255), (col_i * cell, row_i * cell, cell, cell))

    mask = pygame.mask.from_surface(surface, 1)
    _mask_cache[cell] = mask
    return mask


def get_glow(radius: int, color: RGB) -> pygame.Surface:
    """Surface de glow radial (BLEND_RGBA_ADD), cacheada por (raio, cor)."""
    radius = max(1, radius)
    key = (radius, color)
    cached = _glow_cache.get(key)
    if cached is not None:
        return cached

    diam = radius * 2
    glow = pygame.Surface((diam, diam), pygame.SRCALPHA)
    r, g, b = color
    steps = max(2, radius)
    for i in range(steps, 0, -1):
        rr = int(radius * i / steps)
        a = int(120 * (1.0 - i / steps) ** 2)
        if rr > 0 and a > 0:
            pygame.draw.circle(glow, (r, g, b, a), (radius, radius), rr)
    _glow_cache[key] = glow
    return glow
