import json
import logging
import os
import shutil
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, cast

import pygame

from .difficulty import DifficultyPreset
from .levels import DifficultyConfig, LevelConfig
from .ship_types import DEFAULT_SHIP_ID, ShipProfile, get_ship_profile, is_valid_ship_id
from .upgrades import UpgradeType
from .upgrades_config import (
    DEFAULT_KEYBINDINGS,
    DEFAULT_UNLOCKED,
    INITIAL_UNLOCKED_SLOTS,
    UPGRADE_SLOT_COUNT,
    migrate_slot_model,
)

logger = logging.getLogger(__name__)


# Upgrades renomeados: nome antigo gravado no perfil → nome atual do enum.
# O perfil serializa `UpgradeType.name`, então renomear um membro faria o
# `UpgradeType[nome]` da carga levantar KeyError e o jogador PERDER o
# desbloqueio (e o slot do loadout) em silêncio — o pior tipo de falha de
# persistência (§15). O alias vale só na LEITURA; a gravação sempre usa o nome
# novo, então o perfil se converte sozinho no primeiro save.
_UPGRADE_NAME_ALIASES: Dict[str, str] = {
    "LASER_SHOT": "ORBITAL_DISCHARGE",
}


def _upgrade_type_from_saved(name: str) -> UpgradeType:
    """`UpgradeType` a partir do nome gravado, honrando renomeações."""
    return UpgradeType[_UPGRADE_NAME_ALIASES.get(name, name)]


class PerformanceState(Enum):
    """Estados de performance do jogador."""

    STRUGGLING = "struggling"  # Dificuldade excessiva
    LEARNING = "learning"  # Progresso normal
    COMFORTABLE = "comfortable"  # Zona de conforto
    DOMINATING = "dominating"  # Fácil demais
    INCONSISTENT = "inconsistent"  # Resultados variados


# ── Limiares de diagnóstico de performance ──────────────────────────────────
# Fonte ÚNICA: lidos tanto por `LevelPerformance.get_performance_state`
# (diagnóstico) quanto por `PerformanceAnalyzer` (recomendação de ajuste).
#
# Antes cada lado tinha a sua cópia: o analyzer declarava STRUGGLE_THRESHOLD /
# DOMINATE_THRESHOLD que NINGUÉM lia, enquanto o diagnóstico usava 0.3/0.9
# hardcoded. Mexer no knob documentado não fazia nada.
STRUGGLE_CLEAR_RATE: float = 0.30  # clear rate abaixo disso = lutando
DOMINATE_CLEAR_RATE: float = 0.90  # clear rate acima disso = dominando

# Tentativas mínimas antes de emitir QUALQUER diagnóstico ou ajuste.
# Vale igual para os dois lados de propósito: com gates diferentes (era 3 para
# endurecer e 5 para aliviar) o sistema apertava quase 2x mais rápido do que
# ajudava — viés silencioso contra quem já estava sofrendo.
MIN_ATTEMPTS_TO_DIAGNOSE: int = 3


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

    # Histórico de tentativas (últimas 10) — deque com maxlen evita pop(0) O(n)
    recent_attempts: Deque[Dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=10)
    )

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
        attempts = list(self.recent_attempts)
        mid = len(attempts) // 2
        first_half = attempts[:mid]
        second_half = attempts[mid:]

        first_success_rate = sum(
            1 for a in first_half if a.get("cleared", False)
        ) / len(first_half)
        second_success_rate = sum(
            1 for a in second_half if a.get("cleared", False)
        ) / len(second_half)

        return second_success_rate - first_success_rate

    def get_performance_state(self) -> PerformanceState:
        """Determina estado atual de performance."""
        if self.attempts < MIN_ATTEMPTS_TO_DIAGNOSE:
            return PerformanceState.LEARNING

        # Dificuldade excessiva
        if self.clear_rate < STRUGGLE_CLEAR_RATE:
            return PerformanceState.STRUGGLING

        # Dominando completamente
        if self.clear_rate > DOMINATE_CLEAR_RATE:
            # Verificar consistência de tempos
            if self.clears >= 2 and self.best_time is not None and self.avg_time > 0:
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


@dataclass
class HighScoreEntry:
    """Entrada no Hall da Fama (top 10 arcade)."""

    initials: str
    score: int
    level_reached: int
    difficulty: str  # DifficultyPreset.value
    achieved_at: datetime


MAX_HIGH_SCORES = 10


class PerformanceAnalyzer:
    """Analisa padrões de performance e sugere ajustes."""

    # Os limiares de clear rate e o mínimo de tentativas são módulo-level
    # (STRUGGLE_CLEAR_RATE / DOMINATE_CLEAR_RATE / MIN_ATTEMPTS_TO_DIAGNOSE):
    # fonte única compartilhada com `LevelPerformance.get_performance_state`.

    RECENT_ATTEMPTS_WINDOW = 10  # Quantas tentativas recentes considerar
    IMPROVEMENT_THRESHOLD = 0.2  # Melhoria mínima para considerar progresso

    @staticmethod
    def analyze_level_performance(stats: LevelPerformance) -> Dict[str, Any]:
        """Diagnóstico LEGÍVEL de um nível — para log e UI.

        NÃO decide a dificuldade. O multiplicador vem de
        `DifficultyAdjuster.multiplier_for`, que é contínuo no clear rate; aqui
        os estados são rótulos discretos, cuja utilidade é explicar a um humano
        o que o sistema está vendo. Manter os dois separados é de propósito:
        um rótulo pode saltar de "lutando" para "confortável" sem que o número
        salte junto.
        """
        state = stats.get_performance_state()
        return {
            "state": state,
            "reason": PerformanceAnalyzer._describe(stats, state),
            "clear_rate": stats.clear_rate,
            "attempts": stats.attempts,
            "trend": stats.improvement_trend,
        }

    @staticmethod
    def _describe(stats: LevelPerformance, state: PerformanceState) -> str:
        """Frase curta explicando o diagnóstico (vai para o log)."""
        if stats.attempts < MIN_ATTEMPTS_TO_DIAGNOSE:
            return "Dados insuficientes"
        if state == PerformanceState.STRUGGLING:
            if stats.improvement_trend > PerformanceAnalyzer.IMPROVEMENT_THRESHOLD:
                return f"Clear rate baixo ({stats.clear_rate:.0%}) mas melhorando"
            return f"Clear rate baixo ({stats.clear_rate:.0%}) sem melhoria"
        if state == PerformanceState.DOMINATING:
            return (
                f"Dominando ({stats.clear_rate:.0%}), "
                f"{stats.current_win_streak} vitórias consecutivas"
            )
        if state == PerformanceState.INCONSISTENT:
            return "Performance inconsistente"
        if state == PerformanceState.COMFORTABLE:
            return f"Performance ideal ({stats.clear_rate:.0%})"
        return f"Aprendendo ({stats.clear_rate:.0%})"

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

        # Analisar tendência geral. "Recentes" = jogados há menos tempo
        # (por last_played), não os de maior índice — senão revisitar fases
        # antigas não contaria no overall_trend.
        recent_stats = sorted(
            profile.level_stats.values(),
            key=lambda s: s.last_played or datetime.min,
        )[-5:]
        if len(recent_stats) >= 3:
            recent_clear_rates = [s.clear_rate for s in recent_stats]
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
        from .i18n import t

        recommendations: List[str] = []

        # Recomendações baseadas em skill level
        if skill_level in ["Novato", "Aprendiz"]:
            recommendations.append(t("stats.rec.novice_shield"))
            recommendations.append(t("stats.rec.dodge"))

        # Recomendações baseadas em tendência
        if trend == "declining":
            recommendations.append(t("stats.rec.declining"))
            recommendations.append(t("stats.rec.revisit"))
        elif trend == "improving":
            recommendations.append(t("stats.rec.improving"))

        # Recomendações baseadas em padrões específicos
        struggling_levels = [
            lv
            for lv, stats in profile.level_stats.items()
            if stats.attempts >= 5 and stats.clear_rate < 0.3
        ]

        if struggling_levels:
            recommendations.append(
                t(
                    "stats.rec.challenging",
                    levels=", ".join(map(str, struggling_levels[:3])),
                )
            )

        return recommendations


class DifficultyAdjuster:
    """Multiplicador de dificuldade de um nível — função PURA das estatísticas.

    A política inteira em uma frase: **ajudar rápido, apertar devagar, e nunca
    apertar o caminho de volta.**

    Três entradas, uma conta::

        mult = 1.0 + (alvo(clear_rate) - 1.0) * evidência(attempts)

    **Não há estado persistido.** Chamar duas vezes com as mesmas estatísticas
    dá o mesmo número. A versão anterior guardava um valor por nível
    (`PlayerProfile.level_adjustments`) e o avançava um passo A CADA CHAMADA:
    o grau de adaptação era medido por *quantas vezes a função tinha sido
    chamada* — um contador implícito, não-idempotente e gravado em disco, que
    sombreava o `stats.attempts` já existente. Os dois só concordavam por
    coincidência dos call sites; qualquer leitor a mais (preview de HUD, tela de
    seleção, overlay de debug) teria acelerado a adaptação em silêncio, e o
    desvio sobreviveria à sessão que o causou.

    Duas propriedades sustentam isso:

    1. **O alvo é CONTÍNUO no clear rate.** Antes se escolhia entre valores
       discretos (0.85 / 1.0 / 1.15) por faixa, e o multiplicador saltava 15% de
       uma fase para a outra quando o clear rate cruzava um limiar — com poucas
       tentativas, um único abate ou morte cruzava. A versão com estado
       amortecia esse salto por acidente (o passo suave escondia a
       descontinuidade). Sendo contínuo, 0.299 e 0.301 de clear rate dão
       praticamente o mesmo número, e nem histerese nem memória são necessárias:
       a descontinuidade era a doença, o amortecimento era só o curativo.
    2. **A evidência substitui a "confiança".** Era um enum (low/medium/high)
       que gatilhava ramos distintos; agora é uma rampa sobre `attempts`, que é
       a unidade em que a política sempre foi descrita ("por tentativa").
    """

    # Desvio máximo em cada direção. MIN/MAX_ADJUSTMENT derivam daqui para não
    # existirem dois números dizendo a mesma coisa.
    #
    # Assimétricos, e isso é a política — não descuido. Além de o alívio chegar
    # com menos evidência (ver as rampas), ele chega MAIS FUNDO. Há também uma
    # razão geométrica: a faixa de alívio tem 0.30 de largura em clear rate
    # (STRUGGLE_CLEAR_RATE até 0) e a de aperto só 0.10 (DOMINATE_CLEAR_RATE até
    # 1.0). Tetos iguais fariam o aperto reagir 3x mais forte ao mesmo desvio de
    # clear rate — exatamente o contrário de "apertar devagar".
    MAX_EASE = 0.25  # piso 0.75 — 25% mais fácil
    MAX_HARDEN = 0.15  # teto 1.15 — 15% mais difícil

    MIN_ADJUSTMENT = 1.0 - MAX_EASE
    MAX_ADJUSTMENT = 1.0 + MAX_HARDEN

    # Tentativas (ALÉM do mínimo de diagnóstico) até o alvo valer integralmente.
    # Assimétrico de propósito: errar para o lado fácil custa uma fase morna;
    # errar para o lado difícil custa o jogador (§11).
    EASE_RAMP_ATTEMPTS = 2
    HARDEN_RAMP_ATTEMPTS = 4

    # Diferença imperceptível: trata como "sem ajuste" e devolve a config base.
    NEUTRAL_BAND = 0.02

    # Quão atrás da fronteira do jogador uma fase pode estar e ainda ser
    # candidata a endurecer. Ver `hardening_allowed`.
    FRONTIER_MARGIN = 2

    @staticmethod
    def hardening_allowed(level_number: int, highest_level_reached: int) -> bool:
        """A fase está perto o bastante da fronteira para poder endurecer?

        Morrer manda o jogador de volta ao checkpoint do mundo, então as fases
        de ENTRADA são rejogadas em toda run e limpas em toda run. Pelas
        estatísticas puras elas parecem "dominadas" (clear rate ~100%, win
        streak alto) e o adaptativo as endurecia em até +25% — enquanto a fase
        onde o jogador realmente trava só amolecia depois de várias runs
        inteiras. O resultado líquido era o caminho de volta ficando mais duro
        justamente para quem já estava apanhando.

        A fronteira (`highest_level_reached`) separa os dois casos sem precisar
        de estado novo: uma fase muito atrás dela é trajeto, não desafio — o
        jogador já provou que a domina, e apertá-la só cobra pedágio na
        retomada. Perto da fronteira, "clear rate alto" significa de fato que a
        fase está fácil demais, e aí endurecer é legítimo.

        Alívio NUNCA passa por este gate: ajudar é sempre permitido.
        """
        return level_number + DifficultyAdjuster.FRONTIER_MARGIN >= highest_level_reached

    @staticmethod
    def multiplier_for(
        stats: LevelPerformance, *, allow_hardening: bool = True
    ) -> float:
        """O multiplicador de dificuldade deste nível. Puro e idempotente.

        Args:
            stats: desempenho acumulado do jogador NESTE nível.
            allow_hardening: se False, o alvo é limitado a 1.0 — o resultado
                pode aliviar ou ficar neutro, nunca apertar. Vem de
                `hardening_allowed`.

        Returns:
            Multiplicador em [`MIN_ADJUSTMENT`, `MAX_ADJUSTMENT`]. Acima de 1.0
            = mais difícil (spawn mais rápido, mais inimigos).
        """
        target = DifficultyAdjuster._target(stats)
        if not allow_hardening:
            target = min(target, 1.0)

        evidence = DifficultyAdjuster._evidence(stats, target)
        multiplier = 1.0 + (target - 1.0) * evidence

        return max(
            DifficultyAdjuster.MIN_ADJUSTMENT,
            min(DifficultyAdjuster.MAX_ADJUSTMENT, multiplier),
        )

    @staticmethod
    def _target(stats: LevelPerformance) -> float:
        """Para onde a dificuldade deveria ir, ignorando quanta evidência há.

        Contínuo por construção: no limiar exato o desvio é ZERO e cresce
        proporcionalmente a quão longe dele o jogador está. É o que dispensa
        histerese — não há degrau para oscilar em cima.
        """
        clear_rate = stats.clear_rate

        if clear_rate < STRUGGLE_CLEAR_RATE:
            severity = (STRUGGLE_CLEAR_RATE - clear_rate) / STRUGGLE_CLEAR_RATE
            # Quem já está melhorando sozinho precisa de menos ajuda. Atenuação
            # proporcional à tendência, não um ramo à parte por limiar.
            severity *= 1.0 - max(0.0, min(1.0, stats.improvement_trend))
            return 1.0 - DifficultyAdjuster.MAX_EASE * severity

        if clear_rate > DOMINATE_CLEAR_RATE:
            severity = (clear_rate - DOMINATE_CLEAR_RATE) / (1.0 - DOMINATE_CLEAR_RATE)
            return 1.0 + DifficultyAdjuster.MAX_HARDEN * severity

        return 1.0

    @staticmethod
    def _evidence(stats: LevelPerformance, target: float) -> float:
        """Quanto do alvo aplicar (0..1), dado o volume de tentativas.

        Substitui o enum de confiança: a mesma ideia ("não reaja a ruído"), mas
        na unidade em que a política é descrita. Abaixo de
        `MIN_ATTEMPTS_TO_DIAGNOSE` é zero — sem dado, sem ajuste.
        """
        extra_attempts = stats.attempts - MIN_ATTEMPTS_TO_DIAGNOSE
        if extra_attempts <= 0:
            return 0.0

        ramp = (
            DifficultyAdjuster.EASE_RAMP_ATTEMPTS
            if target < 1.0
            else DifficultyAdjuster.HARDEN_RAMP_ATTEMPTS
        )
        return min(1.0, extra_attempts / ramp)

    @staticmethod
    def is_neutral(multiplier: float) -> bool:
        """Diferença imperceptível — não vale materializar uma config nova."""
        return abs(multiplier - 1.0) <= DifficultyAdjuster.NEUTRAL_BAND

    @staticmethod
    def apply_to_config(config: LevelConfig, multiplier: float) -> LevelConfig:
        """Aplica multiplicador à configuração do nível."""
        # Ajustar spawn times (inverso do multiplier)
        adjusted_spawn_config: Dict[Any, float] = {}
        for enemy_type, spawn_time in config.enemy_spawn_config.items():
            # Multiplicador maior = mais difícil = spawn mais rápido
            adjusted_time = spawn_time / multiplier

            # Garantir mínimo jogável
            adjusted_time = max(DifficultyConfig.MIN_SPAWN_TIME, adjusted_time)

            adjusted_spawn_config[enemy_type] = adjusted_time

        # Ajustar quantidade de inimigos. O piso é o MESMO do pipeline
        # (`_apply_stage_grace_and_coop`): antes era um `max(20, ...)` solto que
        # deixava o adaptativo furar em 25% o mínimo que o pipeline declara.
        adjusted_enemies = max(
            DifficultyConfig.MIN_ENEMIES_TO_CLEAR,
            int(config.enemies_to_clear * multiplier),
        )

        return replace(
            config,
            enemy_spawn_config=adjusted_spawn_config,
            enemies_to_clear=adjusted_enemies,
        )


class PlayerProfile:
    """Perfil completo do jogador com meta-progression."""

    MAX_SESSION_HISTORY = 50  # Limit session history to last 50 sessions

    @staticmethod
    def _build_initial_world_unlocks() -> Dict[int, WorldUnlockStatus]:
        """Estado inicial de world_unlocks: só o Mundo 1 desbloqueado, com checkpoint.

        Fonte única usada por `reset()` e `_ensure_safe_world_defaults()` para
        evitar drift entre os dois. NÃO usar no `__init__`: lá `world_unlocks`
        começa vazio e é populado por `load()`; este default é só o fallback.
        """
        return {
            1: WorldUnlockStatus(
                world_id=1,
                is_unlocked=True,
                first_accessed_at=datetime.now(),
                checkpoint_set=True,
            )
        }

    def _ensure_safe_world_defaults(self) -> None:
        """Garante estado mínimo seguro para mundos/checkpoint."""
        if 1 not in self.world_unlocks:
            self.world_unlocks.update(self._build_initial_world_unlocks())
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

        # NOTA: não existe `level_adjustments`. O multiplicador de dificuldade é
        # DERIVADO de `level_stats` a cada consulta (`DifficultyAdjuster`), não
        # guardado. Perfis antigos ainda têm a chave no JSON; ela é ignorada na
        # carga e some no próximo save.

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

        # Naves desbloqueadas + nave atualmente selecionada.
        self.unlocked_ships: set[str] = {DEFAULT_SHIP_ID}
        self.selected_ship: str = DEFAULT_SHIP_ID

        # Hall da Fama: lista global ordenada desc por score (top 10).
        self.high_scores: List[HighScoreEntry] = []

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
            pygame.K_0,
            pygame.K_MINUS,
            pygame.K_EQUALS,
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

    def unlock_all_worlds(self):
        """Desbloqueia todos os 4 mundos e permite checkpoints neles."""
        for world_id in range(1, 5):
            if world_id not in self.world_unlocks:
                self.world_unlocks[world_id] = WorldUnlockStatus(
                    world_id=world_id,
                    is_unlocked=True,
                    first_accessed_at=datetime.now(),
                    checkpoint_set=True,
                )
            else:
                self.world_unlocks[world_id].is_unlocked = True
                self.world_unlocks[world_id].checkpoint_set = True

        self._mark_dirty()
        logger.info("🌍 Todos os mundos foram desbloqueados via cheat!")

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
                "🌍 Mundo %s desbloqueado! Checkpoint atualizado.", next_world_id
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
                "🌍 Primeiro acesso ao Mundo %s - checkpoint definido!",
                world_config.world_id,
            )
        elif not self.world_unlocks[world_config.world_id].checkpoint_set:
            # Já existe mas não era checkpoint ainda
            self.world_unlocks[world_config.world_id].checkpoint_set = True
            self.current_checkpoint_world = world_config.world_id
            self.save()
            logger.info("🌍 Checkpoint definido no Mundo %s!", world_config.world_id)

    def reset_to_checkpoint(self) -> int:
        """Jogador perdeu: retorna nível inicial do mundo checkpoint atual.

        Não toca em ``current_session`` — mortes e score já foram registrados
        por ``record_death`` no caller. Mexer aqui causaria contagem dupla de
        mortes e descartaria o score da run.
        """
        from .world_config import get_world_for_level_by_id

        checkpoint_world = get_world_for_level_by_id(self.current_checkpoint_world)
        if checkpoint_world:
            logger.info(
                "💀 Reset para checkpoint: Mundo %s, Nível %s",
                checkpoint_world.world_id,
                checkpoint_world.start_level,
            )
            return checkpoint_world.start_level

        # Fallback para nível 1 se algo der errado
        logger.warning("Checkpoint inválido, fallback para nível 1")
        return 1

    def record_run_best_score(self, score: int) -> None:
        """Registra o melhor score de uma run que alcançou o checkpoint atual.

        Chamado no game over com o score final da run. Mantém o máximo por
        mundo-checkpoint — é o "BEST" exibido no card da seleção de mundo.
        Salva imediatamente, como os demais mutadores de ``world_unlocks``.
        """
        status = self.world_unlocks.get(self.current_checkpoint_world)
        if status is None:
            return
        if score > status.last_best_score_at_checkpoint:
            status.last_best_score_at_checkpoint = score
            self.save()
            logger.info(
                "🏆 Novo BEST do Mundo %s: %s",
                self.current_checkpoint_world,
                score,
            )

    def can_equip_upgrade(self, upgrade_type: UpgradeType, slot_index: int) -> bool:
        """Um upgrade cabe em qualquer slot destravado — um por slot.

        O orçamento de PESO saiu do modelo (ver `upgrades_config`): a única
        pergunta que sobra é se o slot existe e está destravado. O método
        continua existindo porque é o contrato que a tela de aprimoramentos
        consulta antes de equipar.
        """
        from .upgrades import UPGRADES_META

        if not 0 <= slot_index < self.unlocked_slots:
            return False
        return upgrade_type in UPGRADES_META

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

    # ------------------------------------------------------------------
    # Naves
    # ------------------------------------------------------------------

    def is_ship_unlocked(self, ship_id: str) -> bool:
        return ship_id in self.unlocked_ships

    def can_unlock_ship(self, ship_id: str) -> bool:
        """True se a nave existe, não está desbloqueada e há estrelas suficientes."""
        if not is_valid_ship_id(ship_id) or ship_id in self.unlocked_ships:
            return False
        return self.available_stars >= get_ship_profile(ship_id).unlock_cost

    def unlock_ship(self, ship_id: str) -> bool:
        """Compra a nave deduzindo o custo. Retorna False se não puder."""
        if not self.can_unlock_ship(ship_id):
            return False

        self.stars_spent += get_ship_profile(ship_id).unlock_cost
        self.unlocked_ships.add(ship_id)
        self._mark_dirty()
        return True

    def select_ship(self, ship_id: str) -> bool:
        """Define a nave ativa. Só funciona se a nave estiver desbloqueada."""
        if ship_id not in self.unlocked_ships:
            return False
        if self.selected_ship == ship_id:
            return True
        self.selected_ship = ship_id
        self._mark_dirty()
        return True

    def get_selected_ship_profile(self) -> ShipProfile:
        """Retorna o ShipProfile correspondente à nave selecionada."""
        return get_ship_profile(self.selected_ship)

    # ------------------------------------------------------------------
    # SISTEMA DE HIGH SCORES
    # ------------------------------------------------------------------

    def qualifies_for_high_score(self, score: int) -> bool:
        """True se ``score`` entra no top 10. Score <= 0 nunca qualifica."""
        if score <= 0:
            return False
        if len(self.high_scores) < MAX_HIGH_SCORES:
            return True
        return score > self.high_scores[-1].score

    def submit_high_score(self, entry: HighScoreEntry) -> int:
        """Insere ``entry`` mantendo ordem desc por score (FIFO em empates) e
        recorta para os ``MAX_HIGH_SCORES`` melhores.

        Returns:
            Posição final 0-indexed, ou -1 se foi cortado fora do top.
        """
        self.high_scores.append(entry)
        self.high_scores.sort(key=lambda e: (-e.score, e.achieved_at))
        del self.high_scores[MAX_HIGH_SCORES:]
        self._mark_dirty()
        try:
            return self.high_scores.index(entry)
        except ValueError:
            return -1

    def get_predicted_rank(self, score: int) -> int:
        """Retorna a posição 1-indexed onde o score ficaria no top 10."""
        if score <= 0:
            return -1
        # Simular inserção (considerando FIFO em empates por data)
        temp_list = list(self.high_scores)
        dummy_entry = HighScoreEntry(
            initials="???",
            score=score,
            level_reached=1,
            difficulty="normal",
            achieved_at=datetime.now(),
        )
        temp_list.append(dummy_entry)
        temp_list.sort(key=lambda e: (-e.score, e.achieved_at))
        try:
            rank = temp_list.index(dummy_entry) + 1
            return rank if rank <= MAX_HIGH_SCORES else -1
        except ValueError:
            return -1

    def get_high_scores(self) -> List[HighScoreEntry]:
        """Cópia defensiva da lista (já ordenada desc por score)."""
        return list(self.high_scores)

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
        # Web (emscripten): sem I/O no loop. O filesystem é MEMFS volátil (some
        # no reload), então o auto-save só custaria stutter de escrita a cada 10s
        # sem persistir nada. Persistência web é feature à parte (IDBFS/localStorage).
        if sys.platform == "emscripten":
            return
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
        """Registra clear detalhado de um nível.

        Precondição: `record_attempt(level_number)` foi chamado antes nesta
        sessão. O fluxo de jogo garante isso — não há clear sem tentativa prévia
        no caminho normal; um KeyError aqui indica bug de sequência no caller.
        """
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

    def record_death(
        self,
        level_number: int,
        cause: str = "unknown",
        score: int = 0,
        ended_attempt: bool = True,
    ):
        """Registra morte em um nível.

        Se ``score`` > 0, persiste o ganho da fase incompleta nos agregadores
        (usado no game over para capturar o progresso da fase em que o jogador
        morreu, já que ``record_clear`` não roda nesse caso). Para perdas de
        vida sem game over, mantenha ``score=0`` — o ganho do nível será
        persistido por ``record_clear`` quando a fase for concluída.

        ``ended_attempt`` distingue o DESFECHO de um attempt (game over) de uma
        perda de vida intra-attempt. Só desfechos vão para ``recent_attempts`` —
        que é o histórico de OUTCOMES lido por ``improvement_trend`` e
        ``get_performance_state``; contá-los com perdas de vida enviesaria a taxa
        de sucesso. ``stats.deaths`` conta TODAS as mortes (perdas de vida
        incluídas). O caller passa ``ended_attempt=is_game_over``.

        Normalmente ``record_attempt`` precede esta chamada. Se não precedeu
        (ex.: game over chegando de contexto fora do fluxo normal), faz back-fill
        via ``record_attempt`` — garante que um nível com mortes tenha
        ``attempts >= 1`` (nunca um nível com atividade e ``attempts == 0``) e
        reutiliza a lógica de init sem duplicação. NÃO garante ``attempts >=
        deaths``: várias perdas de vida podem ocorrer num mesmo attempt.
        """
        if level_number not in self.level_stats:
            # back-fill: morreu ⇒ jogou ⇒ attempts >= 1
            self.record_attempt(level_number)
        stats = self.level_stats[level_number]
        stats.deaths += 1
        stats.current_win_streak = 0  # Reset streak
        self.total_deaths += 1

        if score > 0:
            stats.total_score += score
            stats.best_score = max(stats.best_score, score)
            self.total_score += score
            if self.current_session:
                self.current_session.score += score

        # Histórico recente: só o DESFECHO do attempt (game over) entra; perda de
        # vida intra-attempt já contou em stats.deaths e não é um outcome.
        if ended_attempt:
            attempt_data: Dict[str, Any] = {
                "timestamp": datetime.now().isoformat(),
                "cleared": False,
                "cause": cause,
                "score": score,
            }
            stats.recent_attempts.append(attempt_data)

        # Sessão
        if self.current_session:
            self.current_session.deaths += 1

        self._mark_dirty()

    def _parse_profile_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parseia JSON em valores de campo. Levanta exceção em estrutura inválida.

        Nunca modifica self — garante atomicidade: load() só aplica o resultado
        se este método retornar com sucesso completo.
        """
        if "level_stats" not in data:
            raise ValueError("Invalid profile structure")

        from .world_config import get_world_for_level_by_id

        parsed: Dict[str, Any] = {}

        # Dados básicos
        parsed["total_playtime"] = data.get("total_playtime", 0.0)
        parsed["highest_level_reached"] = data.get("highest_level_reached", 1)
        parsed["total_deaths"] = data.get("total_deaths", 0)
        parsed["total_score"] = data.get("total_score", 0)

        # Configurações de vídeo
        resolution_raw = data.get("resolution")
        if isinstance(resolution_raw, list):
            resolution_list = cast(List[Any], resolution_raw)
            parsed["resolution"] = (
                (int(resolution_list[0]), int(resolution_list[1]))
                if len(resolution_list) == 2
                else (1280, 720)
            )
        else:
            parsed["resolution"] = (1280, 720)

        # Configurações de controle
        parsed["mouse_control"] = data.get("mouse_control", False)
        parsed["auto_fire"] = data.get("auto_fire", False)

        # Star collection system.
        #
        # `migrate_slot_model` converte perfis do modelo antigo (8 slots + peso)
        # para o de 3 slots, devolvendo as estrelas dos slots que deixaram de
        # existir. Roda sempre: é idempotente para perfis já migrados. O loadout
        # em si já é truncado a `UPGRADE_SLOT_COUNT` mais abaixo, na leitura.
        parsed["stars_collected"] = data.get("stars_collected", 0)
        slots_salvos = data.get("unlocked_slots", INITIAL_UNLOCKED_SLOTS)
        slots_migrados, gasto_migrado = migrate_slot_model(
            int(slots_salvos), int(data.get("stars_spent", 0))
        )
        if slots_migrados != slots_salvos:
            logger.info(
                "Perfil migrado para o modelo de %s slots: %s → %s (estrelas "
                "devolvidas: %s)",
                UPGRADE_SLOT_COUNT,
                slots_salvos,
                slots_migrados,
                int(data.get("stars_spent", 0)) - gasto_migrado,
            )
        parsed["stars_spent"] = gasto_migrado
        parsed["unlocked_slots"] = slots_migrados

        # Naves
        unlocked_ships_raw = data.get("unlocked_ships")
        if isinstance(unlocked_ships_raw, list):
            unlocked_ships: set[str] = {
                sid
                for sid in cast(List[Any], unlocked_ships_raw)
                if isinstance(sid, str) and is_valid_ship_id(sid)
            }
            unlocked_ships.add(DEFAULT_SHIP_ID)
        else:
            unlocked_ships = {DEFAULT_SHIP_ID}
        parsed["unlocked_ships"] = unlocked_ships

        selected = data.get("selected_ship", DEFAULT_SHIP_ID)
        parsed["selected_ship"] = (
            selected
            if isinstance(selected, str) and selected in unlocked_ships
            else DEFAULT_SHIP_ID
        )

        # Sistema de mundos e savepoints
        world_unlocks: Dict[int, WorldUnlockStatus] = {}
        world_unlocks_raw = data.get("world_unlocks", {})
        if isinstance(world_unlocks_raw, dict):
            for wid_key, wdata in cast(Dict[Any, Any], world_unlocks_raw).items():
                if not (isinstance(wid_key, str) and isinstance(wdata, dict)):
                    continue
                wdata = cast(Dict[str, Any], wdata)
                try:
                    wid = int(wid_key)
                    world_unlocks[wid] = WorldUnlockStatus(
                        world_id=wid,
                        is_unlocked=wdata.get("is_unlocked", False),
                        first_accessed_at=(
                            datetime.fromisoformat(wdata["first_accessed_at"])
                            if wdata.get("first_accessed_at")
                            else None
                        ),
                        last_best_score_at_checkpoint=wdata.get(
                            "last_best_score_at_checkpoint", 0
                        ),
                        checkpoint_set=wdata.get("checkpoint_set", False),
                    )
                except (ValueError, TypeError, KeyError):
                    logger.warning("Skipping corrupt world data for world %s", wid_key)
        if 1 not in world_unlocks:
            world_unlocks[1] = WorldUnlockStatus(
                world_id=1,
                is_unlocked=True,
                first_accessed_at=datetime.now(),
                checkpoint_set=True,
            )
        parsed["world_unlocks"] = world_unlocks

        checkpoint_raw = data.get("current_checkpoint_world", 1)
        checkpoint = (
            int(checkpoint_raw)
            if isinstance(checkpoint_raw, (int, float, str))
            and str(checkpoint_raw).isdigit()
            else 1
        )
        if (
            checkpoint not in world_unlocks
            or get_world_for_level_by_id(checkpoint) is None
        ):
            checkpoint = 1
        parsed["current_checkpoint_world"] = checkpoint

        # Hall da Fama
        high_scores: List[HighScoreEntry] = []
        valid_difficulties = {p.value for p in DifficultyPreset}
        for entry_raw in cast(List[Any], data.get("high_scores", [])):
            if not isinstance(entry_raw, dict):
                continue
            entry = cast(Dict[str, Any], entry_raw)
            try:
                diff = str(entry.get("difficulty", "normal"))
                if diff not in valid_difficulties:
                    diff = "normal"
                high_scores.append(
                    HighScoreEntry(
                        initials=str(entry["initials"])[:3].upper(),
                        score=int(entry["score"]),
                        level_reached=int(entry.get("level_reached", 1)),
                        difficulty=diff,
                        achieved_at=datetime.fromisoformat(entry["achieved_at"]),
                    )
                )
            except (KeyError, ValueError, TypeError):
                logger.warning("Pulando entrada corrupta de high_score")
        high_scores.sort(key=lambda e: (-e.score, e.achieved_at))
        del high_scores[MAX_HIGH_SCORES:]
        parsed["high_scores"] = high_scores

        # Timestamps
        if "profile_created" in data and isinstance(data["profile_created"], str):
            parsed["profile_created"] = datetime.fromisoformat(data["profile_created"])
        if data.get("last_played") and isinstance(data["last_played"], str):
            parsed["last_played"] = datetime.fromisoformat(data["last_played"])

        # Level stats
        level_stats: Dict[int, LevelPerformance] = {}
        for level_num_str, stats_data in data.get("level_stats", {}).items():
            try:
                level_num = int(level_num_str)
                stats = LevelPerformance(level_number=level_num)
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
                stats.total_damage_taken = int(stats_data.get("total_damage_taken", 0))
                stats.total_powerups_collected = int(
                    stats_data.get("total_powerups_collected", 0)
                )
                stats.recent_attempts = deque(
                    cast(List[Dict[str, Any]], stats_data.get("recent_attempts", [])),
                    maxlen=PerformanceAnalyzer.RECENT_ATTEMPTS_WINDOW,
                )
                stats.current_win_streak = int(stats_data.get("current_win_streak", 0))
                stats.best_win_streak = int(stats_data.get("best_win_streak", 0))
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
                level_stats[level_num] = stats
            except (ValueError, TypeError, KeyError):
                logger.warning(
                    "Skipping corrupt level data for level %s", level_num_str
                )
        parsed["level_stats"] = level_stats

        # Histórico de sessões
        session_history: List[SessionStats] = []
        for session_data in data.get("session_history", []):
            if session_data.get("start_time") is None:
                continue
            try:
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
                session.levels_attempted = [
                    int(lvl)
                    for lvl in session_data.get("levels_attempted", [])
                    if isinstance(lvl, (int, float))
                ]
                deaths_raw = session_data.get("deaths", 0)
                session.deaths = (
                    int(deaths_raw) if isinstance(deaths_raw, (int, float)) else 0
                )
                score_raw = session_data.get("score", 0)
                session.score = (
                    int(score_raw) if isinstance(score_raw, (int, float)) else 0
                )
                pc_raw = session_data.get("powerups_collected", 0)
                session.powerups_collected = (
                    int(pc_raw) if isinstance(pc_raw, (int, float)) else 0
                )
                session_history.append(session)
            except (ValueError, TypeError, KeyError) as ve:
                logger.warning("Skipping corrupt session data: %s", ve)
        parsed["session_history"] = session_history

        # Aprimoramentos: unlocked + loadout
        try:
            unlocked_raw = data.get("unlocked_upgrades")
            if isinstance(unlocked_raw, list):
                up_parsed: set[UpgradeType] = set()
                for name in cast(List[Any], unlocked_raw):
                    try:
                        up_parsed.add(_upgrade_type_from_saved(name))
                    except KeyError:
                        logger.warning("Skipping unknown upgrade: %s", name)
                parsed["unlocked_upgrades"] = (
                    up_parsed.union(set(DEFAULT_UNLOCKED))
                    if up_parsed
                    else set(DEFAULT_UNLOCKED)
                )
            else:
                parsed["unlocked_upgrades"] = set(DEFAULT_UNLOCKED)

            loadout_raw = data.get("upgrade_loadout")
            if isinstance(loadout_raw, list):
                slots: List[Optional[UpgradeType]] = []
                for item in cast(List[Any], loadout_raw)[:UPGRADE_SLOT_COUNT]:
                    if item is None:
                        slots.append(None)
                        continue
                    try:
                        slots.append(_upgrade_type_from_saved(item))
                    except KeyError:
                        slots.append(None)
                        logger.warning("Skipping unknown upgrade: %s", item)
                while len(slots) < UPGRADE_SLOT_COUNT:
                    slots.append(None)
                parsed["upgrade_loadout"] = slots
            else:
                parsed["upgrade_loadout"] = [None] * UPGRADE_SLOT_COUNT
        except (KeyError, ValueError, TypeError):
            parsed["unlocked_upgrades"] = set(DEFAULT_UNLOCKED)
            parsed["upgrade_loadout"] = [None] * UPGRADE_SLOT_COUNT

        # Keybindings
        try:
            keybindings_raw = data.get("upgrade_keybindings")
            if isinstance(keybindings_raw, list):
                keys: List[int] = []
                for key in cast(List[Any], keybindings_raw)[:UPGRADE_SLOT_COUNT]:
                    if isinstance(key, int) and 0 <= key <= 1000000:
                        keys.append(key)
                    else:
                        keys.append(DEFAULT_KEYBINDINGS[len(keys)])
                while len(keys) < UPGRADE_SLOT_COUNT:
                    keys.append(DEFAULT_KEYBINDINGS[len(keys)])
                parsed["upgrade_keybindings"] = keys
            else:
                parsed["upgrade_keybindings"] = DEFAULT_KEYBINDINGS[:UPGRADE_SLOT_COUNT]
        except (KeyError, ValueError, TypeError, IndexError):
            parsed["upgrade_keybindings"] = DEFAULT_KEYBINDINGS[:UPGRADE_SLOT_COUNT]

        return parsed

    @property
    def _backup_path(self) -> Path:
        """Cópia do último perfil íntegro, escrita antes de cada save."""
        return self.profile_path.with_suffix(".bak.json")

    def _try_parse_profile(self, path: Path) -> Optional[Dict[str, Any]]:
        """Lê e valida um arquivo de perfil. `None` se ausente ou ilegível."""
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data: Dict[str, Any] = json.load(f)
            return self._parse_profile_data(data)
        except (OSError, ValueError, KeyError, TypeError) as e:
            logger.error("Perfil ilegível em %s: %s", path, e)
            return None

    def load(self) -> None:
        """Carrega perfil do disco. Transacional: self só é modificado em caso de sucesso total.

        Cadeia de recuperação: principal → backup do save anterior → defaults.
        O backup existe porque o save é atômico mas o CONTEÚDO pode estar
        corrompido por outra via (edição manual, bug de serialização); sem ele,
        um perfil ilegível zerava toda a progressão do jogador.
        """
        parsed = self._try_parse_profile(self.profile_path)

        if parsed is None and self.profile_path.exists():
            # Preserva o arquivo problemático para diagnóstico (não sobrescreve
            # o backup, que é o último estado BOM conhecido) e tenta restaurar.
            try:
                shutil.copy2(
                    self.profile_path, self.profile_path.with_suffix(".corrupt.json")
                )
            except OSError as e:
                logger.warning("Não foi possível preservar o perfil corrompido: %s", e)
            parsed = self._try_parse_profile(self._backup_path)
            if parsed is not None:
                logger.warning("Perfil restaurado do backup %s", self._backup_path)

        if parsed is None:
            self._ensure_safe_world_defaults()
            return

        self.__dict__.update(parsed)
        if len(self.session_history) > self.MAX_SESSION_HISTORY:
            self.session_history = self.session_history[-self.MAX_SESSION_HISTORY :]

    def _prepare_save_data(self) -> Dict[str, Any]:
        """Prepara dados do perfil para serialização (sincronous, side-effect free)."""
        # Serializar level stats
        level_stats_data: Dict[str, Dict[str, Any]] = {}
        for level_num, stats in self.level_stats.items():
            stats_dict = {}
            for key, value in stats.__dict__.items():
                if isinstance(value, datetime):
                    stats_dict[key] = value.isoformat()
                elif isinstance(value, deque):
                    # Cast deque element type for the type-checker when serializing
                    stats_dict[key] = list(cast(List[Dict[str, Any]], value))
                elif key == "best_time" and value is None:
                    stats_dict[key] = None
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
            "session_history": session_history_data,
            "unlocked_upgrades": unlocked_serialized,
            "upgrade_loadout": loadout_serialized,
            "upgrade_keybindings": keybindings_serialized,
            "stars_collected": self.stars_collected,
            "stars_spent": self.stars_spent,
            "unlocked_slots": self.unlocked_slots,
            "unlocked_ships": sorted(self.unlocked_ships),
            "selected_ship": self.selected_ship,
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
            "high_scores": [
                {
                    "initials": e.initials,
                    "score": e.score,
                    "level_reached": e.level_reached,
                    "difficulty": e.difficulty,
                    "achieved_at": e.achieved_at.isoformat(),
                }
                for e in self.high_scores
            ],
        }
        return data

    @staticmethod
    def _write_profile_atomic(path: Path, backup_path: Path, data: Dict[str, Any]) -> None:
        """Grava o perfil sem janela de corrupção (§15).

        Escrever direto sobre o arquivo real (o que era feito aqui) deixa um
        JSON truncado se o processo morrer no meio — queda de energia, crash,
        fechar a janela durante um auto-save. O perfil vira ilegível e o
        jogador perde moedas, naves, mundos e estatísticas de uma vez.

        Sequência segura:
        1. grava num `.tmp` e força o flush até o disco (`fsync`);
        2. promove o perfil íntegro atual a `.bak.json`;
        3. `os.replace` do `.tmp` para o nome final — operação **atômica** em
           POSIX e Windows: ou o arquivo antigo continua inteiro, ou o novo
           está completo. Nunca um estado intermediário.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        if path.exists():
            try:
                shutil.copy2(path, backup_path)
            except OSError as e:
                # Backup é rede de segurança, não pré-requisito: se falhar, o
                # save principal ainda vale a pena (e segue atômico).
                logger.warning("Falha ao atualizar backup do perfil: %s", e)

        os.replace(tmp_path, path)

    def save(self):
        """Salva perfil no disco (síncrono, bloqueante)."""
        # Web (emscripten): escrita é I/O bloqueante no loop, e o alvo é o MEMFS
        # volátil (perdido no reload). Nada a persistir aqui; ver auto_save.
        if sys.platform == "emscripten":
            return

        self._write_profile_atomic(
            self.profile_path, self._backup_path, self._prepare_save_data()
        )

        self._dirty = False
        self._last_save = time.time()

    def save_async(self) -> None:
        """Salva perfil em thread separada (não-bloqueante).

        Útil para auto-save durante gameplay. Para sessão/exit, use save().
        """
        # Web (emscripten): threads são terreno minado no pygbag (ver crash de
        # worker thread com pygame) e o MEMFS é volátil — não salva no web.
        if sys.platform == "emscripten":
            return
        # Preparar dados de forma síncrona (sem efeitos colaterais)
        data = self._prepare_save_data()
        path = self.profile_path
        backup_path = self._backup_path

        def _write_to_disk():
            try:
                # Mesma escrita atômica do save síncrono. Aqui ela importa
                # ainda mais: o auto-save roda durante o gameplay, então a
                # janela de escrita coincide com o jogador podendo fechar o
                # jogo a qualquer momento.
                self._write_profile_atomic(path, backup_path, data)
                logger.debug("Async save completed for %s", path)
            except OSError as e:
                logger.error("Async save failed for %s: %s", path, e)
                # Re-marca dirty: senão a mudança se perderia silenciosamente
                # (próximo auto-save tenta de novo). Só ADICIONA dirty, nunca
                # limpa daqui — evita corrida com _mark_dirty no thread principal.
                self._dirty = True

        # Executar escrita em daemon thread (não bloqueia exit)
        thread = threading.Thread(target=_write_to_disk, daemon=True)
        thread.start()

        # Otimista: marca saved já (a escrita confirma em background). Em falha,
        # _write_to_disk re-marca dirty para retry.
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
        self.world_unlocks = self._build_initial_world_unlocks()
        self.current_checkpoint_world = 1
        self.selected_world_id = 1
        self.current_session = None
        self.session_history = []
        self.preferred_difficulty = None
        self.resolution = (1280, 720)  # Default resolution
        self.mouse_control = False
        self.auto_fire = False
        self.unlocked_upgrades = set(DEFAULT_UNLOCKED)
        self.upgrade_loadout = [None] * UPGRADE_SLOT_COUNT
        self.upgrade_keybindings = DEFAULT_KEYBINDINGS[:UPGRADE_SLOT_COUNT]

        # Resetar sistema de estrelas
        self.stars_collected = 0
        self.stars_spent = 0
        self.unlocked_slots = INITIAL_UNLOCKED_SLOTS

        # Resetar naves
        self.unlocked_ships = {DEFAULT_SHIP_ID}
        self.selected_ship = DEFAULT_SHIP_ID

        # Resetar Hall da Fama
        self.high_scores = []

        self.profile_created = datetime.now()
        self.last_played = None
        self._dirty = False
        self._last_save = time.time()

        # Invalidar o cache de stats do perfil anterior (senão get_global_stats
        # devolveria stats velhos até o próximo _mark_dirty).
        self._cached_global_stats = None
        self._stats_dirty = True

        # Salvar o perfil resetado
        self.save()

        logger.info("Perfil do jogador resetado com sucesso!")
