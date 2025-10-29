import random
from typing import List, Union, TYPE_CHECKING, Dict, Type

from ..core.time import Timer
from ..core.config import Config, PowerUpType
from ..entities.powerup import PowerUp
from ..core.levels import LevelConfig

from ..entities.explosive_mine import ExplosiveMine
from ..entities.eye_enemy import EyeEnemy

if TYPE_CHECKING:
    from ..entities.meteor import Meteor
    from ..entities.alien import Alien


class EnemySpawner:
    def __init__(self, config: LevelConfig, is_initial_level: bool = False):
        self.config = config
        self.stopped = False

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

    def update(
        self,
        dt: float,
        enemies: List[Union["Meteor", "Alien", "ExplosiveMine", "EyeEnemy"]],
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
                    x = random.randint(40, Config.SCREEN_WIDTH - 80)
                    y = random.randint(40, 100)
                    new_enemy = EyeEnemy(x, y)
                else:
                    new_enemy = enemy_type()  # type: ignore[misc]
                enemies.append(new_enemy)  # type: ignore[arg-type]
                timer.start()  # Reiniciar timer

        # Spawner de minas
        if self.config.mines_enabled:
            self.mine_spawn_timer.update(dt)
            if self.mine_spawn_timer.done() and random.random() < self.spawn_intensity:
                if random.random() < 0.5:  # 50% de chance de spawnar minas
                    num_mines = random.choices(
                        [2, 3, 5], weights=[0.50, 0.25, 0.10], k=1
                    )[0]
                    for _ in range(num_mines):
                        enemies.append(
                            ExplosiveMine(y=-random.uniform(10, 100))
                        )  # Adiciona um delay aleatório no eixo y
                    self.mine_spawn_timer.start()
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
                    enemies.append(guided_meteor)

                self.guided_meteor_timer.start()  # Reinicia timer de 3 segundos

    def stop(self) -> None:
        self.stopped = True

    def set_level(self, config: LevelConfig) -> None:
        """Atualiza o spawner para uma nova fase."""
        self.config = config
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
