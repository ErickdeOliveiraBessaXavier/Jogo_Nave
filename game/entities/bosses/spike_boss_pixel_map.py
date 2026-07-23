from typing import Tuple

# Spike Boss Pixel Map - Design: Máscara metálica com formato trapezoidal / chifres
# Camadas:
# Base/Corpo: Uma estrutura metálica robusta (tons de cinza/chumbo ou vermelho no frenzy)
# Chifres: Estruturas pontiagudas laterais
# Rosto/Olhos: Região central vazada onde os olhos brilham
# Boca/Núcleo: Abertura inferior de onde sai o laser gigante

# Dimensões aproximadas: 18x14 pixels (cada pixel será escalado)
# fmt: off
PIXEL_MAP: list[list[str | None]] = [
    # Topo chifres
    [None, None, "A", "A", None, None, None, None, None, None, None, None, None, None, "A", "A", None, None],
    [None, "A", "C", "D", "A", None, None, None, None, None, None, None, None, "A", "D", "C", "A", None],
    ["A", "C", "E", "F", "D", "A", "A", "A", "A", "A", "A", "A", "A", "A", "D", "F", "E", "C", "A"],
    ["A", "E", "G", "F", "D", "A", "C", "C", "C", "C", "C", "C", "C", "A", "D", "F", "G", "E", "A"],
    # Testa
    ["A", "G", "G", "F", "D", "A", "E", "F", "F", "F", "F", "F", "E", "A", "D", "F", "G", "G", "A"],
    ["A", "D", "D", "D", "C", "A", "F", "H", "H", "H", "H", "H", "F", "A", "C", "D", "D", "D", "A"],
    # Olhos (espaço reservado para render procedural, desenhados nas colunas 5-7 e 10-12)
    ["A", "C", "C", "C", "C", "A", "F", "H", "H", "H", "H", "H", "F", "A", "C", "C", "C", "C", "A"],
    ["A", "C", "B", "B", "C", "A", "F", "F", "F", "F", "F", "F", "F", "A", "C", "B", "B", "C", "A"],
    # Bochechas
    [None, "A", "C", "B", "C", "A", "E", "E", "E", "E", "E", "E", "E", "A", "C", "B", "C", "A", None],
    [None, "A", "C", "C", "C", "A", "D", "D", "D", "D", "D", "D", "D", "A", "C", "C", "C", "A", None],
    # Boca/Núcleo (abertura)
    [None, None, "A", "C", "C", "A", "C", "B", "B", "B", "B", "B", "C", "A", "C", "C", "A", None, None],
    [None, None, "A", "C", "C", "A", "B", "M", "M", "M", "M", "M", "B", "A", "C", "C", "A", None, None],
    [None, None, None, "A", "A", "A", "B", "M", "M", "M", "M", "M", "B", "A", "A", "A", None, None, None],
    [None, None, None, None, None, "A", "A", "B", "B", "B", "B", "B", "A", "A", None, None, None, None, None],
]
# fmt: on

PIXEL_ROWS = len(PIXEL_MAP)  # 14
PIXEL_COLS = len(PIXEL_MAP[0])  # 18

# Cores base (Normal)
COLORS_NORMAL: dict[str, Tuple[int, int, int]] = {
    "A": (30, 30, 40),      # Contorno escuro
    "B": (50, 50, 70),      # Sombra interna / Boca base
    "C": (80, 80, 120),     # Corpo base
    "D": (100, 100, 150),   # Corpo luz 1
    "E": (130, 130, 180),   # Corpo luz 2
    "F": (160, 160, 210),   # Highlight
    "G": (200, 200, 240),   # Brilho forte chifre
    "H": (180, 180, 230),   # Testa highlight
    "M": (20, 20, 30),      # Interior boca (vazio)
}

# Cores base (Frenzy)
COLORS_FRENZY: dict[str, Tuple[int, int, int]] = {
    "A": (40, 10, 10),      # Contorno escuro (avermelhado)
    "B": (80, 20, 20),      # Sombra interna
    "C": (140, 30, 30),     # Corpo base (vermelho escuro)
    "D": (180, 50, 50),     # Corpo luz 1
    "E": (220, 70, 70),     # Corpo luz 2
    "F": (250, 100, 100),   # Highlight
    "G": (255, 150, 150),   # Brilho forte chifre
    "H": (255, 120, 120),   # Testa highlight
    "M": (40, 0, 0),        # Interior boca avermelhado
}

# Cores base (Telegraph - Medo)
COLORS_TELEGRAPH: dict[str, Tuple[int, int, int]] = {
    "A": (50, 0, 0),
    "B": (100, 0, 0),
    "C": (160, 0, 0),
    "D": (200, 0, 0),
    "E": (230, 0, 0),
    "F": (255, 50, 50),
    "G": (255, 100, 100),
    "H": (255, 80, 80),
    "M": (20, 0, 0),
}

# Configurações do Olho
EYE_ROW = 6
EYE_COL_LEFT = 3
EYE_COL_RIGHT = 13
EYE_WIDTH = 3
EYE_HEIGHT = 2

EYE_COLORS: dict[str, Tuple[int, int, int]] = {
    "NORMAL_BG": (0, 0, 0),
    "NORMAL_IRIS": (0, 255, 255),
    "FRENZY_BG": (50, 0, 0),
    "FRENZY_IRIS": (255, 255, 0),
    "TELEGRAPH_BG": (0, 0, 0),
    "TELEGRAPH_CLOSED": (0, 0, 0), # Quando está com medo, os olhos fecham
}
