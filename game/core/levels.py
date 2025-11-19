from dataclasses import dataclass
from typing import Type
import random
import math
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

    BASE_METEOR_SPAWN_TIME: float = 1.2
    BASE_ALIEN_SPAWN_TIME: float = 2.5
    BASE_EYE_SPAWN_TIME: float = 6.0

    MIN_ENEMIES_TO_CLEAR: int = 80
    BASE_ENEMIES: int = 25
    ENEMIES_PER_LEVEL: int = 5
    ENEMY_VARIATION: int = 20

    DIFFICULTY_SCALING: float = 0.15
    MAX_DIFFICULTY_MULTIPLIER: float = 3.0

    # Curvas de dificuldade configuráveis
    SPAWN_RATE_CURVE: str = "logarithmic"  # "linear", "logarithmic", "exponential"
    ENEMY_COUNT_CURVE: str = "linear"  # "linear", "square_root", "logarithmic"

    MINES_UNLOCK_LEVEL: int = 2
    MINES_PROBABILITY: float = 0.6
    FORMATIONS_UNLOCK_LEVEL: int = 4

    # Habilitar variedade de níveis com temas
    LEVEL_VARIETY_ENABLED: bool = True  # True para usar sistema de temas


# ============================================================================
# CURVAS DE DIFICULDADE
# ============================================================================


class DifficultyCurves:
    """Diferentes curvas matemáticas para progressão de dificuldade."""

    @staticmethod
    def linear(level: int, base: float, scaling: float) -> float:
        return base * (1.0 + level * scaling)

    @staticmethod
    def logarithmic(level: int, base: float, scaling: float) -> float:
        return base * (1.0 + math.log1p(level) * scaling)

    @staticmethod
    def exponential(level: int, base: float, scaling: float) -> float:
        return base * math.pow(1.0 + scaling, level)

    @staticmethod
    def square_root(level: int, base: float, scaling: float) -> float:
        return base * (1.0 + math.sqrt(level) * scaling)

    @staticmethod
    def sigmoid(level: int, base: float, midpoint: int = 10) -> float:
        x = (level - midpoint) / 3.0
        sigmoid_value = 1.0 / (1.0 + math.exp(-x))
        return base * (1.0 + sigmoid_value * 2.0)


# ============================================================================
# SISTEMA DE TEMAS DE NÍVEIS
# ============================================================================


@dataclass
class LevelTheme:
    """Define um 'tema' ou estilo de nível."""

    name: str
    description: str
    enemy_weight: dict[str, float]  # "meteor", "alien", "eye" -> peso relativo
    spawn_rate_multiplier: float  # Multiplica spawn rate (>1 = mais inimigos)
    enemies_multiplier: float  # Multiplica quantidade para limpar
    special_feature: str | None = None  # "mines_heavy", "formations_heavy", etc


LEVEL_THEMES = {
    "asteroid_field": LevelTheme(
        name="Campo de Asteroides",
        description="Muitos meteoros, poucos aliens",
        enemy_weight={"meteor": 3.0, "alien": 0.5, "eye": 0.3},
        spawn_rate_multiplier=1.3,
        enemies_multiplier=1.2,
        special_feature=None,
    ),
    "alien_invasion": LevelTheme(
        name="Invasão Alienígena",
        description="Predominância de aliens",
        enemy_weight={"meteor": 0.5, "alien": 3.0, "eye": 1.0},
        spawn_rate_multiplier=1.0,
        enemies_multiplier=1.0,
        special_feature=None,
    ),
    "eye_swarm": LevelTheme(
        name="Enxame de Olhos",
        description="Muitos Eye Enemies",
        enemy_weight={"meteor": 0.3, "alien": 0.5, "eye": 3.0},
        spawn_rate_multiplier=0.8,
        enemies_multiplier=0.9,
        special_feature=None,
    ),
    "minefield": LevelTheme(
        name="Campo Minado",
        description="Muitas minas explosivas",
        enemy_weight={"meteor": 1.0, "alien": 1.0, "eye": 0.5},
        spawn_rate_multiplier=1.0,
        enemies_multiplier=1.0,
        special_feature="mines_heavy",
    ),
    "formation_hell": LevelTheme(
        name="Inferno de Formações",
        description="Formações complexas constantemente",
        enemy_weight={"meteor": 0.8, "alien": 2.0, "eye": 1.0},
        spawn_rate_multiplier=0.9,
        enemies_multiplier=0.85,
        special_feature="formations_heavy",
    ),
    "balanced": LevelTheme(
        name="Balanceado",
        description="Mix equilibrado de tudo",
        enemy_weight={"meteor": 1.0, "alien": 1.0, "eye": 1.0},
        spawn_rate_multiplier=1.0,
        enemies_multiplier=1.0,
        special_feature=None,
    ),
}


# ============================================================================
# DATACLASS - LEVEL CONFIG
# ============================================================================


@dataclass
class LevelConfig:
    """Configuração de um nível do jogo."""

    level_number: int
    enemy_spawn_config: dict[
        Type[Meteor | Alien | ExplosiveMine | EyeEnemy], float
    ]  # Tipo -> tempo de spawn
    enemies_to_clear: int  # quantos inimigos para passar de fase
    boss_type: Type[Boss | SpikeBoss] | None = None
    mines_enabled: bool = False
    formations_enabled: bool = False
    formation_types: list[str] | None = None

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
        self.seed = seed or random.randint(0, 999999)
        self.difficulty_curves = DifficultyCurves()

    def generate_level(self, level_number: int) -> LevelConfig:
        """Gera configuração procedural para um nível."""
        random.seed(self.seed + level_number)

        # 1. Calcular dificuldade base usando curva configurada
        difficulty = self._calculate_difficulty(level_number)

        # 2. Escolher tema do nível (se habilitado)
        theme = None
        if DifficultyConfig.LEVEL_VARIETY_ENABLED:
            theme = self._choose_theme(level_number)

        # 3. Gerar configuração
        config = self._generate_config(level_number, difficulty, theme)

        random.seed()
        return config

    def _calculate_difficulty(self, level_number: int) -> float:
        """Calcula multiplicador de dificuldade usando curva configurada."""
        curve = DifficultyConfig.SPAWN_RATE_CURVE
        scaling = DifficultyConfig.DIFFICULTY_SCALING
        base = 1.0

        if curve == "logarithmic":
            difficulty = base + math.log1p(level_number) * scaling
        elif curve == "exponential":
            difficulty = math.pow(base + scaling, level_number * 0.5)
        else:  # linear
            difficulty = base + (level_number * scaling)

        return min(difficulty, DifficultyConfig.MAX_DIFFICULTY_MULTIPLIER)

    def _choose_theme(self, level_number: int) -> LevelTheme | None:
        """Escolhe um tema baseado no nível."""
        # Níveis iniciais: sempre balanceado
        if level_number <= 2:
            return LEVEL_THEMES["balanced"]

        # A cada 3 níveis, chance de tema especial
        if level_number % 3 == 0 and level_number >= 6:
            special_themes = ["minefield", "formation_hell", "eye_swarm"]
            available = [
                t for t in special_themes if self._theme_available(t, level_number)
            ]
            if available:
                theme_name = random.choice(available)
                return LEVEL_THEMES[theme_name]

        # Outros níveis: temas variados
        standard_themes = ["asteroid_field", "alien_invasion", "balanced"]
        if level_number >= 5:
            standard_themes.append("eye_swarm")

        theme_name = random.choice(standard_themes)
        return LEVEL_THEMES[theme_name]

    def _theme_available(self, theme_name: str, level_number: int) -> bool:
        """Verifica se um tema está disponível neste nível."""
        if theme_name == "minefield":
            return level_number >= DifficultyConfig.MINES_UNLOCK_LEVEL
        if theme_name == "formation_hell":
            return level_number >= DifficultyConfig.FORMATIONS_UNLOCK_LEVEL
        if theme_name == "eye_swarm":
            return level_number >= 5
        return True

    def _generate_config(
        self, level_number: int, difficulty: float, theme: LevelTheme | None
    ) -> LevelConfig:
        """Gera configuração baseada em dificuldade e tema."""

        # Aplicar multiplicadores do tema (se houver)
        spawn_multiplier = theme.spawn_rate_multiplier if theme else 1.0
        enemies_multiplier = theme.enemies_multiplier if theme else 1.0

        # 1. Calcular spawn times com pesos do tema
        enemy_spawn_config: dict[
            Type[Meteor | Alien | ExplosiveMine | EyeEnemy], float
        ] = {}

        # Meteoros
        meteor_weight = theme.enemy_weight.get("meteor", 1.0) if theme else 1.0
        base_meteor_time = (
            DifficultyConfig.BASE_METEOR_SPAWN_TIME / difficulty
        ) / spawn_multiplier
        enemy_spawn_config[Meteor] = base_meteor_time * (2.0 / meteor_weight)

        # Aliens (nível 2+)
        if level_number >= 2:
            alien_weight = theme.enemy_weight.get("alien", 1.0) if theme else 1.0
            base_alien_time = (
                DifficultyConfig.BASE_ALIEN_SPAWN_TIME / difficulty
            ) / spawn_multiplier
            enemy_spawn_config[Alien] = base_alien_time * (2.0 / alien_weight)

        # Eyes (nível 5+)
        if level_number >= 5:
            eye_weight = theme.enemy_weight.get("eye", 1.0) if theme else 1.0
            base_eye_time = (
                DifficultyConfig.BASE_EYE_SPAWN_TIME / difficulty
            ) / spawn_multiplier
            enemy_spawn_config[EyeEnemy] = base_eye_time * (2.0 / eye_weight)

        # 2. Calcular quantidade de inimigos
        curve = DifficultyConfig.ENEMY_COUNT_CURVE
        if curve == "square_root":
            base_enemies = DifficultyConfig.BASE_ENEMIES + int(
                math.sqrt(level_number) * 15
            )
        elif curve == "logarithmic":
            base_enemies = DifficultyConfig.BASE_ENEMIES + int(
                math.log1p(level_number) * 20
            )
        else:  # linear
            base_enemies = DifficultyConfig.BASE_ENEMIES + (
                level_number * DifficultyConfig.ENEMIES_PER_LEVEL
            )

        base_enemies = int(base_enemies * enemies_multiplier)
        variation = random.randint(
            -DifficultyConfig.ENEMY_VARIATION, DifficultyConfig.ENEMY_VARIATION
        )
        enemies_to_clear = max(
            DifficultyConfig.MIN_ENEMIES_TO_CLEAR, base_enemies + variation
        )

        # 3. Features baseadas no tema
        mines_enabled = False
        if level_number >= DifficultyConfig.MINES_UNLOCK_LEVEL:
            if theme and theme.special_feature == "mines_heavy":
                mines_enabled = True
            else:
                mines_enabled = random.random() < DifficultyConfig.MINES_PROBABILITY

        formations_enabled = level_number >= DifficultyConfig.FORMATIONS_UNLOCK_LEVEL
        if theme and theme.special_feature == "formations_heavy":
            formations_enabled = True

        # 4. Tipos de formação
        formation_types = None
        if formations_enabled:
            all_formations = [
                "spiral_circle",
                "spiral_v",
                "spiral_square",
                "full_cycle",
                "spiral_line",
            ]

            if theme and theme.special_feature == "formations_heavy":
                formation_types = all_formations
            elif level_number >= 6:
                formation_types = all_formations
            else:
                num_formations = random.randint(3, 4)
                formation_types = random.sample(all_formations, num_formations)

        return LevelConfig(
            level_number=level_number,
            enemy_spawn_config=enemy_spawn_config,
            enemies_to_clear=enemies_to_clear,
            boss_type=None,
            mines_enabled=mines_enabled,
            formations_enabled=formations_enabled,
            formation_types=formation_types,
        )


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
    if level_number in FIXED_LEVELS:
        return FIXED_LEVELS[level_number]

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


# ============================================================================
# ESTATÍSTICAS E DEBUG
# ============================================================================


class LevelAnalyzer:
    """Analisa e exibe estatísticas de níveis gerados."""

    @staticmethod
    def analyze_level(config: LevelConfig) -> dict[str, object]:
        """Retorna estatísticas de um nível."""
        stats: dict[str, object] = {
            "level": config.level_number,
            "enemies_to_clear": config.enemies_to_clear,
            "enemy_types": len(config.enemy_types),
            "avg_spawn_rate": sum(config.enemy_spawn_config.values())
            / len(config.enemy_spawn_config),
            "has_boss": config.boss_type is not None,
            "mines": config.mines_enabled,
            "formations": config.formations_enabled,
        }
        return stats

    @staticmethod
    def print_level_progression(
        start: int, end: int, generator: ProceduralLevelGenerator
    ):
        """Imprime progressão de dificuldade para análise."""
        print(f"\n{'='*70}")
        print(f"ANÁLISE DE PROGRESSÃO: Níveis {start} a {end}")
        print(f"{'='*70}\n")

        for level_num in range(start, end + 1):
            config = generator.generate_level(level_num)
            stats = LevelAnalyzer.analyze_level(config)

            print(
                f"Nível {level_num:2d} | "
                f"Inimigos: {stats['enemies_to_clear']:3d} | "
                f"Tipos: {stats['enemy_types']} | "
                f"Spawn: {stats['avg_spawn_rate']:.2f}s | "
                f"{'[BOSS]' if stats['has_boss'] else '      '} "
                f"{'[M]' if stats['mines'] else '   '} "
                f"{'[F]' if stats['formations'] else '   '}"
            )
