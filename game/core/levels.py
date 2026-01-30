from dataclasses import dataclass
from typing import Type, Union, TYPE_CHECKING
from functools import lru_cache
import random
import math
import logging
from ..entities.meteor import Meteor
from ..entities.alien import Alien
from ..entities.boss import Boss
from ..entities.explosive_mine import ExplosiveMine
from ..entities.eye_enemy import EyeEnemy
from ..entities.spike_boss import SpikeBoss
from ..entities.square_minion_boss import SquareMinionBoss
from ..entities.slime_boss import SlimeBoss
from ..entities.giant_meteor_boss import GiantMeteorBoss
from .difficulty import DifficultyPreset, DifficultySettings
from .world_config import get_world_for_level, WorldTheme

if TYPE_CHECKING:
    from .world_config import WorldConfig


logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTES DE CONFIGURAÇÃO
# ============================================================================

# OPT #7: Pre-calculate math lookup table for enemy counts (levels 1-100)
_ENEMY_COUNT_TABLE = {i: int(math.log1p(i) * 20) for i in range(1, 101)}


class DifficultyConfig:
    """Constantes para balanceamento de dificuldade."""

    BASE_METEOR_SPAWN_TIME: float = 1.2
    BASE_ALIEN_SPAWN_TIME: float = 2.5
    BASE_EYE_SPAWN_TIME: float = 6.0
    MIN_SPAWN_TIME: float = 0.3  # Aumentado de 0.15 para 0.3 (mais jogável)

    MIN_ENEMIES_TO_CLEAR: int = 80
    BASE_ENEMIES: int = 25
    ENEMIES_PER_LEVEL: int = 5
    ENEMY_VARIATION: int = 20

    DIFFICULTY_SCALING: float = 0.15
    MAX_DIFFICULTY_MULTIPLIER: float = 2.5  # Reduzido de 3.0 para 2.5

    # Limites de inimigos simultâneos por tipo
    MAX_METEORS_ON_SCREEN: int = 35
    MAX_ALIENS_ON_SCREEN: int = 12
    MAX_EYES_ON_SCREEN: int = 5
    MAX_SQUARE_MINIONS_ON_SCREEN: int = 3
    MAX_TOTAL_ENEMIES_ON_SCREEN: int = 50  # Limite total absoluto

    # Controle adaptativo de spawn
    ADAPTIVE_SPAWN_ENABLED: bool = True  # Reduz spawn se muitos inimigos na tela
    SPAWN_REDUCTION_THRESHOLD: float = 0.8  # 80% do limite = começa a reduzir spawn

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
        enemy_weight={
            "meteor": 3.0,
            "alien": 0.5,
            "eye": 0.3,
            "square_minion_boss": 0.1,
        },
        spawn_rate_multiplier=1.3,
        enemies_multiplier=1.2,
        special_feature=None,
    ),
    "alien_invasion": LevelTheme(
        name="Invasão Alienígena",
        description="Predominância de aliens",
        enemy_weight={
            "meteor": 0.5,
            "alien": 3.0,
            "eye": 1.0,
            "square_minion_boss": 0.2,
        },
        spawn_rate_multiplier=1.0,
        enemies_multiplier=1.0,
        special_feature=None,
    ),
    "eye_swarm": LevelTheme(
        name="Enxame de Olhos",
        description="Muitos Eye Enemies",
        enemy_weight={
            "meteor": 0.3,
            "alien": 0.5,
            "eye": 3.0,
            "square_minion_boss": 0.1,
        },
        spawn_rate_multiplier=0.8,
        enemies_multiplier=0.9,
        special_feature=None,
    ),
    "minefield": LevelTheme(
        name="Campo Minado",
        description="Muitas minas explosivas",
        enemy_weight={
            "meteor": 1.0,
            "alien": 1.0,
            "eye": 0.5,
            "square_minion_boss": 0.1,
        },
        spawn_rate_multiplier=1.0,
        enemies_multiplier=1.0,
        special_feature="mines_heavy",
    ),
    "formation_hell": LevelTheme(
        name="Inferno de Formações",
        description="Formações complexas constantemente",
        enemy_weight={
            "meteor": 0.8,
            "alien": 2.0,
            "eye": 1.0,
            "square_minion_boss": 0.2,
        },
        spawn_rate_multiplier=0.9,
        enemies_multiplier=0.85,
        special_feature="formations_heavy",
    ),
    "meteor_storm": LevelTheme(
        name="Tempestade de Meteoros",
        description="Apenas meteoros em volume extremo",
        enemy_weight={
            "meteor": 10.0,
            "alien": 0.0,
            "eye": 0.0,
            "square_minion_boss": 0.0,
        },
        spawn_rate_multiplier=1.4,  # Reduzido de 2.0 para 1.4 (mais balanceado)
        enemies_multiplier=1.3,  # Reduzido de 1.8 para 1.3 (menos frustrante)
        special_feature="meteor_only",
    ),
    "balanced": LevelTheme(
        name="Balanceado",
        description="Mix equilibrado de tudo",
        enemy_weight={
            "meteor": 1.0,
            "alien": 1.0,
            "eye": 1.0,
            "square_minion_boss": 0.1,
        },
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
        Type[Meteor | Alien | ExplosiveMine | EyeEnemy | SquareMinionBoss], float
    ]  # Tipo -> tempo de spawn
    enemies_to_clear: int  # quantos inimigos para passar de fase
    boss_type: Type[Boss | SpikeBoss | SlimeBoss | GiantMeteorBoss] | None = None
    mines_enabled: bool = False
    formations_enabled: bool = False
    formation_types: list[str] | None = None
    theme_name: str | None = None  # Para UI mostrar "Invasão Alienígena!"
    score_multiplier: float = 1.0  # Multiplicador de pontuação para o nível

    @property
    def enemy_types(
        self,
    ) -> list[Type[Meteor | Alien | ExplosiveMine | EyeEnemy | SquareMinionBoss]]:
        """Retorna lista de tipos de inimigos configurados."""
        return list(self.enemy_spawn_config.keys())

    def get_spawn_time(
        self,
        enemy_type: Type[Meteor | Alien | ExplosiveMine | EyeEnemy | SquareMinionBoss],
    ) -> float:
        """Retorna o tempo de spawn para um tipo específico de inimigo."""
        return self.enemy_spawn_config.get(enemy_type, 1.0)

    def get_random_enemy_type(
        self,
    ) -> Type[Meteor | Alien | ExplosiveMine | EyeEnemy | SquareMinionBoss]:
        """Retorna um tipo de inimigo aleatório da lista."""
        if not self.enemy_types:
            raise ValueError(f"Level {self.level_number} has no enemies configured!")
        return random.choice(self.enemy_types)

    def get_random_formation_type(self) -> str | None:
        """Retorna um tipo de formação aleatório da lista."""
        if self.formation_types:
            return random.choice(self.formation_types)
        return None

    def validate_sanity(self) -> list[str]:
        """Valida se a configuração do nível é jogável e faz sentido.

        Returns:
            Lista de avisos/problemas encontrados (vazia se tudo OK)
        """
        warnings: list[str] = []

        # Verificar spawn times muito rápidos
        for enemy_type, spawn_time in self.enemy_spawn_config.items():
            if spawn_time < DifficultyConfig.MIN_SPAWN_TIME:
                warnings.append(
                    f"Spawn time de {enemy_type.__name__} muito rápido: {spawn_time:.2f}s "
                    f"(mínimo recomendado: {DifficultyConfig.MIN_SPAWN_TIME}s)"
                )

        # Verificar se tem inimigos demais para limpar
        if self.enemies_to_clear > 1000:
            warnings.append(
                f"Muitos inimigos para limpar: {self.enemies_to_clear} "
                f"(pode levar mais de 10 minutos)"
            )

        # Verificar se tema tem multiplicadores extremos
        if self.score_multiplier > 3.0:
            warnings.append(
                f"Score multiplier muito alto: {self.score_multiplier:.1f}x"
            )

        return warnings

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

    def __init__(
        self,
        seed: int | None = None,
        difficulty_preset: DifficultyPreset = DifficultyPreset.NORMAL,
    ):
        self.seed = seed or random.randint(0, 999999)
        self.difficulty_curves = DifficultyCurves()
        self.difficulty_preset = difficulty_preset
        self.difficulty_settings = DifficultySettings.get_settings(difficulty_preset)
        self._difficulty_cache: dict[Union[int, str], float] = (
            {}
        )  # Cache for difficulty and score multiplier calculations

    # OPT #6: Cache últimos 50 níveis gerados para não recalcular
    @lru_cache(maxsize=50)
    def generate_level(self, level_number: int) -> LevelConfig:
        """Gera configuração procedural para um nível."""
        # Criar uma instância de Random com uma seed determinística para este nível
        rng = random.Random(self.seed + level_number)

        # 1. Calcular dificuldade base usando curva configurada
        difficulty = self.calculate_difficulty(level_number)

        # 2. Escolher tema do nível (se habilitado)
        theme = None
        if DifficultyConfig.LEVEL_VARIETY_ENABLED:
            theme = self._choose_theme(level_number, rng)

        # 3. Gerar configuração
        config = self.generate_config(level_number, difficulty, theme, rng)

        return config

    def calculate_difficulty(self, level_number: int) -> float:
        """Calcula multiplicador de dificuldade usando curva configurada."""
        # OPT #8: Cache difficulty calculations per level_number
        if level_number in self._difficulty_cache:
            return self._difficulty_cache[level_number]

        curve = DifficultyConfig.SPAWN_RATE_CURVE
        scaling = self.difficulty_settings["difficulty_scaling"]
        base = 1.0

        difficulty: float
        if curve == "logarithmic":
            difficulty = base + math.log1p(level_number) * scaling
        elif curve == "exponential":
            difficulty = math.pow(base + scaling, level_number * 0.5)
        else:  # linear
            difficulty = base + (level_number * scaling)

        difficulty = min(difficulty, DifficultyConfig.MAX_DIFFICULTY_MULTIPLIER)

        # Store in cache
        self._difficulty_cache[level_number] = difficulty

        return difficulty

    def _choose_theme(self, level_number: int, rng: random.Random) -> LevelTheme | None:
        """Escolhe um tema baseado no nível."""
        # Níveis iniciais: sempre balanceado
        if level_number <= 2:
            return LEVEL_THEMES["balanced"]

        # A cada 5 níveis, chance de tempestade de meteoros (nível 8+)
        if level_number >= 8 and level_number % 5 == 0:
            if rng.random() < 0.4:  # 40% de chance
                return LEVEL_THEMES["meteor_storm"]

        # Chance de tema especial (aumenta com o nível)
        if level_number >= 6:
            special_chance = min(
                0.7, 0.3 + (level_number / 100)
            )  # Aumenta com progressão, max 70%
            if rng.random() < special_chance:
                special_themes = ["minefield", "formation_hell", "eye_swarm"]
                available = [
                    t for t in special_themes if self._theme_available(t, level_number)
                ]
                if available:
                    theme_name = rng.choice(available)
                    return LEVEL_THEMES[theme_name]

        # Outros níveis: temas variados
        standard_themes = ["asteroid_field", "alien_invasion", "balanced"]
        if level_number >= 5:
            standard_themes.append("eye_swarm")

        theme_name = rng.choice(standard_themes)
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

    def _clamp_spawn_time(self, time: float) -> float:
        """Garante que o tempo de spawn não seja menor que o mínimo."""
        return max(DifficultyConfig.MIN_SPAWN_TIME, time)

    def _calculate_score_multiplier(self, level_number: int) -> float:
        """Calcula o multiplicador de pontuação baseado no nível."""
        # OPT #9: Cache score multiplier calculations per level_number
        cache_key = f"score_{level_number}"
        if cache_key in self._difficulty_cache:
            return self._difficulty_cache[cache_key]

        # Multiplicador cresce logaritmicamente com o nível
        # Nível 1: 1.0x, Nível 10: ~2.0x, Nível 20: ~2.5x, etc.
        base_multiplier = 1.0
        level_bonus = math.log1p(level_number) * 0.3  # Crescimento logarítmico
        multiplier = base_multiplier + level_bonus

        # Store in cache
        self._difficulty_cache[cache_key] = multiplier

        return multiplier

    def generate_config(
        self,
        level_number: int,
        difficulty: float,
        theme: LevelTheme | None,
        rng: random.Random,
    ) -> LevelConfig:
        """Gera configuração baseada em dificuldade e tema."""

        # Aplicar multiplicadores do tema (se houver)
        theme_spawn_mult = theme.spawn_rate_multiplier if theme else 1.0
        theme_enemies_mult = theme.enemies_multiplier if theme else 1.0

        # Multiplicadores do preset
        preset_spawn_mult = self.difficulty_settings["spawn_rate_multiplier"]

        # Multiplicador final combinado
        spawn_multiplier = theme_spawn_mult * preset_spawn_mult
        enemies_multiplier = theme_enemies_mult

        # 1. Calcular spawn times com pesos do tema
        enemy_spawn_config: dict[
            Type[Meteor | Alien | ExplosiveMine | EyeEnemy | SquareMinionBoss], float
        ] = {}

        # Verificar se é fase especial "meteor_only"
        if theme and theme.special_feature == "meteor_only":
            # Apenas meteoros, spawn rate extremo
            meteor_spawn_time = (
                (DifficultyConfig.BASE_METEOR_SPAWN_TIME / difficulty)
                / spawn_multiplier
                / 2.0
            )  # Mesmo mais rápido
            enemy_spawn_config[Meteor] = self._clamp_spawn_time(meteor_spawn_time)
        else:
            # Meteoros
            meteor_weight = theme.enemy_weight.get("meteor", 1.0) if theme else 1.0
            base_meteor_time = (
                DifficultyConfig.BASE_METEOR_SPAWN_TIME / difficulty
            ) / spawn_multiplier
            enemy_spawn_config[Meteor] = self._clamp_spawn_time(
                base_meteor_time * (2.0 / meteor_weight)
            )

            # Aliens (nível 2+)
            if level_number >= 2:
                alien_weight = theme.enemy_weight.get("alien", 1.0) if theme else 1.0
                base_alien_time = (
                    DifficultyConfig.BASE_ALIEN_SPAWN_TIME / difficulty
                ) / spawn_multiplier
                enemy_spawn_config[Alien] = self._clamp_spawn_time(
                    base_alien_time * (2.0 / alien_weight)
                )

            # Eyes (nível 5+)
            if level_number >= 5:
                eye_weight = theme.enemy_weight.get("eye", 1.0) if theme else 1.0
                base_eye_time = (
                    DifficultyConfig.BASE_EYE_SPAWN_TIME / difficulty
                ) / spawn_multiplier
                enemy_spawn_config[EyeEnemy] = self._clamp_spawn_time(
                    base_eye_time * (2.0 / eye_weight)
                )

            # Square Minion Boss (nível 3+)
            if level_number >= 3 and len(enemy_spawn_config) < 3:
                square_weight = (
                    theme.enemy_weight.get("square_minion_boss", 0.1) if theme else 0.1
                )
                base_square_time = (
                    8.0 / difficulty  # Spawn time base
                ) / spawn_multiplier
                enemy_spawn_config[SquareMinionBoss] = self._clamp_spawn_time(
                    base_square_time * (2.0 / square_weight)
                )

        # 2. Calcular quantidade de inimigos
        curve = DifficultyConfig.ENEMY_COUNT_CURVE
        if curve == "square_root":
            base_enemies = DifficultyConfig.BASE_ENEMIES + int(
                math.sqrt(level_number) * 15
            )
        elif curve == "logarithmic":
            # OPT #7: Use pre-calculated lookup table for levels 1-100
            if level_number <= 100:
                base_enemies = (
                    DifficultyConfig.BASE_ENEMIES + _ENEMY_COUNT_TABLE[level_number]
                )
            else:
                base_enemies = DifficultyConfig.BASE_ENEMIES + int(
                    math.log1p(level_number) * 20
                )
        else:  # linear
            base_enemies = DifficultyConfig.BASE_ENEMIES + (
                level_number * DifficultyConfig.ENEMIES_PER_LEVEL
            )

        base_enemies = int(base_enemies * enemies_multiplier)

        # Aplicar variação baseada na dificuldade (mais inimigos em hardcore/nightmare)
        if self.difficulty_preset == DifficultyPreset.HARDCORE:
            base_enemies = int(base_enemies * 1.2)
        elif self.difficulty_preset == DifficultyPreset.NIGHTMARE:
            base_enemies = int(base_enemies * 1.5)
        elif self.difficulty_preset == DifficultyPreset.CASUAL:
            base_enemies = int(base_enemies * 0.8)

        variation = rng.randint(
            -DifficultyConfig.ENEMY_VARIATION, DifficultyConfig.ENEMY_VARIATION
        )
        enemies_to_clear = max(
            DifficultyConfig.MIN_ENEMIES_TO_CLEAR, base_enemies + variation
        )

        # 3. Features baseadas no tema
        mines_enabled = False
        formations_enabled = False

        if theme and theme.special_feature == "meteor_only":
            # Fase especial: apenas meteoros, sem features extras
            pass
        else:
            # Configuração normal de features
            if level_number >= DifficultyConfig.MINES_UNLOCK_LEVEL:
                if theme and theme.special_feature == "mines_heavy":
                    mines_enabled = True
                else:
                    mines_enabled = rng.random() < DifficultyConfig.MINES_PROBABILITY

            formations_enabled = (
                level_number >= DifficultyConfig.FORMATIONS_UNLOCK_LEVEL
            )
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
                num_formations = rng.randint(3, 4)
                formation_types = rng.sample(all_formations, num_formations)

        # Boss sempre presente na fase 'meteor_storm'
        boss_type = None
        if theme and theme.name == "meteor_storm":
            from ..entities.giant_meteor_boss import GiantMeteorBoss

            boss_type = GiantMeteorBoss

        return LevelConfig(
            level_number=level_number,
            enemy_spawn_config=enemy_spawn_config,
            enemies_to_clear=enemies_to_clear,
            boss_type=boss_type,
            mines_enabled=mines_enabled,
            formations_enabled=formations_enabled,
            formation_types=formation_types,
            theme_name=theme.name if theme else LEVEL_THEMES["balanced"].name,
            score_multiplier=self._calculate_score_multiplier(level_number),
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
            SquareMinionBoss: 15.0,  # Spawn lento para tutorial
            # Alien: 2.5,
            # EyeEnemy: 5.0,
        },
        enemies_to_clear=150,
        # formations_enabled=True,
        # formation_types=["spiral_circle", "spiral_v", "spiral_square", "full_cycle", "spiral_line"],
        # mines_enabled=True,
        # boss_type=SlimeBoss,
        # boss_type=Boss,
        # boss_type=GiantMeteorBoss,
        # boss_type=SpikeBoss,
        theme_name="Tutorial",
        score_multiplier=1.0,
    ),
    # Nível 3: Primeiro Boss - Mix de inimigos + Boss clássico
    3: LevelConfig(
        level_number=3,
        enemy_spawn_config={
            Meteor: 0.5,
            Alien: 2.5,
            SquareMinionBoss: 15.0,
        },
        enemies_to_clear=350,
        boss_type=Boss,
        mines_enabled=True,
        theme_name="Chefe Inicial",
        score_multiplier=1.2,
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
        # mines_enabled=True,
        formations_enabled=True,
        formation_types=["spiral_circle", "spiral_v", "spiral_line"],
        theme_name="Chefe Avançado",
        score_multiplier=1.6,
    ),
    # Novo nível: Meteoro Gigante
    14: LevelConfig(
        level_number=14,
        enemy_spawn_config={
            Meteor: 1.0,
            Alien: 3.0,
        },
        enemies_to_clear=220,
        boss_type=GiantMeteorBoss,
        mines_enabled=True,
        formations_enabled=False,
        theme_name="Meteoro Gigante",
        score_multiplier=1.5,
    ),
    # Slime Boss
    20: LevelConfig(
        level_number=20,
        enemy_spawn_config={
            Meteor: 0.7,
            # Alien: 15.0,
            EyeEnemy: 15.0,
        },
        enemies_to_clear=300,
        boss_type=SlimeBoss,
        # mines_enabled=True,
        formations_enabled=True,
        formation_types=[
            "spiral_circle",
            "spiral_v",
            "spiral_square",
            "full_cycle",
            "spiral_line",
        ],
        theme_name="Chefe Avançado",
        score_multiplier=1.8,
    ),
}


# ============================================================================
# FUNÇÕES AUXILIARES - INTEGRAÇÃO COM MUNDOS
# ============================================================================

def _apply_world_theme_to_config(config: LevelConfig, world: "WorldConfig") -> LevelConfig:
    """
    Aplica modificadores do tema do mundo à configuração de nível.
    
    Modifica os pesos de spawn de inimigos baseado no tema.
    """
    if not world.theme_modifiers:
        return config
    
    # Copiar config de spawn
    adjusted_spawn_config = dict(config.enemy_spawn_config)
    
    # Aplicar multiplicadores de peso
    meteor_mult = world.theme_modifiers.get("meteor_weight", 1.0)
    alien_mult = world.theme_modifiers.get("alien_weight", 1.0)
    eye_mult = world.theme_modifiers.get("eye_weight", 1.0)
    
    # Ajustar tempos de spawn (menor tempo = mais frequente)
    for enemy_type, spawn_time in list(adjusted_spawn_config.items()):
        if enemy_type.__name__ == "Meteor" and meteor_mult != 1.0:
            adjusted_spawn_config[enemy_type] = spawn_time / meteor_mult
        elif enemy_type.__name__ == "Alien" and alien_mult != 1.0:
            adjusted_spawn_config[enemy_type] = spawn_time / alien_mult
        elif enemy_type.__name__ == "EyeEnemy" and eye_mult != 1.0:
            adjusted_spawn_config[enemy_type] = spawn_time / eye_mult
    
    # Aplicar multiplicador geral de spawn rate
    spawn_rate_mult = world.theme_modifiers.get("spawn_rate_multiplier", 1.0)
    if spawn_rate_mult != 1.0:
        for enemy_type in adjusted_spawn_config:
            adjusted_spawn_config[enemy_type] /= spawn_rate_mult
    
    # Garantir que tempos de spawn respeitam mínimo
    for enemy_type in adjusted_spawn_config:
        adjusted_spawn_config[enemy_type] = max(
            DifficultyConfig.MIN_SPAWN_TIME,
            adjusted_spawn_config[enemy_type]
        )
    
    # Criar nova config com tema do mundo
    return LevelConfig(
        level_number=config.level_number,
        enemy_spawn_config=adjusted_spawn_config,
        enemies_to_clear=config.enemies_to_clear,
        boss_type=config.boss_type,
        mines_enabled=config.mines_enabled,
        formations_enabled=config.formations_enabled,
        formation_types=config.formation_types,
        theme_name=world.name,  # Usar nome do mundo
        score_multiplier=config.score_multiplier,
    )


def _create_world_boss_level(
    world: "WorldConfig",
    level_number: int,
    difficulty_preset: DifficultyPreset,
) -> LevelConfig:
    """Cria configuração para o boss de um mundo."""
    # Configuração base: mais inimigos conforme o mundo avança
    base_enemies_to_clear = 200 + (world.world_id - 1) * 50
    
    # Montagem de spawn config baseado no tema
    if world.theme == WorldTheme.MOUNTAINS:
        enemy_spawn_config = {
            Meteor: 0.8,
            Alien: 3.0,
        }
    elif world.theme == WorldTheme.STARFIELD:
        enemy_spawn_config = {
            Meteor: 1.2,
            Alien: 2.0,
            EyeEnemy: 6.0,
        }
    elif world.theme == WorldTheme.CITY:
        enemy_spawn_config = {
            Meteor: 1.5,
            Alien: 2.5,
            EyeEnemy: 5.0,
        }
    elif world.theme == WorldTheme.VOLCANIC:
        enemy_spawn_config = {
            Meteor: 0.7,
            EyeEnemy: 4.0,
        }
    else:  # PROCEDURAL
        enemy_spawn_config = {
            Meteor: 1.0,
            Alien: 2.0,
        }
    
    config = LevelConfig(
        level_number=level_number,
        enemy_spawn_config=enemy_spawn_config,
        enemies_to_clear=base_enemies_to_clear,
        boss_type=world.boss_type,
        mines_enabled=True,
        formations_enabled=True,
        formation_types=["spiral_circle", "spiral_v", "spiral_square", "full_cycle"],
        theme_name=f"Boss: {world.name}",
        score_multiplier=1.0 + (world.world_id * 0.2),
    )
    
    return _apply_difficulty_to_fixed_level(config, difficulty_preset)


# ============================================================================
# FUNÇÕES PÚBLICAS
# ============================================================================


# Geradores procedurais por dificuldade (singleton)
_procedural_generators: dict[DifficultyPreset, ProceduralLevelGenerator] = {}


def get_level_config(
    level_number: int,
    difficulty_preset: DifficultyPreset = DifficultyPreset.NORMAL,
    force_meteor_storm: bool = False,
) -> LevelConfig:
    """
    Retorna a configuração de um nível com dificuldade aplicada.

    Sistema Híbrido com Mundos:
    - Se o nível é um boss_level de um mundo: retorna config customizada para boss
    - Se o nível está em FIXED_LEVELS: retorna versão handcrafted ajustada
    - Caso contrário: gera proceduralmente com tema do mundo

    Args:
        level_number: Número do nível desejado (1+)
        difficulty_preset: Preset de dificuldade a aplicar
        force_meteor_storm: Forçar tema meteor storm (ignora mundo)

    Returns:
        LevelConfig do nível com dificuldade aplicada
    """
    # NOVO: Obter mundo do nível
    world = get_world_for_level(level_number)
    
    # NOVO: Se é boss_level e mundo tem boss definido
    if (level_number == world.boss_level and 
        world.boss_type is not None and 
        not force_meteor_storm):
        return _create_world_boss_level(world, level_number, difficulty_preset)
    
    # Para Hardcore e Nightmare, o nível 1 é sempre procedural (sem tutorial)
    if (
        level_number in FIXED_LEVELS
        and not (
            level_number == 1
            and difficulty_preset
            in [DifficultyPreset.HARDCORE, DifficultyPreset.NIGHTMARE]
        )
        and not force_meteor_storm
    ):
        config = FIXED_LEVELS[level_number]
        # NOVO: Aplicar tema do mundo ao nível fixo
        config = _apply_world_theme_to_config(config, world)
        # Aplicar modificadores do preset aos níveis fixos também
        return _apply_difficulty_to_fixed_level(config, difficulty_preset)

    # Obter ou criar gerador para este preset
    if difficulty_preset not in _procedural_generators:
        _procedural_generators[difficulty_preset] = ProceduralLevelGenerator(
            difficulty_preset=difficulty_preset
        )

    generator = _procedural_generators[difficulty_preset]
    
    # Forçar tema meteor_storm no procedural
    if force_meteor_storm:
        difficulty = generator.calculate_difficulty(level_number)
        theme = LEVEL_THEMES["meteor_storm"]
        return generator.generate_config(
            level_number,
            difficulty,
            theme,
            random.Random(generator.seed + level_number),
        )
    
    # NOVO: Gerar com tema do mundo aplicado
    config = generator.generate_level(level_number)
    config = _apply_world_theme_to_config(config, world)
    return config


def _apply_difficulty_to_fixed_level(
    config: LevelConfig, preset: DifficultyPreset
) -> LevelConfig:
    """Aplica multiplicadores de dificuldade a níveis fixos."""
    settings = DifficultySettings.get_settings(preset)

    # Criar nova config com valores ajustados
    adjusted_spawn_config = {
        enemy_type: max(
            DifficultyConfig.MIN_SPAWN_TIME,
            spawn_time / settings["spawn_rate_multiplier"],
        )
        for enemy_type, spawn_time in config.enemy_spawn_config.items()
    }

    adjusted_enemies = config.enemies_to_clear
    if preset == DifficultyPreset.HARDCORE:
        adjusted_enemies = int(adjusted_enemies * 1.2)
    elif preset == DifficultyPreset.NIGHTMARE:
        adjusted_enemies = int(adjusted_enemies * 1.5)
    elif preset == DifficultyPreset.CASUAL:
        adjusted_enemies = int(adjusted_enemies * 0.8)

    return LevelConfig(
        level_number=config.level_number,
        enemy_spawn_config=adjusted_spawn_config,
        enemies_to_clear=adjusted_enemies,
        boss_type=config.boss_type,
        mines_enabled=config.mines_enabled,
        formations_enabled=config.formations_enabled,
        formation_types=config.formation_types,
        theme_name=config.theme_name,
        score_multiplier=config.score_multiplier,
    )


class LevelManager:
    """Gerenciador de níveis do jogo."""

    def __init__(self, initial_levels: dict[int, LevelConfig] | None = None):
        """
        Args:
            initial_levels: Níveis iniciais (opcional, não usado atualmente)
        """
        self._levels = initial_levels or {}

    def get_level(
        self,
        level_number: int,
        difficulty_preset: DifficultyPreset = DifficultyPreset.NORMAL,
    ) -> LevelConfig:
        """Retorna a configuração de um nível com dificuldade aplicada."""
        return get_level_config(level_number, difficulty_preset)


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
            "avg_spawn_rate": (
                sum(config.enemy_spawn_config.values()) / len(config.enemy_spawn_config)
                if config.enemy_spawn_config
                else 0.0
            ),
            "has_boss": config.boss_type is not None,
            "mines": config.mines_enabled,
            "formations": config.formations_enabled,
        }
        return stats

    @staticmethod
    def estimate_duration(config: LevelConfig) -> float:
        """Estima duração em segundos assumindo 80% de eficiência."""
        if not config.enemy_spawn_config:
            return 0.0

        avg_spawn = sum(config.enemy_spawn_config.values()) / len(
            config.enemy_spawn_config
        )
        # Assume que jogador mata ~80% dos inimigos que spawnam
        return (config.enemies_to_clear / 0.8) * avg_spawn

    @staticmethod
    def estimate_spawn_rate(config: LevelConfig) -> float:
        """Estima taxa de spawn total (inimigos por segundo)."""
        if not config.enemy_spawn_config:
            return 0.0

        # Somar inverso dos spawn times = taxa total
        total_rate = sum(
            1.0 / spawn_time for spawn_time in config.enemy_spawn_config.values()
        )
        return total_rate

    @staticmethod
    def estimate_max_enemies_on_screen(config: LevelConfig) -> int:
        """Estima número máximo provável de inimigos na tela simultaneamente."""
        spawn_rate = LevelAnalyzer.estimate_spawn_rate(config)
        # Assumir que inimigos vivem ~5 segundos em média
        avg_lifetime = 5.0
        return int(spawn_rate * avg_lifetime)

    @staticmethod
    def print_level_progression(
        start: int, end: int, generator: ProceduralLevelGenerator
    ):
        """Imprime progressão de dificuldade para análise."""
        logger.info(f"\n{'='*80}")
        logger.info(f"ANÁLISE DE PROGRESSÃO: Níveis {start} a {end}")
        logger.info(f"{'='*80}\n")

        for level_num in range(start, end + 1):
            config = generator.generate_level(level_num)
            stats = LevelAnalyzer.analyze_level(config)
            duration = LevelAnalyzer.estimate_duration(config)

            # Emoji visual para features
            features = ""
            if stats["has_boss"]:
                features += "👹"
            if stats["mines"]:
                features += "💣"
            if stats["formations"]:
                features += "🌀"

            theme_name = config.theme_name or "N/A"
            spawn_rate = LevelAnalyzer.estimate_spawn_rate(config)
            max_enemies = LevelAnalyzer.estimate_max_enemies_on_screen(config)
            warnings = config.validate_sanity()

            # Indicador de problemas
            warning_icon = "⚠️" if warnings else "✓"

            logger.info(
                f"{warning_icon} Nv.{level_num:2d} │ "
                f"{theme_name:22s} │ "
                f"👾{stats['enemies_to_clear']:3d} │ "
                f"📊{spawn_rate:.1f}/s │ "
                f"🎯~{max_enemies:2d} tela │ "
                f"🕐{duration/60:.1f}min │ "
                f"{features:5s}"
            )

            # Mostrar avisos se houver
            if warnings:
                for warning in warnings:
                    logger.info(f"    └─ ⚠️  {warning}")
