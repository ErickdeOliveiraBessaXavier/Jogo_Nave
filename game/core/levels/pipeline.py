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
from ...entities.Inimigos_Tema_Cidade.city_mine import CityMine
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
from ...entities.cutting_storm import CuttingStorm
from ...entities.ice_golem import IceGolem
from ...entities.meteor import Meteor
from ...entities.mountain_geode import MountainGeode
from ...entities.mountain_mage import MountainMage
from ...entities.mountain_propeller import MountainPropeller
from ...entities.orbital_turret import OrbitalTurret
from ...entities.repair_drone import RepairDrone
from ...entities.rock_glider import RockGlider
from ...entities.satellite import Satellite
from ...entities.square_minion_boss import SquareMinionBoss
from ...entities.stealth_fighter import StealthFighter
from ...entities.stone_eagle import StoneEagle
from ...entities.stone_sentry import StoneSentry
from ..difficulty import DifficultyPreset, DifficultySettings
from ..world_config import (
    WorldTheme,
    get_boss_for_level,
    get_world_for_level,
)
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
    OrbitalTurret: {WorldTheme.STARFIELD},  # sentinela sniper — exclusivo do Espaço
    StealthFighter: {WorldTheme.STARFIELD},  # caça rush — exclusivo do Espaço
    RepairDrone: {WorldTheme.STARFIELD},  # suporte/cura — exclusivo do Espaço
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
    IceGolem: {WorldTheme.MOUNTAINS},  # tanque — exclusivo das Cordilheiras
    CuttingStorm: {WorldTheme.MOUNTAINS},  # negação de área — exclusivo das Cordilheiras
    StoneEagle: {WorldTheme.MOUNTAINS},  # rush em mergulho — exclusivo das Cordilheiras
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
            IceGolem: 0.85,
            CuttingStorm: 0.90,
            StoneEagle: 1.00,
        },
        WorldTheme.STARFIELD: {
            Alien: 1.05,
            EyeEnemy: 1.05,
            OrbitalTurret: 0.90,
            StealthFighter: 1.00,
            RepairDrone: 0.85,
        },
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
            IceGolem: 0.95,
            CuttingStorm: 1.00,
            StoneEagle: 1.10,
        },
        WorldTheme.STARFIELD: {
            Alien: 1.10,
            EyeEnemy: 1.08,
            OrbitalTurret: 1.00,
            StealthFighter: 1.10,
            RepairDrone: 0.95,
        },
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
            IceGolem: 1.05,
            CuttingStorm: 1.10,
            StoneEagle: 1.20,
        },
        WorldTheme.STARFIELD: {
            Alien: 1.15,
            EyeEnemy: 1.10,
            OrbitalTurret: 1.10,
            StealthFighter: 1.20,
            RepairDrone: 1.05,
        },
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
        # P3: nas bandas "late" o base sofre leve TAPER e os specials ganham
        # reforço — no fim do mundo os arquétipos pesados "leem" mais, sem mudar
        # a pressão total (o spawn_multiplier/diretor governa o volume; aqui só
        # se redistribui QUEM nasce).
        WorldTheme.MOUNTAINS: {
            "early": {RockGlider: 1.15, StoneSentry: 0.85, ElementalRobot: 0.80},
            "mid": {RockGlider: 1.02, StoneSentry: 1.08, ElementalRobot: 1.03, StoneEagle: 1.00},
            "late": {RockGlider: 0.88, StoneSentry: 1.35, ElementalRobot: 1.30, MountainMage: 1.20, StoneEagle: 1.10, CuttingStorm: 1.15, IceGolem: 1.20},
        },
        WorldTheme.STARFIELD: {
            "early": {Alien: 1.00, EyeEnemy: 0.90},
            "mid": {Alien: 1.04, EyeEnemy: 1.00, StealthFighter: 1.00},
            "late": {Meteor: 0.90, Alien: 1.15, EyeEnemy: 1.25, Satellite: 1.20, StealthFighter: 1.10, OrbitalTurret: 1.20, RepairDrone: 1.10},
        },
        WorldTheme.CITY: {
            "early": {PoliceInterceptor: 0.85},
            "mid": {PoliceInterceptor: 1.10, CyberTank: 0.55, CyberCaptor: 0.80, TeslaTwin: 0.80, JammerNode: 0.80, MortarDrone: 0.85, CargoCarrier: 0.55, SplitterTank: 0.55, SapperDrone: 0.65, MirrorPylon: 0.58},
            "late": {CityDrone: 0.80, PoliceInterceptor: 1.35, CyberTank: 1.30, CyberCaptor: 1.32, TeslaTwin: 1.32, JammerNode: 1.32, MortarDrone: 1.34, CargoCarrier: 1.30, SplitterTank: 1.30, SapperDrone: 1.28, MirrorPylon: 1.32},
        },
        WorldTheme.VOLCANIC: {
            # Antes o base (Meteor) era BOOSTADO no mid/late, agravando o flood;
            # invertido para taper + reforço de Alien/Eye.
            "early": {Meteor: 1.08, EyeEnemy: 0.95},
            "mid": {Meteor: 1.00, Alien: 1.08, EyeEnemy: 1.10},
            "late": {Meteor: 0.92, Alien: 1.18, EyeEnemy: 1.25},
        },
        WorldTheme.PROCEDURAL: {
            "early": {Meteor: 1.08, Alien: 1.00, EyeEnemy: 0.88},
            "mid": {Meteor: 1.03, Alien: 1.04, EyeEnemy: 1.00},
            "late": {Meteor: 0.90, Alien: 1.12, EyeEnemy: 1.20},
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
    WorldTheme.MOUNTAINS: [
        RockGlider, MountainMage, StoneSentry, ElementalRobot,
        StoneEagle, CuttingStorm, IceGolem,
    ],
    WorldTheme.STARFIELD: [
        Meteor, Alien, EyeEnemy, Satellite,
        StealthFighter, OrbitalTurret, RepairDrone,
    ],
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
    OrbitalTurret: 16.0,
    StealthFighter: 9.0,
    RepairDrone: 18.0,
    IceGolem: 22.0,
    CuttingStorm: 16.0,
    StoneEagle: 9.0,
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
    (WorldTheme.CITY, ExplosiveMine): CityMine,
}


# Teto de variedade: ver o bloco "ENCOUNTER COMPOSITION CONFIG" (logo antes de
# `_select_variety_subset`). O teto agora é GLOBAL e dirigido pelo TAMANHO DO POOL
# — sem tabela fixa por dificuldade nem exceção por tema. A rampa de introdução
# (X-1→1, X-2→2, …) continua via `min(estágio, teto)`.

# Inimigo "base" garantido em cada tema.
THEME_BASE_ENEMY: dict[WorldTheme, type] = {
    WorldTheme.MOUNTAINS: RockGlider,
    WorldTheme.STARFIELD: Meteor,
    WorldTheme.CITY: CityDrone,
    WorldTheme.VOLCANIC: Meteor,
    WorldTheme.PROCEDURAL: Meteor,
}

# Specials "assinatura" do tema = fonte ÚNICA e declarativa da ORDEM DE INTRODUÇÃO
# (do mais cedo ao mais tarde). O SPOTLIGHT (ver ENCOUNTER COMPOSITION CONFIG) dá
# destaque ao special mais recém-introduzido presente no pool e DECAI a cada rank
# mais antigo até o piso dos veteranos — assim o novo aparece com cobertura no seu
# estágio de introdução, mas os antigos NÃO são substituídos: voltam à rotação.
# ORDEM = ORDEM DE DESBLOQUEIO (gate em `_configure_*_spawn`).
# DEVE casar com os gates: Sniper(X-2) → Police(X-3) → Mortar(X-4) → Captor/Sapper
# (X-5) → Tesla/Jammer(X-6) → CyberTank/Cargo(X-7) → Splitter/Mirror(X-8).
THEME_SIGNATURE_ENEMIES: dict[WorldTheme, tuple[type, ...]] = {
    WorldTheme.CITY: (
        NeonSniper, PoliceInterceptor, MortarDrone, CyberCaptor, SapperDrone,
        TeslaTwin, JammerNode, CyberTank, CargoCarrier, SplitterTank, MirrorPylon,
    ),
    # ORDEM = ORDEM DE DESBLOQUEIO (gates em procedural). Sem assinatura, os
    # specials raros (spawn_time alto) somem na loteria de variedade — ver
    # memory/variety-cap-exclui-specials-raros. Os emergentes do trio de
    # introdução (Alien/EyeEnemy, RockGlider/MountainMage) seguem o gate de
    # stage_number e não precisam de assinatura.
    WorldTheme.STARFIELD: (StealthFighter, OrbitalTurret, RepairDrone),
    WorldTheme.MOUNTAINS: (StoneEagle, CuttingStorm, IceGolem),
}

# Papel de combate (arquétipo) de cada inimigo. Usado pelo variety cap para
# montar encontros COMPLEMENTARES (triangulação): ao preencher as vagas de
# specials, papéis já cobertos são penalizados, evitando empilhar 3 unidades da
# mesma função (ex.: 3 area-denial) e favorecendo trios que se complementam.
# Bases/volume recebem papel próprio ("volume") para não penalizar nenhum special.
# Colisões de papel hoje só existem na linhagem CITY (area_denial×3, support×2,
# summoner×2) — nos demais temas os specials já têm papéis distintos, então a
# diversificação é naturalmente um no-op lá.
ENEMY_ARCHETYPE: dict[type, str] = {
    Meteor: "volume", RockGlider: "volume", CityDrone: "volume",
    MountainPropeller: "swarm",
    Satellite: "hazard",
    EyeEnemy: "shooter",
    StoneSentry: "sniper", NeonSniper: "sniper", OrbitalTurret: "sniper",
    Alien: "rush", PoliceInterceptor: "rush",
    StealthFighter: "rush", StoneEagle: "rush",
    MountainMage: "support", JammerNode: "support", SapperDrone: "support",
    RepairDrone: "support",
    ElementalRobot: "elite", CyberTank: "tank", IceGolem: "tank",
    CyberCaptor: "area_denial", MortarDrone: "area_denial", TeslaTwin: "area_denial",
    CuttingStorm: "area_denial",
    CargoCarrier: "summoner", SplitterTank: "summoner", SquareMinionBoss: "summoner",
    MirrorPylon: "shield",
}

def _enemy_role(enemy_type: type) -> str:
    """Papel de combate do inimigo; fallback ao nome (papel único) se não mapeado."""
    return ENEMY_ARCHETYPE.get(enemy_type, enemy_type.__name__)


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


# ════════════════════════════════════════════════════════════════════════════
# ENCOUNTER COMPOSITION CONFIG — fonte ÚNICA e GLOBAL da lógica de variedade.
# Todos os temas (atuais e futuros) compartilham estes knobs; NÃO há exceção por
# tema. Adicionar inimigos ajusta o comportamento sozinho: o teto cresce com o
# pool e o spotlight decai com o tempo. Consumido por `_select_variety_subset`.
# ════════════════════════════════════════════════════════════════════════════

# — TETO de variedade (filosofia "SWARM + N complementares") —
# O base do tema (Meteor/RockGlider/CityDrone, papel "volume") é o SWARM: a massa
# sempre presente e mais frequente. O teto conta o base como 1 dos slots, então:
#   Normal/Casual  cap 3 → SWARM + 2 complementares (pressão + controle + ameaça);
#   Hardcore/Pesadelo cap 4 → SWARM + 3 complementares (uma ameaça extra).
# É um teto FIXO por dificuldade (FLOOR == MAX): a fase nunca vira uma sopa de
# specials, sempre tem o swarm + um punhado pequeno de papéis distintos. cap final
# = min(estágio_absoluto, teto) — a rampa X-1→1, X-2→2, … ainda vale na entrada do
# mundo. (POOL_FRACTION só teria efeito se FLOOR < MAX; mantido p/ extensão futura.)
VARIETY_CAP_FLOOR_BY_DIFFICULTY: dict[DifficultyPreset, int] = {
    DifficultyPreset.CASUAL: 3, DifficultyPreset.NORMAL: 3,
    DifficultyPreset.HARDCORE: 4, DifficultyPreset.NIGHTMARE: 4,
}
VARIETY_CAP_MAX_BY_DIFFICULTY: dict[DifficultyPreset, int] = {
    DifficultyPreset.CASUAL: 3, DifficultyPreset.NORMAL: 3,
    DifficultyPreset.HARDCORE: 4, DifficultyPreset.NIGHTMARE: 4,
}
VARIETY_CAP_POOL_FRACTION: float = 0.5

# — SPOTLIGHT (destaque BRANDO do special recém-introduzido) —
# Peso do special = BASELINE × (1 + GAIN × DECAY**(ranks desde o mais novo
# presente)). ADITIVO e modesto de propósito: um empurrão na estreia (cobertura)
# sem dominar — a RECÊNCIA é o motor principal de rotação e derruba quem acabou de
# aparecer. Ex. (GAIN=2, DECAY=.5): novo ×3.0 → ×2.0 → ×1.5 → ×1.25 → ~×1.0.
SPOTLIGHT_GAIN: float = 2.0
SPOTLIGHT_DECAY: float = 0.5
SPOTLIGHT_BASELINE: float = 1.0
SPOTLIGHT_WINDOW: int = 2  # ranks (a partir do mais novo) que contam como "fresco"

# — RECÊNCIA (motor de rotação / anti-repetição no mesmo mundo) —
# Aplicada a TODOS, inclusive specials (antes a assinatura a ignorava pelo peso).
# Forte e com janela 3: quem apareceu cai bem abaixo do campo por ~2-3 níveis,
# forçando rotação — nem o special mais novo se repete em excesso.
RECENCY_WINDOW: int = 3
RECENCY_PENALTY_BY_DISTANCE: dict[int, float] = {1: 0.12, 2: 0.30, 3: 0.55}

# — ARQUÉTIPO (encontros COMPLEMENTARES) —
# Penaliza candidato cujo papel já está no encontro (triangulação support/tank/
# sniper/swarm/area-denial/…), favorecendo combinações que se complementam. A
# penalidade é ESCALONADA por ocorrência (`PENALTY ** nº já presentes`): o 2º do
# mesmo papel cai ×0.18, o 3º ×0.0324, … — empurra mais forte contra empilhar a
# mesma função na cauda de pools grandes (ex.: 3 area_denial da Cidade).
ROLE_REPEAT_PENALTY: float = 0.18

# — PERSISTÊNCIA dos antigos —
# Nº de vagas (além da base) barradas a specials "frescos", garantindo ao menos um
# veterano/antigo por encontro grande (só aplica se houver candidato não-fresco).
VETERAN_RESERVE: int = 1

# — HISTÓRICO DE COMBINAÇÃO (anti-repetição do "triângulo" inteiro) —
# Além da recência POR TIPO, evitamos repetir o CONJUNTO de specials (o triângulo
# sem o swarm) das fases vizinhas. A fase imediatamente anterior (distância 1) é
# PROIBIDA: se o sorteio reproduzir aquele conjunto exato, re-sorteamos com seed
# perturbado até diferir. As distâncias 2-3 são EVITADAS em best-effort no mesmo
# re-sorteio (preferimos um conjunto inédito na janela, mas não falhamos por elas).
# Só atua quando o pool de specials excede o nº de vagas — senão não há como variar.
COMBINATION_HISTORY: int = 3
COMBINATION_RESHUFFLE_ATTEMPTS: int = 16

# — SEMENTE POR-PARTIDA (variedade entre runs) —
# A seleção de variedade é determinística por nível: sem isto, rejogar a MESMA
# fase (ou uma nova campanha) traz sempre os MESMOS specials, e um tipo que perde
# o sorteio (ex.: IceGolem no Mundo 1) fica com chance ZERO para sempre, para todo
# jogador. Este salt é sorteado UMA vez por run (início da PlayingScene, via
# `set_run_variety_salt`) e somado à seed de TODO nível. Como é constante durante a
# run, a reconstrução de níveis vizinhos (recência + histórico de combinação) segue
# batendo com a realidade — a anti-repetição ENTRE fases é preservada. Entre runs
# distintas o salt muda, então cada tipo (inclusive os raros) ganha chance real ao
# longo das tentativas. Default 0 = determinístico (análise/testes reproduzíveis).
_RUN_VARIETY_SALT: int = 0


def set_run_variety_salt(salt: int) -> None:
    """Define o salt de variedade da run atual (0 = determinístico, legado).

    Chamado no início de cada sessão de jogo. Afeta só QUAIS tipos são sorteados
    por nível — não muda o teto de variedade, os gates de introdução, nem a
    dificuldade. Persistência global (não thread) espelha `TEST_ARENA_ENABLED`.
    """
    global _RUN_VARIETY_SALT
    _RUN_VARIETY_SALT = int(salt) & 0x7FFFFFFF


def _global_variety_ceiling(pool_size: int, difficulty_preset: DifficultyPreset) -> int:
    """Teto de variedade GLOBAL dirigido pelo tamanho do pool (sem exceção por
    tema): mais tipos disponíveis → mais vagas, limitado a [FLOOR, MAX]."""
    floor = VARIETY_CAP_FLOOR_BY_DIFFICULTY.get(difficulty_preset, 3)
    ceil_ = VARIETY_CAP_MAX_BY_DIFFICULTY.get(difficulty_preset, 4)
    target = int(pool_size * VARIETY_CAP_POOL_FRACTION + 0.5)  # round-half-up
    return max(floor, min(ceil_, target))


def _select_variety_subset(
    spawn_config: EnemySpawnConfig,
    world: "WorldConfig",
    difficulty_preset: DifficultyPreset,
    level_number: int,
    recency_penalty: dict[type, float],
    seed_salt: int = 0,
) -> list[type]:
    """Seleciona o subconjunto de tipos de um nível (base + specials).

    Determinístico por nível. Combina, num único sorteio ponderado por vaga:
      - SPOTLIGHT: o special recém-introduzido domina sua vaga e DECAI até o piso
        dos veteranos (`SPOTLIGHT_*`) — destaque ao novo sem descartar o antigo;
      - TRIANGULAÇÃO: papel já no encontro é penalizado (`ROLE_REPEAT_PENALTY`);
      - RECÊNCIA: tipo visto nos níveis recentes é penalizado (`recency_penalty`);
      - PERSISTÊNCIA: `VETERAN_RESERVE` vagas barradas a specials frescos.
    O teto vem de `_global_variety_ceiling` (dirigido pelo pool, global). O sorteio
    ponderado (seed por nível) faz níveis consecutivos divergirem.
    """
    total_stages = max(1, world.total_stages)
    stage_number = max(1, min(total_stages, world.get_stage_number(level_number)))

    types = list(spawn_config)
    cap = min(stage_number, _global_variety_ceiling(len(types), difficulty_preset))
    if len(types) <= cap:
        return types

    signatures = THEME_SIGNATURE_ENEMIES.get(world.theme, ())
    sig_rank = {t: i for i, t in enumerate(signatures)}  # maior = mais recém-liberada
    present_ranks = [sig_rank[t] for t in types if t in sig_rank]
    newest_rank = max(present_ranks) if present_ranks else -1

    def _is_fresh(t: type) -> bool:
        """Special recém-introduzido — dentro da janela de spotlight."""
        return t in sig_rank and (newest_rank - sig_rank[t]) < SPOTLIGHT_WINDOW

    # adler32 garante seed determinístico entre sessões (hash(str) é randomizado).
    # seed_salt perturba o sorteio no re-sorteio do histórico de combinação,
    # mantendo determinismo por (nível, tentativa). `_RUN_VARIETY_SALT` varia por
    # run (constante DURANTE a run — ver set_run_variety_salt): dá variedade entre
    # partidas sem quebrar a reconstrução de vizinhos (que usa o mesmo salt global).
    theme_seed = zlib.adler32(world.theme.value.encode("utf-8"))
    rng = random.Random(
        level_number * 7919
        + theme_seed
        + seed_salt * 104729
        + _RUN_VARIETY_SALT * 2654435761
    )

    chosen: list[type] = []
    # Contagem de papéis já no encontro (não um set): a penalidade de repetição é
    # escalonada por ocorrência. PREMISSA: o base usa papel exclusivo ("volume"/
    # "swarm"), que nenhum special compartilha — então ocupar o slot do base não
    # penaliza nenhum candidato. Se um base futuro herdar papel de uma assinatura,
    # essa assinatura nasceria penalizada já no 1º slot (rever aqui).
    chosen_roles: dict[str, int] = {}
    base = THEME_BASE_ENEMY.get(world.theme)
    if base is not None and base in spawn_config:
        chosen.append(base)
        chosen_roles[_enemy_role(base)] = chosen_roles.get(_enemy_role(base), 0) + 1

    max_fresh = max(0, cap - 1 - VETERAN_RESERVE)  # vagas p/ frescos além da base
    fresh_count = 0

    while len(chosen) < cap:
        candidates = [t for t in types if t not in chosen]
        # Trava de persistência: atingido o teto de "frescos", reserva a(s) vaga(s)
        # restante(s) p/ veteranos/antigos — só se houver candidato não-fresco.
        if fresh_count >= max_fresh:
            veterans = [t for t in candidates if not _is_fresh(t)]
            if veterans:
                candidates = veterans
        if not candidates:
            break
        weights: list[float] = []
        for t in candidates:
            if t in sig_rank:
                steps_old = newest_rank - sig_rank[t]
                w = SPOTLIGHT_BASELINE * (
                    1.0 + SPOTLIGHT_GAIN * SPOTLIGHT_DECAY**steps_old
                )
            else:
                w = SPOTLIGHT_BASELINE
            role_reps = chosen_roles.get(_enemy_role(t), 0)
            if role_reps:
                w *= ROLE_REPEAT_PENALTY**role_reps
            w *= recency_penalty.get(t, 1.0)
            weights.append(max(w, 1e-6))
        idx = rng.choices(range(len(candidates)), weights=weights, k=1)[0]
        pick = candidates[idx]
        chosen.append(pick)
        pick_role = _enemy_role(pick)
        chosen_roles[pick_role] = chosen_roles.get(pick_role, 0) + 1
        if _is_fresh(pick):
            fresh_count += 1

    return chosen


def _recency_penalty_for_level(
    composition: EnemySpawnConfig,
    world: "WorldConfig",
    difficulty_preset: DifficultyPreset,
    level_number: int,
) -> dict[type, float]:
    """Penalidade de recência POR TIPO para um nível: aproximada rodando a seleção
    recency-FREE dos `RECENCY_WINDOW` níveis anteriores sobre o pool atual.

    Sem recursão — a seleção dos anteriores não consulta recência. O base nunca é
    penalizado (sempre aparece). Reusada pelo nível atual e, no histórico de
    combinação, para reconstruir a composição dos níveis vizinhos.
    """
    base = THEME_BASE_ENEMY.get(world.theme)
    recency_penalty: dict[type, float] = {}
    for dist in range(1, RECENCY_WINDOW + 1):
        prev = level_number - dist
        if prev < world.start_level:
            break
        prev_chosen = _select_variety_subset(
            composition, world, difficulty_preset, prev, {}
        )
        factor = RECENCY_PENALTY_BY_DISTANCE.get(dist, 1.0)
        for t in prev_chosen:
            if t == base:
                continue
            recency_penalty[t] = min(recency_penalty.get(t, 1.0), factor)
    return recency_penalty


def _apply_enemy_variety_cap(
    config: LevelConfig,
    world: "WorldConfig",
    difficulty_preset: DifficultyPreset,
) -> LevelConfig:
    """Limita o spawn_config à "pirâmide de N" tipos por nível via uma rampa
    GLOBAL ancorada no índice absoluto do estágio dentro do mundo.

    Regra de design (aplicada a todos os temas, existentes e futuros):
      - `cap = min(estágio_absoluto, _global_variety_ceiling(|pool|, dif))` — teto
        GLOBAL dirigido pelo tamanho do pool (sem exceção por tema). X-1 → 1 tipo,
        X-2 → 2, …, até o teto. Mais tipos liberados → mais vagas.
      - É só TETO: se o pool ainda tem poucos tipos liberados, mostra menos — sem
        pico de complexidade na entrada de um mundo novo.
      - A seleção (`_select_variety_subset`) é base (SWARM) + specials, com
        assinatura, triangulação por papel e JANELA DE RECÊNCIA: tipos vistos nos
        `RECENCY_WINDOW` níveis anteriores (mesmo mundo) têm a chance reduzida.
      - HISTÓRICO DE COMBINAÇÃO: além da recência por tipo, o CONJUNTO de specials
        não pode repetir a fase imediatamente anterior (proibição dura via
        re-sorteio) e evita as `COMBINATION_HISTORY` fases recentes em best-effort
        — o triângulo muda de fase em fase, dando sensação de progressão.
    """
    spawn_config = config.enemy_spawn_config

    # CAMADA SEPARADA — ameaças ocasionais (SquareMinionBoss, GuidedMeteor) marcadas
    # com OCCASIONAL_THREAT são eventos/ameaças esporádicas, não parte da composição
    # do tema. Saem da seleção do variety cap (não disputam vaga, não entram na
    # triangulação/recência/introdução de arquétipos) e voltam intactas no fim —
    # assim sua aparição não reduz a variedade dos inimigos principais da fase.
    occasional = {
        t: st for t, st in spawn_config.items() if getattr(t, "OCCASIONAL_THREAT", False)
    }
    composition = (
        spawn_config
        if not occasional
        else {t: st for t, st in spawn_config.items() if t not in occasional}
    )

    base = THEME_BASE_ENEMY.get(world.theme)

    def _specials(types_list: list[type]) -> frozenset:
        """Conjunto de specials (o triângulo SEM o swarm-base)."""
        return frozenset(t for t in types_list if t != base)

    # HISTÓRICO DE COMBINAÇÃO — anti-repetição do "triângulo" inteiro (conjunto de
    # specials). Resolvido RECURSIVAMENTE e memoizado, ancorado no início do mundo:
    # cada nível compara seu sorteio contra os conjuntos FINAIS (já resolvidos) das
    # fases recentes — não contra uma aproximação pré-histórico, que falharia quando
    # a fase anterior tivesse sido re-sorteada. Distância 1 é PROIBIDA (re-sorteio
    # com seed perturbado força um conjunto diferente); distâncias 2-3 são evitadas
    # em best-effort. Só atua quando há specials suficientes para variar.
    # Aproximação herdada da recência: usa o pool (composition) do nível ATUAL para
    # reconstruir os vizinhos — estável entre níveis adjacentes do mesmo mundo.
    resolved: dict[int, list[type]] = {}

    def _resolve(level: int) -> list[type]:
        cached = resolved.get(level)
        if cached is not None:
            return cached
        recency = _recency_penalty_for_level(
            composition, world, difficulty_preset, level
        )
        picked = _select_variety_subset(
            composition, world, difficulty_preset, level, recency
        )
        recent_sets: list[frozenset] = []
        for dist in range(1, COMBINATION_HISTORY + 1):
            prev = level - dist
            if prev < world.start_level:
                break
            recent_sets.append(_specials(_resolve(prev)))
        if recent_sets and _specials(picked) in set(recent_sets):
            forbidden = recent_sets[0]  # fase anterior — proibição dura
            avoid = set(recent_sets)  # janela 1-3 — evitar
            fallback: list[type] | None = None  # ao menos diverge da fase anterior
            for salt in range(1, COMBINATION_RESHUFFLE_ATTEMPTS + 1):
                cand = _select_variety_subset(
                    composition, world, difficulty_preset, level, recency, salt
                )
                cand_set = _specials(cand)
                if cand_set not in avoid:
                    picked = cand  # inédito na janela inteira — melhor caso
                    break
                if cand_set != forbidden and fallback is None:
                    fallback = cand
            else:
                # Nenhum conjunto inédito na janela; use o que ao menos não repete a
                # fase anterior. Se nem isso (pool pequeno demais), mantém o sorteio.
                if fallback is not None:
                    picked = fallback
        resolved[level] = picked
        return picked

    chosen = _resolve(config.level_number)

    # Composição capada + ameaças ocasionais de volta (sempre presentes quando o
    # gate de spawn as liberou — não foram cortadas pelo teto).
    adjusted_spawn_config = {t: composition[t] for t in chosen}
    adjusted_spawn_config.update(occasional)
    if adjusted_spawn_config == spawn_config:
        return config
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

    # Padrão do pipeline: copy.copy + mutar só os campos afetados (robusto a
    # campos novos de LevelConfig, que de outro modo seriam zerados aqui).
    config_copy = copy.copy(config)
    config_copy.enemy_spawn_config = adjusted_spawn_config
    config_copy.theme_name = world.name
    return config_copy


def _create_world_boss_level(
    world: "WorldConfig",
    level_number: int,
    difficulty_preset: DifficultyPreset,
    boss_cls: type,
) -> LevelConfig:
    """Cria configuração paramétrica para um boss-level (adds por tema).

    Usado para bosses SEM layout handcrafted em FIXED_LEVELS (setores procedurais
    e o boss final da Cidade/Vulcão). A classe vem do resolvedor único
    (`get_boss_for_level`), não de `world.boss_type`.
    """
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
        boss_type=boss_cls,
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

    EXCEÇÃO ao fluxo de boss: aqui o `boss_type` vem do TEMPLATE da arena
    (`THEME_TEST_LEVELS`), NÃO do roadmap — é dev/teste e não passa pelo pipeline,
    então a classe injetada por `get_boss_for_level` não se aplica.
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

    # Fonte ÚNICA da classe do boss (mid + final, nomeado + procedural).
    boss_cls = get_boss_for_level(level_number)

    # Boss SEM layout handcrafted (setores procedurais, final da Cidade/Vulcão):
    # adds paramétricos por tema. Bosses COM entrada em FIXED_LEVELS caem no branch
    # abaixo (mantêm o layout desenhado à mão) e recebem a classe injetada.
    if (
        boss_cls is not None
        and level_number not in FIXED_LEVELS
        and not force_meteor_storm
    ):
        config = _create_world_boss_level(
            world, level_number, difficulty_preset, boss_cls
        )
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
        # Boss-level handcrafted: a CLASSE vem do roadmap (fonte única); FIXED_LEVELS
        # contribui só com o layout de inimigos/score/nome.
        config.boss_type = boss_cls
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
