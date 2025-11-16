import pygame
from typing import TYPE_CHECKING, Optional
from ..core.state import Scene
from ..render.renderer import Renderer
from ..core.config import Config
from ..core.colors import BLACK, WHITE, GREEN, BRIGHT_GREEN
from ..core.assets import get_font
from ..core.sound import sound_manager

if TYPE_CHECKING:
    from ..app import GameApp


class PausedScene(Scene):
    def __init__(self, app: "GameApp", previous_scene: Optional[Scene] = None):
        super().__init__(app)
        self.r = Renderer()
        self.previous_scene = previous_scene  # Armazena a cena anterior
        self.button_font = get_font(22)

        # Button colors
        self.button_color = GREEN
        self.button_hover_color = BRIGHT_GREEN
        self.border_color = WHITE

        # Continue Button
        self.continue_button_rect = pygame.Rect(0, 0, 280, 60)
        self.continue_button_rect.center = (
            Config.SCREEN_WIDTH // 2,
            Config.SCREEN_HEIGHT // 2 - 40,
        )
        self.continue_button_text = self.button_font.render("Continuar", True, BLACK)
        self.continue_button_text_rect = self.continue_button_text.get_rect(
            center=self.continue_button_rect.center
        )

        # Settings Button
        self.settings_button_rect = pygame.Rect(0, 0, 280, 60)
        self.settings_button_rect.center = (
            Config.SCREEN_WIDTH // 2,
            Config.SCREEN_HEIGHT // 2 + 40,
        )
        self.settings_button_text = self.button_font.render(
            "Configurações", True, BLACK
        )
        self.settings_button_text_rect = self.settings_button_text.get_rect(
            center=self.settings_button_rect.center
        )

        # Menu Button
        self.menu_button_rect = pygame.Rect(0, 0, 280, 60)
        self.menu_button_rect.center = (
            Config.SCREEN_WIDTH // 2,
            Config.SCREEN_HEIGHT // 2 + 120,
        )
        self.menu_button_text = self.button_font.render("Menu", True, BLACK)
        self.menu_button_text_rect = self.menu_button_text.get_rect(
            center=self.menu_button_rect.center
        )

        # Track hover state
        self.continue_button_hovered = False
        self.settings_button_hovered = False
        self.menu_button_hovered = False
        self.prev_continue_button_hovered = False
        self.prev_settings_button_hovered = False
        self.prev_menu_button_hovered = False

    def enter(self):
        pygame.mouse.set_visible(True)
        sound_manager.pause_music()

    def exit(self):
        # Music is resumed only if returning to PlayingScene
        # If going to MainMenuScene, MainMenuScene will handle its music
        pass

    def update(self, dt: float):
        # Não atualiza nada durante a pausa
        pass

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_p:
                # Volta para a cena anterior (Playing) sem criar nova instância
                if self.previous_scene:
                    self.app.states.switch(self.previous_scene)
                    sound_manager.resume_music()
                else:
                    # Fallback caso não tenha cena anterior
                    from .playing import PlayingScene

                    self.app.states.switch(
                        PlayingScene(self.app, self.app.level_manager)
                    )
                    sound_manager.resume_music()

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.continue_button_rect.collidepoint(event.pos):
                # Volta para a cena anterior
                if self.previous_scene:
                    self.app.states.switch(self.previous_scene)
                    sound_manager.resume_music()
                else:
                    from .playing import PlayingScene

                    self.app.states.switch(
                        PlayingScene(self.app, self.app.level_manager)
                    )
                    sound_manager.resume_music()

            elif self.settings_button_rect.collidepoint(event.pos):
                # Abre as configurações
                from .settings import SettingsScene

                self.app.states.push(SettingsScene(self.app))

            elif self.menu_button_rect.collidepoint(event.pos):
                # Volta para o menu principal
                from .main_menu import MainMenuScene

                # Remove todas as cenas e vai direto para o menu
                self.app.states.pop()  # Remove PausedScene
                self.app.states.pop()  # Remove PlayingScene
                sound_manager.stop_music() # Stop any game music before going to main menu
                self.app.states.push(MainMenuScene(self.app))

        elif event.type == pygame.MOUSEMOTION:
            self.continue_button_hovered = self.continue_button_rect.collidepoint(
                event.pos
            )
            self.settings_button_hovered = self.settings_button_rect.collidepoint(
                event.pos
            )
            self.menu_button_hovered = self.menu_button_rect.collidepoint(event.pos)

            # Play hover sound only when the state changes
            if self.continue_button_hovered and not self.prev_continue_button_hovered:
                sound_manager.play_sound("button_hover")
            if self.settings_button_hovered and not self.prev_settings_button_hovered:
                sound_manager.play_sound("button_hover")
            if self.menu_button_hovered and not self.prev_menu_button_hovered:
                sound_manager.play_sound("button_hover")

        # Update previous hover states
        self.prev_continue_button_hovered = self.continue_button_hovered
        self.prev_settings_button_hovered = self.settings_button_hovered
        self.prev_menu_button_hovered = self.menu_button_hovered

    def render(self, surface: pygame.Surface):
        # Renderiza a cena anterior primeiro (congelada)
        if self.previous_scene:
            self.previous_scene.render(surface)

        # Desenha overlay de pausa por cima
        overlay = pygame.Surface(
            (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        # Draw title
        pause_font = get_font(60)
        title = pause_font.render("PAUSADO", True, WHITE)
        title_rect = title.get_rect(
            center=(Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 4)
        )

        surface.blit(title, title_rect)

        # Draw Continue Button
        continue_color = (
            self.button_hover_color
            if self.continue_button_hovered
            else self.button_color
        )
        pygame.draw.rect(
            surface, continue_color, self.continue_button_rect, border_radius=10
        )
        pygame.draw.rect(
            surface, self.border_color, self.continue_button_rect, 2, border_radius=10
        )
        surface.blit(self.continue_button_text, self.continue_button_text_rect)

        # Draw Settings Button
        settings_color = (
            self.button_hover_color
            if self.settings_button_hovered
            else self.button_color
        )
        pygame.draw.rect(
            surface, settings_color, self.settings_button_rect, border_radius=10
        )
        pygame.draw.rect(
            surface, self.border_color, self.settings_button_rect, 2, border_radius=10
        )
        surface.blit(self.settings_button_text, self.settings_button_text_rect)

        # Draw Menu Button
        menu_color = (
            self.button_hover_color if self.menu_button_hovered else self.button_color
        )
        pygame.draw.rect(surface, menu_color, self.menu_button_rect, border_radius=10)
        pygame.draw.rect(
            surface, self.border_color, self.menu_button_rect, 2, border_radius=10
        )
        surface.blit(self.menu_button_text, self.menu_button_text_rect)

        # Draw hint text
        hint_font = get_font(14)
        hint_text = hint_font.render("Pressione P para continuar", True, WHITE)
        hint_rect = hint_text.get_rect(
            center=(Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT - 40)
        )
        surface.blit(hint_text, hint_rect)
