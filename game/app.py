import pygame
from .core.state import StateManager
from .core.config import Config
from .scenes.main_menu import MainMenuScene
from .core.levels import LevelManager, FIXED_LEVELS
from .core.input import Input


class GameApp:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))
        pygame.display.set_caption("Space Shooter")
        self.clock = pygame.time.Clock()
        self.running = True
        
        self.states: StateManager = StateManager()
        self.level_manager = LevelManager(FIXED_LEVELS)
        self.input: Input = Input()
        
        # Start with main menu
        self.states.push(MainMenuScene(self))

    def run(self):
        while self.running:
            dt = self.clock.tick(Config.FPS) / 1000.0
            
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                else:
                    # Pass events to current scene
                    current_scene = self.states.current()
                    if current_scene:
                        current_scene.handle_event(event)
            
            # Update
            current_scene = self.states.current()
            if current_scene:
                current_scene.update(dt)
            
            # Render
            current_scene = self.states.current()
            if current_scene:
                current_scene.render(self.screen)
            
            pygame.display.flip()
        
        pygame.quit()


def main():
    app = GameApp()
    app.run()


if __name__ == "__main__":
    main()
