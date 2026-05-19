import logging
import random
from collections import deque
from dataclasses import replace
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Protocol,
    Tuple,
    Type,
    TypedDict,
    Union,
    cast,
)

# ---------------------------------------------------------------------------
# Imports de entidades movidos para o topo — evita late imports em hot paths
# ---------------------------------------------------------------------------
from ..core.config import PowerUpType
from ..core.config import config as Config
from ..core.difficulty import DifficultyPreset
from ..core.levels import (
    THEME_ENEMY_REPLACEMENTS,
    THEME_FEATURES,
    DifficultyConfig,
    calculate_dynamic_enemy_cap,
)
from ..core.powerup_weights import get_powerup_weights
from ..core.time import Timer
from ..core.world_config import get_world_for_level
from ..entities.alien import Alien
from ..entities.bot_elemental import ElementalRobot
from ..entities.explosive_mine import ExplosiveMine
from ..entities.eye_enemy import EyeEnemy
from ..entities.formation import Formation, FormationPattern
from ..entities.guided_meteor import GuidedMeteor
from ..entities.meteor import Meteor
from ..entities.meteor_pool import MeteorPool
from ..entities.mountain_mage import MountainMage
from ..entities.mountain_propeller import MountainPropeller
from ..entities.powerup import PowerUp
from ..entities.rock_glider import RockGlider
from ..entities.square_minion_boss import SquareMinionBoss
from ..entities.star import Star
from ..entities.stone_sentry import StoneSentry

if TYPE_CHECKING:
    from ..systems.entity_manager import EntityManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes globais de configuração — ajuste aqui para afetar todo o spawner
# ---------------------------------------------------------------------------

# EnemySpawner — caps de inimigos especiais por tela
SPAWNER_CAP_ELEMENTAL_ROBOT: int = 1
SPAWNER_CAP_STONE_SENTRY: int = 2
SPAWNER_CAP_MOUNTAIN_MAGE: int = 1
SPAWNER_CAP_MOUNTAIN_PROPELLER: int = 3
SPAWNER_CAP_ALIEN: int = 4  # Limite máximo de Aliens simultâneos
SPAWNER_CAP_EYE_ENEMY: int = 3  # Limite máximo de EyeEnemies simultâneos
SPAWNER_CAP_FORMATIONS: int = 2  # Limite máximo de Formações ativas simultâneas
SPAWNER_STORM_ENEMY_CAP: int = 30

# EnemySpawner — spawn de minas. Pesos relativos para o número de minas spawnadas
# em cada leva: 2 é o caso comum (~59%), 3 é frequente (~29%), 5 é raro (~12%).
# random.choices normaliza, então os valores absolutos só importam pela proporção.
MINE_NUM_OPTIONS: list[int] = [2, 3, 5]
MINE_NUM_WEIGHTS: list[float] = [0.59, 0.29, 0.12]
MINE_SPAWN_CHANCE: float = 0.5  # chance extra além de spawn_intensity
MINE_MIN_DISTANCE: int = 60  # pixels mínimos entre minas na mesma leva
MINE_MAX_POSITION_ATTEMPTS: int = 10  # tentativas para achar posição válida
MINE_Y_OFFSET_MIN: float = 10.0
MINE_Y_OFFSET_MAX: float = 100.0
MINE_X_MARGIN: int = 20  # margem lateral para spawn de minas

# EnemySpawner — spawn de meteoros guiados
GUIDED_METEOR_SIZE_MIN: int = 15
GUIDED_METEOR_SIZE_MAX: int = 25
GUIDED_METEOR_SPAWN_Y: float = -30.0
GUIDED_METEOR_INITIAL_VX: float = 0.0
GUIDED_METEOR_INITIAL_VY: float = 50.0

# EnemySpawner — formações
FORMATION_MIN_DISTANCE: int = 300  # pixels mínimos entre centros de formação
FORMATION_MAX_POSITION_ATTEMPTS: int = 10
FORMATION_DEFAULT_COUNT: int = 5  # fallback quando config não especifica count
FORMATION_SCREEN_MARGIN_BUFFER: int = 100  # buffer extra ao limitar safe_margin

# EnemySpawner — spawn lateral (side scroll)
SIDE_SCROLL_SPAWN_X_OFFSET: int = 40
SIDE_SCROLL_Y_MIN: int = 60

# EnemySpawner — posições de spawn de inimigos especiais
ELEMENTAL_ROBOT_X_FRACTION_MIN: float = 0.2
ELEMENTAL_ROBOT_X_FRACTION_MAX: float = 0.8
ELEMENTAL_ROBOT_Y_FRACTION: float = 0.15
MOUNTAIN_MAGE_Y_MAX_FRACTION: float = 0.32
MOUNTAIN_MAGE_X_MIN: int = 90
MOUNTAIN_MAGE_X_MIN_FALLBACK: int = 110  # usado em max() para garantir largura mínima
MOUNTAIN_MAGE_X_MARGIN: int = 140

# EnemySpawner — formação: fallback de margem se tipo desconhecido
FORMATION_UNKNOWN_MARGIN_FALLBACK: float = 200.0

# EyeEnemy — posições de spawn
EYE_SIDE_SCROLL_Y_MIN: int = 60
EYE_NORMAL_X_MIN: int = 40
EYE_NORMAL_X_MAX_OFFSET: int = 80  # subtrai da largura da tela
EYE_NORMAL_Y_MIN: int = 40
EYE_NORMAL_Y_MAX: int = 100

# SquareMinionBoss — posições de spawn
SQUARE_MINION_SPAWN_Y: int = -50
SQUARE_MINION_X_MIN: int = 40
SQUARE_MINION_X_MAX_OFFSET: int = 80

# PowerUpSpawner
POWERUP_SPAWN_FALLBACK_COUNT: int = 1  # choices retorna lista, pegar índice 0

# StarSpawner
STAR_X_MIN: int = 40
STAR_Y_OFFSET_MIN: float = 20.0
STAR_Y_OFFSET_MAX: float = 100.0

# EnemySpawner — warm-up e rampa de intensidade para transição de mundo.
# Troca de mundo = silêncio extra + rampa mais lenta para não jogar o jogador
# direto no máximo de pressão logo na primeira fase do novo mundo.
WORLD_TRANSITION_WARMUP_EXTRA: float = 4.0   # segundos extras de silêncio pós-boss
WORLD_TRANSITION_RAMP_DURATION: float = 25.0  # segundos para atingir spawn_intensity=1.0
NORMAL_RAMP_DURATION: float = 15.0            # rampa padrão (troca de fase normal)


# ---------------------------------------------------------------------------
# Tipos / Protocols
# ---------------------------------------------------------------------------


class EnemyWithHealth(Protocol):
    """Protocol para inimigos que têm atributo health."""

    health: int
    dead: bool
    active: bool


class FormationConfig(TypedDict, total=False):
    """Configuração de um tipo de formação."""

    patterns: List[FormationPattern]
    count_range: Tuple[int, int]
    count_options: List[int]


# ---------------------------------------------------------------------------
# Configurações de formações disponíveis
# ---------------------------------------------------------------------------

FORMATION_CONFIGS: Dict[str, FormationConfig] = {
    "spiral_circle": {
        "patterns": [FormationPattern.SPIRAL_ENTRY, FormationPattern.CIRCLE],
        "count_range": (4, 6),  # Reduzido de (5, 8)
    },
    "spiral_v": {
        "patterns": [FormationPattern.SPIRAL_ENTRY, FormationPattern.V_SHAPE],
        "count_options": [3, 5],  # Reduzido de [5, 7]
    },
    "spiral_square": {
        "patterns": [FormationPattern.SPIRAL_ENTRY, FormationPattern.SQUARE],
        "count_options": [4, 8],  # Removido 12
    },
    "spiral_line": {
        "patterns": [FormationPattern.SPIRAL_ENTRY, FormationPattern.LINE],
        "count_range": (4, 6),  # Reduzido de (5, 8)
    },
    "full_cycle": {
        "patterns": [
            FormationPattern.SPIRAL_ENTRY,
            FormationPattern.CIRCLE,
            FormationPattern.V_SHAPE,
        ],
        "count_options": [4, 5],  # Reduzido de [5, 7]
    },
}


# ---------------------------------------------------------------------------
# EnemySpawner
# ---------------------------------------------------------------------------


class EnemySpawner:
    def __init__(
        self,
        level_manager: Any,
        meteor_pool: MeteorPool,
        is_initial_level: bool = False,
        difficulty_preset: DifficultyPreset = DifficultyPreset.NORMAL,
        enemy_health_multiplier: float = 1.0,
    ) -> None:
        self.level_manager = level_manager
        self.meteor_pool = meteor_pool
        self.difficulty_preset = difficulty_preset
        self.enemy_health_multiplier = enemy_health_multiplier
        self.current_level_number: int = 1
        self.level_config: Any = self.level_manager.get_level(
            self.current_level_number, self.difficulty_preset
        )
        self.stopped: bool = False

        self._validate_formation_types()

        # Sistema de intensidade gradual para spawn orgânico
        self.spawn_intensity: float = 0.0
        self._is_world_transition: bool = False  # sinaliza rampa mais lenta
        if is_initial_level:
            self.warm_up_duration: float = Config.INITIAL_GAME_DELAY
            self.warm_up_timer: float = self.warm_up_duration
        else:
            self.warm_up_duration = 0.0
            self.warm_up_timer = 0.0
            self.spawn_intensity = 1.0

        # Pré-calcular margens e entry_y de formações
        self._formation_safe_margins: Dict[
            str, Union[float, Callable[[int], float]]
        ] = {
            "spiral_circle": Config.FORMATION_CIRCLE_RADIUS,
            "spiral_v": lambda count: (count // 2) * Config.FORMATION_V_SPACING,
            "spiral_square": Config.FORMATION_SQUARE_SIZE / 2,
            "spiral_line": lambda count: (
                ((count - 1) * Config.FORMATION_LINE_SPACING) / 2
            ),
            "full_cycle": Config.FORMATION_CIRCLE_RADIUS,
        }
        self._formation_entry_y: Dict[str, float] = {
            "spiral_circle": float(Config.FORMATION_CIRCLE_RADIUS + 40),
            "spiral_v": 80.0,
            "spiral_square": float(Config.FORMATION_SQUARE_SIZE / 2 + 40),
            "spiral_line": 80.0,
            "full_cycle": float(Config.FORMATION_CIRCLE_RADIUS + 40),
        }

        # Pipeline ponderado com fallback para o modo legado
        self.use_weighted_spawn: bool = DifficultyConfig.WEIGHTED_SPAWN_ENABLED
        self.recent_enemy_types: deque[type] = deque(
            maxlen=DifficultyConfig.WEIGHTED_RECENT_MEMORY
        )
        self.weighted_telemetry_enabled: bool = (
            DifficultyConfig.WEIGHTED_SPAWN_TELEMETRY
        )
        self.weighted_telemetry_timer: float = 0.0
        self.weighted_spawn_attempts: int = 0
        self.weighted_spawn_success: int = 0
        self.weighted_spawn_blocked: int = 0
        self.weighted_spawn_by_type: dict[str, int] = {}
        self.weighted_occupancy_samples: deque[int] = deque(maxlen=768)
        self.weighted_peak_occupancy: int = 0
        self.weighted_near_cap_samples: int = 0
        self.weighted_hard_cap_samples: int = 0

        self.spawn_clock: float = 0.0
        self.last_spawn_clock: float = -9999.0
        self.last_spawn_clock_by_type: dict[str, float] = {}

        self._reset_spawn_pipeline()

        self.guided_meteor_timer = Timer(3.0)
        self.guided_meteor_timer.start()

        self.mine_spawn_timer = Timer(10.0)
        self.mine_spawn_timer.start()

        self.propeller_spawn_timer = Timer(14.0)
        self.propeller_spawn_timer.start()

        min_t, max_t = Config.FORMATION_SPAWN_INTERVAL
        self.formation_spawn_timer = Timer(random.uniform(min_t, max_t))
        self.formation_spawn_timer.start()

    # ------------------------------------------------------------------
    # Setup / configuração
    # ------------------------------------------------------------------

    def _validate_formation_types(self) -> None:
        """Filtra tipos de formação inválidos e desativa formações se necessário."""
        if not (
            self.level_config.formations_enabled and self.level_config.formation_types
        ):
            return

        invalid_types = self.level_config.validate_formation_types(
            set(FORMATION_CONFIGS.keys())
        )
        if not invalid_types:
            return

        logger.warning(
            "Level %s has invalid formation types: %s. Available: %s",
            self.level_config.level_number,
            invalid_types,
            list(FORMATION_CONFIGS.keys()),
        )
        # `level_config` é cacheada por `LevelManager`. Em vez de mutar a instância
        # (vazaria entre invocações), substitui-se a referência local por uma cópia
        # com os campos saneados.
        sanitized_types = [
            t for t in self.level_config.formation_types if t in FORMATION_CONFIGS
        ]
        if not sanitized_types:
            logger.warning(
                "No valid formation types remain — disabling formations for level %s.",
                self.level_config.level_number,
            )
            self.level_config = replace(
                self.level_config,
                formation_types=[],
                formations_enabled=False,
            )
        else:
            logger.warning("Using valid types: %s", sanitized_types)
            self.level_config = replace(
                self.level_config, formation_types=sanitized_types
            )

    def _reset_spawn_pipeline(self) -> None:
        """Recria timers para o modo ativo de spawn."""
        self.enemy_timers: Dict[Type[object], Timer] = {}
        for enemy_type in self.level_config.enemy_types:
            spawn_time = self.level_config.get_spawn_time(enemy_type)
            timer = Timer(spawn_time)
            timer.start()
            self.enemy_timers[enemy_type] = timer

        self.weighted_spawn_timer = Timer(DifficultyConfig.WEIGHTED_SPAWN_TICK)
        self.weighted_spawn_timer.start()
        self.recent_enemy_types.clear()
        self.weighted_telemetry_timer = 0.0
        self.weighted_spawn_attempts = 0
        self.weighted_spawn_success = 0
        self.weighted_spawn_blocked = 0
        self.weighted_spawn_by_type = {}
        self.weighted_occupancy_samples.clear()
        self.weighted_peak_occupancy = 0
        self.weighted_near_cap_samples = 0
        self.weighted_hard_cap_samples = 0
        self.spawn_clock = 0.0
        self.last_spawn_clock = -9999.0
        self.last_spawn_clock_by_type = {
            self._enemy_type_key(et): 0.0 for et in self.level_config.enemy_types
        }
        self._last_enemy_counts: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Helpers de cadência / gaps
    # ------------------------------------------------------------------

    @staticmethod
    def _enemy_type_key(enemy_type: type) -> str:
        aliases = {
            "Meteor": "meteor",
            "RockGlider": "rock_glider",
            "Alien": "alien",
            "EyeEnemy": "eye",
            "SquareMinionBoss": "square_minion_boss",
            "ElementalRobot": "elemental_robot",
            "StoneSentry": "stone_sentry",
            "MountainMage": "mountain_mage",
            "MountainPropeller": "mountain_propeller",
        }
        return aliases.get(enemy_type.__name__, enemy_type.__name__.lower())

    def _get_min_spawn_gap(self, enemy_type: type) -> float:
        type_key = self._enemy_type_key(enemy_type)
        base_gap = DifficultyConfig.MIN_SPAWN_GAP_BY_TYPE.get(
            type_key, DifficultyConfig.MIN_GLOBAL_SPAWN_GAP
        )
        if enemy_type in (
            ElementalRobot,
            StoneSentry,
            MountainMage,
            MountainPropeller,
        ):
            base_gap = max(base_gap, self.level_config.get_spawn_time(enemy_type))

        return base_gap * DifficultyConfig.DIFFICULTY_SPAWN_GAP_MULTIPLIER.get(
            self.difficulty_preset, 1.0
        )

    def _get_min_global_spawn_gap(self) -> float:
        return DifficultyConfig.MIN_GLOBAL_SPAWN_GAP * (
            DifficultyConfig.DIFFICULTY_SPAWN_GAP_MULTIPLIER.get(
                self.difficulty_preset, 1.0
            )
        )

    def _can_spawn_now(self, enemy_type: type) -> bool:
        if self.spawn_clock - self.last_spawn_clock < self._get_min_global_spawn_gap():
            return False
        type_key = self._enemy_type_key(enemy_type)
        last_type_spawn = self.last_spawn_clock_by_type.get(type_key, -9999.0)
        return self.spawn_clock - last_type_spawn >= self._get_min_spawn_gap(enemy_type)

    def _register_spawn(self, enemy_type: type) -> None:
        self.last_spawn_clock = self.spawn_clock
        self.last_spawn_clock_by_type[self._enemy_type_key(enemy_type)] = (
            self.spawn_clock
        )

    def _refresh_death_clocks(self, counts: dict[str, int]) -> None:
        previous_counts = self._last_enemy_counts
        for key, prev in previous_counts.items():
            if prev > 0 and counts.get(key, 0) == 0:
                self.last_spawn_clock_by_type[key] = self.spawn_clock
        previous_counts.clear()
        previous_counts.update(counts)

    # ------------------------------------------------------------------
    # Caps e contagem
    # ------------------------------------------------------------------

    def _is_storm_level(self) -> bool:
        return self.level_config.is_storm

    def _is_rock_glider_storm_level(self) -> bool:
        return self.level_config.is_rock_glider_storm

    def _get_current_enemy_cap(self) -> int:
        if self._is_storm_level():
            return SPAWNER_STORM_ENEMY_CAP
        return calculate_dynamic_enemy_cap(
            self.current_level_number, self.difficulty_preset
        )

    def _count_enemies_by_type(self, entity_manager: "EntityManager") -> dict[str, int]:
        counts: dict[str, int] = {
            "meteor": 0,
            "alien": 0,
            "eye": 0,
            "square_minion": 0,
            "elemental_robot": 0,
            "stone_sentry": 0,
            "mountain_mage": 0,
            "mountain_propeller": 0,
            "total": 0,
        }

        for enemy in entity_manager.enemies:
            if getattr(enemy, "dead", False):
                continue
            counts["total"] += 1
            if isinstance(enemy, Meteor):
                counts["meteor"] += 1
            elif isinstance(enemy, Alien):
                counts["alien"] += 1
            elif isinstance(enemy, EyeEnemy):
                counts["eye"] += 1
            elif isinstance(enemy, SquareMinionBoss):
                counts["square_minion"] += 1
            elif isinstance(enemy, ElementalRobot):
                counts["elemental_robot"] += 1
            elif isinstance(enemy, StoneSentry):
                counts["stone_sentry"] += 1
            elif isinstance(enemy, MountainMage):
                counts["mountain_mage"] += 1

        for prop in entity_manager.mountain_propellers:
            if not prop.dead:
                counts["total"] += 1
                counts["mountain_propeller"] += 1

        return counts

    def _is_hard_capped(self, enemy_type: type, counts: dict[str, int]) -> bool:
        if counts["total"] >= self._get_current_enemy_cap():
            return True
        if (
            enemy_type == ElementalRobot
            and counts["elemental_robot"] >= SPAWNER_CAP_ELEMENTAL_ROBOT
        ):
            return True
        if (
            enemy_type == StoneSentry
            and counts["stone_sentry"] >= SPAWNER_CAP_STONE_SENTRY
        ):
            return True
        if (
            enemy_type == MountainMage
            and counts["mountain_mage"] >= SPAWNER_CAP_MOUNTAIN_MAGE
        ):
            return True
        if (
            enemy_type == MountainPropeller
            and counts["mountain_propeller"] >= SPAWNER_CAP_MOUNTAIN_PROPELLER
        ):
            return True
        if enemy_type == Alien and counts["alien"] >= SPAWNER_CAP_ALIEN:
            return True
        if enemy_type == EyeEnemy and counts["eye"] >= SPAWNER_CAP_EYE_ENEMY:
            return True
        return False

    def _should_spawn_enemy(
        self,
        enemy_type: type,
        entity_manager: "EntityManager",
        counts: dict[str, int] | None = None,
    ) -> bool:
        if not DifficultyConfig.ADAPTIVE_SPAWN_ENABLED:
            return True

        if counts is None:
            counts = self._count_enemies_by_type(entity_manager)

        # Caps rígidos de instâncias únicas/duplas
        if (
            enemy_type == ElementalRobot
            and counts["elemental_robot"] >= SPAWNER_CAP_ELEMENTAL_ROBOT
        ):
            return False
        if (
            enemy_type == StoneSentry
            and counts["stone_sentry"] >= SPAWNER_CAP_STONE_SENTRY
        ):
            return False
        if (
            enemy_type == MountainMage
            and counts["mountain_mage"] >= SPAWNER_CAP_MOUNTAIN_MAGE
        ):
            return False

        max_enemies = self._get_current_enemy_cap()
        if counts["total"] >= max_enemies:
            return False

        # Redução adaptativa quando próximo do limite
        threshold = int(max_enemies * DifficultyConfig.SPAWN_REDUCTION_THRESHOLD)
        if counts["total"] >= threshold:
            ratio = (counts["total"] - threshold) / (max_enemies - threshold)
            return random.random() < 1.0 - (ratio * 0.6)

        return True

    # ------------------------------------------------------------------
    # Pipeline ponderado
    # ------------------------------------------------------------------

    def _record_pressure_sample(
        self, entity_manager: "EntityManager", counts: dict[str, int] | None = None
    ) -> None:
        if counts is None:
            counts = self._count_enemies_by_type(entity_manager)
        total = counts["total"]
        self.weighted_occupancy_samples.append(total)
        self.weighted_peak_occupancy = max(self.weighted_peak_occupancy, total)

        total_cap = self._get_current_enemy_cap()
        near_cap_threshold = int(total_cap * DifficultyConfig.SPAWN_REDUCTION_THRESHOLD)
        if total >= near_cap_threshold:
            self.weighted_near_cap_samples += 1
        if total >= total_cap:
            self.weighted_hard_cap_samples += 1

    def _get_dynamic_enemy_weights(
        self,
        entity_manager: "EntityManager",
        counts: dict[str, int] | None = None,
    ) -> dict[type, float]:
        if counts is None:
            counts = self._count_enemies_by_type(entity_manager)
        base_weights = self.level_config.get_enemy_spawn_weights()
        dynamic_weights: dict[type, float] = {}

        for enemy_type, base_weight in base_weights.items():
            if base_weight <= 0 or self._is_hard_capped(enemy_type, counts):
                continue
            repeat_count = sum(1 for t in self.recent_enemy_types if t == enemy_type)
            penalty = DifficultyConfig.WEIGHTED_REPEAT_PENALTY**repeat_count
            dynamic_weights[enemy_type] = max(0.01, base_weight * penalty)

        return dynamic_weights

    def _pick_weighted_enemy_type(
        self,
        entity_manager: "EntityManager",
        counts: dict[str, int] | None = None,
    ) -> type | None:
        weights_by_type = self._get_dynamic_enemy_weights(entity_manager, counts=counts)
        if not weights_by_type:
            return None
        enemy_types = list(weights_by_type.keys())
        weights = list(weights_by_type.values())
        return random.choices(enemy_types, weights=weights, k=1)[0]

    def _record_weighted_spawn(self, enemy_type: type) -> None:
        type_name = enemy_type.__name__
        self.weighted_spawn_by_type[type_name] = (
            self.weighted_spawn_by_type.get(type_name, 0) + 1
        )

    @staticmethod
    def _percentile(values: list[int], percentile: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        idx = max(0, min(int((len(ordered) - 1) * percentile), len(ordered) - 1))
        return float(ordered[idx])

    def _flush_weighted_telemetry(self, dt: float) -> None:
        if not self.weighted_telemetry_enabled:
            return

        self.weighted_telemetry_timer += dt
        if self.weighted_telemetry_timer < DifficultyConfig.WEIGHTED_TELEMETRY_INTERVAL:
            return

        attempts = max(1, self.weighted_spawn_attempts)
        occupancy_values = list(self.weighted_occupancy_samples)
        sample_count = max(1, len(occupancy_values))
        by_type_text = ", ".join(
            f"{name}:{count}"
            for name, count in sorted(self.weighted_spawn_by_type.items())
        )
        logger.info(
            "[WeightedSpawn] level=%s success=%.2f blocked=%.2f attempts=%s "
            "peak=%s p95=%.1f near_cap=%.2f hard_cap=%.2f dist={%s}",
            self.current_level_number,
            self.weighted_spawn_success / attempts,
            self.weighted_spawn_blocked / attempts,
            self.weighted_spawn_attempts,
            self.weighted_peak_occupancy,
            self._percentile(occupancy_values, 0.95),
            self.weighted_near_cap_samples / sample_count,
            self.weighted_hard_cap_samples / sample_count,
            by_type_text,
        )

        # Reset telemetria
        self.weighted_telemetry_timer = 0.0
        self.weighted_spawn_attempts = 0
        self.weighted_spawn_success = 0
        self.weighted_spawn_blocked = 0
        self.weighted_spawn_by_type = {}
        self.weighted_occupancy_samples.clear()
        self.weighted_peak_occupancy = 0
        self.weighted_near_cap_samples = 0
        self.weighted_hard_cap_samples = 0

    # ------------------------------------------------------------------
    # Spawn de inimigos
    # ------------------------------------------------------------------

    def _get_theme_mine_type(self) -> type[ExplosiveMine]:
        world = get_world_for_level(self.current_level_number)
        return THEME_ENEMY_REPLACEMENTS.get((world.theme, ExplosiveMine), ExplosiveMine)

    def _pick_rock_glider_size(self, storm_small_bias: bool) -> int:
        if storm_small_bias:
            return random.choices(
                Config.ROCK_GLIDER_STORM_SIZE_OPTIONS,
                weights=Config.ROCK_GLIDER_STORM_SIZE_WEIGHTS,
                k=1,
            )[0]
        return random.randint(
            Config.ROCK_GLIDER_NORMAL_MIN_SIZE, Config.ROCK_GLIDER_NORMAL_MAX_SIZE
        )

    def _spawn_enemy_of_type(
        self,
        enemy_type: type,
        entity_manager: "EntityManager",
        player_x: float | None = None,
        player_y: float | None = None,
        is_side_scroll: bool = False,
    ) -> bool:
        if enemy_type == EyeEnemy:
            return self._spawn_eye_enemy(entity_manager, is_side_scroll)

        if issubclass(enemy_type, Meteor):
            return self._spawn_meteor_type(enemy_type, entity_manager, is_side_scroll)

        if enemy_type == SquareMinionBoss:
            return self._spawn_square_minion(
                entity_manager, player_x, player_y, is_side_scroll
            )

        if enemy_type == ElementalRobot:
            return self._spawn_elemental_robot(entity_manager)

        if enemy_type == StoneSentry:
            return self._spawn_stone_sentry(entity_manager)

        if enemy_type == MountainMage:
            return self._spawn_mountain_mage(entity_manager, is_side_scroll)

        if enemy_type == MountainPropeller:
            y = random.randint(
                SIDE_SCROLL_Y_MIN, Config.SCREEN_HEIGHT - SIDE_SCROLL_Y_MIN
            )
            prop = entity_manager.spawn_mountain_propeller(y=y)
            prop.health = max(1, int(prop.health * self.enemy_health_multiplier))
            return True

        # Fallback genérico
        new_enemy = cast(EnemyWithHealth, enemy_type())
        new_enemy.health = int(new_enemy.health * self.enemy_health_multiplier)
        entity_manager.enemies.append(new_enemy)  # type: ignore[arg-type]
        return True

    def _spawn_eye_enemy(
        self, entity_manager: "EntityManager", is_side_scroll: bool
    ) -> bool:
        if is_side_scroll:
            x = Config.SCREEN_WIDTH + SIDE_SCROLL_SPAWN_X_OFFSET
            y = random.randint(
                EYE_SIDE_SCROLL_Y_MIN, Config.SCREEN_HEIGHT - EYE_SIDE_SCROLL_Y_MIN
            )
        else:
            x = random.randint(
                EYE_NORMAL_X_MIN, Config.SCREEN_WIDTH - EYE_NORMAL_X_MAX_OFFSET
            )
            y = random.randint(EYE_NORMAL_Y_MIN, EYE_NORMAL_Y_MAX)
        new_enemy = EyeEnemy(x, y)
        new_enemy.health = int(new_enemy.health * self.enemy_health_multiplier)
        entity_manager.enemies.append(new_enemy)
        return True

    def _spawn_meteor_type(
        self,
        enemy_type: type,
        entity_manager: "EntityManager",
        is_side_scroll: bool,
    ) -> bool:
        if enemy_type is RockGlider:
            return self._spawn_rock_glider(entity_manager, is_side_scroll)

        if enemy_type is Meteor:
            return self._spawn_meteor(entity_manager, is_side_scroll)

        # Subclasse de Meteor não especificada acima
        if is_side_scroll:
            size = random.randint(Config.MIN_METEOR_SIZE, Config.MAX_METEOR_SIZE)
            meteor = cast(
                EnemyWithHealth,
                enemy_type(
                    size=size,
                    x=Config.SCREEN_WIDTH + SIDE_SCROLL_SPAWN_X_OFFSET,
                    y=random.randint(
                        SIDE_SCROLL_Y_MIN, Config.SCREEN_HEIGHT - SIDE_SCROLL_Y_MIN
                    ),
                    vx=None,  # RockGlider controla velocidade horizontal internamente
                    vy=random.uniform(-50, 50),
                ),
            )
        else:
            meteor = cast(EnemyWithHealth, enemy_type())

        meteor.health = int(meteor.health * self.enemy_health_multiplier)
        entity_manager.enemies.append(meteor)  # type: ignore[arg-type]
        return True

    def _spawn_rock_glider(
        self, entity_manager: "EntityManager", is_side_scroll: bool
    ) -> bool:
        storm_bias = self._is_rock_glider_storm_level()
        glider_size = self._pick_rock_glider_size(storm_bias)

        if is_side_scroll:
            glider = entity_manager.rock_glider_pool.get(
                size=glider_size,
                x=Config.SCREEN_WIDTH + SIDE_SCROLL_SPAWN_X_OFFSET,
                y=random.randint(
                    SIDE_SCROLL_Y_MIN, Config.SCREEN_HEIGHT - SIDE_SCROLL_Y_MIN
                ),
                vx=None,
                vy=random.uniform(-50, 50),
            )
        else:
            glider = entity_manager.rock_glider_pool.get(size=glider_size)

        # Aplica multiplicador de HP do preset de forma uniforme. Mantém a
        # proporção entre rocha e bot (rocha vale o dobro do bot na contagem
        # base). O resultado é arredondado e clamped em >=1 para evitar
        # gliders com 0 HP em multiplicadores muito baixos.
        rock_hp = max(1, int(RockGlider.ROCK_MAX_HP * self.enemy_health_multiplier))
        bot_hp = max(1, int(RockGlider.BOT_MAX_HP * self.enemy_health_multiplier))
        glider.set_hp(rock_hp, bot_hp)

        entity_manager.enemies.append(glider)  # type: ignore[arg-type]
        return True

    def _spawn_meteor(
        self, entity_manager: "EntityManager", is_side_scroll: bool
    ) -> bool:
        if is_side_scroll:
            size = random.randint(Config.MIN_METEOR_SIZE, Config.MAX_METEOR_SIZE)
            meteor = self.meteor_pool.get(
                size=size,
                x=Config.SCREEN_WIDTH + SIDE_SCROLL_SPAWN_X_OFFSET,
                y=random.randint(
                    SIDE_SCROLL_Y_MIN, Config.SCREEN_HEIGHT - SIDE_SCROLL_Y_MIN
                ),
                vx=-random.uniform(150, 300),
                vy=random.uniform(-50, 50),
            )
        else:
            meteor = self.meteor_pool.get()

        meteor.health = int(meteor.health * self.enemy_health_multiplier)
        entity_manager.enemies.append(meteor)  # type: ignore[arg-type]
        return True

    def _spawn_square_minion(
        self,
        entity_manager: "EntityManager",
        player_x: float | None,
        player_y: float | None,
        is_side_scroll: bool,
    ) -> bool:
        if player_x is None or player_y is None:
            return False
        if is_side_scroll:
            x = Config.SCREEN_WIDTH + SIDE_SCROLL_SPAWN_X_OFFSET
            y = random.randint(
                SIDE_SCROLL_Y_MIN, Config.SCREEN_HEIGHT - SIDE_SCROLL_Y_MIN
            )
        else:
            x = random.randint(
                SQUARE_MINION_X_MIN, Config.SCREEN_WIDTH - SQUARE_MINION_X_MAX_OFFSET
            )
            y = SQUARE_MINION_SPAWN_Y
        new_enemy = SquareMinionBoss(x, y, player_x, player_y)
        new_enemy.health = int(new_enemy.health * self.enemy_health_multiplier)
        entity_manager.enemies.append(new_enemy)
        return True

    def _spawn_elemental_robot(self, entity_manager: "EntityManager") -> bool:
        spawn_x = random.randint(
            int(Config.SCREEN_WIDTH * ELEMENTAL_ROBOT_X_FRACTION_MIN),
            int(Config.SCREEN_WIDTH * ELEMENTAL_ROBOT_X_FRACTION_MAX),
        )
        target_y = Config.SCREEN_HEIGHT * ELEMENTAL_ROBOT_Y_FRACTION
        robot = ElementalRobot(
            spawn_x,
            target_y,
            difficulty_multiplier=self.enemy_health_multiplier,
        )
        entity_manager.enemies.append(robot)
        return True

    def _spawn_stone_sentry(self, entity_manager: "EntityManager") -> bool:
        new_enemy = StoneSentry()
        new_enemy.health = int(new_enemy.health * self.enemy_health_multiplier)
        entity_manager.enemies.append(new_enemy)
        return True

    def _spawn_mountain_mage(
        self, entity_manager: "EntityManager", is_side_scroll: bool
    ) -> bool:
        y_max = int(Config.SCREEN_HEIGHT * MOUNTAIN_MAGE_Y_MAX_FRACTION)
        if is_side_scroll:
            x = Config.SCREEN_WIDTH + SIDE_SCROLL_SPAWN_X_OFFSET
            y = random.randint(SIDE_SCROLL_Y_MIN, y_max)
        else:
            x = random.randint(
                MOUNTAIN_MAGE_X_MIN,
                max(
                    MOUNTAIN_MAGE_X_MIN_FALLBACK,
                    Config.SCREEN_WIDTH - MOUNTAIN_MAGE_X_MARGIN,
                ),
            )
            y = random.randint(SIDE_SCROLL_Y_MIN, y_max)
        new_enemy = MountainMage(x, y)
        new_enemy.health = int(new_enemy.health * self.enemy_health_multiplier)
        entity_manager.enemies.append(new_enemy)
        return True

    # ------------------------------------------------------------------
    # Update — legado e ponderado
    # ------------------------------------------------------------------

    def _update_legacy_enemy_spawn(
        self,
        dt: float,
        entity_manager: "EntityManager",
        player_x: float | None,
        player_y: float | None,
        is_side_scroll: bool,
        counts: dict[str, int] | None = None,
    ) -> None:
        for enemy_type, timer in self.enemy_timers.items():
            timer.update(dt)
            if not timer.done():
                continue
            timer.start()

            if random.random() >= self.spawn_intensity:
                continue
            if not self._should_spawn_enemy(enemy_type, entity_manager, counts=counts):
                continue
            if not self._can_spawn_now(enemy_type):
                continue

            self._spawn_enemy_of_type(
                enemy_type,
                entity_manager,
                player_x=player_x,
                player_y=player_y,
                is_side_scroll=is_side_scroll,
            )
            self._register_spawn(enemy_type)

    def _update_weighted_enemy_spawn(
        self,
        dt: float,
        entity_manager: "EntityManager",
        player_x: float | None,
        player_y: float | None,
        is_side_scroll: bool,
        counts: dict[str, int] | None = None,
    ) -> None:
        self.weighted_spawn_timer.update(dt)
        if not self.weighted_spawn_timer.done():
            return

        self.weighted_spawn_attempts += 1

        if random.random() >= self.spawn_intensity:
            self.weighted_spawn_blocked += 1
            self.weighted_spawn_timer.start()
            return

        enemy_type = self._pick_weighted_enemy_type(entity_manager, counts=counts)
        if enemy_type is None or not self._should_spawn_enemy(
            enemy_type, entity_manager, counts=counts
        ):
            self.weighted_spawn_blocked += 1
            self.weighted_spawn_timer.start()
            return

        if not self._can_spawn_now(enemy_type):
            self.weighted_spawn_blocked += 1
            self.weighted_spawn_timer.start()
            return

        did_spawn = self._spawn_enemy_of_type(
            enemy_type,
            entity_manager,
            player_x=player_x,
            player_y=player_y,
            is_side_scroll=is_side_scroll,
        )
        if did_spawn:
            self.weighted_spawn_success += 1
            self._record_weighted_spawn(enemy_type)
            self.recent_enemy_types.append(enemy_type)
            self._register_spawn(enemy_type)
        else:
            self.weighted_spawn_blocked += 1

        self.weighted_spawn_timer.start()

    # ------------------------------------------------------------------
    # Update principal
    # ------------------------------------------------------------------

    def update(
        self,
        dt: float,
        entity_manager: "EntityManager",
        player_x: float | None = None,
        player_y: float | None = None,
        is_side_scroll: bool = False,
    ) -> None:
        if self.stopped:
            return

        self.spawn_clock += dt
        # Conta inimigos uma única vez por frame e propaga para os consumidores.
        counts = self._count_enemies_by_type(entity_manager)
        self._refresh_death_clocks(counts)

        # Warm-up: mantém intensidade em 0 sem early return (timers precisam atualizar)
        if self.warm_up_timer > 0:
            self.warm_up_timer -= dt
            self.spawn_intensity = 0.0
        else:
            # Rampa de intensidade orgânica: de 0.1 a 1.0 após o warmup.
            # Troca de mundo usa rampa mais lenta para não sobrecarregar o jogador
            # logo nas primeiras fases do novo mundo.
            ramp_duration = (
                WORLD_TRANSITION_RAMP_DURATION
                if self._is_world_transition
                else NORMAL_RAMP_DURATION
            )
            ramp_elapsed = abs(self.warm_up_timer)
            self.spawn_intensity = min(1.0, 0.1 + (ramp_elapsed / ramp_duration) * 0.9)
            self.warm_up_timer -= dt  # Continua decrementando para a rampa funcionar

        # Spawn principal (ponderado ou legado)
        if self.use_weighted_spawn:
            self._record_pressure_sample(entity_manager, counts=counts)
            self._update_weighted_enemy_spawn(
                dt,
                entity_manager,
                player_x,
                player_y,
                is_side_scroll,
                counts=counts,
            )
            self._flush_weighted_telemetry(dt)
        else:
            self._update_legacy_enemy_spawn(
                dt,
                entity_manager,
                player_x,
                player_y,
                is_side_scroll,
                counts=counts,
            )

        self._update_mine_spawner(dt, entity_manager, counts=counts)
        self._update_propeller_spawner(dt, entity_manager, counts=counts)
        self._update_formation_spawner(dt, entity_manager, counts=counts)
        self._update_guided_meteor_spawner(
            dt, entity_manager, player_x, player_y, counts=counts
        )

    def _update_mine_spawner(
        self,
        dt: float,
        entity_manager: "EntityManager",
        counts: dict[str, int] | None = None,
    ) -> None:
        del counts
        if not self.level_config.mines_enabled:
            return

        self.mine_spawn_timer.update(dt)
        if not self.mine_spawn_timer.done():
            return

        self.mine_spawn_timer.start()
        if (
            random.random() >= self.spawn_intensity
            or random.random() >= MINE_SPAWN_CHANCE
        ):
            return

        mine_type = self._get_theme_mine_type()
        num_mines = random.choices(MINE_NUM_OPTIONS, weights=MINE_NUM_WEIGHTS, k=1)[0]
        positions: list[int] = []

        for _ in range(num_mines):
            for _ in range(MINE_MAX_POSITION_ATTEMPTS):
                x = random.randint(MINE_X_MARGIN, Config.SCREEN_WIDTH - MINE_X_MARGIN)
                if all(abs(x - px) > MINE_MIN_DISTANCE for px in positions):
                    positions.append(x)
                    entity_manager.enemies.append(
                        mine_type(
                            x=x, y=-random.uniform(MINE_Y_OFFSET_MIN, MINE_Y_OFFSET_MAX)
                        )
                    )
                    break

    def _update_propeller_spawner(
        self,
        dt: float,
        entity_manager: "EntityManager",
        counts: dict[str, int] | None = None,
    ) -> None:
        del counts
        world = get_world_for_level(self.current_level_number)
        if "propellers" not in THEME_FEATURES.get(world.theme, set()):
            return
        if MountainPropeller not in self.level_config.enemy_spawn_config:
            return

        self.propeller_spawn_timer.update(dt)
        if not self.propeller_spawn_timer.done():
            return

        self.propeller_spawn_timer.start()
        if (
            random.random() < self.spawn_intensity
            and len(entity_manager.mountain_propellers) < SPAWNER_CAP_MOUNTAIN_PROPELLER
        ):
            prop = entity_manager.spawn_mountain_propeller()
            prop.health = max(1, int(prop.health * self.enemy_health_multiplier))

    def _update_formation_spawner(
        self,
        dt: float,
        entity_manager: "EntityManager",
        counts: dict[str, int] | None = None,
    ) -> None:
        del counts
        if not self.level_config.formations_enabled:
            return
        world = get_world_for_level(self.current_level_number)
        if "formations" not in THEME_FEATURES.get(world.theme, set()):
            return

        self.formation_spawn_timer.update(dt)
        if not self.formation_spawn_timer.done():
            return

        # Reinicia com intervalo aleatório (comportamento original mantido)
        min_t, max_t = Config.FORMATION_SPAWN_INTERVAL
        self.formation_spawn_timer = Timer(random.uniform(min_t, max_t))
        self.formation_spawn_timer.start()

        if random.random() >= self.spawn_intensity:
            return

        # Aplicar limite máximo de formações ativas
        if len(entity_manager.formations) >= SPAWNER_CAP_FORMATIONS:
            return

        formation_type = self.level_config.get_random_formation_type()
        if not formation_type:
            return

        formation_cfg = FORMATION_CONFIGS[formation_type]
        patterns = formation_cfg.get(
            "patterns", [FormationPattern.SPIRAL_ENTRY, FormationPattern.CIRCLE]
        )

        if "count_options" in formation_cfg:
            count = random.choice(formation_cfg["count_options"])
        elif "count_range" in formation_cfg:
            lo, hi = formation_cfg["count_range"]
            count = random.randint(lo, hi)
        else:
            count = FORMATION_DEFAULT_COUNT

        margin_value = self._formation_safe_margins.get(
            formation_type, FORMATION_UNKNOWN_MARGIN_FALLBACK
        )
        safe_margin = float(
            margin_value(count) if callable(margin_value) else margin_value
        )
        safe_margin = min(
            safe_margin, Config.SCREEN_WIDTH / 2 - FORMATION_SCREEN_MARGIN_BUFFER
        )

        # Tentar posição que não sobreponha formações existentes
        existing_xs = [f.center_x for f in entity_manager.formations]
        entry_x: int | None = None
        for _ in range(FORMATION_MAX_POSITION_ATTEMPTS):
            candidate = random.randint(
                int(safe_margin), int(Config.SCREEN_WIDTH - safe_margin)
            )
            if all(abs(candidate - ex) >= FORMATION_MIN_DISTANCE for ex in existing_xs):
                entry_x = candidate
                break
        if entry_x is None:
            entry_x = random.randint(
                int(safe_margin), int(Config.SCREEN_WIDTH - safe_margin)
            )

        entry_y = float(self._formation_entry_y.get(formation_type, 80.0))
        entity_manager.formations.append(
            Formation(Alien, count, entry_x, entry_y, patterns)
        )

    def _update_guided_meteor_spawner(
        self,
        dt: float,
        entity_manager: "EntityManager",
        player_x: float | None,
        player_y: float | None,
        counts: dict[str, int] | None = None,
    ) -> None:
        del counts
        world = get_world_for_level(self.current_level_number)
        if "guided_meteors" not in THEME_FEATURES.get(world.theme, set()):
            return
        if Meteor not in self.level_config.enemy_types:
            return
        if player_x is None or player_y is None:
            return

        self.guided_meteor_timer.update(dt)
        if not self.guided_meteor_timer.done():
            return
        self.guided_meteor_timer.start()

        if random.random() >= self.spawn_intensity:
            return
        if random.random() >= Config.GUIDED_METEOR_NORMAL_PHASES_CHANCE:
            return

        guided = GuidedMeteor(
            size=random.randint(GUIDED_METEOR_SIZE_MIN, GUIDED_METEOR_SIZE_MAX),
            x=random.randint(0, Config.SCREEN_WIDTH),
            y=GUIDED_METEOR_SPAWN_Y,
            vx=GUIDED_METEOR_INITIAL_VX,
            vy=GUIDED_METEOR_INITIAL_VY,
            target_x=player_x,
            target_y=player_y,
        )
        entity_manager.enemies.append(guided)

    # ------------------------------------------------------------------
    # Controle de ciclo de vida
    # ------------------------------------------------------------------

    def stop(self) -> None:
        self.stopped = True

    def set_level(
        self,
        level_number: int,
        is_world_transition: bool = False,
        level_config: Any | None = None,
    ) -> None:
        self.current_level_number = level_number
        # Se um LevelConfig pré-ajustado (ex: com meta-progression aplicado) for
        # fornecido, usá-lo diretamente em vez de recalcular do zero. Isso garante
        # que o ajuste adaptativo do PerformanceAnalyzer chegue de fato ao spawner.
        self.level_config = (
            level_config
            if level_config is not None
            else self.level_manager.get_level(self.current_level_number, self.difficulty_preset)
        )
        self.stopped = False
        self._is_world_transition = is_world_transition
        # Troca de mundo: warm-up estendido para dar ao jogador tempo de respirar
        # antes que o novo mundo ganhe pressão máxima.
        extra = WORLD_TRANSITION_WARMUP_EXTRA if is_world_transition else 0.0
        self.warm_up_timer = Config.PREPARATION_TIME + extra
        self.spawn_intensity = 0.0
        self._reset_spawn_pipeline()
        self.guided_meteor_timer.start()


# ---------------------------------------------------------------------------
# PowerUpSpawner
# ---------------------------------------------------------------------------


class PowerUpSpawner:
    def __init__(self, difficulty: DifficultyPreset = DifficultyPreset.NORMAL) -> None:
        from ..core.difficulty import DifficultySettings

        self.difficulty = difficulty
        settings = DifficultySettings.get_settings(difficulty)
        # >1 = mais frequente (intervalo menor). Casual=1.3, Pesadelo=0.5.
        self._spawn_rate_multiplier: float = settings["powerup_spawn_rate_multiplier"]
        self._reset_timer()

    def _select_powerup_by_rarity(self) -> PowerUpType:
        powerup_weights = get_powerup_weights(self.difficulty)
        return random.choices(
            list(powerup_weights.keys()), weights=list(powerup_weights.values())
        )[0]

    def _reset_timer(self) -> None:
        min_t, max_t = Config.POWERUP_SPAWN_INTERVAL
        # Divide pelo multiplicador: rate>1 (Casual) → intervalo menor; rate<1
        # (Hardcore/Pesadelo) → intervalo maior. Clamp para evitar valores
        # degenerados caso o preset venha com multiplicador zero/negativo.
        mult = max(0.1, self._spawn_rate_multiplier)
        interval = random.uniform(min_t, max_t) / mult
        self.timer = Timer(interval)
        self.timer.start()

    def update(self, dt: float, powerups: List[PowerUp]) -> None:
        self.timer.update(dt)
        if self.timer.done():
            powerups.append(PowerUp(self._select_powerup_by_rarity()))
            self._reset_timer()
        powerups[:] = [p for p in powerups if not p.is_off_screen()]


# ---------------------------------------------------------------------------
# StarSpawner
# ---------------------------------------------------------------------------


class StarSpawner:
    def __init__(self) -> None:
        self.kill_counter: int = 0
        self.kill_threshold: int = getattr(Config, "STAR_SPAWN_KILL_THRESHOLD", 200)

    def update(self, stars: List[Star]) -> None:
        """No-op: estrelas só aparecem por abates, não por timer."""

    def add_kills(self, count: int, stars: List[Star]) -> None:
        """Acumula abates e spawna uma estrela ao atingir o limiar."""
        if count <= 0:
            return
        self.kill_counter += count
        if self.kill_counter >= self.kill_threshold:
            self.kill_counter = 0
            x = random.randint(STAR_X_MIN, Config.SCREEN_WIDTH - STAR_X_MIN)
            y = -random.uniform(STAR_Y_OFFSET_MIN, STAR_Y_OFFSET_MAX)
            stars.append(Star(x, y))