from dataclasses import dataclass
from typing import Type
import random
from enum import Enum
from ..entities.meteor import Meteor
from ..entities.alien import Alien
from ..entities.boss import Boss
from ..entities.explosive_mine import ExplosiveMine
from ..entities.eye_enemy import EyeEnemy
from ..entities.spike_boss import SpikeBoss


class FormationType(Enum):
    SPIRAL_CIRCLE = "spiral_circle"
    SPIRAL_V = "spiral_v"
    SPIRAL_SQUARE = "spiral_square"
    FULL_CYCLE = "full_cycle"
    SPIRAL_LINE = "spiral_line"


@dataclass
class LevelConfig:
    level_number: int
    enemy_spawn_config: dict[
        Type[Meteor | Alien | ExplosiveMine | EyeEnemy], float
    ]  # Tipo -> tempo de spawn
    enemies_to_clear: int  # quantos inimigos para passar de fase
    boss_type: Type[Boss | SpikeBoss] | None = None  # O tipo de classe do chefe (opcional)
    mines_enabled: bool = False  # Se as minas estão habilitadas neste nível
    formations_enabled: bool = False  # Se formações estão habilitadas neste nível
    formation_types: list[FormationType] | None = None  # Tipos de formação disponíveis

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
            return random.choice(self.formation_types).value
        return None
    
    def validate_formation_types(self, valid_types: set[str]) -> list[str]:
        """
        Valida os tipos de formação configurados.
        
        Args:
            valid_types: Conjunto de tipos válidos (chaves de FORMATION_CONFIGS)
        
        Returns:
            Lista de tipos inválidos encontrados (vazia se todos válidos)
        """
        if not self.formation_types:
            return []
        
        invalid: list[str] = []
        for formation_type in self.formation_types:
            if formation_type.value not in valid_types:
                invalid.append(formation_type.value)
        
        return invalid


LEVELS: list[LevelConfig] = [
    LevelConfig(
        level_number=1,
        enemy_spawn_config={
            Meteor: 0.6,            
            #EyeEnemy: 15.0,
        },
        enemies_to_clear=200,
        #boss_type=Boss,     
    ),
    LevelConfig(
        level_number=2,
        enemy_spawn_config={
            Alien: 0.7,
        },
        enemies_to_clear=100,
        mines_enabled=True,
    ),
    LevelConfig(
        level_number=3,
        enemy_spawn_config={
            Meteor: 0.5,
            Alien: 2.5,
        },
        enemies_to_clear=300,
        boss_type=Boss,
        mines_enabled=True,
    ),
    LevelConfig(
        level_number=4,
        enemy_spawn_config={
            #Meteor: 1.0,
            #EyeEnemy: 5.0,
        },
        enemies_to_clear=150,
        mines_enabled=True,
        formations_enabled=True,
        formation_types=[FormationType.SPIRAL_CIRCLE, FormationType.SPIRAL_V, FormationType.SPIRAL_SQUARE, FormationType.FULL_CYCLE, FormationType.SPIRAL_LINE],
    ),
    LevelConfig(
        level_number=5,
        enemy_spawn_config={
            Meteor: 1.5,
            EyeEnemy: 5.0,
        },
        enemies_to_clear=200,
        formations_enabled=True,
        formation_types=[FormationType.SPIRAL_V, FormationType.FULL_CYCLE, FormationType.SPIRAL_LINE],
    ),
    LevelConfig(
        level_number=6,
        enemy_spawn_config={
            Meteor: 0.8,
            Alien: 3.0,
        },
        enemies_to_clear=300,
        mines_enabled=True,
        formations_enabled=True,
        formation_types=[FormationType.SPIRAL_CIRCLE, FormationType.SPIRAL_V, FormationType.FULL_CYCLE],
    ),
    LevelConfig(
        level_number=7,
        enemy_spawn_config={
            Meteor: 1.5,
            EyeEnemy: 5.0,
        },
        enemies_to_clear=250,
        boss_type=SpikeBoss,
        mines_enabled=True,
        formations_enabled=True,
        formation_types=[FormationType.SPIRAL_CIRCLE, FormationType.SPIRAL_V, FormationType.SPIRAL_LINE],
    ),
        LevelConfig(
        level_number=8,
        enemy_spawn_config={
            Meteor: 0.1,
        },
        enemies_to_clear=200,        
    ),
    # Adicione mais fases aqui
]


class LevelManager:
    """
    Gerencia a progressão de níveis no jogo.
    """
    def __init__(self, levels: list[LevelConfig]):
        self._levels = sorted(levels, key=lambda lvl: lvl.level_number)
        self.current_level_index = 0

    def start_next_level(self) -> None:
        """
        Avança para o próximo nível, se houver.
        """
        if not self.is_last_level():
            self.current_level_index += 1

    def get_current_config(self) -> LevelConfig:
        """
        Retorna a configuração do nível atual.
        """
        return self._levels[self.current_level_index]

    def is_last_level(self) -> bool:
        """
        Verifica se o nível atual é o último.
        """
        return self.current_level_index >= len(self._levels) - 1

    def reset(self) -> None:
        """
        Reinicia a progressão para o primeiro nível.
        """
        self.current_level_index = 0