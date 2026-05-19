"""Suporte a controle Xbox (e compatíveis XInput/SDL2) via pygame.joystick.

Centraliza descoberta, hot-plug, dead zone e leitura de eixos/botões em um
único ponto. O resto do jogo consome via ``GameApp.gamepad``.

Convenções para pygame 2.x com Xbox controller (referência: doc oficial em
``código_teste/Texto_Auxílio_implementar_controles.txt``):

- Axis 0/1 = stick esquerdo X/Y
- Axis 3/4 = stick direito X/Y
- Axis 2 = trigger esquerdo (LT), -1 solto → +1 apertado
- Axis 5 = trigger direito (RT)
- Botões 0..9 = A, B, X, Y, LB, RB, Back, Start, L3, R3
- Hat 0 = D-pad
"""

import logging
from typing import Any, Literal, Optional

import pygame

logger = logging.getLogger(__name__)


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
    armazena o layout real em atributos de instância (``axis_lt``, etc.).
    Use os atributos do manager — estas constantes servem só como default.
    """

    LEFT_X = 0
    LEFT_Y = 1
    LT = 2
    RIGHT_X = 3
    RIGHT_Y = 4
    RT = 5


class GamepadManager:
    """Singleton de gerenciamento de gamepad.

    Mantém referência ao primeiro joystick conectado e expõe API uniforme
    para leitura de eixos (com dead zone), botões, D-pad e rumble. O sistema
    de input do jogo só usa o gamepad quando ``is_active`` é True (toggle
    em UserPreferences + dispositivo conectado).
    """

    DEAD_ZONE: float = 0.18
    TRIGGER_THRESHOLD: float = 0.5

    def __init__(self) -> None:
        # ``pygame.joystick.Joystick`` é exposto como factory function nos
        # stubs do Pylance (não como classe), então não dá para anotar com
        # ``Optional[pygame.joystick.Joystick]``. O atributo é Any em tempo
        # de checagem; em runtime é uma instância de Joystick após ``_scan``.
        self._joystick: Optional[Any] = None
        self._enabled: bool = False
        # Estado do D-pad cacheado (último valor lido) para queries síncronas.
        self._hat_state: tuple[int, int] = (0, 0)
        # Layout de eixos detectado em runtime. Default XInput; ``_detect_axis_layout``
        # re-mapeia se identificar PS4-like via posição de repouso dos triggers.
        self.axis_left_x: int = XboxAxis.LEFT_X
        self.axis_left_y: int = XboxAxis.LEFT_Y
        self.axis_lt: int = XboxAxis.LT
        self.axis_right_x: int = XboxAxis.RIGHT_X
        self.axis_right_y: int = XboxAxis.RIGHT_Y
        self.axis_rt: int = XboxAxis.RT

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Inicializa o módulo pygame.joystick e abre o primeiro disponível."""
        if not pygame.joystick.get_init():
            pygame.joystick.init()
        self._scan()

    def _scan(self) -> None:
        """Abre o primeiro joystick disponível, se houver."""
        count = pygame.joystick.get_count()
        if count > 0 and self._joystick is None:
            try:
                joy = pygame.joystick.Joystick(0)
                joy.init()
                self._joystick = joy
                logger.info(
                    "Controle conectado: %s (%d eixos, %d botões, %d hats)",
                    joy.get_name(),
                    joy.get_numaxes(),
                    joy.get_numbuttons(),
                    joy.get_numhats(),
                )
                self._detect_axis_layout()
            except pygame.error as e:
                logger.warning("Falha ao abrir controle: %s", e)
                self._joystick = None

    def _detect_axis_layout(self) -> None:
        """Identifica se o controle reporta layout XInput ou PS4.

        Em pygame 2.x, triggers descansam em -1 (estado solto) e sticks
        descansam em ~0. Layout XInput (Xbox 360/One/PS5 via SDL): LT=axis 2,
        RS=axis 3/4. Layout PS4: RS=axis 2/3, LT=axis 4. Probe checa o valor
        de repouso do axis 2: se < -0.5, é um trigger → XInput. Senão, é um
        stick e o LT está no axis 4 → PS4-like.

        Bug capturado: sem detecção, a leitura de RS Y caía no axis 4 do
        controle PS4 (que na verdade é o LT, em repouso -1) e empurrava
        o cursor virtual constantemente para cima.
        """
        joy = self._joystick
        if joy is None:
            return
        # Pump events força o SDL a flushar os valores iniciais para que
        # get_axis() reflita o estado de repouso e não 0.0 padrão.
        pygame.event.pump()
        try:
            axis2 = joy.get_axis(2)
            axis4 = joy.get_axis(4) if joy.get_numaxes() > 4 else 0.0
        except (pygame.error, IndexError):
            return

        if axis2 < -0.5:
            # XInput / PS5 layout: defaults estão corretos, sem mudança.
            logger.info(
                "Layout detectado: XInput (LT=axis 2, RS=axis 3/4, RT=axis 5)"
            )
        elif axis4 < -0.5:
            # PS4-like: trigger esquerdo migra para axis 4, RS para 2/3.
            self.axis_right_x = 2
            self.axis_right_y = 3
            self.axis_lt = 4
            logger.info(
                "Layout detectado: PS4-like (LT=axis 4, RS=axis 2/3, RT=axis 5)"
            )
        else:
            # Nenhum trigger em repouso reconhecível — fica no default e loga
            # para diagnóstico. Provavelmente um controle não-padrão.
            logger.warning(
                "Não foi possível detectar layout — axis2=%.2f axis4=%.2f. "
                "Usando default XInput. Se RS/LT estiverem trocados, reporte.",
                axis2,
                axis4,
            )

    def handle_event(self, event: pygame.event.Event) -> None:
        """Processa eventos de hot-plug e cacheia estado contínuo (hat)."""
        if event.type == pygame.JOYDEVICEADDED:
            if self._joystick is None:
                self._scan()
            return

        joy = self._joystick
        if joy is None:
            return

        if event.type == pygame.JOYDEVICEREMOVED:
            if event.instance_id == joy.get_instance_id():
                logger.info("Controle desconectado")
                self._joystick = None
                self._hat_state = (0, 0)
                # Tenta re-escanear caso outro controle ainda esteja conectado
                self._scan()
        elif event.type == pygame.JOYHATMOTION:
            if event.instance_id == joy.get_instance_id():
                self._hat_state = event.value

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._joystick is not None

    @property
    def is_active(self) -> bool:
        """True quando habilitado pelo usuário E com dispositivo conectado."""
        return self._enabled and self.connected

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

    def get_axis(self, idx: int) -> float:
        """Valor do eixo com dead zone. Retorna 0.0 se não conectado."""
        joy = self._joystick
        if not self._enabled or joy is None:
            return 0.0
        try:
            return self._apply_dead_zone(joy.get_axis(idx))
        except (pygame.error, IndexError):
            return 0.0

    def get_stick(self, side: Literal["left", "right"]) -> tuple[float, float]:
        """Retorna (x, y) do stick com dead zone aplicado."""
        if side == "left":
            return self.get_axis(self.axis_left_x), self.get_axis(self.axis_left_y)
        return self.get_axis(self.axis_right_x), self.get_axis(self.axis_right_y)

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
        self, side: Literal["left", "right"], dead_zone: float
    ) -> tuple[float, float]:
        """Lê o stick aplicando dead zone customizada com reescala linear.

        Bypassa o ``DEAD_ZONE`` padrão da classe para permitir thresholds
        diferentes por consumidor — gameplay quer alta resposta (zona menor),
        cursor virtual quer baixo drift (zona maior).
        """
        joy = self._joystick
        if not self._enabled or joy is None:
            return (0.0, 0.0)
        ax_x = self.axis_left_x if side == "left" else self.axis_right_x
        ax_y = self.axis_left_y if side == "left" else self.axis_right_y
        try:
            raw_x = joy.get_axis(ax_x)
            raw_y = joy.get_axis(ax_y)
        except (pygame.error, IndexError):
            return (0.0, 0.0)
        return (
            self._rescale_dead_zone(raw_x, dead_zone),
            self._rescale_dead_zone(raw_y, dead_zone),
        )

    def get_trigger(self, side: Literal["left", "right"]) -> float:
        """Retorna 0..1 do trigger. Triggers reportam -1 (solto) a +1 (full)
        em pygame 2.x; normalizamos para 0..1 e ignoramos jitter abaixo do
        dead zone."""
        joy = self._joystick
        if not self._enabled or joy is None:
            return 0.0
        axis = self.axis_lt if side == "left" else self.axis_rt
        try:
            raw = joy.get_axis(axis)
        except (pygame.error, IndexError):
            return 0.0
        # Mapeia [-1, 1] → [0, 1].
        normalized = (raw + 1.0) * 0.5
        if normalized < self.DEAD_ZONE:
            return 0.0
        return max(0.0, min(1.0, normalized))

    def is_button_pressed(self, button: int) -> bool:
        """Estado contínuo do botão (True enquanto segurado)."""
        joy = self._joystick
        if not self._enabled or joy is None:
            return False
        try:
            return bool(joy.get_button(button))
        except (pygame.error, IndexError):
            return False

    def get_dpad(self) -> tuple[int, int]:
        """Posição atual do D-pad como (x, y), valores -1/0/+1."""
        if not self.is_active:
            return (0, 0)
        return self._hat_state

    # ------------------------------------------------------------------
    # Vibração
    # ------------------------------------------------------------------

    def rumble(self, low: float, high: float, ms: int) -> bool:
        """Dispara vibração. Silenciosamente no-op se não suportado."""
        joy = self._joystick
        if not self._enabled or joy is None:
            return False
        try:
            return bool(joy.rumble(low, high, ms))
        except (pygame.error, AttributeError):
            return False

    def stop_rumble(self) -> None:
        joy = self._joystick
        if not self._enabled or joy is None:
            return
        try:
            joy.stop_rumble()
        except (pygame.error, AttributeError):
            pass
