"""Pacote `core.levels` — API pública de configuração de níveis.

Estrutura interna após split:
  - `fixed_levels.py`  — Tipos centrais (LevelConfig, LevelTheme), LEVEL_THEMES, FIXED_LEVELS.
  - `procedural.py`    — DifficultyConfig, DifficultyCurves, ProceduralLevelGenerator,
                         calculate_dynamic_enemy_cap, THEME_FEATURES, helpers de pressão.
  - `pipeline.py`      — Regras de tema (ENEMY_THEME_*, MAX_VARIETY_*, etc.),
                         `_THEME_RULES_PIPELINE`, `get_level_config`, grace e coop scaling.
  - `analysis.py`      — LevelManager, LevelAnalyzer.

`__init__.py` reexporta o contrato público — callers continuam usando
`from game.core.levels import X`.
"""

from ..difficulty import DifficultyPreset, DifficultySettings
from .analysis import LevelAnalyzer, LevelManager
from .fixed_levels import (
    EnemySpawnConfig,
    FIXED_LEVELS,
    LEVEL_THEMES,
    LevelConfig,
    LevelTheme,
)
from .pipeline import (
    DEFAULT_ENEMY_SPAWN_TIME,
    ENEMY_THEME_ALLOWLIST,
    MAX_ENEMY_VARIETY_BY_DIFFICULTY,
    MAX_ENEMY_VARIETY_BY_STAGE,
    THEME_BASE_ENEMY,
    THEME_ENEMY_REPLACEMENTS,
    THEME_FALLBACK_ENEMIES,
    get_level_config,
)
from .procedural import (
    THEME_FEATURES,
    DifficultyConfig,
    DifficultyCurves,
    ProceduralLevelGenerator,
    calculate_dynamic_enemy_cap,
)

__all__ = [
    "EnemySpawnConfig",
    "LevelConfig",
    "LevelTheme",
    "LEVEL_THEMES",
    "FIXED_LEVELS",
    "DifficultyConfig",
    "DifficultyCurves",
    "ProceduralLevelGenerator",
    "get_level_config",
    "calculate_dynamic_enemy_cap",
    "LevelAnalyzer",
    "LevelManager",
    "THEME_ENEMY_REPLACEMENTS",
    "THEME_FEATURES",
    "THEME_FALLBACK_ENEMIES",
    "ENEMY_THEME_ALLOWLIST",
    "DEFAULT_ENEMY_SPAWN_TIME",
    "MAX_ENEMY_VARIETY_BY_DIFFICULTY",
    "MAX_ENEMY_VARIETY_BY_STAGE",
    "THEME_BASE_ENEMY",
    "DifficultyPreset",
    "DifficultySettings",
]
