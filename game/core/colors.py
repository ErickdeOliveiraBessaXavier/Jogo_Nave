from typing import Tuple

Color = Tuple[int, int, int]

BLACK: Color = (0, 0, 0)
WHITE: Color = (255, 255, 255)
RED: Color = (255, 60, 60)
BRIGHT_RED: Color = (255, 120, 120)
YELLOW: Color = (255, 230, 120)
BLUE: Color = (90, 150, 255)
GREEN: Color = (80, 220, 120)
BRIGHT_GREEN: Color = (120, 255, 160)
ORANGE: Color = (255, 165, 0)
DARK_RED: Color = (150, 50, 50)
LIGHT_ORANGE: Color = (255, 200, 100)
CYAN: Color = (0, 255, 255)
MAGENTA: Color = (255, 0, 255)
GRAY: Color = (128, 128, 128)
LIGHT_BLUE: Color = (173, 216, 230)
LIGHT_GRAY: Color = (192, 192, 192)
DARK_GRAY: Color = (64, 64, 64)
BRIGHT_GRAY: Color = (180, 180, 180)
# Linha de mira do boss. Azul para acompanhar a rampa de energia dele
# (`bosses/boss_pixel_map.ENERGY_*`) — era vermelha, a única cor quente que
# sobrava num boss de aço azulado. Só o boss "normal" consome esta constante.
BOSS_AIM_LINE: Color = (110, 225, 255)
GUIDED_METEOR_GREEN: Color = (50, 255, 50)  # Verde brilhante para meteoros teleguiados
PURPLE: Color = (200, 0, 255)

# Paleta Monocromática
MONO_WHITE: Color = (245, 245, 245)
MONO_LIGHT_GRAY: Color = (200, 200, 200)
MONO_MEDIUM_GRAY: Color = (128, 128, 128)
MONO_DARK_GRAY: Color = (64, 64, 64)
MONO_VERY_DARK_GRAY: Color = (32, 32, 32)

# Paleta Customizada
CUSTOM_PURPLE: Color = (70, 65, 217)  # #4641D9
CUSTOM_DARK_BG: Color = (21, 28, 38)  # #151C26
CUSTOM_GOLD: Color = (242, 182, 109)  # #F2B66D

# Paleta Neon Retro
NEON_PINK: Color = (255, 0, 127)
NEON_CYAN: Color = (0, 255, 255)
NEON_PURPLE: Color = (188, 0, 255)

# Cores do Alien Bullet
ALIEN_BULLET_GREEN_1: Color = (37, 217, 166)  # #25D9A6
ALIEN_BULLET_GREEN_2: Color = (115, 255, 215)  # #4ED94A

# Paleta Arcade Clássica
ARCADE_YELLOW: Color = (255, 255, 0)
ARCADE_ORANGE: Color = (255, 128, 0)

# Cores dos power-ups.
#
# A paleta é separada perceptualmente: nenhum par fica abaixo de ΔE 40 em
# CIELAB (travado por `tests/test_powerup_colors.py`). Antes cinco pares
# ficavam abaixo de 25 e dois eram praticamente o mesmo tom na tela —
# `cooldown_haste` × `chain_shot` diferiam em 20 num único canal (ΔE 13).
#
# As sete primeiras carregam significado estabelecido e não se mexe; as demais
# eram arbitrárias e foram reposicionadas nos vãos livres do espaço de cor.
POWERUP_LIFE: Color = (255, 50, 50)  # vermelho
POWERUP_SHIELD: Color = (50, 50, 255)  # azul
POWERUP_DOUBLE_SHOT: Color = (50, 255, 50)  # verde
POWERUP_SPEED: Color = (255, 255, 50)  # amarelo
POWERUP_SCORE: Color = (255, 50, 255)  # magenta
POWERUP_RAINBOW: Color = (255, 255, 255)  # branco
POWERUP_DAMAGE_BOOST: Color = (255, 140, 0)  # laranja
POWERUP_PIERCING_SHOT: Color = (217, 43, 130)  # rosa-pink
POWERUP_MINI_SHIPS: Color = (217, 184, 87)  # dourado
POWERUP_COOLDOWN_HASTE: Color = (0, 130, 217)  # azul-médio
POWERUP_TIME_STOP: Color = (145, 87, 217)  # roxo
POWERUP_CHAIN_SHOT: Color = (0, 195, 217)  # turquesa
POWERUP_REPULSION_SHIELD: Color = (102, 255, 178)  # verde-menta
POWERUP_SPREAD_SHOT: Color = (255, 150, 140)  # coral

# Fonte ÚNICA da cor de cada power-up. Consumida pelo pickup no mundo
# (`entities/pickups/powerup.py`) e pelo HUD (`render/game_renderer.py`), que
# antes tinham tabelas independentes: o pickup usava as constantes acima e o
# HUD usava as cores genéricas da paleta. O mesmo power-up aparecia em duas
# cores na mesma tela — `time_stop` era (180,120,255) no chão e PURPLE
# (200,0,255) no HUD — e `piercing_shot` ficava indistinguível dele no HUD
# porque os dois caíam em PURPLE.
#
# As chaves são os valores de `PowerUpType` (`core/config.py`). Power-up novo
# entra AQUI e os dois lados o pegam de graça; esquecer o registro faz cair no
# branco do fallback, que foi o que aconteceu com `chain_shot` e
# `repulsion_shield` — tinham constante definida e nenhum leitor.
POWERUP_COLORS: dict[str, Color] = {
    "life": POWERUP_LIFE,
    "shield": POWERUP_SHIELD,
    "double_shot": POWERUP_DOUBLE_SHOT,
    "spread_shot": POWERUP_SPREAD_SHOT,
    "speed": POWERUP_SPEED,
    "score": POWERUP_SCORE,
    "piercing_shot": POWERUP_PIERCING_SHOT,
    "mini_ships": POWERUP_MINI_SHIPS,
    "rainbow": POWERUP_RAINBOW,
    "cooldown_haste": POWERUP_COOLDOWN_HASTE,
    "time_stop": POWERUP_TIME_STOP,
    "damage_boost": POWERUP_DAMAGE_BOOST,
    "chain_shot": POWERUP_CHAIN_SHOT,
    "repulsion_shield": POWERUP_REPULSION_SHIELD,
}

RAINBOW_COLORS = [
    (255, 0, 0),  # vermelho
    (255, 127, 0),  # laranja
    (255, 255, 0),  # amarelo
    (0, 255, 0),  # verde
    (0, 0, 255),  # azul
    (75, 0, 130),  # índigo
    (148, 0, 211),  # violeta
]

# Cores das partículas do Black Hole (disco de acreção)
BLACK_HOLE_PARTICLE_COLORS = [
    (255, 107, 53),  # laranja
    (247, 147, 30),  # laranja claro
    (255, 215, 0),  # dourado
    (255, 69, 0),  # vermelho alaranjado
    (255, 140, 0),  # laranja escuro
    (255, 170, 0),  # amarelo alaranjado
]
