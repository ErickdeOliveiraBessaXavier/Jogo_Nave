from __future__ import annotations

import pygame


CHEAT_CODE = "271195"


class CheatBuffer:
    """Acumula dígitos de KEYDOWN e sinaliza quando o cheat code é digitado.

    Cada cena instancia o próprio buffer e define a ação ao matchar — esta
    classe centraliza apenas a lógica de acumulação/match para que o código
    secreto e o tamanho do buffer não precisem ser redefinidos por cena.
    """

    def __init__(self, code: str = CHEAT_CODE) -> None:
        self.code: str = code
        self._max_len: int = len(code)
        self.buffer: str = ""

    def feed(self, event: pygame.event.Event) -> bool:
        """Alimenta o buffer com um KEYDOWN. Retorna True ao bater o code.

        Após match, o buffer é resetado para permitir múltiplos toggles.
        Qualquer tecla fora de [0-9] também reseta.
        """
        if not pygame.K_0 <= event.key <= pygame.K_9:
            self.buffer = ""
            return False

        self.buffer += chr(event.key)
        if len(self.buffer) > self._max_len:
            self.buffer = self.buffer[-self._max_len :]

        if self.buffer == self.code:
            self.buffer = ""
            return True
        return False

    def reset(self) -> None:
        self.buffer = ""
