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

    def update(self, dt: float, enemies: List[Union['Meteor', 'Alien']]) -> None:
        if self.stopped: return
        self.timer.update(dt)
        if self.timer.done():
            # Cria uma instÃ¢ncia do tipo de inimigo definido na configuraÃ§Ã£o da fase
            enemies.append(self.config.enemy_type())
            self.timer.start()

    def stop(self) -> None:
        self.stopped = True

    def set_level(self, config: LevelConfig) -> None:
        """ Atualiza o spawner para uma nova fase. """
        self.config = config
        self.timer.duration = self.config.spawn_every
        self.stopped = False
        self.timer.start()

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