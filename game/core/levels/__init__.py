"""Pacote `core.levels` — API pública de configuração de níveis.

Estrutura: a implementação atual vive em `_legacy.py` (snapshot do antigo
`core/levels.py` monolítico). Este `__init__.py` apenas reexporta o contrato
público para que callers continuem usando `from game.core.levels import X`.

Split por domínio (`fixed_levels`, `procedural`, `pipeline`, `analysis`)
fica como follow-up — separar internamente sem mudar a fronteira do pacote.
"""

from ._legacy import (
    # Tipos centrais
    EnemySpawnConfig,
    LevelConfig,
    LevelTheme,
    LEVEL_THEMES,
    # Dados fixos
    FIXED_LEVELS,
    # Procedural / Dificuldade
    DifficultyConfig,
    DifficultyCurves,
    ProceduralLevelGenerator,
    # Pipeline
    get_level_config,
    calculate_dynamic_enemy_cap,
    # Análise / Management
    LevelAnalyzer,
    LevelManager,
    # Constantes consumidas externamente
    THEME_ENEMY_REPLACEMENTS,
    THEME_FEATURES,
    THEME_FALLBACK_ENEMIES,
    THEME_BASE_ENEMY,
    ENEMY_THEME_ALLOWLIST,
    DEFAULT_ENEMY_SPAWN_TIME,
    MAX_ENEMY_VARIETY_BY_DIFFICULTY,
    MAX_ENEMY_VARIETY_BY_STAGE,
    # Re-export de difficulty (usado em código legacy)
    DifficultyPreset,
    DifficultySettings,
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
    "THEME_BASE_ENEMY",
    "ENEMY_THEME_ALLOWLIST",
    "DEFAULT_ENEMY_SPAWN_TIME",
    "MAX_ENEMY_VARIETY_BY_DIFFICULTY",
    "MAX_ENEMY_VARIETY_BY_STAGE",
    "DifficultyPreset",
    "DifficultySettings",
]
