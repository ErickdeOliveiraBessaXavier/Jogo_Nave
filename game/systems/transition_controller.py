from __future__ import annotations

from enum import Enum, auto


class TransitionPhase(Enum):
    """Fases da FSM de transição entre níveis/mundos.

    `PLAYING` é o estado padrão de gameplay. As demais formam o caminho de
    encerramento de fase: delay de vitória → espera de animação → cutscene
    (se mundo trocou) → painel → preparação do próximo nível.
    """

    PLAYING = auto()
    POST_VICTORY_DELAY = auto()
    LEVEL_TRANSITION_WAIT = auto()
    CUTSCENE_EXIT = auto()
    WORLD_PANEL = auto()
    LEVEL_ENTRY = auto()


class TransitionController:
    """Owner da FSM `TransitionPhase` e seus timers.

    Mantém o estado e o tick — a cena consulta gates (`is_*`,
    `can_handle_gameplay_actions`) e chama `update_post_victory(dt)` /
    `update_level_transition_wait(dt, ...)` por frame para avançar as fases.
    Cutscene visual de transição de mundo continua na cena.
    """

    def __init__(
        self,
        post_victory_delay: float,
        level_transition_delay: float,
        animation_timeout: float,
    ) -> None:
        self.phase: TransitionPhase = TransitionPhase.LEVEL_ENTRY

        # Timers tickados nos métodos `update_*`.
        self.level_transition_timer: float = 0.0
        self.level_transition_pending_timer: float = 0.0

        # Janelas configuradas (lidas do `Config`).
        self.level_transition_delay: float = level_transition_delay
        self.level_transition_pending_delay: float = post_victory_delay
        self.level_transition_animation_timeout: float = animation_timeout

    # ------------------------------------------------------------------
    # Mutação de fase
    # ------------------------------------------------------------------

    def set_phase(self, phase: TransitionPhase) -> None:
        """Define a fase atual e reseta os timers das fases que ficaram para trás."""
        self.phase = phase
        if phase != TransitionPhase.POST_VICTORY_DELAY:
            self.level_transition_pending_timer = 0.0
        if phase != TransitionPhase.LEVEL_TRANSITION_WAIT:
            self.level_transition_timer = 0.0

    # ------------------------------------------------------------------
    # Gates de fase
    # ------------------------------------------------------------------

    @property
    def is_playing(self) -> bool:
        return self.phase == TransitionPhase.PLAYING

    @property
    def is_post_victory_delay(self) -> bool:
        return self.phase == TransitionPhase.POST_VICTORY_DELAY

    @property
    def is_level_transition_wait(self) -> bool:
        return self.phase == TransitionPhase.LEVEL_TRANSITION_WAIT

    @property
    def is_cutscene_exit(self) -> bool:
        return self.phase == TransitionPhase.CUTSCENE_EXIT

    @property
    def is_world_panel(self) -> bool:
        return self.phase == TransitionPhase.WORLD_PANEL

    @property
    def can_handle_gameplay_actions(self) -> bool:
        """True quando o jogador pode agir normalmente."""
        return self.phase == TransitionPhase.PLAYING

    # ------------------------------------------------------------------
    # Ticks
    # ------------------------------------------------------------------

    def update_post_victory(self, dt: float) -> None:
        """Avança o timer de POST_VICTORY_DELAY e migra para LEVEL_TRANSITION_WAIT."""
        if not self.is_post_victory_delay:
            return
        self.level_transition_pending_timer += dt
        if (
            self.level_transition_pending_timer
            >= self.level_transition_pending_delay
        ):
            self.set_phase(TransitionPhase.LEVEL_TRANSITION_WAIT)

    def update_level_transition_wait(self, dt: float, animations_finished: bool) -> bool:
        """Avança o timer de LEVEL_TRANSITION_WAIT.

        Returns:
            True quando é hora de a cena chamar `_start_next_level()`
            (delay completo + animações terminadas, ou timeout duro).
        """
        if not self.is_level_transition_wait:
            return False
        self.level_transition_timer += dt
        if self.level_transition_timer < self.level_transition_delay:
            return False
        timed_out = self.level_transition_timer >= (
            self.level_transition_delay + self.level_transition_animation_timeout
        )
        return animations_finished or timed_out
