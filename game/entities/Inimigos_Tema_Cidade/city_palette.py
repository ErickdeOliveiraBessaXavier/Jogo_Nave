"""Paleta cyberpunk compartilhada do bioma CITY.

Centraliza as cores da "Máquina Urbana" descritas na proposta para que os 6
inimigos da cidade tenham uma estética coesa (Industrial Gritty). Importe
daqui em vez de hardcodar tuplas RGB por arquivo.

Camadas de cor (mapeadas nos pixel-maps por letra de zona):
  - Chassi / blindagem: Gunmetal Gray e Deep Slate desgastados.
  - Glow / energia:     Electric Blue, Cyber Magenta, Toxic Orange.
  - Detalhe:            highlights e sombras derivados do chassi.
"""

from __future__ import annotations

from typing import Tuple

RGB = Tuple[int, int, int]

# ── Chassi / blindagem (metais desgastados) ────────────────────────────────
OUTLINE: RGB = (14, 16, 22)  # Contorno quase preto (Deep Slate profundo)
DEEP_SLATE: RGB = (28, 32, 42)
GUNMETAL: RGB = (60, 66, 78)  # Corpo principal
HULL_LIGHT: RGB = (96, 104, 118)  # Face superior iluminada
HULL_SHADOW: RGB = (38, 42, 52)  # Face inferior em sombra
GRID_BAR: RGB = (20, 23, 30)  # Grade sobre o núcleo

# ── Glow / energia (pixels emissivos) ──────────────────────────────────────
ELECTRIC_BLUE: RGB = (40, 200, 255)
ELECTRIC_BLUE_DIM: RGB = (20, 90, 140)
CYBER_MAGENTA: RGB = (255, 50, 200)
CYBER_MAGENTA_DIM: RGB = (120, 22, 95)
TOXIC_ORANGE: RGB = (255, 140, 30)
TOXIC_ORANGE_DIM: RGB = (130, 70, 16)

# ── Apelidos semânticos por função ──────────────────────────────────────────
WIRE: RGB = TOXIC_ORANGE  # Fiação exposta
NEON_CORE: RGB = ELECTRIC_BLUE  # Núcleo emissivo / indicador de estado
THRUSTER: RGB = CYBER_MAGENTA  # Micro-propulsores

# Paleta de explosão "Static Pop" (descarga elétrica): azul → magenta → branco.
EXPLOSION_CYBER: list[RGB] = [
    ELECTRIC_BLUE,
    (180, 220, 255),
    CYBER_MAGENTA,
    (255, 255, 255),
]


def lerp(a: RGB, b: RGB, t: float) -> RGB:
    """Interpola linearmente entre duas cores (t em 0..1). Usado para pulso de glow."""
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )
