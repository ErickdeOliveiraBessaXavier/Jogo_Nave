import pygame
from abc import ABC, abstractmethod

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
    def update(self, dt: float):
        ...

    @abstractmethod
    def render(self, surface: pygame.Surface):
        ...

class StateManager:
    def __init__(self):
        self._stack: list[Scene] = []

    def push(self, scene: Scene):
        if self._stack:
            self._stack[-1].exit()
        self._stack.append(scene)
        scene.enter()

    def pop(self):
        if self._stack:
            s = self._stack.pop()
            s.exit()
        if self._stack:
            self._stack[-1].enter()

    def switch(self, scene: Scene):
        self.pop()
        self.push(scene)

    def current(self) -> Scene:
        return self._stack[-1]
