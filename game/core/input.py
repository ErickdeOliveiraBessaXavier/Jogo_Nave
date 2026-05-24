from typing import Optional

import pygame

from .gamepad import GamepadManager, XboxButton

KEYMAP = {
    pygame.K_LEFT: "move_left",
    pygame.K_a: "move_left",
    pygame.K_RIGHT: "move_right",
    pygame.K_d: "move_right",
    pygame.K_UP: "move_up",
    pygame.K_w: "move_up",
    pygame.K_DOWN: "move_down",
    pygame.K_s: "move_down",
    pygame.K_SPACE: "shoot",
    pygame.K_RETURN: "shoot",
    pygame.K_p: "pause",
    pygame.K_r: "restart",
    pygame.K_ESCAPE: "quit",
}

# Botões Xbox em ações discretas (KEYDOWN equivalente). A direção do D-pad
# é tratada em outro caminho (eventos sintéticos no app.py). O tiro normal
# saiu daqui — agora é acionado pelo RT (trigger direito) via
# ``_poll_held_gamepad``.
BUTTONMAP_GAMEPLAY = {
    XboxButton.START: "pause",
}


class Input:
    def poll_events(self, gamepad: Optional[GamepadManager] = None) -> set[str]:
        actions: set[str] = set()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                actions.add("quit")
            elif event.type == pygame.KEYDOWN:
                if event.key in KEYMAP:
                    actions.add(KEYMAP[event.key])
            elif (
                event.type == pygame.JOYBUTTONDOWN
                and gamepad is not None
                and gamepad.is_active
            ):
                action = BUTTONMAP_GAMEPLAY.get(event.button)
                if action is not None:
                    actions.add(action)
        return actions

    def poll_held(self, gamepad: Optional[GamepadManager] = None) -> set[str]:
        """Estado contínuo agregando teclado + gamepad do P1 (slot 0).

        Mantida com assinatura legada para call sites que não conhecem o
        conceito de slot; equivale a ``poll_held_for(gamepad, slot=0)``.
        """
        return self.poll_held_for(gamepad, slot=0)

    def poll_held_for(
        self, gamepad: Optional[GamepadManager], slot: int = 0
    ) -> set[str]:
        """Estado contínuo do slot indicado.

        Slot 0 (P1) inclui teclado + gamepad. Demais slots leem apenas
        gamepad — P2/P3 jogam exclusivamente com controle, sem fallback
        para teclado para evitar conflito de input com P1.

        Em modo coop (2 gamepads conectados), o teclado é suprimido
        automaticamente para evitar conflito de inputs — P1 joga só com
        o controle do slot 0, P2 só com o slot 1. Sem essa supressão,
        teclas WASD vazariam pra P1 mesmo quando ele está usando gamepad.
        """
        held: set[str] = set()

        coop_active = (
            gamepad is not None
            and gamepad.is_slot_active(0)
            and gamepad.is_slot_active(1)
        )

        if slot == 0 and not coop_active:
            keys = pygame.key.get_pressed()
            if keys[pygame.K_LEFT] or keys[pygame.K_a]:
                held.add("hold_left")
            if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                held.add("hold_right")
            if keys[pygame.K_UP] or keys[pygame.K_w]:
                held.add("hold_up")
            if keys[pygame.K_DOWN] or keys[pygame.K_s]:
                held.add("hold_down")
            if keys[pygame.K_SPACE] or keys[pygame.K_RETURN]:
                held.add("hold_shoot")

        if gamepad is not None and gamepad.is_slot_active(slot):
            held |= self._poll_held_gamepad(gamepad, slot)

        return held

    def _poll_held_gamepad(self, gp: GamepadManager, slot: int = 0) -> set[str]:
        """Lê estado contínuo do controle do slot e mapeia para ações de hold.

        Em gameplay o D-pad é reservado para o modo de seleção de upgrade
        (tratado em playing.py), então NÃO entra em ações de movimento.
        Movimento vem só do stick esquerdo; a magnitude exata é exposta em
        ``gamepad_movement_vector``. Tiro contínuo vem do RT (gatilho
        direito) — apertar segura, soltar para. LT fica reservado para
        habilidades especiais (dash / charge shot).
        """
        held: set[str] = set()

        lx, ly = gp.get_stick("left", slot=slot)
        if lx < 0:
            held.add("hold_left")
        if lx > 0:
            held.add("hold_right")
        if ly < 0:
            held.add("hold_up")
        if ly > 0:
            held.add("hold_down")

        if gp.get_trigger("right", slot=slot) > GamepadManager.TRIGGER_THRESHOLD:
            held.add("hold_shoot")

        return held

    def gamepad_movement_vector(
        self, gamepad: Optional[GamepadManager]
    ) -> tuple[float, float]:
        """Vetor de movimento (x, y) com magnitude do stick esquerdo do P1.

        Mantida com assinatura legada; equivale a
        ``gamepad_movement_vector_for(gamepad, slot=0)``.
        """
        return self.gamepad_movement_vector_for(gamepad, slot=0)

    def gamepad_movement_vector_for(
        self, gamepad: Optional[GamepadManager], slot: int = 0
    ) -> tuple[float, float]:
        """Vetor de movimento (x, y) com magnitude do stick esquerdo do slot.

        Cada componente já tem dead zone aplicada (vale 0.0 fora da zona).
        Retorna (0, 0) se o slot não tem gamepad ativo. Permite ``ship.move``
        aplicar velocidade proporcional à inclinação do stick.
        """
        if gamepad is None or not gamepad.is_slot_active(slot):
            return (0.0, 0.0)
        return gamepad.get_stick("left", slot=slot)
