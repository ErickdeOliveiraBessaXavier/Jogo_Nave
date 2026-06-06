"""Pipeline de transformações de `LevelConfig` + `get_level_config`.

Carrega o ponto de entrada (`get_level_config`) que decide entre:
  - boss-level customizado por mundo
  - nível fixo do `FIXED_LEVELS` com modificadores
  - geração procedural via `ProceduralLevelGenerator`

E aplica em sequência (via `_THEME_RULES_PIPELINE`) regras de elegibilidade,
multiplicadores de tema, progressão por estágio, e cap de variedade.
"""

from __future__ import annotations

import copy
import logging
import random
import zlib
from typing import TYPE_CHECKING, Callable

from ...entities.alien import Alien
from ...entities.bot_elemental import ElementalRobot
from ...entities.explosive_mine import ExplosiveMine
from ...entities.eye_enemy import EyeEnemy
from ...entities.Inimigos_Tema_Cidade.city_drone import CityDrone
from ...entities.Inimigos_Tema_Cidade.cyber_captor import CyberCaptor
from ...entities.Inimigos_Tema_Cidade.cyber_tank import CyberTank
from ...entities.Inimigos_Tema_Cidade.jammer_node import JammerNode
from ...entities.Inimigos_Tema_Cidade.mirror_pylon import MirrorPylon
from ...entities.Inimigos_Tema_Cidade.mortar_drone import MortarDrone
from ...entities.Inimigos_Tema_Cidade.neon_sniper import NeonSniper
from ...entities.Inimigos_Tema_Cidade.cargo_carrier import CargoCarrier
from ...entities.Inimigos_Tema_Cidade.sapper_drone import SapperDrone
from ...entities.Inimigos_Tema_Cidade.splitter_tank import SplitterTank
from ...entities.Inimigos_Tema_Cidade.police_interceptor import PoliceInterceptor
from ...entities.Inimigos_Tema_Cidade.tesla_twin import TeslaTwin
from ...entities.meteor import Meteor
from ...entities.mountain_geode import MountainGeode
from ...entities.mountain_mage import MountainMage
from ...entities.mountain_propeller import MountainPropeller
from ...entities.rock_glider import RockGlider
from ...entities.satellite import Satellite
from ...entities.square_minion_boss import SquareMinionBoss
from ...entities.stone_sentry import StoneSentry
from ..difficulty import DifficultyPreset, DifficultySettings
from ..world_config import WorldTheme, get_world_for_level
from .fixed_levels import (
    EnemySpawnConfig,
    FIXED_LEVELS,
    LEVEL_THEMES,
    TEST_ARENA_ENABLED,
    THEME_TEST_LEVELS,
    LevelConfig,
)
from .procedural import (
    DIFFICULTY_ENEMY_COUNT_MULTIPLIER,
    DifficultyConfig,
    ProceduralLevelGenerator,
)

if TYPE_CHECKING:
    from ..world_config import WorldConfig


logger = logging.getLogger(__name__)


ACTIVE_ENEMY_TUNING_PROFILE = "moderate"


# Registro central de elegibilidade por tema.
# Se um inimigo está aqui, ele só aparece nos temas listados.
ENEMY_THEME_ALLOWLIST: dict[type, set[WorldTheme]] = {
    # CITY tem a própria linhagem completa (Inimigos_Tema_Cidade) — não usa mais
    # os inimigos emprestados de outros temas (Meteor/Alien/EyeEnemy/SquareMinion).
    Meteor: {
        WorldTheme.STARFIELD,
        WorldTheme.VOLCANIC,
        WorldTheme.PROCEDURAL,
    },
    Alien: {
        WorldTheme.STARFIELD,
        WorldTheme.VOLCANIC,
        WorldTheme.PROCEDURAL,
    },
    EyeEnemy: {
        WorldTheme.STARFIELD,
        WorldTheme.VOLCANIC,
        WorldTheme.PROCEDURAL,
    },
    SquareMinionBoss: {
        WorldTheme.STARFIELD,
        WorldTheme.VOLCANIC,
        WorldTheme.PROCEDURAL,
    },
    Satellite: {WorldTheme.STARFIELD},  # lixo orbital — exclusivo do Espaço
    CityDrone: {WorldTheme.CITY},
    NeonSniper: {WorldTheme.CITY},
    PoliceInterceptor: {WorldTheme.CITY},
    CyberTank: {WorldTheme.CITY},
    CyberCaptor: {WorldTheme.CITY},
    TeslaTwin: {WorldTheme.CITY},
    JammerNode: {WorldTheme.CITY},
    MortarDrone: {WorldTheme.CITY},
    CargoCarrier: {WorldTheme.CITY},
    SplitterTank: {WorldTheme.CITY},
    SapperDrone: {WorldTheme.CITY},
    MirrorPylon: {WorldTheme.CITY},
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
ENEMY_THEME_WEIGHT_PROFILES: dict[str, dict[WorldTheme, dict[type, float]]] = {
    "conservative": {
        WorldTheme.MOUNTAINS: {
            RockGlider: 1.06,
            StoneSentry: 1.15,
            ElementalRobot: 1.10,
        },
        WorldTheme.STARFIELD: {Alien: 1.05, EyeEnemy: 1.05},
        WorldTheme.CITY: {
            CityDrone: 1.20,
            NeonSniper: 0.80,
            PoliceInterceptor: 0.85,
            CyberTank: 0.50,
            CyberCaptor: 0.70,
            TeslaTwin: 0.65,
            JammerNode: 0.65,
            MortarDrone: 0.70,
            CargoCarrier: 0.45,
            SplitterTank: 0.45,
            SapperDrone: 0.55,
            MirrorPylon: 0.50,
        },
        WorldTheme.VOLCANIC: {Meteor: 1.12, EyeEnemy: 1.05},
        WorldTheme.PROCEDURAL: {Meteor: 1.05, Alien: 1.05, EyeEnemy: 1.00},
    },
    "moderate": {
        WorldTheme.MOUNTAINS: {
            RockGlider: 1.10,
            StoneSentry: 1.30,
            ElementalRobot: 1.18,
        },
        WorldTheme.STARFIELD: {Alien: 1.10, EyeEnemy: 1.08},
        WorldTheme.CITY: {
            CityDrone: 1.30,
            NeonSniper: 0.90,
            PoliceInterceptor: 0.95,
            CyberTank: 0.60,
            CyberCaptor: 0.80,
            TeslaTwin: 0.75,
            JammerNode: 0.75,
            MortarDrone: 0.80,
            CargoCarrier: 0.55,
            SplitterTank: 0.55,
            SapperDrone: 0.65,
            MirrorPylon: 0.60,
        },
        WorldTheme.VOLCANIC: {Meteor: 1.18, EyeEnemy: 1.08},
        WorldTheme.PROCEDURAL: {Meteor: 1.08, Alien: 1.08, EyeEnemy: 1.05},
    },
    "aggressive": {
        WorldTheme.MOUNTAINS: {
            RockGlider: 1.14,
            StoneSentry: 1.45,
            ElementalRobot: 1.25,
        },
        WorldTheme.STARFIELD: {Alien: 1.15, EyeEnemy: 1.10},
        WorldTheme.CITY: {
            CityDrone: 1.40,
            NeonSniper: 1.00,
            PoliceInterceptor: 1.10,
            CyberTank: 0.70,
            CyberCaptor: 0.90,
            TeslaTwin: 0.85,
            JammerNode: 0.85,
            MortarDrone: 0.90,
            CargoCarrier: 0.65,
            SplitterTank: 0.65,
            SapperDrone: 0.75,
            MirrorPylon: 0.70,
        },
        WorldTheme.VOLCANIC: {Meteor: 1.25, EyeEnemy: 1.10},
        WorldTheme.PROCEDURAL: {Meteor: 1.12, Alien: 1.12, EyeEnemy: 1.08},
    },
}

# Terceira camada por estágio dentro do mundo, organizada por preset.
ENEMY_STAGE_WEIGHT_PROFILES: dict[
    str, dict[WorldTheme, dict[str, dict[type, float]]]
] = {
    "conservative": {
        WorldTheme.MOUNTAINS: {
            "early": {RockGlider: 1.10, StoneSentry: 0.88, ElementalRobot: 0.85},
            "mid": {RockGlider: 1.01, StoneSentry: 1.05, ElementalRobot: 1.00},
            "late": {RockGlider: 0.94, StoneSentry: 1.15, ElementalRobot: 1.10},
        },
        WorldTheme.STARFIELD: {
            "early": {Alien: 1.00, EyeEnemy: 0.95},
            "mid": {Alien: 1.02, EyeEnemy: 1.00},
            "late": {Alien: 1.05, EyeEnemy: 1.08},
        },
        WorldTheme.CITY: {
            "early": {PoliceInterceptor: 0.80},
            "mid": {PoliceInterceptor: 1.05, CyberTank: 0.50, CyberCaptor: 0.70, TeslaTwin: 0.70, JammerNode: 0.70, MortarDrone: 0.75, CargoCarrier: 0.50, SplitterTank: 0.50, SapperDrone: 0.60, MirrorPylon: 0.52},
            "late": {PoliceInterceptor: 1.18, CyberTank: 1.05, CyberCaptor: 1.10, TeslaTwin: 1.10, JammerNode: 1.10, MortarDrone: 1.12, CargoCarrier: 1.05, SplitterTank: 1.05, SapperDrone: 1.05, MirrorPylon: 1.08},
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
            "early": {RockGlider: 1.15, StoneSentry: 0.85, ElementalRobot: 0.80},
            "mid": {RockGlider: 1.02, StoneSentry: 1.08, ElementalRobot: 1.03},
            "late": {RockGlider: 0.95, StoneSentry: 1.22, ElementalRobot: 1.18},
        },
        WorldTheme.STARFIELD: {
            "early": {Alien: 1.00, EyeEnemy: 0.90},
            "mid": {Alien: 1.04, EyeEnemy: 1.00},
            "late": {Alien: 1.08, EyeEnemy: 1.12},
        },
        WorldTheme.CITY: {
            "early": {PoliceInterceptor: 0.85},
            "mid": {PoliceInterceptor: 1.10, CyberTank: 0.55, CyberCaptor: 0.80, TeslaTwin: 0.80, JammerNode: 0.80, MortarDrone: 0.85, CargoCarrier: 0.55, SplitterTank: 0.55, SapperDrone: 0.65, MirrorPylon: 0.58},
            "late": {PoliceInterceptor: 1.25, CyberTank: 1.15, CyberCaptor: 1.20, TeslaTwin: 1.20, JammerNode: 1.20, MortarDrone: 1.22, CargoCarrier: 1.15, SplitterTank: 1.15, SapperDrone: 1.15, MirrorPylon: 1.18},
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
            "early": {RockGlider: 1.20, StoneSentry: 0.80, ElementalRobot: 0.75},
            "mid": {RockGlider: 1.04, StoneSentry: 1.10, ElementalRobot: 1.05},
            "late": {RockGlider: 0.96, StoneSentry: 1.30, ElementalRobot: 1.25},
        },
        WorldTheme.STARFIELD: {
            "early": {Alien: 1.00, EyeEnemy: 0.90},
            "mid": {Alien: 1.05, EyeEnemy: 1.00},
            "late": {Alien: 1.10, EyeEnemy: 1.15},
        },
        WorldTheme.CITY: {
            "early": {PoliceInterceptor: 0.90},
            "mid": {PoliceInterceptor: 1.15, CyberTank: 0.60, CyberCaptor: 0.90, TeslaTwin: 0.90, JammerNode: 0.90, MortarDrone: 0.95, CargoCarrier: 0.62, SplitterTank: 0.62, SapperDrone: 0.72, MirrorPylon: 0.65},
            "late": {PoliceInterceptor: 1.32, CyberTank: 1.25, CyberCaptor: 1.30, TeslaTwin: 1.30, JammerNode: 1.30, MortarDrone: 1.32, CargoCarrier: 1.25, SplitterTank: 1.25, SapperDrone: 1.25, MirrorPylon: 1.28},
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
    WorldTheme.STARFIELD: [Meteor, Alien, EyeEnemy, Satellite],
    WorldTheme.CITY: [
        CityDrone, NeonSniper, PoliceInterceptor, CyberCaptor, TeslaTwin, CyberTank,
        JammerNode, MortarDrone, CargoCarrier, SplitterTank, SapperDrone, MirrorPylon,
    ],
    WorldTheme.VOLCANIC: [Meteor, EyeEnemy, Alien],
    WorldTheme.PROCEDURAL: [Meteor, Alien, EyeEnemy],
}

DEFAULT_ENEMY_SPAWN_TIME: dict[type, float] = {
    Meteor: 1.2,
    RockGlider: 1.05,
    Alien: 2.5,
    EyeEnemy: 6.0,
    Satellite: 6.0,
    StoneSentry: 30.0,
    ElementalRobot: 2.6,
    MountainMage: 18.0,
    MountainPropeller: 15.0,
    CityDrone: 5.5,
    NeonSniper: 16.0,
    PoliceInterceptor: 14.0,
    CyberTank: 24.0,
    CyberCaptor: 17.0,
    TeslaTwin: 18.0,
    JammerNode: 17.0,
    MortarDrone: 16.0,
    CargoCarrier: 22.0,
    SplitterTank: 24.0,
    SapperDrone: 18.0,
    MirrorPylon: 20.0,
}

THEME_ENEMY_REPLACEMENTS: dict[tuple[WorldTheme, type], type] = {
    (WorldTheme.MOUNTAINS, Meteor): RockGlider,
    (WorldTheme.MOUNTAINS, ExplosiveMine): MountainGeode,
}


# Teto rígido de variedade de inimigos simultâneos por dificuldade. A rampa de
# introdução (X-1→1, X-2→2, X-3+→teto) é derivada do índice absoluto do estágio
# em `_apply_enemy_variety_cap` via `min(estágio, teto)`.
MAX_ENEMY_VARIETY_BY_DIFFICULTY: dict[DifficultyPreset, int] = {
    DifficultyPreset.CASUAL: 3,
    DifficultyPreset.NORMAL: 3,
    DifficultyPreset.HARDCORE: 4,
    DifficultyPreset.NIGHTMARE: 4,
}

# Inimigo "base" garantido em cada tema.
THEME_BASE_ENEMY: dict[WorldTheme, type] = {
    WorldTheme.MOUNTAINS: RockGlider,
    WorldTheme.STARFIELD: Meteor,
    WorldTheme.CITY: CityDrone,
    WorldTheme.VOLCANIC: Meteor,
    WorldTheme.PROCEDURAL: Meteor,
}

# Specials "assinatura" do tema: têm PRIORIDADE no pool sobre a loteria
# 1/spawn_time (que penaliza fortemente inimigos raros — sem isso um especial
# como o Neon Sniper quase nunca sobreviveria ao corte). Ainda respeitam o teto
# rígido de variedade (MAX_ENEMY_VARIETY_BY_DIFFICULTY).
# ORDEM = ORDEM DE DESBLOQUEIO (gate em `_configure_city_spawn`), do mais cedo ao
# mais tarde. O variety cap mostra as `n_slots` assinaturas da CAUDA (mais recém-
# liberadas) → cada uma aparece no estágio em que é introduzida (cobertura
# garantida) e o conjunto avança junto com os gates ("novos entram, antigos saem").
# DEVE casar com os gates: Sniper(X-2) → Police(X-3) → Mortar(X-4) → Captor/Sapper
# (X-5) → Tesla/Jammer(X-6) → CyberTank/Cargo(X-7) → Splitter/Mirror(X-8).
THEME_SIGNATURE_ENEMIES: dict[WorldTheme, tuple[type, ...]] = {
    WorldTheme.CITY: (
        NeonSniper, PoliceInterceptor, MortarDrone, CyberCaptor, SapperDrone,
        TeslaTwin, JammerNode, CyberTank, CargoCarrier, SplitterTank, MirrorPylon,
    ),
}


def _is_enemy_allowed_in_theme(enemy_type: type, world_theme: WorldTheme) -> bool:
    """Valida se um tipo de inimigo é permitido no tema informado."""
    allowed_themes = ENEMY_THEME_ALLOWLIST.get(enemy_type)
    if allowed_themes is None:
        return True
    return world_theme in allowed_themes


def _filter_enemy_spawn_for_theme(
    enemy_spawn_config: EnemySpawnConfig,
    world_theme: WorldTheme,
) -> EnemySpawnConfig:
    """Filtra inimigos proibidos no tema e garante fallback mínimo."""
    filtered: EnemySpawnConfig = {}
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
    config: LevelConfig,
    world: "WorldConfig",
    _difficulty_preset: DifficultyPreset,
) -> LevelConfig:
    """Aplica elegibilidade de inimigos por tema em qualquer LevelConfig."""
    adjusted_spawn_config = _filter_enemy_spawn_for_theme(
        config.enemy_spawn_config,
        world.theme,
    )

    if adjusted_spawn_config == config.enemy_spawn_config:
        return config

    config_copy = copy.copy(config)
    config_copy.enemy_spawn_config = adjusted_spawn_config
    return config_copy


def _apply_theme_enemy_weights(
    config: LevelConfig,
    world: "WorldConfig",
    _difficulty_preset: DifficultyPreset,
) -> LevelConfig:
    """Aplica multiplicadores de frequência por tema no spawn_config."""
    theme_weights = ENEMY_THEME_WEIGHT_MULTIPLIERS.get(world.theme)
    if not theme_weights:
        return config

    adjusted_spawn_config: EnemySpawnConfig = {}
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

    config_copy = copy.copy(config)
    config_copy.enemy_spawn_config = adjusted_spawn_config
    return config_copy


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
    config: LevelConfig,
    world: "WorldConfig",
    _difficulty_preset: DifficultyPreset,
) -> LevelConfig:
    """Aplica pesos extras por faixa de estágio dentro do mundo."""
    theme_stage_weights = ENEMY_STAGE_WEIGHT_MULTIPLIERS.get(world.theme)
    if not theme_stage_weights:
        return config

    stage_band = _get_stage_band(world, config.level_number)
    stage_weights = theme_stage_weights.get(stage_band)
    if not stage_weights:
        return config

    adjusted_spawn_config: EnemySpawnConfig = {}
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

    config_copy = copy.copy(config)
    config_copy.enemy_spawn_config = adjusted_spawn_config
    return config_copy


def _apply_enemy_variety_cap(
    config: LevelConfig,
    world: "WorldConfig",
    difficulty_preset: DifficultyPreset,
) -> LevelConfig:
    """Limita o spawn_config à "pirâmide de N" tipos por nível via uma rampa
    GLOBAL ancorada no índice absoluto do estágio dentro do mundo.

    Regra de design (aplicada a todos os temas, existentes e futuros):
      - `cap = min(estágio_absoluto, teto_por_dificuldade)`. Logo:
        X-1 → 1 tipo, X-2 → 2, X-3+ → o teto da dificuldade
        (`MAX_ENEMY_VARIETY_BY_DIFFICULTY`: 3 no Normal/Casual,
        4 no Hardcore/Pesadelo, onde o 4º tipo entra em X-4).
      - É só TETO (limite superior): se o pool do tema ainda tem poucos tipos
        liberados cedo, mostra menos — sem pico de complexidade na entrada de
        um mundo novo.
      - Quando há mais candidatos que vagas, escolhe-se: base (volume) sempre;
        depois as `n_slots` assinaturas MAIS RECÉM-LIBERADAS (cauda da ordem de
        unlock em THEME_SIGNATURE_ENEMIES) — cada assinatura aparece no estágio em
        que é introduzida (cobertura garantida, sem o viés que excluía algumas);
        por fim, as vagas restantes pelos demais tipos via loteria 1/spawn_time.
      - O subconjunto de assinaturas é determinístico por estágio (segue os gates);
        o filler não-assinatura usa seed determinístico por nível.
    """
    total_stages = max(1, world.total_stages)
    stage_number = max(
        1, min(total_stages, world.get_stage_number(config.level_number))
    )
    hard_max = MAX_ENEMY_VARIETY_BY_DIFFICULTY.get(difficulty_preset, 3)
    cap = min(stage_number, hard_max)
    spawn_config = config.enemy_spawn_config

    # Assinaturas têm prioridade na seleção (abaixo), mas NÃO ampliam o cap: a
    # rampa por estágio é a autoridade única sobre a contagem.
    signatures = [
        t for t in THEME_SIGNATURE_ENEMIES.get(world.theme, ()) if t in spawn_config
    ]

    if len(spawn_config) <= cap:
        return config

    # adler32 garante seed determinístico entre sessões (hash(str) é randomizado por PYTHONHASHSEED).
    theme_seed = zlib.adler32(world.theme.value.encode("utf-8"))
    rng = random.Random(config.level_number * 7919 + theme_seed)

    chosen: list[type] = []
    base = THEME_BASE_ENEMY.get(world.theme)
    if base is not None and base in spawn_config:
        chosen.append(base)

    # Assinaturas: prioridade sobre os demais. `signatures` está em ORDEM DE
    # UNLOCK; pega-se a CAUDA (as `n_slots` mais recém-liberadas). Como os gates
    # introduzem ~n_slots assinaturas por estágio, cada uma cai na cauda no estágio
    # em que é liberada → aparece garantidamente ali (cobertura completa), sem o
    # viés da loteria por recência que fazia Jammer/Mirror/Tesla sumirem. Custo
    # aceito: nos estágios finais sem novo unlock, repete os "pesados" mais novos.
    sigs = [t for t in signatures if t not in chosen]
    n_slots = cap - len(chosen)
    if sigs and n_slots > 0:
        chosen.extend(sigs[-n_slots:])

    # Vagas restantes: demais tipos (não-assinatura) por loteria 1/spawn_time.
    if len(chosen) < cap:
        candidates = [t for t in spawn_config if t not in chosen]
        weights = [1.0 / max(spawn_config[t], 0.01) for t in candidates]
        while candidates and len(chosen) < cap:
            idx = rng.choices(range(len(candidates)), weights=weights, k=1)[0]
            chosen.append(candidates.pop(idx))
            weights.pop(idx)

    adjusted_spawn_config = {t: spawn_config[t] for t in chosen}
    config_copy = copy.copy(config)
    config_copy.enemy_spawn_config = adjusted_spawn_config
    return config_copy


# Pipeline declarativo de transformações aplicadas a um `LevelConfig` em ordem.
_ThemeRuleStep = Callable[
    [LevelConfig, "WorldConfig", DifficultyPreset], LevelConfig
]

_THEME_RULES_PIPELINE: tuple[tuple[str, _ThemeRuleStep], ...] = (
    ("eligibility", _apply_theme_enemy_eligibility),
    ("theme_weights", _apply_theme_enemy_weights),
    ("stage_progression", _apply_stage_progression_enemy_weights),
    ("variety_cap", _apply_enemy_variety_cap),
)


def _apply_theme_enemy_rules(
    config: LevelConfig,
    world: "WorldConfig",
    difficulty_preset: DifficultyPreset,
) -> LevelConfig:
    """Executa o pipeline declarativo `_THEME_RULES_PIPELINE` em ordem."""
    for _name, step in _THEME_RULES_PIPELINE:
        config = step(config, world, difficulty_preset)
    return config


# ============================================================================
# AJUSTES POR MUNDO E POR BOSS
# ============================================================================


def _apply_world_theme_to_config(
    config: LevelConfig, world: "WorldConfig"
) -> LevelConfig:
    """Aplica modificadores do tema do mundo à configuração de nível."""
    if not world.theme_modifiers:
        return config

    adjusted_spawn_config: EnemySpawnConfig = dict(config.enemy_spawn_config)

    meteor_mult = world.theme_modifiers.get("meteor_weight", 1.0)
    alien_mult = world.theme_modifiers.get("alien_weight", 1.0)
    eye_mult = world.theme_modifiers.get("eye_weight", 1.0)

    for enemy_type, spawn_time in list(adjusted_spawn_config.items()):
        if (
            issubclass(enemy_type, Meteor) or issubclass(enemy_type, RockGlider)
        ) and meteor_mult != 1.0:
            adjusted_spawn_config[enemy_type] = spawn_time / meteor_mult
        elif issubclass(enemy_type, Alien) and alien_mult != 1.0:
            adjusted_spawn_config[enemy_type] = spawn_time / alien_mult
        elif issubclass(enemy_type, EyeEnemy) and eye_mult != 1.0:
            adjusted_spawn_config[enemy_type] = spawn_time / eye_mult

    spawn_rate_mult = world.theme_modifiers.get("spawn_rate_multiplier", 1.0)
    if spawn_rate_mult != 1.0:
        for enemy_type in adjusted_spawn_config:
            adjusted_spawn_config[enemy_type] /= spawn_rate_mult

    for enemy_type in adjusted_spawn_config:
        adjusted_spawn_config[enemy_type] = max(
            DifficultyConfig.MIN_SPAWN_TIME, adjusted_spawn_config[enemy_type]
        )

    return LevelConfig(
        level_number=config.level_number,
        enemy_spawn_config=adjusted_spawn_config,
        enemies_to_clear=config.enemies_to_clear,
        boss_type=config.boss_type,
        mines_enabled=config.mines_enabled,
        formations_enabled=config.formations_enabled,
        formation_types=config.formation_types,
        theme_name=world.name,
        score_multiplier=config.score_multiplier,
        storm_kind=config.storm_kind,
    )


def _create_world_boss_level(
    world: "WorldConfig",
    level_number: int,
    difficulty_preset: DifficultyPreset,
) -> LevelConfig:
    """Cria configuração para o boss de um mundo."""
    base_enemies_to_clear = 200 + (world.world_id - 1) * 50

    enemy_spawn_config: EnemySpawnConfig
    if world.theme == WorldTheme.MOUNTAINS:
        enemy_spawn_config = {
            RockGlider: 0.9,
            ElementalRobot: 2.2,
            StoneSentry: 30.0,
        }
    elif world.theme == WorldTheme.STARFIELD:
        enemy_spawn_config = {Meteor: 1.2, Alien: 2.0, EyeEnemy: 6.0}
    elif world.theme == WorldTheme.CITY:
        enemy_spawn_config = {
            CityDrone: 2.5,
            NeonSniper: 12.0,
            Alien: 2.5,
            EyeEnemy: 5.0,
            Meteor: 3.0,
        }
    elif world.theme == WorldTheme.VOLCANIC:
        enemy_spawn_config = {Meteor: 0.7, EyeEnemy: 4.0}
    else:  # PROCEDURAL
        enemy_spawn_config = {Meteor: 1.0, Alien: 2.0}

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
# ENTRADA PÚBLICA
# ============================================================================

# Geradores procedurais por dificuldade (singleton)
_procedural_generators: dict[DifficultyPreset, ProceduralLevelGenerator] = {}


def _build_test_arena_config(level_number: int) -> LevelConfig | None:
    """Arena de teste por tema (dev): config CRUA do tema do nível.

    Usada só quando `TEST_ARENA_ENABLED`. Pega a `LevelConfig` de
    `THEME_TEST_LEVELS` para o tema do mundo atual e a devolve SEM passar pelo
    pipeline de regras (sem variety cap, sem filtro/fallback de tema, sem grace
    nem coop scaling) — o objetivo é mostrar exatamente os inimigos listados,
    para validar o ecossistema isoladamente. Retorna ``None`` se o tema não tem
    arena definida (ex.: PROCEDURAL), caindo no fluxo normal.
    """
    world = get_world_for_level(level_number)
    template = THEME_TEST_LEVELS.get(world.theme)
    if template is None:
        return None
    config = copy.copy(template)
    config.level_number = level_number
    return config


def get_level_config(
    level_number: int,
    difficulty_preset: DifficultyPreset = DifficultyPreset.NORMAL,
    force_meteor_storm: bool = False,
    player_count: int = 1,
) -> LevelConfig:
    """Retorna a configuração de um nível com dificuldade aplicada.

    Sistema Híbrido com Mundos:
    - arena de teste (dev): se TEST_ARENA_ENABLED, retorna a arena do tema crua
    - boss_level de mundo: retorna config customizada para boss
    - nível em FIXED_LEVELS: retorna versão handcrafted ajustada
    - caso contrário: gera proceduralmente com tema do mundo
    """
    if TEST_ARENA_ENABLED:
        test_config = _build_test_arena_config(level_number)
        if test_config is not None:
            return test_config

    coop_enemies_multiplier = 1.0 + 0.35 * (player_count - 1)
    coop_spawn_multiplier = 1.0 + 0.20 * (player_count - 1)

    world = get_world_for_level(level_number)

    if (
        level_number == world.boss_level
        and world.boss_type is not None
        and not force_meteor_storm
    ):
        config = _create_world_boss_level(world, level_number, difficulty_preset)
        return _apply_theme_enemy_rules(config, world, difficulty_preset)

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
        config = _apply_world_theme_to_config(config, world)
        config = _apply_difficulty_to_fixed_level(config, difficulty_preset)

        fixed_stage = world.get_stage_number(level_number)
        fixed_grace = 1.0
        if fixed_stage == 1:
            fixed_grace = 0.70
        elif fixed_stage == 2:
            fixed_grace = 0.80
        elif fixed_stage == 3:
            fixed_grace = 0.90

        adjusted_spawn = {
            et: (spawn_time / fixed_grace) / coop_spawn_multiplier
            for et, spawn_time in config.enemy_spawn_config.items()
        }
        adjusted_to_clear = max(
            DifficultyConfig.MIN_ENEMIES_TO_CLEAR,
            int(config.enemies_to_clear * fixed_grace * coop_enemies_multiplier),
        )
        config = copy.copy(config)
        config.enemy_spawn_config = adjusted_spawn
        config.enemies_to_clear = adjusted_to_clear
        # Níveis handcrafted também seguem a regra global de variedade/elegibilidade
        # por tema (rampa X-1→1, X-2→2, X-3+→teto; filtro de tema).
        config = _apply_theme_enemy_rules(config, world, difficulty_preset)
        return config

    if difficulty_preset not in _procedural_generators:
        _procedural_generators[difficulty_preset] = ProceduralLevelGenerator(
            difficulty_preset=difficulty_preset
        )
    generator = _procedural_generators[difficulty_preset]

    stage_number = world.get_stage_number(level_number)
    world_entry_grace = 1.0
    if stage_number == 1:
        world_entry_grace = 0.70
    elif stage_number == 2:
        world_entry_grace = 0.80
    elif stage_number == 3:
        world_entry_grace = 0.90

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
        adjusted_spawn = {
            et: (spawn_time / world_entry_grace) / coop_spawn_multiplier
            for et, spawn_time in config.enemy_spawn_config.items()
        }
        adjusted_to_clear = max(
            DifficultyConfig.MIN_ENEMIES_TO_CLEAR,
            int(config.enemies_to_clear * world_entry_grace * coop_enemies_multiplier),
        )
        config = copy.copy(config)
        config.enemy_spawn_config = adjusted_spawn
        config.enemies_to_clear = adjusted_to_clear
        config = _apply_theme_enemy_rules(config, world, difficulty_preset)
        return config

    config = generator.generate_level(level_number)
    config = _apply_world_theme_to_config(config, world)

    adjusted_spawn = {
        et: (spawn_time / world_entry_grace) / coop_spawn_multiplier
        for et, spawn_time in config.enemy_spawn_config.items()
    }
    adjusted_to_clear = max(
        DifficultyConfig.MIN_ENEMIES_TO_CLEAR,
        int(config.enemies_to_clear * world_entry_grace * coop_enemies_multiplier),
    )
    config = copy.copy(config)
    config.enemy_spawn_config = adjusted_spawn
    config.enemies_to_clear = adjusted_to_clear

    config = _apply_theme_enemy_rules(config, world, difficulty_preset)
    return config


def _apply_difficulty_to_fixed_level(
    config: LevelConfig, preset: DifficultyPreset
) -> LevelConfig:
    """Aplica multiplicadores de dificuldade a níveis fixos."""
    settings = DifficultySettings.get_settings(preset)

    adjusted_spawn_config = {
        enemy_type: max(
            DifficultyConfig.MIN_SPAWN_TIME,
            spawn_time / settings["spawn_rate_multiplier"],
        )
        for enemy_type, spawn_time in config.enemy_spawn_config.items()
    }

    adjusted_enemies = int(
        config.enemies_to_clear * DIFFICULTY_ENEMY_COUNT_MULTIPLIER.get(preset, 1.0)
    )

    config_copy = copy.copy(config)
    config_copy.enemy_spawn_config = adjusted_spawn_config
    config_copy.enemies_to_clear = adjusted_enemies
    return config_copy
