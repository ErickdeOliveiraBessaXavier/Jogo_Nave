import pygame
from .core.state import StateManager
from .core.config import Config, set_screen_resolution
from .scenes.main_menu import MainMenuScene
from .core.levels import LevelManager, FIXED_LEVELS
from .core.input import Input


class GameApp:
    def __init__(self):
        pygame.init()
        
        # Detectar resolução do monitor se estiver em fullscreen
        if Config.FULLSCREEN:
            # Obter informações do display
            info = pygame.display.Info()
            screen_width = info.current_w
            screen_height = info.current_h
        else:
            # Usar resolução configurada
            screen_width = Config.SCREEN_WIDTH
            screen_height = Config.SCREEN_HEIGHT
        
        # Atualizar Config com a resolução detectada/configurada
        set_screen_resolution(screen_width, screen_height)
        
        # Armazenar resolução para uso em outras classes
        self.screen_width = screen_width
        self.screen_height = screen_height
        
        # Criar display com fullscreen se ativado
        flags = pygame.FULLSCREEN if Config.FULLSCREEN else 0
        self.screen = pygame.display.set_mode(
            (screen_width, screen_height),
            flags
        )
        
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
                elif event.type == pygame.KEYDOWN:
                    # F12: Toggle fullscreen/windowed
                    if event.key == pygame.K_F12:
                        self._toggle_fullscreen()
                    # ESC: Exit game
                    elif event.key == pygame.K_ESCAPE:
                        self.running = False
                    else:
                        # Pass other key events to current scene
                        current_scene = self.states.current()
                        if current_scene:
                            current_scene.handle_event(event)
                else:
                    # Pass other events to current scene
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

    def _toggle_fullscreen(self):
        """Alterna entre modo fullscreen e janela."""
        if self.screen.get_flags() & pygame.FULLSCREEN:
            # Mudar para modo janela
            set_screen_resolution(self.screen_width, self.screen_height)
            self.screen = pygame.display.set_mode(
                (self.screen_width, self.screen_height),
                0  # Sem flag FULLSCREEN
            )
        else:
            # Mudar para modo fullscreen
            info = pygame.display.Info()
            new_width = info.current_w
            new_height = info.current_h
            set_screen_resolution(new_width, new_height)
            self.screen = pygame.display.set_mode(
                (new_width, new_height),
                pygame.FULLSCREEN
            )
            self.screen_width = new_width
            self.screen_height = new_height
        
        pygame.display.set_caption("Space Shooter")


def main():
    app = GameApp()
    app.run()


if __name__ == "__main__":
    main()
