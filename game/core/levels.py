import logging
import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Type

from ..entities.alien import Alien
from ..entities.boss import Boss
from ..entities.bot_elemental import ElementalRobot
from ..entities.cloud_archmage_boss import CloudArchmageBoss
from ..entities.explosive_mine import ExplosiveMine
from ..entities.eye_enemy import EyeEnemy
from ..entities.giant_meteor_boss import GiantMeteorBoss
from ..entities.meteor import Meteor
from ..entities.mountain_geode import MountainGeode
from ..entities.mountain_mage import MountainMage
from ..entities.mountain_propeller import MountainPropeller
from ..entities.mountain_serpent_boss import MountainSerpentBoss
from ..entities.rock_glider import RockGlider
from ..entities.slime_boss import SlimeBoss
from ..entities.spike_boss import SpikeBoss
from ..entities.square_minion_boss import SquareMinionBoss
from ..entities.stone_golem_boss import StoneGolemBoss
from ..entities.stone_sentry import StoneSentry
from .difficulty import DifficultyPreset, DifficultySettings
from .world_config import WorldTheme, get_world_for_level

if TYPE_CHECKING:
    from .world_config import WorldConfig


logger = logging.getLogger(__name__)

ACTIVE_ENEMY_TUNING_PROFILE = "moderate"


# Registro central de elegibilidade por tema.
# Se um inimigo está aqui, ele só aparece nos temas listados.
ENEMY_THEME_ALLOWLIST: dict[type, set[WorldTheme]] = {
    Meteor: {
        WorldTheme.STARFIELD,
        WorldTheme.CITY,
        WorldTheme.VOLCANIC,
        WorldTheme.PROCEDURAL,
    },
    Alien: {
        WorldTheme.STARFIELD,
        WorldTheme.CITY,
        WorldTheme.VOLCANIC,
        WorldTheme.PROCEDURAL,
    },
    EyeEnemy: {
        WorldTheme.STARFIELD,
        WorldTheme.CITY,
        WorldTheme.VOLCANIC,
        WorldTheme.PROCEDURAL,
    },
    SquareMinionBoss: {
        WorldTheme.STARFIELD,
        WorldTheme.CITY,
        WorldTheme.VOLCANIC,
        WorldTheme.PROCEDURAL,
    },
    RockGlider: {WorldTheme.MOUNTAINS},
    StoneSentry: {WorldTheme.MOUNTAINS},
    ElementalRobot: {WorldTheme.MOUNTAINS},
    MountainMage: {WorldTheme.MOUNTAINS},
    MountainPropeller: {WorldTheme.MOUNTAINS},
    MountainGeode: {WorldTheme.MOUNTAINS},
    ExplosiveMine: {
        WorldTheme.STARFIELD,
        WorldTheme.CITY,
        WorldTheme.VOLCANIC,
        WorldTheme.PROCEDURAL,
    },
}

# Multiplicadores de frequência por tema (camada 2), organizados por preset.
# Valor > 1.0 aumenta frequência (reduz spawn_time), valor < 1.0 reduz frequência.
ENEMY_THEME_WEIGHT_PROFILES: dict[str, dict[WorldTheme, dict[type, float]]] = {
    "conservative": {
        WorldTheme.MOUNTAINS: {
            RockGlider: 1.06,
            StoneSentry: 1.15,
            ElementalRobot: 1.10,
        },
        WorldTheme.STARFIELD: {
            Alien: 1.05,
            EyeEnemy: 1.05,
        },
        WorldTheme.CITY: {
            Alien: 1.10,
            EyeEnemy: 1.10,
        },
        WorldTheme.VOLCANIC: {
            Meteor: 1.12,
            EyeEnemy: 1.05,
        },
        WorldTheme.PROCEDURAL: {
            Meteor: 1.05,
            Alien: 1.05,
            EyeEnemy: 1.00,
        },
    },
    "moderate": {
        WorldTheme.MOUNTAINS: {
            RockGlider: 1.10,
            StoneSentry: 1.30,
            ElementalRobot: 1.18,
        },
        WorldTheme.STARFIELD: {
            Alien: 1.10,
            EyeEnemy: 1.08,
        },
        WorldTheme.CITY: {
            Alien: 1.15,
            EyeEnemy: 1.18,
        },
        WorldTheme.VOLCANIC: {
            Meteor: 1.18,
            EyeEnemy: 1.08,
        },
        WorldTheme.PROCEDURAL: {
            Meteor: 1.08,
            Alien: 1.08,
            EyeEnemy: 1.05,
        },
    },
    "aggressive": {
        WorldTheme.MOUNTAINS: {
            RockGlider: 1.14,
            StoneSentry: 1.45,
            ElementalRobot: 1.25,
        },
        WorldTheme.STARFIELD: {
            Alien: 1.15,
            EyeEnemy: 1.10,
        },
        WorldTheme.CITY: {
            Alien: 1.20,
            EyeEnemy: 1.25,
        },
        WorldTheme.VOLCANIC: {
            Meteor: 1.25,
            EyeEnemy: 1.10,
        },
        WorldTheme.PROCEDURAL: {
            Meteor: 1.12,
            Alien: 1.12,
            EyeEnemy: 1.08,
        },
    },
}

# Terceira camada por estágio dentro do mundo, organizada por preset.
ENEMY_STAGE_WEIGHT_PROFILES: dict[
    str, dict[WorldTheme, dict[str, dict[type, float]]]
] = {
    "conservative": {
        WorldTheme.MOUNTAINS: {
            "early": {
                RockGlider: 1.10,
                StoneSentry: 0.88,
                ElementalRobot: 0.85,
            },
            "mid": {
                RockGlider: 1.01,
                StoneSentry: 1.05,
                ElementalRobot: 1.00,
            },
            "late": {
                RockGlider: 0.94,
                StoneSentry: 1.15,
                ElementalRobot: 1.10,
            },
        },
        WorldTheme.STARFIELD: {
            "early": {Alien: 1.00, EyeEnemy: 0.95},
            "mid": {Alien: 1.02, EyeEnemy: 1.00},
            "late": {Alien: 1.05, EyeEnemy: 1.08},
        },
        WorldTheme.CITY: {
            "early": {Alien: 1.00, EyeEnemy: 0.95},
            "mid": {Alien: 1.05, EyeEnemy: 1.05},
            "late": {Alien: 1.10, EyeEnemy: 1.12},
        },
        WorldTheme.VOLCANIC: {
            "early": {Meteor: 1.05, EyeEnemy: 0.95},
            "mid": {Meteor: 1.10, EyeEnemy: 1.00},
            "late": {Meteor: 1.15, EyeEnemy: 1.08},
        },
        WorldTheme.PROCEDURAL: {
            "early": {Meteor: 1.05, Alien: 1.00, EyeEnemy: 0.90},
            "mid": {Meteor: 1.02, Alien: 1.02, EyeEnemy: 1.00},
            "late": {Meteor: 1.00, Alien: 1.05, EyeEnemy: 1.10},
        },
    },
    "moderate": {
        WorldTheme.MOUNTAINS: {
            "early": {
                RockGlider: 1.15,
                StoneSentry: 0.85,
                ElementalRobot: 0.80,
            },
            "mid": {
                RockGlider: 1.02,
                StoneSentry: 1.08,
                ElementalRobot: 1.03,
            },
            "late": {
                RockGlider: 0.95,
                StoneSentry: 1.22,
                ElementalRobot: 1.18,
            },
        },
        WorldTheme.STARFIELD: {
            "early": {Alien: 1.00, EyeEnemy: 0.90},
            "mid": {Alien: 1.04, EyeEnemy: 1.00},
            "late": {Alien: 1.08, EyeEnemy: 1.12},
        },
        WorldTheme.CITY: {
            "early": {Alien: 1.00, EyeEnemy: 0.95},
            "mid": {Alien: 1.08, EyeEnemy: 1.08},
            "late": {Alien: 1.14, EyeEnemy: 1.18},
        },
        WorldTheme.VOLCANIC: {
            "early": {Meteor: 1.08, EyeEnemy: 0.95},
            "mid": {Meteor: 1.13, EyeEnemy: 1.03},
            "late": {Meteor: 1.20, EyeEnemy: 1.12},
        },
        WorldTheme.PROCEDURAL: {
            "early": {Meteor: 1.08, Alien: 1.00, EyeEnemy: 0.88},
            "mid": {Meteor: 1.03, Alien: 1.04, EyeEnemy: 1.00},
            "late": {Meteor: 0.98, Alien: 1.08, EyeEnemy: 1.15},
        },
    },
    "aggressive": {
        WorldTheme.MOUNTAINS: {
            "early": {
                RockGlider: 1.20,
                StoneSentry: 0.80,
                ElementalRobot: 0.75,
            },
            "mid": {
                RockGlider: 1.04,
                StoneSentry: 1.10,
                ElementalRobot: 1.05,
            },
            "late": {
                RockGlider: 0.96,
                StoneSentry: 1.30,
                ElementalRobot: 1.25,
            },
        },
        WorldTheme.STARFIELD: {
            "early": {Alien: 1.00, EyeEnemy: 0.90},
            "mid": {Alien: 1.05, EyeEnemy: 1.00},
            "late": {Alien: 1.10, EyeEnemy: 1.15},
        },
        WorldTheme.CITY: {
            "early": {Alien: 1.00, EyeEnemy: 0.95},
            "mid": {Alien: 1.10, EyeEnemy: 1.10},
            "late": {Alien: 1.20, EyeEnemy: 1.25},
        },
        WorldTheme.VOLCANIC: {
            "early": {Meteor: 1.10, EyeEnemy: 0.95},
            "mid": {Meteor: 1.15, EyeEnemy: 1.05},
            "late": {Meteor: 1.25, EyeEnemy: 1.15},
        },
        WorldTheme.PROCEDURAL: {
            "early": {Meteor: 1.10, Alien: 1.00, EyeEnemy: 0.85},
            "mid": {Meteor: 1.05, Alien: 1.05, EyeEnemy: 1.00},
            "late": {Meteor: 0.96, Alien: 1.10, EyeEnemy: 1.20},
        },
    },
}


def _resolve_tuning_profile(profile_name: str) -> str:
    """Retorna perfil válido ou fallback seguro (moderate)."""
    if (
        profile_name in ENEMY_THEME_WEIGHT_PROFILES
        and profile_name in ENEMY_STAGE_WEIGHT_PROFILES
    ):
        return profile_name

    logger.warning(
        "Unknown enemy tuning profile '%s'. Falling back to 'moderate'.",
        profile_name,
    )
    return "moderate"


_ACTIVE_PROFILE = _resolve_tuning_profile(ACTIVE_ENEMY_TUNING_PROFILE)
ENEMY_THEME_WEIGHT_MULTIPLIERS = ENEMY_THEME_WEIGHT_PROFILES[_ACTIVE_PROFILE]
ENEMY_STAGE_WEIGHT_MULTIPLIERS = ENEMY_STAGE_WEIGHT_PROFILES[_ACTIVE_PROFILE]

THEME_FALLBACK_ENEMIES: dict[WorldTheme, list[type]] = {
    WorldTheme.MOUNTAINS: [RockGlider, MountainMage, StoneSentry, ElementalRobot],
    WorldTheme.STARFIELD: [Meteor, Alien, EyeEnemy],
    WorldTheme.CITY: [Alien, EyeEnemy, Meteor],
    WorldTheme.VOLCANIC: [Meteor, EyeEnemy, Alien],
    WorldTheme.PROCEDURAL: [Meteor, Alien, EyeEnemy],
}

DEFAULT_ENEMY_SPAWN_TIME: dict[type, float] = {
    Meteor: 1.2,
    RockGlider: 1.05,
    Alien: 2.5,
    EyeEnemy: 6.0,
    StoneSentry: 30.0,
    ElementalRobot: 2.6,
    MountainMage: 18.0,
    MountainPropeller: 15.0,
}

THEME_ENEMY_REPLACEMENTS: dict[tuple[WorldTheme, type], type] = {
    (WorldTheme.MOUNTAINS, Meteor): RockGlider,
    (WorldTheme.MOUNTAINS, ExplosiveMine): MountainGeode,
}


def _is_enemy_allowed_in_theme(enemy_type: type, world_theme: WorldTheme) -> bool:
    """Valida se um tipo de inimigo é permitido no tema informado."""
    allowed_themes = ENEMY_THEME_ALLOWLIST.get(enemy_type)
    if allowed_themes is None:
        return True
    return world_theme in allowed_themes


def _filter_enemy_spawn_for_theme(
    enemy_spawn_config: dict[
        Type[
            Meteor
            | Alien
            | ExplosiveMine
            | EyeEnemy
            | SquareMinionBoss
            | ElementalRobot
            | StoneSentry
        ],
        float,
    ],
    world_theme: WorldTheme,
) -> dict[
    Type[
        Meteor
        | Alien
        | ExplosiveMine
        | EyeEnemy
        | SquareMinionBoss
        | ElementalRobot
        | StoneSentry
    ],
    float,
]:
    """Filtra inimigos proibidos no tema e garante fallback mínimo."""
    filtered: dict[
        Type[
            Meteor
            | Alien
            | ExplosiveMine
            | EyeEnemy
            | SquareMinionBoss
            | ElementalRobot
            | StoneSentry
        ],
        float,
    ] = {}
    removed: list[str] = []

    for enemy_type, spawn_time in enemy_spawn_config.items():
        if _is_enemy_allowed_in_theme(enemy_type, world_theme):
            filtered[enemy_type] = spawn_time
        else:
            removed.append(enemy_type.__name__)
            replacement = THEME_ENEMY_REPLACEMENTS.get((world_theme, enemy_type))
            if replacement is not None and _is_enemy_allowed_in_theme(
                replacement, world_theme
            ):
                current = filtered.get(replacement)
                filtered[replacement] = (
                    spawn_time if current is None else min(current, spawn_time)
                )

    if removed:
        logger.info(
            "Theme filter removed enemies for %s: %s",
            world_theme.value,
            ", ".join(sorted(removed)),
        )

    if filtered:
        return filtered

    # Segurança: evita nível sem pool de inimigos.
    for fallback_type in THEME_FALLBACK_ENEMIES.get(world_theme, [Meteor]):
        if not _is_enemy_allowed_in_theme(fallback_type, world_theme):
            continue

        fallback_time = DEFAULT_ENEMY_SPAWN_TIME.get(fallback_type, 1.0)
        fallback_time = max(DifficultyConfig.MIN_SPAWN_TIME, fallback_time)
        filtered[fallback_type] = fallback_time
        logger.warning(
            "Theme %s had empty enemy pool after filtering. Fallback=%s",
            world_theme.value,
            fallback_type.__name__,
        )
        break

    return filtered


def _apply_theme_enemy_eligibility(
    config: "LevelConfig", world: "WorldConfig"
) -> "LevelConfig":
    """Aplica elegibilidade de inimigos por tema em qualquer LevelConfig."""
    adjusted_spawn_config = _filter_enemy_spawn_for_theme(
        config.enemy_spawn_config,
        world.theme,
    )

    if adjusted_spawn_config == config.enemy_spawn_config:
        return config

    return LevelConfig(
        level_number=config.level_number,
        enemy_spawn_config=adjusted_spawn_config,
        enemies_to_clear=config.enemies_to_clear,
        boss_type=config.boss_type,
        mines_enabled=config.mines_enabled,
        formations_enabled=config.formations_enabled,
        formation_types=config.formation_types,
        theme_name=config.theme_name,
        score_multiplier=config.score_multiplier,
    )


def _apply_theme_enemy_weights(
    config: "LevelConfig", world: "WorldConfig"
) -> "LevelConfig":
    """Aplica multiplicadores de frequência por tema no spawn_config."""
    theme_weights = ENEMY_THEME_WEIGHT_MULTIPLIERS.get(world.theme)
    if not theme_weights:
        return config

    adjusted_spawn_config: dict[
        Type[
            Meteor
            | RockGlider
            | Alien
            | ExplosiveMine
            | EyeEnemy
            | SquareMinionBoss
            | ElementalRobot
            | StoneSentry
        ],
        float,
    ] = {}
    changed = False

    for enemy_type, spawn_time in config.enemy_spawn_config.items():
        weight_multiplier = theme_weights.get(enemy_type, 1.0)
        if weight_multiplier <= 0:
            weight_multiplier = 1.0

        adjusted_spawn_time = max(
            DifficultyConfig.MIN_SPAWN_TIME,
            spawn_time / weight_multiplier,
        )
        adjusted_spawn_config[enemy_type] = adjusted_spawn_time
        if abs(adjusted_spawn_time - spawn_time) > 1e-9:
            changed = True

    if not changed:
        return config

    return LevelConfig(
        level_number=config.level_number,
        enemy_spawn_config=adjusted_spawn_config,
        enemies_to_clear=config.enemies_to_clear,
        boss_type=config.boss_type,
        mines_enabled=config.mines_enabled,
        formations_enabled=config.formations_enabled,
        formation_types=config.formation_types,
        theme_name=config.theme_name,
        score_multiplier=config.score_multiplier,
    )


def _get_stage_band(world: "WorldConfig", level_number: int) -> str:
    """Retorna faixa de estágio no mundo: early, mid ou late."""
    total_stages = max(1, world.total_stages)
    stage_number = max(1, min(total_stages, world.get_stage_number(level_number)))
    progress = stage_number / total_stages

    if progress <= 0.33:
        return "early"
    if progress <= 0.66:
        return "mid"
    return "late"


def _apply_stage_progression_enemy_weights(
    config: "LevelConfig", world: "WorldConfig"
) -> "LevelConfig":
    """Aplica pesos extras por faixa de estágio dentro do mundo."""
    theme_stage_weights = ENEMY_STAGE_WEIGHT_MULTIPLIERS.get(world.theme)
    if not theme_stage_weights:
        return config

    stage_band = _get_stage_band(world, config.level_number)
    stage_weights = theme_stage_weights.get(stage_band)
    if not stage_weights:
        return config

    adjusted_spawn_config: dict[
        Type[
            Meteor
            | Alien
            | ExplosiveMine
            | EyeEnemy
            | SquareMinionBoss
            | ElementalRobot
            | StoneSentry
        ],
        float,
    ] = {}
    changed = False

    for enemy_type, spawn_time in config.enemy_spawn_config.items():
        weight_multiplier = stage_weights.get(enemy_type, 1.0)
        if weight_multiplier <= 0:
            weight_multiplier = 1.0

        adjusted_spawn_time = max(
            DifficultyConfig.MIN_SPAWN_TIME,
            spawn_time / weight_multiplier,
        )
        adjusted_spawn_config[enemy_type] = adjusted_spawn_time
        if abs(adjusted_spawn_time - spawn_time) > 1e-9:
            changed = True

    if not changed:
        return config

    return LevelConfig(
        level_number=config.level_number,
        enemy_spawn_config=adjusted_spawn_config,
        enemies_to_clear=config.enemies_to_clear,
        boss_type=config.boss_type,
        mines_enabled=config.mines_enabled,
        formations_enabled=config.formations_enabled,
        formation_types=config.formation_types,
        theme_name=config.theme_name,
        score_multiplier=config.score_multiplier,
    )


def _apply_theme_enemy_rules(
    config: "LevelConfig", world: "WorldConfig"
) -> "LevelConfig":
    """Pipeline único: elegibilidade + pesos por tema + pesos por estágio."""
    config = _apply_theme_enemy_eligibility(config, world)
    config = _apply_theme_enemy_weights(config, world)
    config = _apply_stage_progression_enemy_weights(config, world)
    return config


# ============================================================================
# CONSTANTES DE CONFIGURAÇÃO
# ============================================================================

# OPT #7: Pre-calculate math lookup table for enemy counts (levels 1-100)
_ENEMY_COUNT_TABLE = {i: int(math.log1p(i) * 20) for i in range(1, 101)}

# Multiplicadores de volume (objetivo de fase) por preset.
# Mantidos em um único lugar para evitar drift entre fluxo procedural e níveis fixos.
DIFFICULTY_ENEMY_COUNT_MULTIPLIER: dict[DifficultyPreset, float] = {
    DifficultyPreset.CASUAL: 0.8,
    DifficultyPreset.NORMAL: 1.0,
    DifficultyPreset.HARDCORE: 1.1,
    DifficultyPreset.NIGHTMARE: 1.25,
}


class DifficultyConfig:
    """Constantes para balanceamento de dificuldade."""

    BASE_METEOR_SPAWN_TIME: float = 1.2
    BASE_ALIEN_SPAWN_TIME: float = 2.5
    BASE_EYE_SPAWN_TIME: float = 6.0
    MIN_SPAWN_TIME: float = 0.3  # Aumentado de 0.15 para 0.3 (mais jogável)
    WEIGHTED_SPAWN_ENABLED: bool = True  # Feature flag do novo spawn ponderado
    WEIGHTED_SPAWN_TICK: float = 0.15  # Janela entre tentativas de spawn ponderado
    WEIGHTED_RECENT_MEMORY: int = 3  # Quantos spawns recentes entram no anti-repetição
    WEIGHTED_REPEAT_PENALTY: float = 0.45  # Penalidade por repetição recente
    WEIGHTED_SPAWN_TELEMETRY: bool = False  # Logs periódicos para calibração
    WEIGHTED_TELEMETRY_INTERVAL: float = 15.0  # Segundos entre relatórios

    MIN_ENEMIES_TO_CLEAR: int = 80
    MAX_ENEMIES_TO_CLEAR: int = 600
    BASE_ENEMIES: int = 25
    ENEMIES_PER_LEVEL: int = 5
    ENEMY_VARIATION: int = 20

    # Cadência mínima entre spawns para evitar bursts em sequência.
    # ALINHADO com spawn_rate_multiplier: valores menores = spawn mais rápido.
    MIN_GLOBAL_SPAWN_GAP: float = 0.16
    DIFFICULTY_SPAWN_GAP_MULTIPLIER: dict[DifficultyPreset, float] = {
        DifficultyPreset.CASUAL: 1.10,  # 10% mais lento (menos spawn)
        DifficultyPreset.NORMAL: 1.00,
        DifficultyPreset.HARDCORE: 0.85,  # 15% mais rápido (mais spawn)
        DifficultyPreset.NIGHTMARE: 0.70,  # 30% mais rápido (muito mais spawn)
    }
    MIN_SPAWN_GAP_BY_TYPE: dict[str, float] = {
        "meteor": 0.18,
        "rock_glider": 0.18,
        "alien": 0.42,
        "eye": 0.70,
        "square_minion_boss": 1.00,
        "elemental_robot": 0.90,
        # StoneSentry deve ter cadência rara (30s entre spawns).
        "stone_sentry": 30.0,
    }

    DIFFICULTY_SCALING: float = 0.15
    MAX_DIFFICULTY_MULTIPLIER: float = 2.5  # Reduzido de 3.0 para 2.5

    # Limite total de inimigos simultâneos por dificuldade
    DIFFICULTY_TOTAL_ENEMY_CAPS: dict[DifficultyPreset, int] = {
        DifficultyPreset.CASUAL: 15,  # Fácil: poucos inimigos
        DifficultyPreset.NORMAL: 20,  # Médio: balanceado
        DifficultyPreset.HARDCORE: 22,  # Difícil: mais desafio
        DifficultyPreset.NIGHTMARE: 25,  # Super difícil: máximo caos controlado
    }

    # Controle adaptativo de spawn
    ADAPTIVE_SPAWN_ENABLED: bool = True  # Reduz spawn se próximo do limite
    SPAWN_REDUCTION_THRESHOLD: float = (
        0.80  # 80% do limite = começa a reduzir spawn (evitar picos)
    )

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
            "elemental_robot": 0.2,
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
            "elemental_robot": 0.1,
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
            "elemental_robot": 0.1,
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
            "elemental_robot": 0.1,
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
            "elemental_robot": 0.1,
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
            "elemental_robot": 0.0,
        },
        spawn_rate_multiplier=1.4,
        enemies_multiplier=1.3,
        special_feature="meteor_only",
    ),
    "rock_glider_storm": LevelTheme(
        name="Tempestade de Rock Gliders",
        description="Enxame de Rock Gliders pequenos em volume extremo",
        enemy_weight={
            "meteor": 0.0,
            "alien": 0.0,
            "eye": 0.0,
            "square_minion_boss": 0.0,
            "elemental_robot": 0.0,
        },
        spawn_rate_multiplier=1.35,
        enemies_multiplier=1.35,
        special_feature="rock_glider_only",
    ),
    "balanced": LevelTheme(
        name="Balanceado",
        description="Mix equilibrado de tudo",
        enemy_weight={
            "meteor": 1.0,
            "alien": 1.0,
            "eye": 1.0,
            "square_minion_boss": 0.1,
            "elemental_robot": 0.15,
        },
        spawn_rate_multiplier=1.0,
        enemies_multiplier=1.0,
        special_feature=None,
    ),
}

# ============================================================================
# PROGRESSÃO NATURAL DE PRESSÃO (VOLUME / INTERMEDIÁRIO / FORTE)
# ============================================================================

# Mapeia cada grupo de inimigos para uma faixa de pressão.
ENEMY_PRESSURE_TIER_BY_KEY: dict[str, str] = {
    "meteor": "volume",
    "rock_glider": "volume",
    "alien": "intermediate",
    "eye": "strong",
    "square_minion_boss": "strong",
    "elemental_robot": "strong",
    "stone_sentry": "strong",
}

# Curvas por tier ao longo do tema (início -> fim).
# volume: mais forte no início, suavemente reduzido no fim.
# intermediate/strong: entram e crescem gradualmente até o fim.
ENEMY_PRESSURE_TIER_CURVE: dict[str, tuple[float, float]] = {
    "volume": (1.25, 0.90),
    "intermediate": (0.55, 1.15),
    "strong": (0.20, 0.95),
}

# Gate de entrada por tipo para evitar picos bruscos no início do mundo.
ENEMY_PRESSURE_UNLOCK_START: dict[str, float] = {
    "meteor": 0.0,
    "rock_glider": 0.0,
    "alien": 0.08,
    "eye": 0.38,
    "square_minion_boss": 0.30,
    "elemental_robot": 0.55,
    "stone_sentry": 0.42,
}

ENEMY_PRESSURE_UNLOCK_WINDOW: dict[str, float] = {
    "meteor": 0.01,
    "rock_glider": 0.01,
    "alien": 0.30,
    "eye": 0.28,
    "square_minion_boss": 0.32,
    "elemental_robot": 0.30,
    "stone_sentry": 0.30,
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _get_world_stage_progress(level_number: int) -> float:
    """Retorna progresso normalizado [0..1] dentro do tema/mundo atual."""
    world = get_world_for_level(level_number)
    if world.total_stages <= 1:
        return 1.0
    stage = world.get_stage_number(level_number)
    return _clamp01((stage - 1) / (world.total_stages - 1))


def _get_progressive_enemy_weight(
    enemy_key: str,
    base_weight: float,
    stage_progress: float,
) -> float:
    """Aplica tier + gate por estágio para progressão natural de pressão."""
    if base_weight <= 0.0:
        return 0.0

    tier = ENEMY_PRESSURE_TIER_BY_KEY.get(enemy_key, "intermediate")
    start_mult, end_mult = ENEMY_PRESSURE_TIER_CURVE.get(tier, (1.0, 1.0))
    tier_mult = start_mult + (end_mult - start_mult) * _clamp01(stage_progress)

    unlock_start = ENEMY_PRESSURE_UNLOCK_START.get(enemy_key, 0.0)
    unlock_window = max(0.01, ENEMY_PRESSURE_UNLOCK_WINDOW.get(enemy_key, 0.25))
    unlock_progress = _clamp01((stage_progress - unlock_start) / unlock_window)

    # Mantém presença mínima de tipos desbloqueados para evitar "on/off" abrupto.
    if unlock_start <= 0.0:
        gate_mult = 1.0
    else:
        gate_mult = 0.15 + 0.85 * unlock_progress

    return max(0.05, base_weight * tier_mult * gate_mult)


def calculate_dynamic_enemy_cap(
    level_number: int, difficulty_preset: DifficultyPreset
) -> int:
    """
    Calcula o limite de inimigos simultâneos de forma progressiva por mundo.

    A progressão é composta por:
    1. Cap base da dificuldade (CASUAL 15, NORMAL 20, HARDCORE 22, NIGHTMARE 25)
    2. Bonus por mundo: cada novo mundo adiciona 1 inimigo (mundo 1=0, mundo 2=1, etc)
    3. Bonus por progresso dentro do mundo: cresce de 0 a +2 do início ao fim

    Exemplo NORMAL (resets dentro de cada mundo):
    Mundo 1 (níveis 1-10):
    - Nível 1: 20 + 0 + 0 = 20
    - Nível 5: 20 + 0 + 1 = 21
    - Nível 10: 20 + 0 + 2 = 22

    Mundo 2 (níveis 11-25) - reinicia progressão:
    - Nível 11: 20 + 1 + 0 = 21
    - Nível 18: 20 + 1 + 1 = 22
    - Nível 25: 20 + 1 + 2 = 23

    Mundo 3 (níveis 26-35) - reinicia progressão:
    - Nível 26: 20 + 2 + 0 = 22
    - Nível 30: 20 + 2 + 1 = 23
    - Nível 35: 20 + 2 + 2 = 24
    """
    # Cap base por dificuldade
    base_cap = DifficultyConfig.DIFFICULTY_TOTAL_ENEMY_CAPS.get(difficulty_preset, 20)

    # Obter mundo atual
    world = get_world_for_level(level_number)

    # Bonus por mundo com teto para evitar cap excessivo em mundos procedurais.
    world_bonus = min(world.world_id - 1, 6)

    # Bonus por progresso dentro do mundo: cresce de 0 a 2 do início ao fim
    # Este bonus REINICIA para cada novo mundo
    stage = world.get_stage_number(level_number)
    total_stages = world.total_stages
    if total_stages > 1:
        # Normalizar progresso 0..1 dentro do mundo e multiplicar por 2 para range 0..2
        stage_progress = (stage - 1) / (total_stages - 1)
        stage_bonus = min(
            2, int(stage_progress * 2 + 0.5)
        )  # +0.5 para arredondar corretamente
    else:
        stage_bonus = 0

    return base_cap + world_bonus + stage_bonus


# ============================================================================
# DATACLASS - LEVEL CONFIG
# ============================================================================


@dataclass
class LevelConfig:
    """Configuração de um nível do jogo."""

    level_number: int
    enemy_spawn_config: dict[type, float]  # Tipo -> tempo de spawn
    enemies_to_clear: int  # quantos inimigos para passar de fase
    boss_type: (
        Type[
            Boss
            | SpikeBoss
            | SlimeBoss
            | GiantMeteorBoss
            | StoneGolemBoss
            | MountainSerpentBoss
            | CloudArchmageBoss
        ]
        | None
    ) = None
    mines_enabled: bool = False
    formations_enabled: bool = False
    formation_types: list[str] | None = None
    theme_name: str | None = None  # Para UI mostrar "Invasão Alienígena!"
    score_multiplier: float = 1.0  # Multiplicador de pontuação para o nível

    @property
    def enemy_types(self) -> list[type]:
        """Retorna lista de tipos de inimigos configurados."""
        return list(self.enemy_spawn_config.keys())

    def get_spawn_time(self, enemy_type: type) -> float:
        """Retorna o tempo de spawn para um tipo específico de inimigo."""
        return self.enemy_spawn_config.get(enemy_type, 1.0)

    def get_random_enemy_type(self) -> type:
        """Retorna um tipo de inimigo aleatório ponderado pelo spawn_time configurado."""
        if not self.enemy_types:
            raise ValueError(f"Level {self.level_number} has no enemies configured!")
        weights_map = self.get_enemy_spawn_weights()
        types = list(weights_map.keys())
        weights = [weights_map[t] for t in types]
        result: list[type] = random.choices(types, weights=weights, k=1)
        return result[0]

    def get_enemy_spawn_weights(self) -> dict[type, float]:
        """Retorna pesos base de spawn derivados do intervalo configurado.

        Spawn menor significa maior frequência. Convertemos isso em peso por
        inversão de tempo para suportar seleção ponderada dinâmica.
        """
        weights: dict[type, float] = {}

        for enemy_type, spawn_time in self.enemy_spawn_config.items():
            safe_spawn_time = max(DifficultyConfig.MIN_SPAWN_TIME, spawn_time)
            weights[enemy_type] = 1.0 / safe_spawn_time

        return weights

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
                    f"Spawn time de {enemy_type.__name__} muito rápido: {spawn_time:.2f}s "  # noqa: E501
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
        self._difficulty_cache: dict[int, float] = {}
        self._score_cache: dict[int, float] = {}
        self._level_cache: dict[int, LevelConfig] = {}

    def generate_level(self, level_number: int) -> LevelConfig:
        """Gera configuração procedural para um nível com cache por instância."""
        cached = self._level_cache.get(level_number)
        if cached is not None:
            return cached

        config = self._generate_level_impl(level_number)
        self._level_cache[level_number] = config

        # LRU simples: remove o item mais antigo quando excede 50 entradas.
        if len(self._level_cache) > 50:
            self._level_cache.pop(next(iter(self._level_cache)))

        return config

    def _generate_level_impl(self, level_number: int) -> LevelConfig:
        """Gera configuração procedural para um nível."""
        # Criar uma instância de Random com uma seed determinística para este nível
        rng = random.Random(self.seed * 10_000 + level_number)

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
        world = get_world_for_level(level_number)

        # Níveis iniciais: sempre balanceado
        if level_number <= 2:
            return LEVEL_THEMES["balanced"]

        # A cada 5 níveis, chance de tempestade temática por mundo (nível 8+)
        if level_number >= 8 and level_number % 5 == 0:
            if rng.random() < 0.4:  # 40% de chance
                if world.theme == WorldTheme.STARFIELD:
                    return LEVEL_THEMES["meteor_storm"]
                if world.theme == WorldTheme.MOUNTAINS:
                    return LEVEL_THEMES["rock_glider_storm"]

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
        if level_number in self._score_cache:
            return self._score_cache[level_number]

        base_multiplier = 1.0
        level_bonus = math.log1p(level_number) * 0.3
        multiplier = base_multiplier + level_bonus

        self._score_cache[level_number] = multiplier
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

        # Multiplicador global do mundo (quando configurado em world_config).
        world = get_world_for_level(level_number)
        world_spawn_mult = float(
            world.theme_modifiers.get("spawn_rate_multiplier", 1.0)
        )

        # Multiplicador final combinado
        spawn_multiplier = theme_spawn_mult * preset_spawn_mult * world_spawn_mult
        enemies_multiplier = theme_enemies_mult
        stage_progress = _get_world_stage_progress(level_number)

        # 1. Calcular spawn times com pesos do tema
        enemy_spawn_config: dict[
            Type[
                Meteor
                | Alien
                | ExplosiveMine
                | EyeEnemy
                | SquareMinionBoss
                | ElementalRobot
                | StoneSentry
                | MountainMage
                | MountainPropeller
            ],
            float,
        ] = {}  # Tipo -> tempo de spawn

        # Verificar se é fase especial de inimigo único
        if theme and theme.special_feature in ("meteor_only", "rock_glider_only"):
            if theme.special_feature == "meteor_only":
                # Apenas meteoros, spawn rate extremo
                meteor_spawn_time = (
                    (DifficultyConfig.BASE_METEOR_SPAWN_TIME / difficulty)
                    / spawn_multiplier
                    / 2.0
                )
                enemy_spawn_config[Meteor] = self._clamp_spawn_time(meteor_spawn_time)
            else:
                # Apenas RockGlider com cadência agressiva.
                rock_glider_spawn_time = (
                    (DifficultyConfig.BASE_METEOR_SPAWN_TIME / difficulty)
                    / spawn_multiplier
                    / 1.9
                )
                enemy_spawn_config[RockGlider] = self._clamp_spawn_time(
                    rock_glider_spawn_time
                )
        else:
            # Meteoros
            meteor_weight = theme.enemy_weight.get("meteor", 1.0) if theme else 1.0
            meteor_weight = _get_progressive_enemy_weight(
                "meteor", meteor_weight, stage_progress
            )
            if meteor_weight > 0.0:
                base_meteor_time = (
                    DifficultyConfig.BASE_METEOR_SPAWN_TIME / difficulty
                ) / spawn_multiplier
                enemy_spawn_config[Meteor] = self._clamp_spawn_time(
                    base_meteor_time * (2.0 / meteor_weight)
                )

            # Aliens (nível 2+)
            if level_number >= 2:
                alien_weight = theme.enemy_weight.get("alien", 1.0) if theme else 1.0
                alien_weight = _get_progressive_enemy_weight(
                    "alien", alien_weight, stage_progress
                )
                if alien_weight > 0.0:
                    base_alien_time = (
                        DifficultyConfig.BASE_ALIEN_SPAWN_TIME / difficulty
                    ) / spawn_multiplier
                    enemy_spawn_config[Alien] = self._clamp_spawn_time(
                        base_alien_time * (2.0 / alien_weight)
                    )

            # Eyes (nível 5+)
            if level_number >= 5:
                eye_weight = theme.enemy_weight.get("eye", 1.0) if theme else 1.0
                eye_weight = _get_progressive_enemy_weight(
                    "eye", eye_weight, stage_progress
                )
                if eye_weight > 0.0:
                    base_eye_time = (
                        DifficultyConfig.BASE_EYE_SPAWN_TIME / difficulty
                    ) / spawn_multiplier
                    enemy_spawn_config[EyeEnemy] = self._clamp_spawn_time(
                        base_eye_time * (2.0 / eye_weight)
                    )

            # Square Minion Boss (nível 3+)
            if level_number >= 3:
                square_weight = (
                    theme.enemy_weight.get("square_minion_boss", 0.1) if theme else 0.1
                )
                square_weight = _get_progressive_enemy_weight(
                    "square_minion_boss", square_weight, stage_progress
                )
                if square_weight > 0.0:
                    base_square_time = (
                        8.0 / difficulty  # Spawn time base
                    ) / spawn_multiplier
                    enemy_spawn_config[SquareMinionBoss] = self._clamp_spawn_time(
                        base_square_time * (2.0 / square_weight)
                    )

            if world.theme == WorldTheme.MOUNTAINS and stage_progress >= 0.15:
                if stage_progress < 0.40:
                    mage_base_time = 22.0  # raro no early
                elif stage_progress < 0.70:
                    mage_base_time = 14.0  # moderado no mid
                else:
                    mage_base_time = 10.0  # frequente no late
                mage_spawn_time = (mage_base_time / difficulty) / spawn_multiplier
                enemy_spawn_config[MountainMage] = self._clamp_spawn_time(
                    mage_spawn_time
                )

            # Mountain Propeller
            if world.theme == WorldTheme.MOUNTAINS and stage_progress >= 0.35:
                propeller_base_time = 20.0
                propeller_spawn_time = (
                    propeller_base_time / difficulty
                ) / spawn_multiplier
                enemy_spawn_config[MountainPropeller] = self._clamp_spawn_time(
                    propeller_spawn_time
                )

            # StoneSentry — entra a partir de 40% do mundo (gate suavizado por 0.42)
            if world.theme == WorldTheme.MOUNTAINS and stage_progress >= 0.40:
                sentry_weight = _get_progressive_enemy_weight(
                    "stone_sentry", 1.0, stage_progress
                )
                sentry_spawn_time = (10.0 / difficulty / spawn_multiplier) * (
                    2.0 / sentry_weight
                )
                enemy_spawn_config[StoneSentry] = self._clamp_spawn_time(
                    sentry_spawn_time
                )

            # ElementalRobot — mini-boss, entra a partir de 53% (gate suavizado por 0.55)
            if world.theme == WorldTheme.MOUNTAINS and stage_progress >= 0.53:
                robot_weight = _get_progressive_enemy_weight(
                    "elemental_robot", 1.0, stage_progress
                )
                robot_spawn_time = (15.0 / difficulty / spawn_multiplier) * (
                    2.0 / robot_weight
                )
                enemy_spawn_config[ElementalRobot] = self._clamp_spawn_time(
                    robot_spawn_time
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

        # Aplicar volume alvo por preset (centralizado para facilitar manutenção).
        base_enemies = int(
            base_enemies
            * DIFFICULTY_ENEMY_COUNT_MULTIPLIER.get(self.difficulty_preset, 1.0)
        )

        variation = rng.randint(
            -DifficultyConfig.ENEMY_VARIATION, DifficultyConfig.ENEMY_VARIATION
        )
        enemies_to_clear = max(
            DifficultyConfig.MIN_ENEMIES_TO_CLEAR, base_enemies + variation
        )
        enemies_to_clear = min(DifficultyConfig.MAX_ENEMIES_TO_CLEAR, enemies_to_clear)

        # 3. Features baseadas no tema
        mines_enabled = False
        formations_enabled = False

        if theme and theme.special_feature in ("meteor_only", "rock_glider_only"):
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
            # Meteor: 0.5,
            # Alien: 1.5,
            # EyeEnemy: 2.0,
            # RockGlider: 0.6,
            # ElementalRobot: 1.0,
            # StoneSentry: 30.0,
            # MountainMage: 10.0,
            # MountainPropeller: 0.8,
            # MountainGeode: 1.0,
        },
        enemies_to_clear=1,
        # formations_enabled=True,
        # formation_types=["spiral_circle", "spiral_v", "spiral_square", "full_cycle", "spiral_line"],
        # mines_enabled=True,
        # boss_type=Boss,
        # boss_type=GiantMeteorBoss,
        # boss_type=SlimeBoss,
        # boss_type=SpikeBoss,
        # boss_type=SquareMinionBoss,
        boss_type=StoneGolemBoss,
        # boss_type=MountainSerpentBoss,
        # boss_type=GiantMeteorBoss,
        # boss_type=CloudArchmageBoss,
        theme_name="Tutorial",
        score_multiplier=1.0,
    ),
    # Nível 3: Primeiro Boss - Stone Golem (Montanhas)
    3: LevelConfig(
        level_number=3,
        enemy_spawn_config={
            RockGlider: 0.7,
            ElementalRobot: 12.0,
            StoneSentry: 18.0,
        },
        enemies_to_clear=250,
        boss_type=StoneGolemBoss,
        mines_enabled=True,
        theme_name="Chefe do Golem de Pedra",
        score_multiplier=1.2,
    ),
    # Nível 6: Segundo Boss - Mountain Serpent
    6: LevelConfig(
        level_number=6,
        enemy_spawn_config={
            RockGlider: 0.6,
            MountainPropeller: 4.0,
            MountainMage: 10.0,
        },
        enemies_to_clear=300,
        boss_type=MountainSerpentBoss,
        mines_enabled=True,
        theme_name="Boss da Serpente de Pedra",
        score_multiplier=1.3,
    ),
    # Nível 10: Terceiro Boss - Cloud Archmage (Final do Mundo 1)
    10: LevelConfig(
        level_number=10,
        enemy_spawn_config={
            RockGlider: 0.5,
            MountainMage: 12.0,
            MountainPropeller: 10.0,
        },
        enemies_to_clear=350,
        boss_type=CloudArchmageBoss,
        mines_enabled=True,
        theme_name="O Arquimago das Nuvens",
        score_multiplier=1.5,
    ),
    # Vazio Sideral - 4 Bosses
    # Nível 12: Boss clássico
    12: LevelConfig(
        level_number=12,
        enemy_spawn_config={
            Meteor: 0.8,
            Alien: 3.0,
        },
        enemies_to_clear=350,
        boss_type=Boss,
        mines_enabled=True,
        formations_enabled=False,
        # formation_types=["spiral_circle", "spiral_v"],
        theme_name="Chefe Clássico do Espaço",
        score_multiplier=1.3,
    ),
    # Nível 16: Spike Boss
    16: LevelConfig(
        level_number=16,
        enemy_spawn_config={
            Meteor: 0.7,
            Alien: 2.0,
            EyeEnemy: 4.0,
        },
        enemies_to_clear=380,
        boss_type=SpikeBoss,
        mines_enabled=True,
        formations_enabled=True,
        formation_types=["spiral_circle", "spiral_v", "spiral_square"],
        theme_name="Criatura Alienígena com Espinhos",
        score_multiplier=1.4,
    ),
    # Nível 20: Giant Meteor Boss
    20: LevelConfig(
        level_number=20,
        enemy_spawn_config={
            Meteor: 0.5,
        },
        enemies_to_clear=300,
        boss_type=GiantMeteorBoss,
        mines_enabled=True,
        formations_enabled=False,
        theme_name="Meteorito Gigante",
        score_multiplier=1.5,
    ),
    # Nível 25: Slime Boss
    25: LevelConfig(
        level_number=25,
        enemy_spawn_config={
            Meteor: 0.6,
            Alien: 2.5,
        },
        enemies_to_clear=420,
        boss_type=SlimeBoss,
        mines_enabled=True,
        formations_enabled=True,
        formation_types=[
            "spiral_circle",
            "spiral_v",
            "spiral_square",
            "full_cycle",
            "spiral_line",
        ],
        theme_name="Criatura Gelatinosa Alienígena",
        score_multiplier=1.6,
    ),
}


# ============================================================================
# FUNÇÕES AUXILIARES - INTEGRAÇÃO COM MUNDOS
# ============================================================================


def _apply_world_theme_to_config(
    config: LevelConfig, world: "WorldConfig"
) -> LevelConfig:
    """
    Aplica modificadores do tema do mundo à configuração de nível.

    Modifica os pesos de spawn de inimigos baseado no tema.
    """
    if not world.theme_modifiers:
        return config

    # Copiar config de spawn com type hint
    adjusted_spawn_config: dict[
        Type[
            Meteor
            | Alien
            | ExplosiveMine
            | EyeEnemy
            | SquareMinionBoss
            | ElementalRobot
            | StoneSentry
        ],
        float,
    ] = dict(config.enemy_spawn_config)

    # Aplicar multiplicadores de peso (RockGlider agora compartilha com Meteor)
    meteor_mult = world.theme_modifiers.get("meteor_weight", 1.0)
    alien_mult = world.theme_modifiers.get("alien_weight", 1.0)
    eye_mult = world.theme_modifiers.get("eye_weight", 1.0)

    # Ajustar tempos de spawn (menor tempo = mais frequente)
    for enemy_type, spawn_time in list(adjusted_spawn_config.items()):
        if (
            issubclass(enemy_type, Meteor) or issubclass(enemy_type, RockGlider)
        ) and meteor_mult != 1.0:
            adjusted_spawn_config[enemy_type] = spawn_time / meteor_mult
        elif issubclass(enemy_type, Alien) and alien_mult != 1.0:
            adjusted_spawn_config[enemy_type] = spawn_time / alien_mult
        elif issubclass(enemy_type, EyeEnemy) and eye_mult != 1.0:
            adjusted_spawn_config[enemy_type] = spawn_time / eye_mult

    # Aplicar multiplicador geral de spawn rate
    spawn_rate_mult = world.theme_modifiers.get("spawn_rate_multiplier", 1.0)
    if spawn_rate_mult != 1.0:
        for enemy_type in adjusted_spawn_config:
            adjusted_spawn_config[enemy_type] /= spawn_rate_mult

    # Garantir que tempos de spawn respeitam mínimo
    for enemy_type in adjusted_spawn_config:
        adjusted_spawn_config[enemy_type] = max(
            DifficultyConfig.MIN_SPAWN_TIME, adjusted_spawn_config[enemy_type]
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
    enemy_spawn_config: dict[
        Type[
            Meteor
            | Alien
            | ExplosiveMine
            | EyeEnemy
            | SquareMinionBoss
            | ElementalRobot
            | StoneSentry
        ],
        float,
    ]  # Tipo -> tempo de spawn

    if world.theme == WorldTheme.MOUNTAINS:
        enemy_spawn_config = {
            RockGlider: 0.9,
            ElementalRobot: 2.2,
            StoneSentry: 30.0,
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
        force_meteor_storm: Forçar tema meteor storm mantendo regras de elegibilidade por mundo

    Returns:
        LevelConfig do nível com dificuldade aplicada
    """
    # NOVO: Obter mundo do nível
    world = get_world_for_level(level_number)

    # NOVO: Se é boss_level e mundo tem boss definido
    if (
        level_number == world.boss_level
        and world.boss_type is not None
        and not force_meteor_storm
    ):
        config = _create_world_boss_level(world, level_number, difficulty_preset)
        return _apply_theme_enemy_rules(config, world)

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
        config = _apply_theme_enemy_rules(config, world)
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
        config = generator.generate_config(
            level_number,
            difficulty,
            theme,
            random.Random(generator.seed * 10_000 + level_number),
        )
        config = _apply_world_theme_to_config(config, world)
        config = _apply_theme_enemy_rules(config, world)
        return config

    # NOVO: Gerar com tema do mundo aplicado
    config = generator.generate_level(level_number)
    config = _apply_world_theme_to_config(config, world)
    config = _apply_theme_enemy_rules(config, world)
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
    adjusted_enemies = int(
        adjusted_enemies * DIFFICULTY_ENEMY_COUNT_MULTIPLIER.get(preset, 1.0)
    )

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
        logger.info("\n%s", "=" * 80)
        logger.info("ANÁLISE DE PROGRESSÃO: Níveis %s a %s", start, end)
        logger.info("%s\n", "=" * 80)

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
                "%s Nv.%2d │ %-22s │ %3d │ %.1f/s │ ~%2d tela │ %.1fmin │ %-5s",
                warning_icon,
                level_num,
                theme_name,
                stats["enemies_to_clear"],
                spawn_rate,
                max_enemies,
                duration / 60,
                features,
            )

            # Mostrar avisos se houver
            if warnings:
                for warning in warnings:
                    logger.info("    └─ ⚠️  %s", warning)
