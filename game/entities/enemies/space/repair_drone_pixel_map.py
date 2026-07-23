"""Drone Reconstrutor — Pixel-Map (linhagem STARFIELD).

Identidade **espacial**, não "nó neon": é um **satélite de salvagem** — corpo
metálico (alumínio de nave) embrulhado em **manta dourada (foil térmico)**, dois
**painéis solares** azuis flanqueando, e um pequeno **bico de solda** verde na
base, de onde sai o feixe que remonta um aliado abatido. O verde é o **único**
ponto luminoso (glow animado no render); todo o resto é casco estático/metálico —
deliberadamente distante do glow saturado do bioma Cidade Neon.

Convenção dos pixel-maps do projeto: grade de letras → cor da paleta; casco
construído por `cell` e cacheado (§7); o bico ('w') recebe glow no render.

Legenda de zona:
  '.' transparente   'o' contorno         'a' aço (luz)      'm' aço (meio)
  'h' aço (sombra)   'f' manta dourada    'p' painel (escuro) 'q' painel (célula)
  'w' bico de solda (glow animado)
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

RGB = Tuple[int, int, int]

# Silhueta de satélite: corpo central alto com painéis solares laterais,
# antena no topo e bico de solda alongado na base.
PIXEL_MAP: List[str] = [
    ".........o.........",  # 0  ponta da antena
    "........oao........",  # 1  antena (metal)
    ".......ooaoo.......",  # 2  topo do corpo
    "......oafffao......",  # 3  manta térmica (foil)
    "oooooo.oagao.oooooo",  # 4  topo dos painéis + brilho foil
    "opqpqo.oafao.oqpqpo",  # 5  painéis solares
    "oqpqpomfgggfmopqpqo",  # 6  mastro central cruzando o corpo
    "opqpqo.oafao.oqpqpo",  # 7
    "oooooo.oafao.oooooo",  # 8  base dos painéis
    "......oafffao......",  # 9
    ".......oafao.......",  # 10
    ".......oawao.......",  # 11 bico de solda
    ".......ohwho.......",  # 12 base do bico
]

PIXEL_COLS = 19
PIXEL_ROWS = 13

# ── Paleta espacial ──────────────────────────────────────────────────────────
OUTLINE: RGB = (12, 16, 30)
STEEL_LIGHT: RGB = (150, 160, 178)  # alumínio iluminado
STEEL_MID: RGB = (92, 102, 122)
STEEL_SHADOW: RGB = (50, 58, 78)
GOLD_FOIL: RGB = (214, 172, 80)  # manta térmica dourada (foil térmico)
GOLD_BRIGHT: RGB = (255, 225, 140)  # brilho metálico na manta
PANEL_DARK: RGB = (26, 50, 102)  # moldura/sombra do painel solar
PANEL_CELL: RGB = (72, 124, 208)  # célula solar azul
WELD: RGB = (90, 255, 150)  # bico de solda (verde reconstrução)
WELD_DIM: RGB = (34, 130, 92)
# Painéis "carregados" de energia de reconstrução (verde) — usados no cross-fade
# das asas enquanto o drone canaliza a ressurreição de um aliado.
CHARGE_DARK: RGB = (18, 92, 60)
CHARGE_CELL: RGB = (96, 255, 150)

_ZONE_COLORS: Dict[str, RGB] = {
    "o": OUTLINE,
    "a": STEEL_LIGHT,
    "m": STEEL_MID,
    "h": STEEL_SHADOW,
    "f": GOLD_FOIL,
    "g": GOLD_BRIGHT,
    "p": PANEL_DARK,
    "q": PANEL_CELL,
    "w": WELD_DIM,  # base do bico; glow vivo é animado no render
}

EMITTER_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "w"
]

assert len(PIXEL_MAP) == PIXEL_ROWS, "PIXEL_MAP deve ter 13 linhas"
assert all(len(row) == PIXEL_COLS for row in PIXEL_MAP), (
    "cada linha deve ter 19 colunas"
)
assert EMITTER_CELLS, "precisa de ao menos um bico de solda 'w'"
# Satélite é simétrico esquerda/direita: cada linha deve ser um palíndromo. Pega
# painéis/asas desalinhados na hora de editar o mapa à mão.
for _i, _row in enumerate(PIXEL_MAP):
    assert _row == _row[::-1], f"linha {_i} não é simétrica (esq≠dir): {_row!r}"

# ── Caches (§7: construídos uma vez por chave) ──────────────────────────────
_hull_cache: Dict[int, pygame.Surface] = {}
_parts_cache: Dict[int, Dict[str, pygame.Surface]] = {}
_glow_cache: Dict[Tuple[int, RGB], pygame.Surface] = {}


def build_hull_surface(cell: int) -> pygame.Surface:
    """Surface estática completa (legado), cacheada por `cell`."""
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


def build_parts(cell: int) -> Dict[str, pygame.Surface]:
    """Cria superfícies separadas para corpo e asas (para animação)."""
    cached = _parts_cache.get(cell)
    if cached is not None:
        return cached

    # Dimensões lógicas:
    # Asa Esq: 0-5 (6 cols) | Mastro Esq: 6 (1 col) | Corpo: 7-11 (5 cols) | ...
    body_surf = pygame.Surface((5 * cell, PIXEL_ROWS * cell), pygame.SRCALPHA)
    left_wing = pygame.Surface((6 * cell, PIXEL_ROWS * cell), pygame.SRCALPHA)
    right_wing = pygame.Surface((6 * cell, PIXEL_ROWS * cell), pygame.SRCALPHA)
    left_mast = pygame.Surface((1 * cell, PIXEL_ROWS * cell), pygame.SRCALPHA)
    right_mast = pygame.Surface((1 * cell, PIXEL_ROWS * cell), pygame.SRCALPHA)

    for r, row in enumerate(PIXEL_MAP):
        for c, ch in enumerate(row):
            color = _ZONE_COLORS.get(ch)
            if color is None:
                continue
            if 0 <= c <= 5:    # Asa Esquerda
                left_wing.fill(color, (c * cell, r * cell, cell, cell))
            elif c == 6:       # Mastro Esquerdo
                left_mast.fill(color, (0, r * cell, cell, cell))
            elif 7 <= c <= 11: # Corpo Central
                body_surf.fill(color, ((c - 7) * cell, r * cell, cell, cell))
            elif c == 12:      # Mastro Direito
                right_mast.fill(color, (0, r * cell, cell, cell))
            elif 13 <= c <= 18: # Asa Direita
                right_wing.fill(color, ((c - 13) * cell, r * cell, cell, cell))

    res = {
        "body": body_surf,
        "left_wing": left_wing,
        "right_wing": right_wing,
        "left_mast": left_mast,
        "right_mast": right_mast,
    }
    _parts_cache[cell] = res
    return res


_charged_wings_cache: Dict[int, Dict[str, pygame.Surface]] = {}


def build_charged_wings(cell: int) -> Dict[str, pygame.Surface]:
    """Asas com os painéis recoloridos de verde (energia de reconstrução).

    Idênticas às asas normais exceto pelas células solares ('p'/'q'), que viram
    verde — para o cross-fade azul→verde durante a canalização da ressurreição.
    Cacheado por `cell` (§7)."""
    cached = _charged_wings_cache.get(cell)
    if cached is not None:
        return cached
    zone = {**_ZONE_COLORS, "p": CHARGE_DARK, "q": CHARGE_CELL}
    left = pygame.Surface((6 * cell, PIXEL_ROWS * cell), pygame.SRCALPHA)
    right = pygame.Surface((6 * cell, PIXEL_ROWS * cell), pygame.SRCALPHA)
    for r, row in enumerate(PIXEL_MAP):
        for c, ch in enumerate(row):
            color = zone.get(ch)
            if color is None:
                continue
            if 0 <= c <= 5:
                left.fill(color, (c * cell, r * cell, cell, cell))
            elif 13 <= c <= 18:
                right.fill(color, ((c - 13) * cell, r * cell, cell, cell))
    res = {"left_wing": left, "right_wing": right}
    _charged_wings_cache[cell] = res
    return res


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
        a = int(110 * (1.0 - i / steps) ** 2)
        if rr > 0 and a > 0:
            pygame.draw.circle(glow, (r, g, b, a), (radius, radius), rr)
    _glow_cache[key] = glow
    return glow
