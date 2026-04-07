from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

import pygame

if TYPE_CHECKING:
    from ..app import GameApp


class Scene(ABC):
    def __init__(self, app: "GameApp") -> None:
        self.app = app

    def enter(self):
        pass

    def exit(self):
        pass

    def handle_event(self, event: pygame.event.Event):
        pass

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
