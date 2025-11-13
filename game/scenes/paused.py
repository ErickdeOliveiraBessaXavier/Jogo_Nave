import pygame
from typing import TYPE_CHECKING, Optional
from ..core.state import Scene
from ..render.renderer import Renderer

if TYPE_CHECKING:
    from ..app import GameApp


class PausedScene(Scene):
    def __init__(self, app: "GameApp", previous_scene: Optional[Scene] = None):
        super().__init__(app)
        self.r = Renderer()
        self.previous_scene = previous_scene  # Armazena a cena anterior

    def update(self, dt: float):
        # Não atualiza nada durante a pausa
        pass

    def handle_event(self, event: pygame.event.Event):
        import pygame

        if event.type == pygame.KEYDOWN and event.key == pygame.K_p:
            # Volta para a cena anterior (Playing) sem criar nova instância
            if self.previous_scene:
                self.app.states.switch(self.previous_scene)
            else:
                # Fallback caso não tenha cena anterior
                from .playing import PlayingScene

                self.app.states.switch(PlayingScene(self.app, self.app.level_manager))

    def render(self, surface: pygame.Surface):
        # Renderiza a cena anterior primeiro (congelada)
        if self.previous_scene:
            self.previous_scene.render(surface)

        # Desenha overlay de pausa por cima
        self.r.overlay(surface, "PAUSADO", "Pressione P para continuar")
