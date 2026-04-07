"""
Elemental Robot — Pixel Map e paletas de cores.

Estrutura da sprite (19×22 "pixels"):
  - Ponta da antena (topo)
  - Haste da antena
  - Corpo principal com olhos
  - Base
  - Propulsor (thruster)
"""

from typing import Tuple

# ──────────────────────────────────────────────────────────────────
# MAPA DE PIXELS
# Letras representam zonas de cor (A = mais escuro … F = mais claro).
# None = transparente.
# ──────────────────────────────────────────────────────────────────

# Dimensões base da sprite (em "pixels" do mapa)
PIXEL_COLS = 18
PIXEL_ROWS = 26

# ── Antena ────────────────────────────────────────────────────────
# Topo quadrado (4×4) centrado na coluna 7..10
# Haste fina (2×6) centralizada nas colunas 8..9
# ── Corpo ─────────────────────────────────────────────────────────
# Largura: 14 px (colunas 2..15), altura: 8 px (linhas 12..19)
# Saliências de ombro: 2×2 no topo esquerdo (col 1) e direito (col 16)
# Braços: 1×5 nas laterais (cols 0..1 e 16..17), linhas 13..17
# ── Olhos ─────────────────────────────────────────────────────────
# 2 olhos 4×3 px dentro do corpo (ver constantes EYE_*)
# ── Base ──────────────────────────────────────────────────────────
# Faixa fina 12×2 centrada (colunas 3..14)
# ── Propulsor ─────────────────────────────────────────────────────
# Desenhado proceduralmente em _draw_thruster()

PIXEL_MAP: list[list[str | None]] = [
    # row 0 — topo da antena (ponta 4×4)
    [None, None, None, None, None, None, None, "E", "E", "E", "E", None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, "E", "D", "D", "E", None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, "E", "D", "D", "E", None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, "E", "E", "E", "E", None, None, None, None, None, None, None],
    # row 4..9 — haste da antena (2×6)
    [None, None, None, None, None, None, None, None, "C", "C", None, None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, "C", "C", None, None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, "C", "C", None, None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, "C", "C", None, None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, "C", "C", None, None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, "C", "C", None, None, None, None, None, None, None, None],
    # row 10..11 — ombros / topo do corpo
    [None, "B", "B", "B", "B", "B", "B", "B", "B", "B", "B", "B", "B", "B", "B", "B", "B", None],
    [None, "B", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "B", None],
    # row 12..17 — corpo com braços e olhos
    ["A", "B", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "B", "A"],
    ["A", "B", "D", "D", None, None, None, None, None, None, None, None, None, "D", "D", "B", "A"],  # linha dos olhos — None = desenhado em _draw_eyes
    ["A", "B", "D", "D", None, None, None, None, None, None, None, None, None, "D", "D", "B", "A"],
    ["A", "B", "D", "D", None, None, None, None, None, None, None, None, None, "D", "D", "B", "A"],
    ["A", "B", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "B", "A"],
    ["A", "B", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "B", "A"],
    # row 18..19 — base do corpo
    [None, "B", "B", "B", "B", "B", "B", "B", "B", "B", "B", "B", "B", "B", "B", "B", "B", None],
    [None, None, "A", "A", "A", "A", "A", "A", "A", "A", "A", "A", "A", "A", "A", "A", None, None],
    # row 20..25 — propulsor (placeholder; desenhado proceduralmente)
    [None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
]

# ──────────────────────────────────────────────────────────────────
# REGIÕES ESPECIAIS
# ──────────────────────────────────────────────────────────────────

# Ponta da antena (linhas 0..3, colunas 7..10)
ANTENNA_ROW_START = 0
ANTENNA_ROW_END = 3
ANTENNA_COL_START = 7
ANTENNA_COL_END = 10

# Olhos: 2 olhos de 4×3 px dentro do corpo
# Olho esquerdo: colunas 4..7, linhas 13..15
# Olho direito:  colunas 9..12, linhas 13..15
EYE_ROW_START = 13
EYE_ROW_END = 15
EYE_LEFT_COL_START = 4
EYE_LEFT_COL_END = 7
EYE_RIGHT_COL_START = 9
EYE_RIGHT_COL_END = 12

# ──────────────────────────────────────────────────────────────────
# PALETA BASE (neutro)
# ──────────────────────────────────────────────────────────────────

C: dict[str, Tuple[int, int, int]] = {
    # Corpo neutro
    "A": (11, 12, 16),    # contorno / sombra profunda
    "B": (58, 79, 99),    # corpo escuro (borda)
    "C": (74, 90, 104),   # haste antena
    "D": (58, 79, 99),    # painel do corpo (igual B — variação via iluminação)
    "E": (142, 158, 171), # topo antena (mais claro)

    # Olho — estado padrão (azul ciano)
    "EYE_BG_DEFAULT":   (19, 25, 32),
    "EYE_IRIS_DEFAULT": (92, 225, 230),   # ciano

    # Olho — Inferno (vermelho/laranja)
    "EYE_BG_INFERNO":   (40, 10, 0),
    "EYE_IRIS_INFERNO": (255, 140, 0),

    # Olho — Toxina (verde neon)
    "EYE_BG_TOXINA":    (13, 46, 13),
    "EYE_IRIS_TOXINA":  (57, 255, 20),

    # Olho — Nevasca (azul gelo)
    "EYE_BG_NEVASCA":   (0, 26, 51),
    "EYE_IRIS_NEVASCA": (138, 226, 255),

    # Núcleo de energia da antena (cor varia por ataque)
    "CORE_INFERNO": (255, 235, 181),
    "CORE_TOXINA":  (234, 255, 208),
    "CORE_NEVASCA": (255, 255, 255),

    # Reflexo / brilho do olho
    "PUPIL": (255, 255, 255),
}

# Paletas completas por ataque — espelham o JS
ATTACK_PALETTES: dict[str, dict[str, Tuple[int, int, int]]] = {
    "inferno": {
        "core":         (255, 235, 181),
        "mid":          (255, 140, 0),
        "outer":        (209, 32, 0),
        "eye_bg":       C["EYE_BG_INFERNO"],
        "eye_iris":     C["EYE_IRIS_INFERNO"],
        "body_outline": (61, 20, 0),
        "body_main":    (94, 71, 62),
        "body_dark":    (66, 48, 42),
        "body_light":   (138, 108, 98),
        "thruster_1":   (255, 235, 181),
        "thruster_2":   (255, 140, 0),
        "thruster_3":   (209, 32, 0),
    },
    "toxina": {
        "core":         (234, 255, 208),
        "mid":          (57, 255, 20),
        "outer":        (0, 128, 0),
        "eye_bg":       C["EYE_BG_TOXINA"],
        "eye_iris":     C["EYE_IRIS_TOXINA"],
        "body_outline": (13, 46, 13),
        "body_main":    (71, 99, 58),
        "body_dark":    (48, 66, 38),
        "body_light":   (122, 140, 99),
        "thruster_1":   (234, 255, 208),
        "thruster_2":   (57, 255, 20),
        "thruster_3":   (0, 128, 0),
    },
    "nevasca": {
        "core":         (255, 255, 255),
        "mid":          (138, 226, 255),
        "outer":        (0, 85, 255),
        "eye_bg":       C["EYE_BG_NEVASCA"],
        "eye_iris":     C["EYE_IRIS_NEVASCA"],
        "body_outline": (0, 26, 51),
        "body_main":    (77, 110, 140),
        "body_dark":    (43, 74, 105),
        "body_light":   (140, 168, 196),
        "thruster_1":   (255, 255, 255),
        "thruster_2":   (138, 226, 255),
        "thruster_3":   (0, 85, 255),
    },
}

# Cor neutra do propulsor (fora de ataque)
THRUSTER_NEUTRAL: tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]] = (
    (255, 255, 255),    # tb-1
    (92, 225, 230),     # tb-2
    (0, 119, 194),      # tb-3
)