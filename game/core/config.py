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


@dataclass(frozen=True)
class Config:
    # ========================================
    # DISPLAY & PERFORMANCE SETTINGS
    # ========================================
    SCREEN_WIDTH: int = 1000
    SCREEN_HEIGHT: int = 600
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
    SLOW_METEOR_SPEED: float = 25.0   # meteoros grandes
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
    SPEED_ATTACK_MULTIPLIER: float = 2.0  # Multiplicador de velocidade de ataque
    PIERCING_SHOT_ATTACK_SPEED_MULTIPLIER: float = 1.5

    # Rarity system - chances devem somar 1.0
    POWERUP_RARITY_CHANCES = {
        PowerUpType.SHIELD: 0.30,       # 30% - Comum
        PowerUpType.DOUBLE_SHOT: 0.25,  # 25% - Comum
        PowerUpType.SPEED: 0.15,        # 15% - Incomum
        PowerUpType.PIERCING_SHOT: 0.15, # 15% - Raro
        PowerUpType.LIFE: 0.10,         # 10% - Raro
        PowerUpType.SCORE: 0.04,        # 4% - Épico
        PowerUpType.RAINBOW: 0.01       # 1% - Lendário
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
    BOSS_PRE_WARNING_DELAY: float = 5.0   # Delay antes do warning
    BOSS_WARNING_DURATION: float = 5.0    # Duração do warning ativo 
    BOSS_POST_WARNING_DELAY: float = 3.0  # Delay após warning antes do boss

    # Music transition settings for boss warning
    BOSS_MUSIC_FADE_OUT_START: float = 3.0     # Inicia fade-out 3s antes do warning
    BOSS_MUSIC_FADE_OUT_DURATION: float = 2.0  # Tempo do fade-out da música normal
    BOSS_MUSIC_SILENCE_DURATION: float = 8.0   # Tempo total de silêncio (warning + delay)
    BOSS_MUSIC_FADE_IN_DURATION: float = 3.0   # Tempo do fade-in da música do boss
    BOSS_MUSIC_FADE_IN_START_DELAY: float = 1.0  # Delay antes do fade-in começar (quando boss aparece)

    # ========================================
    # VISUAL EFFECTS & ANIMATIONS
    # ========================================
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

    # Boss movement
    BOSS_NORMAL_SPEED: float = 6.0   # Velocidade normal lateral
    BOSS_FRENZY_SPEED: float = 8.0   # Velocidade no frenzy
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
    BOSS_METEOR_AIM_SPREAD: float = 30.0      # Desvio normal (±30°)
    BOSS_SIDE_METEOR_AIM_SPREAD: float = 45.0 # Desvio lateral (±45°)

    # ========================================
    # UI SETTINGS
    # ========================================
    WARNING_FONT_SIZE: int = 60
