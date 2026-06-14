"""Metropolis Overlord Pixel Map — "Reator Triangular".

Silhueta: um grande TRIÂNGULO tecnológico flutuante (estrutura de contenção),
ápice no topo e base larga embaixo — presença imponente, reconhecível à distância,
como um reator central / inteligência urbana ancestral da Cidade Neon.

A carcaça externa (P) se fragmenta com o dano, revelando o frame interno escuro
(G). O contorno neon (E) PERSISTE, mantendo a silhueta triangular mesmo após o
descascamento. Os TRÊS núcleos energéticos (esferas com plasma vivo) NÃO moram
aqui — são desenhados proceduralmente pelo boss (`_draw_plasma_sphere`), pois
precisam animar (oscilar/girar/pulsar) e são o foco visual, acima da carcaça.

Direção: pixel art, formas simples e legíveis, silhueta triangular forte, neon de
alto contraste, poucos detalhes mecânicos.

Legenda:
  '.' Transparente
  'E' Edge — contorno neon (persiste; define a silhueta)
  'P' Plating — carcaça externa destrutível (fragmenta com o dano)
  'G' Gutter — frame interno escuro (revelado quando a placa cai)
"""

from typing import Dict, List, Tuple

RGB = Tuple[int, int, int]

PIXEL_COLS = 24
PIXEL_ROWS = 20


def _build_maps() -> Tuple[List[str], List[str]]:
    """Gera o triângulo (ápice no topo) preenchido, com contorno neon.

    Programático para garantir uma silhueta limpa e simétrica (formas simples,
    poucos detalhes). Externo = E (borda) + P (placa); interno = E (borda) + G.
    """
    cols, rows = PIXEL_COLS, PIXEL_ROWS
    apex = (cols - 1) / 2.0
    ext: List[List[str]] = [["."] * cols for _ in range(rows)]
    intr: List[List[str]] = [["."] * cols for _ in range(rows)]
    for r in range(rows):
        frac = r / (rows - 1)
        half = frac * (cols - 1) / 2.0
        left = round(apex - half)
        right = round(apex + half)
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

EDGE_GLOW: RGB = (180, 250, 255)  # brilho do contorno ao pulsar
