import pygame
from .core.config import Config
from .core.state import StateManager
from .scenes.preparation import PreparationScene
from .core.input import Input


class GameApp:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(
            (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
        )
        pygame.display.set_caption("Structured Pygame Template")
        self.clock = pygame.time.Clock()
        self.states = StateManager()
        self.input = Input()
        self.states.push(PreparationScene(self))

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(Config.FPS) / 1000.0

            # event -> actions (we keep direct events for scenes that need
            # them)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    break
                self.states.current().handle_event(event)

            # update & render
            self.states.current().update(dt)
            self.states.current().render(self.screen)
            pygame.display.flip()

        pygame.quit()
