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
from ..core.world_config import WorldTheme, get_world_for_level
from ..entities.alien import Alien
from ..entities.bot_elemental import ElementalRobot
from ..entities.explosive_mine import ExplosiveMine
from ..entities.eye_enemy import EyeEnemy
from ..entities.formation import Formation, FormationPattern
from ..entities.guided_meteor import GuidedMeteor
from ..entities.Inimigos_Tema_Cidade.city_drone import CityDrone
from ..entities.Inimigos_Tema_Cidade.cyber_captor import CyberCaptor
from ..entities.Inimigos_Tema_Cidade.cyber_tank import CyberTank
from ..entities.Inimigos_Tema_Cidade.interceptor_squad import InterceptorSquad
from ..entities.Inimigos_Tema_Cidade.jammer_node import JammerNode
from ..entities.Inimigos_Tema_Cidade.mirror_pylon import MirrorPylon
from ..entities.Inimigos_Tema_Cidade.mortar_drone import MortarDrone
from ..entities.Inimigos_Tema_Cidade.cargo_carrier import CargoCarrier
from ..entities.Inimigos_Tema_Cidade.sapper_drone import SapperDrone
from ..entities.Inimigos_Tema_Cidade.splitter_tank import SplitterTank
from ..entities.Inimigos_Tema_Cidade.neon_sniper import NeonSniper
from ..entities.Inimigos_Tema_Cidade.police_interceptor import PoliceInterceptor
from ..entities.Inimigos_Tema_Cidade.tesla_link import TeslaLink
from ..entities.Inimigos_Tema_Cidade.tesla_twin import TeslaTwin
from ..entities.meteor import Meteor
from ..entities.meteor_pool import MeteorPool
from ..entities.mountain_mage import MountainMage
from ..entities.mountain_propeller import MountainPropeller
from ..entities.powerup import PowerUp
from ..entities.rock_glider import RockGlider
from ..entities.satellite import Satellite, SatelliteFragment
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
SPAWNER_CAP_CITY_DRONE: int = 16  # Limite de City Drones simultâneos (enxame)
CITY_DRONE_CLUSTER_MIN: int = 6  # Tamanho mínimo da leva (clustering)
CITY_DRONE_CLUSTER_MAX: int = 10  # Tamanho máximo da leva
SPAWNER_CAP_NEON_SNIPER: int = 3  # Sentinelas de longa distância (perch units)
SPAWNER_CAP_POLICE_INTERCEPTOR: int = 4  # Perseguidores (spawnam em duplas)
SPAWNER_CAP_CYBER_TANK: int = 1  # Colosso "gatekeeper" — sempre sozinho
SPAWNER_CAP_CYBER_CAPTOR: int = 2  # Armadilhas de energia (orbitam o topo)
SPAWNER_CAP_JAMMER: int = 2  # Nós de interferência (orbitam o topo, suprimem tiros)
SPAWNER_CAP_MORTAR: int = 2  # Artilheiros (perch no alto, bombardeio de área)
SPAWNER_CAP_CARGO_CARRIER: int = 1  # Cargueiro (transporte de tropas, larga caixas)
SPAWNER_CAP_SPLITTER: int = 1  # Splitter Tanks (conta filhotes → limita o enxame)
SPAWNER_CAP_SAPPER: int = 2  # Rebocadores (suporte de blindagem)
SPAWNER_CAP_MIRROR: int = 1  # Mirror Pylons (refletem tiros — sempre sozinho)
SPAWNER_CAP_TESLA_TWIN: int = 2  # Barreira vertical: 1 par (2 unidades) por vez
SPAWNER_CAP_ALIEN: int = 4  # Limite máximo de Aliens simultâneos
SPAWNER_CAP_EYE_ENEMY: int = 3  # Limite máximo de EyeEnemies simultâneos
SPAWNER_CAP_SATELLITE: int = 5  # Limite máximo de Satélites simultâneos
SPAWNER_CAP_FORMATIONS: int = 2  # Limite máximo de Formações ativas simultâneas
SPAWNER_STORM_ENEMY_CAP: int = 30

# Hazards/modificadores de encontro (minas, geodes, armadilhas) — categoria
# COMPLEMENTAR. Não são arquétipos principais: não entram na pirâmide de variedade
# (não estão no `enemy_spawn_config`) NEM ocupam vaga no cap de população (`total`).
# Sua presença é decidida por lógica própria (`_update_mine_spawner`). MountainGeode
# e as minas temáticas são subclasses de ExplosiveMine → cobertas por isinstance;
# armadilhas futuras devem herdar de ExplosiveMine ou ser adicionadas aqui.
HAZARD_ENEMY_TYPES: tuple[type, ...] = (ExplosiveMine,)

# EnemySpawner — escala de HP de inimigos COMUNS em coop. Por jogador extra,
# soma este fator ao multiplicador de vida (ex.: 2 jogadores = +15%). Fica
# abaixo do boss (+40%, `PlayingScene._COOP_BOSS_HP_PER_EXTRA_PLAYER`): o boss
# concentra o ajuste; nos comuns o coop já pesa via cadência/cap/meta de abates.
# Propagado até a entidade no spawn (§11), recalculado em `set_player_count`.
SPAWNER_COOP_ENEMY_HP_PER_EXTRA_PLAYER: float = 0.15

# Ramp suave de HP por estágio DENTRO do mundo, resetando a cada mundo novo.
# +0% no estágio X-1 → +SPAWNER_WORLD_HP_RAMP no último estágio (interpolado por
# stage_progress). Dá progressão de poder intra-mundo sem virar bullet-sponge nem
# compor pela campanha (reseta por mundo), coerente com "cada mundo é uma
# introdução fresca" (ver memory/enemy-variety-intro-curve). Propagado até a
# entidade via `enemy_health_multiplier` no spawn (§11).
SPAWNER_WORLD_HP_RAMP: float = 0.15

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
WORLD_TRANSITION_WARMUP_EXTRA: float = 4.0  # segundos extras de silêncio pós-boss
WORLD_TRANSITION_RAMP_DURATION: float = (
    25.0  # segundos para atingir spawn_intensity=1.0
)
NORMAL_RAMP_DURATION: float = 15.0  # rampa padrão (troca de fase normal)

# DIRETOR DE ONDAS — faixa base de duração do REST (respiro entre ondas), em
# segundos. Encurtada do antigo (4.0, 7.0) para tirar o "buraco" entre ciclos.
# A duração efetiva escala pela dificuldade via DIFFICULTY_SPAWN_GAP_MULTIPLIER
# (mesmo multiplicador dos gaps de spawn): presets mais difíceis dão menos
# respiro. Ver `EnemySpawner._roll_rest_duration`.
DIRECTOR_REST_DURATION_RANGE: tuple[float, float] = (2.5, 4.5)


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
        aggressiveness_multiplier: float = 1.0,
        player_count: int = 1,
    ) -> None:
        self.level_manager = level_manager
        self.meteor_pool = meteor_pool
        self.difficulty_preset = difficulty_preset
        # HP base vem do preset de dificuldade; o multiplicador efetivo aplicado
        # às entidades soma a escala de coop por cima (ver
        # `_recompute_enemy_health_multiplier`). Guardamos o base separado para
        # poder recalcular quando P2 entra/sai mid-game.
        self._base_enemy_health_multiplier = enemy_health_multiplier
        self.aggressiveness_multiplier = aggressiveness_multiplier
        # Player count alimenta o cap dinâmico de inimigos em tela (coop ganha
        # +20% por jogador extra) e o HP de inimigos comuns (+15% por extra).
        # Atualizado via `set_player_count` quando P2 entra/sai mid-game.
        self.player_count = max(1, player_count)
        # current_level_number antes do recompute: o ramp de HP por estágio o lê.
        self.current_level_number: int = 1
        # Define `self.enemy_health_multiplier` (efetivo = base × coop × ramp estágio).
        self._recompute_enemy_health_multiplier()
        self.level_config: Any = self.level_manager.get_level(
            self.current_level_number, self.difficulty_preset
        )
        self.stopped: bool = False
        self.inverted_vertical: bool = False

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

        # Pipeline ponderado
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

        # ------------------------------------------------------------------
        # DIRETOR DE ONDAS (PACING FSM)
        # ------------------------------------------------------------------
        # Estados: BUILDUP (crescimento), PEAK (horda), REST (respiro)
        self.director_state: str = "BUILDUP"
        self.director_timer: float = 0.0
        self.director_intensity_mult: float = 1.0  # Multiplicador na cadência global

        # Duração base dos ciclos (com variação randômica)
        self._dir_buildup_dur = random.uniform(8.0, 12.0)
        self._dir_peak_dur = random.uniform(12.0, 18.0)
        self._dir_rest_dur = self._roll_rest_duration()

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
        """Recria timers para o spawn ponderado."""
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
            "Satellite": "satellite",
            "CityDrone": "city_drone",
            "NeonSniper": "neon_sniper",
            "PoliceInterceptor": "police_interceptor",
            "CyberTank": "cyber_tank",
            "CyberCaptor": "cyber_captor",
            "TeslaTwin": "tesla_twin",
            "JammerNode": "jammer",
            "MortarDrone": "mortar",
            "CargoCarrier": "cargo_carrier",
            "SplitterTank": "splitter",
            "SapperDrone": "sapper",
            "MirrorPylon": "mirror",
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
            NeonSniper,
            PoliceInterceptor,
            CyberTank,
            CyberCaptor,
            TeslaTwin,
            JammerNode,
            MortarDrone,
            CargoCarrier,
            SplitterTank,
            SapperDrone,
            MirrorPylon,
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

    def _roll_rest_duration(self) -> float:
        """Sorteia a duração do REST (respiro entre ondas) já escalada pela
        dificuldade. Reusa o multiplicador dos gaps de spawn — presets mais
        difíceis encurtam o respiro (menos folga para o jogador)."""
        lo, hi = DIRECTOR_REST_DURATION_RANGE
        difficulty_mult = DifficultyConfig.DIFFICULTY_SPAWN_GAP_MULTIPLIER.get(
            self.difficulty_preset, 1.0
        )
        return random.uniform(lo, hi) * difficulty_mult

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
            self.current_level_number,
            self.difficulty_preset,
            player_count=self.player_count,
        )

    def set_player_count(self, count: int) -> None:
        """Atualiza player_count em tempo real (P2 entra/sai mid-game).

        Diferente de `LevelProgressionController.set_player_count`, este
        afeta o cap dinâmico imediatamente — não espera transição de fase.
        Justificativa: o cap é consultado a cada spawn tentado, então
        passar a permitir mais inimigos na tela logo após P2 entrar
        casa com a expectativa do jogador.

        O HP de inimigos comuns também reescala imediatamente — os próximos
        spawns nascem com a vida do novo player_count (entidades já em campo
        mantêm a vida com que nasceram).
        """
        self.player_count = max(1, int(count))
        self._recompute_enemy_health_multiplier()

    def _coop_hp_multiplier(self) -> float:
        """Fator de HP de coop para inimigos comuns (1.0 = solo)."""
        return 1.0 + SPAWNER_COOP_ENEMY_HP_PER_EXTRA_PLAYER * max(
            0, self.player_count - 1
        )

    def _stage_hp_multiplier(self) -> float:
        """Ramp suave de HP por estágio dentro do mundo, resetando a cada mundo.

        +0% no X-1 → +SPAWNER_WORLD_HP_RAMP no último estágio (linear em
        stage_progress). Inimigos invocados (filhotes/fragmentos) herdam o mesmo
        `enemy_health_multiplier`, então o ramp os acompanha.
        """
        world = get_world_for_level(self.current_level_number)
        total = world.total_stages
        if total <= 1:
            return 1.0
        stage = world.get_stage_number(self.current_level_number)
        progress = max(0.0, min(1.0, (stage - 1) / (total - 1)))
        return 1.0 + SPAWNER_WORLD_HP_RAMP * progress

    def _recompute_enemy_health_multiplier(self) -> None:
        """Recompõe o HP efetivo = base (preset) × coop × ramp de estágio (mundo)."""
        self.enemy_health_multiplier = (
            self._base_enemy_health_multiplier
            * self._coop_hp_multiplier()
            * self._stage_hp_multiplier()
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
            "satellite": 0,
            "city_drone": 0,
            "neon_sniper": 0,
            "police_interceptor": 0,
            "cyber_tank": 0,
            "cyber_captor": 0,
            "tesla_twin": 0,
            "jammer": 0,
            "mortar": 0,
            "cargo_carrier": 0,
            "splitter": 0,
            "sapper": 0,
            "mirror": 0,
            "total": 0,
        }

        for enemy in entity_manager.enemies:
            if getattr(enemy, "dead", False):
                continue
            # Hazards (minas/geodes/armadilhas) são modificadores de encontro:
            # não contam no `total` p/ não roubar vaga dos arquétipos do tema.
            if isinstance(enemy, HAZARD_ENEMY_TYPES):
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
            elif isinstance(enemy, Satellite):
                counts["satellite"] += 1
            elif isinstance(enemy, CityDrone):
                counts["city_drone"] += 1
            elif isinstance(enemy, NeonSniper):
                counts["neon_sniper"] += 1
            elif isinstance(enemy, PoliceInterceptor):
                counts["police_interceptor"] += 1
            elif isinstance(enemy, CyberTank):
                counts["cyber_tank"] += 1
            elif isinstance(enemy, CyberCaptor):
                counts["cyber_captor"] += 1
            elif isinstance(enemy, TeslaTwin):
                counts["tesla_twin"] += 1
            elif isinstance(enemy, JammerNode):
                counts["jammer"] += 1
            elif isinstance(enemy, MortarDrone):
                counts["mortar"] += 1
            elif isinstance(enemy, CargoCarrier):
                counts["cargo_carrier"] += 1
            elif isinstance(enemy, SplitterTank):
                counts["splitter"] += 1
            elif isinstance(enemy, SapperDrone):
                counts["sapper"] += 1
            elif isinstance(enemy, MirrorPylon):
                counts["mirror"] += 1

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
        if enemy_type == Satellite and counts["satellite"] >= SPAWNER_CAP_SATELLITE:
            return True
        if enemy_type == CityDrone and counts["city_drone"] >= SPAWNER_CAP_CITY_DRONE:
            return True
        if enemy_type == NeonSniper and counts["neon_sniper"] >= SPAWNER_CAP_NEON_SNIPER:
            return True
        if (
            enemy_type == PoliceInterceptor
            and counts["police_interceptor"] >= SPAWNER_CAP_POLICE_INTERCEPTOR
        ):
            return True
        if enemy_type == CyberTank and counts["cyber_tank"] >= SPAWNER_CAP_CYBER_TANK:
            return True
        if (
            enemy_type == CyberCaptor
            and counts["cyber_captor"] >= SPAWNER_CAP_CYBER_CAPTOR
        ):
            return True
        if enemy_type == TeslaTwin and counts["tesla_twin"] >= SPAWNER_CAP_TESLA_TWIN:
            return True
        if enemy_type == JammerNode and counts["jammer"] >= SPAWNER_CAP_JAMMER:
            return True
        if enemy_type == MortarDrone and counts["mortar"] >= SPAWNER_CAP_MORTAR:
            return True
        if enemy_type == CargoCarrier and counts["cargo_carrier"] >= SPAWNER_CAP_CARGO_CARRIER:
            return True
        if enemy_type == SplitterTank and counts["splitter"] >= SPAWNER_CAP_SPLITTER:
            return True
        if enemy_type == SapperDrone and counts["sapper"] >= SPAWNER_CAP_SAPPER:
            return True
        if enemy_type == MirrorPylon and counts["mirror"] >= SPAWNER_CAP_MIRROR:
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
        if (
            enemy_type == NeonSniper
            and counts["neon_sniper"] >= SPAWNER_CAP_NEON_SNIPER
        ):
            return False
        if (
            enemy_type == PoliceInterceptor
            and counts["police_interceptor"] >= SPAWNER_CAP_POLICE_INTERCEPTOR
        ):
            return False
        if enemy_type == CyberTank and counts["cyber_tank"] >= SPAWNER_CAP_CYBER_TANK:
            return False
        if (
            enemy_type == CyberCaptor
            and counts["cyber_captor"] >= SPAWNER_CAP_CYBER_CAPTOR
        ):
            return False
        if enemy_type == TeslaTwin and counts["tesla_twin"] >= SPAWNER_CAP_TESLA_TWIN:
            return False
        if enemy_type == JammerNode and counts["jammer"] >= SPAWNER_CAP_JAMMER:
            return False
        if enemy_type == MortarDrone and counts["mortar"] >= SPAWNER_CAP_MORTAR:
            return False
        if enemy_type == CargoCarrier and counts["cargo_carrier"] >= SPAWNER_CAP_CARGO_CARRIER:
            return False
        if enemy_type == SplitterTank and counts["splitter"] >= SPAWNER_CAP_SPLITTER:
            return False
        if enemy_type == SapperDrone and counts["sapper"] >= SPAWNER_CAP_SAPPER:
            return False
        if enemy_type == MirrorPylon and counts["mirror"] >= SPAWNER_CAP_MIRROR:
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
        if not self.weighted_telemetry_enabled:
            return
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

        if enemy_type == Satellite:
            return self._spawn_satellite(entity_manager)

        if enemy_type == CityDrone:
            return self._spawn_city_drone_cluster(entity_manager, is_side_scroll)

        if enemy_type == NeonSniper:
            return self._spawn_neon_sniper(entity_manager, is_side_scroll)

        if enemy_type == PoliceInterceptor:
            return self._spawn_police_interceptor_pair(entity_manager, is_side_scroll)

        if enemy_type == CyberTank:
            return self._spawn_cyber_tank(entity_manager, is_side_scroll)

        if enemy_type == CyberCaptor:
            return self._spawn_cyber_captor(entity_manager, is_side_scroll)

        if enemy_type == JammerNode:
            return self._spawn_jammer(entity_manager, is_side_scroll)

        if enemy_type == MortarDrone:
            return self._spawn_mortar(entity_manager, is_side_scroll)

        if enemy_type == CargoCarrier:
            return self._spawn_cargo_carrier(entity_manager, is_side_scroll)

        if enemy_type == SplitterTank:
            return self._spawn_splitter_tank(entity_manager, is_side_scroll)

        if enemy_type == SapperDrone:
            return self._spawn_sapper(entity_manager, is_side_scroll)

        if enemy_type == MirrorPylon:
            return self._spawn_mirror_pylon(entity_manager, is_side_scroll)

        if enemy_type == TeslaTwin:
            return self._spawn_tesla_twins(entity_manager, is_side_scroll)

        if enemy_type == SatelliteFragment:
            return self._spawn_satellite_fragment(entity_manager)

        # Fallback genérico
        new_enemy = cast(EnemyWithHealth, enemy_type())
        new_enemy.health = int(new_enemy.health * self.enemy_health_multiplier)
        entity_manager.enemies.append(new_enemy)  # type: ignore[arg-type]
        return True

    def _spawn_satellite(self, entity_manager: "EntityManager") -> bool:
        new_enemy = Satellite(inverted_vertical=self.inverted_vertical)
        new_enemy.health = int(new_enemy.health * self.enemy_health_multiplier)
        entity_manager.enemies.append(new_enemy)
        return True

    def _spawn_satellite_fragment(self, entity_manager: "EntityManager") -> bool:
        # Lixo espacial à deriva (entra pela borda respeitando entry/re-entry),
        # diferente dos fragmentos que explodem de um satélite destruído.
        fragment = SatelliteFragment.spawn_ambient(
            inverted_vertical=self.inverted_vertical
        )
        fragment.health = max(
            1, int(fragment.health * self.enemy_health_multiplier)
        )
        entity_manager.enemies.append(fragment)
        return True

    def _spawn_neon_sniper(
        self, entity_manager: "EntityManager", is_side_scroll: bool
    ) -> bool:
        """Spawna 1 Neon Sniper como "perch unit" entrando por uma extremidade
        superior (sentinela), diferente do enxame em leva do City Drone."""
        size = NeonSniper.SIZE
        if is_side_scroll:
            # Entra pela direita, numa banda superior (canto de cima).
            x = Config.SCREEN_WIDTH + random.uniform(20.0, 80.0)
            y = random.uniform(40.0, Config.SCREEN_HEIGHT * 0.35)
        else:
            # Entra pelo topo, encostado num dos cantos (esquerdo/direito).
            if random.random() < 0.5:
                x = random.uniform(30.0, Config.SCREEN_WIDTH * 0.18)
            else:
                x = random.uniform(
                    Config.SCREEN_WIDTH * 0.82 - size, Config.SCREEN_WIDTH - 30.0 - size
                )
            y = -(size + random.uniform(20.0, 80.0))

        sniper = NeonSniper(
            x,
            y,
            aggressiveness_multiplier=self.aggressiveness_multiplier,
            side_scroll=is_side_scroll,
        )
        sniper.health = max(1, int(sniper.health * self.enemy_health_multiplier))
        entity_manager.enemies.append(sniper)
        return True

    def _spawn_cyber_captor(
        self, entity_manager: "EntityManager", is_side_scroll: bool
    ) -> bool:
        """Spawna 1 Cyber-Captor com "Shadow Support": nasce escondido em meio a um
        **enxame de City Drones** (clutter visual), e orbita uma âncora no alto da
        tela. NÃO usa o CyberTank como cobertura (parecia que o tanque o invocava)."""
        size = CyberCaptor.SIZE
        # Esconde-se num enxame de drones (precisa de uma "nuvem" para de fato
        # camuflar). Sem enxame, entra discretamente pela borda.
        drones = [
            e
            for e in entity_manager.enemies
            if isinstance(e, CityDrone) and not e.dead
        ]
        if len(drones) >= 3:
            host = random.choice(drones)
            spawn_x = host.x + getattr(host, "w", size) / 2 - size / 2
            spawn_y = host.y + getattr(host, "h", size) / 2 - size / 2
        else:
            spawn_x = Config.SCREEN_WIDTH + random.uniform(10.0, 60.0)
            spawn_y = random.uniform(40.0, Config.SCREEN_HEIGHT * 0.30)

        # Âncora da órbita: alto da tela, à direita do centro.
        anchor = (
            random.uniform(Config.SCREEN_WIDTH * 0.45, Config.SCREEN_WIDTH * 0.80),
            random.uniform(Config.SCREEN_HEIGHT * 0.18, Config.SCREEN_HEIGHT * 0.38),
        )
        captor = CyberCaptor(
            spawn_x,
            spawn_y,
            aggressiveness_multiplier=self.aggressiveness_multiplier,
            side_scroll=is_side_scroll,
            anchor=anchor,
        )
        captor.health = max(1, int(captor.health * self.enemy_health_multiplier))
        entity_manager.enemies.append(captor)
        return True

    def _spawn_mirror_pylon(
        self, entity_manager: "EntityManager", is_side_scroll: bool
    ) -> bool:
        """Spawna 1 Mirror Pylon entrando pela direita numa faixa central — pilar
        que avança refletindo os tiros da nave pela face espelhada frontal."""
        h = MirrorPylon.H
        if is_side_scroll:
            x = Config.SCREEN_WIDTH + random.uniform(20.0, 60.0)
            y = random.uniform(
                Config.SCREEN_HEIGHT * 0.25, Config.SCREEN_HEIGHT * 0.70 - h
            )
        else:
            x = random.uniform(40.0, Config.SCREEN_WIDTH - 40.0 - MirrorPylon.W)
            y = -(h + random.uniform(20.0, 60.0))
        pylon = MirrorPylon(
            x,
            y,
            aggressiveness_multiplier=self.aggressiveness_multiplier,
            side_scroll=is_side_scroll,
            health_multiplier=self.enemy_health_multiplier,
        )
        # Vida já escalada no construtor (§11) — não reaplicar externamente.
        entity_manager.enemies.append(pylon)
        return True

    def _spawn_sapper(
        self, entity_manager: "EntityManager", is_side_scroll: bool
    ) -> bool:
        """Spawna 1 Rebocador entrando pela borda numa banda ampla — vai caçar um
        aliado ferido para blindar."""
        size = SapperDrone.SIZE
        if is_side_scroll:
            x = Config.SCREEN_WIDTH + random.uniform(20.0, 80.0)
            y = random.uniform(50.0, Config.SCREEN_HEIGHT - 50.0 - size)
        else:
            x = random.uniform(40.0, Config.SCREEN_WIDTH - 40.0 - size)
            y = -(size + random.uniform(20.0, 80.0))
        sapper = SapperDrone(
            x,
            y,
            aggressiveness_multiplier=self.aggressiveness_multiplier,
            side_scroll=is_side_scroll,
            health_multiplier=self.enemy_health_multiplier,
        )
        # Vida já escalada no construtor (§11) — não reaplicar externamente.
        entity_manager.enemies.append(sapper)
        return True

    def _spawn_splitter_tank(
        self, entity_manager: "EntityManager", is_side_scroll: bool
    ) -> bool:
        """Spawna 1 Splitter Tank (tier 0) entrando numa faixa central — colosso
        que avança e se parte em unidades menores ao morrer."""
        # Dimensões do tier 0 (sem instanciar): cell 6 × grade 15×13.
        size_w = SplitterTank.PIXEL_COLS * 6
        size_h = SplitterTank.PIXEL_ROWS * 6
        if is_side_scroll:
            x = Config.SCREEN_WIDTH + random.uniform(10.0, 50.0)
            y = random.uniform(
                Config.SCREEN_HEIGHT * 0.25, Config.SCREEN_HEIGHT * 0.70 - size_h
            )
        else:
            x = random.uniform(40.0, Config.SCREEN_WIDTH - 40.0 - size_w)
            y = -(size_h + random.uniform(20.0, 60.0))
        tank = SplitterTank(
            x,
            y,
            aggressiveness_multiplier=self.aggressiveness_multiplier,
            side_scroll=is_side_scroll,
            health_multiplier=self.enemy_health_multiplier,
            tier=0,
        )
        entity_manager.enemies.append(tank)
        return True

    def _spawn_cargo_carrier(
        self, entity_manager: "EntityManager", is_side_scroll: bool
    ) -> bool:
        """Spawna 1 Cargueiro entrando pela parte superior da lateral direita —
        transporte pesado que avança devagar e larga caixas de tropa."""
        h = CargoCarrier.H
        if is_side_scroll:
            x = Config.SCREEN_WIDTH + random.uniform(20.0, 60.0)
            # Sempre na faixa superior: deixa espaço p/ a caixa descer abaixo dele.
            y = random.uniform(
                Config.SCREEN_HEIGHT * 0.06, Config.SCREEN_HEIGHT * 0.18
            )
        else:
            # Vertical: enviesa para a direita (entrando pelo topo).
            x = random.uniform(
                Config.SCREEN_WIDTH * 0.60, Config.SCREEN_WIDTH - 40.0 - CargoCarrier.W
            )
            y = -(h + random.uniform(20.0, 60.0))
        carrier = CargoCarrier(
            x,
            y,
            aggressiveness_multiplier=self.aggressiveness_multiplier,
            side_scroll=is_side_scroll,
            health_multiplier=self.enemy_health_multiplier,
        )
        # Vida já escalada no construtor (§11) — não reaplicar externamente.
        entity_manager.enemies.append(carrier)
        return True

    def _spawn_mortar(
        self, entity_manager: "EntityManager", is_side_scroll: bool
    ) -> bool:
        """Spawna 1 Artilheiro como perch unit numa banda superior (entra pela
        direita no side-scroll, pelo topo no vertical) e ancora p/ bombardear."""
        size = MortarDrone.SIZE
        if is_side_scroll:
            x = Config.SCREEN_WIDTH + random.uniform(20.0, 80.0)
            y = random.uniform(40.0, Config.SCREEN_HEIGHT * 0.40)
        else:
            x = random.uniform(40.0, Config.SCREEN_WIDTH - 40.0 - size)
            y = -(size + random.uniform(20.0, 80.0))
        mortar = MortarDrone(
            x,
            y,
            aggressiveness_multiplier=self.aggressiveness_multiplier,
            side_scroll=is_side_scroll,
            health_multiplier=self.enemy_health_multiplier,
        )
        # Vida já escalada no construtor (§11) — não reaplicar externamente.
        entity_manager.enemies.append(mortar)
        return True

    def _spawn_jammer(
        self, entity_manager: "EntityManager", is_side_scroll: bool
    ) -> bool:
        """Spawna 1 Jammer Node entrando pela borda e orbitando uma âncora no
        alto da tela (à esquerda do centro, p/ não sobrepor a do Cyber-Captor)."""
        size = JammerNode.SIZE
        if is_side_scroll:
            spawn_x = Config.SCREEN_WIDTH + random.uniform(10.0, 60.0)
            spawn_y = random.uniform(40.0, Config.SCREEN_HEIGHT * 0.30)
        else:
            spawn_x = random.uniform(40.0, Config.SCREEN_WIDTH - 40.0 - size)
            spawn_y = -(size + random.uniform(20.0, 80.0))

        anchor = (
            random.uniform(Config.SCREEN_WIDTH * 0.20, Config.SCREEN_WIDTH * 0.55),
            random.uniform(Config.SCREEN_HEIGHT * 0.18, Config.SCREEN_HEIGHT * 0.38),
        )
        jammer = JammerNode(
            spawn_x,
            spawn_y,
            aggressiveness_multiplier=self.aggressiveness_multiplier,
            side_scroll=is_side_scroll,
            anchor=anchor,
            health_multiplier=self.enemy_health_multiplier,
        )
        # Vida já escalada no construtor (§11) — não reaplicar externamente.
        entity_manager.enemies.append(jammer)
        return True

    def _spawn_tesla_twins(
        self, entity_manager: "EntityManager", is_side_scroll: bool
    ) -> bool:
        """Spawna o par de Tesla Twins ("Boundary Link"): duas torres ancoradas
        no topo e na base, entrando juntas pela direita, ligadas pelo `TeslaLink`.
        O feixe vertical entre elas é uma parede que avança p/ a esquerda. Spawna
        o par inteiro de uma vez; se já há um par vivo, não spawna outro."""
        current = sum(
            1
            for e in entity_manager.enemies
            if isinstance(e, TeslaTwin) and not e.dead
        )
        if current > 0:
            return False

        x = Config.SCREEN_WIDTH + random.uniform(20.0, 60.0)
        h = TeslaTwin.H
        y_top = Config.SCREEN_HEIGHT * 0.20 - h / 2
        y_bottom = Config.SCREEN_HEIGHT * 0.80 - h / 2
        top = TeslaTwin(
            x, y_top, is_top=True,
            aggressiveness_multiplier=self.aggressiveness_multiplier,
            side_scroll=is_side_scroll,
            health_multiplier=self.enemy_health_multiplier,
        )
        bottom = TeslaTwin(
            x, y_bottom, is_top=False,
            aggressiveness_multiplier=self.aggressiveness_multiplier,
            side_scroll=is_side_scroll,
            health_multiplier=self.enemy_health_multiplier,
        )
        # Vida já escalada no construtor (§11) — não reaplicar externamente.
        TeslaLink([top, bottom])
        entity_manager.enemies.append(top)
        entity_manager.enemies.append(bottom)
        return True

    def _spawn_cyber_tank(
        self, entity_manager: "EntityManager", is_side_scroll: bool
    ) -> bool:
        """Spawna 1 Cyber Tank "gatekeeper" (sozinho), entrando pela direita numa
        faixa central — colosso que atravessa a tela avançando."""
        size = CyberTank.SIZE
        x = Config.SCREEN_WIDTH + random.uniform(10.0, 50.0)
        y = random.uniform(
            Config.SCREEN_HEIGHT * 0.30, Config.SCREEN_HEIGHT * 0.70 - size
        )
        tank = CyberTank(
            x,
            y,
            aggressiveness_multiplier=self.aggressiveness_multiplier,
            side_scroll=is_side_scroll,
        )
        tank.health = max(1, int(tank.health * self.enemy_health_multiplier))
        entity_manager.enemies.append(tank)
        return True

    def _spawn_police_interceptor_pair(
        self, entity_manager: "EntityManager", is_side_scroll: bool
    ) -> bool:
        """Spawna uma **dupla sincronizada** ("Squad Pairs") de Police Interceptors.

        Ambos entram pela direita (convenção side-scroll do bioma CITY), um na
        banda superior e outro na inferior, com viés vertical oposto — assim se
        cruzam ao atravessar a tela. Se só há folga para um até o cap, spawna um.
        """
        current = sum(
            1
            for e in entity_manager.enemies
            if isinstance(e, PoliceInterceptor) and not e.dead
        )
        room = SPAWNER_CAP_POLICE_INTERCEPTOR - current
        if room <= 0:
            return False

        size = PoliceInterceptor.SIZE
        x = Config.SCREEN_WIDTH + random.uniform(20.0, 70.0)
        top_y = random.uniform(50.0, Config.SCREEN_HEIGHT * 0.32)
        bottom_y = random.uniform(
            Config.SCREEN_HEIGHT * 0.68 - size, Config.SCREEN_HEIGHT - 50.0 - size
        )
        # (y, viés vertical): superior desce, inferior sobe → cruzam-se.
        plan = [(top_y, 1.0), (bottom_y, -1.0)][: max(1, min(2, room))]

        squad_members: list[PoliceInterceptor] = []
        for y, bias in plan:
            unit = PoliceInterceptor(
                x,
                y,
                aggressiveness_multiplier=self.aggressiveness_multiplier,
                side_scroll=is_side_scroll,
                patrol_bias=bias if is_side_scroll else 0.0,
            )
            unit.health = max(1, int(unit.health * self.enemy_health_multiplier))
            entity_manager.enemies.append(unit)
            squad_members.append(unit)

        # Pincer sincronizado: une a dupla num esquadrão que coordena o bote
        # conjunto. Unidade única (sem folga p/ a dupla) age sozinha (squad=None).
        if len(squad_members) >= 2:
            InterceptorSquad(squad_members)
        return True

    def _spawn_city_drone_cluster(
        self, entity_manager: "EntityManager", is_side_scroll: bool
    ) -> bool:
        """Spawna uma leva (cluster) de 5-8 City Drones — "nuvem desordenada".

        Diferente dos outros spawns (uma unidade por tick), o enxame nasce em
        leva. O tamanho é limitado pela folga até o cap de drones e o cap total
        de inimigos para não estourar a tela.
        """
        current_drones = sum(
            1 for e in entity_manager.enemies if isinstance(e, CityDrone) and not e.dead
        )
        drone_room = SPAWNER_CAP_CITY_DRONE - current_drones
        if drone_room <= 0:
            return False

        active_total = sum(
            1
            for e in entity_manager.enemies
            if not getattr(e, "dead", False)
            and not isinstance(e, HAZARD_ENEMY_TYPES)
        )
        total_room = self._get_current_enemy_cap() - active_total
        room = min(drone_room, total_room)
        if room <= 0:
            return False

        cluster_size = min(
            random.randint(CITY_DRONE_CLUSTER_MIN, CITY_DRONE_CLUSTER_MAX), room
        )

        max_y = max(40, Config.SCREEN_HEIGHT - 40 - CityDrone.MAX_SIZE)
        for _ in range(cluster_size):
            if is_side_scroll:
                # Entra pela direita, espalhado numa banda fora da tela.
                x = Config.SCREEN_WIDTH + random.uniform(20.0, 160.0)
                y = random.uniform(40.0, max_y)
            else:
                x = random.uniform(20.0, Config.SCREEN_WIDTH - 20.0 - CityDrone.MAX_SIZE)
                y = -random.uniform(20.0, 160.0)
            drone = CityDrone(
                x,
                y,
                aggressiveness_multiplier=self.aggressiveness_multiplier,
                side_scroll=is_side_scroll,
                health_multiplier=self.enemy_health_multiplier,
            )
            # Vida já escalada no construtor (propaga aos filhotes emergentes);
            # não reaplicar aqui para não dobrar o multiplicador.
            entity_manager.enemies.append(drone)
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
        new_enemy = EyeEnemy(
            x, y, aggressiveness_multiplier=self.aggressiveness_multiplier
        )
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
            meteor = self.meteor_pool.get(inverted_vertical=self.inverted_vertical)

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
    # ------------------------------------------------------------------

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

        if self.weighted_telemetry_enabled:
            self.weighted_spawn_attempts += 1

        if random.random() >= self.spawn_intensity:
            if self.weighted_telemetry_enabled:
                self.weighted_spawn_blocked += 1
            self.weighted_spawn_timer.start()
            return

        enemy_type = self._pick_weighted_enemy_type(entity_manager, counts=counts)
        if enemy_type is None or not self._should_spawn_enemy(
            enemy_type, entity_manager, counts=counts
        ):
            if self.weighted_telemetry_enabled:
                self.weighted_spawn_blocked += 1
            self.weighted_spawn_timer.start()
            return

        if not self._can_spawn_now(enemy_type):
            if self.weighted_telemetry_enabled:
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
            if self.weighted_telemetry_enabled:
                self.weighted_spawn_success += 1
            self._record_weighted_spawn(enemy_type)
            self.recent_enemy_types.append(enemy_type)
            self._register_spawn(enemy_type)
        elif self.weighted_telemetry_enabled:
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
        counts = self._count_enemies_by_type(entity_manager)
        self._refresh_death_clocks(counts)

        # Warm-up estrito
        if self.warm_up_timer > 0:
            self.warm_up_timer -= dt
            self.spawn_intensity = 0.0
        else:
            # --------------------------------------------------------------
            # DIRETOR DE ONDAS (PACING FSM)
            # Controla `self.spawn_intensity` e `self.director_intensity_mult`
            # para gerar o ciclo orgânico: BUILDUP -> PEAK -> REST -> BUILDUP
            # --------------------------------------------------------------
            self.director_timer += dt

            if self.director_state == "BUILDUP":
                # Cresce de 0.2 até 1.0 gradualmente
                progress = min(1.0, self.director_timer / self._dir_buildup_dur)
                self.spawn_intensity = 0.2 + (0.8 * progress)
                self.director_intensity_mult = 1.0

                if self.director_timer >= self._dir_buildup_dur:
                    self.director_state = "PEAK"
                    self.director_timer = 0.0
                    self._dir_peak_dur = random.uniform(
                        12.0, 18.0
                    )  # Sorteia próximo Peak

            elif self.director_state == "PEAK":
                # Intensidade máxima + cadência 10% mais agressiva
                self.spawn_intensity = 1.0
                self.director_intensity_mult = 1.10

                if self.director_timer >= self._dir_peak_dur:
                    self.director_state = "REST"
                    self.director_timer = 0.0
                    # Próximo Rest: faixa base encurtada e escalada por dificuldade
                    self._dir_rest_dur = self._roll_rest_duration()

            elif self.director_state == "REST":
                # Quebra o spawn quase a zero para o jogador respirar
                self.spawn_intensity = 0.1
                self.director_intensity_mult = 0.50

                if self.director_timer >= self._dir_rest_dur:
                    self.director_state = "BUILDUP"
                    self.director_timer = 0.0
                    self._dir_buildup_dur = random.uniform(
                        8.0, 12.0
                    )  # Sorteia próximo Buildup

        # Spawn ponderado com multiplicador do diretor aplicado
        self._record_pressure_sample(entity_manager, counts=counts)
        self._update_weighted_enemy_spawn(
            dt * self.director_intensity_mult,  # Acelera ou retarda os timers
            entity_manager,
            player_x,
            player_y,
            is_side_scroll,
            counts=counts,
        )
        self._flush_weighted_telemetry(dt)

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

        formation_chance = world.theme_modifiers.get("formation_chance", 1.0)
        if world.theme == WorldTheme.STARFIELD:
            formation_chance = max(0.0, min(1.0, formation_chance))

        effective_chance = self.spawn_intensity * formation_chance
        if random.random() >= effective_chance:
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
            Formation(
                Alien,
                count,
                entry_x,
                entry_y,
                patterns,
                enemy_kwargs={
                    "aggressiveness_multiplier": self.aggressiveness_multiplier
                },
            )
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
            aggressiveness_multiplier=self.aggressiveness_multiplier,
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
        inverted_vertical: bool = False,
    ) -> None:
        self.current_level_number = level_number
        # Ramp de HP por estágio depende do nível atual → recomputa o multiplicador.
        self._recompute_enemy_health_multiplier()
        # Se um LevelConfig pré-ajustado (ex: com meta-progression aplicado) for
        # fornecido, usá-lo diretamente em vez de recalcular do zero. Isso garante
        # que o ajuste adaptativo do PerformanceAnalyzer chegue de fato ao spawner.
        self.level_config = (
            level_config
            if level_config is not None
            else self.level_manager.get_level(
                self.current_level_number, self.difficulty_preset
            )
        )
        self.stopped = False
        self._is_world_transition = is_world_transition
        self.inverted_vertical = inverted_vertical
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
    # +25% por jogador extra. Em coop, 2 jogadores competem pelos mesmos
    # powerups (quem toca primeiro leva) — sem essa compensação, a sensação
    # é "powerups raros demais pra dupla". Equivalente à lógica do Item 1
    # do balanceamento (que aumentou +20% a cadência de inimigos em coop).
    COOP_RATE_PER_EXTRA_PLAYER: float = 0.25

    def __init__(
        self,
        difficulty: DifficultyPreset = DifficultyPreset.NORMAL,
        player_count: int = 1,
    ) -> None:
        from ..core.difficulty import DifficultySettings

        self.difficulty = difficulty
        settings = DifficultySettings.get_settings(difficulty)
        # >1 = mais frequente (intervalo menor). Casual=1.3, Pesadelo=0.5.
        self._spawn_rate_multiplier: float = settings["powerup_spawn_rate_multiplier"]
        self.player_count = max(1, player_count)
        self._reset_timer()

    def set_player_count(self, count: int) -> None:
        """Atualiza coop scaling em runtime (P2 entra/sai mid-game).

        O timer atual mantém o intervalo computado; o novo valor entra
        em vigor no próximo `_reset_timer()`. Isso evita "saltar" um
        powerup imediatamente quando P2 entra — só afeta os próximos.
        """
        self.player_count = max(1, int(count))

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
        coop_mult = 1.0 + self.COOP_RATE_PER_EXTRA_PLAYER * max(0, self.player_count - 1)
        interval = random.uniform(min_t, max_t) / (mult * coop_mult)
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
