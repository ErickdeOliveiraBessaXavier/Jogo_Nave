"""
Elemental Robot — Pixel Map e paletas de cores.

Estrutura da sprite (18 × 28 "pixels"):
  - Ponta da antena com glint e sombra inset (linhas 0-3)
  - Haste da antena com bordas laterais (linhas 4-9)
  - Ombros salientes / shoulder bumps (linha 9, coexiste com base da haste)
  - Corpo principal com faixas de luz/sombra inset e olhos (linhas 10-18)
  - Base strip (linha 19)
  - Propulsor com 3 faixas de largura decrescente (linhas 20-27)

Zonas de cor no PIXEL_MAP
──────────────────────────
  "A"  → --current-outline / contorno / sombra profunda / braço exterior
  "B"  → --current-body    / corpo principal (borda estrutural e interior base)
  "C"  → #4a5a68 fixo      / haste da antena / sombra inset da ponta (não muda por tema)
  "D"  → --current-body    / interior neutro do corpo (zona média)
  "E"  → #8e9eab fixo      / face superior da ponta da antena (não muda por tema)
  "F"  → --current-light   / faixa de luz no topo do corpo  (inset 0  12px)
  "G"  → --current-dark    / faixa de sombra na base do corpo (inset 0 -12px)
  "H"  → #ffffff fixo      / glint branco da ponta da antena (.glint no HTML)
  "I"  → #4a5a68 fixo      / interior dos shoulder bumps (background hardcoded no HTML)
  "T1" → --thruster-1      / propulsor — banda 1 (mais larga)
  "T2" → --thruster-2      / propulsor — banda 2 (média)
  "T3" → --thruster-3      / propulsor — banda 3 (mais fina)
  None → transparente

Zonas de olho (não entram no PIXEL_MAP — desenhadas proceduralmente):
  EYE_BG_*    → fundo do olho (--eye-base)
  EYE_IRIS_*  → íris / pupila colorida
  EYE_GLINT   → reflexo branco (pupil::before)
"""

from typing import Tuple

# ──────────────────────────────────────────────────────────────────
# DIMENSÕES BASE
# ──────────────────────────────────────────────────────────────────

PIXEL_COLS = 18
PIXEL_ROWS = 28

# ──────────────────────────────────────────────────────────────────
# REGIÕES ESPECIAIS
# ──────────────────────────────────────────────────────────────────

# Ponta da antena (rows 0-3, cols 7-10)
ANTENNA_ROW_START = 0
ANTENNA_ROW_END = 3
ANTENNA_COL_START = 7
ANTENNA_COL_END = 10

# Glint branco da ponta — espelha .glint { top:2px; left:2px; width:8px; height:8px }
ANTENNA_GLINT_ROW = 1
ANTENNA_GLINT_COL = 8

# Centro da aura de energia — espelha .aura { top:8px; left:calc(50%-4px) }
# Usado pelo código de renderização para posicionar o efeito de charging/firing.
AURA_ROW = 1
AURA_COL = 9

# Haste da antena: interior cols 8-9, bordas laterais cols 7 e 10
ANTENNA_STEM_ROW_START = 4
ANTENNA_STEM_ROW_END = 9
ANTENNA_STEM_COL_START = 8  # interior esquerdo
ANTENNA_STEM_COL_END = 9  # interior direito
ANTENNA_STEM_BORDER_L = 7  # border-left:  4px solid --current-outline
ANTENNA_STEM_BORDER_R = 10  # border-right: 4px solid --current-outline

# Ombros / shoulder bumps
# Aparecem na linha 9 (última da haste, acima do corpo).
# No HTML: body-main::before/after { width:12px; height:12px; border:4px solid;
#           top:-4px; left:-16px / right:-16px; background:#4a5a68 }
SHOULDER_ROW = 9
SHOULDER_LEFT_COL_START = 1  # "A" = borda exterior
SHOULDER_LEFT_COL_END = 2  # "I" = interior (#4a5a68 fixo)
SHOULDER_RIGHT_COL_START = 15  # "I" = interior
SHOULDER_RIGHT_COL_END = 16  # "A" = borda exterior

# Corpo principal
BODY_ROW_START = 10
BODY_ROW_END = 18
BODY_COL_START = 2  # interior começa aqui (col 1 e 16 = borda "B")
BODY_COL_END = 15

# Faixa clara — espelha: box-shadow inset 0 12px 0 var(--current-light)
BODY_LIGHT_ROW_START = 11
BODY_LIGHT_ROW_END = 12

# Faixa escura — espelha: box-shadow inset 0 -12px 0 var(--current-dark)
BODY_DARK_ROW_START = 16
BODY_DARK_ROW_END = 17

# Olhos: 2 olhos de 4×3 blocos — espelha .eye { width:32px; height:24px }
# Linhas 13-15, olho esquerdo cols 4-7, olho direito cols 9-12
EYE_ROW_START = 13
EYE_ROW_END = 15
EYE_LEFT_COL_START = 4
EYE_LEFT_COL_END = 7
EYE_RIGHT_COL_START = 9
EYE_RIGHT_COL_END = 12

# Pupila — espelha .pupil { width:16px; height:16px; bottom:2px; left:8px }
# Não está no PIXEL_MAP (desenhada proceduralmente), mas as constantes
# guiam o código de renderização quanto à posição correta (off-center: 1 bloco
# da esquerda, 2 últimas linhas do olho).
PUPIL_ROW_START = 14
PUPIL_ROW_END = 15
PUPIL_LEFT_COL_START = 5  # EYE_LEFT_COL_START  + 1  (left: 8px)
PUPIL_LEFT_COL_END = 6
PUPIL_RIGHT_COL_START = 10  # EYE_RIGHT_COL_START + 1
PUPIL_RIGHT_COL_END = 11

# Reflexo (glint) da pupila — espelha pupil::before { top:2px; left:2px; 4×4px }
# = canto superior-esquerdo do bloco da pupila
PUPIL_GLINT_ROW = 14
PUPIL_GLINT_LEFT_COL = 5
PUPIL_GLINT_RIGHT_COL = 10

# Base strip — espelha .base { width:110px; height:16px; background:#0b0c10;
#               border:4px solid --current-outline; border-top:none }
BASE_ROW = 19
BASE_COL_START = 2  # ~110px centrado no corpo de 14 cols
BASE_COL_END = 15

# Propulsor — espelha .thruster-block { height:6px; margin-bottom:2px }
# Bandas centradas com larguras 70px : 44px : 20px (ratio aprox. 10 : 6 : 2 cols)
THRUSTER_ROW_1_START = 20
THRUSTER_ROW_1_END = 21
THRUSTER_ROW_2_START = 23  # linha 22 = gap (None)
THRUSTER_ROW_2_END = 24
THRUSTER_ROW_3_START = 26  # linha 25 = gap (None)
THRUSTER_ROW_3_END = 27

THRUSTER_1_COL_START = 4  # 10 cols centradas ≈ 70px do HTML
THRUSTER_1_COL_END = 13
THRUSTER_2_COL_START = 6  # 6 cols centradas  ≈ 44px
THRUSTER_2_COL_END = 11
THRUSTER_3_COL_START = 8  # 2 cols centradas  ≈ 20px
THRUSTER_3_COL_END = 9

# ──────────────────────────────────────────────────────────────────
# PIXEL MAP  (18 colunas × 28 linhas)
# ──────────────────────────────────────────────────────────────────

_ = None  # alias para transparente

#                col: 0     1     2     3     4     5     6     7     8     9    10    11    12    13    14    15    16    17
PIXEL_MAP: list[list[str | None]] = [
    # row  0 — borda superior da ponta da antena
    [_, _, _, _, _, _, _, "A", "A", "A", "A", _, _, _, _, _, _, _],
    # row  1 — H=glint (top-left), E=face, A=borda  (.glint { top:2px; left:2px })
    [_, _, _, _, _, _, _, "A", "H", "E", "A", _, _, _, _, _, _, _],
    # row  2 — E=face, C=inset-shadow canto bot-right  (box-shadow inset -4px -4px 0 #4a5a68)
    [_, _, _, _, _, _, _, "A", "E", "C", "A", _, _, _, _, _, _, _],
    # row  3 — borda inferior da ponta
    [_, _, _, _, _, _, _, "A", "A", "A", "A", _, _, _, _, _, _, _],
    # row  4 — haste da antena  (cols 7,10=bordas "A"; cols 8-9=interior "C")
    [_, _, _, _, _, _, _, "A", "C", "C", "A", _, _, _, _, _, _, _],
    # row  5
    [_, _, _, _, _, _, _, "A", "C", "C", "A", _, _, _, _, _, _, _],
    # row  6
    [_, _, _, _, _, _, _, "A", "C", "C", "A", _, _, _, _, _, _, _],
    # row  7
    [_, _, _, _, _, _, _, "A", "C", "C", "A", _, _, _, _, _, _, _],
    # row  8
    [_, _, _, _, _, _, _, "A", "C", "C", "A", _, _, _, _, _, _, _],
    # row  9 — última haste + shoulder bumps  (::before/after { top:-4px; left/right:-16px })
    [_, "A", "I", _, _, _, _, "A", "C", "C", "A", _, _, _, _, "I", "A", _],
    # row 10 — borda superior do corpo
    [
        _,
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        _,
    ],
    # row 11 — faixa clara topo (F), sem braços  (box-shadow inset 0 12px 0 --current-light)
    [
        _,
        "B",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "B",
        _,
    ],
    # row 12 — faixa clara topo (F), com braços
    [
        "A",
        "B",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "F",
        "B",
        "A",
    ],
    # row 13 — olhos  (cols 4-7=eye_L, cols 9-12=eye_R; None=desenhado proceduralmente)
    ["A", "B", "D", "D", _, _, _, _, "D", _, _, _, _, "D", "D", "D", "B", "A"],
    # row 14
    ["A", "B", "D", "D", _, _, _, _, "D", _, _, _, _, "D", "D", "D", "B", "A"],
    # row 15
    ["A", "B", "D", "D", _, _, _, _, "D", _, _, _, _, "D", "D", "D", "B", "A"],
    # row 16 — faixa escura base (G), com braços  (box-shadow inset 0 -12px 0 --current-dark)
    [
        "A",
        "B",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "B",
        "A",
    ],
    # row 17
    [
        "A",
        "B",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "G",
        "B",
        "A",
    ],
    # row 18 — borda inferior do corpo
    [
        _,
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        "B",
        _,
    ],
    # row 19 — base strip  (.base { background:#0b0c10; border:4px solid; border-top:none })
    [_, _, "A", "A", "A", "A", "A", "A", "A", "A", "A", "A", "A", "A", "A", "A", _, _],
    # row 20 — propulsor banda 1 / tb-1  (width≈70px, cols 4-13)
    [
        _,
        _,
        _,
        _,
        "T1",
        "T1",
        "T1",
        "T1",
        "T1",
        "T1",
        "T1",
        "T1",
        "T1",
        "T1",
        _,
        _,
        _,
        _,
    ],
    # row 21
    [
        _,
        _,
        _,
        _,
        "T1",
        "T1",
        "T1",
        "T1",
        "T1",
        "T1",
        "T1",
        "T1",
        "T1",
        "T1",
        _,
        _,
        _,
        _,
    ],
    # row 22 — gap entre bandas (margin-bottom:2px)
    [_, _, _, _, _, _, _, _, _, _, _, _, _, _, _, _, _, _],
    # row 23 — propulsor banda 2 / tb-2  (width≈44px, cols 6-11)
    [_, _, _, _, _, _, "T2", "T2", "T2", "T2", "T2", "T2", _, _, _, _, _, _],
    # row 24
    [_, _, _, _, _, _, "T2", "T2", "T2", "T2", "T2", "T2", _, _, _, _, _, _],
    # row 25 — gap entre bandas
    [_, _, _, _, _, _, _, _, _, _, _, _, _, _, _, _, _, _],
    # row 26 — propulsor banda 3 / tb-3  (width≈20px, cols 8-9)
    [_, _, _, _, _, _, _, _, "T3", "T3", _, _, _, _, _, _, _, _],
    # row 27
    [_, _, _, _, _, _, _, _, "T3", "T3", _, _, _, _, _, _, _, _],
]

# ──────────────────────────────────────────────────────────────────
# MAPEAMENTO DE ZONAS → CHAVES DE PALETA TEMÁTICA
# Utilizado pelo código de renderização ao aplicar ATTACK_PALETTES.
# Zonas ausentes (C, E, H, I) são cores fixas e não mudam por tema.
# ──────────────────────────────────────────────────────────────────

COLOR_ZONE_MAP: dict[str, str] = {
    "A": "body_outline",  # --current-outline
    "B": "body_main",  # --current-body
    "D": "body_main",  # idem (mesmo CSS var, zona conceptualmente distinta)
    "F": "body_light",  # inset top   → --current-light
    "G": "body_dark",  # inset bottom → --current-dark
}

# ──────────────────────────────────────────────────────────────────
# PALETA DE CORES BASE (neutro)
# Espelha os valores de :root do HTML de referência.
# ──────────────────────────────────────────────────────────────────

C: dict[str, Tuple[int, int, int]] = {
    # ── Zonas do pixel map ────────────────────────────────────────
    "A": (11, 12, 16),  # --robot-outline-neutral: #0b0c10
    "B": (58, 79, 99),  # --robot-body-neutral:    #3a4f63
    "C": (74, 90, 104),  # #4a5a68 — haste / inset sombra ponta (fixo)
    "D": (58, 79, 99),  # interior corpo (= B neutro; tematizado como body_main)
    "E": (142, 158, 171),  # #8e9eab — face da ponta da antena (fixo)
    "F": (99, 122, 140),  # --robot-light-neutral:   #637a8c
    "G": (38, 52, 66),  # --robot-dark-neutral:    #263442
    "H": (255, 255, 255),  # glint branco da antena   #ffffff (fixo)
    "I": (74, 90, 104),  # #4a5a68 — shoulder bump interior (fixo, não tematizado)
    "T1": (255, 255, 255),  # --thruster-1 neutro: #ffffff
    "T2": (92, 225, 230),  # --thruster-2 neutro: #5CE1E6
    "T3": (0, 119, 194),  # --thruster-3 neutro: #0077c2
    # ── Derivados neutros (referência) ───────────────────────────
    "DARK_NEUTRAL": (38, 52, 66),  # #263442
    "LIGHT_NEUTRAL": (99, 122, 140),  # #637a8c
    # ── Olho — estado padrão (azul ciano) ────────────────────────
    "EYE_BG_DEFAULT": (19, 25, 32),
    "EYE_IRIS_DEFAULT": (92, 225, 230),  # --eye-pupil-cyan: #5CE1E6
    "EYE_GLINT": (255, 255, 255),  # pupil::before #ffffff
    # ── Olho — Inferno (laranja) ──────────────────────────────────
    "EYE_BG_INFERNO": (40, 10, 0),
    "EYE_IRIS_INFERNO": (255, 140, 0),
    # ── Olho — Toxina (verde neon) ────────────────────────────────
    "EYE_BG_TOXINA": (13, 46, 13),
    "EYE_IRIS_TOXINA": (57, 255, 20),
    # ── Olho — Nevasca (azul gelo) ────────────────────────────────
    "EYE_BG_NEVASCA": (0, 26, 51),
    "EYE_IRIS_NEVASCA": (138, 226, 255),
    # ── Núcleo de energia da antena (aura / charging) ─────────────
    "CORE_INFERNO": (255, 235, 181),
    "CORE_TOXINA": (234, 255, 208),
    "CORE_NEVASCA": (255, 255, 255),
    # Mantido por compatibilidade com código existente
    "PUPIL": (255, 255, 255),  # use EYE_GLINT em código novo
}

# ──────────────────────────────────────────────────────────────────
# PALETAS COMPLETAS POR ATAQUE
# Espelham applyPalette() e os valores CSS de cada [data-theme].
# ──────────────────────────────────────────────────────────────────

ATTACK_PALETTES: dict[str, dict[str, Tuple[int, int, int]]] = {
    "inferno": {
        # Energia / aura
        "core": (255, 235, 181),  # #ffebb5
        "mid": (255, 140, 0),  # #ff8c00
        "outer": (209, 32, 0),  # #d12000
        # Olho
        "eye_bg": C["EYE_BG_INFERNO"],
        "eye_iris": C["EYE_IRIS_INFERNO"],
        # Corpo (zones A/B/D/F/G)
        "body_outline": (61, 20, 0),  # #3d1400  → zone "A"
        "body_main": (94, 71, 62),  # #5e473e  → zones "B","D"
        "body_dark": (66, 48, 42),  # #42302a  → zone  "G"
        "body_light": (138, 108, 98),  # #8a6c62  → zone  "F"
        # Propulsor (zones T1/T2/T3)
        "thruster_1": (255, 235, 181),
        "thruster_2": (255, 140, 0),
        "thruster_3": (209, 32, 0),
    },
    "toxina": {
        "core": (234, 255, 208),  # #eaffd0
        "mid": (57, 255, 20),  # #39ff14
        "outer": (0, 128, 0),  # #008000
        "eye_bg": C["EYE_BG_TOXINA"],
        "eye_iris": C["EYE_IRIS_TOXINA"],
        "body_outline": (13, 46, 13),  # #0d2e0d
        "body_main": (71, 99, 58),  # #47633a
        "body_dark": (48, 66, 38),  # #304226
        "body_light": (122, 140, 99),  # #7a8c63
        "thruster_1": (234, 255, 208),
        "thruster_2": (57, 255, 20),
        "thruster_3": (0, 128, 0),
    },
    "nevasca": {
        "core": (255, 255, 255),  # #ffffff
        "mid": (138, 226, 255),  # #8ae2ff
        "outer": (0, 85, 255),  # #0055ff
        "eye_bg": C["EYE_BG_NEVASCA"],
        "eye_iris": C["EYE_IRIS_NEVASCA"],
        "body_outline": (0, 26, 51),  # #001a33
        "body_main": (77, 110, 140),  # #4d6e8c
        "body_dark": (43, 74, 105),  # #2b4a69
        "body_light": (140, 168, 196),  # #8ca8c4
        "thruster_1": (255, 255, 255),
        "thruster_2": (138, 226, 255),
        "thruster_3": (0, 85, 255),
    },
}

# Propulsor neutro (fora de ataque) — espelha :root do HTML
# Índices: [0] = T1/tb-1, [1] = T2/tb-2, [2] = T3/tb-3
THRUSTER_NEUTRAL: tuple[
    Tuple[int, int, int],
    Tuple[int, int, int],
    Tuple[int, int, int],
] = (
    (255, 255, 255),  # tb-1  --thruster-1: #ffffff
    (92, 225, 230),  # tb-2  --thruster-2: #5CE1E6
    (0, 119, 194),  # tb-3  --thruster-3: #0077c2
)
