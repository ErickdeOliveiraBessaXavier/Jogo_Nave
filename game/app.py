import pygame

from .core.assets import load_custom_cursor
from .core.config import config as Config
from .core.config import set_screen_resolution
from .core.difficulty import DifficultyPreset
from .core.input import Input
from .core.levels import FIXED_LEVELS, LevelManager
from .core.meta_progression import PlayerProfile
from .core.paths import get_preferences_path, get_profile_path
from .core.preferences import UserPreferences
from .core.state import StateManager
from .scenes.main_menu import MainMenuScene


class GameApp:
    def __init__(self):
        # Melhor qualidade/latência para o mixer antes do pygame.init()
        pygame.mixer.pre_init(44100, -16, 2, 4096)
        pygame.init()

        # Carregar preferências de sistema (vídeo, áudio, controles)
        self.preferences = UserPreferences(get_preferences_path())
        base_width, base_height = self.preferences.resolution

        # Carregar perfil de progressão
        self.player_profile = PlayerProfile(get_profile_path())

        # Garantir proporção 16:9 se necessário
        target_ratio = 16 / 9
        current_ratio = base_width / base_height
        if abs(current_ratio - target_ratio) > 0.1:
            base_height = int(base_width / target_ratio)

        # Garante que a configuração global use a resolução detectada.
        set_screen_resolution(base_width, base_height)

        # Sincronizar volumes do SoundManager com as preferências
        from .core.sound import sound_manager

        sound_manager.load_config(
            self.preferences.music_volume,
            self.preferences.sfx_volume,
            self.preferences.shot_volume,
        )

        # Define as flags da tela.
        flags = 0
        if self.preferences.fullscreen:
            flags |= pygame.FULLSCREEN
        flags |= pygame.SCALED

        self.screen = pygame.display.set_mode((base_width, base_height), flags)
        self.screen_width = base_width
        self.screen_height = base_height

        load_custom_cursor()

        # Registrar sprites para pré-carregamento
        from .core.sprite_loader import sprite_loader
        from .entities.mountain_serpent_boss import (MountainSerpentBoss,
                                                     SerpentBlock)
        from .entities.slime_boss import SlimeBoss

        sprite_loader.register("slime_boss", SlimeBoss.load_frames_for_preload)
        sprite_loader.register(
            "mountain_serpent_boss", MountainSerpentBoss.load_frames_for_preload
        )
        sprite_loader.register("serpent_block", SerpentBlock.load_frames_for_preload)
        sprite_loader.load_all()

        pygame.display.set_caption("Space Shooter")
        self.clock = pygame.time.Clock()
        self.running = True

        self.states: StateManager = StateManager()
        self.level_manager = LevelManager(FIXED_LEVELS)
        self.input: Input = Input()

        from .render.renderer import Renderer

        self.renderer = Renderer()

        self.selected_difficulty = DifficultyPreset.NORMAL
        self.heal_usage_count = 0

        self.states.push(MainMenuScene(self))

    def run(self):
        from .core.sound import sound_manager

        try:
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
        finally:
            sound_manager.shutdown()
            pygame.quit()


def main():
    app = GameApp()
    app.run()


if __name__ == "__main__":
    main()
