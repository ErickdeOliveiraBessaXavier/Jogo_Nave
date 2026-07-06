"""Paleta compartilhada do bioma STARFIELD (Espaço) — estética SÓBRIA.

Ao contrário da CITY (neon saturado + halos aditivos), o Espaço é frio e fosco:
casco em cinzas-aço e azul-noite, sombreamento chapado, contornos escuros e
**acentos discretos** (luzes de posição fracas, âmbar de aviso apagado). Nada de
glow de múltiplas camadas — o brilho, quando existe, é 1 disco tênue e sutil.

Utilidade pura (constantes + `lerp`); nenhuma classe alcança o privado de outra
para pintar (§1). Sem cache de glow próprio (a sobriedade dispensa o bloom).
"""

from __future__ import annotations

from typing import Tuple

RGB = Tuple[int, int, int]

# ── Casco (metal frio, fosco) ────────────────────────────────────────────────
VOID = (10, 12, 18)            # fundo/vazio interno, quase preto azulado
OUTLINE = (16, 19, 26)         # contorno escuro
HULL_SHADOW = (34, 39, 49)     # metal em sombra
HULL_DARK = (48, 55, 66)       # metal base escuro
HULL_BASE = (66, 74, 87)       # metal base
HULL_LIGHT = (94, 103, 117)    # face iluminada
HULL_HILIGHT = (128, 138, 152) # aresta de destaque (luz superior)

# ── Acentos discretos (usar com PARCIMÔNIA) ──────────────────────────────────
ACCENT_COLD = (120, 152, 172)      # ciano-acinzentado frio (luzes de posição)
ACCENT_COLD_DIM = (58, 78, 92)     # o mesmo, apagado
WARNING_AMBER = (170, 138, 82)     # âmbar de aviso fosco (telegraph)
WARNING_AMBER_DIM = (96, 78, 48)

# ── Núcleo/energia contida (sombrio, não neon) ───────────────────────────────
CORE_DARK = (22, 27, 38)       # núcleo colapsado (quase preto)
CORE_RIM = (86, 108, 128)      # aro frio do núcleo
CORE_HOT = (150, 178, 198)     # ponto mais claro (contido)


def lerp(a: RGB, b: RGB, t: float) -> RGB:
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )
