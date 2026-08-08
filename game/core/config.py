import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Tuple

logger = logging.getLogger(__name__)


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
    SPREAD_SHOT = "spread_shot"  # Leque de 5 tiros (ver SPREAD_SHOT_ANGLES)
    SPEED = "speed"
    SCORE = "score"
    RAINBOW = "rainbow"
    PIERCING_SHOT = "piercing_shot"
    MINI_SHIPS = "mini_ships"
    COOLDOWN_HASTE = "cooldown_haste"  # Reduz tempo de recarga
    TIME_STOP = "time_stop"  # Congela inimigos e projéteis
    DAMAGE_BOOST = "damage_boost"  # Dobra o dano das balas temporariamente
    CHAIN_SHOT = "chain_shot"  # Tiros encadeiam raios entre inimigos
    REPULSION_SHIELD = "repulsion_shield"  # Escudo que empurra inimigos


@dataclass(frozen=True)
class DisplayConfig:
    FULLSCREEN: bool = True
    SCREEN_WIDTH: int = 1280
    SCREEN_HEIGHT: int = 720
    FPS: int = 120
    WARNING_FONT_SIZE: int = 60


@dataclass(frozen=True)
class GameplayConfig:
    INITIAL_LIVES: int = 5
    PREPARATION_TIME: float = 5.0
    SHOOT_COOLDOWN: float = 0.20
    FIRE_RATE: float = 5.0
    BULLET_SPEED: float = 480.0
    BULLET_BASE_DAMAGE: int = 10
    # Engorda o tamanho-base do tiro de TODAS as naves (visual + hitbox), antes
    # do Giant Shot — que passa a escalar a partir do novo base.
    #
    # É um ACRÉSCIMO em pixels, não um fator: pixel é inteiro (pygame.Rect
    # trunca float, então "2.5px" na tela não existe) e +1px é o menor passo
    # que existe. Um fator escalaria o eixo comprido junto — 1.25x levava o
    # Estilete de 2x14 a 3x18, quase o dobro de área, e o hitbox é o mesmo
    # retângulo, então viraria buff de mira disfarçado de ajuste visual.
    BULLET_BASE_SIZE_BONUS: int = 1
    MINI_SHIP_BULLET_DAMAGE: int = 10
    POWERUP_SPEED: float = 100.0
    INVULN_TIME: float = 3.0
    # Invulnerabilidade curta (ms) concedida quando o escudo absorve um hit —
    # evita perder duas cargas (ou tomar dano logo após a última) por dois
    # acertos no mesmo instante/frames consecutivos.
    SHIELD_ABSORB_INVULN_MS: float = 1000.0
    LEVEL_TRANSITION_DELAY: float = 2.0
    LEVEL_TRANSITION_PENDING_DELAY: float = 2.0
    LEVEL_TRANSITION_ANIMATION_TIMEOUT: float = 1.2
    INITIAL_GAME_DELAY: float = 5.0


@dataclass(frozen=True)
class MeteorConfig:
    FAST_METEOR_SPEED: float = 320.0
    SLOW_METEOR_SPEED: float = 25.0
    MIN_METEOR_SIZE: int = 12
    MAX_METEOR_SIZE: int = 55
    DIAGONAL_CHANCE: float = 2
    FRAGMENT_SPLIT_THRESHOLD: int = 28
    FRAGMENT_COUNT_RANGE: Tuple[int, int] = (2, 5)
    FRAGMENT_SPEED_BOOST: float = 1.25
    FRAGMENT_SPREAD: float = 260.0
    GUIDED_METEOR_NORMAL_PHASES_CHANCE: float = 0.1
    GUIDED_METEOR_MAX_SPEED: float = 250.0
    GUIDED_METEOR_ACCELERATION: float = 100.0
    GUIDED_METEOR_TURN_RATE: float = 3.0
    ROCK_GLIDER_NORMAL_MIN_SIZE: int = 12
    ROCK_GLIDER_NORMAL_MAX_SIZE: int = 45
    ROCK_GLIDER_BASE_MIN_SIZE: int = 15
    ROCK_GLIDER_BASE_MAX_SIZE: int = 22
    ROCK_GLIDER_STORM_SIZE_OPTIONS: Tuple[int, ...] = (15, 16, 17, 18, 19, 20, 21, 22)
    ROCK_GLIDER_STORM_SIZE_WEIGHTS: Tuple[int, ...] = (22, 20, 17, 13, 10, 8, 6, 4)


@dataclass(frozen=True)
class AlienConfig:
    ALIEN_BULLET_SPEED: float = 200.0
    ALIEN_BULLET_MIN_RADIUS: int = 5
    ALIEN_BULLET_MAX_RADIUS: int = 8
    ALIEN_BULLET_PULSE_SPEED: float = 4.0
    ALIEN_BULLET_COLOR_CHANGE_INTERVAL: float = 0.2
    # Sprite nativo é 32×28; 64×56 é 2× exato — mantém a proporção da arte
    # (75×58 esticava só a largura, achatando o desenho) e dobra os pixels
    # sem sobra, sem linhas de espessura desigual.
    ALIEN_WIDTH: int = 52
    ALIEN_HEIGHT: int = 56
    ALIEN_SPEED_X_OPTIONS: list[int] = field(default_factory=lambda: [-100, 100])
    ALIEN_SPEED_Y: float = 60.0
    ALIEN_HEALTH: int = 15
    # Loop de voo: 4 frames × 0.2s = 0.8s por ciclo (os 12 frames antigos a
    # 0.1s davam 1.2s — com 4 frames, 0.1s deixava a animação frenética)
    ALIEN_ANIMATION_FRAME_DURATION: float = 0.2
    # Animação de morte (Sprite_Morte): 4 frames × 0.09s ≈ 0.36s, roda uma vez
    ALIEN_DEATH_FRAME_DURATION: float = 0.09
    ALIEN_DEATH_MARGIN: int = 100
    ALIEN_POINTS_VALUE: int = 150
    ALIEN_SHOOT_PAUSE_DURATION: float = 0.5
    ALIEN_POST_SHOOT_COOLDOWN: float = 0.5
    ALIEN_SHOOT_INTERVAL_MIN: float = 1.0
    ALIEN_SHOOT_INTERVAL_MAX: float = 4.0
    ALIEN_SHOOT_BURST_CHANCE: float = 0.3
    ALIEN_BURST_COUNT: int = 3
    ALIEN_BURST_INTERVAL: float = 1.0
    ALIEN_BURST_PAUSE_DURATION: float = 0.2


@dataclass(frozen=True)
class PowerUpConfig:
    POWERUP_SPAWN_INTERVAL: Tuple[float, float] = (15.0, 25.0)
    POWERUP_SIZE: int = 50
    POWERUP_SCORE_BONUS: int = 500
    SHIELD_DURATION: float = 8.0
    DOUBLE_SHOT_DURATION: float = 10.0
    SPREAD_SHOT_DURATION: float = 8.0
    # Leque do Spread Shot: deslocamentos angulares (graus) aplicados à direção
    # base do disparo, do mais externo à esquerda ao mais externo à direita. O
    # 0.0 do meio é o tiro central — a lista É a arma, mudar o leque é mudar
    # esta tupla e nada mais.
    #
    # 8°/17° é a faixa que ainda lê como "mira": a 500px de distância os
    # internos abrem ~70px e os externos ~150px para cada lado, o bastante para
    # varrer um grupo sem que o jogador perca a noção de onde o tiro central
    # vai cair. Acima de ~25° o leque vira cone de shotgun e a nave deixa de
    # acertar qualquer coisa longe.
    SPREAD_SHOT_ANGLES: Tuple[float, ...] = (-17.0, -8.0, 0.0, 8.0, 17.0)
    # Custo de cadência do leque (multiplica `attack_speed_multiplier`).
    # 5 projéteis a dano cheio e cadência cheia rendem 2,5x o DPS do tiro normal
    # contra um alvo largo — mais que o DAMAGE_BOOST, que é o power-up
    # explicitamente de dano. O -15% traz o pico para ~2,1x e deixa o leque
    # pesar diferente na mão, em vez de ser um Double Shot estritamente melhor.
    # Ganho real dele continua sendo cobertura contra grupos, não DPS de boss.
    SPREAD_SHOT_FIRE_RATE_PENALTY: float = 0.85
    SPEED_BOOST_DURATION: float = 8.0
    RAINBOW_DURATION: float = 15.0
    PIERCING_SHOT_DURATION: float = 7.0
    MINI_SHIPS_DURATION: float = 25.0
    COOLDOWN_HASTE_REDUCTION: float = 20.0
    TIME_STOP_DURATION: float = 8.0
    # Janela final do congelamento em que o jogador é avisado de que vai acabar:
    # o HUD pulsa e os inimigos tremem. Curta o bastante para virar urgência,
    # longa o bastante para dar tempo de reposicionar a nave.
    TIME_STOP_WARNING_TIME: float = 1.5
    # Rampa de saída: os congelados voltam ACELERANDO ao longo deste tempo, em
    # vez de destravarem na velocidade cheia de um frame para o outro.
    TIME_STOP_RECOVERY_DURATION: float = 3.0
    # Amplitude (px) do tremor dos congelados no auge da janela de aviso.
    # Proposital de um dígito: precisa ler como "vibrando preso", não como
    # "andando de novo".
    TIME_STOP_TREMOR_PIXELS: float = 2.0
    DAMAGE_BOOST_DURATION: float = 8.0
    DAMAGE_BOOST_MULTIPLIER: float = 2.0
    SPEED_ATTACK_MULTIPLIER: float = 2.0
    CHAIN_SHOT_DURATION: float = 8.0
    CHAIN_SHOT_MAX_JUMPS: int = 4
    CHAIN_SHOT_RADIUS: float = 220.0
    CHAIN_SHOT_DAMAGE_FACTOR: float = 0.6
    REPULSION_SHIELD_DURATION: float = 8.0
    REPULSION_SHIELD_RADIUS: float = 140.0
    REPULSION_FORCE: float = 420.0
    PIERCING_SHOT_ATTACK_SPEED_MULTIPLIER: float = 1.5
    EXPLOSIVE_SHOT_FIRE_RATE_PENALTY: float = 0.6


@dataclass(frozen=True)
class BossConfig:
    BOSS_HEALTH: int = 1000
    BOSS_FRENZY_THRESHOLD: float = 0.5
    BOSS_ENTRY_SPEED: float = 30.0
    BOSS_ENTRY_SHAKE_DURATION: float = 4.0
    BOSS_NORMAL_SPEED: float = 4.0
    BOSS_FRENZY_SPEED: float = 6.0
    BOSS_FRENZY_SHAKE_DURATION: float = 3.0
    BOSS_UPGRADE_DAMAGE_MULTIPLIER: float = 0.5
    LASER_DISTANCE: float = 800.0
    BOSS_LASER_LIFETIME: float = 2.0
    BOSS_FRENZY_LASER_LIFETIME: float = 1.5
    BOSS_CALM_ATTACK_INTERVAL: Tuple[float, float] = (2.0, 5.0)
    BOSS_FRENZY_ATTACK_INTERVAL: Tuple[float, float] = (1.0, 2.0)
    BOSS_CHARGE_DURATION: float = 1.0
    BOSS_LASER_DELAY: float = 0.5
    BOSS_FRENZY_CHARGE_DURATION: float = 0.5
    BOSS_FRENZY_LASER_DELAY: float = 0.4
    BOSS_ANIMATION_SPEED_MULTIPLIER: float = 1.0
    BOSS_FRENZY_ANIMATION_SPEED_MULTIPLIER: float = 2.0
    BOSS_PRE_WARNING_DELAY: float = 5.0
    BOSS_WARNING_DURATION: float = 5.0
    BOSS_POST_WARNING_DELAY: float = 3.0
    BOSS_MUSIC_FADE_OUT_START: float = 3.0
    BOSS_MUSIC_FADE_OUT_DURATION: float = 2.0
    BOSS_DEFEAT_SCORE: int = 10000
    BOSS_EXPLOSION_DURATION: float = 5.0
    BOSS_EXPLOSION_COUNT: int = 12
    BOSS_EXPLOSION_RADIUS: int = 60
    BOSS_EXPLOSION_SMALL_SIZE: int = 40
    BOSS_EXPLOSION_LARGE_SIZE: int = 60
    BOSS_AIM_BLINK_INTERVAL: int = 400
    BOSS_AIM_BLINK_ON_DURATION: int = 200
    BOSS_AIM_DASH_LENGTH: int = 20
    BOSS_AIM_GAP_LENGTH: int = 25
    BOSS_CHARGE_CIRCLE_MAX_RADIUS: float = 30.0
    BOSS_FRENZY_AIM_BLINK_INTERVAL: int = 200
    BOSS_FRENZY_AIM_BLINK_ON_DURATION: int = 100


@dataclass(frozen=True)
class SlimeBossConfig:
    SLIME_BOSS_HEALTH: int = 3200
    SLIME_BOSS_WIDTH_MARGIN: int = 100
    SLIME_BOSS_HEIGHT: int = 600
    SLIME_BOSS_ANIMATION_SPEED: float = 0.2
    SLIME_BOSS_MOVE_SPEED: float = 50.0
    SLIME_BOSS_MOVE_RANGE: int = 50
    SLIME_BOSS_THRESHOLD_STAGE_1: float = 0.75
    SLIME_BOSS_THRESHOLD_STAGE_3: float = 0.20
    SLIME_BOSS_ENTRY_SPEED_SLOW: float = 80.0
    SLIME_BOSS_ENTRY_SPEED_FAST: float = 300.0
    SLIME_BOSS_LEAVING_SPEED: float = 300.0
    SLIME_BOSS_STAGES: dict[SlimeBossState, StageConfig] = field(
        default_factory=lambda: {
            SlimeBossState.STAGE_1_NORMAL: StageConfig(
                max_drips=18,
                spawn_interval=0.5,
                duration=None,
                is_homing=False,
                target_y=-40,
            ),
            SlimeBossState.STAGE_2_HOMING: StageConfig(
                max_drips=18,
                spawn_interval=0.4,
                duration=15.0,
                is_homing=True,
                target_y=-40,
            ),
            SlimeBossState.STAGE_3_NORMAL: StageConfig(
                max_drips=int(15 * 2.5),
                spawn_interval=0.4 * 0.8,
                duration=None,
                is_homing=False,
                target_y=-40,
            ),
            SlimeBossState.STAGE_4_HOMING: StageConfig(
                max_drips=20,
                spawn_interval=0.3,
                duration=20.0,
                is_homing=True,
                target_y=-30,
            ),
            SlimeBossState.STAGE_5_FINAL: StageConfig(
                max_drips=20,
                spawn_interval=0.3,
                duration=None,
                is_homing=False,
                target_y=-40,
                drip_mode=SlimeDripMode.DUAL,
                max_homing_drips=8,
                homing_spawn_interval=1.5,
            ),
        }
    )
    SLIME_DRIP_RADIUS_MAX: float = 75.0
    SLIME_DRIP_MAX_ACTIVE: int = 15
    SLIME_DRIP_SPAWN_INTERVAL: float = 0.6
    SLIME_DRIP_POOL_SIZE_MULTIPLIER: int = 2
    SLIME_DRIP_SPATIAL_GRID_CELL_SIZE: int = 150
    SLIME_DRIP_DETACH_PARTICLE_SPAWN_INTERVAL: float = 0.05
    SLIME_DRIP_DETACH_PARTICLE_MAX_PER_DRIP: int = 15
    SLIME_DRIP_DETACH_PARTICLE_SIZE_START: float = 0.4
    SLIME_DRIP_DETACH_PARTICLE_SIZE_END: float = 0.1
    SLIME_DRIP_DETACH_PARTICLE_LIFETIME: float = 1.0
    SLIME_DRIP_DETACH_PARTICLE_SPEED_MIN: float = 20.0
    SLIME_DRIP_DETACH_PARTICLE_SPEED_MAX: float = 60.0
    SLIME_DRIP_PULSE_PERIOD: float = 3.0
    SLIME_DRIP_PULSE_AMPLITUDE: float = 0.15
    SLIME_DRIP_DEATH_MARGIN: int = 100
    SLIME_DRIP_COLORS: list[Tuple[int, int, int]] = field(
        default_factory=lambda: [
            (241, 187, 242),
            (166, 29, 224),
            (68, 18, 89),
        ]
    )
    SLIME_DRIP_HOMING_MAX_SPEED: float = 180.0
    SLIME_DRIP_HOMING_ACCELERATION: float = 150.0
    SLIME_DRIP_HOMING_BLEND_FACTOR: float = 0.15
    SLIME_DRIP_HOMING_AIM_OFFSET: float = 50.0
    SLIME_DRIP_HOMING_MAX_DURATION: float = 15.0
    SLIME_DRIP_HOMING_TARGET_UPDATE_INTERVAL: float = 0.4
    SLIME_DRIP_HOMING_SPAWN_Y_OFFSET: float = -50.0
    SLIME_DRIP_HOMING_SCALE_MIN: float = 0.3
    SLIME_DRIP_HOMING_SCALE_MAX: float = 0.5
    SLIME_DRIP_HOMING_DISENGAGE_DISTANCE: float = 100.0
    SLIME_DRIP_HOMING_DISENGAGE_TIME: float = 5.0
    SLIME_DRIP_HOMING_MAX_ACTIVE: int = 15
    SLIME_DRIP_HOMING_SPAWN_INTERVAL: float = 0.5
    SLIME_DRIP_MAX_ORPHAN_PARTICLES: int = 200
    SLIME_DRIP_BOSS_SPAWN_Y_OFFSET: float = -50.0


@dataclass(frozen=True)
class GiantMeteorBossConfig:
    GIANT_METEOR_BOSS_HEALTH: int = 3000
    GIANT_METEOR_BOSS_HEIGHT: int = 800
    GIANT_METEOR_BOSS_ENTRY_SPEED: float = 35.0
    GIANT_METEOR_BOSS_FALL_SPEED: float = 3.0
    GIANT_METEOR_FRAGMENT_MIN_SIZE: int = 16
    GIANT_METEOR_FRAGMENT_MAX_SIZE: int = 40
    GIANT_METEOR_HIT_FRAGMENT_CHANCE: float = 0.35
    GIANT_METEOR_HIT_FRAGMENT_COUNT: tuple[int, int] = (1, 3)
    GIANT_METEOR_DEATH_FRAGMENT_COUNT: tuple[int, int] = (8, 12)


@dataclass(frozen=True)
class StoneGolemBossConfig:
    GOLEM_HEALTH: int = 1000
    GOLEM_ENTRY_SPEED: float = 160.0
    GOLEM_SPEED: float = 75.0
    GOLEM_ATTACK_DEBRIS_SPEED: float = 200.0
    GOLEM_ORBITAL_DEBRIS_SPEED: float = 340.0
    GOLEM_DEBRIS_GRAVITY: float = 30.0
    GOLEM_EMERGE_DEBRIS_COUNT: int = 12
    GOLEM_SUBMERGE_DEBRIS_COUNT: int = 10


@dataclass(frozen=True)
class SpikeBossConfig:
    SPIKE_BOSS_HEALTH: int = 1200
    SPIKE_BOSS_FRENZY_THRESHOLD: float = 0.5
    SPIKE_BOSS_ENTRY_SPEED: float = 25.0
    SPIKE_BOSS_SPEED: float = 80.0
    SPIKE_BOSS_FRENZY_SPEED: float = 520.0
    SPIKE_BOSS_FRENZY_SHAKE_DURATION: float = 3.0
    SPIKE_BOSS_FRENZY_PAUSE_DURATION: float = 2.0
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
    SPIKE_BOSS_MOUTH_CYCLE_DURATION: float = 2.0
    SPIKE_BOSS_MOUTH_MAX_OPENING: int = 15
    SPIKE_BOSS_BODY_STRETCH: int = 8
    SPIKE_BOSS_EYE_TRACK_DURATION: float = 2.5
    SPIKE_BOSS_EYE_FRENETIC_DURATION: float = 1.0
    SPIKE_BOSS_EYE_FRENETIC_SPEED: float = 0.15
    SPIKE_BOSS_LASER_COOLDOWN: float = 8.0
    SPIKE_BOSS_LASER_CHARGE_TIME: float = 1.0
    SPIKE_BOSS_LASER_LIFETIME: float = 1.5


@dataclass(frozen=True)
class SpikeProjectileConfig:
    SPIKE_SIZE: int = 25
    SPIKE_DAMAGE: int = 1
    SPIKE_POINTS: int = 50
    SPIKE_WALL_SPACING: int = 5
    SPIKE_MAX_ATTACKING: int = 10
    SPIKE_WAVE_MIN_SIZE: int = 3
    SPIKE_WAVE_MAX_SIZE: int = 6
    SPIKE_WAVE_INTERVAL: float = 4.0
    SPIKE_FRENZY_WAVE_INTERVAL: float = 2.5
    SPIKE_MIN_ATTACH_TIME: float = 1.0
    SPIKE_MAX_ATTACH_TIME: float = 2.5
    SPIKE_TREMBLE_DURATION: float = 1.0
    SPIKE_MAX_TREMBLE: int = 5
    SPIKE_INITIAL_SPEED: float = 50.0
    SPIKE_SPEED_VARIATION: float = 30.0
    SPIKE_ACCELERATION: float = 200.0
    SPIKE_MAX_SPEED: float = 300.0
    SPIKE_MAX_SPEED_VARIATION: float = 50.0
    SPIKE_AIM_IMPRECISION: float = 100.0
    SPIKE_ROTATION_SPEED_MIN: float = 8.0
    SPIKE_ROTATION_SPEED_MAX: float = 15.0
    SPIKE_SPAWN_ANIMATION_DURATION: float = 0.4
    SPIKE_SPAWN_DELAY_MIN: float = 0.0
    SPIKE_SPAWN_DELAY_MAX: float = 2.0
    SPIKE_RESPAWN_TIME: float = 10.0
    SPIKE_LAUNCH_COOLDOWN: float = 0.2


@dataclass(frozen=True)
class FormationConfig:
    FORMATION_SPAWN_INTERVAL: Tuple[float, float] = (25.0, 35.0)
    FORMATION_ENTRY_CURVE_AMPLITUDE: float = 150.0
    FORMATION_ENTRY_CURVE_FREQUENCY: float = 1.2
    FORMATION_ENTRY_TIME_OFFSET: float = 0.25
    FORMATION_ENTRY_SPEED: float = 60.0
    FORMATION_ENTRY_CURVE_OFFSET_X: float = 100.0
    FORMATION_ENTRY_LOOP_SPEED: float = 50.0
    FORMATION_ENTRY_WAVE_SPEED: float = 65.0
    FORMATION_ENTRY_FAN_SPEED: float = 40.0
    FORMATION_ENTRY_DIAGONAL_SPEED: float = 55.0
    FORMATION_PATTERN_DURATION: float = 8.0
    FORMATION_TRANSITION_DURATION: float = 2.0
    FORMATION_CIRCLE_RADIUS: float = 100.0
    FORMATION_V_SPACING: float = 45.0
    FORMATION_SQUARE_SIZE: float = 180.0
    FORMATION_LINE_SPACING: float = 80.0
    FORMATION_DESCENT_SPEED: float = 30.0


@dataclass(frozen=True)
class VisualEffectConfig:
    WARP_SPEED_MULTIPLIER: float = 30.0
    BOSS_WARP_SPEED_MULTIPLIER: float = 15.0
    EXPLOSION_DURATION: float = 0.8
    MOUNTAIN_MAGE_WARNING_DURATION: float = 0.9
    MOUNTAIN_MAGE_COOLDOWN: float = 2.8
    MOUNTAIN_MAGE_STALAGMITE_HEALTH: int = 3
    MOUNTAIN_MAGE_STALAGMITE_MIN_HEIGHT: int = 62
    MOUNTAIN_MAGE_STALAGMITE_MAX_HEIGHT: int = 150
    # Tremor do slot ao tentar usar um poder indisponível. Curto de propósito:
    # é uma negativa, não um evento — longo viraria distração no caos. Lido
    # pela cena (arma o timer) e pelo renderer (decai a amplitude).
    UPGRADE_DENIED_SHAKE_TIME: float = 0.28
    UPGRADE_DENIED_SHAKE_AMPLITUDE: int = 5  # px de pico, no design 1280x720
    # Recusa da habilidade especial (laser do Magneto / teleguiados do Caçador
    # ainda em efeito). Mais longo que o tremor de slot porque carrega TEXTO —
    # 0.28s some antes de dar para ler, e a mensagem é justamente o que separa
    # "o comando não foi reconhecido" de "a habilidade ainda está em uso".
    ABILITY_DENIED_FEEDBACK_TIME: float = 0.65
    ABILITY_DENIED_SHAKE_AMPLITUDE: int = 4  # px de pico, no design 1280x720
    SCREEN_SHAKE_NORMAL: int = 10
    SCREEN_SHAKE_GAME_OVER: int = 15
    SCREEN_SHAKE_BOSS_DEATH: int = 25
    SCREEN_SHAKE_BOSS_DEATH_DURATION: float = 2.5
    GAME_OVER_FADE_DURATION: float = 2.0
    GAME_OVER_RESTART_DELAY: float = 1.5
    GAME_OVER_OVERLAY_ALPHA: int = 200
    WORLD_TRANSITION_CUTSCENE_DURATION: float = 1.6
    WORLD_TRANSITION_CUTSCENE_CHARGE_DURATION: float = 0.6
    WORLD_TRANSITION_CUTSCENE_LAUNCH_SPEED: float = 80.0
    WORLD_TRANSITION_CUTSCENE_LAUNCH_ACCELERATION: float = 2200.0
    BLACK_HOLE_SPEED_Y: float = -50.0
    BLACK_HOLE_INITIAL_CORE_RADIUS: float = 10.0
    BLACK_HOLE_MAX_CORE_RADIUS: float = 60.0
    BLACK_HOLE_GROWTH_RATE: float = 15.0
    BLACK_HOLE_PARTICLE_COUNT: int = 90
    BLACK_HOLE_PULL_SPEED: float = 300.0
    BLACK_HOLE_INITIAL_PULL_RADIUS: float = 250.0
    BLACK_HOLE_MAX_PULL_RADIUS: float = 800.0


@dataclass(frozen=True)
class ScoringConfig:
    BASE_POINTS: int = 5
    SIZE_BONUS_MULTIPLIER: float = 1.2


@dataclass(frozen=True)
class ParticleConfig:
    PARTICLE_ENTRY_COUNT = 3
    PARTICLE_THRUSTER_COUNT = 2
    PARTICLE_ENTRY_VELOCITY = (-80, 80)
    PARTICLE_ENTRY_LIFETIME = (0.2, 0.6)
    PARTICLE_ENTRY_SIZE = (1, 3)
    PARTICLE_THRUSTER_VELOCITY_X = (-10, 10)
    PARTICLE_THRUSTER_VELOCITY_Y = (100, 200)
    PARTICLE_THRUSTER_LIFETIME = (0.05, 0.15)
    PARTICLE_THRUSTER_SIZE = (2, 4)


@dataclass(frozen=True)
class SatelliteConfig:
    SATELLITE_POINTS: int = 300
    SATELLITE_HEALTH: int = 80
    SATELLITE_ANIMATION_SPEED: float = 0.15
    SATELLITE_TARGET_SIZE: int = 90
    SATELLITE_SPEED_Y_MIN: float = 80.0
    SATELLITE_SPEED_Y_MAX: float = 100.0
    SATELLITE_SPEED_X_MIN: float = 40.0
    SATELLITE_SPEED_X_MAX: float = 90.0
    SATELLITE_FRAGMENT_HEALTH: int = 15
    SATELLITE_FRAGMENT_POINTS: int = 100


class ConfigurationManager:
    """
    Gerencia as configurações globais do jogo agrupadas por domínio.
    Mantém compatibilidade com acesso via atributos (Config.FPS) enquanto
    permite atualizações dinâmicas e validação.
    """

    def __init__(self) -> None:
        self.display = DisplayConfig()
        self.gameplay = GameplayConfig()
        self.meteors = MeteorConfig()
        self.aliens = AlienConfig()
        self.powerups = PowerUpConfig()
        self.boss = BossConfig()
        self.slime_boss = SlimeBossConfig()
        self.giant_meteor_boss = GiantMeteorBossConfig()
        self.stone_golem_boss = StoneGolemBossConfig()
        self.spike_boss = SpikeBossConfig()
        self.spike_projectile = SpikeProjectileConfig()
        self.formations = FormationConfig()
        self.visuals = VisualEffectConfig()
        self.scoring = ScoringConfig()
        self.particles = ParticleConfig()
        self.satellite = SatelliteConfig()

        # Overrides dinâmicos (ex: resolução)
        self._overrides: dict[str, Any] = {
            "SCREEN_WIDTH": self.display.SCREEN_WIDTH,
            "SCREEN_HEIGHT": self.display.SCREEN_HEIGHT,
        }

    def __getattr__(self, name: str) -> Any:
        # 1. Verificar overrides (prioridade máxima)
        if name in self._overrides:
            return self._overrides[name]

        # 2. Verificar em todos os domínios (busca linear para compatibilidade)
        # Em um projeto maior, poderíamos usar um mapa de lookup.
        domains: tuple[object, ...] = (
            self.display,
            self.gameplay,
            self.meteors,
            self.aliens,
            self.powerups,
            self.boss,
            self.slime_boss,
            self.giant_meteor_boss,
            self.stone_golem_boss,
            self.spike_boss,
            self.spike_projectile,
            self.formations,
            self.visuals,
            self.scoring,
            self.particles,
            self.satellite,
        )
        for domain in domains:
            if hasattr(domain, name):
                return getattr(domain, name)

        raise AttributeError(f"Configuração '{name}' não encontrada em nenhum domínio.")

    def update_resolution(self, width: int, height: int) -> None:
        """Atualiza a resolução da tela em tempo de execução."""
        self._overrides["SCREEN_WIDTH"] = width
        self._overrides["SCREEN_HEIGHT"] = height
        logger.info("Resolução de configuração atualizada para %dx%d", width, height)

    @property
    def BOSS_MUSIC_SILENCE_DURATION(self) -> float:
        return self.boss.BOSS_WARNING_DURATION + self.boss.BOSS_POST_WARNING_DELAY

    def validate(self) -> list[str]:
        """
        Valida as configurações e retorna lista de erros encontrados.
        (Implementação simplificada delegando para sub-objetos se necessário)
        """
        errors: list[str] = []
        # Validação básica de ranges pode ser feita aqui ou nos domínios
        if self.display.FPS <= 0:
            errors.append("FPS deve ser positivo")
        return errors


# Instância global para o projeto
config = ConfigurationManager()


def set_screen_resolution(width: int, height: int):
    """Atualiza a resolução global."""
    config.update_resolution(width, height)
