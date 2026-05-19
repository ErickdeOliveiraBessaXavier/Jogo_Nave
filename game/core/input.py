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
            elif event.type == pygame.JOYBUTTONDOWN and gamepad is not None and gamepad.is_active:
                action = BUTTONMAP_GAMEPLAY.get(event.button)
                if action is not None:
                    actions.add(action)
        return actions

    def poll_held(self, gamepad: Optional[GamepadManager] = None) -> set[str]:
        held: set[str] = set()
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

        if gamepad is not None and gamepad.is_active:
            held |= self._poll_held_gamepad(gamepad)

        return held

    def _poll_held_gamepad(self, gp: GamepadManager) -> set[str]:
        """Lê estado contínuo do controle e mapeia para ações de hold.

        Em gameplay o D-pad é reservado para o modo de seleção de upgrade
        (tratado em playing.py), então NÃO entra em ações de movimento.
        Movimento vem só do stick esquerdo; a magnitude exata é exposta em
        ``gamepad_movement_vector``. Tiro contínuo vem do RT (gatilho
        direito) — apertar segura, soltar para. LT fica reservado para
        habilidades especiais (dash / charge shot).
        """
        held: set[str] = set()

        lx, ly = gp.get_stick("left")
        if lx < 0:
            held.add("hold_left")
        if lx > 0:
            held.add("hold_right")
        if ly < 0:
            held.add("hold_up")
        if ly > 0:
            held.add("hold_down")

        if gp.get_trigger("right") > GamepadManager.TRIGGER_THRESHOLD:
            held.add("hold_shoot")

        return held

    def gamepad_movement_vector(
        self, gamepad: Optional[GamepadManager]
    ) -> tuple[float, float]:
        """Vetor de movimento (x, y) com magnitude do stick esquerdo.

        Cada componente já tem dead zone aplicada (vale 0.0 fora da zona).
        Retorna (0, 0) se nenhum gamepad ativo. Permite ``ship.move`` aplicar
        velocidade proporcional à inclinação do stick.
        """
        if gamepad is None or not gamepad.is_active:
            return (0.0, 0.0)
        return gamepad.get_stick("left")
