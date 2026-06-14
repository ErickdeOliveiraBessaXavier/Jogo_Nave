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
