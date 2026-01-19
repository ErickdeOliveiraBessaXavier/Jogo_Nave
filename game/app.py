import pygame
from .core.state import StateManager
from .core.config import config as Config, set_screen_resolution
from .core.assets import load_custom_cursor
from .scenes.main_menu import MainMenuScene
from .core.levels import LevelManager, FIXED_LEVELS
from .core.input import Input
from .core.difficulty import DifficultyPreset
from .core.meta_progression import PlayerProfile
from .core.paths import get_profile_path


class GameApp:
    def __init__(self):
        pygame.init()

        # Carregar perfil para obter resolução salva
        profile = PlayerProfile(get_profile_path())
        saved_res = profile.resolution

        if saved_res and saved_res != (1600, 900):  # Se não for o default, usar salva
            # Usar resolução salva
            base_width, base_height = saved_res
        else:
            # Detectar resolução nativa do monitor para resolução dinâmica
            display_info = pygame.display.Info()
            native_width = display_info.current_w
            native_height = display_info.current_h

            # Usar resolução nativa como base, mas com fallback para 1600x900 se muito pequena
            base_width = max(native_width, 1600)
            base_height = max(native_height, 900)

            # Para evitar distorções, manter proporção 16:9 se possível
            target_ratio = 16 / 9
            current_ratio = base_width / base_height
            if abs(current_ratio - target_ratio) > 0.1:  # Tolerância de 10%
                # Ajustar altura para manter 16:9
                base_height = int(base_width / target_ratio)

        # Garante que a configuração global use a resolução detectada.
        set_screen_resolution(base_width, base_height)

        # Define as flags da tela. Usa FULLSCREEN se ativado.
        flags = 0
        if Config.FULLSCREEN:
            flags |= pygame.FULLSCREEN

        # A flag SCALED é a chave para o desempenho.
        # O Pygame gerencia o dimensionamento via hardware, que é muito mais rápido
        # do que o escalonamento manual via software (CPU).
        flags |= pygame.SCALED

        # Cria a tela com a resolução detectada. O Pygame cuidará do dimensionamento
        # para a resolução real do monitor, mantendo a proporção ("letterboxing").
        self.screen = pygame.display.set_mode((base_width, base_height), flags)

        # Armazenar resolução para consistência.
        self.screen_width = base_width
        self.screen_height = base_height

        # Carregar cursor customizado.
        load_custom_cursor()

        # Registrar sprites para pré-carregamento
        from .core.sprite_loader import sprite_loader
        from .entities.slime_boss import SlimeBoss

        sprite_loader.register("slime_boss", SlimeBoss.load_frames_for_preload)

        # PRÉ-CARREGAR TODOS OS SPRITES (adicionar aqui)
        sprite_loader.load_all()

        pygame.display.set_caption("Space Shooter")
        self.clock = pygame.time.Clock()
        self.running = True

        self.states: StateManager = StateManager()
        self.level_manager = LevelManager(FIXED_LEVELS)
        self.input: Input = Input()

        # Renderer compartilhado para manter starfield contínuo
        from .render.renderer import Renderer

        self.renderer = Renderer()

        # Dificuldade selecionada (padrão: normal)
        self.selected_difficulty = DifficultyPreset.NORMAL

        # Contador de uso do HEAL (persiste por jogo)
        self.heal_usage_count = 0

        # Inicia com o menu principal.
        self.states.push(MainMenuScene(self))

    def run(self):
        while self.running:
            dt = self.clock.tick(Config.FPS) / 1000.0

            current_scene = self.states.current()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                # Removido: ESC global que fechava o jogo
                # elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                #     self.running = False
                elif current_scene:
                    current_scene.handle_event(event)

            if current_scene:
                current_scene.update(dt)
                current_scene.render(self.screen)

            pygame.display.flip()

        pygame.quit()


def main():
    app = GameApp()
    app.run()


if __name__ == "__main__":
    main()
