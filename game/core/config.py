from dataclasses import dataclass
from typing import Tuple
from enum import Enum


class PowerUpType(Enum):
    LIFE = "life"
    SHIELD = "shield"
    DOUBLE_SHOT = "double_shot"
    SPEED = "speed"
    SCORE = "score"
    RAINBOW = "rainbow"
    PIERCING_SHOT = "piercing_shot"
    MINI_SHIPS = "mini_ships"


@dataclass(frozen=True)
class Config:
    # ========================================
    # DISPLAY & PERFORMANCE SETTINGS
    # ========================================
    FULLSCREEN: bool = True  # True para fullscreen, False para janela
    SCREEN_WIDTH: int = 1600  # Maior = elementos menores (era 1000)
    SCREEN_HEIGHT: int = 900  # Maior = elementos menores (era 600)
    FPS: int = 60

    # ========================================
    # BASIC GAMEPLAY SETTINGS
    # ========================================
    INITIAL_LIVES: int = 3
    PREPARATION_TIME: float = 3.0  # seconds
    SHOOT_COOLDOWN: float = 0.20  # Tempo entre tiros quando segura a tecla

    # ========================================
    # ENTITY MOVEMENT SPEEDS (pixels/second)
    # ========================================
    SHIP_SPEED: float = 300.0
    BULLET_SPEED: float = 480.0
    FAST_METEOR_SPEED: float = 320.0  # meteoros pequenos
    SLOW_METEOR_SPEED: float = 25.0  # meteoros grandes
    POWERUP_SPEED: int = 100

    # ========================================
    # METEOR SYSTEM
    # ========================================
    # Basic meteor settings
    MIN_METEOR_SIZE: int = 12
    MAX_METEOR_SIZE: int = 55
    METEOR_SPAWN_EVERY: float = 0.58  # seconds
    DIAGONAL_CHANCE: float = 2

    # Fragmentation system
    FRAGMENT_MIN_SIZE: int = 12
    FRAGMENT_SPLIT_THRESHOLD: int = 28
    FRAGMENT_COUNT_RANGE: Tuple[int, int] = (2, 5)
    FRAGMENT_SPEED_BOOST: float = 1.25
    FRAGMENT_SPREAD: float = 260.0  # degrees

    # Guided meteors
    GUIDED_METEOR_SPAWN_CHANCE: float = 0.5  # Chance no modo frenzy (50%)
    GUIDED_METEOR_NORMAL_PHASES_CHANCE: float = 0.1  # Chance nas fases normais (10%)
    GUIDED_METEOR_MAX_SPEED: float = 250.0
    GUIDED_METEOR_ACCELERATION: float = 100.0
    GUIDED_METEOR_TURN_RATE: float = 3.0  # rad/s

    # ========================================
    # POWER-UP SYSTEM
    # ========================================
    # Spawn settings
    POWERUP_SPAWN_INTERVAL: Tuple[float, float] = (15.0, 25.0)
    POWERUP_SIZE: int = 48
    POWERUP_SCORE_BONUS: int = 500

    # Effect durations (seconds)
    SHIELD_DURATION: float = 8.0
    DOUBLE_SHOT_DURATION: float = 10.0
    SPEED_BOOST_DURATION: float = 8.0
    RAINBOW_DURATION: float = 15.0
    PIERCING_SHOT_DURATION: float = 7.0
    MINI_SHIPS_DURATION: float = 25.0
    SPEED_ATTACK_MULTIPLIER: float = 2.0  # Multiplicador de velocidade de ataque
    PIERCING_SHOT_ATTACK_SPEED_MULTIPLIER: float = 1.5

    # Rarity system - chances devem somar 1.0
    POWERUP_RARITY_CHANCES = {
        PowerUpType.SHIELD: 0.20,  # 20% - Comum
        PowerUpType.DOUBLE_SHOT: 0.25,  # 25% - Comum
        PowerUpType.SPEED: 0.15,  # 15% - Incomum
        PowerUpType.PIERCING_SHOT: 0.15,  # 15% - Raro
        PowerUpType.MINI_SHIPS: 0.10,  # 10% - Raro
        PowerUpType.LIFE: 0.10,  # 10% - Raro
        PowerUpType.SCORE: 0.04,  # 4% - Épico
        PowerUpType.RAINBOW: 0.01,  # 1% - Lendário
    }

    # ========================================
    # SCORING SYSTEM
    # ========================================
    BASE_POINTS: int = 5
    SIZE_BONUS_MULTIPLIER: float = 1.2
    BOSS_DEFEAT_SCORE: int = 10000

    # ========================================
    # TIMING & TRANSITIONS
    # ========================================
    INVULN_TIME: float = 3.0
    LEVEL_TRANSITION_DELAY: float = 2.0
    INITIAL_GAME_DELAY: float = 5.0

    # Boss warning sequence
    BOSS_PRE_WARNING_DELAY: float = 5.0  # Delay antes do warning
    BOSS_WARNING_DURATION: float = 5.0  # Duração do warning ativo
    BOSS_POST_WARNING_DELAY: float = 3.0  # Delay após warning antes do boss

    # Music transition settings for boss warning
    BOSS_MUSIC_FADE_OUT_START: float = 3.0  # Inicia fade-out 3s antes do warning
    BOSS_MUSIC_FADE_OUT_DURATION: float = 2.0  # Tempo do fade-out da música normal
    # Calculado dinamicamente: warning + delay pós-warning
    BOSS_MUSIC_SILENCE_DURATION: float = BOSS_WARNING_DURATION + BOSS_POST_WARNING_DELAY  # 5.0 + 3.0 = 8.0
    BOSS_MUSIC_FADE_IN_DURATION: float = 3.0  # Tempo do fade-in da música do boss
    BOSS_MUSIC_FADE_IN_START_DELAY: float = (
        1.0  # Delay antes do fade-in começar (quando boss aparece)
    )

    # ========================================
    # VISUAL EFFECTS & ANIMATIONS
    # ========================================
    WARP_SPEED_MULTIPLIER: float = 5.0

    # Explosion effects
    EXPLOSION_DURATION: float = 0.8
    BOSS_EXPLOSION_DURATION: float = 5.0
    BOSS_EXPLOSION_COUNT: int = 12
    BOSS_EXPLOSION_RADIUS: int = 60
    BOSS_EXPLOSION_SMALL_SIZE: int = 40
    BOSS_EXPLOSION_LARGE_SIZE: int = 60

    # Screen shake effects
    SCREEN_SHAKE_NORMAL: int = 10
    SCREEN_SHAKE_GAME_OVER: int = 15
    SCREEN_SHAKE_BOSS_DEATH: int = 25
    SCREEN_SHAKE_BOSS_DEATH_DURATION: float = 2.5

    # Game over effects
    GAME_OVER_FADE_DURATION: float = 2.0
    GAME_OVER_RESTART_DELAY: float = 1.5
    GAME_OVER_OVERLAY_ALPHA: int = 200  # 0-255

    # ========================================
    # BOSS SYSTEM
    # ========================================
    # Basic boss stats
    BOSS_HEALTH: int = 1000
    BOSS_FRENZY_THRESHOLD: float = 0.5
    BOSS_ENTRY_SPEED: float = 30.0
    BOSS_ENTRY_SHAKE_DURATION: float = 4.0

    # ========================================
    # SPIKE BOSS SYSTEM
    # ========================================
    # Basic stats
    SPIKE_BOSS_HEALTH: int = 1200
    SPIKE_BOSS_FRENZY_THRESHOLD: float = 0.5
    SPIKE_BOSS_ENTRY_SPEED: float = 25.0
    SPIKE_BOSS_SPEED: float = 80.0  # Velocidade horizontal normal
    SPIKE_BOSS_FRENZY_SPEED: float = 120.0  # Velocidade no frenzy
    SPIKE_BOSS_FRENZY_SHAKE_DURATION: float = 3.0
    
    # Proximity attack (quando jogador se aproxima demais)
    SPIKE_BOSS_PROXIMITY_DISTANCE: float = 150.0  # Distância mínima para ativar
    SPIKE_BOSS_PROXIMITY_COOLDOWN: float = 3.0  # Tempo entre ataques de proximidade
    SPIKE_BOSS_PROXIMITY_TELEGRAPH_DURATION: float = 0.4  # Duração do aviso antes do ataque
    SPIKE_BOSS_PROXIMITY_WAVE_DURATION: float = 0.6  # Duração da onda visual
    SPIKE_BOSS_PROXIMITY_WAVE_MAX_RADIUS: float = 180.0  # Raio máximo da onda
    SPIKE_BOSS_PROXIMITY_DAMAGE: int = 1  # Dano se atingir o jogador
    SPIKE_BOSS_PROXIMITY_WARNING_COLOR_NORMAL: Tuple[int, int, int] = (255, 255, 0)  # Amarelo (aviso)
    SPIKE_BOSS_PROXIMITY_WARNING_COLOR_FRENZY: Tuple[int, int, int] = (255, 0, 0)  # Vermelho (aviso)
    SPIKE_BOSS_PROXIMITY_WAVE_COLOR_NORMAL: Tuple[int, int, int] = (0, 255, 255)  # Ciano (onda)
    SPIKE_BOSS_PROXIMITY_WAVE_COLOR_FRENZY: Tuple[int, int, int] = (255, 0, 0)  # Vermelho (onda)
    SPIKE_BOSS_PROXIMITY_WAVE_INNER_COLOR_NORMAL: Tuple[int, int, int] = (255, 255, 255)  # Branco (centro)
    SPIKE_BOSS_PROXIMITY_WAVE_INNER_COLOR_FRENZY: Tuple[int, int, int] = (255, 255, 0)  # Amarelo (centro)

    # Mouth animation (boca abrindo e fechando)
    SPIKE_BOSS_MOUTH_CYCLE_DURATION: float = 2.0  # Duração completa do ciclo (abrir + fechar)
    SPIKE_BOSS_MOUTH_MAX_OPENING: int = 15  # Altura máxima que a boca abre
    SPIKE_BOSS_BODY_STRETCH: int = 8  # Pixels que o corpo estica quando a boca abre

    # Eye behavior (comportamento dos olhos)
    SPIKE_BOSS_EYE_TRACK_DURATION: float = 2.5  # Tempo seguindo a nave
    SPIKE_BOSS_EYE_FRENETIC_DURATION: float = 1.0  # Tempo olhando freneticamente
    SPIKE_BOSS_EYE_FRENETIC_SPEED: float = 0.15  # Velocidade da mudança frenética (segundos)

    # Attack timing
    SPIKE_BOSS_ATTACK_INTERVAL: Tuple[float, float] = (3.0, 5.0)  # Normal mode
    SPIKE_BOSS_FRENZY_ATTACK_INTERVAL: Tuple[float, float] = (1.5, 2.5)  # Frenzy mode

    # Spike spawn settings (quantidade de triângulos grudados criados por ataque)
    SPIKE_BOSS_SPIKE_COUNT: Tuple[int, int] = (3, 5)  # Quantidade normal
    SPIKE_BOSS_FRENZY_SPIKE_COUNT: Tuple[int, int] = (6, 9)  # Quantidade no frenzy

    # ========================================
    # SPIKE (PROJECTILE) SYSTEM
    # ========================================
    SPIKE_SIZE: int = 25  # Tamanho do triângulo
    SPIKE_DAMAGE: int = 1
    SPIKE_POINTS: int = 50  # Pontos ao destruir
    SPIKE_WALL_SPACING: int = 5  # Espaçamento entre triângulos na parede
    SPIKE_MAX_ATTACKING: int = 10  # Máximo de triângulos atacando simultaneamente
    
    # Sistema de ondas de ataque
    SPIKE_WAVE_MIN_SIZE: int = 3  # Mínimo de triângulos por onda
    SPIKE_WAVE_MAX_SIZE: int = 6  # Máximo de triângulos por onda
    SPIKE_WAVE_INTERVAL: float = 4.0  # Pausa entre ondas (segundos)
    SPIKE_FRENZY_WAVE_INTERVAL: float = 2.5  # Pausa entre ondas no frenzy
    
    # Comportamento de grudado na parede
    SPIKE_MIN_ATTACH_TIME: float = 1.0  # Tempo mínimo grudado antes de atacar
    SPIKE_MAX_ATTACH_TIME: float = 2.5  # Tempo máximo grudado antes de atacar
    
    # Tremor antes de soltar
    SPIKE_TREMBLE_DURATION: float = 1.0  # Duração do tremor
    SPIKE_MAX_TREMBLE: int = 5  # Intensidade máxima do tremor (pixels)
    
    # Míssil teleguiado
    SPIKE_INITIAL_SPEED: float = 50.0  # Velocidade inicial base ao soltar
    SPIKE_SPEED_VARIATION: float = 30.0  # Variação de velocidade (+/- pixels/s)
    SPIKE_ACCELERATION: float = 200.0  # Aceleração do míssil
    SPIKE_MAX_SPEED: float = 300.0  # Velocidade máxima base
    SPIKE_MAX_SPEED_VARIATION: float = 50.0  # Variação na velocidade máxima
    SPIKE_AIM_IMPRECISION: float = 100.0  # Imprecisão na mira (pixels)
    SPIKE_ROTATION_SPEED_MIN: float = 8.0  # Velocidade mínima de rotação ao voar (rad/s) - giro rápido!
    SPIKE_ROTATION_SPEED_MAX: float = 15.0  # Velocidade máxima de rotação ao voar (rad/s) - giro muito rápido!
    
    # Efeito de entrada (zoom-in)
    SPIKE_SPAWN_ANIMATION_DURATION: float = 0.4  # Duração do zoom-in (segundos)
    SPIKE_SPAWN_DELAY_MIN: float = 0.0  # Delay mínimo antes do spawn
    SPIKE_SPAWN_DELAY_MAX: float = 2.0  # Delay máximo antes do spawn
    
    # Respawn e controle de lançamento
    SPIKE_RESPAWN_TIME: float = 10.0  # Tempo para triângulo reaparecer após sair
    SPIKE_LAUNCH_COOLDOWN: float = 0.2  # Intervalo mínimo entre lançamentos dentro da onda

    # Boss movement
    BOSS_NORMAL_SPEED: float = 6.0  # Velocidade normal lateral
    BOSS_FRENZY_SPEED: float = 8.0  # Velocidade no frenzy
    BOSS_FRENZY_SHAKE_DURATION: float = 3.0

    # Boss laser system
    LASER_DISTANCE: float = 800.0
    BOSS_LASER_LIFETIME: float = 2.0
    BOSS_FRENZY_LASER_LIFETIME: float = 1.5

    # Boss attack timing
    BOSS_CALM_ATTACK_INTERVAL: Tuple[float, float] = (2.0, 5.0)
    BOSS_FRENZY_ATTACK_INTERVAL: Tuple[float, float] = (1.0, 2.0)

    # Boss attack animations - Normal mode
    BOSS_CHARGE_DURATION: float = 1.0
    BOSS_LASER_DELAY: float = 0.3

    # Boss attack animations - Frenzy mode
    BOSS_FRENZY_CHARGE_DURATION: float = 0.5
    BOSS_FRENZY_LASER_DELAY: float = 0.30

    # Boss animation speed multipliers
    BOSS_ANIMATION_SPEED_MULTIPLIER: float = 1.0
    BOSS_FRENZY_ANIMATION_SPEED_MULTIPLIER: float = 2.0

    # Boss visual effects - Normal mode
    BOSS_AIM_BLINK_INTERVAL: int = 400
    BOSS_AIM_BLINK_ON_DURATION: int = 200
    BOSS_AIM_DASH_LENGTH: int = 20
    BOSS_AIM_GAP_LENGTH: int = 25
    BOSS_CHARGE_CIRCLE_MAX_RADIUS: float = 30.0

    # Boss visual effects - Frenzy mode
    BOSS_FRENZY_AIM_BLINK_INTERVAL: int = 200
    BOSS_FRENZY_AIM_BLINK_ON_DURATION: int = 100

    # Boss meteor attacks
    BOSS_METEOR_AIM_SPREAD: float = 30.0  # Desvio normal (±30°)
    BOSS_SIDE_METEOR_AIM_SPREAD: float = 45.0  # Desvio lateral (±45°)

    # ========================================
    # FORMATION SYSTEM
    # ========================================
    # Formation spawn settings
    FORMATION_SPAWN_INTERVAL: Tuple[float, float] = (10.0, 15.0)  # Min/max tempo entre formações
    
    # Entry pattern settings - Curved path (Galaga-style)
    FORMATION_ENTRY_CURVE_AMPLITUDE: float = 150.0  # Amplitude da curva lateral (reduzida de 250)
    FORMATION_ENTRY_CURVE_FREQUENCY: float = 1.2  # Frequência da curva (mais loops)
    FORMATION_ENTRY_TIME_OFFSET: float = 0.25  # Delay entre cada nave na fila
    FORMATION_ENTRY_SPEED: float = 60.0  # Velocidade de descida (curved path) - REDUZIDA
    FORMATION_ENTRY_CURVE_OFFSET_X: float = 100.0  # Offset inicial horizontal (reduzido de 150)
    
    # Entry pattern speeds - Outros padrões de entrada
    FORMATION_ENTRY_LOOP_SPEED: float = 50.0  # Velocidade de descida (loop) - REDUZIDA
    FORMATION_ENTRY_WAVE_SPEED: float = 65.0  # Velocidade de descida (wave) - REDUZIDA
    FORMATION_ENTRY_FAN_SPEED: float = 40.0  # Velocidade de descida (fan) - REDUZIDA
    FORMATION_ENTRY_DIAGONAL_SPEED: float = 55.0  # Velocidade de descida (diagonal) - REDUZIDA
    
    # Pattern settings
    FORMATION_PATTERN_DURATION: float = 8.0  # Tempo em cada padrão antes de transicionar
    FORMATION_TRANSITION_DURATION: float = 2.0  # Tempo de transição entre padrões
    
    # Pattern dimensions
    FORMATION_CIRCLE_RADIUS: float = 100.0
    FORMATION_V_SPACING: float = 45.0  # Espaçamento entre inimigos no V
    FORMATION_SQUARE_SIZE: float = 180.0
    FORMATION_LINE_SPACING: float = 50.0
    FORMATION_DRIFT_SPEED: float = 150.0  # Velocidade de movimento lateral
    FORMATION_DESCENT_SPEED: float = 30.0  # Velocidade de descida após formar padrão
    
    # ========================================
    # UI SETTINGS
    # ========================================
    WARNING_FONT_SIZE: int = 60


# Validação: garantir que as chances de power-up somam 1.0
_powerup_chances_sum = sum(Config.POWERUP_RARITY_CHANCES.values())
assert abs(_powerup_chances_sum - 1.0) < 0.001, \
    f"POWERUP_RARITY_CHANCES must sum to 1.0, got {_powerup_chances_sum:.4f}"
