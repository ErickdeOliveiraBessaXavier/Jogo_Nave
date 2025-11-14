from dataclasses import dataclass
from typing import Type
import random
from ..entities.meteor import Meteor
from ..entities.alien import Alien
from ..entities.boss import Boss
from ..entities.explosive_mine import ExplosiveMine
from ..entities.eye_enemy import EyeEnemy
from ..entities.spike_boss import SpikeBoss


# ============================================================================
# CONSTANTES DE CONFIGURAÇÃO
# ============================================================================


class DifficultyConfig:
    """Constantes para balanceamento de dificuldade."""

    BASE_METEOR_SPAWN_TIME = 1.2
    BASE_ALIEN_SPAWN_TIME = 2.5
    BASE_EYE_SPAWN_TIME = 6.0

    MIN_ENEMIES_TO_CLEAR = 10
    BASE_ENEMIES = 25
    ENEMIES_PER_LEVEL = 5
    ENEMY_VARIATION = 20

    DIFFICULTY_SCALING = 0.15
    MAX_DIFFICULTY_MULTIPLIER = 3.0

    MINES_UNLOCK_LEVEL = 2
    MINES_PROBABILITY = 0.6
    FORMATIONS_UNLOCK_LEVEL = 4


# ============================================================================
# DATACLASS - DEFINIR ANTES DE USAR
# ============================================================================


@dataclass
class LevelConfig:
    """Configuração de um nível do jogo."""

    level_number: int
    enemy_spawn_config: dict[
        Type[Meteor | Alien | ExplosiveMine | EyeEnemy], float
    ]  # Tipo -> tempo de spawn
    enemies_to_clear: int  # quantos inimigos para passar de fase
    boss_type: Type[Boss | SpikeBoss] | None = (
        None  # O tipo de classe do chefe (opcional)
    )
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
            if formation_type not in valid_types:
                invalid.append(formation_type)

        return invalid


# ============================================================================
# GERADOR PROCEDURAL
# ============================================================================


class ProceduralLevelGenerator:
    """
    Gerador de níveis procedurais com progressão de dificuldade.

    Usa fórmulas matemáticas para escalar dificuldade progressivamente:
    - Spawn rate aumenta (tempo diminui)
    - Mais tipos de inimigos aparecem
    - Quantidade de inimigos para limpar aumenta
    - Features (minas, formações) desbloqueadas progressivamente
    """

    def __init__(self, seed: int | None = None):
        """
        Args:
            seed: Semente para geração reproduzível (opcional)
        """
        self.seed = seed or random.randint(0, 999999)

    def generate_level(self, level_number: int) -> LevelConfig:
        """
        Gera configuração procedural para um nível.

        Args:
            level_number: Número do nível a gerar

        Returns:
            LevelConfig gerado proceduralmente
        """
        # Usar seed + level_number para reproduzibilidade
        random.seed(self.seed + level_number)

        # Calcular multiplicador de dificuldade (1.0 a ~3.0)
        # Cresce logaritmicamente para não ficar impossível muito rápido
        difficulty = 1.0 + (level_number * DifficultyConfig.DIFFICULTY_SCALING)
        difficulty = min(difficulty, DifficultyConfig.MAX_DIFFICULTY_MULTIPLIER)

        # Gerar configuração baseada na dificuldade
        config = self._generate_config(level_number, difficulty)

        # Resetar seed para não afetar outros randoms
        random.seed()

        return config

    def _generate_config(self, level_number: int, difficulty: float) -> LevelConfig:
        """Gera configuração baseada em dificuldade."""

        # 1. Calcular spawn times (diminui com dificuldade)
        enemy_spawn_config: dict[
            Type[Meteor | Alien | ExplosiveMine | EyeEnemy], float
        ] = {}

        # Meteoros sempre presentes
        base_meteor_time = DifficultyConfig.BASE_METEOR_SPAWN_TIME / difficulty
        enemy_spawn_config[Meteor] = base_meteor_time

        # Nível 2: Foco em Aliens, mas mantém meteoros com spawn baixo
        if level_number == 2:
            base_alien_time = DifficultyConfig.BASE_ALIEN_SPAWN_TIME / difficulty
            enemy_spawn_config[Alien] = base_alien_time
            # Meteoros mais raros para focar em Aliens
            enemy_spawn_config[Meteor] = base_meteor_time * 3.0

        # Nível 3+: Aliens começam a aparecer junto com meteoros
        elif level_number >= 3:
            base_alien_time = DifficultyConfig.BASE_ALIEN_SPAWN_TIME / difficulty
            enemy_spawn_config[Alien] = base_alien_time

        # Eyes aparecem a partir do nível 5
        if level_number >= 5:
            base_eye_time = DifficultyConfig.BASE_EYE_SPAWN_TIME / difficulty
            enemy_spawn_config[EyeEnemy] = base_eye_time

        # 2. Calcular quantos inimigos para limpar
        # Fórmula: BASE + (nível * MULTIPLIER) com alguma variação
        base_enemies = DifficultyConfig.BASE_ENEMIES + (
            level_number * DifficultyConfig.ENEMIES_PER_LEVEL
        )
        variation = random.randint(
            -DifficultyConfig.ENEMY_VARIATION, DifficultyConfig.ENEMY_VARIATION
        )
        enemies_to_clear = max(
            DifficultyConfig.MIN_ENEMIES_TO_CLEAR, base_enemies + variation
        )

        # 3. Features progressivas
        mines_enabled = (
            level_number >= DifficultyConfig.MINES_UNLOCK_LEVEL
            and random.random() < DifficultyConfig.MINES_PROBABILITY
        )
        formations_enabled = level_number >= DifficultyConfig.FORMATIONS_UNLOCK_LEVEL

        # 4. Tipos de formação disponíveis (mais tipos em níveis altos)
        formation_types: list[str] | None = None
        if formations_enabled:
            all_formations = [
                "spiral_circle",
                "spiral_v",
                "spiral_square",
                "full_cycle",
                "spiral_line",
            ]

            if level_number >= 6:
                # Níveis altos: todas as formações
                formation_types = all_formations
            else:
                # Níveis médios: subset aleatório (3-4 formações)
                num_formations = random.randint(3, 4)
                formation_types = random.sample(all_formations, num_formations)

        config = LevelConfig(
            level_number=level_number,
            enemy_spawn_config=enemy_spawn_config,
            enemies_to_clear=enemies_to_clear,
            boss_type=None,  # Procedural não gera bosses (são fixos)
            mines_enabled=mines_enabled,
            formations_enabled=formations_enabled,
            formation_types=formation_types,
        )

        # Validar formações se habilitadas (opcional, comentado por enquanto)
        # if config.formations_enabled and config.formation_types:
        #     try:
        #         from ..systems.formation_spawner import FORMATION_CONFIGS
        #         invalid = config.validate_formation_types(set(FORMATION_CONFIGS.keys()))
        #         if invalid:
        #             print(f"⚠️ Aviso: Formações inválidas no nível {level_number}: {invalid}")
        #     except ImportError:
        #         pass  # FORMATION_CONFIGS não disponível

        return config


# ============================================================================
# NÍVEIS FIXOS (HANDCRAFTED)
# ============================================================================

FIXED_LEVELS: dict[int, LevelConfig] = {
    # Nível 1: Tutorial - Apenas meteoros, ritmo controlado
    1: LevelConfig(
        level_number=1,
        enemy_spawn_config={
            Meteor: 0.6,
        },
        enemies_to_clear=200,
    ),
    # Nível 3: Primeiro Boss - Mix de inimigos + Boss clássico
    3: LevelConfig(
        level_number=3,
        enemy_spawn_config={
            Meteor: 0.5,
            Alien: 2.5,
        },
        enemies_to_clear=300,
        boss_type=Boss,
        mines_enabled=True,
    ),
    # Nível 7: Boss Spike - Desafio avançado com todas as features
    7: LevelConfig(
        level_number=7,
        enemy_spawn_config={
            Meteor: 1.5,
            EyeEnemy: 5.0,
        },
        enemies_to_clear=250,
        boss_type=SpikeBoss,
        mines_enabled=True,
        formations_enabled=True,
        formation_types=["spiral_circle", "spiral_v", "spiral_line"],
    ),
}


# ============================================================================
# FUNÇÕES PÚBLICAS
# ============================================================================

# Gerador procedural (singleton)
_procedural_generator = ProceduralLevelGenerator()


def get_level_config(level_number: int) -> LevelConfig:
    """
    Retorna a configuração de um nível.

    Sistema Híbrido:
    - Se o nível está em FIXED_LEVELS, retorna a versão handcrafted
    - Caso contrário, gera proceduralmente

    Args:
        level_number: Número do nível desejado (1+)

    Returns:
        LevelConfig do nível (fixo ou procedural)
    """
    # Se é um nível fixo, retornar ele
    if level_number in FIXED_LEVELS:
        return FIXED_LEVELS[level_number]

    # Senão, gerar proceduralmente
    return _procedural_generator.generate_level(level_number)


class LevelManager:
    """Gerenciador de níveis do jogo."""

    def __init__(self, initial_levels: dict[int, LevelConfig] | None = None):
        """
        Args:
            initial_levels: Níveis iniciais (opcional, não usado atualmente)
        """
        self._levels = initial_levels or {}

    def get_level(self, level_number: int) -> LevelConfig:
        """Retorna a configuração de um nível."""
        return get_level_config(level_number)
