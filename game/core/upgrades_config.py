from __future__ import annotations

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
