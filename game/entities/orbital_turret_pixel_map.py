"""Torreta Orbital — Pixel-Map do núcleo (olho energético).

O novo OrbitalTurret é um **olho de energia** central orbitado por três esferas
elétricas instáveis. Este módulo define apenas o núcleo: anel de blindagem
(`h`), esclera energética (`e`), íris (`i`) e miolo da íris (`p`). A pupila que
**rastreia o jogador** e o glint são dinâmicos, desenhados pelo render por cima
da íris — o pixel-map é a base estática cacheada (§7).

As esferas orbitais são procedurais (orbitam por ângulo, com ruído elétrico
animado) — não há como representá-las numa grade fixa. A colisão da entidade
respeita a silhueta real via `collision_circles()` (olho + 3 esferas), não uma
hitbox genérica (§8).

Mesma convenção dos demais pixel-maps: grade 15×15 de letras → cor da paleta;
builder constrói Surfaces por camada, cacheadas por `cell`.

Legenda de zona:
  '.' transparente   'o' contorno   'h' blindagem (anel)
  'e' esclera energética   'i' íris   'p' miolo da íris (tom mais fundo)
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

RGB = Tuple[int, int, int]

# ── Grade 15×15 (olho circular, simétrico) ──────────────────────────────────
PIXEL_MAP: List[str] = [
    ".....ooooo.....",
    "...oohhhhhoo...",
    "..ohhheeehhho..",
    ".ohheeeeeeehho.",
    ".oheeeiiieeeho.",
    "oheeeiiiiieeeho",
    "oheeiiipiiieeho",
    "oheeiipppiieeho",
    "oheeiiipiiieeho",
    "oheeeiiiiieeeho",
    ".oheeeiiieeeho.",
    ".ohheeeeeeehho.",
    "..ohhheeehhho..",
    "...oohhhhhoo...",
    ".....ooooo.....",
]

PIXEL_COLS = 15
PIXEL_ROWS = 15

# ── Paleta ──────────────────────────────────────────────────────────────────
OUTLINE: RGB = (14, 18, 34)
ARMOR: RGB = (62, 80, 112)          # anel de blindagem (gunmetal azulado)
SCLERA: RGB = (38, 70, 110)         # esclera energética (base dim)
IRIS: RGB = (96, 190, 240)          # íris ciano (base; glow vivo é animado)
IRIS_DEEP: RGB = (60, 140, 200)     # miolo da íris (profundidade)

# Cores "vivas" lidas pelo render para glow/arcos animados.
EYE_GLOW: RGB = (130, 215, 255)
EYE_GLOW_DIM: RGB = (50, 100, 160)
SPHERE_CORE: RGB = (235, 250, 255)
SPHERE_MID: RGB = (130, 200, 255)
SPHERE_DIM: RGB = (70, 120, 190)
ARC_COLOR: RGB = (180, 235, 255)
ARC_HOT: RGB = (255, 255, 255)
PUPIL: RGB = (10, 16, 30)

_ZONE_COLORS: Dict[str, RGB] = {
    "o": OUTLINE,
    "h": ARMOR,
    "e": SCLERA,
    "i": IRIS,
    "p": IRIS_DEEP,
}

# Validação de integridade (falha cedo se alguém editar errado).
assert len(PIXEL_MAP) == PIXEL_ROWS, "PIXEL_MAP deve ter 15 linhas"
assert all(len(row) == PIXEL_COLS for row in PIXEL_MAP), (
    "Toda linha de PIXEL_MAP deve ter 15 colunas"
)

# ── Caches (§7: construído uma vez por `cell`) ──────────────────────────────
_layers_cache: Dict[int, Dict[str, pygame.Surface]] = {}
_glow_cache: Dict[Tuple[int, RGB], pygame.Surface] = {}

_HULL_CHARS = frozenset("oh")
_EYE_CHARS = frozenset("eip")


def build_layers(cell: int) -> Dict[str, pygame.Surface]:
    """Constrói (ou reusa do cache) as surfaces do núcleo: 'hull' e 'eye'.

    Camadas separadas para o hit-flash clarear o anel sem lavar a íris, e para
    o render aplicar glow só na parte energética.
    """
    cached = _layers_cache.get(cell)
    if cached is not None:
        return cached

    size = (PIXEL_COLS * cell, PIXEL_ROWS * cell)
    layers = {
        "hull": pygame.Surface(size, pygame.SRCALPHA),
        "eye": pygame.Surface(size, pygame.SRCALPHA),
    }
    for row_i, row in enumerate(PIXEL_MAP):
        for col_i, ch in enumerate(row):
            if ch == ".":
                continue
            layer = layers["hull"] if ch in _HULL_CHARS else layers["eye"]
            layer.fill(_ZONE_COLORS[ch], (col_i * cell, row_i * cell, cell, cell))

    _layers_cache[cell] = layers
    return layers


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
