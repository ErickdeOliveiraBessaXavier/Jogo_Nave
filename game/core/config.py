from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Tuple


class SlimeBossState(Enum):
    ENTERING = auto()
    STAGE_1_NORMAL = auto()
    WAITING_DRIPS = auto()
    RETREATING = auto()
    STAGE_2_HOMING = auto()
    STAGE_3_NORMAL = auto()
    STAGE_4_HOMING = auto()
    STAGE_5_FINAL = auto()


class SlimeDripMode(Enum):
    NORMAL = auto()  # Apenas drips normais
    HOMING = auto()  # Apenas drips homing
    DUAL = auto()  # Ambos simultaneamente


@dataclass
class StageConfig:
    max_drips: int
    spawn_interval: float
    duration: float | None
    is_homing: bool
    target_y: float

    # NOVO: Controles para modo dual
    drip_mode: SlimeDripMode = SlimeDripMode.NORMAL
    max_homing_drips: int = 0  # Máximo de homing quando dual
    homing_spawn_interval: float = 1.0  # Intervalo homing quando dual


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
    DAMAGE_BOOST = "damage_boost"  # Dobra o dano das balas temporariamente


@dataclass(frozen=True)
class Config:
    # ========================================
    # DISPLAY & PERFORMANCE SETTINGS
    # ========================================
    FULLSCREEN: bool = True
    SCREEN_WIDTH: int = 1280  # Largura padrão (será sobrescrita se fullscreen)
    SCREEN_HEIGHT: int = 720  # Altura padrão (será sobrescrita se fullscreen)
    FPS: int = 120

    # ========================================
    # BASIC GAMEPLAY SETTINGS
    # ========================================
    INITIAL_LIVES: int = 5
    PREPARATION_TIME: float = 5.0  # seconds
    SHOOT_COOLDOWN: float = 0.20  # Tempo entre tiros quando segura a tecla
    FIRE_RATE: float = 5.0  # Tiros por segundo (1 / SHOOT_COOLDOWN)

    # ========================================
    # ENTITY MOVEMENT SPEEDS (pixels/second)
    # ========================================
    BULLET_SPEED: float = 480.0
    BULLET_BASE_DAMAGE: int = 10
    MINI_SHIP_BULLET_DAMAGE: int = 10
    FAST_METEOR_SPEED: float = 320.0  # meteoros pequenos
    SLOW_METEOR_SPEED: float = 25.0  # meteoros grandes
    POWERUP_SPEED: float = 100.0  # CORRIGIDO: float para consistência

    # ========================================
    # ALIEN BULLET SETTINGS
    # ========================================
    ALIEN_BULLET_SPEED: float = 200.0
    ALIEN_BULLET_MIN_RADIUS: int = 5
    ALIEN_BULLET_MAX_RADIUS: int = 8
    ALIEN_BULLET_PULSE_SPEED: float = 4.0
    ALIEN_BULLET_COLOR_CHANGE_INTERVAL: float = 0.2  # segundos

    # ========================================
    # ALIEN SETTINGS
    # ========================================
    # ========================================
    # ALIEN SETTINGS
    # ========================================
    ALIEN_WIDTH: int = 75
    ALIEN_HEIGHT: int = 58
    ALIEN_SPEED_X_OPTIONS: list[int] = field(default_factory=lambda: [-100, 100])
    ALIEN_SPEED_Y: float = 60.0
    ALIEN_HEALTH: int = 15
    ALIEN_ANIMATION_FRAME_DURATION: float = 0.1
    ALIEN_DEATH_MARGIN: int = 100  # Margem de segurança para considerar morto
    ALIEN_POINTS_VALUE: int = 150  # Pontos por destruir
    ALIEN_SHOOT_PAUSE_DURATION: float = 0.5  # Tempo que fica parado antes de atirar
    ALIEN_POST_SHOOT_COOLDOWN: float = (
        0.5  # Tempo para esperar após disparar antes de mover
    )
    ALIEN_SHOOT_INTERVAL_MIN: float = 1.0  # Intervalo mínimo entre tiros
    ALIEN_SHOOT_INTERVAL_MAX: float = 4.0  # Intervalo máximo entre tiros
    ALIEN_SHOOT_BURST_CHANCE: float = 0.3  # Chance de disparo em rajada (30%)
    ALIEN_BURST_COUNT: int = 3  # Quantos tiros na rajada
    ALIEN_BURST_INTERVAL: float = 1.0  # Intervalo entre tiros da rajada (1 segundo)
    ALIEN_BURST_PAUSE_DURATION: float = 0.2  # Pausa antes de cada tiro da rajada

    # ========================================
    # METEOR SYSTEM
    # ========================================
    # Basic meteor settings
    MIN_METEOR_SIZE: int = 12
    MAX_METEOR_SIZE: int = 55
    DIAGONAL_CHANCE: float = 2

    # Fragmentation system
    FRAGMENT_SPLIT_THRESHOLD: int = 28
    FRAGMENT_COUNT_RANGE: Tuple[int, int] = (2, 5)
    FRAGMENT_SPEED_BOOST: float = 1.25
    FRAGMENT_SPREAD: float = 260.0  # degrees

    # Guided meteors
    GUIDED_METEOR_NORMAL_PHASES_CHANCE: float = 0.1  # Chance nas fases normais (10%)
    GUIDED_METEOR_MAX_SPEED: float = 250.0
    GUIDED_METEOR_ACCELERATION: float = 100.0
    GUIDED_METEOR_TURN_RATE: float = 3.0  # rad/s

    # RockGlider sizes
    ROCK_GLIDER_NORMAL_MIN_SIZE: int = 12
    ROCK_GLIDER_NORMAL_MAX_SIZE: int = 45
    ROCK_GLIDER_BASE_MIN_SIZE: int = 15
    ROCK_GLIDER_BASE_MAX_SIZE: int = 22
    ROCK_GLIDER_STORM_SIZE_OPTIONS: Tuple[int, ...] = (15, 16, 17, 18, 19, 20, 21, 22)
    ROCK_GLIDER_STORM_SIZE_WEIGHTS: Tuple[int, ...] = (22, 20, 17, 13, 10, 8, 6, 4)

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
    DAMAGE_BOOST_DURATION: float = 8.0
    DAMAGE_BOOST_MULTIPLIER: float = 2.0
    SPEED_ATTACK_MULTIPLIER: float = 2.0
    PIERCING_SHOT_ATTACK_SPEED_MULTIPLIER: float = 1.5
    EXPLOSIVE_SHOT_FIRE_RATE_PENALTY: float = (
        0.5  # Tiros explosivos são 50% mais lentos
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
    LEVEL_TRANSITION_PENDING_DELAY: float = 2.0
    LEVEL_TRANSITION_ANIMATION_TIMEOUT: float = 1.2
    INITIAL_GAME_DELAY: float = 5.0

    # Boss warning sequence
    BOSS_PRE_WARNING_DELAY: float = 5.0
    BOSS_WARNING_DURATION: float = 5.0
    BOSS_POST_WARNING_DELAY: float = 3.0

    # Music transition settings for boss warning
    BOSS_MUSIC_FADE_OUT_START: float = 3.0
    BOSS_MUSIC_FADE_OUT_DURATION: float = 2.0
    # (Fade in da música do boss não implementado)

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

    # Mountain mage / stalagmite attack tuning
    MOUNTAIN_MAGE_WARNING_DURATION: float = 0.9
    MOUNTAIN_MAGE_COOLDOWN: float = 2.8
    MOUNTAIN_MAGE_STALAGMITE_HEALTH: int = 3
    MOUNTAIN_MAGE_STALAGMITE_MIN_HEIGHT: int = 62
    MOUNTAIN_MAGE_STALAGMITE_MAX_HEIGHT: int = 150

    # Screen shake effects
    SCREEN_SHAKE_NORMAL: int = 10
    SCREEN_SHAKE_GAME_OVER: int = 15
    SCREEN_SHAKE_BOSS_DEATH: int = 25
    SCREEN_SHAKE_BOSS_DEATH_DURATION: float = 2.5

    # Game over effects
    GAME_OVER_FADE_DURATION: float = 2.0
    GAME_OVER_RESTART_DELAY: float = 1.5
    GAME_OVER_OVERLAY_ALPHA: int = 200  # 0-255

    # World transition cutscene
    WORLD_TRANSITION_CUTSCENE_DURATION: float = 1.6
    WORLD_TRANSITION_CUTSCENE_CHARGE_DURATION: float = 0.6
    WORLD_TRANSITION_CUTSCENE_LAUNCH_SPEED: float = 80.0
    WORLD_TRANSITION_CUTSCENE_LAUNCH_ACCELERATION: float = 2200.0

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
    BOSS_LASER_DELAY: float = 0.5  # Delay após linha de mira sumir

    # Boss attack animations - Frenzy mode
    BOSS_FRENZY_CHARGE_DURATION: float = 0.5
    BOSS_FRENZY_LASER_DELAY: float = 0.4  # Delay após linha de mira sumir

    # Boss animation speed multipliers
    BOSS_ANIMATION_SPEED_MULTIPLIER: float = 1.0
    BOSS_FRENZY_ANIMATION_SPEED_MULTIPLIER: float = 2.0

    # ========================================
    # GIANT METEOR BOSS
    # ========================================
    GIANT_METEOR_BOSS_HEALTH: int = 3000
    GIANT_METEOR_BOSS_HEIGHT: int = 800
    GIANT_METEOR_BOSS_ENTRY_SPEED: float = 35.0
    GIANT_METEOR_BOSS_FALL_SPEED: float = 3.0
    GIANT_METEOR_FRAGMENT_MIN_SIZE: int = 16
    GIANT_METEOR_FRAGMENT_MAX_SIZE: int = 40
    GIANT_METEOR_HIT_FRAGMENT_CHANCE: float = 0.35  # 35% por hit
    GIANT_METEOR_HIT_FRAGMENT_COUNT: tuple[int, int] = (1, 3)
    GIANT_METEOR_DEATH_FRAGMENT_COUNT: tuple[int, int] = (8, 12)

    # Boss visual effects - Normal mode
    # (Sistema de partículas de carregamento não implementado)

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
    # (Sistema de quadrados orbitais não implementado)
    BOSS_AIM_BLINK_INTERVAL: int = 400
    BOSS_AIM_BLINK_ON_DURATION: int = 200
    BOSS_AIM_DASH_LENGTH: int = 20
    BOSS_AIM_GAP_LENGTH: int = 25
    BOSS_CHARGE_CIRCLE_MAX_RADIUS: float = 30.0

    # Boss visual effects - Frenzy mode
    BOSS_FRENZY_AIM_BLINK_INTERVAL: int = 200
    BOSS_FRENZY_AIM_BLINK_ON_DURATION: int = 100

    # ========================================
    # STONE GOLEM BOSS
    # ========================================
    GOLEM_HEALTH: int = 1800
    GOLEM_ENTRY_SPEED: float = 160.0
    GOLEM_SPEED: float = 75.0
    GOLEM_ATTACK_DEBRIS_SPEED: float = 300.0
    GOLEM_ORBITAL_DEBRIS_SPEED: float = 340.0
    GOLEM_DEBRIS_GRAVITY: float = 30.0
    GOLEM_EMERGE_DEBRIS_COUNT: int = 8
    GOLEM_SUBMERGE_DEBRIS_COUNT: int = 8

    # ========================================
    # BLACK HOLE SYSTEM
    # ========================================
    # Movement and physics
    BLACK_HOLE_SPEED_Y: float = -50.0
    BLACK_HOLE_INITIAL_CORE_RADIUS: float = 10.0
    BLACK_HOLE_MAX_CORE_RADIUS: float = 60.0
    BLACK_HOLE_GROWTH_RATE: float = 15.0
    BLACK_HOLE_PARTICLE_COUNT: int = 90  # Otimizado para performance
    BLACK_HOLE_PULL_SPEED: float = 300.0

    # Radii
    BLACK_HOLE_INITIAL_PULL_RADIUS: float = 250.0
    BLACK_HOLE_MAX_PULL_RADIUS: float = 800.0

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

    # ========================================
    # SLIME BOSS - DRIPPING SYSTEM
    # ========================================
    # Basic stats
    SLIME_BOSS_HEALTH: int = 3200
    SLIME_BOSS_WIDTH_MARGIN: int = 100  # Extra width (50px each side)
    SLIME_BOSS_HEIGHT: int = 600
    SLIME_BOSS_ANIMATION_SPEED: float = 0.2

    # Movement (Active State)
    SLIME_BOSS_MOVE_SPEED: float = 50.0
    SLIME_BOSS_MOVE_RANGE: int = 50

    # Health Thresholds
    SLIME_BOSS_THRESHOLD_STAGE_1: float = 0.75
    SLIME_BOSS_THRESHOLD_STAGE_3: float = 0.20

    # Movement speeds
    SLIME_BOSS_ENTRY_SPEED_SLOW: float = 80.0  # Dramatic initial entry
    SLIME_BOSS_ENTRY_SPEED_FAST: float = 300.0  # Subsequent entries/leaving
    SLIME_BOSS_LEAVING_SPEED: float = 300.0  # Leaving speed (same as fast entry)

    # Stage configurations
    SLIME_BOSS_STAGES: dict[SlimeBossState, StageConfig] = field(
        default_factory=lambda: {
            SlimeBossState.STAGE_1_NORMAL: StageConfig(
                max_drips=18,  # SLIME_DRIP_MAX_ACTIVE
                spawn_interval=0.5,  # SLIME_DRIP_SPAWN_INTERVAL
                duration=None,
                is_homing=False,
                target_y=-40,
            ),
            SlimeBossState.STAGE_2_HOMING: StageConfig(
                max_drips=18,  # SLIME_DRIP_HOMING_MAX_ACTIVE
                spawn_interval=0.4,  # SLIME_DRIP_HOMING_SPAWN_INTERVAL
                duration=15.0,
                is_homing=True,
                target_y=-40,
            ),
            SlimeBossState.STAGE_3_NORMAL: StageConfig(
                max_drips=int(15 * 2.5),  # SLIME_DRIP_MAX_ACTIVE * 2.5
                spawn_interval=0.4 * 0.8,  # SLIME_DRIP_SPAWN_INTERVAL * 0.8
                duration=None,
                is_homing=False,
                target_y=-40,
            ),
            SlimeBossState.STAGE_4_HOMING: StageConfig(
                max_drips=20,  # SLIME_DRIP_HOMING_MAX_ACTIVE
                spawn_interval=0.3,  # SLIME_DRIP_HOMING_SPAWN_INTERVAL
                duration=20.0,
                is_homing=True,
                target_y=-30,
            ),
            SlimeBossState.STAGE_5_FINAL: StageConfig(
                # Drips normais (caindo do boss)
                max_drips=20,  # Menos que 2.0x para compensar homing
                spawn_interval=0.3,  # Mais rápido
                duration=None,
                is_homing=False,  # Legado
                target_y=-40,
                # NOVO: Modo dual ativo
                drip_mode=SlimeDripMode.DUAL,
                max_homing_drips=8,  # Quantidade moderada de homing
                homing_spawn_interval=1.5,  # Mais espaçados (menos frequentes)
            ),
        }
    )

    # Propriedades físicas das gotas
    SLIME_DRIP_RADIUS_MAX: float = 75.0

    # Spawn e gameplay
    SLIME_DRIP_MAX_ACTIVE: int = 15
    SLIME_DRIP_SPAWN_INTERVAL: float = 0.6

    # Pool e otimização
    SLIME_DRIP_POOL_SIZE_MULTIPLIER: int = (
        2  # Multiplicador para tamanho inicial do pool
    )
    SLIME_DRIP_SPATIAL_GRID_CELL_SIZE: int = 150  # Tamanho da célula do spatial grid

    # Sistema de partículas desprendidas
    SLIME_DRIP_DETACH_PARTICLE_SPAWN_INTERVAL: float = (
        0.05  # Intervalo entre spawns (segundos) - para produção contínua
    )
    SLIME_DRIP_DETACH_PARTICLE_MAX_PER_DRIP: int = 15  # Máximo de partículas por gota
    SLIME_DRIP_DETACH_PARTICLE_SIZE_START: float = (
        0.4  # Tamanho inicial relativo à gota
    )
    SLIME_DRIP_DETACH_PARTICLE_SIZE_END: float = 0.1  # Tamanho final (quando some)
    SLIME_DRIP_DETACH_PARTICLE_LIFETIME: float = 1.0  # Tempo de vida (segundos)
    SLIME_DRIP_DETACH_PARTICLE_SPEED_MIN: float = 20.0  # Velocidade mínima de movimento
    SLIME_DRIP_DETACH_PARTICLE_SPEED_MAX: float = 60.0  # Velocidade máxima de movimento

    # Sistema de pulso
    SLIME_DRIP_PULSE_PERIOD: float = 3.0  # Período completo do pulso (segundos)
    SLIME_DRIP_PULSE_AMPLITUDE: float = 0.15  # Amplitude do pulso (15% de variação)

    # Física e limites
    SLIME_DRIP_DEATH_MARGIN: int = 100  # Margem para considerar gota morta (pixels)

    # Visual - Cores
    SLIME_DRIP_COLORS: list[Tuple[int, int, int]] = field(
        default_factory=lambda: [
            (241, 187, 242),
            (166, 29, 224),
            (68, 18, 89),
        ]
    )

    # Homing system
    SLIME_DRIP_HOMING_MAX_SPEED: float = 180.0
    SLIME_DRIP_HOMING_ACCELERATION: float = 150.0
    SLIME_DRIP_HOMING_BLEND_FACTOR: float = (
        0.15  # Reduzido de 1.0 para suavizar mudanças de direção
    )
    SLIME_DRIP_HOMING_AIM_OFFSET: float = 50.0
    SLIME_DRIP_HOMING_MAX_DURATION: float = 15.0
    SLIME_DRIP_HOMING_TARGET_UPDATE_INTERVAL: float = 0.4
    SLIME_DRIP_HOMING_SPAWN_Y_OFFSET: float = -50.0
    SLIME_DRIP_HOMING_SCALE_MIN: float = 0.3
    SLIME_DRIP_HOMING_SCALE_MAX: float = 0.5

    # Novo: Sistema de desengajamento
    SLIME_DRIP_HOMING_DISENGAGE_DISTANCE: float = 100.0  # Distância para destravar
    SLIME_DRIP_HOMING_DISENGAGE_TIME: float = 5.0  # Tempo máximo perseguindo (segundos)

    # Controle separado para homing drips
    SLIME_DRIP_HOMING_MAX_ACTIVE: int = 15
    SLIME_DRIP_HOMING_SPAWN_INTERVAL: float = 0.5

    # Pool settings
    SLIME_DRIP_MAX_ORPHAN_PARTICLES: int = 200
    SLIME_DRIP_BOSS_SPAWN_Y_OFFSET: float = -50.0

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
    FORMATION_DESCENT_SPEED: float = 30.0

    # ========================================
    # UI SETTINGS
    # ========================================
    WARNING_FONT_SIZE: int = 60

    # ========================================
    # COMPUTED PROPERTIES (não editáveis diretamente)
    # ========================================
    @property
    def BOSS_MUSIC_SILENCE_DURATION(self) -> float:
        """Duração calculada do silêncio musical durante aviso do boss."""
        return self.BOSS_WARNING_DURATION + self.BOSS_POST_WARNING_DELAY

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
            ("POWERUP_SPAWN_INTERVAL", self.POWERUP_SPAWN_INTERVAL),
            ("FORMATION_SPAWN_INTERVAL", self.FORMATION_SPAWN_INTERVAL),
            (
                "ROCK_GLIDER_NORMAL_SIZE_RANGE",
                (self.ROCK_GLIDER_NORMAL_MIN_SIZE, self.ROCK_GLIDER_NORMAL_MAX_SIZE),
            ),
            (
                "ROCK_GLIDER_BASE_SIZE_RANGE",
                (self.ROCK_GLIDER_BASE_MIN_SIZE, self.ROCK_GLIDER_BASE_MAX_SIZE),
            ),
        ]

        for name, (min_val, max_val) in ranges_to_check:
            if min_val > max_val:
                errors.append(f"{name}: min ({min_val}) > max ({max_val})")

        # Validar thresholds (0.0 a 1.0)
        thresholds = [
            ("BOSS_FRENZY_THRESHOLD", self.BOSS_FRENZY_THRESHOLD),
            ("SPIKE_BOSS_FRENZY_THRESHOLD", self.SPIKE_BOSS_FRENZY_THRESHOLD),
        ]

        for name, value in thresholds:
            if not 0.0 <= value <= 1.0:
                errors.append(f"{name} deve estar entre 0.0 e 1.0, mas é {value}")

        # Validar valores positivos
        positive_values = [
            "FPS",
            "INITIAL_LIVES",
            "SCREEN_WIDTH",
            "SCREEN_HEIGHT",
            "BOSS_HEALTH",
            "SPIKE_BOSS_HEALTH",
            "SLIME_BOSS_HEALTH",
            "SLIME_BOSS_ENTRY_SPEED_SLOW",
            "SLIME_BOSS_ENTRY_SPEED_FAST",
            "SLIME_BOSS_LEAVING_SPEED",
        ]

        for name in positive_values:
            value = getattr(self, name)
            if value <= 0:
                errors.append(f"{name} deve ser positivo, mas é {value}")

        if len(self.ROCK_GLIDER_STORM_SIZE_OPTIONS) != len(
            self.ROCK_GLIDER_STORM_SIZE_WEIGHTS
        ):
            errors.append(
                "ROCK_GLIDER_STORM_SIZE_OPTIONS e ROCK_GLIDER_STORM_SIZE_WEIGHTS devem ter o mesmo tamanho"
            )

        if not self.ROCK_GLIDER_STORM_SIZE_OPTIONS:
            errors.append("ROCK_GLIDER_STORM_SIZE_OPTIONS não pode estar vazio")

        golem_debris_counts = [
            ("GOLEM_EMERGE_DEBRIS_COUNT", self.GOLEM_EMERGE_DEBRIS_COUNT),
            ("GOLEM_SUBMERGE_DEBRIS_COUNT", self.GOLEM_SUBMERGE_DEBRIS_COUNT),
        ]
        for name, value in golem_debris_counts:
            if value < 0:
                errors.append(f"{name} deve ser >= 0, mas é {value}")

        return errors


# ============================================================================
# INSTÂNCIA GLOBAL E VALIDAÇÃO
# ============================================================================


_config_instance = Config()


_runtime_screen = {
    "width": _config_instance.SCREEN_WIDTH,
    "height": _config_instance.SCREEN_HEIGHT,
}


class ConfigProxy:
    """Proxy que retorna valores dinâmicos para SCREEN_WIDTH e SCREEN_HEIGHT."""

    def __init__(self, config_instance: "Config") -> None:
        self._config = config_instance

    def __getattr__(self, name: str) -> Any:
        if name == "SCREEN_WIDTH":
            return _runtime_screen["width"]
        if name == "SCREEN_HEIGHT":
            return _runtime_screen["height"]
        return getattr(self._config, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_config":
            super().__setattr__(name, value)
        else:
            raise AttributeError(f"Config é imutável. Não é possível alterar {name}")


def set_screen_resolution(width: int, height: int):
    """Atualiza a resolução da tela em tempo de execução."""
    _runtime_screen["width"] = width
    _runtime_screen["height"] = height


# Envolver a instância com o proxy
config = ConfigProxy(_config_instance)

# Validar na importação (desenvolvimento)
_validation_errors = _config_instance.validate()
if _validation_errors:
    error_msg = "Erros encontrados na configuração:\n" + "\n".join(
        f"  - {err}" for err in _validation_errors
    )
    raise ValueError(error_msg)
