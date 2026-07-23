"""Metropolis Overlord Pixel Map — "Reator Triangular".

Silhueta: um grande TRIÂNGULO tecnológico flutuante (estrutura de contenção),
ápice no topo e base larga embaixo — presença imponente, como um reator central /
inteligência urbana ancestral da Cidade Neon.

A carcaça externa (P) se fragmenta com o dano, revelando o frame interno escuro
(G). O contorno neon (E) PERSISTE, mantendo a silhueta triangular. Os TRÊS
núcleos energéticos (esferas com plasma vivo) NÃO moram aqui — são desenhados
proceduralmente por `draw_plasma_sphere` (precisam animar e são o foco visual).

Direção: pixel art, formas simples e legíveis, silhueta triangular FORTE e
simétrica, neon de alto contraste, poucos detalhes mecânicos.

Legenda:
  '.' Transparente
  'E' Edge — contorno neon (persiste; define a silhueta)
  'P' Plating — carcaça externa destrutível (fragmenta com o dano)
  'G' Gutter — frame interno escuro (revelado quando a placa cai)
"""

import math
from typing import Dict, List, Tuple

import pygame

RGB = Tuple[int, int, int]

# Ímpar → existe uma coluna central exata (12), garantindo ápice afiado de 1px e
# triângulo perfeitamente simétrico por construção.
PIXEL_COLS = 25
PIXEL_ROWS = 21


def _build_maps() -> Tuple[List[str], List[str]]:
    """Gera o triângulo simétrico (ápice no topo), preenchido + contorno neon.

    Simetria garantida: para cada linha, escolhemos uma meia-largura inteira `hw`
    e preenchemos de `center-hw` a `center+hw` — espelhado em torno da coluna
    central. Externo = E (borda) + P (placa); interno = E (borda) + G.
    """
    cols, rows = PIXEL_COLS, PIXEL_ROWS
    center = (cols - 1) // 2
    max_hw = center
    ext: List[List[str]] = [["."] * cols for _ in range(rows)]
    intr: List[List[str]] = [["."] * cols for _ in range(rows)]
    for r in range(rows):
        hw = round(r / (rows - 1) * max_hw)
        left, right = center - hw, center + hw
        for c in range(left, right + 1):
            is_edge = c == left or c == right or r == rows - 1
            ext[r][c] = "E" if is_edge else "P"
            intr[r][c] = "E" if is_edge else "G"
    return ["".join(row) for row in ext], ["".join(row) for row in intr]


PIXEL_MAP, PIXEL_MAP_INTERNAL = _build_maps()

# Paleta de alto contraste: carcaça fosca/discreta para os núcleos dominarem.
COLORS: Dict[str, RGB] = {
    "E": (0, 238, 255),  # contorno neon cyan (silhueta de alto contraste)
    "P": (58, 66, 92),   # plating azul-aço fosco (secundário)
    "G": (22, 24, 36),   # frame interno escuro
}

EDGE_GLOW: RGB = (180, 250, 255)  # brilho do contorno-escudo energizado (Fase 1)

# ── Núcleos de plasma ──────────────────────────────────────────────────────
# Gradientes (escuro → meio → brilho), neon de alto contraste, um por núcleo.
PLASMA_THEMES: Dict[str, Tuple[RGB, RGB, RGB]] = {
    "cyan": ((4, 26, 54), (0, 150, 205), (150, 255, 255)),
    "magenta": ((46, 4, 52), (205, 25, 165), (255, 165, 240)),
    "amber": ((54, 28, 0), (225, 120, 15), (255, 232, 150)),
}


def _grad3(stops: Tuple[RGB, RGB, RGB], v: float) -> RGB:
    """Interpola um gradiente de 3 paradas (dark → mid → bright) em v∈[0,1]."""
    if v <= 0.0:
        return stops[0]
    if v >= 1.0:
        return stops[2]
    if v < 0.5:
        t, a, b = v / 0.5, stops[0], stops[1]
    else:
        t, a, b = (v - 0.5) / 0.5, stops[1], stops[2]
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def draw_plasma_sphere(
    surface: pygame.Surface,
    cx: int,
    cy: int,
    radius: float,
    theme: str,
    phase: float,
    intensity: float,
    anim_time: float,
) -> None:
    """Núcleo de fluido energético VIVO (metaballs animadas), sem encapsulamento.

    Fluido renderizado em células chunky (pixel art), cor por um campo de
    metaballs que orbitam dentro do raio — sensação de plasma condensado em
    movimento. SEM halo de glow externo NEM aro de contenção (removidos a pedido):
    só a energia interna, limpa. Função pura de
    render (§3): animação só via `anim_time` + a `phase` fixa do núcleo. Reusada
    pelo boss e pelos segmentos.
    """
    grad = PLASMA_THEMES.get(theme, PLASMA_THEMES["cyan"])
    t = anim_time

    # Centros das metaballs orbitando dentro da esfera (fluido em movimento).
    blobs = []
    for k in range(3):
        ang = t * (0.6 + 0.25 * k) + phase + k * 2.1
        orbit = radius * 0.5 * (0.4 + 0.6 * abs(math.sin(t * 0.7 + phase + k * 1.3)))
        blobs.append((math.cos(ang) * orbit, math.sin(ang) * orbit))

    res = max(6, int(radius * 2 / 6))  # ~6px por célula
    cell = radius * 2 / res
    r2 = radius * radius
    base_x = cx - radius
    base_y = cy - radius
    for gy in range(res):
        ly = (gy + 0.5) / res * 2.0 * radius - radius
        for gx in range(res):
            lx = (gx + 0.5) / res * 2.0 * radius - radius
            if lx * lx + ly * ly > r2:
                continue
            field = 0.16
            for bx, by in blobs:
                d2 = (lx - bx) ** 2 + (ly - by) ** 2 + 30.0
                field += (r2 * 0.16) / d2
            v = max(0.0, min(1.0, field * intensity))
            pygame.draw.rect(
                surface,
                _grad3(grad, v),
                (int(base_x + gx * cell), int(base_y + gy * cell), int(cell + 1), int(cell + 1)),
            )

    # SEM aro de contenção (removido a pedido): núcleo limpo, só o plasma vivo —
    # o campo de metaballs já escurece nas bordas, dando vinheta orgânica sem anel.


# ─────────────────────────────────────────────────────────────────────────────
# Estrutura interna "viva" + borda neon — COMPARTILHADA pelo boss e pelos
# mini-Overlords (segmentos da Fase 3). Funções puras de `anim_time` (§3).
# ─────────────────────────────────────────────────────────────────────────────
INNER_A: RGB = (46, 38, 82)        # violeta-escuro (placa)
INNER_B: RGB = (28, 52, 86)        # azul-aço escuro (placa)
INNER_FLOW: RGB = (70, 165, 225)   # corrente ciano-elétrica
INNER_VEIN: RGB = (140, 110, 215)  # veia violeta luminosa
FRAME_A: RGB = (20, 22, 40)        # frame escuro (violeta)
FRAME_B: RGB = (28, 30, 52)        # frame escuro (azul)
SILHOUETTE: RGB = (40, 44, 58)     # silhueta cinza-azulada (intro)
EDGE_SILHOUETTE: RGB = (20, 150, 205)  # bordas azuis estáticas (intro)


def inner_cell_color(r: int, c: int, kind: str, anim_time: float) -> RGB:
    """Cor energética de UMA célula interna (placa `P` / frame `G`): respiração de
    cor + corrente diagonal + veias (só placas) + pulso. Determinístico (§3)."""
    t = anim_time
    sin = math.sin
    a, b = (INNER_A, INNER_B) if kind == "P" else (FRAME_A, FRAME_B)
    m = 0.5 + 0.5 * sin(t * 0.5 + (r + c) * 0.18)
    r0 = a[0] + (b[0] - a[0]) * m
    g0 = a[1] + (b[1] - a[1]) * m
    b0 = a[2] + (b[2] - a[2]) * m
    band = sin((r - c) * 0.5 - t * 2.0)
    if band > 0.5:
        gain = (band - 0.5) * 2.0 * (0.55 if kind == "P" else 0.3)
        fl = INNER_FLOW
        r0 += (fl[0] - r0) * gain
        g0 += (fl[1] - g0) * gain
        b0 += (fl[2] - b0) * gain
    if kind == "P":
        vein = sin((r * 1.3 + c * 0.7) - t * 1.2)
        if vein > 0.86:
            gv = (vein - 0.86) * 7.0 * 0.5
            vc = INNER_VEIN
            r0 += (vc[0] - r0) * gv
            g0 += (vc[1] - g0) * gv
            b0 += (vc[2] - b0) * gv
    pulse = 0.9 + 0.1 * sin(t * 3.0 + r * 0.7 - c * 0.4)
    return (min(255, int(r0 * pulse)), min(255, int(g0 * pulse)), min(255, int(b0 * pulse)))


def shield_live_color(th: float, anim_time: float) -> RGB:
    """Cor de uma célula de BORDA (`E`) com a corrente energética CIRCULANDO pelo
    perímetro (posição `th`∈[0,1]) + nós branco-quentes viajando. Determinístico."""
    t = anim_time
    for k in range(2):
        node = (t * 0.16 + k * 0.5) % 1.0
        d = abs(((th - node + 0.5) % 1.0) - 0.5)
        if d < 0.045:
            f = 1.0 - d / 0.045
            hot, g = (235, 252, 255), EDGE_GLOW
            return (int(g[0] + (hot[0] - g[0]) * f), int(g[1] + (hot[1] - g[1]) * f), int(g[2] + (hot[2] - g[2]) * f))
    wave = 0.5 + 0.5 * math.sin(th * (2.0 * math.pi * 3.0) - t * 2.4)
    wave *= 0.85 + 0.15 * math.sin(t * 1.3)
    neon, glow = COLORS["E"], EDGE_GLOW
    return (int(neon[0] + (glow[0] - neon[0]) * wave), int(neon[1] + (glow[1] - neon[1]) * wave), int(neon[2] + (glow[2] - neon[2]) * wave))


def _build_edge_threshold() -> Dict[Tuple[int, int], float]:
    """Posição de perímetro (0→1) de cada célula `E`, ordenada por ângulo em torno
    do centro — base da corrente que circula a borda. Idêntica em qualquer escala."""
    cx, cy = PIXEL_COLS / 2.0, PIXEL_ROWS / 2.0
    cells = [
        (r, c)
        for r, row in enumerate(PIXEL_MAP_INTERNAL)
        for c, ch in enumerate(row)
        if ch == "E"
    ]
    cells.sort(key=lambda rc: math.atan2(rc[0] - cy, rc[1] - cx))
    n = max(1, len(cells))
    return {rc: i / n for i, rc in enumerate(cells)}


EDGE_THRESHOLD: Dict[Tuple[int, int], float] = _build_edge_threshold()


def draw_mini_overlord(
    surface: pygame.Surface,
    cx: float,
    cy: float,
    scale: float,
    theme: str,
    anim_time: float,
    hit: bool = False,
    core_phase: float = 0.0,
) -> None:
    """Desenha um MINI Metropolis Overlord centrado em (cx,cy): a MESMA silhueta
    pixel-art do boss (placas `P` energizadas + bordas `E` com corrente neon),
    escalada, com UM único núcleo de plasma no centro. `draw` puro (§3)."""
    cell = int(scale + 1)
    grid_w = PIXEL_COLS * scale
    grid_h = PIXEL_ROWS * scale
    x = cx - grid_w / 2.0
    y = cy - grid_h / 2.0
    white = (255, 255, 255)
    for r, row in enumerate(PIXEL_MAP):  # PIXEL_MAP = triângulo cheio (P + bordas E)
        py = int(y + r * scale)
        for c, ch in enumerate(row):
            if ch == ".":
                continue
            if ch == "E":
                color = white if hit else shield_live_color(EDGE_THRESHOLD.get((r, c), 0.0), anim_time)
            else:  # "P"
                color = inner_cell_color(r, c, "P", anim_time)
            pygame.draw.rect(surface, color, (int(x + c * scale), py, cell, cell))
    # UM núcleo de plasma no centro do triângulo (foco do fragmento).
    core_cx = int(x + 0.5 * grid_w)
    core_cy = int(y + 0.60 * grid_h)
    radius = 0.17 * grid_w
    intensity = 1.0 + 0.15 * (0.5 + 0.5 * math.sin(anim_time * 4.0))
    draw_plasma_sphere(surface, core_cx, core_cy, radius, theme, core_phase, intensity, anim_time)
