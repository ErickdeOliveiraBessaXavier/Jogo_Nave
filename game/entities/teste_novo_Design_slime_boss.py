"""
Boss Gosma — Pixel Art Renderer (Layered)

Corpo e olhos são camadas independentes com lerp, glow e animações separadas.
Estrutura análoga ao CloudArchmageBoss: cada parte tem posição própria rastreada
por lerp, permitindo offset, lag e animações ortogonais sem acoplamento.

Camadas (ordem de blit):
  1. DripsSystem  — gosma caindo, desenhada antes do corpo
  2. BodyLayer    — pixel map completo sem os olhos (transparente nos slots de olho)
  3. EyeLayer     — apenas os pixels de olho, com lerp offset, glow e piscar
"""

from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass

import pygame

# ---------------------------------------------------------------------------
# Dados do sprite original (96×40 px, 16 cores)
# ---------------------------------------------------------------------------

PALETTE = [
    (72, 17, 86),    # 0  — roxo médio
    (83, 27, 96),    # 1  — roxo claro
    (56, 15, 68),    # 2  — roxo escuro
    (35, 7, 44),     # 3  — roxo muito escuro
    (27, 7, 33),     # 4  — roxo quase preto
    (148, 89, 158),  # 5  — lilás claro (olhos)
    (54, 11, 66),    # 6  — roxo médio-escuro
    (44, 9, 54),     # 7  — roxo escuro médio
    (11, 2, 14),     # 8  — quase preto
    (19, 4, 25),     # 9  — preto arroxeado
    (13, 3, 16),     # 10 — preto arroxeado escuro
    (28, 4, 36),     # 11 — roxo muito escuro 2
    (4, 1, 5),       # 12 — preto quase total
    (0, 0, 1),       # 13 — preto
    (0, 0, 0),       # 14 — preto puro
    (2, 0, 3),       # 15 — preto quase total 2
]

PIXEL_MAP = [
    [0, 1, 2, 3, 0, 1, 2, 0, 0, 4, 1, 0, 0, 2, 2, 1, 1, 2, 5, 1, 0, 6, 4, 2, 2, 7, 8, 3, 1, 0, 0, 6, 0, 1, 7, 8, 9, 9, 10, 9, 0, 1, 4, 6, 1, 1, 1, 3, 2, 9, 0, 1, 1, 1, 1, 1, 6, 0, 1, 1, 1, 1, 2, 3, 5, 5, 2, 0, 4, 3, 0, 0, 11, 7, 6, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0, 4, 3, 0, 1, 0, 1, 0, 7, 2, 1, 1],
    [2, 7, 7, 1, 1, 0, 6, 2, 0, 0, 1, 1, 0, 7, 0, 1, 0, 0, 1, 5, 1, 6, 6, 9, 11, 0, 7, 6, 0, 0, 0, 3, 5, 1, 9, 0, 1, 1, 1, 1, 1, 2, 7, 1, 3, 4, 0, 7, 11, 9, 11, 7, 2, 2, 1, 1, 1, 1, 0, 0, 1, 1, 0, 3, 0, 5, 5, 0, 7, 12, 9, 8, 11, 2, 0, 1, 0, 1, 1, 0, 1, 1, 1, 0, 2, 1, 6, 2, 1, 0, 1, 1, 1, 7, 7, 0],
    [4, 7, 0, 1, 6, 2, 1, 7, 1, 1, 1, 0, 1, 7, 0, 1, 1, 0, 0, 6, 0, 2, 2, 7, 9, 8, 11, 7, 2, 7, 3, 4, 2, 11, 1, 1, 1, 5, 1, 0, 1, 1, 1, 1, 1, 0, 13, 8, 4, 7, 3, 4, 10, 8, 10, 0, 1, 2, 5, 1, 6, 1, 1, 7, 3, 2, 1, 2, 6, 4, 11, 8, 12, 4, 0, 0, 1, 1, 5, 5, 0, 1, 1, 1, 1, 5, 1, 11, 5, 5, 0, 0, 1, 0, 7, 11],
    [3, 0, 2, 6, 1, 5, 5, 0, 1, 1, 1, 6, 4, 1, 1, 1, 0, 0, 0, 1, 0, 5, 0, 6, 7, 12, 10, 7, 0, 5, 0, 14, 4, 1, 1, 1, 5, 5, 1, 7, 1, 1, 1, 11, 4, 4, 3, 1, 2, 0, 1, 7, 4, 12, 10, 8, 7, 6, 5, 5, 1, 1, 1, 1, 11, 3, 0, 0, 0, 3, 6, 0, 4, 14, 6, 1, 1, 0, 1, 5, 5, 1, 1, 1, 1, 1, 1, 0, 0, 5, 5, 0, 0, 0, 0, 7],
    [4, 7, 3, 7, 5, 1, 6, 0, 0, 1, 1, 3, 11, 1, 1, 1, 5, 5, 0, 1, 7, 2, 2, 6, 8, 3, 7, 3, 2, 1, 2, 3, 1, 1, 0, 1, 5, 1, 3, 1, 1, 0, 9, 9, 12, 12, 7, 10, 12, 12, 9, 12, 12, 11, 2, 7, 12, 11, 6, 1, 5, 1, 0, 1, 6, 10, 0, 0, 0, 6, 7, 3, 2, 9, 4, 3, 1, 1, 1, 0, 1, 1, 6, 1, 0, 1, 0, 0, 7, 0, 0, 0, 0, 7, 7, 11],
    [0, 0, 7, 2, 6, 0, 6, 0, 0, 0, 0, 1, 1, 1, 1, 5, 5, 1, 1, 0, 6, 2, 6, 11, 9, 3, 11, 7, 6, 6, 7, 9, 2, 6, 0, 2, 7, 7, 0, 7, 8, 8, 3, 7, 8, 10, 4, 15, 15, 12, 12, 12, 12, 12, 15, 10, 12, 10, 2, 6, 2, 1, 0, 0, 1, 2, 8, 6, 0, 0, 0, 8, 3, 11, 4, 2, 1, 2, 1, 1, 1, 1, 3, 9, 3, 1, 1, 0, 3, 7, 0, 0, 0, 6, 0, 0],
    [1, 2, 2, 2, 2, 1, 3, 9, 6, 0, 0, 1, 6, 1, 1, 1, 0, 0, 0, 2, 2, 11, 11, 4, 4, 11, 6, 7, 6, 2, 7, 15, 10, 6, 2, 0, 0, 0, 0, 9, 3, 3, 9, 15, 12, 12, 15, 12, 12, 12, 12, 12, 12, 10, 3, 3, 3, 9, 10, 2, 3, 7, 6, 9, 1, 1, 7, 4, 0, 0, 6, 7, 11, 9, 4, 0, 0, 0, 9, 7, 7, 2, 1, 6, 10, 1, 1, 1, 1, 6, 7, 11, 2, 6, 2, 1],
    [2, 6, 0, 2, 0, 0, 9, 10, 0, 0, 5, 1, 10, 2, 1, 0, 1, 2, 7, 7, 6, 8, 3, 9, 4, 11, 3, 11, 7, 4, 6, 7, 3, 7, 1, 2, 10, 9, 9, 11, 11, 11, 7, 7, 11, 10, 15, 12, 12, 15, 12, 4, 3, 7, 3, 11, 11, 4, 9, 4, 15, 4, 2, 3, 1, 1, 0, 2, 3, 7, 2, 7, 3, 4, 3, 1, 1, 7, 7, 2, 1, 1, 0, 0, 7, 2, 1, 1, 0, 0, 9, 4, 6, 6, 2, 2],
    [7, 7, 7, 6, 0, 7, 9, 6, 0, 1, 5, 0, 9, 7, 0, 1, 1, 3, 10, 1, 0, 3, 15, 9, 4, 9, 12, 11, 7, 9, 7, 2, 7, 11, 0, 12, 9, 2, 1, 5, 5, 5, 1, 3, 7, 3, 12, 15, 15, 15, 4, 7, 3, 2, 5, 5, 5, 1, 2, 3, 15, 3, 2, 4, 0, 0, 0, 7, 2, 2, 3, 7, 10, 9, 11, 1, 3, 3, 0, 1, 1, 1, 7, 7, 2, 7, 2, 6, 0, 2, 6, 6, 4, 3, 6, 7],
    [7, 2, 3, 12, 11, 8, 7, 2, 2, 2, 6, 3, 0, 3, 2, 1, 1, 1, 7, 2, 3, 7, 8, 10, 3, 4, 8, 11, 6, 7, 10, 2, 9, 10, 6, 14, 3, 5, 5, 5, 5, 5, 5, 5, 9, 3, 10, 14, 15, 8, 3, 9, 1, 5, 5, 5, 5, 5, 5, 0, 14, 8, 2, 8, 4, 0, 2, 7, 2, 6, 11, 7, 9, 10, 10, 9, 3, 0, 1, 1, 1, 2, 4, 0, 0, 8, 11, 6, 2, 0, 6, 2, 2, 4, 12, 9],
    [7, 0, 11, 1, 5, 3, 0, 10, 6, 0, 4, 10, 0, 7, 4, 1, 1, 1, 1, 6, 10, 11, 3, 10, 7, 11, 11, 11, 3, 0, 10, 6, 3, 9, 9, 10, 15, 5, 5, 5, 5, 5, 5, 5, 1, 8, 4, 12, 15, 9, 10, 2, 5, 5, 5, 5, 5, 5, 5, 9, 12, 8, 6, 3, 12, 4, 13, 4, 9, 9, 2, 3, 10, 8, 14, 4, 2, 2, 0, 0, 7, 3, 2, 0, 7, 2, 6, 9, 10, 2, 0, 6, 2, 7, 1, 1],
    [9, 0, 11, 1, 2, 1, 7, 14, 11, 11, 8, 6, 7, 7, 6, 9, 7, 0, 0, 0, 6, 9, 6, 8, 4, 7, 9, 4, 4, 0, 4, 9, 6, 6, 4, 8, 9, 1, 5, 5, 5, 5, 5, 5, 5, 8, 3, 12, 13, 3, 15, 5, 5, 5, 5, 5, 5, 5, 5, 9, 10, 9, 7, 7, 14, 4, 5, 6, 14, 8, 6, 11, 11, 8, 12, 4, 6, 3, 3, 3, 7, 2, 0, 6, 2, 2, 1, 11, 3, 10, 1, 6, 0, 1, 0, 3],
    [11, 1, 4, 7, 2, 1, 6, 9, 11, 8, 6, 2, 1, 4, 0, 6, 3, 3, 3, 7, 2, 9, 6, 2, 12, 7, 7, 3, 14, 7, 2, 8, 2, 6, 9, 13, 11, 6, 5, 5, 5, 1, 5, 5, 5, 3, 9, 8, 12, 3, 10, 5, 5, 5, 1, 5, 5, 5, 1, 11, 12, 12, 3, 6, 9, 8, 5, 5, 1, 15, 9, 7, 6, 8, 15, 9, 6, 2, 0, 2, 2, 6, 2, 1, 2, 8, 10, 10, 7, 11, 1, 1, 3, 3, 2, 2],
    [3, 1, 2, 6, 2, 1, 1, 6, 3, 2, 6, 11, 3, 6, 2, 6, 7, 2, 0, 0, 6, 12, 9, 5, 0, 12, 3, 11, 8, 4, 7, 11, 2, 3, 9, 12, 10, 7, 5, 5, 5, 5, 5, 5, 5, 3, 10, 10, 12, 4, 10, 5, 5, 5, 5, 5, 5, 5, 7, 9, 15, 8, 11, 7, 3, 12, 14, 7, 4, 3, 6, 3, 9, 8, 10, 8, 7, 7, 0, 0, 0, 3, 5, 5, 9, 0, 1, 1, 1, 1, 1, 2, 3, 0, 4, 10],
    [4, 1, 1, 0, 7, 0, 0, 6, 6, 1, 6, 9, 6, 0, 2, 1, 1, 3, 0, 6, 7, 2, 9, 2, 5, 9, 9, 10, 6, 11, 14, 4, 1, 2, 11, 4, 13, 4, 7, 5, 5, 5, 5, 5, 5, 1, 12, 12, 12, 12, 2, 5, 5, 5, 5, 5, 5, 2, 11, 14, 9, 4, 3, 0, 2, 7, 10, 5, 2, 12, 7, 7, 12, 9, 7, 8, 9, 3, 0, 6, 7, 4, 2, 3, 1, 1, 1, 5, 5, 0, 1, 1, 1, 1, 1, 6],
    [10, 4, 1, 0, 1, 4, 2, 1, 7, 2, 7, 1, 0, 7, 7, 0, 1, 6, 0, 6, 2, 1, 6, 4, 3, 3, 6, 9, 2, 5, 1, 9, 2, 0, 4, 8, 8, 2, 6, 3, 2, 5, 5, 1, 7, 2, 8, 15, 12, 15, 7, 7, 2, 1, 5, 1, 7, 7, 2, 10, 12, 12, 6, 7, 6, 2, 13, 5, 5, 2, 11, 7, 7, 11, 9, 11, 4, 7, 0, 5, 1, 14, 9, 1, 1, 1, 5, 5, 1, 3, 1, 1, 1, 7, 10, 4],
    [1, 3, 4, 6, 1, 7, 3, 1, 2, 3, 6, 0, 1, 1, 6, 7, 0, 0, 7, 0, 4, 2, 7, 11, 10, 3, 7, 11, 2, 1, 0, 7, 7, 1, 1, 0, 7, 1, 1, 3, 7, 3, 11, 10, 13, 14, 12, 12, 15, 12, 14, 14, 8, 9, 11, 3, 3, 1, 5, 3, 2, 2, 1, 3, 2, 1, 3, 11, 6, 2, 7, 10, 10, 14, 9, 2, 7, 7, 0, 1, 2, 3, 0, 1, 0, 1, 1, 1, 3, 0, 1, 1, 1, 0, 8, 15],
    [1, 1, 0, 0, 7, 5, 5, 1, 1, 1, 2, 2, 0, 1, 1, 11, 11, 0, 3, 6, 7, 9, 2, 5, 4, 7, 3, 2, 2, 0, 6, 9, 1, 1, 1, 0, 0, 3, 2, 11, 10, 8, 8, 8, 10, 10, 12, 12, 13, 12, 15, 12, 8, 8, 8, 8, 4, 7, 4, 6, 0, 0, 2, 1, 1, 1, 7, 4, 6, 7, 9, 3, 2, 12, 6, 2, 7, 2, 2, 0, 6, 4, 2, 6, 0, 2, 7, 3, 0, 7, 8, 7, 1, 1, 0, 6],
    [2, 1, 2, 0, 9, 5, 5, 1, 2, 0, 12, 0, 2, 2, 2, 0, 11, 2, 0, 7, 2, 8, 5, 5, 11, 7, 0, 2, 2, 0, 7, 12, 11, 2, 7, 1, 1, 2, 3, 3, 11, 9, 12, 3, 8, 7, 9, 8, 8, 4, 4, 10, 3, 12, 9, 9, 3, 3, 2, 0, 1, 3, 11, 6, 1, 2, 3, 9, 6, 7, 7, 9, 0, 4, 7, 7, 0, 0, 0, 0, 7, 15, 10, 6, 2, 0, 2, 0, 6, 9, 2, 2, 0, 0, 2, 2],
    [7, 5, 5, 1, 1, 3, 3, 7, 0, 7, 10, 4, 2, 2, 7, 2, 3, 3, 6, 2, 7, 9, 1, 2, 11, 7, 6, 7, 6, 11, 6, 2, 7, 2, 1, 3, 0, 2, 0, 7, 3, 7, 9, 3, 10, 6, 7, 11, 3, 10, 6, 9, 9, 9, 3, 11, 7, 0, 2, 0, 3, 6, 0, 7, 4, 3, 11, 3, 3, 7, 7, 10, 13, 8, 3, 7, 6, 7, 6, 11, 7, 7, 3, 7, 1, 2, 6, 0, 4, 7, 6, 6, 6, 2, 6, 3],
    [11, 0, 1, 0, 1, 1, 0, 6, 7, 0, 3, 7, 8, 7, 2, 2, 3, 6, 6, 11, 7, 4, 8, 4, 7, 3, 8, 7, 0, 9, 7, 0, 7, 3, 0, 10, 8, 8, 0, 3, 6, 9, 7, 11, 6, 3, 7, 3, 11, 7, 6, 12, 10, 7, 9, 3, 7, 0, 4, 8, 9, 2, 3, 6, 0, 2, 6, 3, 0, 9, 11, 11, 8, 10, 3, 9, 8, 3, 2, 9, 3, 2, 7, 3, 0, 8, 4, 8, 9, 7, 3, 12, 6, 3, 10, 9],
    [8, 3, 7, 0, 0, 2, 12, 9, 5, 1, 10, 7, 4, 9, 7, 9, 3, 3, 11, 6, 3, 9, 4, 11, 6, 7, 10, 7, 2, 6, 9, 2, 10, 10, 6, 3, 12, 4, 9, 8, 7, 10, 0, 3, 6, 10, 10, 2, 6, 9, 8, 12, 10, 0, 10, 6, 3, 10, 3, 1, 2, 9, 7, 8, 7, 3, 9, 3, 11, 4, 7, 10, 8, 10, 3, 11, 8, 3, 6, 6, 9, 2, 9, 10, 2, 7, 12, 9, 2, 1, 0, 9, 12, 12, 8, 10],
    [1, 2, 12, 3, 2, 11, 9, 7, 7, 10, 9, 7, 3, 10, 12, 4, 12, 14, 9, 6, 4, 9, 7, 9, 2, 7, 7, 7, 7, 0, 8, 2, 6, 11, 2, 6, 2, 1, 1, 3, 14, 10, 0, 4, 9, 8, 12, 8, 15, 14, 3, 2, 9, 0, 3, 3, 8, 11, 7, 2, 4, 3, 2, 11, 12, 9, 4, 13, 15, 3, 11, 10, 10, 10, 3, 11, 3, 3, 3, 0, 8, 6, 6, 11, 0, 0, 0, 1, 0, 2, 7, 7, 15, 1, 5, 0],
    [2, 6, 3, 8, 4, 10, 9, 8, 15, 8, 9, 7, 3, 11, 12, 5, 1, 10, 8, 9, 7, 11, 8, 12, 7, 2, 11, 3, 4, 0, 4, 11, 0, 11, 7, 11, 2, 1, 1, 1, 9, 12, 2, 9, 14, 0, 1, 12, 13, 3, 5, 5, 10, 2, 4, 9, 10, 9, 12, 8, 8, 7, 6, 6, 12, 1, 5, 7, 12, 9, 9, 3, 8, 13, 11, 7, 9, 4, 9, 2, 4, 4, 0, 3, 7, 7, 0, 1, 1, 1, 9, 7, 10, 3, 5, 5],
    [4, 3, 8, 14, 8, 9, 1, 4, 10, 10, 3, 8, 11, 3, 14, 7, 1, 2, 9, 12, 3, 3, 12, 10, 8, 0, 7, 9, 7, 3, 2, 9, 6, 2, 9, 7, 3, 3, 2, 2, 11, 14, 8, 9, 12, 4, 1, 9, 13, 7, 0, 12, 4, 10, 12, 8, 3, 1, 8, 10, 11, 11, 10, 6, 9, 8, 1, 1, 4, 12, 10, 11, 10, 12, 12, 7, 11, 9, 7, 9, 6, 9, 6, 0, 9, 7, 3, 2, 0, 0, 7, 14, 9, 4, 10, 4],
    [8, 15, 12, 12, 9, 6, 2, 9, 3, 3, 3, 3, 11, 8, 10, 15, 14, 10, 4, 8, 10, 10, 12, 10, 9, 10, 7, 11, 5, 0, 4, 11, 7, 3, 10, 3, 3, 3, 3, 9, 12, 10, 12, 9, 15, 13, 14, 13, 15, 14, 14, 12, 12, 8, 12, 4, 2, 4, 4, 7, 7, 7, 7, 9, 8, 8, 15, 12, 4, 10, 8, 8, 12, 12, 8, 8, 11, 4, 5, 2, 9, 4, 3, 3, 8, 11, 3, 11, 11, 10, 12, 9, 15, 9, 9, 12],
    [9, 9, 4, 10, 10, 12, 8, 11, 3, 9, 10, 3, 4, 5, 1, 12, 3, 10, 9, 4, 14, 7, 12, 12, 9, 9, 0, 11, 4, 2, 8, 8, 4, 12, 7, 9, 7, 11, 9, 14, 14, 9, 9, 9, 8, 10, 10, 12, 14, 8, 12, 10, 8, 10, 8, 8, 12, 10, 11, 3, 10, 11, 11, 2, 5, 4, 10, 11, 12, 11, 15, 9, 9, 15, 12, 10, 6, 9, 4, 7, 12, 8, 4, 12, 11, 10, 3, 4, 10, 14, 14, 4, 9, 4, 10, 9],
    [9, 9, 8, 9, 9, 4, 11, 11, 4, 9, 9, 13, 2, 1, 9, 12, 9, 3, 10, 9, 8, 3, 9, 14, 9, 0, 7, 12, 15, 12, 11, 9, 4, 4, 2, 11, 9, 4, 10, 3, 11, 15, 9, 10, 12, 10, 10, 8, 8, 10, 10, 10, 10, 12, 9, 10, 11, 4, 11, 9, 4, 10, 12, 1, 1, 13, 8, 11, 9, 10, 8, 8, 4, 14, 12, 7, 11, 12, 13, 15, 9, 8, 9, 9, 7, 9, 8, 9, 8, 4, 4, 15, 9, 9, 12, 9],
    [9, 7, 10, 9, 10, 3, 9, 10, 14, 11, 7, 11, 14, 14, 9, 3, 8, 7, 8, 12, 10, 7, 9, 13, 0, 6, 8, 4, 10, 10, 4, 3, 4, 3, 6, 2, 0, 9, 2, 0, 0, 8, 4, 9, 8, 9, 9, 12, 11, 9, 9, 10, 11, 12, 9, 10, 3, 10, 8, 12, 3, 7, 9, 14, 14, 11, 9, 9, 3, 14, 8, 10, 4, 15, 6, 3, 12, 9, 10, 8, 9, 4, 9, 4, 3, 3, 7, 8, 11, 6, 6, 8, 9, 4, 8, 9],
    [4, 7, 11, 12, 12, 4, 10, 9, 8, 10, 11, 2, 9, 8, 9, 12, 14, 7, 4, 14, 9, 3, 15, 4, 0, 12, 9, 8, 15, 8, 2, 3, 9, 3, 12, 3, 0, 3, 1, 0, 3, 10, 8, 12, 12, 11, 3, 8, 8, 8, 11, 9, 3, 8, 14, 10, 10, 10, 8, 9, 10, 7, 7, 12, 8, 8, 14, 8, 3, 13, 12, 9, 10, 9, 6, 12, 10, 8, 15, 8, 7, 4, 8, 4, 12, 9, 7, 10, 0, 7, 9, 8, 8, 12, 12, 11],
    [10, 6, 11, 10, 6, 11, 3, 9, 12, 10, 10, 2, 7, 13, 14, 9, 10, 0, 9, 13, 3, 4, 14, 4, 6, 8, 12, 14, 13, 3, 2, 15, 8, 10, 11, 10, 8, 0, 1, 2, 9, 4, 15, 12, 9, 3, 3, 9, 4, 9, 8, 9, 7, 8, 9, 3, 9, 3, 8, 8, 8, 9, 2, 10, 14, 15, 10, 10, 3, 14, 8, 9, 14, 9, 3, 12, 12, 15, 15, 3, 7, 15, 12, 8, 9, 8, 12, 7, 1, 3, 8, 9, 13, 15, 9, 11],
    [3, 4, 9, 3, 10, 12, 3, 9, 14, 10, 10, 6, 7, 13, 15, 10, 4, 2, 15, 14, 10, 4, 15, 12, 3, 10, 12, 13, 13, 7, 9, 10, 14, 12, 12, 12, 14, 0, 1, 7, 9, 8, 12, 12, 9, 10, 8, 9, 9, 9, 4, 11, 10, 4, 9, 12, 8, 3, 12, 14, 10, 9, 6, 10, 14, 12, 8, 11, 4, 14, 15, 9, 12, 12, 11, 12, 15, 15, 12, 3, 10, 8, 13, 12, 12, 12, 14, 7, 1, 11, 10, 12, 12, 12, 9, 10],
    [9, 9, 9, 12, 8, 15, 9, 9, 14, 8, 10, 6, 10, 14, 12, 8, 2, 3, 14, 15, 14, 12, 12, 14, 4, 4, 12, 15, 13, 4, 9, 12, 13, 12, 12, 14, 13, 4, 1, 7, 9, 10, 12, 12, 12, 10, 15, 10, 12, 12, 12, 9, 10, 10, 15, 8, 15, 4, 12, 15, 8, 4, 3, 13, 14, 12, 8, 3, 12, 14, 14, 14, 12, 14, 9, 10, 12, 15, 12, 4, 10, 12, 14, 12, 12, 13, 13, 9, 1, 3, 8, 10, 12, 12, 12, 9],
    [10, 8, 12, 12, 9, 14, 4, 10, 14, 8, 11, 3, 14, 14, 13, 8, 7, 3, 14, 13, 13, 14, 14, 14, 10, 11, 12, 14, 14, 8, 3, 10, 15, 12, 8, 14, 14, 14, 0, 0, 8, 8, 15, 12, 12, 4, 8, 8, 8, 12, 12, 8, 12, 14, 8, 12, 15, 4, 13, 15, 8, 11, 9, 14, 14, 12, 8, 3, 8, 14, 14, 14, 14, 14, 10, 9, 15, 14, 14, 8, 4, 8, 15, 12, 8, 14, 14, 13, 2, 2, 12, 8, 15, 8, 12, 4],
    [9, 8, 14, 15, 8, 14, 8, 12, 14, 8, 3, 7, 14, 13, 14, 8, 9, 2, 10, 14, 14, 14, 13, 14, 10, 3, 12, 14, 13, 14, 9, 4, 15, 12, 12, 14, 13, 13, 4, 2, 10, 8, 14, 12, 12, 9, 12, 14, 12, 13, 15, 9, 13, 14, 8, 12, 13, 10, 14, 15, 8, 3, 9, 14, 13, 13, 10, 4, 11, 15, 13, 14, 13, 14, 10, 4, 15, 14, 13, 14, 9, 9, 13, 12, 12, 14, 13, 14, 4, 6, 10, 12, 14, 8, 12, 9],
    [8, 12, 14, 13, 15, 14, 14, 14, 14, 12, 10, 7, 9, 14, 15, 15, 12, 4, 7, 12, 14, 14, 13, 12, 11, 9, 14, 14, 13, 14, 8, 4, 14, 14, 14, 14, 13, 14, 4, 7, 10, 12, 14, 13, 13, 10, 12, 13, 12, 15, 14, 8, 15, 14, 15, 15, 14, 14, 14, 13, 8, 9, 3, 15, 14, 15, 12, 12, 4, 11, 14, 13, 14, 12, 4, 10, 14, 14, 14, 14, 10, 9, 14, 14, 14, 14, 13, 14, 4, 7, 10, 12, 14, 15, 14, 2],
    [10, 8, 14, 15, 12, 14, 14, 14, 14, 13, 12, 4, 7, 3, 10, 14, 13, 14, 9, 9, 14, 13, 14, 12, 8, 14, 14, 14, 14, 14, 10, 10, 14, 13, 13, 12, 14, 8, 7, 9, 10, 14, 14, 14, 14, 8, 15, 13, 13, 14, 14, 10, 15, 14, 12, 12, 14, 14, 14, 14, 15, 12, 4, 3, 9, 12, 14, 13, 12, 11, 12, 14, 14, 12, 8, 14, 14, 14, 14, 14, 10, 8, 14, 14, 13, 15, 14, 8, 6, 9, 10, 14, 14, 13, 14, 2],
    [9, 10, 14, 15, 12, 14, 14, 14, 14, 14, 14, 12, 8, 10, 15, 14, 14, 14, 15, 12, 14, 14, 14, 14, 14, 13, 14, 14, 14, 14, 14, 14, 14, 14, 13, 10, 11, 6, 4, 8, 14, 14, 14, 14, 14, 9, 12, 14, 14, 14, 13, 9, 12, 14, 8, 12, 14, 14, 14, 14, 14, 13, 12, 8, 12, 14, 14, 14, 14, 12, 15, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 13, 10, 11, 6, 11, 10, 14, 14, 14, 14, 14, 9],
    [14, 13, 14, 14, 13, 14, 14, 14, 14, 14, 13, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 10, 10, 15, 15, 14, 14, 14, 14, 14, 10, 12, 14, 14, 14, 14, 13, 13, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 13, 8, 10, 15, 15, 14, 14, 14, 14, 14, 9],
    [14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 13, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14],
]

MAP_W = 96
MAP_H = 40

EYE_COLOR_IDX = 5
EYE_GLOW_COLOR: tuple[int, int, int] = (200, 140, 220)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PIXEL_SIZE = 12
WIN_W = MAP_W * PIXEL_SIZE
WIN_H = MAP_H * PIXEL_SIZE
FPS = 60
TITLE = "Boss — Gosma (Layered)"
BG_COLOR = (0, 0, 0)

# Body animation
_PULSE_FREQ = 1.4
_PULSE_MIN = 0.85
_PULSE_RANGE = 0.30
_WAVE_FREQ = 1.1
_WAVE_ROW_PHASE = 0.35
_WAVE_AMP = 0.6
_DARK_INDICES: frozenset[int] = frozenset({12, 13, 14, 15})

# Eye animation
_EYE_PULSE_FREQ = 2.2
_EYE_GLOW_ALPHA_MAX = 90
_EYE_GLOW_RADIUS_PAD = 8          # glow radius = PIXEL_SIZE + pad
_EYE_LERP_SPEED = 3.0              # mais lento → lag em relação ao corpo
_EYE_BLINK_MIN = 2.5
_EYE_BLINK_MAX = 6.0
_EYE_BLINK_DURATION = 0.12        # duração de um piscar completo (fechar + abrir)

# Drips
_DRIP_COUNT = 18
_DRIP_Y_LO = MAP_H * PIXEL_SIZE * 0.55
_DRIP_Y_HI = MAP_H * PIXEL_SIZE * 0.85
_DRIP_VY_LO = 18.0
_DRIP_VY_HI = 55.0
_DRIP_COLOR_INDICES = (2, 3, 6, 7)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lerp_color(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _brighten(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return (
        min(255, int(color[0] * factor)),
        min(255, int(color[1] * factor)),
        min(255, int(color[2] * factor)),
    )



# ---------------------------------------------------------------------------
# Internal state dataclasses (EyeLayer)
# ---------------------------------------------------------------------------

@dataclass
class _LerpOffset:
    ox: float = 0.0
    oy: float = 0.0
    target_ox: float = 0.0
    target_oy: float = 0.0

    def step(self, dt: float) -> None:
        self.ox += (self.target_ox - self.ox) * _EYE_LERP_SPEED * dt
        self.oy += (self.target_oy - self.oy) * _EYE_LERP_SPEED * dt


@dataclass
class _BlinkState:
    t: float = 1.0
    timer: float = 0.0
    next_blink: float = 0.0
    active: bool = False
    phase: float = 0.0

    def __post_init__(self) -> None:
        self.next_blink = random.uniform(_EYE_BLINK_MIN, _EYE_BLINK_MAX)

    def step(self, dt: float) -> None:
        self.timer += dt
        if not self.active and self.timer >= self.next_blink:
            self.active = True
            self.phase = 0.0
            self.next_blink = random.uniform(_EYE_BLINK_MIN, _EYE_BLINK_MAX)
            self.timer = 0.0
        if self.active:
            self.phase = min(1.0, self.phase + dt / _EYE_BLINK_DURATION)
            self.t = 1.0 - math.sin(self.phase * math.pi)
            if self.phase >= 1.0:
                self.active = False
                self.t = 1.0


# ---------------------------------------------------------------------------
# BodyLayer
# ---------------------------------------------------------------------------

class BodyLayer:
    """
    Renderiza o corpo pixel-a-pixel com pulsação de brilho e wave horizontal.
    Pixels do olho (EYE_COLOR_IDX) são omitidos — preenchidos por EyeLayer.

    A posição da camada é passada externamente por ox/oy, permitindo que o
    SlimeBossRenderer aplique qualquer lerp ou offset sem acoplamento.
    """

    def __init__(self) -> None:
        # Pré-computa: None marca os slots de olho (transparentes nesta camada).
        self._rows: list[list[tuple[int, int, int] | None]] = [
            [None if idx == EYE_COLOR_IDX else PALETTE[idx] for idx in row]
            for row in PIXEL_MAP
        ]

    def draw(self, surface: pygame.Surface, ox: float, oy: float, t: float) -> None:
        pulse = _PULSE_MIN + _PULSE_RANGE * (math.sin(t * _PULSE_FREQ) + 1.0) / 2.0

        for row_i, row_colors in enumerate(self._rows):
            dx = int(math.sin(t * _WAVE_FREQ + row_i * _WAVE_ROW_PHASE) * _WAVE_AMP)
            y = int(oy) + row_i * PIXEL_SIZE
            x_base = int(ox) + dx

            for col_i, base in enumerate(row_colors):
                if base is None:
                    continue
                cidx = PIXEL_MAP[row_i][col_i]
                color = base if cidx in _DARK_INDICES else _brighten(base, pulse)
                pygame.draw.rect(
                    surface, color,
                    (x_base + col_i * PIXEL_SIZE, y, PIXEL_SIZE, PIXEL_SIZE),
                )


# ---------------------------------------------------------------------------
# EyeLayer
# ---------------------------------------------------------------------------

class EyeLayer:
    """
    Camada dos olhos com lerp offset independente do corpo.

    Recursos:
      - Glow pulsante sob os pixels de olho.
      - Piscar suave (squish vertical via escala do rect).
      - Offset com lerp próprio (mais lento que o corpo → efeito de "nadar").
      - set_target_offset() para mover os olhos de fora (ex: seguir jogador).
    """

    def __init__(self, eye_positions: list[tuple[int, int]]) -> None:
        self._positions = eye_positions
        self._offset = _LerpOffset()
        self._pulse: float = 0.0
        self._blink = _BlinkState()
        self._glow_surf: pygame.Surface | None = None
        self._glow_radius: int = PIXEL_SIZE + _EYE_GLOW_RADIUS_PAD
        self._eye_surf_cache: tuple[int, pygame.Surface] | None = None

    def set_target_offset(self, ox: float, oy: float) -> None:
        self._offset.target_ox = ox
        self._offset.target_oy = oy

    def update(self, dt: float, t: float) -> None:
        self._pulse = (math.sin(t * _EYE_PULSE_FREQ) + 1.0) / 2.0
        self._offset.step(dt)
        self._blink.step(dt)

    def _draw_glow(self, surface: pygame.Surface, ox: float, oy: float, glow_alpha: int) -> None:
        r = self._glow_radius
        if self._glow_surf is None:
            self._glow_surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        self._glow_surf.fill((0, 0, 0, 0))
        pygame.draw.circle(self._glow_surf, (*EYE_GLOW_COLOR, glow_alpha), (r, r), r)
        for col_i, row_i in self._positions:
            cx = int(ox + col_i * PIXEL_SIZE + PIXEL_SIZE // 2)
            cy = int(oy + row_i * PIXEL_SIZE + PIXEL_SIZE // 2)
            surface.blit(self._glow_surf, (cx - r, cy - r))

    def _draw_pixels(self, surface: pygame.Surface, ox: float, oy: float,
                     eye_color: tuple[int, int, int], ph: int, y_pad: int, alpha: int) -> None:
        if self._eye_surf_cache is None or self._eye_surf_cache[0] != ph:
            px_surf = pygame.Surface((PIXEL_SIZE, ph), pygame.SRCALPHA)
            self._eye_surf_cache = (ph, px_surf)
        else:
            px_surf = self._eye_surf_cache[1]
        px_surf.fill((*eye_color, alpha))
        for col_i, row_i in self._positions:
            x = int(ox + col_i * PIXEL_SIZE)
            y = int(oy + row_i * PIXEL_SIZE) + y_pad
            surface.blit(px_surf, (x, y))

    def draw(self, surface: pygame.Surface, body_ox: float, body_oy: float) -> None:
        if self._blink.t <= 0.01:
            return
        ox = body_ox + self._offset.ox
        oy = body_oy + self._offset.oy
        eye_color = _lerp_color(PALETTE[EYE_COLOR_IDX], EYE_GLOW_COLOR, self._pulse)
        eye_color = _brighten(eye_color, 1.0 + 0.5 * self._pulse)
        glow_alpha = int(_EYE_GLOW_ALPHA_MAX * self._pulse * self._blink.t)
        if glow_alpha > 4:
            self._draw_glow(surface, ox, oy, glow_alpha)
        ph = max(1, int(PIXEL_SIZE * self._blink.t))
        y_pad = (PIXEL_SIZE - ph) // 2
        alpha = int(200 + 55 * self._pulse)
        self._draw_pixels(surface, ox, oy, eye_color, ph, y_pad, alpha)


# ---------------------------------------------------------------------------
# DripsSystem
# ---------------------------------------------------------------------------

@dataclass
class _Drip:
    x: float
    y: float
    vy: float
    size: int
    color: tuple[int, int, int]


class DripsSystem:
    """Gosma caindo pela base do sprite. Camada desenhada antes do corpo."""

    def __init__(self) -> None:
        self._drips: list[_Drip] = [self._make() for _ in range(_DRIP_COUNT)]
        # Cache de glow surfaces por raio
        self._glow_cache: dict[int, pygame.Surface] = {}

    def _make(self, force_x: int | None = None) -> _Drip:
        x_pixel = force_x if force_x is not None else random.randint(10, MAP_W - 10)
        return _Drip(
            x=x_pixel * PIXEL_SIZE + PIXEL_SIZE // 2,
            y=random.uniform(_DRIP_Y_LO, _DRIP_Y_HI),
            vy=random.uniform(_DRIP_VY_LO, _DRIP_VY_HI),
            size=random.randint(2, 5),
            color=PALETTE[random.choice(_DRIP_COLOR_INDICES)],
        )

    def _glow_surf(self, size: int) -> pygame.Surface:
        r = size + 1
        if r not in self._glow_cache:
            diam = r * 4
            s = pygame.Surface((diam, diam), pygame.SRCALPHA)
            pygame.draw.circle(s, (*PALETTE[3], 60), (r * 2, r * 2), r * 2)
            self._glow_cache[r] = s
        return self._glow_cache[r]

    def update_and_draw(self, surface: pygame.Surface, dt: float) -> None:
        alive: list[_Drip] = []
        for drip in self._drips:
            drip.y += drip.vy * dt

            glow = self._glow_surf(drip.size)
            r = drip.size + 1
            surface.blit(glow, (int(drip.x) - r * 2, int(drip.y) - r * 2))
            pygame.draw.circle(surface, drip.color, (int(drip.x), int(drip.y)), drip.size)

            alive.append(drip if drip.y < WIN_H + 20 else self._make())
        self._drips = alive


# ---------------------------------------------------------------------------
# SlimeBossRenderer — orquestra as três camadas
# ---------------------------------------------------------------------------

class SlimeBossRenderer:
    """
    Renderizador em camadas do Boss Gosma.

    Ordem de blit por frame:
      1. DripsSystem  — sob o corpo
      2. BodyLayer    — corpo sem olhos
      3. EyeLayer     — olhos com glow, lag e piscar
    """

    def __init__(self, surface: pygame.Surface) -> None:
        self.surface = surface
        self.time: float = 0.0

        eye_positions: list[tuple[int, int]] = [
            (col_i, row_i)
            for row_i, row in enumerate(PIXEL_MAP)
            for col_i, idx in enumerate(row)
            if idx == EYE_COLOR_IDX
        ]

        self._body = BodyLayer()
        self._eyes = EyeLayer(eye_positions)
        self._drips = DripsSystem()

        # Posição do canto superior-esquerdo do boss em tela
        self._ox: float = 0.0
        self._oy: float = 0.0

    def update(self, dt: float) -> None:
        self.time += dt
        self._eyes.update(dt, self.time)

    def draw(self) -> None:
        self.surface.fill(BG_COLOR)
        self._drips.update_and_draw(self.surface, 0.0)  # dt gerenciado internamente
        self._body.draw(self.surface, self._ox, self._oy, self.time)
        self._eyes.draw(self.surface, self._ox, self._oy)

    def render(self, dt: float) -> None:
        """Atalho para o loop de teste: update + draw em uma chamada."""
        self.update(dt)
        # Drips precisam do dt real — refazemos aqui com dt correto
        self.surface.fill(BG_COLOR)
        self._drips.update_and_draw(self.surface, dt)
        self._body.draw(self.surface, self._ox, self._oy, self.time)
        self._eyes.draw(self.surface, self._ox, self._oy)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption(TITLE)
    clock = pygame.time.Clock()

    renderer = SlimeBossRenderer(screen)

    running = True
    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        renderer.render(dt)
        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
