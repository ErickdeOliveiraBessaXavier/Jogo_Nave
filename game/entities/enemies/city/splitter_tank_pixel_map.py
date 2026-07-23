"""Splitter Tank — constantes de grade e paleta do núcleo.

O chassi do Splitter Tank é desenhado a partir de **sprites pixel-art** feitos à
mão (`assets/images/Sprites_Splitter_Tank/`, ver `splitter_tank.py`), não mais por
uma surface procedural. Este módulo guarda só o que o entity ainda consome:

  - `PIXEL_COLS`/`PIXEL_ROWS`: grade lógica que define o tamanho do chassi por
    tier (`PIXEL_COLS * cell`), preservando a escala original.
  - `CORE_NEON`/`CORE_NEON_DIM`: cor do bloom neon que o `draw` anima sobre o
    núcleo para telegrafar o *split*.
"""

from __future__ import annotations

from typing import Tuple

from . import city_palette as pal

RGB = Tuple[int, int, int]

PIXEL_COLS = 15
PIXEL_ROWS = 15

# ── Núcleo (consumido pelo bloom animado do draw) ──────────────────────────
CORE_NEON: RGB = pal.TOXIC_ORANGE
CORE_NEON_DIM: RGB = pal.TOXIC_ORANGE_DIM
