import pygame
from ..core.state import Scene
from ..render.renderer import Renderer

class GameOverScene(Scene):
    def __init__(self, app, score: int):
        super().__init__(app)
        self.score = score
        self.r = Renderer()

    def update(self, dt: float):
        pass

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
            from .preparation import PreparationScene
            self.app.states.switch(PreparationScene(self.app))

    def render(self, surface: pygame.Surface):
        self.r.overlay(surface, "", f"Score: {self.score} — Pressione R para reiniciar")
