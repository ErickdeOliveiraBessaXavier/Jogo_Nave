"""Suporte a controle Xbox (e compatíveis XInput/SDL2) via pygame.joystick.

Centraliza descoberta, hot-plug, dead zone e leitura de eixos/botões em um
único ponto. O resto do jogo consome via ``GameApp.gamepad``.

A partir do suporte a multiplayer local, mantém até dois slots de controle
(slot 0 = P1, slot 1 = P2). API legada (sem parâmetro `slot`) sempre opera
no slot 0, preservando compatibilidade com call sites single-player.

Convenções para pygame 2.x com Xbox controller (referência: doc oficial em
``código_teste/Texto_Auxílio_implementar_controles.txt``):

- Axis 0/1 = stick esquerdo X/Y
- Axis 3/4 = stick direito X/Y
- Axis 2 = trigger esquerdo (LT), -1 solto → +1 apertado
- Axis 5 = trigger direito (RT)
- Botões 0..9 = A, B, X, Y, LB, RB, Back, Start, L3, R3
- Hat 0 = D-pad
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List, Literal, Optional

import pygame

logger = logging.getLogger(__name__)


MAX_GAMEPAD_SLOTS: int = 2
"""Quantidade máxima de controles rastreados (P1 + P2)."""


class XboxButton:
    """Índices de botões para Xbox controller em pygame 2.x."""

    A = 0
    B = 1
    X = 2
    Y = 3
    LB = 4
    RB = 5
    BACK = 6
    START = 7
    L3 = 8
    R3 = 9


class XboxAxis:
    """Índices DEFAULT de eixos para Xbox controller em pygame 2.x (XInput).

    Note: alguns drivers/sistemas reportam o controle com layout PS4
    (RS em 2/3, LT em 4). ``GamepadManager`` faz detecção em runtime e
    armazena o layout real em atributos por slot. Estas constantes servem
    só como default inicial.
    """

    LEFT_X = 0
    LEFT_Y = 1
    LT = 2
    RIGHT_X = 3
    RIGHT_Y = 4
    RT = 5


@dataclass
class _GamepadSlotState:
    """Estado por-slot: referência ao joystick + layout detectado + hat cache."""

    joystick: Any
    instance_id: int
    hat_state: tuple[int, int] = (0, 0)
    axis_left_x: int = XboxAxis.LEFT_X
    axis_left_y: int = XboxAxis.LEFT_Y
    axis_lt: int = XboxAxis.LT
    axis_right_x: int = XboxAxis.RIGHT_X
    axis_right_y: int = XboxAxis.RIGHT_Y
    axis_rt: int = XboxAxis.RT


class GamepadManager:
    """Gerenciamento de até dois gamepads simultâneos.

    Slot 0 = P1, slot 1 = P2. API sem parâmetro ``slot`` é equivalente a
    ``slot=0`` por retrocompat — manter assim evita ter que tocar nos 18+
    call sites existentes que assumem um único controle.
    """

    DEAD_ZONE: float = 0.18
    TRIGGER_THRESHOLD: float = 0.5

    def __init__(self) -> None:
        # Lista de slots: posição fixa, None quando vazio. Slot 0 é sempre
        # reservado para P1 — quando um único controle está conectado, vai
        # nele. Segundo controle vai pro slot 1 (candidato a P2).
        self._slots: List[Optional[_GamepadSlotState]] = [None] * MAX_GAMEPAD_SLOTS
        self._enabled: bool = False
        self._prefer_slot_1_for_new_devices: bool = False

    # ------------------------------------------------------------------
    # Backward compat: ``_joystick`` antigo aponta pra slot 0
    # ------------------------------------------------------------------

    @property
    def _joystick(self) -> Optional[Any]:
        """Compat com código legado que lia ``self._joystick`` diretamente."""
        s = self._slots[0]
        return s.joystick if s else None

    @property
    def axis_left_x(self) -> int:
        s = self._slots[0]
        return s.axis_left_x if s else XboxAxis.LEFT_X

    @property
    def axis_left_y(self) -> int:
        s = self._slots[0]
        return s.axis_left_y if s else XboxAxis.LEFT_Y

    @property
    def axis_lt(self) -> int:
        s = self._slots[0]
        return s.axis_lt if s else XboxAxis.LT

    @property
    def axis_right_x(self) -> int:
        s = self._slots[0]
        return s.axis_right_x if s else XboxAxis.RIGHT_X

    @property
    def axis_right_y(self) -> int:
        s = self._slots[0]
        return s.axis_right_y if s else XboxAxis.RIGHT_Y

    @property
    def axis_rt(self) -> int:
        s = self._slots[0]
        return s.axis_rt if s else XboxAxis.RT

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def init(self, prefer_slot_1: bool = False) -> None:
        """Inicializa o módulo pygame.joystick e abre os disponíveis."""
        self._prefer_slot_1_for_new_devices = bool(prefer_slot_1)
        if not pygame.joystick.get_init():
            pygame.joystick.init()
        self._scan()

    def set_primary_keyboard_preference(self, enabled: bool) -> None:
        """Define se controles novos devem priorizar o slot 1 (P2)."""
        enabled = bool(enabled)
        if self._prefer_slot_1_for_new_devices == enabled:
            return
        self._prefer_slot_1_for_new_devices = enabled
        self._rescan_devices()

    def _reset_slots(self) -> None:
        for state in self._slots:
            if state is None:
                continue
            try:
                state.joystick.quit()
            except pygame.error:
                pass
        self._slots = [None] * MAX_GAMEPAD_SLOTS

    def _rescan_devices(self) -> None:
        self._reset_slots()
        self._scan()

    def _scan(self) -> None:
        """Abre joysticks disponíveis preenchendo slots livres em ordem."""
        count = pygame.joystick.get_count()
        for raw_idx in range(count):
            self.add_device(raw_idx, prefer_slot_1=self._prefer_slot_1_for_new_devices)

    def add_device(
        self, device_index: int, prefer_slot_1: Optional[bool] = None
    ) -> Optional[int]:
        """Reivindica um joystick em um slot livre. Retorna o slot ocupado.

        ``prefer_slot_1=True`` reserva o gamepad pro slot 1 (candidato a P2),
        deixando o slot 0 vago — útil quando o caller (app.py) decide que P1
        está jogando teclado e o novo controle deve ser do P2. Se o slot 1
        já estiver ocupado ou inexistente, cai no comportamento padrão de
        preencher o primeiro slot vazio.
        """
        try:
            probe = pygame.joystick.Joystick(device_index)
        except pygame.error:
            return None
        iid = probe.get_instance_id()
        if any(s and s.instance_id == iid for s in self._slots):
            return None  # já mapeado
        target_slot: Optional[int] = None
        if prefer_slot_1 and MAX_GAMEPAD_SLOTS > 1 and self._slots[1] is None:
            target_slot = 1
        if target_slot is None:
            target_slot = self._first_empty_slot()
        if target_slot is None:
            return None
        self._claim_slot(target_slot, probe)
        return target_slot

    def _first_empty_slot(self) -> Optional[int]:
        for i, s in enumerate(self._slots):
            if s is None:
                return i
        return None

    def _claim_slot(self, slot: int, joy: Any) -> None:
        """Inicializa o joystick, detecta layout e ocupa o slot informado."""
        try:
            joy.init()
        except pygame.error as e:
            logger.warning("Falha ao abrir controle: %s", e)
            return
        state = _GamepadSlotState(joystick=joy, instance_id=joy.get_instance_id())
        self._slots[slot] = state
        logger.info(
            "Controle conectado no slot %d (%s): %d eixos, %d botões, %d hats",
            slot,
            joy.get_name(),
            joy.get_numaxes(),
            joy.get_numbuttons(),
            joy.get_numhats(),
        )
        self._detect_axis_layout(slot)

    def _detect_axis_layout(self, slot: int) -> None:
        """Identifica se o controle do slot reporta layout XInput ou PS4.

        Em pygame 2.x, triggers descansam em -1 (estado solto) e sticks
        descansam em ~0. Layout XInput (Xbox 360/One/PS5 via SDL): LT=axis 2,
        RS=axis 3/4. Layout PS4: RS=axis 2/3, LT=axis 4. Probe checa o valor
        de repouso do axis 2: se < -0.5, é um trigger → XInput. Senão, é um
        stick e o LT está no axis 4 → PS4-like.

        Bug capturado: sem detecção, a leitura de RS Y caía no axis 4 do
        controle PS4 (que na verdade é o LT, em repouso -1) e empurrava
        o cursor virtual constantemente para cima.
        """
        state = self._slots[slot]
        if state is None:
            return
        joy = state.joystick
        # Pump events força o SDL a flushar os valores iniciais para que
        # get_axis() reflita o estado de repouso e não 0.0 padrão.
        pygame.event.pump()
        try:
            axis2 = joy.get_axis(2)
            axis4 = joy.get_axis(4) if joy.get_numaxes() > 4 else 0.0
        except (pygame.error, IndexError):
            return

        if axis2 < -0.5:
            logger.info(
                "Slot %d — layout XInput (LT=axis 2, RS=axis 3/4, RT=axis 5)",
                slot,
            )
        elif axis4 < -0.5:
            state.axis_right_x = 2
            state.axis_right_y = 3
            state.axis_lt = 4
            logger.info(
                "Slot %d — layout PS4-like (LT=axis 4, RS=axis 2/3, RT=axis 5)",
                slot,
            )
        else:
            logger.warning(
                "Slot %d — layout indetectável (axis2=%.2f axis4=%.2f). "
                "Usando default XInput.",
                slot,
                axis2,
                axis4,
            )

    def handle_event(self, event: pygame.event.Event) -> None:
        """Processa eventos de hot-plug e cacheia estado contínuo (hat)."""
        if event.type == pygame.JOYDEVICEADDED:
            # Pode encher slot 0 (se vazio) ou slot 1 (candidato P2).
            self._scan()
            return

        if event.type == pygame.JOYDEVICEREMOVED:
            for i, state in enumerate(self._slots):
                if state and state.instance_id == event.instance_id:
                    logger.info("Controle do slot %d desconectado", i)
                    self._slots[i] = None
                    break
            # Re-escanear pra cobrir caso outro controle ainda esteja conectado
            # e possa preencher a vaga liberada.
            self._scan()
            return

        if event.type == pygame.JOYHATMOTION:
            for state in self._slots:
                if state and state.instance_id == event.instance_id:
                    state.hat_state = event.value
                    return

    # ------------------------------------------------------------------
    # Estado por slot
    # ------------------------------------------------------------------

    def is_slot_connected(self, slot: int) -> bool:
        return 0 <= slot < MAX_GAMEPAD_SLOTS and self._slots[slot] is not None

    def is_slot_active(self, slot: int) -> bool:
        """True quando habilitado pelo usuário E slot tem controle conectado."""
        return self._enabled and self.is_slot_connected(slot)

    def slot_instance_id(self, slot: int) -> Optional[int]:
        if not self.is_slot_connected(slot):
            return None
        state = self._slots[slot]
        return state.instance_id if state else None

    def slot_of_instance_id(self, instance_id: int) -> Optional[int]:
        """Slot ocupado por um dado instance_id, ou None se não encontrado.

        Útil pra rotear eventos de botão/axis pelo slot certo durante
        gameplay multiplayer (saber se um JOYBUTTONDOWN veio do P1 ou P2).
        """
        for i, state in enumerate(self._slots):
            if state and state.instance_id == instance_id:
                return i
        return None

    @property
    def connected(self) -> bool:
        """Backward compat: slot 0 conectado."""
        return self.is_slot_connected(0)

    @property
    def is_active(self) -> bool:
        """Backward compat: slot 0 ativo."""
        return self.is_slot_active(0)

    @property
    def secondary_connected(self) -> bool:
        """Há um segundo controle disponível (candidato a P2)?"""
        return self.is_slot_connected(1)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------

    def _apply_dead_zone(self, value: float) -> float:
        if abs(value) < self.DEAD_ZONE:
            return 0.0
        return value

    def get_axis(self, idx: int, slot: int = 0) -> float:
        """Valor do eixo com dead zone. Retorna 0.0 se slot não ativo."""
        if not self.is_slot_active(slot):
            return 0.0
        state = self._slots[slot]
        if state is None:
            return 0.0
        try:
            return self._apply_dead_zone(state.joystick.get_axis(idx))
        except (pygame.error, IndexError):
            return 0.0

    def get_stick(
        self, side: Literal["left", "right"], slot: int = 0
    ) -> tuple[float, float]:
        """Retorna (x, y) do stick com dead zone aplicado."""
        state = self._slots[slot] if 0 <= slot < MAX_GAMEPAD_SLOTS else None
        if state is None:
            return (0.0, 0.0)
        if side == "left":
            return (
                self.get_axis(state.axis_left_x, slot),
                self.get_axis(state.axis_left_y, slot),
            )
        return (
            self.get_axis(state.axis_right_x, slot),
            self.get_axis(state.axis_right_y, slot),
        )

    @staticmethod
    def _rescale_dead_zone(value: float, dead_zone: float) -> float:
        """Aplica dead zone com reescala linear pós-zona morta.

        Diferente do ``_apply_dead_zone`` simples (que só zera abaixo do limite),
        este reescala valores acima da zona morta para [0..1], evitando o ``salto``
        de 0 → ~0.2 quando a haste sai do centro. Útil para controle de cursor:
        sem reescala, sticks com drift > dead zone produzem deslocamentos
        constantes (cursor ``escorrega`` lentamente até a borda da tela).
        """
        abs_v = abs(value)
        if abs_v < dead_zone or dead_zone >= 1.0:
            return 0.0
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs_v - dead_zone) / (1.0 - dead_zone)

    def get_stick_rescaled(
        self,
        side: Literal["left", "right"],
        dead_zone: float,
        slot: int = 0,
    ) -> tuple[float, float]:
        """Lê o stick aplicando dead zone customizada com reescala linear.

        Bypassa o ``DEAD_ZONE`` padrão da classe para permitir thresholds
        diferentes por consumidor — gameplay quer alta resposta (zona menor),
        cursor virtual quer baixo drift (zona maior).
        """
        if not self.is_slot_active(slot):
            return (0.0, 0.0)
        state = self._slots[slot]
        if state is None:
            return (0.0, 0.0)
        ax_x = state.axis_left_x if side == "left" else state.axis_right_x
        ax_y = state.axis_left_y if side == "left" else state.axis_right_y
        try:
            raw_x = state.joystick.get_axis(ax_x)
            raw_y = state.joystick.get_axis(ax_y)
        except (pygame.error, IndexError):
            return (0.0, 0.0)
        return (
            self._rescale_dead_zone(raw_x, dead_zone),
            self._rescale_dead_zone(raw_y, dead_zone),
        )

    def get_trigger(
        self, side: Literal["left", "right"], slot: int = 0
    ) -> float:
        """Retorna 0..1 do trigger. Triggers reportam -1 (solto) a +1 (full)
        em pygame 2.x; normalizamos para 0..1 e ignoramos jitter abaixo do
        dead zone."""
        if not self.is_slot_active(slot):
            return 0.0
        state = self._slots[slot]
        if state is None:
            return 0.0
        axis = state.axis_lt if side == "left" else state.axis_rt
        try:
            raw = state.joystick.get_axis(axis)
        except (pygame.error, IndexError):
            return 0.0
        normalized = (raw + 1.0) * 0.5
        if normalized < self.DEAD_ZONE:
            return 0.0
        return max(0.0, min(1.0, normalized))

    def is_button_pressed(self, button: int, slot: int = 0) -> bool:
        """Estado contínuo do botão (True enquanto segurado)."""
        if not self.is_slot_active(slot):
            return False
        state = self._slots[slot]
        if state is None:
            return False
        try:
            return bool(state.joystick.get_button(button))
        except (pygame.error, IndexError):
            return False

    def get_dpad(self, slot: int = 0) -> tuple[int, int]:
        """Posição atual do D-pad como (x, y), valores -1/0/+1."""
        if not self.is_slot_active(slot):
            return (0, 0)
        state = self._slots[slot]
        return state.hat_state if state else (0, 0)

    # ------------------------------------------------------------------
    # Vibração
    # ------------------------------------------------------------------

    def rumble(self, low: float, high: float, ms: int, slot: int = 0) -> bool:
        """Dispara vibração no slot indicado. No-op se não suportado."""
        if not self.is_slot_active(slot):
            return False
        state = self._slots[slot]
        if state is None:
            return False
        try:
            return bool(state.joystick.rumble(low, high, ms))
        except (pygame.error, AttributeError):
            return False

    def stop_rumble(self, slot: int = 0) -> None:
        if not self.is_slot_active(slot):
            return
        state = self._slots[slot]
        if state is None:
            return
        try:
            state.joystick.stop_rumble()
        except (pygame.error, AttributeError):
            pass
