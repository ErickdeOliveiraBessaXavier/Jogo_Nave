import random
from typing import List, Union, TYPE_CHECKING

from ..core.time import Timer
from ..core.config import Config
from ..entities.powerup import PowerUp
from ..core.levels import LevelConfig

if TYPE_CHECKING:
    from ..entities.meteor import Meteor
    from ..entities.alien import Alien


class EnemySpawner:
    def __init__(self, config: LevelConfig):
        self.config = config
        self.timer = Timer(self.config.spawn_every)
        self.timer.start()
        self.stopped = False
        
        # Timer separado para meteoros teleguiados (a cada 3 segundos)
        self.guided_meteor_timer = Timer(3.0)
        self.guided_meteor_timer.start()

    def update(self, dt: float,
               enemies: List[Union["Meteor", "Alien"]], 
               player_x: float | None = None, player_y: float | None = None) -> None:
        if self.stopped:
            return
            
        # Timer normal para spawn de inimigos regulares
        self.timer.update(dt)
        if self.timer.done():
            # Cria uma instância do tipo de inimigo definido na configuração da fase
            enemies.append(self.config.enemy_type())
            self.timer.start()
        
        # Timer separado para meteoros teleguiados (a cada 3 segundos)
        if (self.config.enemy_type.__name__ == 'Meteor' and 
            player_x is not None and player_y is not None):
            
            self.guided_meteor_timer.update(dt)
            if self.guided_meteor_timer.done():
                # 10% de chance de spawnar meteoro guiado
                if random.random() < Config.GUIDED_METEOR_NORMAL_PHASES_CHANCE:
                    from ..entities.guided_meteor import GuidedMeteor
                    
                    guided_meteor = GuidedMeteor(
                        size=random.randint(15, 25),
                        x=random.randint(0, Config.SCREEN_WIDTH),
                        y=-30,  # Spawna acima da tela
                        vx=0,  # Velocidade inicial baixa
                        vy=50,  # Velocidade inicial para baixo
                        target_x=player_x,
                        target_y=player_y
                    )
                    enemies.append(guided_meteor)
                
                self.guided_meteor_timer.start()  # Reinicia timer de 3 segundos

    def stop(self) -> None:
        self.stopped = True

    def set_level(self, config: LevelConfig) -> None:
        """Atualiza o spawner para uma nova fase."""
        self.config = config
        self.timer.duration = self.config.spawn_every
        self.stopped = False
        self.timer.start()
        
        # Reiniciar timer de meteoros guiados para nova fase
        self.guided_meteor_timer.start()


class PowerUpSpawner:
    def __init__(self) -> None:
        self._reset_timer()

    def _reset_timer(self) -> None:
        min_t, max_t = Config.POWERUP_SPAWN_INTERVAL
        self.timer = Timer(random.uniform(min_t, max_t))
        self.timer.start()

    def update(self, dt: float, powerups: List[PowerUp]) -> None:
        self.timer.update(dt)
        if self.timer.done():
            powerups.append(PowerUp())
            self._reset_timer()

        powerups[:] = [p for p in powerups if not p.is_off_screen()]
