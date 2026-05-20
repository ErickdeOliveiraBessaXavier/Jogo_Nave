"""level_progression_controller.py — Controlador isolado de progressão de níveis.

Extrai de PlayingScene: rastreio de progresso da fase, contagem de hostis,
avanço entre níveis e emissão de LevelCleared.

PlayingScene não é referenciada — comunicação via retornos de status (enum)
e atributos públicos. Decisões de FSM de cena/cutscene permanecem na cena.
"""

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Optional

from ..core.levels import LevelConfig, get_level_config
from ..core.meta_progression_service import MetaProgressionService
from ..events import game_events as events

if TYPE_CHECKING:
    from ..core.difficulty import DifficultyPreset
    from ..core.events import EventBus
    from ..systems.entity_manager import EntityManager
    from ..systems.spawner import EnemySpawner

logger = logging.getLogger(__name__)


class ProgressionStatus(Enum):
    """Estado da progressão após avaliação em check_progression()."""

    NONE = auto()            # Threshold ainda não atingido
    CLEANUP_NEEDED = auto()  # Threshold atingido, hostis restantes em tela
    BOSS_READY = auto()      # Threshold atingido, tela limpa, boss disponível
    LEVEL_CLEARED = auto()   # Threshold atingido, tela limpa, sem boss


class LevelProgressionController:
    """Rastreia progresso da fase, estatísticas e avanço entre níveis.

    Responsabilidades:
    - Cache de thresholds (enemies_to_clear, has_boss, score multiplier)
    - Contagem de inimigos abatidos / dano sofrido / powerups coletados
    - Início do timer da fase e registro de tentativa/clear no perfil
    - Emissão de LevelCleared event
    - Carregamento de LevelConfig ajustado via MetaProgressionService
    - Avanço para próximo nível (índice + spawner)

    Comunicação com PlayingScene:
    - check_progression() retorna ProgressionStatus; a cena decide a ação.
    - notify_*() recebem deltas de gameplay (kills, dano, powerups).
    - advance_to_next_level() incrementa índice e devolve o novo LevelConfig.
    - Atributos públicos (level_start_score, current_level_number, etc.) são
      lidos pela cena conforme necessário.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        event_bus: EventBus,
        enemy_spawner: EnemySpawner,
        player_profile: Any,
        difficulty_preset: DifficultyPreset,
        difficulty_settings: dict[str, Any],
    ) -> None:
        self._em = entity_manager
        self._bus = event_bus
        self._enemy_spawner = enemy_spawner
        self._player_profile = player_profile
        self._difficulty_preset = difficulty_preset
        self._difficulty_settings = difficulty_settings

        # Configuração da fase atual
        self.current_level_index: int = 0
        self.level_config: Optional[LevelConfig] = None
        self.enemies_to_clear: int = 0
        self.has_boss: bool = False
        self.base_score_multiplier: float = 1.0

        # Estatísticas da fase atual
        self.enemies_destroyed_in_level: int = 0
        self.level_start_time: Optional[float] = None
        self.level_start_score: int = 0
        self.level_damage_taken: int = 0
        self.level_powerups_collected: int = 0
        self.level_attempt_recorded: bool = False

    @property
    def current_level_number(self) -> int:
        """Número 1-based do nível atual."""
        return self.current_level_index + 1

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup(self, level_index: int, level_config: LevelConfig) -> None:
        """Inicializa o controlador para o nível inicial."""
        self.current_level_index = level_index
        self.level_config = level_config
        self._cache_thresholds()
        self._recompute_score_multiplier()
        self.reset_level_stats()

    def get_adjusted_level_config(self, level_number: int) -> LevelConfig:
        """Carrega LevelConfig ajustado pelo meta-progression."""
        base = get_level_config(level_number, self._difficulty_preset)
        return MetaProgressionService.get_adjusted_config(self._player_profile, base)

    def _cache_thresholds(self) -> None:
        assert self.level_config is not None
        self.enemies_to_clear = self.level_config.enemies_to_clear
        self.has_boss = bool(self.level_config.boss_type)

    def _recompute_score_multiplier(self) -> None:
        assert self.level_config is not None
        self.base_score_multiplier = (
            self.level_config.score_multiplier
            * self._difficulty_settings["rewards_multiplier"]
        )

    def reset_level_stats(self) -> None:
        """Zera estatísticas/timer da fase. Não altera índice/config."""
        self.enemies_destroyed_in_level = 0
        self.level_start_time = None
        self.level_start_score = 0
        self.level_damage_taken = 0
        self.level_powerups_collected = 0
        self.level_attempt_recorded = False

    # ------------------------------------------------------------------
    # Notificações de gameplay
    # ------------------------------------------------------------------

    def notify_enemies_destroyed(self, count: int = 1) -> None:
        self.enemies_destroyed_in_level += count

    def notify_damage_taken(self, amount: int = 1) -> None:
        self.level_damage_taken += amount

    def notify_powerup_collected(self) -> None:
        self.level_powerups_collected += 1

    # ------------------------------------------------------------------
    # Ciclo de vida da fase
    # ------------------------------------------------------------------

    def start_level_timer(self, current_score: int) -> None:
        """Inicia timer e baseline de score. No-op se já iniciado."""
        if self.level_start_time is None:
            self.level_start_time = time.time()
            self.level_start_score = current_score

    def record_attempt_if_needed(self) -> None:
        """Registra tentativa no perfil uma única vez por fase."""
        if not self.level_attempt_recorded:
            self._player_profile.record_attempt(self.current_level_number)
            self.level_attempt_recorded = True

    def count_active_hostiles(self) -> int:
        """Hostis vivos relevantes para conclusão da fase."""
        em = self._em
        active_enemies = sum(1 for e in em.enemies if not getattr(e, "dead", False))
        active_formation_enemies = sum(
            1
            for f in em.formations
            if not getattr(f, "dead", False)
            for e in f.get_enemies()
            if not getattr(e, "dead", False)
        )
        active_boulders = sum(1 for m in em.boulders if not m.dead)
        active_attack_debris = sum(1 for s in em.attack_debris if not s.dead)
        active_orbital_debris = sum(
            1
            for r in em.orbital_debris
            if not r.dead and getattr(r, "causes_damage", False)
        )
        return (
            active_enemies
            + active_formation_enemies
            + active_boulders
            + active_attack_debris
            + active_orbital_debris
        )

    def check_progression(self) -> ProgressionStatus:
        """Avalia progresso e retorna o que a cena deve fazer.

        Quando o threshold é atingido, pausa o spawner antes de retornar.
        """
        if self.enemies_destroyed_in_level < self.enemies_to_clear:
            return ProgressionStatus.NONE

        self._enemy_spawner.stop()

        if self.count_active_hostiles() > 0:
            return ProgressionStatus.CLEANUP_NEEDED
        if self.has_boss:
            return ProgressionStatus.BOSS_READY
        return ProgressionStatus.LEVEL_CLEARED

    def record_clear(self, current_score: int, total_enemies_destroyed: int) -> None:
        """Registra clear no perfil e emite LevelCleared.

        No-op se o timer da fase nunca iniciou (ex.: avanço sem PLAYING).
        """
        if self.level_start_time is None:
            return
        clear_time = time.time() - self.level_start_time
        level_score = current_score - self.level_start_score
        self._player_profile.record_clear(
            level_number=self.current_level_number,
            time_taken=clear_time,
            score=level_score,
            enemies_killed=total_enemies_destroyed,
            damage_taken=self.level_damage_taken,
            powerups_collected=self.level_powerups_collected,
        )
        self._bus.emit(
            events.LevelCleared(
                level_number=self.current_level_number,
                score=level_score,
                time_taken=clear_time,
            )
        )

    def advance_to_next_level(self, is_world_transition: bool) -> LevelConfig:
        """Incrementa índice, carrega config, zera estatísticas, atualiza spawner.

        Retorna o novo LevelConfig para a cena sincronizar seus atributos.
        """
        self.current_level_index += 1
        self.level_config = self.get_adjusted_level_config(self.current_level_number)
        self._cache_thresholds()
        self._recompute_score_multiplier()
        self.reset_level_stats()
        self._enemy_spawner.set_level(
            self.current_level_number,
            is_world_transition=is_world_transition,
            level_config=self.level_config,
        )
        return self.level_config
