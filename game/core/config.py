from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Config:
    # === DISPLAY SETTINGS ===
    SCREEN_WIDTH: int = 1000
    SCREEN_HEIGHT: int = 600
    FPS: int = 60

    # === GAMEPLAY SETTINGS ===
    INITIAL_LIVES: int = 3
    PREPARATION_TIME: float = 5.0  # seconds

    # === ENTITY SPEEDS (pixels/second) ===
    SHIP_SPEED: float = 300.0
    BULLET_SPEED: float = 480.0
    FAST_METEOR_SPEED: float = 320.0  # pequenos
    SLOW_METEOR_SPEED: float = 25.0  # grandes
    POWERUP_SPEED: int = 100

    # === METEOR SETTINGS ===
    MIN_METEOR_SIZE: int = 12
    MAX_METEOR_SIZE: int = 55
    METEOR_SPAWN_EVERY: float = 0.58  # seconds
    DIAGONAL_CHANCE: float = 0.4

    # === FRAGMENTATION SETTINGS ===
    FRAGMENT_MIN_SIZE: int = 12
    FRAGMENT_SPLIT_THRESHOLD: int = 28
    FRAGMENT_COUNT_RANGE: Tuple[int, int] = (2, 5)
    FRAGMENT_SPEED_BOOST: float = 1.25
    FRAGMENT_SPREAD: float = 260.0  # degrees

    # === SCORING ===
    BASE_POINTS: int = 5
    SIZE_BONUS_MULTIPLIER: float = 1.2
    POWERUP_SCORE_BONUS: int = 500

    # === POWER-UP SETTINGS ===
    POWERUP_SPAWN_INTERVAL: Tuple[float, float] = (15.0, 25.0)
    POWERUP_SIZE: int = 48

    # === EFFECT DURATIONS (all in seconds) ===
    EXPLOSION_DURATION: float = 0.8
    # Explosão mais longa e dramática para o boss
    BOSS_EXPLOSION_DURATION: float = 3.0
    INVULN_TIME: float = 3.0
    SHIELD_DURATION: float = 8.0
    DOUBLE_SHOT_DURATION: float = 10.0
    SPEED_BOOST_DURATION: float = 8.0
    RAINBOW_DURATION: float = 15.0

    # === BOSS SETTINGS ===
    BOSS_HEALTH: int = 500
    BOSS_FRENZY_THRESHOLD: float = 0.5
    BOSS_FRENZY_SPEED_MULTIPLIER: float = 1.5
    BOSS_ENTRY_SPEED: float = 30.0
    BOSS_ENTRY_SHAKE_DURATION: float = 3.0
    BOSS_INITIAL_SPEED: float = 2.0
    LASER_DISTANCE: float = 800.0  # How far the boss laser can reach (in pixels)

    # === BOSS TIMING ===
    BOSS_CALM_ATTACK_INTERVAL: Tuple[float, float] = (3.0, 5.0)
    BOSS_FRENZY_ATTACK_INTERVAL: Tuple[float, float] = (1.0, 2.0)
    BOSS_LASER_LIFETIME: float = 2.0
    BOSS_FRENZY_LASER_LIFETIME: float = 1.5
    BOSS_CHARGE_DURATION: float = 1.0  # Tempo do efeito visual de carregamento
    BOSS_FRENZY_SHAKE_DURATION: float = 3.0

    # === BOSS VISUAL EFFECTS ===
    BOSS_AIM_BLINK_INTERVAL: int = 400
    BOSS_AIM_BLINK_ON_DURATION: int = 200
    BOSS_AIM_DASH_LENGTH: int = 20
    BOSS_AIM_GAP_LENGTH: int = 25
    BOSS_CHARGE_CIRCLE_MAX_RADIUS: float = 40.0  # Maximum radius of the charging circle effect
