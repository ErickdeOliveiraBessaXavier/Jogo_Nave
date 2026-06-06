"""Geração procedural de níveis + parâmetros de dificuldade.

Contém:
  - `DifficultyConfig`: constantes globais de spawn/cap/min de dificuldade.
  - `DifficultyCurves`: funções matemáticas de progressão.
  - `ProceduralLevelGenerator`: gera `LevelConfig` para níveis não-fixos.
  - `calculate_dynamic_enemy_cap`: cap total simultâneo por nível.
  - Helpers de pressão (ENEMY_PRESSURE_*) e curva por estágio do mundo.
"""

from __future__ import annotations

import math
import random

from ...entities.alien import Alien
from ...entities.bot_elemental import ElementalRobot
from ...entities.eye_enemy import EyeEnemy
from ...entities.Inimigos_Tema_Cidade.city_drone import CityDrone
from ...entities.Inimigos_Tema_Cidade.cyber_captor import CyberCaptor
from ...entities.Inimigos_Tema_Cidade.cyber_tank import CyberTank
from ...entities.Inimigos_Tema_Cidade.jammer_node import JammerNode
from ...entities.Inimigos_Tema_Cidade.mirror_pylon import MirrorPylon
from ...entities.Inimigos_Tema_Cidade.mortar_drone import MortarDrone
from ...entities.Inimigos_Tema_Cidade.cargo_carrier import CargoCarrier
from ...entities.Inimigos_Tema_Cidade.sapper_drone import SapperDrone
from ...entities.Inimigos_Tema_Cidade.splitter_tank import SplitterTank
from ...entities.Inimigos_Tema_Cidade.neon_sniper import NeonSniper
from ...entities.Inimigos_Tema_Cidade.police_interceptor import PoliceInterceptor
from ...entities.Inimigos_Tema_Cidade.tesla_twin import TeslaTwin
from ...entities.cutting_storm import CuttingStorm
from ...entities.giant_meteor_boss import GiantMeteorBoss
from ...entities.ice_golem import IceGolem
from ...entities.meteor import Meteor
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
from ..world_config import WorldTheme, get_world_for_level
from .fixed_levels import (
    MIN_SPAWN_TIME,
    EnemySpawnConfig,
    LevelConfig,
    LevelTheme,
    LEVEL_THEMES,
)


# Temas em que Alien/Eye/SquareMinionBoss são configurados via bandas de
# stage_progress (early/mid/late). Outros temas usam o cálculo baseado em
# theme.enemy_weight + _get_progressive_enemy_weight.
#
# ATENÇÃO ao duplo papel deste conjunto: ele governa DUAS coisas — (a) as bandas
# de inimigo acima e (b) a lógica banded de FORMAÇÕES em generate_config. A CITY
# está aqui SÓ por (b): tem linhagem própria montada em _configure_city_spawn e é
# EXPLICITAMENTE excluída de (a) (ver `... and world.theme != WorldTheme.CITY` em
# generate_config). Por isso não renomear para "_FORMATION_BANDED_THEMES": o nome
# atual cobre (a), que vale para STARFIELD/VOLCANIC/PROCEDURAL.
_STAGE_BANDED_THEMES: tuple[WorldTheme, ...] = (
    WorldTheme.STARFIELD,
    WorldTheme.CITY,
    WorldTheme.VOLCANIC,
    WorldTheme.PROCEDURAL,
)


# Features de spawn especial disponíveis por tema.
# Consultado pelos spawners especiais — adicionar tema novo = uma entrada aqui.
THEME_FEATURES: dict[WorldTheme, set[str]] = {
    WorldTheme.STARFIELD: {"formations", "mines", "guided_meteors"},
    WorldTheme.MOUNTAINS: {"mines", "propellers"},
    # CITY usa só a própria linhagem coordenada — sem formações de Alien nem
    # meteoros guiados (inimigos de outros temas). Mantém apenas mines (hazard).
    WorldTheme.CITY: {"mines"},
    WorldTheme.VOLCANIC: {"formations", "mines"},
    WorldTheme.PROCEDURAL: {"formations", "mines", "guided_meteors"},
}


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
    BASE_ALIEN_SPAWN_TIME: float = 4.5
    BASE_EYE_SPAWN_TIME: float = 6.0
    MIN_SPAWN_TIME: float = MIN_SPAWN_TIME  # Aumentado para evitar frenesi excessivo
    WEIGHTED_SPAWN_TICK: float = 0.25
    WEIGHTED_RECENT_MEMORY: int = 3
    WEIGHTED_REPEAT_PENALTY: float = 0.45
    WEIGHTED_SPAWN_TELEMETRY: bool = False
    WEIGHTED_TELEMETRY_INTERVAL: float = 15.0

    MIN_ENEMIES_TO_CLEAR: int = 80
    MAX_ENEMIES_TO_CLEAR: int = 600
    BASE_ENEMIES: int = 25
    ENEMIES_PER_LEVEL: int = 5
    ENEMY_VARIATION: int = 20

    # Cadência mínima entre spawns para evitar bursts em sequência.
    MIN_GLOBAL_SPAWN_GAP: float = 0.16
    DIFFICULTY_SPAWN_GAP_MULTIPLIER: dict[DifficultyPreset, float] = {
        DifficultyPreset.CASUAL: 1.10,
        DifficultyPreset.NORMAL: 1.00,
        DifficultyPreset.HARDCORE: 0.85,
        DifficultyPreset.NIGHTMARE: 0.70,
    }
    MIN_SPAWN_GAP_BY_TYPE: dict[str, float] = {
        "meteor": 0.18,
        "rock_glider": 0.18,
        "alien": 0.42,
        "eye": 0.70,
        "square_minion_boss": 1.00,
        "elemental_robot": 0.90,
        "stone_sentry": 30.0,
        "mountain_mage": 8.0,
        "mountain_propeller": 5.0,
        "city_drone": 4.0,
        "neon_sniper": 10.0,
        "police_interceptor": 9.0,
        "cyber_tank": 22.0,
        "cyber_captor": 12.0,
        "tesla_twin": 16.0,
        "jammer": 13.0,
        "orbital_turret": 12.0,
        "stealth_fighter": 7.0,
        "repair_drone": 14.0,
        "ice_golem": 18.0,
        "cutting_storm": 12.0,
        "stone_eagle": 7.0,
    }

    DIFFICULTY_SCALING: float = 0.15
    MAX_DIFFICULTY_MULTIPLIER: float = 2.5

    # Limite total de inimigos simultâneos por dificuldade
    DIFFICULTY_TOTAL_ENEMY_CAPS: dict[DifficultyPreset, int] = {
        DifficultyPreset.CASUAL: 18,
        DifficultyPreset.NORMAL: 20,
        DifficultyPreset.HARDCORE: 22,
        DifficultyPreset.NIGHTMARE: 25,
    }

    ADAPTIVE_SPAWN_ENABLED: bool = True
    SPAWN_REDUCTION_THRESHOLD: float = 0.80

    SPAWN_RATE_CURVE: str = "logarithmic"
    ENEMY_COUNT_CURVE: str = "linear"

    MINES_UNLOCK_LEVEL: int = 2
    MINES_PROBABILITY: float = 0.6
    FORMATIONS_UNLOCK_LEVEL: int = 4

    LEVEL_VARIETY_ENABLED: bool = True


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
# PROGRESSÃO NATURAL DE PRESSÃO (VOLUME / INTERMEDIÁRIO / FORTE)
# ============================================================================

ENEMY_PRESSURE_TIER_BY_KEY: dict[str, str] = {
    "meteor": "volume",
    "rock_glider": "volume",
    "alien": "intermediate",
    "eye": "strong",
    "square_minion_boss": "strong",
    "elemental_robot": "strong",
    "stone_sentry": "strong",
    "neon_sniper": "strong",
    "police_interceptor": "strong",
    "cyber_tank": "strong",
    "cyber_captor": "strong",
    "tesla_twin": "strong",
    "orbital_turret": "strong",
    "stealth_fighter": "intermediate",
    "repair_drone": "strong",
    "ice_golem": "strong",
    "cutting_storm": "strong",
    "stone_eagle": "intermediate",
}

ENEMY_PRESSURE_TIER_CURVE: dict[str, tuple[float, float]] = {
    "volume": (1.25, 0.90),
    "intermediate": (0.55, 1.15),
    "strong": (0.20, 0.95),
}

ENEMY_PRESSURE_UNLOCK_START: dict[str, float] = {
    "meteor": 0.0,
    "rock_glider": 0.0,
    "alien": 0.08,
    "eye": 0.38,
    "square_minion_boss": 0.30,
    "elemental_robot": 0.55,
    "stone_sentry": 0.42,
    "neon_sniper": 0.30,
    "police_interceptor": 0.20,
    "cyber_tank": 0.62,
    "cyber_captor": 0.40,
    "tesla_twin": 0.50,
    "jammer": 0.50,
    "mortar": 0.30,
    "cargo_carrier": 0.62,
    "splitter": 0.74,
    "sapper": 0.40,
    "mirror": 0.74,
    "stealth_fighter": 0.10,
    "orbital_turret": 0.30,
    "repair_drone": 0.50,
    "stone_eagle": 0.10,
    "cutting_storm": 0.40,
    "ice_golem": 0.50,
}

ENEMY_PRESSURE_UNLOCK_WINDOW: dict[str, float] = {
    "meteor": 0.01,
    "rock_glider": 0.01,
    "alien": 0.30,
    "eye": 0.28,
    "square_minion_boss": 0.32,
    "elemental_robot": 0.30,
    "stone_sentry": 0.30,
    "neon_sniper": 0.30,
    "police_interceptor": 0.30,
    "cyber_tank": 0.30,
    "cyber_captor": 0.30,
    "tesla_twin": 0.30,
    "jammer": 0.30,
    "mortar": 0.30,
    "cargo_carrier": 0.30,
    "splitter": 0.30,
    "sapper": 0.30,
    "mirror": 0.30,
    "stealth_fighter": 0.30,
    "orbital_turret": 0.30,
    "repair_drone": 0.30,
    "stone_eagle": 0.30,
    "cutting_storm": 0.30,
    "ice_golem": 0.30,
}


# Tetos de intervalo de spawn (s) por categoria de inimigo do CITY. O fator
# `2/weight` em `_configure_city_spawn` estourava o spawn_time p/ 100-500s na
# introdução (weight no piso), deixando o inimigo no pool mas sem nunca spawnar.
# Estes tetos garantem que ele apareça de fato desde a introdução E APERTAM
# conforme o mundo avança (combate mais frenético no fim). (teto na introdução,
# teto no fim do mundo).
CITY_SPAWN_TIME_CAP: dict[str, tuple[float, float]] = {
    "control": (16.0, 9.0),  # Police/Captor/Tesla/Jammer/Mortar/Sapper
    "miniboss": (38.0, 24.0),  # CyberTank/CargoCarrier/SplitterTank/MirrorPylon
}


# Gates de introdução (unlock) dos specials do CITY por `stage_progress`. Cada um
# marca QUANDO o tipo entra no pool de `_configure_city_spawn` (a frequência rampa
# a partir daí). Valores casam com a rampa de variedade e os comentários "~X-N"
# da função. Nomeados aqui para a lógica ficar autodocumentada (sem números soltos).
CITY_GATE_POLICE: float = 0.20  # ~X-3
CITY_GATE_MORTAR: float = 0.30  # ~X-4
CITY_GATE_CAPTOR: float = 0.40  # ~X-5
CITY_GATE_SAPPER: float = 0.40  # ~X-5
CITY_GATE_TESLA: float = 0.50  # ~X-6
CITY_GATE_JAMMER: float = 0.50  # ~X-6
CITY_GATE_CYBER_TANK: float = 0.62  # ~X-7
CITY_GATE_CARGO: float = 0.62  # ~X-7
CITY_GATE_SPLITTER: float = 0.74  # ~X-8
CITY_GATE_MIRROR: float = 0.74  # ~X-8


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

    if unlock_start <= 0.0:
        gate_mult = 1.0
    else:
        gate_mult = 0.15 + 0.85 * unlock_progress

    return max(0.05, base_weight * tier_mult * gate_mult)


def calculate_dynamic_enemy_cap(
    level_number: int,
    difficulty_preset: DifficultyPreset,
    player_count: int = 1,
) -> int:
    """Calcula o limite de inimigos simultâneos de forma progressiva por mundo."""
    base_cap = DifficultyConfig.DIFFICULTY_TOTAL_ENEMY_CAPS.get(difficulty_preset, 20)
    world = get_world_for_level(level_number)
    world_bonus = min(world.world_id - 1, 4)

    stage = world.get_stage_number(level_number)
    total_stages = world.total_stages
    if total_stages > 1:
        stage_progress = (stage - 1) / (total_stages - 1)
        stage_bonus = min(4, int(stage_progress * 4 + 0.5))
    else:
        stage_bonus = 0

    base = base_cap + world_bonus + stage_bonus
    coop_multiplier = 1.0 + 0.20 * max(0, player_count - 1)
    return int(round(base * coop_multiplier))


# ============================================================================
# GERADOR PROCEDURAL
# ============================================================================


class ProceduralLevelGenerator:
    """Gerador de níveis procedurais com progressão de dificuldade."""

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

        if len(self._level_cache) > 50:
            self._level_cache.pop(next(iter(self._level_cache)))

        return config

    def _generate_level_impl(self, level_number: int) -> LevelConfig:
        rng = random.Random(self.seed * 10_000 + level_number)
        difficulty = self.calculate_difficulty(level_number)

        theme = None
        if DifficultyConfig.LEVEL_VARIETY_ENABLED:
            theme = self._choose_theme(level_number, rng)

        return self.generate_config(level_number, difficulty, theme, rng)

    def calculate_difficulty(self, level_number: int) -> float:
        """Calcula multiplicador de dificuldade usando curva configurada."""
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
        self._difficulty_cache[level_number] = difficulty
        return difficulty

    def _choose_theme(self, level_number: int, rng: random.Random) -> LevelTheme | None:
        """Escolhe um tema baseado no nível."""
        world = get_world_for_level(level_number)
        stage_number = world.get_stage_number(level_number)

        if level_number <= 2 or stage_number <= 2:
            return LEVEL_THEMES["balanced"]

        if level_number >= 8 and level_number % 5 == 0:
            if rng.random() < 0.4:
                if world.theme == WorldTheme.STARFIELD:
                    return LEVEL_THEMES["meteor_storm"]
                if world.theme == WorldTheme.MOUNTAINS:
                    return LEVEL_THEMES["rock_glider_storm"]

        if level_number >= 6:
            special_chance = min(0.7, 0.3 + (level_number / 100))
            if rng.random() < special_chance:
                special_themes = ["minefield", "formation_hell", "eye_swarm"]
                available = [
                    t for t in special_themes if self._theme_available(t, level_number)
                ]
                if available:
                    theme_name = rng.choice(available)
                    return LEVEL_THEMES[theme_name]

        standard_themes = ["asteroid_field", "alien_invasion", "balanced"]
        if level_number >= 5:
            standard_themes.append("eye_swarm")

        theme_name = rng.choice(standard_themes)
        return LEVEL_THEMES[theme_name]

    def _theme_available(self, theme_name: str, level_number: int) -> bool:
        if theme_name == "minefield":
            return level_number >= DifficultyConfig.MINES_UNLOCK_LEVEL
        if theme_name == "formation_hell":
            return level_number >= DifficultyConfig.FORMATIONS_UNLOCK_LEVEL
        if theme_name == "eye_swarm":
            return level_number >= 5
        return True

    def _clamp_spawn_time(self, time: float) -> float:
        return max(DifficultyConfig.MIN_SPAWN_TIME, time)

    def _city_progressive_spawn_time(
        self,
        base: float,
        weight: float,
        difficulty: float,
        spawn_multiplier: float,
        category: str,
        progress: float,
    ) -> float:
        """spawn_time progressivo do CITY com TETO por categoria.

        Mantém a rampa por `weight` (mais frequente conforme o weight sobe), mas
        aplica um teto (`CITY_SPAWN_TIME_CAP`) para o inimigo aparecer de fato
        desde a introdução — o `2/weight` sozinho estourava p/ 100-500s. O teto
        também aperta com `progress` (intensidade crescente ao longo do mundo).
        """
        raw = (base / difficulty / spawn_multiplier) * (2.0 / weight)
        cap_intro, cap_late = CITY_SPAWN_TIME_CAP[category]
        cap = cap_intro + (cap_late - cap_intro) * _clamp01(progress)
        return min(cap, self._clamp_spawn_time(raw))

    def _configure_mountains_spawn(
        self,
        enemy_spawn_config: EnemySpawnConfig,
        stage_progress: float,
        stage_number: int,
        difficulty: float,
        spawn_multiplier: float,
    ) -> None:
        """Configura spawn de MountainMage/Propeller/StoneSentry/ElementalRobot.

        Curva de introdução por estágio absoluto (ver §regra de variedade):
        RockGlider (base, sempre) → MountainMage (2º, X-2) → MountainPropeller
        (3º, X-3). StoneSentry e ElementalRobot são os "pesados" tardios e
        seguem gate por stage_progress (rotacionam no pool depois). A FREQUÊNCIA
        de todos continua escalando por stage_progress.
        """
        if stage_number >= 2:
            if stage_progress < 0.40:
                mage_base_time = 22.0
            elif stage_progress < 0.70:
                mage_base_time = 14.0
            else:
                mage_base_time = 10.0
            enemy_spawn_config[MountainMage] = self._clamp_spawn_time(
                (mage_base_time / difficulty) / spawn_multiplier
            )

        if stage_number >= 3:
            enemy_spawn_config[MountainPropeller] = self._clamp_spawn_time(
                (20.0 / difficulty) / spawn_multiplier
            )

        if stage_progress >= 0.40:
            sentry_weight = _get_progressive_enemy_weight(
                "stone_sentry", 1.0, stage_progress
            )
            enemy_spawn_config[StoneSentry] = self._clamp_spawn_time(
                (10.0 / difficulty / spawn_multiplier) * (2.0 / sentry_weight)
            )

        if stage_progress >= 0.53:
            robot_weight = _get_progressive_enemy_weight(
                "elemental_robot", 1.0, stage_progress
            )
            enemy_spawn_config[ElementalRobot] = self._clamp_spawn_time(
                (15.0 / difficulty / spawn_multiplier) * (2.0 / robot_weight)
            )

        # Specials novos das Cordilheiras — desbloqueiam DEPOIS do trio de
        # introdução (RockGlider/MountainMage/Propeller) para não roubar o slot do
        # 2º/3º tipo. Intervalo direto (sem 2/weight) p/ não estourar a loteria de
        # variedade; são assinaturas (THEME_SIGNATURE_ENEMIES) — ver §11/pipeline.
        if stage_number >= 4:  # Águia de Pedra (rush em mergulho)
            if stage_progress < 0.55:
                eagle_base = 11.0
            elif stage_progress < 0.80:
                eagle_base = 9.0
            else:
                eagle_base = 7.0
            enemy_spawn_config[StoneEagle] = self._clamp_spawn_time(
                (eagle_base / difficulty) / spawn_multiplier
            )

        if stage_progress >= 0.55:  # Tempestade Cortante (negação de área)
            storm_base = 16.0 if stage_progress < 0.75 else 12.0
            enemy_spawn_config[CuttingStorm] = self._clamp_spawn_time(
                (storm_base / difficulty) / spawn_multiplier
            )

        if stage_progress >= 0.65:  # Golem de Gelo (tanque)
            golem_base = 22.0 if stage_progress < 0.85 else 17.0
            enemy_spawn_config[IceGolem] = self._clamp_spawn_time(
                (golem_base / difficulty) / spawn_multiplier
            )

    def _configure_city_spawn(
        self,
        enemy_spawn_config: EnemySpawnConfig,
        stage_progress: float,
        difficulty: float,
        spawn_multiplier: float,
    ) -> None:
        """Injeta o City Drone (enxame) no pool do bioma CITY.

        Disponível desde o início do mundo para dar identidade ao tema; o
        intervalo encurta conforme o estágio avança. O spawn real acontece em
        cluster (5-8 unidades) no `EnemySpawner`, então o intervalo aqui é o
        tempo entre *levas*, não entre drones.
        """
        if stage_progress < 0.40:
            drone_base = 7.0
        elif stage_progress < 0.70:
            drone_base = 5.5
        else:
            drone_base = 4.0
        enemy_spawn_config[CityDrone] = self._clamp_spawn_time(
            (drone_base / difficulty) / spawn_multiplier
        )

        # Neon Sniper: sentinela "assinatura" do bioma. Presente desde o início
        # do mundo (garantido no pool pelo variety cap via THEME_SIGNATURE_ENEMIES)
        # e mais frequente conforme o estágio avança. O cap de 3 simultâneos
        # (SPAWNER_CAP_NEON_SNIPER) controla a presença em tela; aqui é só o
        # intervalo entre perch units. Intervalo direto (sem 2/weight, que
        # explodia para >200s no ramp-up e o excluía da loteria de variedade).
        sniper_base = 15.0 if stage_progress < 0.5 else 10.0
        enemy_spawn_config[NeonSniper] = self._clamp_spawn_time(
            (sniper_base / difficulty) / spawn_multiplier
        )

        # Police Interceptor: 3º inimigo da introdução do CITY (após City Drone e
        # Neon Sniper). Gate em 0.20 p/ entrar no pool em 3-3 (stage_progress
        # (3-1)/9 ≈ 0.222), que é quando a rampa de variedade chega a 3 tipos —
        # mas NÃO em 3-2 (0.111). Casa o UNLOCK_START 0.20 p/ a frequência rampar
        # daí. Spawna em duplas (cap 4 controla a tela); o valor aqui é o
        # intervalo entre *duplas*. Peso ponderado via tier "strong" + gate.
        if stage_progress >= CITY_GATE_POLICE:
            interceptor_weight = _get_progressive_enemy_weight(
                "police_interceptor", 1.0, stage_progress
            )
            enemy_spawn_config[PoliceInterceptor] = self._city_progressive_spawn_time(
                14.0, interceptor_weight, difficulty, spawn_multiplier,
                "control", stage_progress,
            )

        # Cyber Tank: "gatekeeper" mini-boss, introduzido em ~X-7 (gate 0.62).
        # Cap 1 (SPAWNER_CAP_CYBER_TANK) garante que apareça sozinho; o valor é o
        # intervalo entre aparições. BASE_TIME alto.
        if stage_progress >= CITY_GATE_CYBER_TANK:
            tank_weight = _get_progressive_enemy_weight(
                "cyber_tank", 1.0, stage_progress
            )
            enemy_spawn_config[CyberTank] = self._city_progressive_spawn_time(
                22.0, tank_weight, difficulty, spawn_multiplier,
                "miniboss", stage_progress,
            )

        # Cyber-Captor: armadilha de energia, introduzido em ~X-5 (gate 0.40).
        # Cap 2 controla a presença.
        if stage_progress >= CITY_GATE_CAPTOR:
            captor_weight = _get_progressive_enemy_weight(
                "cyber_captor", 1.0, stage_progress
            )
            enemy_spawn_config[CyberCaptor] = self._city_progressive_spawn_time(
                16.0, captor_weight, difficulty, spawn_multiplier,
                "control", stage_progress,
            )

        # Tesla Twins: barreira vertical de controle, introduzido em ~X-6 (gate
        # 0.50). Cap 1 par controla a presença; o valor é o intervalo entre
        # *pares* (peso tier "strong" + gate).
        if stage_progress >= CITY_GATE_TESLA:
            tesla_weight = _get_progressive_enemy_weight(
                "tesla_twin", 1.0, stage_progress
            )
            enemy_spawn_config[TeslaTwin] = self._city_progressive_spawn_time(
                18.0, tesla_weight, difficulty, spawn_multiplier,
                "control", stage_progress,
            )

        # Jammer Node: nó de interferência (suprime tiros por área), introduzido
        # em ~X-6 (gate 0.50). Cap 2 controla a presença; o valor é o intervalo
        # entre aparições (tier "strong" + gate).
        if stage_progress >= CITY_GATE_JAMMER:
            jammer_weight = _get_progressive_enemy_weight(
                "jammer", 1.0, stage_progress
            )
            enemy_spawn_config[JammerNode] = self._city_progressive_spawn_time(
                17.0, jammer_weight, difficulty, spawn_multiplier,
                "control", stage_progress,
            )

        # Artilheiro: bombardeio de área, o 4º tipo do CITY (introduzido em ~X-4,
        # gate 0.30). Cap 2 controla a presença; o valor é o intervalo entre aparições.
        if stage_progress >= CITY_GATE_MORTAR:
            mortar_weight = _get_progressive_enemy_weight(
                "mortar", 1.0, stage_progress
            )
            enemy_spawn_config[MortarDrone] = self._city_progressive_spawn_time(
                16.0, mortar_weight, difficulty, spawn_multiplier,
                "control", stage_progress,
            )

        # Cargueiro: transporte de tropas (mini-boss), introduzido em ~X-7 (gate
        # 0.62). Cap 1 garante que apareça sozinho; intervalo entre aparições.
        if stage_progress >= CITY_GATE_CARGO:
            carrier_weight = _get_progressive_enemy_weight(
                "cargo_carrier", 1.0, stage_progress
            )
            enemy_spawn_config[CargoCarrier] = self._city_progressive_spawn_time(
                22.0, carrier_weight, difficulty, spawn_multiplier,
                "miniboss", stage_progress,
            )

        # Splitter Tank: colosso modular do fim do mundo (mini-boss), introduzido
        # em ~X-8 (gate 0.74). Cap 1 (conta filhotes) garante que apareça sozinho.
        if stage_progress >= CITY_GATE_SPLITTER:
            splitter_weight = _get_progressive_enemy_weight(
                "splitter", 1.0, stage_progress
            )
            enemy_spawn_config[SplitterTank] = self._city_progressive_spawn_time(
                24.0, splitter_weight, difficulty, spawn_multiplier,
                "miniboss", stage_progress,
            )

        # Rebocador: suporte de blindagem, introduzido em ~X-5 (gate 0.40). Cap 2
        # controla a presença; o valor é o intervalo entre aparições.
        if stage_progress >= CITY_GATE_SAPPER:
            sapper_weight = _get_progressive_enemy_weight(
                "sapper", 1.0, stage_progress
            )
            enemy_spawn_config[SapperDrone] = self._city_progressive_spawn_time(
                18.0, sapper_weight, difficulty, spawn_multiplier,
                "control", stage_progress,
            )

        # Mirror Pylon: refletor de controle do fim do mundo, introduzido em ~X-8
        # (gate 0.74). Cap 1 garante que apareça sozinho; intervalo entre aparições.
        if stage_progress >= CITY_GATE_MIRROR:
            mirror_weight = _get_progressive_enemy_weight(
                "mirror", 1.0, stage_progress
            )
            enemy_spawn_config[MirrorPylon] = self._city_progressive_spawn_time(
                20.0, mirror_weight, difficulty, spawn_multiplier,
                "miniboss", stage_progress,
            )

    def _configure_stage_banded_spawn(
        self,
        enemy_spawn_config: EnemySpawnConfig,
        stage_progress: float,
        stage_number: int,
        difficulty: float,
        spawn_multiplier: float,
    ) -> None:
        """Configura Alien/EyeEnemy/SquareMinionBoss (Starfield/Vulcânico/Proc).

        Curva de introdução por estágio absoluto: Meteor (base, sempre) → Alien
        (2º, X-2) → EyeEnemy (3º, X-3). SquareMinionBoss é miniboss tardio (gate
        por stage_progress). A FREQUÊNCIA escala por stage_progress como antes.
        """
        if stage_number < 2:
            enemy_spawn_config.pop(Alien, None)
        else:
            if stage_progress < 0.45:
                alien_base = 5.0
            elif stage_progress < 0.70:
                alien_base = 3.2
            else:
                alien_base = 2.0
            enemy_spawn_config[Alien] = self._clamp_spawn_time(
                (alien_base / difficulty) / spawn_multiplier
            )

        if stage_number < 3:
            enemy_spawn_config.pop(EyeEnemy, None)
        else:
            if stage_progress < 0.70:
                eye_base = 9.0
            elif stage_progress < 0.85:
                eye_base = 6.0
            else:
                eye_base = 4.0
            enemy_spawn_config[EyeEnemy] = self._clamp_spawn_time(
                (eye_base / difficulty) / spawn_multiplier
            )

        if stage_progress < 0.70:
            enemy_spawn_config.pop(SquareMinionBoss, None)
        else:
            square_base = 15.0 if stage_progress < 0.85 else 10.0
            enemy_spawn_config[SquareMinionBoss] = self._clamp_spawn_time(
                (square_base / difficulty) / spawn_multiplier
            )

    def _configure_starfield_spawn(
        self,
        enemy_spawn_config: EnemySpawnConfig,
        stage_progress: float,
        stage_number: int,
        difficulty: float,
        spawn_multiplier: float,
    ) -> None:
        """Injeta o Satélite (lixo orbital) no pool exclusivo do bioma STARFIELD.

        Entra como perigo espacial de meio de mundo — gate por estágio absoluto
        em X-4, depois do trio Meteor/Alien/EyeEnemy se estabelecer, para não
        atropelar a curva de introdução. A FREQUÊNCIA escala por stage_progress.
        Continua sujeito ao teto de variedade do tema (`_apply_enemy_variety_cap`).
        """
        if stage_number < 4:
            enemy_spawn_config.pop(Satellite, None)
            return
        if stage_progress < 0.45:
            sat_base = 10.0
        elif stage_progress < 0.75:
            sat_base = 7.0
        else:
            sat_base = 5.0
        enemy_spawn_config[Satellite] = self._clamp_spawn_time(
            (sat_base / difficulty) / spawn_multiplier
        )

        # Specials novos do Espaço — desbloqueiam DEPOIS do trio de introdução
        # (Meteor/Alien/EyeEnemy nos estágios 1-3) e do Satélite (X-4), para não
        # roubar o slot do 2º/3º tipo. Intervalo direto (sem 2/weight) p/ não
        # estourar a loteria de variedade; são assinaturas — ver §11/pipeline.
        # Caça Furtivo (rush) entra junto com o Satélite (X-4).
        if stage_progress < 0.55:
            fighter_base = 11.0
        elif stage_progress < 0.80:
            fighter_base = 9.0
        else:
            fighter_base = 7.0
        enemy_spawn_config[StealthFighter] = self._clamp_spawn_time(
            (fighter_base / difficulty) / spawn_multiplier
        )

        if stage_number >= 5:  # Torreta Orbital (sniper) — um estágio após o Caça
            turret_base = 16.0 if stage_progress < 0.70 else 12.0
            enemy_spawn_config[OrbitalTurret] = self._clamp_spawn_time(
                (turret_base / difficulty) / spawn_multiplier
            )

        if stage_progress >= 0.60:  # Drone Reparador (suporte) — tardio
            drone_base = 19.0 if stage_progress < 0.80 else 15.0
            enemy_spawn_config[RepairDrone] = self._clamp_spawn_time(
                (drone_base / difficulty) / spawn_multiplier
            )

    def _calculate_score_multiplier(self, level_number: int) -> float:
        if level_number in self._score_cache:
            return self._score_cache[level_number]

        multiplier = 1.0 + math.log1p(level_number) * 0.3
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
        theme_spawn_mult = theme.spawn_rate_multiplier if theme else 1.0
        theme_enemies_mult = theme.enemies_multiplier if theme else 1.0
        preset_spawn_mult = self.difficulty_settings["spawn_rate_multiplier"]

        world = get_world_for_level(level_number)
        spawn_multiplier = theme_spawn_mult * preset_spawn_mult
        enemies_multiplier = theme_enemies_mult
        stage_progress = _get_world_stage_progress(level_number)
        # Índice absoluto do estágio (1-based) — usado pelos gates de
        # DISPONIBILIDADE (quando cada tipo entra no pool), para a curva de
        # introdução X-1→1, X-2→2, X-3+→3 valer independente do tamanho do mundo.
        # A FREQUÊNCIA de cada tipo continua escalando por stage_progress.
        stage_number = world.get_stage_number(level_number)

        enemy_spawn_config: EnemySpawnConfig = {}

        if theme and theme.special_feature in ("meteor_only", "rock_glider_only"):
            if theme.special_feature == "meteor_only":
                meteor_spawn_time = (
                    (DifficultyConfig.BASE_METEOR_SPAWN_TIME / difficulty)
                    / spawn_multiplier
                    / 2.0
                )
                enemy_spawn_config[Meteor] = self._clamp_spawn_time(meteor_spawn_time)
            else:
                rock_glider_spawn_time = (
                    (DifficultyConfig.BASE_METEOR_SPAWN_TIME / difficulty)
                    / spawn_multiplier
                    / 1.9
                )
                enemy_spawn_config[RockGlider] = self._clamp_spawn_time(
                    rock_glider_spawn_time
                )
        else:
            meteor_weight = theme.enemy_weight.get("meteor", 1.0) if theme else 1.0
            meteor_weight = _get_progressive_enemy_weight(
                "meteor", meteor_weight, stage_progress
            )
            # CITY tem linhagem própria (Inimigos_Tema_Cidade) e bane Meteor no
            # allowlist — não injeta meteoro emprestado só p/ ser descartado depois.
            if meteor_weight > 0.0 and world.theme != WorldTheme.CITY:
                base_meteor_time = (
                    DifficultyConfig.BASE_METEOR_SPAWN_TIME / difficulty
                ) / spawn_multiplier
                enemy_spawn_config[Meteor] = self._clamp_spawn_time(
                    base_meteor_time * (2.0 / meteor_weight)
                )

            if world.theme not in _STAGE_BANDED_THEMES:
                if level_number >= 2:
                    alien_weight = (
                        theme.enemy_weight.get("alien", 1.0) if theme else 1.0
                    )
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

                if level_number >= 3:
                    square_weight = (
                        theme.enemy_weight.get("square_minion_boss", 0.1)
                        if theme
                        else 0.1
                    )
                    square_weight = _get_progressive_enemy_weight(
                        "square_minion_boss", square_weight, stage_progress
                    )
                    if square_weight > 0.0:
                        base_square_time = (8.0 / difficulty) / spawn_multiplier
                        enemy_spawn_config[SquareMinionBoss] = self._clamp_spawn_time(
                            base_square_time * (2.0 / square_weight)
                        )

            if world.theme == WorldTheme.MOUNTAINS:
                self._configure_mountains_spawn(
                    enemy_spawn_config,
                    stage_progress,
                    stage_number,
                    difficulty,
                    spawn_multiplier,
                )

            if world.theme == WorldTheme.CITY:
                self._configure_city_spawn(
                    enemy_spawn_config, stage_progress, difficulty, spawn_multiplier
                )

            # CITY está em _STAGE_BANDED_THEMES só pela lógica de formações; a
            # linhagem própria já é montada em _configure_city_spawn. Pular o
            # stage_banded evita injetar Alien/Eye/Square que o allowlist removeria.
            if world.theme in _STAGE_BANDED_THEMES and world.theme != WorldTheme.CITY:
                self._configure_stage_banded_spawn(
                    enemy_spawn_config,
                    stage_progress,
                    stage_number,
                    difficulty,
                    spawn_multiplier,
                )

            if world.theme == WorldTheme.STARFIELD:
                self._configure_starfield_spawn(
                    enemy_spawn_config,
                    stage_progress,
                    stage_number,
                    difficulty,
                    spawn_multiplier,
                )

        curve = DifficultyConfig.ENEMY_COUNT_CURVE
        if curve == "square_root":
            base_enemies = DifficultyConfig.BASE_ENEMIES + int(
                math.sqrt(level_number) * 15
            )
        elif curve == "logarithmic":
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

        mines_enabled = False
        formations_enabled = False

        if theme and theme.special_feature in ("meteor_only", "rock_glider_only"):
            pass
        else:
            if level_number >= DifficultyConfig.MINES_UNLOCK_LEVEL:
                if theme and theme.special_feature == "mines_heavy":
                    mines_enabled = True
                else:
                    mines_enabled = rng.random() < DifficultyConfig.MINES_PROBABILITY

            formations_enabled = (
                level_number >= DifficultyConfig.FORMATIONS_UNLOCK_LEVEL
                and "formations" in THEME_FEATURES.get(world.theme, set())
            )
            if world.theme in _STAGE_BANDED_THEMES:
                if stage_progress < 0.45:
                    formations_enabled = False
                elif stage_progress < 0.70:
                    formations_enabled = formations_enabled and rng.random() < 0.5

            if theme and theme.special_feature == "formations_heavy":
                formations_enabled = True

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
            elif world.theme in _STAGE_BANDED_THEMES and stage_progress < 0.70:
                formation_types = ["spiral_circle", "spiral_v"]
            elif level_number >= 6:
                formation_types = all_formations
            else:
                num_formations = rng.randint(3, 4)
                formation_types = rng.sample(all_formations, num_formations)

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
            storm_kind=(
                "meteor"
                if theme and theme.special_feature == "meteor_only"
                else (
                    "rock_glider"
                    if theme and theme.special_feature == "rock_glider_only"
                    else None
                )
            ),
        )
