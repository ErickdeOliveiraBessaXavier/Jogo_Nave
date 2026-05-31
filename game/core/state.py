from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

import pygame

from .config import config as Config

if TYPE_CHECKING:
    from ..app import GameApp


class Scene(ABC):
    def __init__(self, app: "GameApp") -> None:
        self.app = app
        # Escala de UI relativa ao design base (1280×720). O jogo roda com
        # pygame.SCALED numa resolução lógica escolhida; pixels fixos de UI
        # precisam deste fator para não ficarem desproporcionais fora de 720p
        # (CLAUDE.md §12). Em 720p ui_scale == 1.0. Resoluções são 16:9, então
        # um único fator cobre os dois eixos. Subclasses usam self._s(px).
        self.ui_scale: float = Config.SCREEN_WIDTH / 1280.0

    def _s(self, value: float) -> int:
        """Escala um valor de pixel do design base para a resolução lógica
        atual. Em 720p retorna o valor original (ui_scale == 1.0)."""
        return int(value * self.ui_scale)

    def enter(self):
        pass

    def exit(self):
        pass

    def handle_event(self, event: pygame.event.Event):
        pass

    def get_focusable_rects(self) -> List[pygame.Rect]:
        """Lista opcional de áreas clicáveis para snap-focus via controle.

        Cenas que implementarem retornam os rects dos elementos interativos
        (botões, cards, slots). O app.py usa essa lista para mover o cursor
        virtual entre elementos quando o jogador aperta o DPad, emulando
        navegação por Tab. Lista vazia = cena fica no fallback de KEYDOWN
        sintético (DPad → setas), comportamento atual.
        """
        return []

    @abstractmethod
    def update(self, dt: float): ...

    @abstractmethod
    def render(self, surface: pygame.Surface): ...


class StateManager:
    def __init__(self):
        self._stack: List[Scene] = []

    def push(self, scene: Scene):
        """Pushes a new scene onto the stack without affecting the one below."""
        self._stack.append(scene)
        scene.enter()

    def pop(self):
        """Pops the current scene and re-enters the one below."""
        if self._stack:
            scene = self._stack.pop()
            scene.exit()
        if self._stack:
            self._stack[-1].enter()

    def switch(self, scene: Scene):
        """Switches the current scene with a new one."""
        if self._stack:
            old_scene = self._stack.pop()
            old_scene.exit()
        self._stack.append(scene)
        scene.enter()

    def current(self) -> Optional[Scene]:
        if not self._stack:
            return None
        return self._stack[-1]

    @property
    def stack_length(self) -> int:
        """Returns the number of scenes in the stack."""
        return len(self._stack)
