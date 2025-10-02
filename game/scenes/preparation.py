import pygame
from typing import TYPE_CHECKING
from ..core.state import Scene
from ..core.config import Config
from ..render.renderer import Renderer

if TYPE_CHECKING:
    from ..app import GameApp

class PreparationScene(Scene):
    def __init__(self, app: "GameApp"):
        super().__init__(app)
        self.time_left = Config.PREPARATION_TIME
        self.r = Renderer()

    def update(self, dt: float):
        self.time_left -= dt
        if self.time_left <= 0:
            from .playing import PlayingScene
            self.app.states.switch(PlayingScene(self.app))

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            from .playing import PlayingScene
            self.app.states.switch(PlayingScene(self.app))

    def render(self, surface: pygame.Surface):
        self.r.background(surface, dt=2)
        self.r.preparation(surface, self.time_left)
