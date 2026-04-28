import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pygame

from .difficulty import DifficultyPreset
from .levels import DifficultyConfig, LevelConfig
from .upgrades import UpgradeType
from .upgrades_config import (DEFAULT_UNLOCKED, INITIAL_UNLOCKED_SLOTS,
                              UPGRADE_SLOT_COUNT)

logger = logging.getLogger(__name__)


class PerformanceState(Enum):
    """Estados de performance do jogador."""

    STRUGGLING = "struggling"  # Dificuldade excessiva
    LEARNING = "learning"  # Progresso normal
    COMFORTABLE = "comfortable"  # Zona de conforto
    DOMINATING = "dominating"  # Fácil demais
    INCONSISTENT = "inconsistent"  # Resultados variados


@dataclass
class SessionStats:
    """Estatísticas de uma sessão de jogo."""

    start_time: datetime
    end_time: Optional[datetime] = None
    levels_attempted: List[int] = field(default_factory=lambda: [])
    deaths: int = 0
    score: int = 0
    powerups_collected: int = 0

    @property
    def duration(self) -> float:
        """Duração da sessão em segundos."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return (datetime.now() - self.start_time).total_seconds()


@dataclass
class LevelPerformance:
    """Estatísticas detalhadas de performance em um nível."""

    level_number: int

    # Contadores básicos
    attempts: int = 0
    clears: int = 0
    deaths: int = 0

    # Tempo
    total_time: float = 0.0
    best_time: Optional[float] = None  # Changed from float('inf') to None
    worst_time: float = 0.0

    # Score
    total_score: int = 0
    best_score: int = 0

    # Detalhes de gameplay
    total_enemies_killed: int = 0
    total_damage_taken: int = 0
    total_powerups_collected: int = 0

    # Histórico de tentativas (últimas 10)
    recent_attempts: List[Dict[str, Any]] = field(default_factory=lambda: [])

    # Timestamps
    first_played: Optional[datetime] = None
    last_played: Optional[datetime] = None

    # Streak (vitórias consecutivas)
    current_win_streak: int = 0
    best_win_streak: int = 0

    @property
    def clear_rate(self) -> float:
        """Taxa de sucesso (0.0 a 1.0)."""
        return self.clears / self.attempts if self.attempts > 0 else 0.0

    @property
    def avg_time(self) -> float:
        """Tempo médio de clear."""
        if self.clears <= 0:
            return 0.0
        avg = self.total_time / self.clears
        return avg if avg > 0 else 0.0

    @property
    def avg_score(self) -> float:
        """Score médio."""
        return self.total_score / self.clears if self.clears > 0 else 0.0

    @property
    def death_rate(self) -> float:
        """Mortes por tentativa."""
        return self.deaths / self.attempts if self.attempts > 0 else 0.0

    @property
    def improvement_trend(self) -> float:
        """
        Tendência de melhoria baseada nas últimas tentativas.
        Retorna valor entre -1.0 (piorando) e 1.0 (melhorando).
        """
        if len(self.recent_attempts) < 3:
            return 0.0

        # Comparar primeira metade vs segunda metade das tentativas recentes
        mid = len(self.recent_attempts) // 2
        first_half = self.recent_attempts[:mid]
        second_half = self.recent_attempts[mid:]

        first_success_rate = sum(
            1 for a in first_half if a.get("cleared", False)
        ) / len(first_half)
        second_success_rate = sum(
            1 for a in second_half if a.get("cleared", False)
        ) / len(second_half)

        return second_success_rate - first_success_rate

    def get_performance_state(self) -> PerformanceState:
        """Determina estado atual de performance."""
        if self.attempts < 2:
            return PerformanceState.LEARNING

        # Dificuldade excessiva
        if self.clear_rate < 0.3 and self.attempts >= 5:
            return PerformanceState.STRUGGLING

        # Dominando completamente
        if self.clear_rate > 0.9 and self.attempts >= 3:
            # Verificar consistência de tempos
            if self.clears >= 2 and self.best_time and self.avg_time > 0:
                time_consistency = self.best_time / self.avg_time
                if time_consistency > 0.8:  # Tempos consistentes
                    return PerformanceState.DOMINATING

        # Performance inconsistente
        if len(self.recent_attempts) >= 5:
            recent_variance = sum(
                1 for a in self.recent_attempts if a.get("cleared", False)
            )
            if 0.2 < recent_variance / len(self.recent_attempts) < 0.8:
                return PerformanceState.INCONSISTENT

        # Confortável (taxa de sucesso saudável)
        if 0.5 <= self.clear_rate <= 0.8:
            return PerformanceState.COMFORTABLE

        # Ainda aprendendo
        return PerformanceState.LEARNING


@dataclass
class WorldUnlockStatus:
    """Status de desbloqueio de um mundo."""

    world_id: int
    is_unlocked: bool
    first_accessed_at: Optional[datetime] = None
    last_best_score_at_checkpoint: int = 0
    checkpoint_set: bool = False


class PerformanceAnalyzer:
    """Analisa padrões de performance e sugere ajustes."""

    # Configuração de sensibilidade
    STRUGGLE_THRESHOLD = 0.35  # Clear rate abaixo disso = struggling
    DOMINATE_THRESHOLD = 0.85  # Clear rate acima disso = dominating
    MIN_ATTEMPTS_FOR_ANALYSIS = 3  # Mínimo de tentativas para análise

    RECENT_ATTEMPTS_WINDOW = 10  # Quantas tentativas recentes considerar
    IMPROVEMENT_THRESHOLD = 0.2  # Melhoria mínima para considerar progresso

    @staticmethod
    def analyze_level_performance(stats: LevelPerformance) -> Dict[str, Any]:
        """
        Análise completa de performance em um nível.

        Returns:
            Dict com diagnóstico e recomendações de ajuste
        """
        if stats.attempts < PerformanceAnalyzer.MIN_ATTEMPTS_FOR_ANALYSIS:
            return {
                "state": PerformanceState.LEARNING,
                "adjustment": 1.0,  # Sem ajuste
                "confidence": "low",
                "reason": "Dados insuficientes",
            }

        state = stats.get_performance_state()
        adjustment = 1.0
        confidence = "medium"
        reason = ""

        # Análise baseada no estado
        if state == PerformanceState.STRUGGLING:
            # Verificar tendência de melhoria
            if stats.improvement_trend > PerformanceAnalyzer.IMPROVEMENT_THRESHOLD:
                # Jogador está melhorando, dar mais tempo
                adjustment = 0.95  # Facilitar sutilmente (5%)
                confidence = "low"
                reason = "Lutando mas melhorando - ajuste mínimo"
            else:
                # Sem melhoria, facilitar mais
                adjustment = 0.85  # Facilitar moderadamente (15%)
                confidence = "high"
                reason = f"Clear rate baixo ({stats.clear_rate:.0%}) sem melhoria"

        elif state == PerformanceState.DOMINATING:
            # Verificar se é consistente
            if stats.current_win_streak >= 3:
                adjustment = 1.15  # Dificultar (15%)
                confidence = "high"
                reason = f"Dominando ({stats.clear_rate:.0%}) com {stats.current_win_streak} vitórias consecutivas"
            else:
                adjustment = 1.08  # Dificultar levemente (8%)
                confidence = "medium"
                reason = f"Clear rate alto ({stats.clear_rate:.0%})"

        elif state == PerformanceState.INCONSISTENT:
            # Manter estável, pode ser o nível que é inconsistente
            adjustment = 1.0
            confidence = "low"
            reason = "Performance inconsistente - mantendo dificuldade"

        elif state == PerformanceState.COMFORTABLE:
            # Sweet spot! Não mexer
            adjustment = 1.0
            confidence = "high"
            reason = f"Performance ideal ({stats.clear_rate:.0%})"

        return {
            "state": state,
            "adjustment": adjustment,
            "confidence": confidence,
            "reason": reason,
            "clear_rate": stats.clear_rate,
            "attempts": stats.attempts,
            "trend": stats.improvement_trend,
        }

    @staticmethod
    def analyze_global_performance(profile: "PlayerProfile") -> Dict[str, Any]:
        """
        Análise global do perfil do jogador.

        Identifica padrões gerais de skill level e progressão.
        """
        if not profile.level_stats:
            return {
                "skill_level": "Novato",
                "overall_trend": "neutral",
                "avg_clear_rate": 0.0,
                "recommendations": [],
            }

        # Calcular métricas globais
        total_attempts = sum(s.attempts for s in profile.level_stats.values())
        total_clears = sum(s.clears for s in profile.level_stats.values())
        avg_clear_rate = total_clears / total_attempts if total_attempts > 0 else 0.0

        # Determinar skill level
        skill_level = PerformanceAnalyzer._determine_skill_level(
            profile.highest_level_reached, avg_clear_rate, profile.total_playtime
        )

        # Analisar tendência geral
        recent_levels = sorted(profile.level_stats.keys())[-5:]  # Últimos 5 níveis
        if len(recent_levels) >= 3:
            recent_clear_rates = [
                profile.level_stats[lv].clear_rate for lv in recent_levels
            ]
            overall_trend = PerformanceAnalyzer._calculate_trend(recent_clear_rates)
        else:
            overall_trend = "neutral"

        # Gerar recomendações
        recommendations = PerformanceAnalyzer._generate_recommendations(
            profile, skill_level, overall_trend
        )

        return {
            "skill_level": skill_level,
            "overall_trend": overall_trend,
            "avg_clear_rate": avg_clear_rate,
            "total_playtime_hours": profile.total_playtime / 3600,
            "recommendations": recommendations,
        }

    @staticmethod
    def _determine_skill_level(
        highest_level: int, clear_rate: float, playtime: float
    ) -> str:
        """Determina skill level baseado em múltiplos fatores."""
        # Sistema de pontos ponderado
        level_points = min(highest_level * 1.5, 40)  # Max 40 pontos
        clear_rate_points = clear_rate * 40  # Max 40 pontos
        experience_points = min(playtime / 3600 * 4, 20)  # Max 20 pontos

        total_points = level_points + clear_rate_points + experience_points

        if total_points < 20:
            return "Novato"
        if total_points < 40:
            return "Aprendiz"
        if total_points < 60:
            return "Intermediário"
        if total_points < 80:
            return "Avançado"
        if total_points < 90:
            return "Veterano"
        return "Mestre"

    @staticmethod
    def _calculate_trend(values: List[float]) -> str:
        """Calcula tendência de uma série de valores."""
        if len(values) < 2:
            return "neutral"

        # Regressão linear simples
        n = len(values)
        x_avg = (n - 1) / 2
        y_avg = sum(values) / n

        numerator = sum((i - x_avg) * (values[i] - y_avg) for i in range(n))
        denominator = sum((i - x_avg) ** 2 for i in range(n))

        if denominator == 0:
            return "neutral"

        slope = numerator / denominator

        if slope > 0.05:
            return "improving"
        if slope < -0.05:
            return "declining"
        return "stable"

    @staticmethod
    def _generate_recommendations(
        profile: "PlayerProfile", skill_level: str, trend: str
    ) -> List[str]:
        """Gera recomendações personalizadas."""
        recommendations: List[str] = []

        # Recomendações baseadas em skill level
        if skill_level in ["Novato", "Aprendiz"]:
            recommendations.append(
                "💡 Dica: Colete power-ups de escudo para sobreviver mais tempo"
            )
            recommendations.append("🎯 Foque em desviar antes de atirar")

        # Recomendações baseadas em tendência
        if trend == "declining":
            recommendations.append(
                "⚠️ Notamos dificuldade recente. Considere fazer uma pausa!"
            )
            recommendations.append("🔄 Tente revisitar níveis anteriores para praticar")
        elif trend == "improving":
            recommendations.append("📈 Excelente progresso! Continue assim!")

        # Recomendações baseadas em padrões específicos
        struggling_levels = [
            lv
            for lv, stats in profile.level_stats.items()
            if stats.attempts >= 5 and stats.clear_rate < 0.3
        ]

        if struggling_levels:
            recommendations.append(
                f"🎮 Níveis desafiadores: {', '.join(map(str, struggling_levels[:3]))}. "
                "Dificuldade foi ajustada sutilmente."
            )

        return recommendations


class DifficultyAdjuster:
    """Aplica ajustes adaptativos à configuração de níveis."""

    # Limites de ajuste para evitar extremos
    MIN_ADJUSTMENT = 0.75  # Máximo 25% mais fácil
    MAX_ADJUSTMENT = 1.25  # Máximo 25% mais difícil

    # Velocidade de ajuste (quão rápido o sistema adapta)
    ADJUSTMENT_SPEED = 0.5  # 50% do ajuste sugerido por tentativa

    @staticmethod
    def apply_adjustment(
        base_config: LevelConfig,
        analysis: Dict[str, Any],
        previous_adjustment: float = 1.0,
    ) -> tuple[LevelConfig, float]:
        """
        Aplica ajuste adaptativo à configuração do nível.

        Args:
            base_config: Configuração base do nível
            analysis: Resultado da análise de performance
            previous_adjustment: Ajuste anterior aplicado (para suavizar transições)

        Returns:
            Tupla com (config ajustada, novo multiplicador)
        """
        suggested_adjustment = analysis["adjustment"]
        confidence = analysis["confidence"]

        # Não ajustar se confiança for baixa (dados insuficientes)
        if confidence == "low":
            return base_config, 1.0

        # Suavizar ajuste baseado em confiança
        if confidence == "medium":
            adjustment_factor = 0.6  # 60% do ajuste sugerido
        else:  # high
            adjustment_factor = 1.0  # Ajuste completo

        # Interpolar entre ajuste anterior e novo ajuste
        target_adjustment = suggested_adjustment * adjustment_factor
        new_adjustment = (
            previous_adjustment
            + (target_adjustment - previous_adjustment)
            * DifficultyAdjuster.ADJUSTMENT_SPEED
        )

        # Aplicar limites
        new_adjustment = max(
            DifficultyAdjuster.MIN_ADJUSTMENT,
            min(DifficultyAdjuster.MAX_ADJUSTMENT, new_adjustment),
        )

        # Se o ajuste é muito próximo de 1.0, não aplicar
        if 0.98 <= new_adjustment <= 1.02:
            return base_config, 1.0

        # Aplicar ajuste à configuração
        adjusted_config = DifficultyAdjuster._apply_to_config(
            base_config, new_adjustment
        )

        return adjusted_config, new_adjustment

    @staticmethod
    def _apply_to_config(config: LevelConfig, multiplier: float) -> LevelConfig:
        """Aplica multiplicador à configuração do nível."""
        # Ajustar spawn times (inverso do multiplier)
        adjusted_spawn_config: Dict[Any, float] = {}
        for enemy_type, spawn_time in config.enemy_spawn_config.items():
            # Multiplicador maior = mais difícil = spawn mais rápido
            adjusted_time = spawn_time / multiplier

            # Garantir mínimo jogável
            adjusted_time = max(DifficultyConfig.MIN_SPAWN_TIME, adjusted_time)

            adjusted_spawn_config[enemy_type] = adjusted_time

        # Ajustar quantidade de inimigos
        adjusted_enemies = int(config.enemies_to_clear * multiplier)
        adjusted_enemies = max(20, adjusted_enemies)  # Mínimo de 20 inimigos

        # Criar nova config
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


class PlayerProfile:
    """Perfil completo do jogador com meta-progression."""

    MAX_SESSION_HISTORY = 50  # Limit session history to last 50 sessions

    def _ensure_safe_world_defaults(self) -> None:
        """Garante estado mínimo seguro para mundos/checkpoint."""
        if 1 not in self.world_unlocks:
            self.world_unlocks[1] = WorldUnlockStatus(
                world_id=1,
                is_unlocked=True,
                first_accessed_at=datetime.now(),
                checkpoint_set=True,
            )
        self.current_checkpoint_world = 1

    def __init__(self, profile_path: Path):
        self.profile_path = profile_path

        # Estatísticas básicas
        self.level_stats: Dict[int, LevelPerformance] = {}
        self.total_playtime: float = 0.0
        self.highest_level_reached: int = 1
        self.total_deaths: int = 0
        self.total_score: int = 0

        # Sistema de mundos e savepoints
        self.world_unlocks: Dict[int, WorldUnlockStatus] = {}
        self.current_checkpoint_world: int = 1
        self.selected_world_id: int = 1  # Transient - não salvo

        # Sessão atual
        self.current_session: Optional[SessionStats] = None
        self.session_history: List[SessionStats] = []

        # Ajustes adaptativos por nível
        self.level_adjustments: Dict[int, float] = {}  # level_num -> multiplier

        # Preferências detectadas
        self.preferred_difficulty: Optional[DifficultyPreset] = None

        # Aprimoramentos (ativos)
        # Armazenamos como nomes de enum para JSON estável
        self.unlocked_upgrades: set[UpgradeType] = set(DEFAULT_UNLOCKED)
        self.upgrade_loadout: list[Optional[UpgradeType]] = [None] * UPGRADE_SLOT_COUNT

        # Sistema de estrelas (moedas)
        self.stars_collected: int = 0  # Total de estrelas coletadas
        self.stars_spent: int = 0  # Total de estrelas gastas
        self.unlocked_slots: int = (
            INITIAL_UNLOCKED_SLOTS  # Número de slots desbloqueados
        )

        # Teclas para ativar aprimoramentos (1-9), limitadas por UPGRADE_SLOT_COUNT
        default_keys: list[int] = [
            pygame.K_1,
            pygame.K_2,
            pygame.K_3,
            pygame.K_4,
            pygame.K_5,
            pygame.K_6,
            pygame.K_7,
            pygame.K_8,
            pygame.K_9,
        ]
        self.upgrade_keybindings: list[int] = default_keys[:UPGRADE_SLOT_COUNT]

        # Timestamps
        self.profile_created: datetime = datetime.now()
        self.last_played: Optional[datetime] = None

        # Save optimization
        self._dirty = False
        self._last_save = time.time()

        # Configurações de vídeo (inicializadas com defaults)
        self.resolution = (1280, 720)

        # Configurações de controle (inicializadas com defaults)
        self.mouse_control: bool = False
        self.auto_fire: bool = False

        # OPT #4: Cache global performance analysis
        self._cached_global_stats: Optional[Dict[str, Any]] = None
        self._stats_dirty = True

        self.load()

    # ============================================================================
    # SISTEMA DE MUNDOS E SAVEPOINTS
    # ============================================================================

    def unlock_next_world(self, current_world_id: int | None = None):
        """Desbloqueia o próximo mundo após completar o boss final do mundo atual."""
        if current_world_id is None:
            current_world_id = self.current_checkpoint_world
        next_world_id = current_world_id + 1

        # Máximo 4 mundos nomeados
        if next_world_id <= 4:
            if next_world_id not in self.world_unlocks:
                self.world_unlocks[next_world_id] = WorldUnlockStatus(
                    world_id=next_world_id,
                    is_unlocked=True,
                    first_accessed_at=datetime.now(),
                    checkpoint_set=False,
                )
            else:
                self.world_unlocks[next_world_id].is_unlocked = True
                if not self.world_unlocks[next_world_id].first_accessed_at:
                    self.world_unlocks[next_world_id].first_accessed_at = datetime.now()

            # Atualizar checkpoint para o novo mundo
            self.current_checkpoint_world = next_world_id
            self.save()
            logger.info(
                f"🌍 Mundo {next_world_id} desbloqueado! Checkpoint atualizado."
            )

    def set_checkpoint_on_level_start(self, level_number: int):
        """Chamado quando jogador inicia um novo nível - marca checkpoint se primeira vez neste mundo."""
        from .world_config import get_world_for_level

        world_config = get_world_for_level(level_number)

        # Se é primeira vez neste mundo, marcar como checkpoint
        if world_config.world_id not in self.world_unlocks:
            # Inicializar mundo se não existe
            self.world_unlocks[world_config.world_id] = WorldUnlockStatus(
                world_id=world_config.world_id,
                is_unlocked=True,
                first_accessed_at=datetime.now(),
                checkpoint_set=True,
            )
            self.current_checkpoint_world = world_config.world_id
            self.save()
            logger.info(
                f"🌍 Primeiro acesso ao Mundo {world_config.world_id} - checkpoint definido!"
            )
        elif not self.world_unlocks[world_config.world_id].checkpoint_set:
            # Já existe mas não era checkpoint ainda
            self.world_unlocks[world_config.world_id].checkpoint_set = True
            self.current_checkpoint_world = world_config.world_id
            self.save()
            logger.info(f"🌍 Checkpoint definido no Mundo {world_config.world_id}!")

    def reset_to_checkpoint(self) -> int:
        """Jogador perdeu: retorna nível inicial do mundo checkpoint atual."""
        from .world_config import get_world_for_level_by_id

        checkpoint_world = get_world_for_level_by_id(self.current_checkpoint_world)
        if checkpoint_world:
            # Resetar score da sessão atual
            if self.current_session:
                self.current_session.score = 0
                self.current_session.deaths += 1

            logger.info(
                f"💀 Reset para checkpoint: Mundo {checkpoint_world.world_id}, Nível {checkpoint_world.start_level}"
            )
            return checkpoint_world.start_level

        # Fallback para nível 1 se algo der errado
        logger.warning("Checkpoint inválido, fallback para nível 1")
        return 1

    def get_total_equipped_weight(self) -> int:
        """Retorna o peso total de todos os upgrades equipados."""
        from .upgrades import UPGRADES_META

        total_weight = 0
        for upgrade_type in self.upgrade_loadout:
            if upgrade_type is not None:
                meta = UPGRADES_META.get(upgrade_type)
                if meta:
                    total_weight += meta.slot_weight
        return total_weight

    def can_equip_upgrade(self, upgrade_type: UpgradeType, slot_index: int) -> bool:
        """
        Verifica se pode equipar um upgrade considerando o peso total.

        Returns:
            bool: True se pode equipar, False caso contrário
        """
        from .upgrades import UPGRADES_META

        # Verificar se o slot está desbloqueado
        if slot_index >= self.unlocked_slots:
            return False

        # Obter peso do novo upgrade
        meta = UPGRADES_META.get(upgrade_type)
        if not meta:
            return False

        new_weight = meta.slot_weight

        # Calcular peso atual sem o item do slot de destino
        current_weight = 0
        for i, equipped_type in enumerate(self.upgrade_loadout):
            if i != slot_index and equipped_type is not None:
                equipped_meta = UPGRADES_META.get(equipped_type)
                if equipped_meta:
                    current_weight += equipped_meta.slot_weight

        # Verificar se o peso total não excede o limite
        return (current_weight + new_weight) <= self.unlocked_slots

    def equip_upgrade(self, upgrade_type: Optional[UpgradeType], slot_index: int):
        """Equipa ou desequipa um aprimoramento em um slot específico."""
        if 0 <= slot_index < UPGRADE_SLOT_COUNT:
            self.upgrade_loadout[slot_index] = upgrade_type
            self._mark_dirty()

    def get_equipped_slot(self, upgrade_type: UpgradeType) -> Optional[int]:
        """Retorna o índice do slot onde um aprimoramento está equipado, ou None."""
        try:
            return self.upgrade_loadout.index(upgrade_type)
        except ValueError:
            return None

    def add_stars(self, amount: int) -> None:
        """Adiciona estrelas ao perfil do jogador."""
        self.stars_collected += amount
        self._mark_dirty()

    @property
    def available_stars(self) -> int:
        """Retorna o número de estrelas disponíveis (coletadas - gastas)."""
        return self.stars_collected - self.stars_spent

    def can_unlock_slot(self, slot_index: int) -> bool:
        """Verifica se o jogador pode desbloquear um slot específico."""
        from .upgrades_config import SLOT_UNLOCK_COSTS

        if slot_index < 0 or slot_index >= len(SLOT_UNLOCK_COSTS):
            return False

        # Já está desbloqueado
        if slot_index < self.unlocked_slots:
            return True

        # Precisa desbloquear slots anteriores primeiro
        if slot_index != self.unlocked_slots:
            return False

        # Verifica se tem estrelas suficientes
        cost = SLOT_UNLOCK_COSTS[slot_index]
        return self.available_stars >= cost

    def unlock_slot(self, slot_index: int) -> bool:
        """
        Desbloqueia um slot de upgrade.

        Returns:
            bool: True se desbloqueou com sucesso, False caso contrário
        """
        from .upgrades_config import SLOT_UNLOCK_COSTS

        if not self.can_unlock_slot(slot_index):
            return False

        cost = SLOT_UNLOCK_COSTS[slot_index]
        self.stars_spent += cost
        self.unlocked_slots = slot_index + 1
        self._mark_dirty()
        return True

    def get_slot_cost(self, slot_index: int) -> int:
        """Retorna o custo em estrelas para desbloquear um slot."""
        from .upgrades_config import SLOT_UNLOCK_COSTS

        if slot_index < 0 or slot_index >= len(SLOT_UNLOCK_COSTS):
            return 0
        return SLOT_UNLOCK_COSTS[slot_index]

    def start_session(self):
        """Inicia uma nova sessão de jogo."""
        self.current_session = SessionStats(start_time=datetime.now())

    def end_session(self):
        """Finaliza sessão atual."""
        if self.current_session:
            self.current_session.end_time = datetime.now()
            self.session_history.append(self.current_session)
            # Limit session history
            if len(self.session_history) > self.MAX_SESSION_HISTORY:
                self.session_history = self.session_history[-self.MAX_SESSION_HISTORY :]
            self.total_playtime += self.current_session.duration
            self.current_session = None
            self.save()  # Save on session end

    def _mark_dirty(self):
        """Mark profile as having unsaved changes."""
        self._dirty = True
        self._stats_dirty = True  # OPT #4: Invalidate cache when data changes
        self._cached_global_stats = None

    def get_global_stats(self) -> Dict[str, Any]:
        """OPT #4: Get cached global stats, recalculate only if dirty."""
        if self._cached_global_stats is None or self._stats_dirty:
            self._cached_global_stats = PerformanceAnalyzer.analyze_global_performance(
                self
            )
            self._stats_dirty = False
        return self._cached_global_stats

    def auto_save(self):
        """Auto-save if dirty and enough time has passed."""
        if self._dirty and (time.time() - self._last_save) > 10:
            self.save()

    def record_attempt(self, level_number: int):
        """Registra tentativa de um nível."""
        if level_number not in self.level_stats:
            self.level_stats[level_number] = LevelPerformance(level_number)
            self.level_stats[level_number].first_played = datetime.now()

        stats = self.level_stats[level_number]
        stats.attempts += 1
        stats.last_played = datetime.now()
        self.last_played = datetime.now()
        self._mark_dirty()

    def record_clear(
        self,
        level_number: int,
        time_taken: float,
        score: int,
        enemies_killed: int,
        damage_taken: int,
        powerups_collected: int,
    ):
        """Registra clear detalhado de um nível."""
        stats = self.level_stats[level_number]

        # Contadores
        stats.clears += 1
        stats.current_win_streak += 1
        stats.best_win_streak = max(stats.best_win_streak, stats.current_win_streak)

        # Tempo
        stats.total_time += time_taken
        if stats.best_time is None or time_taken < stats.best_time:
            stats.best_time = time_taken
        stats.worst_time = max(stats.worst_time, time_taken)

        # Score
        stats.total_score += score
        stats.best_score = max(stats.best_score, score)
        self.total_score += score

        # Gameplay
        stats.total_enemies_killed += enemies_killed
        stats.total_damage_taken += damage_taken
        stats.total_powerups_collected += powerups_collected

        # Histórico recente
        attempt_data: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "cleared": True,
            "time": time_taken,
            "score": score,
            "enemies": enemies_killed,
            "damage": damage_taken,
            "powerups": powerups_collected,
        }
        stats.recent_attempts.append(attempt_data)
        if len(stats.recent_attempts) > PerformanceAnalyzer.RECENT_ATTEMPTS_WINDOW:
            stats.recent_attempts.pop(0)

        # Atualizar progresso
        self.highest_level_reached = max(self.highest_level_reached, level_number + 1)

        # Sessão
        if self.current_session:
            self.current_session.score += score
            self.current_session.powerups_collected += powerups_collected

        self._mark_dirty()

        # Salvar a cada 5 níveis completados
        if level_number % 5 == 0:
            self.save()

    def record_death(self, level_number: int, cause: str = "unknown"):
        """Registra morte em um nível."""
        stats = self.level_stats[level_number]
        stats.deaths += 1
        stats.current_win_streak = 0  # Reset streak
        self.total_deaths += 1

        # Histórico recente
        attempt_data: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "cleared": False,
            "cause": cause,
        }
        stats.recent_attempts.append(attempt_data)
        if len(stats.recent_attempts) > PerformanceAnalyzer.RECENT_ATTEMPTS_WINDOW:
            stats.recent_attempts.pop(0)

        # Sessão
        if self.current_session:
            self.current_session.deaths += 1

        self._mark_dirty()

    def get_adjusted_config(self, base_config: LevelConfig) -> LevelConfig:
        """
        Obtém configuração ajustada para um nível.

        Sistema completo de meta-progression em ação.
        """
        level_num = base_config.level_number

        # Primeira tentativa - sem ajuste
        if level_num not in self.level_stats:
            return base_config

        # Analisar performance
        stats = self.level_stats[level_num]
        analysis = PerformanceAnalyzer.analyze_level_performance(stats)

        # Obter ajuste anterior (se houver)
        previous_adjustment = self.level_adjustments.get(level_num, 1.0)

        # Aplicar novo ajuste
        adjusted_config, new_adjustment = DifficultyAdjuster.apply_adjustment(
            base_config, analysis, previous_adjustment
        )

        # Salvar novo ajuste
        if new_adjustment != previous_adjustment:
            self.level_adjustments[level_num] = new_adjustment
            self._mark_dirty()

            # Log para debug
            direction = "mais fácil" if new_adjustment < 1.0 else "mais difícil"
            logging.info(
                f"[Meta-Progression] Level {level_num} ajustado {abs(new_adjustment - 1.0) * 100:.0f}% {direction}"
            )
            logging.info(f"  Motivo: {analysis['reason']}")

        return adjusted_config

    def get_skill_level(self) -> str:
        """Retorna skill level atual."""
        if not self.level_stats:
            return "Novato"

        analysis = self.get_global_stats()  # OPT #4: Use cached version
        return analysis["skill_level"]

    def get_statistics_summary(self) -> Dict[str, Any]:
        """Retorna resumo completo de estatísticas."""
        analysis = self.get_global_stats()  # OPT #4: Use cached version

        return {
            "skill_level": analysis["skill_level"],
            "highest_level": self.highest_level_reached,
            "total_playtime_hours": self.total_playtime / 3600,
            "total_deaths": self.total_deaths,
            "total_score": self.total_score,
            "avg_clear_rate": analysis["avg_clear_rate"],
            "overall_trend": analysis["overall_trend"],
            "levels_played": len(self.level_stats),
            "recommendations": analysis["recommendations"],
            "sessions_played": len(self.session_history),
        }

    def load(self):
        """Carrega perfil do disco."""
        if not self.profile_path.exists():
            # Garantir estado inicial consistente em perfil novo.
            self.world_unlocks = {}
            self._ensure_safe_world_defaults()
            return

        try:
            with open(self.profile_path, "r", encoding="utf-8") as f:
                data: Dict[str, Any] = json.load(f)

                # Validate basic structure
                if "level_stats" not in data:
                    raise ValueError("Invalid profile structure")

                # Dados básicos
                self.total_playtime = data.get("total_playtime", 0.0)
                self.highest_level_reached = data.get("highest_level_reached", 1)
                self.total_deaths = data.get("total_deaths", 0)
                self.total_score = data.get("total_score", 0)

                # Configurações de vídeo
                resolution_raw = data.get("resolution")
                if isinstance(resolution_raw, list):
                    from typing import cast

                    resolution_list = cast(List[Any], resolution_raw)
                    if len(resolution_list) == 2:
                        self.resolution = (
                            int(resolution_list[0]),
                            int(resolution_list[1]),
                        )
                    else:
                        self.resolution = (1280, 720)  # Default
                else:
                    self.resolution = (1280, 720)  # Default

                # Configurações de controle
                self.mouse_control = data.get("mouse_control", False)
                self.auto_fire = data.get("auto_fire", False)

                # Star collection system
                self.stars_collected = data.get("stars_collected", 0)
                self.stars_spent = data.get("stars_spent", 0)
                self.unlocked_slots = data.get("unlocked_slots", INITIAL_UNLOCKED_SLOTS)

                # Sistema de mundos e savepoints
                world_unlocks_raw_untyped = data.get("world_unlocks", {})
                world_unlocks_raw: Dict[str, Dict[str, Any]] = {}
                if isinstance(world_unlocks_raw_untyped, dict):
                    from typing import cast

                    world_unlocks_dict = cast(
                        Dict[Any, Any],
                        world_unlocks_raw_untyped,
                    )
                    for world_id_key, world_data_value in world_unlocks_dict.items():
                        if isinstance(world_id_key, str) and isinstance(
                            world_data_value, dict
                        ):
                            world_unlocks_raw[world_id_key] = world_data_value
                for world_id_str, world_data_raw in world_unlocks_raw.items():
                    world_data: Dict[str, Any] = world_data_raw
                    try:
                        world_id = int(world_id_str)
                        status = WorldUnlockStatus(
                            world_id=world_id,
                            is_unlocked=world_data.get("is_unlocked", False),
                            first_accessed_at=(
                                datetime.fromisoformat(world_data["first_accessed_at"])
                                if world_data.get("first_accessed_at")
                                else None
                            ),
                            last_best_score_at_checkpoint=world_data.get(
                                "last_best_score_at_checkpoint", 0
                            ),
                            checkpoint_set=world_data.get("checkpoint_set", False),
                        )
                        self.world_unlocks[world_id] = status
                    except (ValueError, TypeError, KeyError):
                        logger.warning(
                            f"Skipping corrupt world data for world {world_id_str}"
                        )
                        continue

                # Inicializar mundo 1 se não existir (mundo padrão sempre desbloqueado)
                if 1 not in self.world_unlocks:
                    self.world_unlocks[1] = WorldUnlockStatus(
                        world_id=1,
                        is_unlocked=True,
                        first_accessed_at=datetime.now(),
                        checkpoint_set=True,
                    )

                checkpoint_raw = data.get("current_checkpoint_world", 1)
                self.current_checkpoint_world = (
                    int(checkpoint_raw)
                    if isinstance(checkpoint_raw, (int, float, str))
                    and str(checkpoint_raw).isdigit()
                    else 1
                )
                if self.current_checkpoint_world not in self.world_unlocks:
                    self.current_checkpoint_world = 1

                # Se o checkpoint carregado estiver inválido/corrompido, forçar Mundo 1.
                from .world_config import get_world_for_level_by_id

                if get_world_for_level_by_id(self.current_checkpoint_world) is None:
                    self.current_checkpoint_world = 1

                # Timestamps
                if "profile_created" in data and isinstance(
                    data["profile_created"], str
                ):
                    self.profile_created = datetime.fromisoformat(
                        data["profile_created"]
                    )
                if data.get("last_played") and isinstance(data["last_played"], str):
                    self.last_played = datetime.fromisoformat(data["last_played"])

                # Level stats
                level_stats_raw: Dict[str, Dict[str, Any]] = data.get("level_stats", {})
                for level_num_str, stats_data_raw in level_stats_raw.items():
                    stats_data: Dict[str, Any] = stats_data_raw
                    try:
                        level_num = int(level_num_str)
                        stats = LevelPerformance(level_number=level_num)

                        # Restore fields explicitly for type safety
                        stats.attempts = int(stats_data.get("attempts", 0))
                        stats.clears = int(stats_data.get("clears", 0))
                        stats.deaths = int(stats_data.get("deaths", 0))
                        stats.total_time = float(stats_data.get("total_time", 0.0))
                        stats.best_time = (
                            float(stats_data["best_time"])
                            if isinstance(stats_data.get("best_time"), (int, float))
                            else None
                        )
                        stats.worst_time = float(stats_data.get("worst_time", 0.0))
                        stats.total_score = int(stats_data.get("total_score", 0))
                        stats.best_score = int(stats_data.get("best_score", 0))
                        stats.total_enemies_killed = int(
                            stats_data.get("total_enemies_killed", 0)
                        )
                        stats.total_damage_taken = int(
                            stats_data.get("total_damage_taken", 0)
                        )
                        stats.total_powerups_collected = int(
                            stats_data.get("total_powerups_collected", 0)
                        )
                        stats.recent_attempts = stats_data.get("recent_attempts", [])
                        stats.current_win_streak = int(
                            stats_data.get("current_win_streak", 0)
                        )
                        stats.best_win_streak = int(
                            stats_data.get("best_win_streak", 0)
                        )

                        if "first_played" in stats_data and isinstance(
                            stats_data["first_played"], str
                        ):
                            stats.first_played = datetime.fromisoformat(
                                stats_data["first_played"]
                            )
                        if "last_played" in stats_data and isinstance(
                            stats_data["last_played"], str
                        ):
                            stats.last_played = datetime.fromisoformat(
                                stats_data["last_played"]
                            )

                        self.level_stats[level_num] = stats
                    except (ValueError, TypeError, KeyError):
                        logger.warning(
                            f"Skipping corrupt level data for level {level_num_str}"
                        )
                        continue

                # Ajustes
                level_adjustments_raw = data.get("level_adjustments", {})
                self.level_adjustments = {
                    int(k): v
                    for k, v in level_adjustments_raw.items()
                    if isinstance(v, (int, float))
                }

                # Sessões
                session_history_raw: List[Dict[str, Any]] = data.get(
                    "session_history", []
                )
                for session_data_raw in session_history_raw:
                    if session_data_raw.get("start_time") is None:
                        continue
                    session_data: Dict[str, Any] = session_data_raw
                    try:
                        # Ensure start_time is a string before passing to fromisoformat
                        start_time_str = session_data.get("start_time")
                        if not isinstance(start_time_str, str):
                            logger.warning(
                                "Skipping corrupt session data due to invalid start_time type."
                            )
                            continue

                        session = SessionStats(
                            start_time=datetime.fromisoformat(start_time_str)
                        )

                        end_time_str = session_data.get("end_time")
                        if isinstance(end_time_str, str):
                            session.end_time = datetime.fromisoformat(end_time_str)

                        # Explicitly check types for other fields
                        levels_attempted_raw = session_data.get("levels_attempted", [])
                        session.levels_attempted = [
                            int(lvl)
                            for lvl in levels_attempted_raw
                            if isinstance(lvl, (int, float))
                        ]

                        deaths_raw = session_data.get("deaths", 0)
                        session.deaths = (
                            int(deaths_raw)
                            if isinstance(deaths_raw, (int, float))
                            else 0
                        )

                        score_raw = session_data.get("score", 0)
                        session.score = (
                            int(score_raw) if isinstance(score_raw, (int, float)) else 0
                        )

                        powerups_collected_raw = session_data.get(
                            "powerups_collected", 0
                        )
                        session.powerups_collected = (
                            int(powerups_collected_raw)
                            if isinstance(powerups_collected_raw, (int, float))
                            else 0
                        )

                        self.session_history.append(session)
                    except (ValueError, TypeError, KeyError) as ve:
                        logger.warning(f"Skipping corrupt session data: {ve}")
                        continue

                # Aprimoramentos: unlocked + loadout (migração segura)
                try:
                    unlocked_raw = data.get("unlocked_upgrades")
                    if isinstance(unlocked_raw, list):
                        parsed: set[UpgradeType] = set()
                        from typing import cast

                        for name in cast(List[Any], unlocked_raw):
                            try:
                                parsed.add(UpgradeType[name])
                            except KeyError:
                                logger.warning(f"Skipping unknown upgrade: {name}")
                                continue
                        # Fazer merge com DEFAULT_UNLOCKED para adicionar novos upgrades
                        # Isso garante que upgrades novos sejam automaticamente desbloqueados
                        self.unlocked_upgrades = (
                            parsed.union(set(DEFAULT_UNLOCKED))
                            if parsed
                            else set(DEFAULT_UNLOCKED)
                        )
                    else:
                        self.unlocked_upgrades = set(DEFAULT_UNLOCKED)

                    loadout_raw = data.get("upgrade_loadout")
                    if isinstance(loadout_raw, list):
                        from typing import cast

                        slots: List[Optional[UpgradeType]] = []
                        for item in cast(List[Any], loadout_raw)[:UPGRADE_SLOT_COUNT]:
                            if item is None:
                                slots.append(None)
                                continue
                            try:
                                slots.append(UpgradeType[item])
                            except KeyError:
                                slots.append(None)
                                logger.warning(f"Skipping unknown upgrade: {item}")
                        # Completar tamanho de slots
                        while len(slots) < UPGRADE_SLOT_COUNT:
                            slots.append(None)
                        self.upgrade_loadout = slots
                    else:
                        self.upgrade_loadout = [None] * UPGRADE_SLOT_COUNT
                except (KeyError, ValueError, TypeError):
                    # Em caso de erro, usar defaults
                    self.unlocked_upgrades = set(DEFAULT_UNLOCKED)
                    self.upgrade_loadout = [None] * UPGRADE_SLOT_COUNT

                # Keybindings (migração segura) — deve rodar independente do bloco de upgrades
                try:
                    keybindings_raw = data.get("upgrade_keybindings")
                    if isinstance(keybindings_raw, list):
                        from typing import cast

                        keys: List[int] = []
                        for key in cast(List[Any], keybindings_raw)[
                            :UPGRADE_SLOT_COUNT
                        ]:
                            if (
                                isinstance(key, int) and 0 <= key <= 1000000
                            ):  # Valid pygame key range
                                keys.append(key)
                            else:
                                defaults_all: List[int] = [
                                    pygame.K_1,
                                    pygame.K_2,
                                    pygame.K_3,
                                    pygame.K_4,
                                    pygame.K_5,
                                    pygame.K_6,
                                    pygame.K_7,
                                    pygame.K_8,
                                    pygame.K_9,
                                ]
                                keys.append(defaults_all[len(keys)])
                        # Complete slot count
                        defaults: List[int] = [
                            pygame.K_1,
                            pygame.K_2,
                            pygame.K_3,
                            pygame.K_4,
                            pygame.K_5,
                            pygame.K_6,
                            pygame.K_7,
                            pygame.K_8,
                            pygame.K_9,
                        ]
                        while len(keys) < UPGRADE_SLOT_COUNT:
                            keys.append(defaults[len(keys)])
                        self.upgrade_keybindings = keys
                    else:
                        defaults: List[int] = [
                            pygame.K_1,
                            pygame.K_2,
                            pygame.K_3,
                            pygame.K_4,
                            pygame.K_5,
                            pygame.K_6,
                            pygame.K_7,
                            pygame.K_8,
                            pygame.K_9,
                        ]
                        self.upgrade_keybindings = defaults[:UPGRADE_SLOT_COUNT]
                except (KeyError, ValueError, TypeError, IndexError):
                    defaults: List[int] = [
                        pygame.K_1,
                        pygame.K_2,
                        pygame.K_3,
                        pygame.K_4,
                        pygame.K_5,
                        pygame.K_6,
                        pygame.K_7,
                        pygame.K_8,
                        pygame.K_9,
                    ]
                    self.upgrade_keybindings = defaults[:UPGRADE_SLOT_COUNT]

                # Limit session history after loading
                if len(self.session_history) > self.MAX_SESSION_HISTORY:
                    self.session_history = self.session_history[
                        -self.MAX_SESSION_HISTORY :
                    ]

        except (OSError, ValueError, KeyError, TypeError) as e:
            logger.error(f"Erro ao carregar perfil: {e}")
            # Fazer backup
            if self.profile_path.exists():
                backup_path = self.profile_path.with_suffix(".backup.json")
                import shutil

                shutil.copy2(self.profile_path, backup_path)
                logger.info(f"Backup salvo em: {backup_path}")
            # Carregar defaults ao invés de resetar
            self._ensure_safe_world_defaults()
            return  # Mantém valores inicializados no __init__

    def save(self):
        """Salva perfil no disco."""
        # Criar diretório se não existir
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)

        # Serializar level stats
        level_stats_data: Dict[str, Dict[str, Any]] = {}
        for level_num, stats in self.level_stats.items():
            stats_dict = {}
            for key, value in stats.__dict__.items():
                if isinstance(value, datetime):
                    stats_dict[key] = value.isoformat()
                elif key == "best_time" and value is None:
                    stats_dict[key] = None  # Save None as null
                else:
                    stats_dict[key] = value
            level_stats_data[str(level_num)] = stats_dict

        # Serializar sessões
        session_history_data: List[Dict[str, Any]] = []
        for session in self.session_history:
            session_dict: Dict[str, Any] = {
                "start_time": session.start_time.isoformat(),
                "end_time": session.end_time.isoformat() if session.end_time else None,
                "levels_attempted": session.levels_attempted,
                "deaths": session.deaths,
                "score": session.score,
                "powerups_collected": session.powerups_collected,
            }
            session_history_data.append(session_dict)

        # Serialização dos aprimoramentos
        unlocked_serialized = [
            u.name for u in sorted(self.unlocked_upgrades, key=lambda x: x.name)
        ]
        loadout_serialized = [
            u.name if u is not None else None for u in self.upgrade_loadout
        ]
        keybindings_serialized = self.upgrade_keybindings.copy()

        data: Dict[str, Any] = {
            "version": "1.0",
            "profile_created": self.profile_created.isoformat(),
            "last_played": self.last_played.isoformat() if self.last_played else None,
            "total_playtime": self.total_playtime,
            "highest_level_reached": self.highest_level_reached,
            "total_deaths": self.total_deaths,
            "total_score": self.total_score,
            "resolution": list(self.resolution),
            "mouse_control": self.mouse_control,
            "auto_fire": self.auto_fire,
            "level_stats": level_stats_data,
            "level_adjustments": {str(k): v for k, v in self.level_adjustments.items()},
            "session_history": session_history_data,
            "unlocked_upgrades": unlocked_serialized,
            "upgrade_loadout": loadout_serialized,
            "upgrade_keybindings": keybindings_serialized,
            "stars_collected": self.stars_collected,
            "stars_spent": self.stars_spent,
            "unlocked_slots": self.unlocked_slots,
            "world_unlocks": {
                str(world_id): {
                    "world_id": status.world_id,
                    "is_unlocked": status.is_unlocked,
                    "first_accessed_at": (
                        status.first_accessed_at.isoformat()
                        if status.first_accessed_at
                        else None
                    ),
                    "last_best_score_at_checkpoint": status.last_best_score_at_checkpoint,
                    "checkpoint_set": status.checkpoint_set,
                }
                for world_id, status in self.world_unlocks.items()
            },
            "current_checkpoint_world": self.current_checkpoint_world,
        }

        with open(self.profile_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self._dirty = False
        self._last_save = time.time()

    def reset(self):
        """Reseta completamente o perfil do jogador."""
        # Encerrar sessão atual se existir
        if self.current_session:
            self.end_session()

        # Redefinir todos os atributos para valores iniciais
        self.level_stats = {}
        self.total_playtime = 0.0
        self.highest_level_reached = 1
        self.total_deaths = 0
        self.total_score = 0
        self.world_unlocks = {
            1: WorldUnlockStatus(
                world_id=1,
                is_unlocked=True,
                first_accessed_at=datetime.now(),
                checkpoint_set=True,
            )
        }
        self.current_checkpoint_world = 1
        self.selected_world_id = 1
        self.current_session = None
        self.session_history = []
        self.level_adjustments = {}
        self.preferred_difficulty = None
        self.resolution = (1280, 720)  # Default resolution
        self.mouse_control = False
        self.auto_fire = False
        self.unlocked_upgrades = set(DEFAULT_UNLOCKED)
        self.upgrade_loadout = [None] * UPGRADE_SLOT_COUNT
        self.upgrade_keybindings = [
            pygame.K_1,
            pygame.K_2,
            pygame.K_3,
            pygame.K_4,
            pygame.K_5,
            pygame.K_6,
            pygame.K_7,
            pygame.K_8,
            pygame.K_9,
        ][:UPGRADE_SLOT_COUNT]

        # Resetar sistema de estrelas
        self.stars_collected = 0
        self.stars_spent = 0
        self.unlocked_slots = INITIAL_UNLOCKED_SLOTS

        self.profile_created = datetime.now()
        self.last_played = None
        self._dirty = False
        self._last_save = time.time()

        # Salvar o perfil resetado
        self.save()

        logger.info("Perfil do jogador resetado com sucesso!")


class ProfileVisualizer:
    """Cria visualizações das estatísticas do jogador."""

    @staticmethod
    def render_skill_badge(
        surface: pygame.Surface,
        skill_level: str,
        x: int,
        y: int,
        font: pygame.font.Font,
    ):
        """Renderiza badge de skill level."""
        from ..core import colors

        badge_colors = {
            "Novato": (100, 100, 100),
            "Aprendiz": (139, 69, 19),
            "Intermediário": (192, 192, 192),
            "Avançado": (255, 215, 0),
            "Veterano": (75, 0, 130),
            "Mestre": (255, 0, 255),
        }
        color = badge_colors.get(skill_level, colors.WHITE)

        pygame.draw.circle(surface, color, (x + 40, y + 40), 40, 3)

        text = font.render(skill_level, True, color)
        text_rect = text.get_rect(center=(x + 150, y + 40))
        surface.blit(text, text_rect)

    @staticmethod
    def render_performance_graph(
        surface: pygame.Surface,
        profile: PlayerProfile,
        x: int,
        y: int,
        width: int,
        height: int,
        font: pygame.font.Font,
    ):
        """Renderiza gráfico de performance ao longo dos níveis."""
        from ..core import colors

        if not profile.level_stats:
            return

        levels = sorted(profile.level_stats.keys())
        max_level = max(levels) if levels else 1

        pygame.draw.line(
            surface, colors.GRAY, (x, y + height), (x + width, y + height), 2
        )
        pygame.draw.line(surface, colors.GRAY, (x, y), (x, y + height), 2)

        if len(levels) > 1:
            points: List[Tuple[float, float]] = []
            for level_num in levels:
                stats = profile.level_stats[level_num]
                px = x + (level_num / max_level) * width
                py = y + height - (stats.clear_rate * height)
                points.append((px, py))
                color = ProfileVisualizer._get_performance_color(stats.clear_rate)
                pygame.draw.circle(surface, color, (int(px), int(py)), 5)

            if len(points) > 1:
                pygame.draw.lines(surface, colors.BLUE, False, points, 2)

        for i in range(0, max_level + 1, max(1, max_level // 10)):
            label_x = x + (i / max_level) * width
            label = font.render(str(i), True, colors.WHITE)
            surface.blit(label, (label_x - 5, y + height + 5))

        for i in range(0, 101, 25):
            label_y = y + height - (i / 100 * height)
            label = font.render(f"{i}%", True, colors.WHITE)
            surface.blit(label, (x - 40, label_y - 10))

    @staticmethod
    def render_level_preview(
        surface: pygame.Surface,
        profile: PlayerProfile,
        level_number: int,
        x: int,
        y: int,
    ):
        """Renderiza preview de um nível com estatísticas."""
        from ..core import colors
        from ..core.assets import get_font

        if level_number not in profile.level_stats:
            # Nível novo
            font = get_font(18)
            text = font.render("Nível Novo!", True, colors.GREEN)
            surface.blit(text, (x, y))
            return

        stats = profile.level_stats[level_number]
        analysis = PerformanceAnalyzer.analyze_level_performance(stats)

        # Background
        bg_rect = pygame.Rect(x, y, 300, 120)
        pygame.draw.rect(surface, (40, 40, 40), bg_rect)
        pygame.draw.rect(surface, colors.WHITE, bg_rect, 2)

        font = get_font(16)
        y_offset = y + 10

        # Estado
        state_colors = {
            PerformanceState.STRUGGLING: colors.RED,
            PerformanceState.LEARNING: colors.YELLOW,
            PerformanceState.COMFORTABLE: colors.GREEN,
            PerformanceState.DOMINATING: colors.BLUE,
            PerformanceState.INCONSISTENT: colors.ORANGE,
        }
        state_text = analysis["state"].value.capitalize()
        state_color = state_colors.get(analysis["state"], colors.WHITE)
        text = font.render(f"Status: {state_text}", True, state_color)
        surface.blit(text, (x + 10, y_offset))
        y_offset += 25

        # Estatísticas
        lines = [
            f"Tentativas: {stats.attempts}",
            f"Taxa de Sucesso: {stats.clear_rate:.0%}",
            (
                f"Melhor Tempo: {stats.best_time:.1f}s"
                if stats.best_time is not None
                else "Melhor Tempo: --"
            ),
        ]

        for line in lines:
            text = font.render(line, True, colors.WHITE)
            surface.blit(text, (x + 10, y_offset))
            y_offset += 22

    @staticmethod
    def _get_performance_color(clear_rate: float) -> Tuple[int, int, int]:
        """Retorna cor baseada na taxa de sucesso."""
        if clear_rate < 0.3:
            return (255, 0, 0)  # Vermelho - struggling
        if clear_rate < 0.5:
            return (255, 165, 0)  # Laranja - learning
        if clear_rate < 0.8:
            return (0, 255, 0)  # Verde - comfortable
        return (0, 191, 255)  # Azul - dominating
