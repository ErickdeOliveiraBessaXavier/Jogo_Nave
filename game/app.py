import pygame
from .core.state import StateManager
from .core.config import Config, set_screen_resolution
from .core.assets import load_custom_cursor
from .scenes.main_menu import MainMenuScene
from .core.levels import LevelManager, FIXED_LEVELS
from .core.input import Input


class GameApp:
    def __init__(self):
        pygame.init()

        # Define a resolução base (de design) do jogo.
        base_width = Config.SCREEN_WIDTH
        base_height = Config.SCREEN_HEIGHT

        # Garante que a configuração global use a resolução BASE.
        set_screen_resolution(base_width, base_height)

        # Define as flags da tela. Usa FULLSCREEN se ativado.
        flags = 0
        if Config.FULLSCREEN:
            flags |= pygame.FULLSCREEN

        # A flag SCALED é a chave para o desempenho.
        # O Pygame gerencia o dimensionamento via hardware, que é muito mais rápido
        # do que o escalonamento manual via software (CPU).
        flags |= pygame.SCALED

        # Cria a tela com a resolução base. O Pygame cuidará do dimensionamento
        # para a resolução real do monitor, mantendo a proporção ("letterboxing").
        self.screen = pygame.display.set_mode((base_width, base_height), flags)

        # Armazenar resolução para consistência (agora é sempre a base).
        self.screen_width = base_width
        self.screen_height = base_height

        # Carregar cursor customizado.
        load_custom_cursor()

        pygame.display.set_caption("Space Shooter")
        self.clock = pygame.time.Clock()
        self.running = True

        self.states: StateManager = StateManager()
        self.level_manager = LevelManager(FIXED_LEVELS)
        self.input: Input = Input()

        # Inicia com o menu principal.
        self.states.push(MainMenuScene(self))

    def run(self):
        while self.running:
            dt = self.clock.tick(Config.FPS) / 1000.0

            # Lida com eventos. Com pygame.SCALED, as coordenadas do mouse
            # em `event.pos` já são convertidas para a resolução base.
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    else:
                        current_scene = self.states.current()
                        if current_scene:
                            current_scene.handle_event(event)
                else:
                    current_scene = self.states.current()
                    if current_scene:
                        current_scene.handle_event(event)

            # Atualiza a cena atual.
            current_scene = self.states.current()
            if current_scene:
                current_scene.update(dt)

            # Renderiza a cena atual diretamente na tela principal.
            # Não há mais necessidade de uma tela virtual ou escalonamento manual.
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
