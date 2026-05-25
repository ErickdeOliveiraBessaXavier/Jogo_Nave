"""Inspeção e gerenciamento de níveis.

Contém:
  - `LevelManager`: fachada com método `get_level()` que delega a `get_level_config`.
  - `LevelAnalyzer`: estatísticas, estimativas e análise comparativa de níveis.
"""

from __future__ import annotations

import logging

from ..difficulty import DifficultyPreset
from .fixed_levels import LevelConfig
from .pipeline import get_level_config
from .procedural import ProceduralLevelGenerator

logger = logging.getLogger(__name__)


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
        player_count: int = 1,
    ) -> LevelConfig:
        """Retorna a configuração de um nível com dificuldade aplicada."""
        return get_level_config(
            level_number, difficulty_preset, player_count=player_count
        )


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

        spawn_rate = LevelAnalyzer.estimate_spawn_rate(config)
        if spawn_rate <= 0:
            return 0.0
        avg_inter_spawn = 1.0 / spawn_rate
        return (config.enemies_to_clear / 0.8) * avg_inter_spawn

    @staticmethod
    def estimate_spawn_rate(config: LevelConfig) -> float:
        """Estima taxa de spawn total (inimigos por segundo)."""
        if not config.enemy_spawn_config:
            return 0.0

        total_rate = sum(
            1.0 / spawn_time for spawn_time in config.enemy_spawn_config.values()
        )
        return total_rate

    @staticmethod
    def estimate_max_enemies_on_screen(config: LevelConfig) -> int:
        """Estima número máximo provável de inimigos na tela simultaneamente."""
        spawn_rate = LevelAnalyzer.estimate_spawn_rate(config)
        avg_lifetime = 5.0
        return int(spawn_rate * avg_lifetime)

    @staticmethod
    def print_level_progression(
        start: int, end: int, generator: ProceduralLevelGenerator
    ):
        """Imprime progressão de dificuldade para análise."""
        logger.info("\n%s", "=" * 80)
        logger.info("ANALISE DE PROGRESSAO: Niveis %s a %s", start, end)
        logger.info("%s\n", "=" * 80)

        for level_num in range(start, end + 1):
            config = generator.generate_level(level_num)
            stats = LevelAnalyzer.analyze_level(config)
            duration = LevelAnalyzer.estimate_duration(config)

            features = ""
            if stats["has_boss"]:
                features += "B"
            if stats["mines"]:
                features += "M"
            if stats["formations"]:
                features += "F"

            theme_name = config.theme_name or "N/A"
            spawn_rate = LevelAnalyzer.estimate_spawn_rate(config)
            max_enemies = LevelAnalyzer.estimate_max_enemies_on_screen(config)
            warnings = config.validate_sanity()

            warning_icon = "!" if warnings else "ok"

            logger.info(
                "%s Nv.%2d | %-22s | %3d | %.1f/s | ~%2d tela | %.1fmin | %-5s",
                warning_icon,
                level_num,
                theme_name,
                stats["enemies_to_clear"],
                spawn_rate,
                max_enemies,
                duration / 60,
                features,
            )

            if warnings:
                for warning in warnings:
                    logger.info("    -> %s", warning)
