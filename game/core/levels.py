from dataclasses import dataclass
from typing import Type
import random
from ..entities.meteor import Meteor
from ..entities.alien import Alien
from ..entities.boss import Boss
from ..entities.explosive_mine import ExplosiveMine


@dataclass
class LevelConfig:
    level_number: int
    enemy_spawn_config: dict[Type[Meteor | Alien | ExplosiveMine], float]  # Tipo -> tempo de spawn
    enemies_to_clear: int  # quantos inimigos para passar de fase
    boss_type: Type[Boss] | None = None  # O tipo de classe do chefe (opcional)
    mines_enabled: bool = False # Se as minas estão habilitadas neste nível

    @property
    def enemy_types(self) -> list[Type[Meteor | Alien | ExplosiveMine]]:
        """Retorna lista de tipos de inimigos configurados."""
        return list(self.enemy_spawn_config.keys())

    def get_spawn_time(self, enemy_type: Type[Meteor | Alien | ExplosiveMine]) -> float:
        """Retorna o tempo de spawn para um tipo específico de inimigo."""
        return self.enemy_spawn_config.get(enemy_type, 1.0)

    def get_random_enemy_type(self) -> Type[Meteor | Alien | ExplosiveMine]:
        """Retorna um tipo de inimigo aleatório da lista."""
        return random.choice(self.enemy_types)


LEVELS: list[LevelConfig] = [
    LevelConfig(
        level_number=1,
        enemy_spawn_config={
            Meteor: 0.9,
        },
        enemies_to_clear=250,
    ),
    LevelConfig(
        level_number=2,
        enemy_spawn_config={
            Alien: 0.7,
        },
        enemies_to_clear=50,
        mines_enabled=True,
    ),
    LevelConfig(
        level_number=3,
        enemy_spawn_config={
            Meteor: 0.4,  # Meteoros rápidos a cada 0.3 segundos
            Alien: 1.5,  # Aliens a cada 0.8 segundos
        },
        enemies_to_clear=250,
        boss_type=Boss,
        mines_enabled=True,
    ),
    # Adicione mais fases aqui
]
