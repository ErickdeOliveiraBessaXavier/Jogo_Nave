from dataclasses import dataclass
from typing import Type
import random
from ..entities.meteor import Meteor
from ..entities.alien import Alien
from ..entities.boss import Boss


@dataclass
class LevelConfig:
    level_number: int
    enemy_spawn_config: dict[Type[Meteor | Alien], float]  # Tipo -> tempo de spawn
    enemies_to_clear: int  # quantos inimigos para passar de fase
    boss_type: Type[Boss] | None = None  # O tipo de classe do chefe (opcional)
    
    @property
    def enemy_types(self) -> list[Type[Meteor | Alien]]:
        """Retorna lista de tipos de inimigos configurados."""
        return list(self.enemy_spawn_config.keys())
    
    def get_spawn_time(self, enemy_type: Type[Meteor | Alien]) -> float:
        """Retorna o tempo de spawn para um tipo específico de inimigo."""
        return self.enemy_spawn_config.get(enemy_type, 1.0)
    
    def get_random_enemy_type(self) -> Type[Meteor | Alien]:
        """Retorna um tipo de inimigo aleatório da lista."""
        return random.choice(self.enemy_types)


LEVELS: list[LevelConfig] = [
    LevelConfig(
        level_number=1,
        enemy_spawn_config={
            Meteor: 0.8,  # Meteoros a cada 0.8 segundos
        },
        enemies_to_clear=150,
        boss_type=Boss,
    ),
    LevelConfig(
        level_number=2,
        enemy_spawn_config={
            Alien: 1.5,   # Só aliens a cada 1.5 segundos
        },
        enemies_to_clear=100),
    LevelConfig(
        level_number=3, 
        enemy_spawn_config={
            Meteor: 0.3,  # Meteoros rápidos a cada 0.3 segundos
            Alien: 2.0,   # Aliens a cada 1.2 segundos
        },
        enemies_to_clear=150
    ),
    # Adicione mais fases aqui
]