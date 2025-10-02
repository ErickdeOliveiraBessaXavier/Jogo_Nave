
from dataclasses import dataclass
from typing import Type
from ..entities.meteor import Meteor
from ..entities.alien import Alien
from ..entities.boss import Boss

@dataclass
class LevelConfig:
    level_number: int
    enemy_type: Type[Meteor | Alien] # O tipo de classe do inimigo
    spawn_every: float # segundos
    enemies_to_clear: int # quantos inimigos para passar de fase
    boss_type: Type[Boss] | None = None # O tipo de classe do chefe (opcional)
    # Podemos adicionar mais parÃ¢metros aqui depois, como velocidade, etc.


LEVELS: list[LevelConfig] = [
    LevelConfig(
        level_number=1,
        enemy_type=Meteor,
        spawn_every=0.6,
        enemies_to_clear=1,
        boss_type=Boss
    ),
    LevelConfig(
        level_number=2,
        enemy_type=Alien,
        spawn_every=1.5,
        enemies_to_clear=15
    ),
    LevelConfig(
        level_number=3,
        enemy_type=Meteor,
        spawn_every=0.3,
        enemies_to_clear=30
    ),
    # Adicione mais fases aqui
]
