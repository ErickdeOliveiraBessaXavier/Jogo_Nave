from __future__ import annotations

import math
from typing import List

import pygame

from .upgrades import UpgradeType

# Keybindings padrão para os slots de upgrade
DEFAULT_KEYBINDINGS: List[int] = [
    pygame.K_1,
    pygame.K_2,
    pygame.K_3,
    pygame.K_4,
    pygame.K_5,
    pygame.K_6,
    pygame.K_7,
    pygame.K_8,
    pygame.K_9,
    pygame.K_0,
    pygame.K_MINUS,
    pygame.K_EQUALS,
]

# Quantidade de slots de aprimoramentos ativos
UPGRADE_SLOT_COUNT: int = 8

# Sistema de desbloqueio de slots com estrelas
INITIAL_UNLOCKED_SLOTS = 2  # Slots inicialmente desbloqueados
SLOT_UNLOCK_COSTS = [
    0,  # Slot 1 - gratuito
    0,  # Slot 2 - gratuito
    3,  # Slot 3 - custa 3 estrelas
    5,  # Slot 4 - custa 5 estrelas
    10,  # Slot 5 - custa 10 estrelas
    20,  # Slot 6 - custa 20 estrelas
    35,  # Slot 7 - custa 35 estrelas
    50,  # Slot 8 - custa 50 estrelas
]
# Quais upgrades vêm desbloqueados por padrão (MVP)
DEFAULT_UNLOCKED: List[UpgradeType] = [
    UpgradeType.SHIELD_BURST,
    UpgradeType.HEAL,
    UpgradeType.EMP,
    UpgradeType.HOMING_SHOT,
    UpgradeType.LASER_SHOT,
    UpgradeType.EXPLOSIVE_SHOT,
    UpgradeType.GIANT_SHOT,
    UpgradeType.AIR_STRIKE,
    UpgradeType.BLACK_HOLE,
    UpgradeType.CANNON_TOWER,
    UpgradeType.BLINK_DASH,
    UpgradeType.GRAVITY_BOMB,
    UpgradeType.CHAIN_LIGHTNING,
    UpgradeType.ORBITAL_SHIELD,
    UpgradeType.PLASMA_BEAM,
    UpgradeType.WINGMAN,
    UpgradeType.BERSERK,
    UpgradeType.COOP_LINK,
    UpgradeType.IMPLOSION_SHOT,
]

# Parâmetros de balanceamento do EMP (tempo e intensidade)
EMP_SLOW_FACTOR: float = 0.35  # Mantém 35% da velocidade (mais lento)
EMP_BASE_DURATION: float = 10.0  # Tempo que o EMP fica ativo
EMP_LINGER_DURATION: float = (
    8.0  # Tempo que o slow persiste após ser atingido pela onda
)

# Parâmetros de balanceamento do Tiro Teleguiado
HOMING_SPEED_PENALTY: float = 0.75  # Nave fica a 75% da velocidade normal
HOMING_FIRE_RATE_PENALTY: float = (
    1.2  # Leva 20% mais tempo para atirar (cadência reduzida)
)
HOMING_DAMAGE_MULTIPLIER: float = 1.5  # Tiros teleguiados causam 50% mais dano direto

# Parâmetros de balanceamento do Laser Shot
LASER_SHOT_DAMAGE: int = 80  # Dano do laser disparado pelas orbes

# Parâmetros de balanceamento do Tiro Explosivo
EXPLOSIVE_BULLET_DAMAGE: int = 30  # Dano aplicado a cada inimigo na área
EXPLOSIVE_BULLET_RADIUS: int = 60  # Raio da explosão em pixels

# Parâmetros do Tiro Gigante (Giant Shot)
GIANT_SHOT_SIZE_MULTIPLIER: float = 3.0  # Balas 3x maiores (escala visual + hitbox)

# Quanto o Giant Shot puxa a PROPORÇÃO do tiro para o quadrado: 0.0 preserva a
# proporção da nave (um tiro fino como o do padrão, 3x10, vira só uma barra
# comprida de 9x30 — cresce nos dois eixos, mas continua lendo como "ficou mais
# largo") e 1.0 vira um quadrado perfeito. A ÁREA é `mult²` vezes a original em
# QUALQUER valor — só a forma muda —, então mexer aqui é escolha estética e não
# um buff disfarçado. Naves de tiro já quadrado (magneto, engenheiro) ignoram.
GIANT_SHOT_SQUARENESS: float = 0.5

# Giant Shot também acelera o projétil levemente: o tiro grande "empurra" mais
# rápido. Só vale enquanto o upgrade dura — `Config.BULLET_SPEED` (o tiro
# normal, todas as naves) fica intacto.
GIANT_SHOT_SPEED_MULTIPLIER: float = 1.15


def giant_visual_scale(size_multiplier: float) -> float:
    """Fator visual (sprite do tiro e efeito de impacto) sob o Giant Shot.

    O hitbox já cresce pelo `size_multiplier` cheio (~3x via
    `GIANT_SHOT_SIZE_MULTIPLIER`). Sprites pequenas — o '+' do teleguiado, a
    granada do explosivo, o burst de impacto — ficariam exageradas nesse fator,
    então tomamos a raiz quadrada: crescem de forma perceptível e coerente com o
    hitbox maior, sem virar um borrão que engole a tela. `1.0` (sem Giant Shot)
    passa reto — fonte única para bala e impacto não divergirem.
    """
    if size_multiplier <= 1.0:
        return 1.0
    return math.sqrt(size_multiplier)

# Parâmetros de balanceamento da Implosão (sucção no ponto de impacto)
#
# ATENÇÃO: em pixels do DESIGN BASE (1280×720); passa por `scale.scaled()` na
# hora do uso (§12) — nunca consuma cru. Sem isso a área encolhe em fração de
# tela conforme a resolução lógica sobe, e o upgrade fica mais fraco para quem
# joga em resolução maior. Fonte única: `implosion_pulse.suction_radius`.
#
# Raio PEQUENO de propósito: pega o alvo atingido e a vizinhança imediata, não
# varre a tela. Para comparar, a explosão do tiro explosivo tem 60px.
IMPLOSION_RADIUS: float = 82.5
# Dano por tique dentro da área, e o intervalo entre tiques (4 HP/s).
#
# Pequeno de propósito: em 2s de zona são ~8 de dano, menos que UMA bala (10).
# O upgrade continua sendo de controle — o dano é pressão de fundo sobre o grupo
# freado, não a forma de matar.
#
# O cooldown do tique vive no INIMIGO, não no pulso (`implosion_damage_cd`).
# Sob fogo sustentado há dezenas de pulsos vivos ao mesmo tempo; com o cooldown
# por pulso, cada um tiquetaria por conta própria e o dano escalaria com a
# cadência de tiro em vez de ficar no teto abaixo. Referência do projeto:
# `IcePoisonZone` faz 1 dano a cada 0.2s, mas é zona única e não empilha.
IMPLOSION_DAMAGE: int = 1
IMPLOSION_DAMAGE_INTERVAL: float = 0.25
# Duração da sucção: vale para o círculo E para o deslocamento dos inimigos, que
# são a mesma curva (ver `ImplosionPulse._eased`). 2s é tempo de o jogador VER a
# implosão acontecer — a versão anterior, de 0,18s, cumpria a física mas passava
# rápido demais para registrar como evento.
IMPLOSION_DURATION: float = 2.0
# Abertura do círculo: ele cresce de 0 ao raio cheio e ganha opacidade neste
# tempo, em vez de aparecer pronto. Sai de DENTRO da duração (7,5% dela), não
# se soma a ela.
#
# Existe porque o ease-in deixa o anel quase parado no primeiro segundo (aos
# 0,5s só 1,6% do encolhimento aconteceu): sem abertura, o jogador via um pop
# seguido de um anel estático, e o pop ficava ainda mais evidente por não ter
# movimento nenhum em volta para disfarçá-lo. Acima de ~0,25s a abertura passa a
# competir com a implosão e o efeito lê como uma onda que EXPLODE antes de sugar
# — o oposto do que ele comunica.
IMPLOSION_OPEN_TIME: float = 0.15
# Lentidão deixada pela sucção: 0.25 = o inimigo anda a 1/4 da velocidade (75%
# mais lento).
IMPLOSION_SLOW_FACTOR: float = 0.25
# Quanto o debuff SOBREVIVE à saída da zona.
#
# É o valor cravado no timer a cada frame em que o inimigo está dentro, então
# ele fica lento a zona inteira e sai com estes 3s pela frente — que é o que
# "3 segundos após o término" quer dizer. Não somar a duração da zona aqui: o
# timer é REPOSTO por frame, não aplicado uma vez, e somar daria 5s de sobrevida.
IMPLOSION_SLOW_LINGER: float = 3.0

# Parâmetros de balanceamento do Air Strike
AIR_STRIKE_BOMB_COUNT: int = 20  # Bombas por ativação da ultimate
AIR_STRIKE_BOMB_DAMAGE: int = 100
AIR_STRIKE_BOMB_RADIUS: float = 80.0
AIR_STRIKE_BOMB_FALL_SPEED: float = 800.0
AIR_STRIKE_EXPLOSION_DURATION: float = 0.5  # segundos de animação/janela de dano
# Margem de segurança das bordas = raio + folga, para o círculo de explosão INTEIRO
# caber na tela em qualquer lado. A margem antiga (40/60px) era menor que o raio
# (80px), então o blast dos impactos junto às bordas transbordava — horizontal e
# verticalmente. Fonte única do clamp (gerador de alvos, entity_manager e a bomba).
AIR_STRIKE_SCREEN_MARGIN: float = AIR_STRIKE_BOMB_RADIUS + 12.0

# Parâmetros de balanceamento da Cannon Tower
CANNON_MINE_DAMAGE: int = 120
CANNON_MINE_RADIUS: float = 70.0

# Futuro: overrides por dificuldade ou progressão
# Example structure (não usado no MVP):
# PER_UPGRADE_BALANCE: dict[UpgradeType, dict[str, float | int]] = {
#     UpgradeType.SHIELD_BURST: {"cooldown": 45.0, "duration": 7.0},
# }
