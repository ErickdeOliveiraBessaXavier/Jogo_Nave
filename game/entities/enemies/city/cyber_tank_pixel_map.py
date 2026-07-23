"""Cyber Tank — Layered Pixel-Map (ampulheta horizontal).

"O Colosso Urbano": fortaleza móvel **vista de cima** (side-scroll do bioma CITY).
A silhueta é uma **ampulheta horizontal** — duas **vagens largas** nas pontas
(esquerda/direita) unidas por uma **cintura estreita** no centro, onde fica o
reator. Os **canhões** ficam integrados às duas pontas (encaixe = vagem) e são
desenhados por cima (sprite próprio `build_cannon_surface`) girando para mirar.

Estética pixel-art em camadas (top-lit, com volume), no mesmo nível dos demais
inimigos: contorno escuro, brilho specular no topo, gradiente de metal
(claro→médio→base→sombra→recesso), rebites, costuras de painel e o núcleo neon.
O corpo é **gerado** por regras a partir de um perfil de meia-altura (`_HALF`) —
mantém o look chunky de pixel art (células sólidas) com simetria perfeita nos
dois eixos, sem erros de digitação numa grade grande.

Builders cacheados por `cell` (§7): `build_tank_surface` (corpo) e
`build_cannon_surface` (barril). Zonas → cor em `_ZONE_COLORS`.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

from . import city_palette as pal

RGB = Tuple[int, int, int]

# ── Geometria do corpo (ampulheta) ───────────────────────────────────────────
PIXEL_COLS = 25
PIXEL_ROWS = 13
_CENTER_R = PIXEL_ROWS // 2  # 6

# Meia-altura (em linhas) por coluna: largo nas pontas (vagens), estreito na
# cintura, com leve bojo central (carcaça do reator). Simétrico no eixo X.
_HALF: List[int] = [4, 5, 6, 6, 5, 5, 4, 4, 3, 3, 2, 2, 3, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 5, 4]

# ── Paleta de zonas (camadas de profundidade) ────────────────────────────────
_ZONE_COLORS: Dict[str, RGB] = {
    "o": pal.OUTLINE,            # contorno
    "S": (150, 162, 184),        # brilho specular (rim light no topo)
    "a": pal.HULL_LIGHT,         # metal iluminado
    "m": (78, 86, 104),          # metal médio
    "l": pal.GUNMETAL,           # metal base
    "h": pal.HULL_SHADOW,        # sombra
    "d": pal.DEEP_SLATE,         # recesso profundo
    "r": (200, 210, 230),        # rebite (aço claro)
    "p": pal.OUTLINE,            # costura de painel
    "c": pal.ELECTRIC_BLUE_DIM,  # reator (glow animado no draw)
    "w": pal.TOXIC_ORANGE_DIM,   # conduítes/vents (glow animado no draw)
    "M": (210, 218, 235),        # boca do canhão (sprite do barril)
}

# Cores "vivas" dos cells animados (lidas pelo render para o glow pulsante).
CORE_NEON: RGB = pal.ELECTRIC_BLUE
CORE_NEON_DIM: RGB = pal.ELECTRIC_BLUE_DIM
ENGINE_NEON: RGB = pal.TOXIC_ORANGE
ENGINE_NEON_DIM: RGB = pal.TOXIC_ORANGE_DIM


_CENTER_C = PIXEL_COLS // 2  # 12 (coluna central)
# Vão entre o pod e o núcleo: o pod é recortado antes do centro, criando a
# **separação visual clara** entre as 3 partes (pod | vão | núcleo | vão | pod).
GAP_COLS = 4
_POD_INNER_COL = _CENTER_C - GAP_COLS  # 8


def _inside(x: int, r: int) -> bool:
    if x < 0 or x >= PIXEL_COLS or r < 0 or r >= PIXEL_ROWS:
        return False
    return abs(r - _CENTER_R) <= _HALF[x]


def _inside_pod(x: int, r: int) -> bool:
    # Apenas a vagem de uma ponta (lado esquerdo do canvas), recortada no vão.
    return _inside(x, r) and x <= _POD_INNER_COL


def _shade(x: int, r: int) -> str:
    """Sombreamento top-lit (volume metálico) de um cell interior."""
    h = _HALF[x]
    frac = (r - (_CENTER_R - h)) / (2 * h) if h > 0 else 0.5
    if frac < 0.25:
        return "a"
    if frac < 0.5:
        return "m"
    if frac < 0.7:
        return "l"
    if frac < 0.88:
        return "h"
    return "d"


def _build_body_map() -> List[str]:
    """Gera a grade de zonas da ampulheta (contorno + sombreamento top-lit)."""
    grid = [["." for _ in range(PIXEL_COLS)] for _ in range(PIXEL_ROWS)]

    for r in range(PIXEL_ROWS):
        for x in range(PIXEL_COLS):
            if not _inside(x, r):
                continue
            border = (
                not _inside(x, r - 1)
                or not _inside(x, r + 1)
                or not _inside(x - 1, r)
                or not _inside(x + 1, r)
            )
            if border:
                # Rim light no topo; contorno escuro no resto.
                grid[r][x] = "S" if (not _inside(x, r - 1) and r <= _CENTER_R) else "o"
                continue
            grid[r][x] = _shade(x, r)

    def interior(x: int, r: int) -> bool:
        return (
            0 <= r < PIXEL_ROWS
            and 0 <= x < PIXEL_COLS
            and grid[r][x] not in (".", "o", "S")
        )

    # Reator na cintura central.
    for r in range(5, 8):
        for x in range(11, 14):
            if interior(x, r):
                grid[r][x] = "c"
    # Conduítes laranja flanqueando o reator.
    for x in (9, 15):
        if interior(x, 6):
            grid[6][x] = "w"
    # Costuras de painel (separam vagens da cintura).
    for x in (7, 17):
        for r in (5, 6, 7):
            if interior(x, r):
                grid[r][x] = "p"
    # Rebites nas vagens das pontas.
    for x, r in ((2, 4), (2, 8), (22, 4), (22, 8), (4, 5), (4, 7), (20, 5), (20, 7)):
        if interior(x, r):
            grid[r][x] = "r"

    return ["".join(row) for row in grid]


def _build_pod_map() -> List[str]:
    """Gera UMA vagem (lado esquerdo do canvas, recortada no vão). É desenhada
    duas vezes (rotacionada por `body_spin` e +180°) → as duas metades giram em
    torno do núcleo estático. Pivô = centro do canvas (= centro do tanque)."""
    grid = [["." for _ in range(PIXEL_COLS)] for _ in range(PIXEL_ROWS)]
    for r in range(PIXEL_ROWS):
        for x in range(PIXEL_COLS):
            if not _inside_pod(x, r):
                continue
            border = (
                not _inside_pod(x, r - 1)
                or not _inside_pod(x, r + 1)
                or not _inside_pod(x - 1, r)
                or not _inside_pod(x + 1, r)
            )
            if border:
                grid[r][x] = (
                    "S" if (not _inside_pod(x, r - 1) and r <= _CENTER_R) else "o"
                )
            else:
                grid[r][x] = _shade(x, r)

    def interior(x: int, r: int) -> bool:
        return grid[r][x] not in (".", "o", "S")

    for x, r in ((2, 4), (2, 8), (4, 5), (4, 7), (6, 6)):
        if interior(x, r):
            grid[r][x] = "r"
    return ["".join(row) for row in grid]


PIXEL_MAP: List[str] = _build_body_map()
POD_MAP: List[str] = _build_pod_map()

CORE_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "c"
]
ENGINE_CELLS: List[Tuple[int, int]] = [
    (c, r) for r, row in enumerate(PIXEL_MAP) for c, ch in enumerate(row) if ch == "w"
]

# Encaixes dos canhões: centros das duas vagens (fração da largura a partir do
# centro). off_y = 0 → ficam no eixo horizontal da ampulheta.
MOUNT_OFFSET_X: float = 0.38  # ±0.38*w a partir do centro

# Validação de integridade (a geração pode falhar silenciosa se _HALF mudar).
assert len(PIXEL_MAP) == PIXEL_ROWS, f"PIXEL_MAP deve ter {PIXEL_ROWS} linhas"
assert all(len(row) == PIXEL_COLS for row in PIXEL_MAP), (
    f"Toda linha de PIXEL_MAP deve ter {PIXEL_COLS} colunas"
)
assert len(_HALF) == PIXEL_COLS, "_HALF deve ter PIXEL_COLS entradas"
assert CORE_CELLS and ENGINE_CELLS, "reator/conduítes não foram gerados"

# ── Canhão (barril) ──────────────────────────────────────────────────────────
# Sprite do canhão apontando para a DIREITA (+x). Pivô = centro da surface
# (col 8, row 3) = base do canhão; o barril estende-se até a boca 'M' (col 15).
# O render rotaciona em torno do centro para mirar e blita no encaixe da vagem.
CANNON_MAP: List[str] = [
    "......oooo.......",
    "......oSao.......",
    "......oSmllllllMo",
    "......oSammmmmmMo",
    "......oSmllllllMo",
    "......oSao.......",
    "......oooo.......",
]
CANNON_COLS = 17
CANNON_ROWS = 7
# Distância (em cells) do pivô (col 8) até a boca (col 15) — usada para a posição
# do muzzle flash e do disparo.
CANNON_BARREL_CELLS: int = 7

assert all(len(row) == CANNON_COLS for row in CANNON_MAP), "CANNON_MAP: 17 colunas"
assert len(CANNON_MAP) == CANNON_ROWS, "CANNON_MAP: 7 linhas"

# ── Builders cacheados ────────────────────────────────────────────────────────
_body_cache: Dict[int, pygame.Surface] = {}
_pod_cache: Dict[int, pygame.Surface] = {}
_cannon_cache: Dict[int, pygame.Surface] = {}


def _build_from_map(rows: List[str], cell: int) -> pygame.Surface:
    cols = len(rows[0])
    surface = pygame.Surface((cols * cell, len(rows) * cell), pygame.SRCALPHA)
    for row_i, row in enumerate(rows):
        for col_i, ch in enumerate(row):
            color = _ZONE_COLORS.get(ch)
            if color is None:
                continue
            surface.fill(color, (col_i * cell, row_i * cell, cell, cell))
    return surface


def build_tank_surface(cell: int) -> pygame.Surface:
    """Surface estática do chassi (ampulheta), cacheada por `cell`."""
    cached = _body_cache.get(cell)
    if cached is None:
        cached = _build_from_map(PIXEL_MAP, cell)
        _body_cache[cell] = cached
    return cached


def build_pod_surface(cell: int) -> pygame.Surface:
    """Surface de UMA vagem (metade da ampulheta), cacheada por `cell`. Mesmo
    tamanho do corpo (pivô = centro) para rotacionar em torno do eixo central."""
    cached = _pod_cache.get(cell)
    if cached is None:
        cached = _build_from_map(POD_MAP, cell)
        _pod_cache[cell] = cached
    return cached


def build_cannon_surface(cell: int) -> pygame.Surface:
    """Surface do barril do canhão (apontando +x), cacheada por `cell`."""
    cached = _cannon_cache.get(cell)
    if cached is None:
        cached = _build_from_map(CANNON_MAP, cell)
        _cannon_cache[cell] = cached
    return cached
