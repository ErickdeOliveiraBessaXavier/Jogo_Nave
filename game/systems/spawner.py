import random
from typing import TYPE_CHECKING, Dict, Type, TypedDict, Tuple, List


# Moved Timer class definition here
class Timer:
    def __init__(self, duration: float = 0.0):
        self.duration = duration
        self.time = 0.0
        self.active = False

    def start(self, duration: float | None = None):
        if duration is not None:
            self.duration = duration
        self.time = self.duration
        self.active = True

    def update(self, dt: float):
        if self.active:
            self.time -= dt
            if self.time <= 0:
                self.active = False

    def done(self) -> bool:
        return not self.active

    def get_progress(self) -> float:
        if self.duration == 0 or not self.active:
            return 0.0
        return max(0.0, min(1.0, (self.duration - self.time) / self.duration))


from ..core.config import Config, PowerUpType
from ..entities.powerup import PowerUp
from ..core.levels import LevelManager
from ..entities.formation import Formation, FormationPattern

from ..entities.meteor_pool import MeteorPool
from ..entities.eye_enemy import EyeEnemy
from ..entities.explosive_mine import ExplosiveMine

if TYPE_CHECKING:
    from ..systems.entity_manager import EntityManager


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
    def __init__(self, level_manager: LevelManager, meteor_pool: MeteorPool, is_initial_level: bool = False):
        self.level_manager = level_manager
        self.meteor_pool = meteor_pool
        self.current_level_number = 1  # EnemySpawner starts at level 1
        self.config = self.level_manager.get_level(self.current_level_number)
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
        else:
            # Após warm-up: intensidade 100% (spawn normal)
            self.spawn_intensity = 1.0

        # Atualizar e verificar cada timer de inimigo
        for enemy_type, timer in self.enemy_timers.items():
            timer.update(dt)
            if timer.done() and random.random() < self.spawn_intensity:
                if enemy_type == EyeEnemy:
                    # Limitar o número de EyeEnemies na tela a 5
                    eye_enemy_count = sum(isinstance(e, EyeEnemy) for e in entity_manager.enemies)
                    if eye_enemy_count < 5:
                        x = random.randint(40, Config.SCREEN_WIDTH - 80)
                        y = random.randint(40, 100)
                        new_enemy = EyeEnemy(x, y)
                        entity_manager.enemies.append(new_enemy)
                else:
                    from ..entities.meteor import Meteor

                    if enemy_type == Meteor:
                        # Usar o pool para meteoros
                        meteor = self.meteor_pool.get()
                        entity_manager.enemies.append(meteor)
                    else:
                        # Outros inimigos normalmente
                        new_enemy = enemy_type()  # type: ignore[misc]
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
                    if formation_type not in FORMATION_CONFIGS:
                        # Warning: tipo de formação não existe
                        print(
                            f"WARNING: Formation type '{formation_type}' not found in FORMATION_CONFIGS. Skipping."
                        )
                    else:
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

                        # Calcular margem segura baseada no tipo de formação
                        # Evitar spawn próximo às bordas para formações não saírem da tela
                        if formation_type == "spiral_circle":
                            safe_margin = Config.FORMATION_CIRCLE_RADIUS
                        elif formation_type == "spiral_v":
                            half = count // 2
                            safe_margin = half * Config.FORMATION_V_SPACING
                        elif formation_type == "spiral_square":
                            safe_margin = Config.FORMATION_SQUARE_SIZE / 2
                        elif formation_type == "spiral_line":
                            safe_margin = (
                                (count - 1) * Config.FORMATION_LINE_SPACING
                            ) / 2
                        elif formation_type == "full_cycle":
                            # Usar margem do círculo (maior padrão)
                            safe_margin = Config.FORMATION_CIRCLE_RADIUS
                        else:
                            safe_margin = 200  # Fallback

                        # Garantir que safe_margin não ultrapasse metade da largura da tela
                        safe_margin = min(safe_margin, Config.SCREEN_WIDTH / 2 - 100)

                        # Tentar encontrar uma posição que não esteja muito próxima de outras formações
                        min_distance = 300  # Distância mínima entre formações (pixels)
                        max_attempts = 10  # Número máximo de tentativas
                        entry_x = None

                        for _ in range(max_attempts):
                            candidate_x = random.randint(
                                int(safe_margin), int(Config.SCREEN_WIDTH - safe_margin)
                            )

                            # Verificar distância de todas as formações existentes
                            too_close = False
                            for existing_formation in entity_manager.formations:
                                distance = abs(
                                    candidate_x - existing_formation.center_x
                                )
                                if distance < min_distance:
                                    too_close = True
                                    break

                            if not too_close:
                                entry_x = candidate_x
                                break

                        # Se não encontrou posição boa após todas as tentativas, usar a última
                        if entry_x is None:
                            entry_x = random.randint(
                                int(safe_margin), int(Config.SCREEN_WIDTH - safe_margin)
                            )

                        # Calcular entry_y baseado no padrão para evitar que fique cortado no topo
                        # Considerar o raio/tamanho do padrão para definir posição segura
                        if formation_type in ["spiral_circle", "full_cycle"]:
                            # Círculo precisa de margem = raio + segurança (reduzida)
                            entry_y = Config.FORMATION_CIRCLE_RADIUS + 40
                        elif formation_type == "spiral_square":
                            # Quadrado precisa de margem = metade do lado + segurança (reduzida)
                            entry_y = Config.FORMATION_SQUARE_SIZE / 2 + 40
                        else:
                            # V, linha e outros: margem padrão (reduzida)
                            entry_y = 80

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
        self.config = self.level_manager.get_level(self.current_level_number)
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
        powerup_chances = Config.POWERUP_RARITY_CHANCES

        # Cria lista ponderada
        powerup_types = list(powerup_chances.keys())
        weights = list(powerup_chances.values())

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
