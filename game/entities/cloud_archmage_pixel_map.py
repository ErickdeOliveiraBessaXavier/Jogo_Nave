"""Pixel maps e paletas de cor do `CloudArchmageBoss`.

Centraliza HAT_MAP/BODY_MAP/ARM_MAP (layout de sprites em ascii), o mapa
char->chave de paleta, e as variações de cores por estado (normal/phase3/
flash/white). Mantém a convenção `*_pixel_map.py` dos outros bosses
(`spike_boss_pixel_map.py`, `stone_golem_pixel_map.py`, etc.).
"""

from __future__ import annotations

from typing import Final

Color = tuple[int, int, int]


# ---------------------------------------------------------------------------
# Pixel maps
# ---------------------------------------------------------------------------

HAT_MAP: Final[list[str]] = [
    ".........H........",
    "........H*H.......",
    ".......H**H.......",
    "......H***H.......",
    ".....HH****H......",
    "....H******HH.....",
    "...HH********H....",
    "..HHHHHHHHHHHHHH..",
    ".HOOOOOOOOOOOOOOH.",
    "H****************H",
]

BODY_MAP: Final[list[str]] = [
    "....GGGGGGGG....",
    "...GBBBBBBBBG...",
    "..GBBMMMMMMBBG..",
    "..BBMEEEEEEMBB..",
    "..BBMEEEEEEMBB..",
    "..BBOOOOOOOOBB.",
    "..BBBB....BBBB..",
    ".BBBB......BBBB.",
]

ARM_MAP: Final[list[str]] = [
    "..GG..",
    ".GBBG.",
    ".BBBB.",
    "..MM..",
    ".MOOM.",
    ".MDDM.",
    "..DD..",
]


# ---------------------------------------------------------------------------
# Palettes (estado visual -> paleta de partes)
# ---------------------------------------------------------------------------

PALETTES: Final[dict[str, dict[str, Color]]] = {
    "normal": {
        "robe": (60, 45, 110),
        "metal": (100, 105, 115),
        "visor": (10, 10, 20),
        "core": (30, 25, 45),
        "hat": (45, 30, 85),
        "hat_hl": (80, 60, 150),
        "joint": (30, 30, 35),
        "gold": (212, 175, 55),
        "gola": (80, 70, 140),
    },
    "phase3": {
        "robe": (40, 10, 60),
        "metal": (60, 65, 80),
        "visor": (20, 0, 0),
        "core": (25, 5, 30),
        "hat": (30, 5, 50),
        "hat_hl": (100, 20, 50),
        "joint": (20, 10, 15),
        "gold": (180, 130, 40),
        "gola": (60, 20, 80),
    },
    "flash": {
        k: (255, 255, 255)
        for k in (
            "robe",
            "metal",
            "visor",
            "core",
            "hat",
            "hat_hl",
            "joint",
            "gold",
            "gola",
        )
    },
    "white": {
        "robe": (90, 100, 120),
        "metal": (130, 140, 155),
        "visor": (20, 25, 40),
        "core": (180, 210, 240),
        "hat": (80, 90, 110),
        "hat_hl": (150, 170, 190),
        "joint": (50, 55, 70),
        "gold": (160, 170, 180),
        "gola": (110, 125, 145),
    },
}


# ---------------------------------------------------------------------------
# Mapeamento de caracteres do pixel-map -> chave da paleta
# ---------------------------------------------------------------------------

CHAR_TO_KEY: Final[dict[str, str]] = {
    "H": "hat",
    "*": "hat_hl",
    "M": "metal",
    "V": "visor",
    "E": "core",
    "D": "joint",
    "O": "gold",
    "G": "gola",
    "B": "robe",
}
