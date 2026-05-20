"""Serviços e formatadores derivados de PlayerProfile.

Mantém PlayerProfile focado em estado + persistência. Isola aqui:
- aplicação de ajuste dinâmico de dificuldade (MetaProgressionService)
- formatação de strings/dicts para UI (ProfileStatsFormatter)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict

from .levels import LevelConfig
from .meta_progression import DifficultyAdjuster, PerformanceAnalyzer

if TYPE_CHECKING:
    from .meta_progression import PlayerProfile

logger = logging.getLogger(__name__)


class MetaProgressionService:
    """Application service: aplica ajuste dinâmico de dificuldade por histórico."""

    @staticmethod
    def get_adjusted_config(
        profile: "PlayerProfile", base_config: LevelConfig
    ) -> LevelConfig:
        """Retorna LevelConfig ajustado baseado na performance histórica do jogador."""
        level_num = base_config.level_number

        if level_num not in profile.level_stats:
            return base_config

        stats = profile.level_stats[level_num]
        analysis = PerformanceAnalyzer.analyze_level_performance(stats)
        previous_adjustment = profile.level_adjustments.get(level_num, 1.0)

        adjusted_config, new_adjustment = DifficultyAdjuster.apply_adjustment(
            base_config, analysis, previous_adjustment
        )

        if new_adjustment != previous_adjustment:
            profile.record_level_adjustment(level_num, new_adjustment)
            direction = "mais fácil" if new_adjustment < 1.0 else "mais difícil"
            logger.info(
                "[Meta-Progression] Level %s ajustado %.0f%% %s",
                level_num,
                abs(new_adjustment - 1.0) * 100,
                direction,
            )
            logger.info("  Motivo: %s", analysis["reason"])

        return adjusted_config


class ProfileStatsFormatter:
    """Formatação de dicts/strings de estatísticas para consumo pela UI."""

    @staticmethod
    def skill_level(profile: "PlayerProfile") -> str:
        """Retorna o skill level atual do jogador."""
        if not profile.level_stats:
            return "Novato"
        return profile.get_global_stats()["skill_level"]

    @staticmethod
    def statistics_summary(profile: "PlayerProfile") -> Dict[str, Any]:
        """Retorna resumo completo de estatísticas para exibição."""
        analysis = profile.get_global_stats()
        return {
            "skill_level": analysis["skill_level"],
            "highest_level": profile.highest_level_reached,
            "total_playtime_hours": profile.total_playtime / 3600,
            "total_deaths": profile.total_deaths,
            "total_score": profile.total_score,
            "avg_clear_rate": analysis["avg_clear_rate"],
            "overall_trend": analysis["overall_trend"],
            "levels_played": len(profile.level_stats),
            "recommendations": analysis["recommendations"],
            "sessions_played": len(profile.session_history),
        }
