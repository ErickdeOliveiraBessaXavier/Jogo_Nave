from dataclasses import dataclass, field
from typing import Tuple, Any
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
    COOLDOWN_HASTE = "cooldown_haste"  # Reduz tempo de recarga
    TIME_STOP = "time_stop"  # Congela inimigos e projéteis


@dataclass(frozen=True)
class Config:
    # ========================================
    # DISPLAY & PERFORMANCE SETTINGS
    # ========================================
    FULLSCREEN: bool = True
    SCREEN_WIDTH: int = 1600  # Largura padrão (será sobrescrita se fullscreen)
    SCREEN_HEIGHT: int = 900  # Altura padrão (será sobrescrita se fullscreen)
    FPS: int = 120

    # ========================================
    # BASIC GAMEPLAY SETTINGS
    # ========================================
    INITIAL_LIVES: int = 5
    PREPARATION_TIME: float = 5.0  # seconds
    SHOOT_COOLDOWN: float = 0.20  # Tempo entre tiros quando segura a tecla

    # ========================================
    # ENTITY MOVEMENT SPEEDS (pixels/second)
    # ========================================
    SHIP_SPEED: float = 300.0
    BULLET_SPEED: float = 480.0
    FAST_METEOR_SPEED: float = 320.0  # meteoros pequenos
    SLOW_METEOR_SPEED: float = 25.0  # meteoros grandes
    POWERUP_SPEED: float = 100.0  # CORRIGIDO: float para consistência

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
    COOLDOWN_HASTE_REDUCTION: float = 20.0  # Redução fixa em segundos
    TIME_STOP_DURATION: float = 3.0
    SPEED_ATTACK_MULTIPLIER: float = 2.0
    PIERCING_SHOT_ATTACK_SPEED_MULTIPLIER: float = 1.5
    EXPLOSIVE_SHOT_FIRE_RATE_PENALTY: float = (
        0.5  # Tiros explosivos são 50% mais lentos
    )

    # Rarity system - Sistema de raridade para power-ups (porcentagens 0.0-100.0, soma deve ser 100.0)
    POWERUP_RARITIES: dict[PowerUpType, float] = field(
        default_factory=lambda: {
            # 🔵 COMUM (45% total) - Power-ups básicos e frequentes
            PowerUpType.SHIELD: 5.8,  # 5.8% - Escudo básico
            PowerUpType.DOUBLE_SHOT: 12.7,  # 12.7% - Tiro duplo
            # 🟢 INCOMUM (15% total) - Power-ups situacionais
            PowerUpType.SPEED: 8.7,  # 8.7% - Velocidade aumentada
            # 🟠 RARO (35% total) - Power-ups poderosos mas raros
            PowerUpType.PIERCING_SHOT: 46.2,  # 46.2% - Tiro perfurante
            PowerUpType.MINI_SHIPS: 9.8,  # 9.8% - Naves auxiliares
            PowerUpType.LIFE: 2.9,  # 2.9% - Vida extra
            # 🟣 ÉPICO (4% total) - Power-ups muito valiosos
            PowerUpType.SCORE: 2.3,  # 2.3% - Multiplicador de pontos
            # 🟡 LENDÁRIO (1% total) - Power-ups ultra-raros
            PowerUpType.RAINBOW: 0.6,  # 0.6% - Power-up especial
            # 🟠 NOVOS
            PowerUpType.COOLDOWN_HASTE: 8.7,  # 8.7% - Reduz tempo de recarga
            PowerUpType.TIME_STOP: 2.3,  # 2.3% - Congelamento total
        }
    )

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
    BOSS_PRE_WARNING_DELAY: float = 5.0
    BOSS_WARNING_DURATION: float = 5.0
    BOSS_POST_WARNING_DELAY: float = 3.0

    # Music transition settings for boss warning
    BOSS_MUSIC_FADE_OUT_START: float = 3.0
    BOSS_MUSIC_FADE_OUT_DURATION: float = 2.0
    BOSS_MUSIC_FADE_IN_DURATION: float = 3.0
    BOSS_MUSIC_FADE_IN_START_DELAY: float = 1.0

    # ========================================
    # VISUAL EFFECTS & ANIMATIONS
    # ========================================
    WARP_SPEED_MULTIPLIER: float = 30.0
    BOSS_WARP_SPEED_MULTIPLIER: float = 15.0

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
    # CLASSIC BOSS SYSTEM
    # ========================================
    BOSS_HEALTH: int = 1000
    BOSS_FRENZY_THRESHOLD: float = 0.5
    BOSS_ENTRY_SPEED: float = 30.0
    BOSS_ENTRY_SHAKE_DURATION: float = 4.0

    # Boss movement
    BOSS_NORMAL_SPEED: float = 4.0  # Reduzido de 6.0 para 4.0
    BOSS_FRENZY_SPEED: float = 6.0  # Reduzido de 8.0 para 6.0
    BOSS_FRENZY_SHAKE_DURATION: float = 3.0

    # Boss damage modifiers (nerf geral para todos os aprimoramentos)
    BOSS_UPGRADE_DAMAGE_MULTIPLIER: float = (
        0.5  # Todos os aprimoramentos fazem 50% de dano em boss
    )

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
    BOSS_CHARGE_PARTICLE_COUNT: int = 20
    BOSS_CHARGE_PARTICLE_LIFETIME: float = 1.0
    BOSS_CHARGE_PARTICLE_SIZE: Tuple[int, int] = (2, 6)

    # Ship particles
    PARTICLE_ENTRY_COUNT = 3
    PARTICLE_THRUSTER_COUNT = 2
    PARTICLE_ENTRY_VELOCITY = (-80, 80)
    PARTICLE_ENTRY_LIFETIME = (0.2, 0.6)
    PARTICLE_ENTRY_SIZE = (1, 3)
    PARTICLE_THRUSTER_VELOCITY_X = (-10, 10)
    PARTICLE_THRUSTER_VELOCITY_Y = (100, 200)
    PARTICLE_THRUSTER_LIFETIME = (0.05, 0.15)
    PARTICLE_THRUSTER_SIZE = (2, 4)

    # Boss orbital squares
    BOSS_ORBITAL_SQUARES_COUNT = 14
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
    # SPIKE BOSS SYSTEM
    # ========================================
    # Basic stats
    SPIKE_BOSS_HEALTH: int = 1200
    SPIKE_BOSS_FRENZY_THRESHOLD: float = 0.5
    SPIKE_BOSS_ENTRY_SPEED: float = 25.0
    SPIKE_BOSS_SPEED: float = 80.0
    SPIKE_BOSS_FRENZY_SPEED: float = 520.0
    SPIKE_BOSS_FRENZY_SHAKE_DURATION: float = 3.0
    SPIKE_BOSS_FRENZY_PAUSE_DURATION: float = 2.0

    # Proximity attack
    SPIKE_BOSS_PROXIMITY_DISTANCE: float = 250.0
    SPIKE_BOSS_PROXIMITY_COOLDOWN: float = 3.0
    SPIKE_BOSS_PROXIMITY_TELEGRAPH_DURATION: float = 0.8
    SPIKE_BOSS_PROXIMITY_WAVE_DURATION: float = 0.8
    SPIKE_BOSS_PROXIMITY_WAVE_MAX_RADIUS: float = 280.0
    SPIKE_BOSS_PROXIMITY_DAMAGE: int = 1
    SPIKE_BOSS_PROXIMITY_WARNING_COLOR_NORMAL: Tuple[int, int, int] = (255, 255, 0)
    SPIKE_BOSS_PROXIMITY_WARNING_COLOR_FRENZY: Tuple[int, int, int] = (255, 0, 0)
    SPIKE_BOSS_PROXIMITY_WAVE_COLOR_NORMAL: Tuple[int, int, int] = (0, 255, 255)
    SPIKE_BOSS_PROXIMITY_WAVE_COLOR_FRENZY: Tuple[int, int, int] = (255, 0, 0)
    SPIKE_BOSS_PROXIMITY_WAVE_INNER_COLOR_NORMAL: Tuple[int, int, int] = (255, 255, 255)
    SPIKE_BOSS_PROXIMITY_WAVE_INNER_COLOR_FRENZY: Tuple[int, int, int] = (255, 255, 0)

    # Mouth animation
    SPIKE_BOSS_MOUTH_CYCLE_DURATION: float = 2.0
    SPIKE_BOSS_MOUTH_MAX_OPENING: int = 15
    SPIKE_BOSS_BODY_STRETCH: int = 8

    # Eye behavior
    SPIKE_BOSS_EYE_TRACK_DURATION: float = 2.5
    SPIKE_BOSS_EYE_FRENETIC_DURATION: float = 1.0
    SPIKE_BOSS_EYE_FRENETIC_SPEED: float = 0.15

    # Giant laser attack
    SPIKE_BOSS_LASER_COOLDOWN: float = 8.0
    SPIKE_BOSS_LASER_CHARGE_TIME: float = 1.0
    SPIKE_BOSS_LASER_LIFETIME: float = 1.5

    # Attack timing
    SPIKE_BOSS_ATTACK_INTERVAL: Tuple[float, float] = (3.0, 5.0)
    SPIKE_BOSS_FRENZY_ATTACK_INTERVAL: Tuple[float, float] = (1.5, 2.5)

    # Spike spawn settings
    SPIKE_BOSS_SPIKE_COUNT: Tuple[int, int] = (3, 5)
    SPIKE_BOSS_FRENZY_SPIKE_COUNT: Tuple[int, int] = (6, 9)

    # ========================================
    # SLIME BOSS - DRIPPING SYSTEM
    # ========================================
    # Propriedades físicas das gotas
    SLIME_DRIP_RADIUS_MIN: float = 25.0
    SLIME_DRIP_RADIUS_MAX: float = 85.0
    SLIME_DRIP_SPEED_X: Tuple[float, float] = (-12.0, 12.0)
    SLIME_DRIP_SPEED_Y: Tuple[float, float] = (12.0, 30.0)
    SLIME_DRIP_ANGLE_VELOCITY: Tuple[float, float] = (-3.0, 3.0)
    SLIME_DRIP_RANGE: Tuple[float, float] = (300.0, 900.0)
    SLIME_DRIP_GRAVITY: Tuple[float, float] = (0.18, 0.48)
    SLIME_DRIP_SHRINK_RATE_BASE: float = 3.0
    SLIME_DRIP_SHRINK_RATE_MULTIPLIER: float = 4.8
    SLIME_DRIP_MIN_RADIUS: float = 4.0
    
    # Spawn e gameplay
    SLIME_DRIP_MAX_ACTIVE: int = 15
    SLIME_DRIP_SPAWN_INTERVAL: float = 0.3
    SLIME_DRIP_DAMAGE: int = 1
    SLIME_DRIP_SPAWN_CHANCE_DIRECTED: float = 0.8  # 80% direcionado
    SLIME_DRIP_PREDICTION_TIME: float = 1.5
    
    # Poças no chão
    SLIME_POOL_LIFETIME: float = 5.0
    SLIME_POOL_MAX_ACTIVE: int = 8
    SLIME_POOL_DAMAGE: int = 1
    SLIME_POOL_DAMAGE_COOLDOWN: float = 0.5
    SLIME_POOL_EXPANSION_TIME: float = 0.5
    SLIME_POOL_FADE_TIME: float = 1.5
    SLIME_POOL_RADIUS_MULTIPLIER: float = 1.5
    
    # Visual
    SLIME_DRIP_COLORS: list[Tuple[int, int, int, int]] = field(
        default_factory=lambda: [
            (241, 187, 242, 180),
            (96, 29, 115, 200),
            (68, 18, 89, 220)
        ]
    )
    SLIME_POOL_COLOR: Tuple[int, int, int, int] = (96, 29, 115, 150)

    # ========================================
    # SPIKE (PROJECTILE) SYSTEM
    # ========================================
    SPIKE_SIZE: int = 25
    SPIKE_DAMAGE: int = 1
    SPIKE_POINTS: int = 50
    SPIKE_WALL_SPACING: int = 5
    SPIKE_MAX_ATTACKING: int = 10

    # Sistema de ondas de ataque
    SPIKE_WAVE_MIN_SIZE: int = 3
    SPIKE_WAVE_MAX_SIZE: int = 6
    SPIKE_WAVE_INTERVAL: float = 4.0
    SPIKE_FRENZY_WAVE_INTERVAL: float = 2.5

    # Comportamento de grudado na parede
    SPIKE_MIN_ATTACH_TIME: float = 1.0
    SPIKE_MAX_ATTACH_TIME: float = 2.5

    # Tremor antes de soltar
    SPIKE_TREMBLE_DURATION: float = 1.0
    SPIKE_MAX_TREMBLE: int = 5

    # Míssil teleguiado
    SPIKE_INITIAL_SPEED: float = 50.0
    SPIKE_SPEED_VARIATION: float = 30.0
    SPIKE_ACCELERATION: float = 200.0
    SPIKE_MAX_SPEED: float = 300.0
    SPIKE_MAX_SPEED_VARIATION: float = 50.0
    SPIKE_AIM_IMPRECISION: float = 100.0
    SPIKE_ROTATION_SPEED_MIN: float = 8.0  # rad/s
    SPIKE_ROTATION_SPEED_MAX: float = 15.0  # rad/s

    # Efeito de entrada
    SPIKE_SPAWN_ANIMATION_DURATION: float = 0.4
    SPIKE_SPAWN_DELAY_MIN: float = 0.0
    SPIKE_SPAWN_DELAY_MAX: float = 2.0

    # Respawn e controle
    SPIKE_RESPAWN_TIME: float = 10.0
    SPIKE_LAUNCH_COOLDOWN: float = 0.2

    # ========================================
    # FORMATION SYSTEM
    # ========================================
    FORMATION_SPAWN_INTERVAL: Tuple[float, float] = (10.0, 15.0)

    # Entry pattern settings - Curved path
    FORMATION_ENTRY_CURVE_AMPLITUDE: float = 150.0
    FORMATION_ENTRY_CURVE_FREQUENCY: float = 1.2
    FORMATION_ENTRY_TIME_OFFSET: float = 0.25
    FORMATION_ENTRY_SPEED: float = 60.0
    FORMATION_ENTRY_CURVE_OFFSET_X: float = 100.0

    # Entry pattern speeds
    FORMATION_ENTRY_LOOP_SPEED: float = 50.0
    FORMATION_ENTRY_WAVE_SPEED: float = 65.0
    FORMATION_ENTRY_FAN_SPEED: float = 40.0
    FORMATION_ENTRY_DIAGONAL_SPEED: float = 55.0

    # Pattern settings
    FORMATION_PATTERN_DURATION: float = 8.0
    FORMATION_TRANSITION_DURATION: float = 2.0

    # Pattern dimensions
    FORMATION_CIRCLE_RADIUS: float = 100.0
    FORMATION_V_SPACING: float = 45.0
    FORMATION_SQUARE_SIZE: float = 180.0
    FORMATION_LINE_SPACING: float = 80.0
    FORMATION_DRIFT_SPEED: float = 150.0
    FORMATION_DESCENT_SPEED: float = 30.0

    # ========================================
    # UI SETTINGS
    # ========================================
    WARNING_FONT_SIZE: int = 60

    # ========================================
    # SLIME BOSS - DRIPPING SYSTEM
    # ========================================
    # Propriedades físicas das gotas
    SLIME_DRIP_RADIUS_MIN: float = 25.0  # pyright: ignore[reportConstantRedefinition]
    SLIME_DRIP_RADIUS_MAX: float = 85.0  # pyright: ignore[reportConstantRedefinition]
    SLIME_DRIP_SPEED_X: Tuple[float, float] = (-12.0, 12.0)  # pyright: ignore[reportConstantRedefinition]
    SLIME_DRIP_SPEED_Y: Tuple[float, float] = (12.0, 30.0)  # pyright: ignore[reportConstantRedefinition]
    SLIME_DRIP_ANGLE_VELOCITY: Tuple[float, float] = (-3.0, 3.0)  # pyright: ignore[reportConstantRedefinition]
    SLIME_DRIP_RANGE: Tuple[float, float] = (300.0, 900.0)  # pyright: ignore[reportConstantRedefinition]
    SLIME_DRIP_GRAVITY: Tuple[float, float] = (50.0, 150.0)  # pyright: ignore[reportConstantRedefinition]
    SLIME_DRIP_SHRINK_RATE_BASE: float = 3.0  # pyright: ignore[reportConstantRedefinition]
    SLIME_DRIP_SHRINK_RATE_MULTIPLIER: float = 4.8  # pyright: ignore[reportConstantRedefinition]
    SLIME_DRIP_MIN_RADIUS: float = 4.0  # pyright: ignore[reportConstantRedefinition]
    
    # Spawn e gameplay
    SLIME_DRIP_MAX_ACTIVE: int = 15  # pyright: ignore[reportConstantRedefinition]
    SLIME_DRIP_SPAWN_INTERVAL: float = 0.3  # pyright: ignore[reportConstantRedefinition]
    SLIME_DRIP_DAMAGE: int = 1  # pyright: ignore[reportConstantRedefinition]
    SLIME_DRIP_SPAWN_CHANCE_DIRECTED: float = 0.8  # 80% direcionado  # pyright: ignore[reportConstantRedefinition]
    SLIME_DRIP_PREDICTION_TIME: float = 1.5  # pyright: ignore[reportConstantRedefinition]
    
    # Poças no chão
    SLIME_POOL_LIFETIME: float = 5.0  # pyright: ignore[reportConstantRedefinition]
    SLIME_POOL_MAX_ACTIVE: int = 8  # pyright: ignore[reportConstantRedefinition]
    SLIME_POOL_DAMAGE: int = 1  # pyright: ignore[reportConstantRedefinition]
    SLIME_POOL_DAMAGE_COOLDOWN: float = 0.5  # pyright: ignore[reportConstantRedefinition]
    SLIME_POOL_EXPANSION_TIME: float = 0.5  # pyright: ignore[reportConstantRedefinition]
    SLIME_POOL_FADE_TIME: float = 1.5  # pyright: ignore[reportConstantRedefinition]
    SLIME_POOL_RADIUS_MULTIPLIER: float = 1.5  # pyright: ignore[reportConstantRedefinition]
    
    # Visual
    SLIME_DRIP_COLORS: list[Tuple[int, int, int, int]] = field(  # pyright: ignore[reportConstantRedefinition]
        default_factory=lambda: [
            (241, 187, 242, 180),
            (96, 29, 115, 200),
            (68, 18, 89, 220)
        ]
    )
    SLIME_POOL_COLOR: Tuple[int, int, int, int] = (96, 29, 115, 150)  # pyright: ignore[reportConstantRedefinition]

    # ========================================
    # COMPUTED PROPERTIES (não editáveis diretamente)
    # ========================================
    @property
    def BOSS_MUSIC_SILENCE_DURATION(self) -> float:
        """Duração calculada do silêncio musical durante aviso do boss."""
        return self.BOSS_WARNING_DURATION + self.BOSS_POST_WARNING_DELAY

    @property
    def POWERUP_WEIGHTS(self) -> dict[PowerUpType, int]:
        """Converte raridades em porcentagem para pesos inteiros (compatibilidade)."""
        # Converte porcentagens para pesos (multiplica por 1000 para manter precisão)
        return {k: int(v * 10) for k, v in self.POWERUP_RARITIES.items()}

    # ========================================
    # VALIDATION METHODS
    # ========================================
    def validate(self) -> list[str]:
        """
        Valida as configurações e retorna lista de erros encontrados.

        Returns:
            Lista de mensagens de erro (vazia se tudo OK)
        """
        errors: list[str] = []

        # Validar ranges (min <= max)
        ranges_to_check: list[tuple[str, tuple[float | int, float | int]]] = [
            ("FRAGMENT_COUNT_RANGE", self.FRAGMENT_COUNT_RANGE),
            ("BOSS_CALM_ATTACK_INTERVAL", self.BOSS_CALM_ATTACK_INTERVAL),
            ("BOSS_FRENZY_ATTACK_INTERVAL", self.BOSS_FRENZY_ATTACK_INTERVAL),
            ("SPIKE_BOSS_ATTACK_INTERVAL", self.SPIKE_BOSS_ATTACK_INTERVAL),
            (
                "SPIKE_BOSS_FRENZY_ATTACK_INTERVAL",
                self.SPIKE_BOSS_FRENZY_ATTACK_INTERVAL,
            ),
            ("SPIKE_BOSS_SPIKE_COUNT", self.SPIKE_BOSS_SPIKE_COUNT),
            ("SPIKE_BOSS_FRENZY_SPIKE_COUNT", self.SPIKE_BOSS_FRENZY_SPIKE_COUNT),
            ("POWERUP_SPAWN_INTERVAL", self.POWERUP_SPAWN_INTERVAL),
            ("FORMATION_SPAWN_INTERVAL", self.FORMATION_SPAWN_INTERVAL),
        ]

        for name, (min_val, max_val) in ranges_to_check:
            if min_val > max_val:
                errors.append(f"{name}: min ({min_val}) > max ({max_val})")

        # Validar power-up rarities (devem somar exatamente 100.0)
        total_rarity = sum(self.POWERUP_RARITIES.values())
        if not abs(total_rarity - 100.0) < 0.001:  # Tolerância para erros de arredondamento
            errors.append(f"POWERUP_RARITIES deve somar exatamente 100.0, mas soma {total_rarity}")
        for powerup_type, rarity in self.POWERUP_RARITIES.items():
            if not (0.0 <= rarity <= 100.0):
                errors.append(
                    f"POWERUP_RARITIES[{powerup_type}] deve estar entre 0.0 e 100.0, mas é {rarity}"
                )

        # Validar thresholds (0.0 a 1.0)
        thresholds = [
            ("BOSS_FRENZY_THRESHOLD", self.BOSS_FRENZY_THRESHOLD),
            ("SPIKE_BOSS_FRENZY_THRESHOLD", self.SPIKE_BOSS_FRENZY_THRESHOLD),
        ]

        for name, value in thresholds:
            if not (0.0 <= value <= 1.0):
                errors.append(f"{name} deve estar entre 0.0 e 1.0, mas é {value}")

        # Validar valores positivos
        positive_values = [
            "FPS",
            "INITIAL_LIVES",
            "SCREEN_WIDTH",
            "SCREEN_HEIGHT",
            "BOSS_HEALTH",
            "SPIKE_BOSS_HEALTH",
        ]

        for name in positive_values:
            value = getattr(self, name)
            if value <= 0:
                errors.append(f"{name} deve ser positivo, mas é {value}")

        return errors


# ============================================================================
# INSTÂNCIA GLOBAL E VALIDAÇÃO
# ============================================================================

# Criar instância global da config
_config_instance = Config()

# Variáveis para armazenar resolução em tempo de execução
_runtime_screen_width = _config_instance.SCREEN_WIDTH
_runtime_screen_height = _config_instance.SCREEN_HEIGHT


class ConfigProxy:
    """Proxy que retorna valores dinâmicos para SCREEN_WIDTH e SCREEN_HEIGHT."""

    def __init__(self, config_instance: "Config") -> None:
        self._config = config_instance

    def __getattr__(self, name: str) -> Any:
        if name == "SCREEN_WIDTH":
            return _runtime_screen_width
        elif name == "SCREEN_HEIGHT":
            return _runtime_screen_height
        else:
            return getattr(self._config, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_config":
            super().__setattr__(name, value)
        else:
            raise AttributeError(f"Config é imutável. Não é possível alterar {name}")


def set_screen_resolution(width: int, height: int):
    """Atualiza a resolução da tela em tempo de execução."""
    global _runtime_screen_width, _runtime_screen_height
    _runtime_screen_width = width
    _runtime_screen_height = height


# Envolver a instância com o proxy
config = ConfigProxy(_config_instance)

# Validar na importação (desenvolvimento)
_validation_errors = _config_instance.validate()
if _validation_errors:
    error_msg = "Erros encontrados na configuração:\n" + "\n".join(
        f"  - {err}" for err in _validation_errors
    )
    raise ValueError(error_msg)
