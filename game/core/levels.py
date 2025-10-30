from dataclasses import dataclass
from typing import Type
import random
from ..entities.meteor import Meteor
from ..entities.alien import Alien
from ..entities.boss import Boss
from ..entities.explosive_mine import ExplosiveMine
from ..entities.eye_enemy import EyeEnemy


@dataclass
class LevelConfig:
    level_number: int
    enemy_spawn_config: dict[
        Type[Meteor | Alien | ExplosiveMine | EyeEnemy], float
    ]  # Tipo -> tempo de spawn
    enemies_to_clear: int  # quantos inimigos para passar de fase
    boss_type: Type[Boss] | None = None  # O tipo de classe do chefe (opcional)
    mines_enabled: bool = False  # Se as minas estão habilitadas neste nível
    formations_enabled: bool = False  # Se formações estão habilitadas neste nível
    formation_types: list[str] | None = None  # Tipos de formação disponíveis

    @property
    def enemy_types(self) -> list[Type[Meteor | Alien | ExplosiveMine | EyeEnemy]]:
        """Retorna lista de tipos de inimigos configurados."""
        return list(self.enemy_spawn_config.keys())

    def get_spawn_time(
        self, enemy_type: Type[Meteor | Alien | ExplosiveMine | EyeEnemy]
    ) -> float:
        """Retorna o tempo de spawn para um tipo específico de inimigo."""
        return self.enemy_spawn_config.get(enemy_type, 1.0)

    def get_random_enemy_type(self) -> Type[Meteor | Alien | ExplosiveMine | EyeEnemy]:
        """Retorna um tipo de inimigo aleatório da lista."""
        return random.choice(self.enemy_types)
    
    def get_random_formation_type(self) -> str | None:
        """Retorna um tipo de formação aleatório da lista."""
        if self.formation_types:
            return random.choice(self.formation_types)
        return None


LEVELS: list[LevelConfig] = [
    LevelConfig(
        level_number=1,
        enemy_spawn_config={
            # Meteor: 0.8,            
            # EyeEnemy: 5.0,
        },
        enemies_to_clear=200,
        formations_enabled=True,
        formation_types=["spiral_circle", "spiral_v"]
    ),
    LevelConfig(
        level_number=2,
        enemy_spawn_config={
            Alien: 0.7,
        },
        enemies_to_clear=100,
        mines_enabled=True,
        formations_enabled=True,
        formation_types=["spiral_circle", "spiral_v"],
    ),
    LevelConfig(
        level_number=3,
        enemy_spawn_config={
            Meteor: 0.5,
            Alien: 2.5,
        },
        enemies_to_clear=250,
        boss_type=Boss,
        mines_enabled=True,
        formations_enabled=True,
        formation_types=["spiral_circle", "spiral_v", "spiral_square"],
    ),
    LevelConfig(
        level_number=4,
        enemy_spawn_config={
            Meteor: 0.4,
            EyeEnemy: 5.0,
        },
        enemies_to_clear=300,
        formations_enabled=True,
        formation_types=["spiral_circle", "spiral_v", "spiral_square", "full_cycle"],
    ),
    # Adicione mais fases aqui
]
