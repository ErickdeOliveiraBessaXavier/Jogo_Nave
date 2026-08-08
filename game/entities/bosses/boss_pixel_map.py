from typing import Tuple

# Boss Pixel Map - Design: Nave-mãe massiva, chassi reforçado com núcleo central de energia.
# A arma (BossCannon) é renderizada separadamente por cima da sprite para poder rotacionar.

# Dimensões: 18x14 pixels
# fmt: off
PIXEL_MAP: list[list[str | None]] = [
    [None, None, None, "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", "D", None, None, None],
    [None, None, "D", "C", "C", "E", "E", "E", "E", "E", "E", "E", "E", "C", "C", "D", None, None],
    [None, "D", "C", "B", "C", "C", "C", "C", "C", "C", "C", "C", "C", "C", "B", "C", "D", None],
    ["D", "C", "B", "A", "B", "C", "F", "F", "F", "F", "F", "F", "C", "B", "A", "B", "C", "D"],
    ["D", "C", "B", "B", "B", "C", "F", "G", "H", "H", "G", "F", "C", "B", "B", "B", "C", "D"],
    ["D", "E", "C", "C", "C", "C", "F", "H", "H", "H", "H", "F", "C", "C", "C", "C", "E", "D"],
    ["D", "E", "F", "F", "E", "C", "F", "G", "H", "H", "G", "F", "C", "E", "F", "F", "E", "D"],
    ["D", "E", "F", "F", "E", "C", "C", "F", "F", "F", "F", "C", "C", "E", "F", "F", "E", "D"],
    ["D", "C", "E", "E", "C", "C", "C", "C", "C", "C", "C", "C", "C", "C", "E", "E", "C", "D"],
    ["D", "C", "C", "C", "C", "B", "B", "B", "I", "I", "B", "B", "B", "C", "C", "C", "C", "D"],
    [None, "D", "C", "C", "B", "A", "A", "B", "I", "I", "B", "A", "A", "B", "C", "C", "D", None],
    [None, None, "D", "C", "C", "B", "B", "I", "M", "M", "I", "B", "B", "C", "C", "D", None, None],
    [None, None, None, "D", "D", "C", "C", "I", "M", "M", "I", "C", "C", "D", "D", None, None, None],
    [None, None, None, None, None, "D", "D", "I", "M", "M", "I", "D", "D", None, None, None, None, None],
]
# fmt: on

PIXEL_ROWS = len(PIXEL_MAP)  # 14
PIXEL_COLS = len(PIXEL_MAP[0])  # 18

# ── Rampa de ENERGIA do boss ────────────────────────────────────────────────
#
# Fonte ÚNICA de todo acento luminoso do boss: núcleo do chassi, glow e ponta do
# canhão, anéis de carga, partículas de carga/dissipação, linha de mira, laser e
# o núcleo dos quadrados orbitais. Quem precisa de "energia acesa" importa daqui
# em vez de cravar a cor no ponto do desenho — era assim que a identidade se
# perdia: cada arquivo escolhia o próprio quente (laranja no canhão, amarelo nos
# anéis, vermelho no laser) sobre um chassi que sempre foi de aço AZULADO.
#
# Azul e não quente porque o azul já era a cor mais marcante do boss (rampa
# C/E/F abaixo) e porque laranja/vermelho são a linguagem de EXPLOSÃO no jogo —
# a arma do boss competia com o feedback de dano em vez de identificar o dono.
#
# Os valores de CORE e HOT são exatamente os que `BossSquare` já usava: os
# orbitais eram o único elemento que acertava a identidade, então viraram a
# âncora dela em vez de mais uma exceção.
ENERGY_DEEP: Tuple[int, int, int] = (0, 70, 140)     # azul profundo (glow externo)
ENERGY_CORE: Tuple[int, int, int] = (0, 210, 255)    # azul-ciano: energia acesa
ENERGY_GLOW: Tuple[int, int, int] = (110, 225, 255)  # realce intermediário
ENERGY_HOT: Tuple[int, int, int] = (190, 250, 255)   # branco-azulado incandescente

# Cores base (Normal)
COLORS_NORMAL: dict[str, Tuple[int, int, int]] = {
    "A": (30, 40, 50),      # Detalhe profundo
    "B": (50, 65, 80),      # Sombra interna
    "C": (80, 100, 120),    # Corpo base (Aço azulado)
    "D": (20, 25, 35),      # Contorno escuro
    "E": (110, 130, 150),   # Corpo luz 1
    "F": (150, 170, 190),   # Corpo luz 2 / Reflexos
    "G": (0, 150, 225),     # Núcleo borda (energia)
    "H": (190, 250, 255),   # Núcleo centro (incandescente)
    "I": (62, 70, 82),      # Base do canhão (cinza puxado ao azul do chassi)
    "M": (30, 34, 42),      # Recuo do canhão
}

# Cores base (Frenzy)
#
# O CASCO corrompe para vermelho — é o sinal de que o boss enfureceu, e vale a
# pena manter porque é informação de jogo, não decoração. A ENERGIA (G/H) NÃO
# corrompe: ela intensifica, seguindo a mesma regra que `BossSquare` já
# aplicava aos orbitais. O contraste casco quente + energia fria é o que mantém
# a arma legível como "do mesmo boss" nos dois estados.
COLORS_FRENZY: dict[str, Tuple[int, int, int]] = {
    "A": (50, 10, 20),      # Detalhe profundo avermelhado
    "B": (80, 20, 30),      # Sombra interna avermelhada
    "C": (140, 40, 50),     # Corpo base (Aço corrompido)
    "D": (35, 10, 15),      # Contorno escuro
    "E": (180, 60, 70),     # Corpo luz 1
    "F": (220, 90, 100),    # Corpo luz 2 / Reflexos
    "G": (0, 190, 255),     # Núcleo borda (energia intensificada)
    "H": (225, 252, 255),   # Núcleo centro (quase branco)
    "I": (80, 30, 30),      # Base do canhão
    "M": (40, 15, 15),      # Recuo do canhão
}

# Atalhos para cores de sistema (projéteis, trilhas, etc)
# Usam as chaves do dicionário para facilitar o lerp
PROJECTILE_COLOR_KEY = "G"
PROJECTILE_HIGHLIGHT_KEY = "H"
TRAIL_COLOR_KEY = "C"
