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
from ...entities.giant_meteor_boss import GiantMeteorBoss
from ...entities.meteor import Meteor
from ...entities.mountain_mage import MountainMage
from ...entities.mountain_propeller import MountainPropeller
from ...entities.rock_glider import RockGlider
from ...entities.square_minion_boss import SquareMinionBoss
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
    WorldTheme.CITY: {"formations", "mines", "guided_meteors"},
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
    }

    DIFFICULTY_SCALING: float = 0.15
    MAX_DIFFICULTY_MULTIPLIER: float = 2.5

    # Limite total de inimigos simultâneos por dificuldade
    DIFFICULTY_TOTAL_ENEMY_CAPS: dict[DifficultyPreset, int] = {
        DifficultyPreset.CASUAL: 15,
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

    def _configure_mountains_spawn(
        self,
        enemy_spawn_config: EnemySpawnConfig,
        stage_progress: float,
        difficulty: float,
        spawn_multiplier: float,
    ) -> None:
        """Configura spawn de MountainMage/Propeller/StoneSentry/ElementalRobot."""
        if stage_progress >= 0.15:
            if stage_progress < 0.40:
                mage_base_time = 22.0
            elif stage_progress < 0.70:
                mage_base_time = 14.0
            else:
                mage_base_time = 10.0
            enemy_spawn_config[MountainMage] = self._clamp_spawn_time(
                (mage_base_time / difficulty) / spawn_multiplier
            )

        if stage_progress >= 0.35:
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

    def _configure_stage_banded_spawn(
        self,
        enemy_spawn_config: EnemySpawnConfig,
        stage_progress: float,
        difficulty: float,
        spawn_multiplier: float,
    ) -> None:
        """Configura Alien/EyeEnemy/SquareMinionBoss por bandas de stage_progress."""
        if stage_progress < 0.22:
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

        if stage_progress < 0.45:
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
            if meteor_weight > 0.0:
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
                    enemy_spawn_config, stage_progress, difficulty, spawn_multiplier
                )

            if world.theme == WorldTheme.CITY:
                self._configure_city_spawn(
                    enemy_spawn_config, stage_progress, difficulty, spawn_multiplier
                )

            if world.theme in _STAGE_BANDED_THEMES:
                self._configure_stage_banded_spawn(
                    enemy_spawn_config, stage_progress, difficulty, spawn_multiplier
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
