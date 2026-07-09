"""Dreadnought — pixel-map da **plataforma de bombardeio senciente**.

A silhueta comunica a mecânica ANTES do ataque, e o CENTRO comunica que há uma
inteligência coordenando tudo:

- **convés-plataforma pesado e SIMÉTRICO** (topo chanfrado igual dos dois lados,
  mastros gêmeos espelhados nas pontas, faixa de vents no ventre) — robusto e
  bem-acabado, sem elementos "tortos";
- ao centro, uma **cabine-cérebro** que abriga um **grande olho ciber** (o ponto
  focal — desenhado/animado pelo entity sobre o soquete blindado aqui gravado);
- **células de energia** flanqueando o olho (orbes que pulsam — vida contínua);
- pendurados no ventre, **QUATRO canhões** apontando para baixo (os 4 pontos de
  disparo). O TUBO+BOCA de cada canhão é uma surface separada (`build_barrel_
  surface`) para o entity animar o **recuo** por canhão; a culatra fica no convés.

Sóbrio (`space_palette`): chapa fosca, top-lit chapado, contorno escuro 1px
auto-gerado. Sem bloom — o "brilho" (olho, energia, bocas) é feito pelo entity com
discos/anéis finos. Dois builders cacheados por `cell` (§7): convés e canhão.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

from . import space_palette as pal

RGB = Tuple[int, int, int]

PIXEL_COLS = 34
PIXEL_ROWS = 17

# ── Quatro canhões (assinatura): x-centro de cada boca (fração da largura) ─────
CANNON_FRACS: Tuple[float, float, float, float] = (0.15, 0.385, 0.615, 0.85)
CANNON_CENTER_COLS: Tuple[int, ...] = tuple(int(round(f * PIXEL_COLS)) for f in CANNON_FRACS)

_TUBE_HALF = 1                        # tubo do canhão: 3 cols
_MUZZLE_HALF = 2                      # freio de boca: 5 cols
_BREECH_HALF = 2                      # culatra (raiz, fica no convés): 5 cols
_DECK_TOP, _DECK_BOT = 4, 8           # convés
_BREECH_TOP = 9                       # culatra logo abaixo do convés
BARREL_TOP_ROW = 11                   # onde começa a parte MÓVEL (tubo)
_TUBE_BOT = 14
MUZZLE_ROW = 15                       # boca (freio + alma escura)
MUZZLE_Y_FRAC: float = (MUZZLE_ROW + 0.5) / PIXEL_ROWS  # p/ o entity alinhar o tiro
RECOIL_TRAVEL_CELLS: float = 1.4      # curso do recuo (em cells) — o entity usa
# Larguras públicas p/ o entity pintar o AQUECIMENTO das bocas (célula a célula).
MUZZLE_HALF: int = _MUZZLE_HALF       # freio de boca: 2 → 5 cols
TUBE_HALF: int = _TUBE_HALF           # tubo: 1 → 3 cols

# ── Olho ciber central (o entity desenha; aqui só gravamos o soquete) ─────────
EYE_CX_FRAC: float = 0.5
EYE_CY_FRAC: float = (4.0 + 0.5) / PIXEL_ROWS
EYE_R_CELLS: float = 2.4

# ── Células de energia (o entity pulsa; aqui só gravamos os soquetes) ─────────
ENERGY_CELLS_FRAC: Tuple[Tuple[float, float], ...] = (
    (11.5 / PIXEL_COLS, (5.0 + 0.5) / PIXEL_ROWS),
    (22.5 / PIXEL_COLS, (5.0 + 0.5) / PIXEL_ROWS),
)

_ZONE_COLORS: Dict[str, RGB] = {
    "o": pal.OUTLINE,
    "s": pal.HULL_SHADOW,
    "d": pal.HULL_DARK,
    "b": pal.HULL_BASE,
    "l": pal.HULL_LIGHT,
    "H": pal.HULL_HILIGHT,
    "e": pal.VOID,             # soquetes/vents escuros
}


def _shade(dx: int) -> str:
    """Sombreamento cilíndrico esq→dir (luz superior/esquerda)."""
    return "l" if dx < 0 else "d" if dx > 0 else "b"


def _auto_outline(g: List[List[str]]) -> None:
    """Célula vazia 4-vizinha de corpo vira 'o' (contorno 1px)."""
    rows, cols = len(g), len(g[0])
    body = {
        (x, y) for y in range(rows) for x in range(cols) if g[y][x] not in (".", "o")
    }
    for y in range(rows):
        for x in range(cols):
            if g[y][x] != ".":
                continue
            if any((x + dx, y + dy) in body for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                g[y][x] = "o"


# ── Convés + cabine-cérebro + culatras (parte ESTÁTICA) ───────────────────────
def _build_deck_map() -> List[str]:
    g = [["." for _ in range(PIXEL_COLS)] for _ in range(PIXEL_ROWS)]

    def put(x: int, y: int, ch: str) -> None:
        if 0 <= x < PIXEL_COLS and 0 <= y < PIXEL_ROWS:
            g[y][x] = ch

    def put_sym(x: int, y: int, ch: str) -> None:
        """Grava em x e no espelho (33-x): mantém o sprite bilateralmente
        simétrico em torno do eixo central (col 16.5)."""
        put(x, y, ch)
        put(PIXEL_COLS - 1 - x, y, ch)

    # Convés (slab blindado SIMÉTRICO: topo chanfrado igual dos dois lados,
    # base cheia p/ cobrir as culatras externas). Sombreamento top-lit vertical.
    for y in range(_DECK_TOP, _DECK_BOT + 1):
        inset = max(0, 2 - (y - _DECK_TOP))   # chanfro só nas 2 linhas de cima
        if y == _DECK_TOP:
            ch = "H"
        elif y == _DECK_TOP + 1:
            ch = "l"
        elif y == _DECK_BOT:
            ch = "s"
        elif y == _DECK_BOT - 1:
            ch = "d"
        else:
            ch = "b"
        for x in range(1 + inset, (PIXEL_COLS - 2) - inset + 1):
            put(x, y, ch)

    # Faixa de placas/vents no ventre (simétrica).
    for x in range(3, PIXEL_COLS // 2, 3):
        put_sym(x, _DECK_BOT, "e")

    # CABINE-CÉREBRO central (bloco angular simétrico; abriga o olho).
    bridge = {1: (13, 20), 2: (12, 21), 3: (12, 21)}  # centros em 16.5
    for y, (x0, x1) in bridge.items():
        for x in range(x0, x1 + 1):
            put(x, y, "l" if y == 1 else "b")

    # MASTROS gêmeos (espelhados) nas duas pontas — silhueta robusta e simétrica.
    for mx in (6, 7):
        for y in range(1, 4):
            put_sym(mx, y, "d")
        put_sym(mx, 0, "l")

    # Culatras (raiz larga dos 4 canhões — ficam no convés, não recuam).
    for center in CANNON_CENTER_COLS:
        for y in range(_BREECH_TOP, BARREL_TOP_ROW):
            for dx in range(-_BREECH_HALF, _BREECH_HALF + 1):
                put(center + dx, y, _shade(dx))

    # SOQUETE do olho (recesso escuro no centro; o entity desenha o olho por cima).
    ecx = EYE_CX_FRAC * PIXEL_COLS - 0.5
    ecy = EYE_CY_FRAC * PIXEL_ROWS - 0.5
    for y in range(PIXEL_ROWS):
        for x in range(PIXEL_COLS):
            dist = ((x - ecx) ** 2 + (y - ecy) ** 2) ** 0.5
            if dist <= EYE_R_CELLS + 0.6:
                put(x, y, "o" if dist > EYE_R_CELLS - 0.4 else "e")

    # SOQUETES das células de energia (recesso escuro; o entity pulsa por cima).
    for fx, fy in ENERGY_CELLS_FRAC:
        cxx = int(round(fx * PIXEL_COLS - 0.5))
        cyy = int(round(fy * PIXEL_ROWS - 0.5))
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if abs(dx) + abs(dy) <= 1:
                    put(cxx + dx, cyy + dy, "e")

    _auto_outline(g)
    return ["".join(row) for row in g]


# ── Canhão MÓVEL (tubo + freio de boca) — surface própria p/ animar recuo ──────
# Padding de 1 col em cada lado + 1 row embaixo p/ o contorno caber (o topo fica
# flush, sem contorno, para casar sob a culatra do convés).
BARREL_CENTER_COL: int = _MUZZLE_HALF + 1


def _build_barrel_map() -> List[str]:
    w = (2 * _MUZZLE_HALF + 1) + 2                     # 7 cols (5 + margem)
    h = (MUZZLE_ROW - BARREL_TOP_ROW + 1) + 1          # tubo + boca + margem
    g = [["." for _ in range(w)] for _ in range(h)]
    cx = BARREL_CENTER_COL
    muzzle_local = MUZZLE_ROW - BARREL_TOP_ROW
    # Tubo.
    for y in range(0, (_TUBE_BOT - BARREL_TOP_ROW) + 1):
        for dx in range(-_TUBE_HALF, _TUBE_HALF + 1):
            g[y][cx + dx] = _shade(dx)
    # Freio de boca (flange largo) + alma escura.
    for dx in range(-_MUZZLE_HALF, _MUZZLE_HALF + 1):
        g[muzzle_local][cx + dx] = _shade(dx)
    g[muzzle_local][cx] = "e"
    _auto_outline(g)
    # Remove o contorno acima do tubo (linha 0) p/ casar flush sob a culatra.
    g[0] = [("." if ch == "o" else ch) for ch in g[0]]
    return ["".join(row) for row in g]


DECK_MAP: List[str] = _build_deck_map()
BARREL_MAP: List[str] = _build_barrel_map()

assert len(DECK_MAP) == PIXEL_ROWS and all(len(r) == PIXEL_COLS for r in DECK_MAP)

_deck_cache: Dict[int, pygame.Surface] = {}
_barrel_cache: Dict[int, pygame.Surface] = {}


def _render(rows: List[str], cell: int) -> pygame.Surface:
    surf = pygame.Surface((len(rows[0]) * cell, len(rows) * cell), pygame.SRCALPHA)
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            color = _ZONE_COLORS.get(ch)
            if color is not None:
                surf.fill(color, (c * cell, r * cell, cell, cell))
    return surf


def build_deck_surface(cell: int) -> pygame.Surface:
    """Parte estática (convés + cabine + culatras + mastros), cacheada por cell."""
    cached = _deck_cache.get(cell)
    if cached is None:
        cached = _render(DECK_MAP, cell)
        _deck_cache[cell] = cached
    return cached


def build_barrel_surface(cell: int) -> pygame.Surface:
    """Um canhão móvel (tubo + boca), cacheado por cell. O entity o blita nos 4
    canhões com um deslocamento de recuo (para cima) por instância."""
    cached = _barrel_cache.get(cell)
    if cached is None:
        cached = _render(BARREL_MAP, cell)
        _barrel_cache[cell] = cached
    return cached
