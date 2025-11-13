import pygame
from typing import TYPE_CHECKING
from ..core.state import Scene
from ..render.renderer import Renderer

if TYPE_CHECKING:
    from ..app import GameApp


class GameOverScene(Scene):
    def __init__(self, app: "GameApp", score: int):
        super().__init__(app)
        self.score = score
        self.r = Renderer()

    def update(self, dt: float):
        pass

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
            from .playing import PlayingScene

            self.app.states.switch(PlayingScene(self.app, self.app.level_manager))

    def render(self, surface: pygame.Surface):
        self.r.overlay(
            surface,
            "",
            f"Score: {
                self.score} — Pressione R para reiniciar",
        )
