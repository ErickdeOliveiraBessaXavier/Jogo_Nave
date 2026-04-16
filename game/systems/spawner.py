import logging
import random
from collections import deque
from typing import (
    TYPE_CHECKING,
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

from ..core.config import PowerUpType
from ..core.config import config as Config
from ..core.difficulty import DifficultyPreset
from ..core.levels import DifficultyConfig, LevelManager, calculate_dynamic_enemy_cap
from ..core.powerup_weights import get_powerup_weights
from ..core.time import Timer
from ..entities.bot_elemental import ElementalRobot
from ..entities.explosive_mine import ExplosiveMine
from ..entities.eye_enemy import EyeEnemy
from ..entities.formation import Formation, FormationPattern
from ..entities.meteor_pool import MeteorPool
from ..entities.powerup import PowerUp
from ..entities.rock_glider import RockGlider
from ..entities.square_minion_boss import SquareMinionBoss
from ..entities.star import Star
from ..entities.stone_sentry import StoneSentry

if TYPE_CHECKING:
    from ..systems.entity_manager import EntityManager


logger = logging.getLogger(__name__)


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


# Configurações de formações disponíveis
FORMATION_CONFIGS: Dict[str, FormationConfig] = {
    "spiral_circle": {
        "patterns": [FormationPattern.SPIRAL_ENTRY, FormationPattern.CIRCLE],
        "count_range": (5, 8),
    },
    "spiral_v": {
        "patterns": [FormationPattern.SPIRAL_ENTRY, FormationPattern.V_SHAPE],
        "count_options": [5, 7],  # V sempre com 5 ou 7 naves
    },
    "spiral_square": {
        "patterns": [FormationPattern.SPIRAL_ENTRY, FormationPattern.SQUARE],
        "count_options": [4, 8, 12],  # Quadrado sempre com 4, 8 ou 12 naves
    },
    "spiral_line": {
        "patterns": [FormationPattern.SPIRAL_ENTRY, FormationPattern.LINE],
        "count_range": (5, 8),
    },
    "full_cycle": {
        "patterns": [
            FormationPattern.SPIRAL_ENTRY,
            FormationPattern.CIRCLE,
            FormationPattern.V_SHAPE,
        ],
        "count_options": [5, 7],  # V sempre com 5 ou 7 naves
    },
}


class EnemySpawner:
    def __init__(
        self,
        level_manager: LevelManager,
        meteor_pool: MeteorPool,
        is_initial_level: bool = False,
        difficulty_preset: DifficultyPreset = DifficultyPreset.NORMAL,
        enemy_health_multiplier: float = 1.0,
    ):
        self.level_manager = level_manager
        self.meteor_pool = meteor_pool
        self.difficulty_preset = difficulty_preset
        self.enemy_health_multiplier = enemy_health_multiplier
        self.current_level_number = 1  # EnemySpawner starts at level 1
        self.config = self.level_manager.get_level(
            self.current_level_number, self.difficulty_preset
        )
        self.stopped = False

        # Validar tipos de formação configurados
        if self.config.formations_enabled and self.config.formation_types:
            invalid_types = self.config.validate_formation_types(
                set(FORMATION_CONFIGS.keys())
            )
            if invalid_types:
                print(
                    f"WARNING: Level {self.config.level_number} has invalid formation types: {invalid_types}"
                )
                print(f"Available types: {list(FORMATION_CONFIGS.keys())}")
                # Filtrar tipos inválidos
                self.config.formation_types = [
                    t for t in self.config.formation_types if t in FORMATION_CONFIGS
                ]
                if not self.config.formation_types:
                    print(
                        f"WARNING: No valid formation types remain. Disabling formations for level {self.config.level_number}"
                    )
                    self.config.formations_enabled = False
                else:
                    print(f"Using valid types: {self.config.formation_types}")

        # Sistema de intensidade gradual para spawn orgânico
        self.spawn_intensity = 0.0  # 0.0 = não spawna, 1.0 = taxa normal
        if is_initial_level:
            self.warm_up_duration = Config.INITIAL_GAME_DELAY  # Delay inicial da fase 1
            self.warm_up_timer = self.warm_up_duration
        else:
            self.warm_up_duration = 0.0  # Outras fases começam imediatamente
            self.warm_up_timer = 0.0
            self.spawn_intensity = 1.0  # Já ativo

        # Pré-calcular valores de formações para otimização
        def margin_v(count: int) -> float:
            return (count // 2) * Config.FORMATION_V_SPACING

        def margin_line(count: int) -> float:
            return ((count - 1) * Config.FORMATION_LINE_SPACING) / 2

        self._formation_safe_margins: Dict[
            str, Union[float, Callable[[int], float]]
        ] = {
            "spiral_circle": Config.FORMATION_CIRCLE_RADIUS,
            "spiral_v": margin_v,
            "spiral_square": Config.FORMATION_SQUARE_SIZE / 2,
            "spiral_line": margin_line,
            "full_cycle": Config.FORMATION_CIRCLE_RADIUS,
        }
        self._formation_entry_y: Dict[str, float] = {
            "spiral_circle": float(Config.FORMATION_CIRCLE_RADIUS + 40),
            "spiral_v": 80.0,
            "spiral_square": float(Config.FORMATION_SQUARE_SIZE / 2 + 40),
            "spiral_line": 80.0,
            "full_cycle": float(Config.FORMATION_CIRCLE_RADIUS + 40),
        }

        # Novo pipeline ponderado com fallback para o modo legado.
        self.use_weighted_spawn = DifficultyConfig.WEIGHTED_SPAWN_ENABLED
        self.recent_enemy_types: deque[type] = deque(
            maxlen=DifficultyConfig.WEIGHTED_RECENT_MEMORY
        )
        self.weighted_telemetry_enabled = DifficultyConfig.WEIGHTED_SPAWN_TELEMETRY
        self.weighted_telemetry_timer = 0.0
        self.weighted_spawn_attempts = 0
        self.weighted_spawn_success = 0
        self.weighted_spawn_blocked = 0
        self.weighted_spawn_by_type: dict[str, int] = {}
        self.weighted_occupancy_samples: deque[int] = deque(maxlen=768)
        self.weighted_peak_occupancy = 0
        self.weighted_near_cap_samples = 0
        self.weighted_hard_cap_samples = 0

        self.spawn_clock = 0.0
        self.last_spawn_clock = -9999.0
        self.last_spawn_clock_by_type: dict[str, float] = {}

        self._reset_spawn_pipeline()

        # Timer separado para meteoros teleguiados (a cada 3 segundos)
        self.guided_meteor_timer = Timer(3.0)
        self.guided_meteor_timer.start()

        # Timer para minas explosivas
        self.mine_spawn_timer = Timer(10.0)
        self.mine_spawn_timer.start()

        # Timer para formações
        min_t, max_t = Config.FORMATION_SPAWN_INTERVAL
        self.formation_spawn_timer = Timer(random.uniform(min_t, max_t))
        self.formation_spawn_timer.start()

    def _reset_spawn_pipeline(self) -> None:
        """Recria timers para o modo ativo de spawn."""
        self.enemy_timers: Dict[Type[object], Timer] = {}
        for enemy_type in self.config.enemy_types:
            spawn_time = self.config.get_spawn_time(enemy_type)
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
        self.last_spawn_clock_by_type = {}

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
        }
        return aliases.get(enemy_type.__name__, enemy_type.__name__.lower())

    def _get_min_spawn_gap(self, enemy_type: type) -> float:
        """Retorna o intervalo mínimo entre spawns do mesmo tipo."""
        type_key = self._enemy_type_key(enemy_type)
        base_gap = DifficultyConfig.MIN_SPAWN_GAP_BY_TYPE.get(
            type_key, DifficultyConfig.MIN_GLOBAL_SPAWN_GAP
        )
        preset_mult = DifficultyConfig.DIFFICULTY_SPAWN_GAP_MULTIPLIER.get(
            self.difficulty_preset, 1.0
        )
        return base_gap * preset_mult

    def _get_min_global_spawn_gap(self) -> float:
        """Retorna o espaçamento mínimo entre quaisquer spawns."""
        return (
            DifficultyConfig.MIN_GLOBAL_SPAWN_GAP
            * DifficultyConfig.DIFFICULTY_SPAWN_GAP_MULTIPLIER.get(
                self.difficulty_preset, 1.0
            )
        )

    def _can_spawn_now(self, enemy_type: type) -> bool:
        """Bloqueia spawns muito próximos entre si para evitar bursts."""
        global_gap = self._get_min_global_spawn_gap()
        if self.spawn_clock - self.last_spawn_clock < global_gap:
            return False

        type_key = self._enemy_type_key(enemy_type)
        type_gap = self._get_min_spawn_gap(enemy_type)
        last_type_spawn = self.last_spawn_clock_by_type.get(type_key, -9999.0)
        if self.spawn_clock - last_type_spawn < type_gap:
            return False

        return True

    def _register_spawn(self, enemy_type: type) -> None:
        """Marca a hora do spawn para respeitar a cadência mínima."""
        self.last_spawn_clock = self.spawn_clock
        self.last_spawn_clock_by_type[self._enemy_type_key(enemy_type)] = (
            self.spawn_clock
        )

    def _record_pressure_sample(self, entity_manager: "EntityManager") -> None:
        """Amostra ocupação de tela para telemetria de balanceamento."""
        counts = self._count_enemies_by_type(entity_manager)
        total = counts["total"]
        self.weighted_occupancy_samples.append(total)
        self.weighted_peak_occupancy = max(self.weighted_peak_occupancy, total)

        # Usar cap dinâmico baseado em dificuldade e nível
        total_cap = calculate_dynamic_enemy_cap(
            self.current_level_number, self.difficulty_preset
        )
        near_cap_threshold = int(total_cap * DifficultyConfig.SPAWN_REDUCTION_THRESHOLD)
        if total >= near_cap_threshold:
            self.weighted_near_cap_samples += 1
        if total >= total_cap:
            self.weighted_hard_cap_samples += 1

    @staticmethod
    def _percentile(values: list[int], percentile: float) -> float:
        """Percentil simples para séries pequenas sem dependências externas."""
        if not values:
            return 0.0
        ordered = sorted(values)
        idx = int((len(ordered) - 1) * percentile)
        idx = max(0, min(idx, len(ordered) - 1))
        return float(ordered[idx])

    def _count_enemies_by_type(self, entity_manager: "EntityManager") -> dict[str, int]:
        """Conta inimigos por tipo que estão ativos na tela."""
        counts = {
            "meteor": 0,
            "alien": 0,
            "eye": 0,
            "square_minion": 0,
            "elemental_robot": 0,
            "stone_sentry": 0,
            "total": 0,
        }

        from ..entities.alien import Alien
        from ..entities.meteor import Meteor

        for enemy in entity_manager.enemies:
            if not getattr(enemy, "dead", False):
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

        return counts

    def _should_spawn_enemy(
        self, enemy_type: type, entity_manager: "EntityManager"
    ) -> bool:
        """Verifica se deve spawnar um inimigo baseado em limite total por dificuldade."""
        if not DifficultyConfig.ADAPTIVE_SPAWN_ENABLED:
            return True

        counts = self._count_enemies_by_type(entity_manager)

        # Caps especiais para inimigos muito fortes (sempre únicos ou em duplas)
        if enemy_type == ElementalRobot:
            if counts["elemental_robot"] >= 1:
                return False
        elif enemy_type == StoneSentry:
            if counts["stone_sentry"] >= 2:
                return False

        # Obter limite total baseado em dificuldade e nível atual
        max_enemies = calculate_dynamic_enemy_cap(
            self.current_level_number, self.difficulty_preset
        )

        # Verificar limite total absoluto
        if counts["total"] >= max_enemies:
            return False

        # Redução adaptativa quando próximo do limite
        threshold = int(max_enemies * DifficultyConfig.SPAWN_REDUCTION_THRESHOLD)
        if counts["total"] >= threshold:
            # Chance de spawn reduzida: quanto mais próximo, menor a chance
            ratio = (counts["total"] - threshold) / (max_enemies - threshold)
            spawn_chance = 1.0 - (ratio * 0.6)  # 60% de redução máxima
            return random.random() < spawn_chance

        return True

    def _is_hard_capped(self, enemy_type: type, counts: dict[str, int]) -> bool:
        """Valida apenas caps rígidos para filtrar candidatos de spawn."""
        # Obter limite total baseado em dificuldade e nível atual
        max_enemies = calculate_dynamic_enemy_cap(
            self.current_level_number, self.difficulty_preset
        )
        if counts["total"] >= max_enemies:
            return True

        # Caps especiais para inimigos muito fortes (sempre únicos ou em duplas)
        if enemy_type == ElementalRobot and counts["elemental_robot"] >= 1:
            return True
        if enemy_type == StoneSentry and counts["stone_sentry"] >= 2:
            return True

        return False

    def _get_dynamic_enemy_weights(
        self, entity_manager: "EntityManager"
    ) -> dict[type, float]:
        """Calcula pesos efetivos com anti-repetição e filtro por caps rígidos."""
        counts = self._count_enemies_by_type(entity_manager)
        base_weights = self.config.get_enemy_spawn_weights()
        dynamic_weights: dict[type, float] = {}

        for enemy_type, base_weight in base_weights.items():
            if base_weight <= 0:
                continue
            if self._is_hard_capped(enemy_type, counts):
                continue

            repeat_count = sum(1 for t in self.recent_enemy_types if t == enemy_type)
            penalty = DifficultyConfig.WEIGHTED_REPEAT_PENALTY**repeat_count
            final_weight = max(0.01, base_weight * penalty)
            dynamic_weights[enemy_type] = final_weight

        return dynamic_weights

    def _pick_weighted_enemy_type(self, entity_manager: "EntityManager") -> type | None:
        """Seleciona um tipo de inimigo por sorteio ponderado robusto."""
        weights_by_type = self._get_dynamic_enemy_weights(entity_manager)
        if not weights_by_type:
            return None

        enemy_types = list(weights_by_type.keys())
        weights = list(weights_by_type.values())
        return random.choices(enemy_types, weights=weights, k=1)[0]

    def _spawn_enemy_of_type(
        self,
        enemy_type: type,
        entity_manager: "EntityManager",
        player_x: float | None = None,
        player_y: float | None = None,
        is_side_scroll: bool = False,
    ) -> bool:
        """Spawna um inimigo de um tipo específico mantendo regras antigas."""
        if enemy_type == EyeEnemy:
            if is_side_scroll:
                x = Config.SCREEN_WIDTH + 40
                y = random.randint(60, Config.SCREEN_HEIGHT - 100)
            else:
                x = random.randint(40, Config.SCREEN_WIDTH - 80)
                y = random.randint(40, 100)
            new_enemy = EyeEnemy(x, y)
            new_enemy.health = int(new_enemy.health * self.enemy_health_multiplier)
            entity_manager.enemies.append(new_enemy)
            return True

        from ..entities.meteor import Meteor

        if issubclass(enemy_type, Meteor):
            if enemy_type is RockGlider:
                if is_side_scroll:
                    size = random.randint(
                        Config.MIN_METEOR_SIZE, Config.MAX_METEOR_SIZE
                    )
                    glider = entity_manager.rock_glider_pool.get(
                        size=size,
                        x=Config.SCREEN_WIDTH + 40,
                        y=random.randint(60, Config.SCREEN_HEIGHT - 100),
                        vx=None,
                        vy=random.uniform(-50, 50),
                    )
                else:
                    glider = entity_manager.rock_glider_pool.get()

                glider.health = int(glider.health * self.enemy_health_multiplier)
                entity_manager.enemies.append(glider)  # type: ignore[arg-type]
                return True

            if enemy_type is Meteor:
                if is_side_scroll:
                    size = random.randint(
                        Config.MIN_METEOR_SIZE, Config.MAX_METEOR_SIZE
                    )
                    meteor = self.meteor_pool.get(
                        size=size,
                        x=Config.SCREEN_WIDTH + 40,
                        y=random.randint(60, Config.SCREEN_HEIGHT - 100),
                        vx=-random.uniform(150, 300),
                        vy=random.uniform(-50, 50),
                    )
                else:
                    meteor = self.meteor_pool.get()
            elif is_side_scroll:
                size = random.randint(Config.MIN_METEOR_SIZE, Config.MAX_METEOR_SIZE)
                # RockGlider controla sua propria velocidade horizontal internamente.
                side_vx = (
                    None
                    if enemy_type.__name__ == "RockGlider"
                    else -random.uniform(150, 300)
                )
                meteor = cast(
                    EnemyWithHealth,
                    enemy_type(
                        size=size,
                        x=Config.SCREEN_WIDTH + 40,
                        y=random.randint(60, Config.SCREEN_HEIGHT - 100),
                        vx=side_vx,
                        vy=random.uniform(-50, 50),
                    ),
                )
            else:
                meteor = cast(EnemyWithHealth, enemy_type())

            meteor.health = int(meteor.health * self.enemy_health_multiplier)
            entity_manager.enemies.append(meteor)  # type: ignore[arg-type]
            return True

        if enemy_type == SquareMinionBoss:
            if player_x is None or player_y is None:
                return False
            if is_side_scroll:
                x = Config.SCREEN_WIDTH + 40
                y = random.randint(60, Config.SCREEN_HEIGHT - 100)
            else:
                x = random.randint(40, Config.SCREEN_WIDTH - 80)
                y = -50
            new_enemy = SquareMinionBoss(x, y, player_x, player_y)
            new_enemy.health = int(new_enemy.health * self.enemy_health_multiplier)
            entity_manager.enemies.append(new_enemy)
            return True

        if enemy_type == ElementalRobot:
            spawn_x = random.randint(
                int(Config.SCREEN_WIDTH * 0.2), int(Config.SCREEN_WIDTH * 0.8)
            )
            target_y = Config.SCREEN_HEIGHT * 0.15
            robot = ElementalRobot(
                spawn_x,
                target_y,
                difficulty_multiplier=self.enemy_health_multiplier,
            )
            entity_manager.enemies.append(robot)
            return True

        if enemy_type == StoneSentry:
            new_enemy = StoneSentry()
            new_enemy.health = int(new_enemy.health * self.enemy_health_multiplier)
            entity_manager.enemies.append(new_enemy)
            return True

        new_enemy = cast(EnemyWithHealth, enemy_type())
        new_enemy.health = int(new_enemy.health * self.enemy_health_multiplier)
        entity_manager.enemies.append(new_enemy)  # type: ignore[arg-type]
        return True

    def _record_weighted_spawn(self, enemy_type: type) -> None:
        """Atualiza contadores de telemetria do spawn ponderado."""
        type_name = enemy_type.__name__
        self.weighted_spawn_by_type[type_name] = (
            self.weighted_spawn_by_type.get(type_name, 0) + 1
        )

    def _flush_weighted_telemetry(self, dt: float) -> None:
        """Emite telemetria periódica para calibrar o modelo ponderado."""
        if not self.weighted_telemetry_enabled:
            return

        self.weighted_telemetry_timer += dt
        if self.weighted_telemetry_timer < DifficultyConfig.WEIGHTED_TELEMETRY_INTERVAL:
            return

        attempts = max(1, self.weighted_spawn_attempts)
        success_ratio = self.weighted_spawn_success / attempts
        blocked_ratio = self.weighted_spawn_blocked / attempts
        occupancy_values = list(self.weighted_occupancy_samples)
        sample_count = len(occupancy_values)
        p95_occupancy = self._percentile(occupancy_values, 0.95)
        near_cap_ratio = self.weighted_near_cap_samples / max(1, sample_count)
        hard_cap_ratio = self.weighted_hard_cap_samples / max(1, sample_count)
        by_type_text = ", ".join(
            f"{name}:{count}"
            for name, count in sorted(self.weighted_spawn_by_type.items())
        )
        logger.info(
            "[WeightedSpawn] level=%s success=%.2f blocked=%.2f attempts=%s peak=%s p95=%.1f near_cap=%.2f hard_cap=%.2f dist={%s}",
            self.current_level_number,
            success_ratio,
            blocked_ratio,
            self.weighted_spawn_attempts,
            self.weighted_peak_occupancy,
            p95_occupancy,
            near_cap_ratio,
            hard_cap_ratio,
            by_type_text,
        )

        self.weighted_telemetry_timer = 0.0
        self.weighted_spawn_attempts = 0
        self.weighted_spawn_success = 0
        self.weighted_spawn_blocked = 0
        self.weighted_spawn_by_type = {}
        self.weighted_occupancy_samples.clear()
        self.weighted_peak_occupancy = 0
        self.weighted_near_cap_samples = 0
        self.weighted_hard_cap_samples = 0

    def _update_legacy_enemy_spawn(
        self,
        dt: float,
        entity_manager: "EntityManager",
        player_x: float | None,
        player_y: float | None,
        is_side_scroll: bool,
    ) -> None:
        """Mantém comportamento anterior de timer por tipo (fallback)."""
        for enemy_type, timer in self.enemy_timers.items():
            timer.update(dt)
            if timer.done() and random.random() < self.spawn_intensity:
                if not self._should_spawn_enemy(enemy_type, entity_manager):
                    timer.start()
                    continue

                if not self._can_spawn_now(enemy_type):
                    timer.start()
                    continue

                self._spawn_enemy_of_type(
                    enemy_type,
                    entity_manager,
                    player_x=player_x,
                    player_y=player_y,
                    is_side_scroll=is_side_scroll,
                )
                self._register_spawn(enemy_type)
                timer.start()

    def _update_weighted_enemy_spawn(
        self,
        dt: float,
        entity_manager: "EntityManager",
        player_x: float | None,
        player_y: float | None,
        is_side_scroll: bool,
    ) -> None:
        """Novo spawn ponderado com anti-repetição e caps adaptativos."""
        self.weighted_spawn_timer.update(dt)
        if not self.weighted_spawn_timer.done():
            return

        self.weighted_spawn_attempts += 1

        if random.random() >= self.spawn_intensity:
            self.weighted_spawn_blocked += 1
            self.weighted_spawn_timer.start()
            return

        enemy_type = self._pick_weighted_enemy_type(entity_manager)
        if enemy_type is None:
            self.weighted_spawn_blocked += 1
            self.weighted_spawn_timer.start()
            return

        if not self._should_spawn_enemy(enemy_type, entity_manager):
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

        # Sistema de delay inicial (período sem spawn seguido de ativação total)
        if self.warm_up_timer > 0:
            self.warm_up_timer -= dt
            # Durante warm-up: intensidade 0% (nenhum spawn)
            self.spawn_intensity = 0.0
            # CORRIGIDO: Não fazer early return - deixar timers atualizarem
        else:
            # Após warm-up: intensidade 100% (spawn normal)
            self.spawn_intensity = 1.0

        if self.use_weighted_spawn:
            self._record_pressure_sample(entity_manager)
            self._update_weighted_enemy_spawn(
                dt,
                entity_manager,
                player_x=player_x,
                player_y=player_y,
                is_side_scroll=is_side_scroll,
            )
            self._flush_weighted_telemetry(dt)
        else:
            self._update_legacy_enemy_spawn(
                dt,
                entity_manager,
                player_x=player_x,
                player_y=player_y,
                is_side_scroll=is_side_scroll,
            )

        # Spawner de minas
        if self.config.mines_enabled:
            self.mine_spawn_timer.update(dt)
            if self.mine_spawn_timer.done() and random.random() < self.spawn_intensity:
                if random.random() < 0.5:  # 50% de chance de spawnar minas
                    num_mines = random.choices(
                        [2, 3, 5], weights=[0.50, 0.25, 0.10], k=1
                    )[0]
                    min_distance = 60  # Distância mínima entre minas
                    positions: list[int] = []
                    for _ in range(num_mines):
                        attempts = 0
                        while attempts < 10:
                            x = random.randint(20, Config.SCREEN_WIDTH - 20)
                            if all(abs(x - px) > min_distance for px in positions):
                                positions.append(x)
                                entity_manager.enemies.append(
                                    ExplosiveMine(x=x, y=-random.uniform(10, 100))
                                )
                                break
                            attempts += 1
                    self.mine_spawn_timer.start()

        # Spawner de formações
        if self.config.formations_enabled:
            self.formation_spawn_timer.update(dt)
            if (
                self.formation_spawn_timer.done()
                and random.random() < self.spawn_intensity
            ):
                # Criar formação
                formation_type = self.config.get_random_formation_type()
                if formation_type:
                    # Buscar configuração do tipo de formação
                    config = FORMATION_CONFIGS[formation_type]
                    patterns = config.get(
                        "patterns",
                        [FormationPattern.SPIRAL_ENTRY, FormationPattern.CIRCLE],
                    )

                    # Determinar contagem de naves
                    if "count_options" in config:
                        count = random.choice(config["count_options"])
                    elif "count_range" in config:
                        count_range = config["count_range"]
                        count = random.randint(count_range[0], count_range[1])
                    else:
                        count = 5  # Fallback

                    # CORRIGIDO: Usar valores pré-calculados em vez de condicionais repetidos
                    margin_value: Union[float, Callable[[int], float]] = (
                        self._formation_safe_margins.get(formation_type, 200)
                    )  # type: ignore
                    if callable(margin_value):
                        safe_margin = float(margin_value(count))
                    else:
                        safe_margin = float(margin_value)

                    # Garantir que safe_margin não ultrapasse metade da largura da tela
                    safe_margin = min(safe_margin, Config.SCREEN_WIDTH / 2 - 100)

                    # CORRIGIDO: Calcular posições SEMPRE (não cachear para evitar desync)
                    formation_positions = [
                        f.center_x for f in entity_manager.formations
                    ]

                    # Tentar encontrar uma posição que não esteja muito próxima de outras formações
                    min_distance = 300  # Distância mínima entre formações (pixels)
                    max_attempts = 10  # Número máximo de tentativas
                    entry_x = None

                    for _ in range(max_attempts):
                        candidate_x = random.randint(
                            int(safe_margin), int(Config.SCREEN_WIDTH - safe_margin)
                        )

                        # Verificar distância contra posições atuais
                        too_close = any(
                            abs(candidate_x - pos) < min_distance
                            for pos in formation_positions
                        )

                        if not too_close:
                            entry_x = candidate_x
                            break

                    # Se não encontrou posição boa após todas as tentativas, usar a última
                    if entry_x is None:
                        entry_x = random.randint(
                            int(safe_margin), int(Config.SCREEN_WIDTH - safe_margin)
                        )

                    # Calcular entry_y baseado no padrão para evitar que fique cortado no topo
                    # CORRIGIDO: Usar valores pré-calculados
                    entry_y = float(self._formation_entry_y.get(formation_type, 80.0))

                    from ..entities.alien import Alien

                    new_formation = Formation(Alien, count, entry_x, entry_y, patterns)
                    entity_manager.formations.append(new_formation)

                    # Reiniciar timer
                    min_t, max_t = Config.FORMATION_SPAWN_INTERVAL
                    self.formation_spawn_timer = Timer(random.uniform(min_t, max_t))
                    self.formation_spawn_timer.start()

        # Timer separado para meteoros teleguiados (a cada 3 segundos)
        # Só funciona se a fase tem meteoros na lista de tipos
        from ..entities.meteor import Meteor

        if (
            Meteor in self.config.enemy_types
            and player_x is not None
            and player_y is not None
        ):
            self.guided_meteor_timer.update(dt)
            if (
                self.guided_meteor_timer.done()
                and random.random() < self.spawn_intensity
            ):
                # Chance de spawnar meteoro guiado baseada na intensidade
                base_chance = Config.GUIDED_METEOR_NORMAL_PHASES_CHANCE
                if random.random() < base_chance:
                    from ..entities.guided_meteor import GuidedMeteor

                    guided_meteor = GuidedMeteor(
                        size=random.randint(15, 25),
                        x=random.randint(0, Config.SCREEN_WIDTH),
                        y=-30,  # Spawna acima da tela
                        vx=0,  # Velocidade inicial baixa
                        vy=50,  # Velocidade inicial para baixo
                        target_x=player_x,
                        target_y=player_y,
                    )
                    entity_manager.enemies.append(guided_meteor)

                self.guided_meteor_timer.start()  # Reinicia timer de 3 segundos

    def stop(self) -> None:
        self.stopped = True

    def set_level(self, level_number: int) -> None:
        """Atualiza o spawner para uma nova fase."""
        self.current_level_number = level_number
        self.config = self.level_manager.get_level(
            self.current_level_number, self.difficulty_preset
        )
        self.stopped = False

        # Reiniciar warm-up para nova fase (respeitar tempo de preparação como no início)
        self.warm_up_timer = Config.PREPARATION_TIME
        self.spawn_intensity = 0.0

        # Recriar pipeline de spawn para nova fase
        self._reset_spawn_pipeline()

        # Reiniciar timer de meteoros guiados para nova fase
        self.guided_meteor_timer.start()


class PowerUpSpawner:
    def __init__(self, difficulty: DifficultyPreset = DifficultyPreset.NORMAL) -> None:
        self.difficulty = difficulty
        self._reset_timer()

    def _select_powerup_by_rarity(self) -> PowerUpType:
        """Seleciona power-up baseado na raridade individual de cada tipo."""
        powerup_weights = get_powerup_weights(self.difficulty)

        # Cria lista ponderada
        powerup_types = list(powerup_weights.keys())
        weights = list(powerup_weights.values())

        # Escolhe baseado nos pesos
        return random.choices(powerup_types, weights=weights)[0]

    def _reset_timer(self) -> None:
        min_t, max_t = Config.POWERUP_SPAWN_INTERVAL
        self.timer = Timer(random.uniform(min_t, max_t))
        self.timer.start()

    def update(self, dt: float, powerups: List[PowerUp]) -> None:
        self.timer.update(dt)
        if self.timer.done():
            powerup_type = self._select_powerup_by_rarity()  # Usa sistema de raridade
            powerups.append(PowerUp(powerup_type))
            self._reset_timer()

        powerups[:] = [p for p in powerups if not p.is_off_screen()]


class StarSpawner:
    def __init__(self) -> None:
        self.kill_counter = 0
        self.kill_threshold = getattr(Config, "STAR_SPAWN_KILL_THRESHOLD", 200)

    def update(self, dt: float, stars: List[Star]) -> None:
        # Estrelas só aparecem após derrotar N inimigos, não por timer.
        pass

    def add_kills(self, count: int, stars: List[Star]) -> None:
        """Acumula abates e spawna uma estrela quando atingir o limiar.
        Após spawn, reseta a contagem.
        """
        if count <= 0:
            return
        self.kill_counter += count
        if self.kill_counter >= self.kill_threshold:
            self.kill_counter = 0
            x = random.randint(40, Config.SCREEN_WIDTH - 40)
            y = -random.uniform(20, 100)
            stars.append(Star(x, y))
