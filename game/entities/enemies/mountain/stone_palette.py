"""Paletas de cor compartilhadas para entidades de terra/pedra.

Centraliza tons de marrom/cinza usados por fragmentos do `StoneGolemBoss`
(rocks orbitais) e do `RockGlider`. Evita drift visual entre as duas
fontes que precisam manter consistência.
"""

from __future__ import annotations

STONE_FRAGMENT_PALETTE: list[tuple[int, int, int]] = [
    (101, 67, 33),    # Marrom escuro (terra)
    (84, 56, 26),     # Marrom profundo
    (65, 65, 65),     # Cinza pedra
    (45, 45, 45),     # Pedra escura
    (139, 115, 85),   # Barro/Argila
    (160, 82, 45),    # Sienna
]
