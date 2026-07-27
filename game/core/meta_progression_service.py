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
    def resolve_level_config(
        profile: "PlayerProfile", base_config: LevelConfig
    ) -> LevelConfig:
        """Resolve o `LevelConfig` da fase pela performance histórica do jogador.

        **Query pura**: não escreve no perfil e não depende de quantas vezes foi
        chamada. Pode ser usada livremente para preview/UI/debug.

        Isso é um contrato, não um detalhe. A versão anterior avançava e
        persistia um multiplicador A CADA chamada, então o número de chamadas
        virava parte do estado do jogo — ver `DifficultyAdjuster`.
        """
        stats = profile.level_stats.get(base_config.level_number)
        if stats is None:
            return base_config

        multiplier = DifficultyAdjuster.multiplier_for(
            stats,
            allow_hardening=DifficultyAdjuster.hardening_allowed(
                base_config.level_number, profile.highest_level_reached
            ),
        )
        if DifficultyAdjuster.is_neutral(multiplier):
            return base_config

        direction = "mais fácil" if multiplier < 1.0 else "mais difícil"
        logger.info(
            "[Meta-Progression] Level %s: %.0f%% %s (%s)",
            base_config.level_number,
            abs(multiplier - 1.0) * 100,
            direction,
            PerformanceAnalyzer.analyze_level_performance(stats)["reason"],
        )
        return DifficultyAdjuster.apply_to_config(base_config, multiplier)


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
