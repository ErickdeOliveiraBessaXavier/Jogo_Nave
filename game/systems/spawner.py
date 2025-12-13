import random
from typing import (
    TYPE_CHECKING,
    Dict,
    Type,
    TypedDict,
    Tuple,
    List,
    Protocol,
    cast,
    Union,
    Callable,
)
from ..core.config import config as Config, PowerUpType
from ..core.time import Timer
from ..core.difficulty import DifficultyPreset
from ..entities.powerup import PowerUp
from ..core.levels import LevelManager
from ..entities.formation import Formation, FormationPattern
from ..entities.meteor_pool import MeteorPool
from ..entities.eye_enemy import EyeEnemy
from ..entities.explosive_mine import ExplosiveMine
from ..entities.star import Star
from ..entities.square_minion_boss import SquareMinionBoss

if TYPE_CHECKING:
    from ..systems.entity_manager import EntityManager


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

        # Criar um timer para cada tipo de inimigo
        self.enemy_timers: Dict[Type[object], Timer] = {}
        for enemy_type in self.config.enemy_types:
            spawn_time = self.config.get_spawn_time(enemy_type)
            timer = Timer(spawn_time)
            timer.start()
            self.enemy_timers[enemy_type] = timer

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

    def update(
        self,
        dt: float,
        entity_manager: "EntityManager",
        player_x: float | None = None,
        player_y: float | None = None,
    ) -> None:
        if self.stopped:
            return

        # Sistema de delay inicial (período sem spawn seguido de ativação total)
        if self.warm_up_timer > 0:
            self.warm_up_timer -= dt
            # Durante warm-up: intensidade 0% (nenhum spawn)
            self.spawn_intensity = 0.0
            # CORRIGIDO: Não fazer early return - deixar timers atualizarem
        else:
            # Após warm-up: intensidade 100% (spawn normal)
            self.spawn_intensity = 1.0

        # Atualizar e verificar cada timer de inimigo
        for enemy_type, timer in self.enemy_timers.items():
            timer.update(dt)
            if timer.done() and random.random() < self.spawn_intensity:
                if enemy_type == EyeEnemy:
                    # CORRIGIDO: Sempre recalcular para evitar race condition
                    # quando inimigos morrem entre frames
                    current_eye_count = entity_manager.eye_enemy_count

                    if current_eye_count < 5:
                        x = random.randint(40, Config.SCREEN_WIDTH - 80)
                        y = random.randint(40, 100)
                        new_enemy = EyeEnemy(x, y)
                        new_enemy.health = int(
                            new_enemy.health * self.enemy_health_multiplier
                        )
                        entity_manager.enemies.append(new_enemy)
                else:
                    from ..entities.meteor import Meteor

                    if enemy_type == Meteor:
                        # Usar o pool para meteoros
                        meteor = self.meteor_pool.get()
                        meteor.health = int(
                            meteor.health * self.enemy_health_multiplier
                        )
                        entity_manager.enemies.append(meteor)
                    else:
                        # Outros inimigos normalmente
                        if enemy_type == SquareMinionBoss:
                            # SquareMinionBoss precisa de posição do jogador
                            if player_x is not None and player_y is not None:
                                x = random.randint(40, Config.SCREEN_WIDTH - 80)
                                y = -50  # Spawn acima da tela
                                new_enemy = SquareMinionBoss(x, y, player_x, player_y)
                                new_enemy.health = int(
                                    new_enemy.health * self.enemy_health_multiplier
                                )
                                entity_manager.enemies.append(new_enemy)
                        else:
                            new_enemy = cast(EnemyWithHealth, enemy_type())
                            new_enemy.health = int(
                                new_enemy.health * self.enemy_health_multiplier
                            )
                            entity_manager.enemies.append(new_enemy)  # type: ignore[arg-type]
                timer.start()  # Reiniciar timer

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
                    margin_value: Union[float, Callable[[int], float]] = self._formation_safe_margins.get(formation_type, 200)  # type: ignore
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
                    entry_y = float(
                        self._formation_entry_y.get(formation_type, 80.0)
                    )

                    from ..entities.alien import Alien

                    new_formation = Formation(
                        Alien, count, entry_x, entry_y, patterns
                    )
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

        # Reiniciar warm-up para nova fase (transições suaves)
        self.warm_up_timer = Config.LEVEL_TRANSITION_DELAY
        self.spawn_intensity = 0.0

        # Recriar timers para nova fase
        self.enemy_timers = {}
        for enemy_type in self.config.enemy_types:
            spawn_time = self.config.get_spawn_time(enemy_type)
            timer = Timer(spawn_time)
            timer.start()
            self.enemy_timers[enemy_type] = timer

        # Reiniciar timer de meteoros guiados para nova fase
        self.guided_meteor_timer.start()


class PowerUpSpawner:
    def __init__(self) -> None:
        self._reset_timer()

    def _select_powerup_by_rarity(self) -> PowerUpType:
        """Seleciona power-up baseado na raridade individual de cada tipo."""
        powerup_weights = Config.POWERUP_WEIGHTS

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
        self._reset_timer()
        self.kill_counter = 0
        self.kill_threshold = getattr(Config, "STAR_SPAWN_KILL_THRESHOLD", 200)

    def _reset_timer(self) -> None:
        # Use intervalo configurável para estrelas
        # Garantir tipo de intervalo seguro
        default_interval: tuple[float, float] = (6.0, 10.0)
        conf_interval = getattr(Config, "STAR_SPAWN_INTERVAL", default_interval)
        try:
            min_t, max_t = map(float, conf_interval)  # type: ignore[arg-type]
            spawn_t = random.uniform(min_t, max_t)
        except Exception:
            try:
                spawn_t = float(conf_interval)  # type: ignore[arg-type]
            except Exception:
                spawn_t = sum(default_interval) / 2.0
        self.timer = Timer(spawn_t)
        self.timer.start()

    def update(self, dt: float, stars: List[Star]) -> None:
        # Atualização do timer mantida, porém sem spawn por tempo.
        # Regra atual: estrelas só aparecem após derrotar N inimigos.
        self.timer.update(dt)

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
