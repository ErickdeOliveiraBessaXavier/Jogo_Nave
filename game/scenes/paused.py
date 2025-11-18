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
        self.previous_scene = previous_scene
        self.button_font = get_font(22)
        self.go_to_settings = False
        self.go_to_menu = False
        self.first_entry = True

        # Button colors
        self.button_color = GREEN
        self.button_hover_color = BRIGHT_GREEN
        self.border_color = WHITE

        # Button Rects and Texts
        self.continue_button_rect = pygame.Rect(0, 0, 280, 60)
        self.continue_button_rect.center = (Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 2 - 40)
        self.continue_button_text = self.button_font.render("Continuar", True, BLACK)
        self.continue_button_text_rect = self.continue_button_text.get_rect(center=self.continue_button_rect.center)

        self.settings_button_rect = pygame.Rect(0, 0, 280, 60)
        self.settings_button_rect.center = (Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 2 + 40)
        self.settings_button_text = self.button_font.render("Configurações", True, BLACK)
        self.settings_button_text_rect = self.settings_button_text.get_rect(center=self.settings_button_rect.center)

        self.menu_button_rect = pygame.Rect(0, 0, 280, 60)
        self.menu_button_rect.center = (Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 2 + 120)
        self.menu_button_text = self.button_font.render("Menu", True, BLACK)
        self.menu_button_text_rect = self.menu_button_text.get_rect(center=self.menu_button_rect.center)

        # Hover states
        self.continue_button_hovered = False
        self.settings_button_hovered = False
        self.menu_button_hovered = False
        self.prev_continue_button_hovered = False
        self.prev_settings_button_hovered = False
        self.prev_menu_button_hovered = False

    def enter(self):
        pygame.mouse.set_visible(True)
        self.go_to_settings = False
        self.go_to_menu = False
        if self.first_entry:
            sound_manager.pause_music()
            self.first_entry = False

    def exit(self):
        if not self.go_to_menu and not self.go_to_settings:
            sound_manager.resume_music()

    def update(self, dt: float):
        pass

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_p:
            self.app.states.pop()

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.continue_button_rect.collidepoint(event.pos):
                self.app.states.pop()

            elif self.settings_button_rect.collidepoint(event.pos):
                from .settings import SettingsScene
                self.go_to_settings = True
                self.app.states.push(SettingsScene(self.app, paused_scene=self))

            elif self.menu_button_rect.collidepoint(event.pos):
                self.go_to_menu = True
                sound_manager.stop_music()
                from ..core.sound_config import MusicState
                sound_manager.music_state_manager.transition_to(MusicState.MENU, force=True)
                
                # Pop until we get to the main menu
                while len(self.app.states._stack) > 1:
                    self.app.states.pop()


        elif event.type == pygame.MOUSEMOTION:
            self.continue_button_hovered = self.continue_button_rect.collidepoint(event.pos)
            self.settings_button_hovered = self.settings_button_rect.collidepoint(event.pos)
            self.menu_button_hovered = self.menu_button_rect.collidepoint(event.pos)

            if self.continue_button_hovered and not self.prev_continue_button_hovered:
                sound_manager.play_sound("button_hover")
            if self.settings_button_hovered and not self.prev_settings_button_hovered:
                sound_manager.play_sound("button_hover")
            if self.menu_button_hovered and not self.prev_menu_button_hovered:
                sound_manager.play_sound("button_hover")

        self.prev_continue_button_hovered = self.continue_button_hovered
        self.prev_settings_button_hovered = self.settings_button_hovered
        self.prev_menu_button_hovered = self.menu_button_hovered

    def render(self, surface: pygame.Surface):
        if self.previous_scene:
            self.previous_scene.render(surface)

        overlay = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        pause_font = get_font(60)
        title = pause_font.render("PAUSADO", True, WHITE)
        title_rect = title.get_rect(center=(Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 4))
        surface.blit(title, title_rect)

        # Draw Buttons
        continue_color = self.button_hover_color if self.continue_button_hovered else self.button_color
        pygame.draw.rect(surface, continue_color, self.continue_button_rect, border_radius=10)
        pygame.draw.rect(surface, self.border_color, self.continue_button_rect, 2, border_radius=10)
        surface.blit(self.continue_button_text, self.continue_button_text_rect)

        settings_color = self.button_hover_color if self.settings_button_hovered else self.button_color
        pygame.draw.rect(surface, settings_color, self.settings_button_rect, border_radius=10)
        pygame.draw.rect(surface, self.border_color, self.settings_button_rect, 2, border_radius=10)
        surface.blit(self.settings_button_text, self.settings_button_text_rect)

        menu_color = self.button_hover_color if self.menu_button_hovered else self.button_color
        pygame.draw.rect(surface, menu_color, self.menu_button_rect, border_radius=10)
        pygame.draw.rect(surface, self.border_color, self.menu_button_rect, 2, border_radius=10)
        surface.blit(self.menu_button_text, self.menu_button_text_rect)

        hint_font = get_font(14)
        hint_text = hint_font.render("Pressione P para continuar", True, WHITE)
        hint_rect = hint_text.get_rect(center=(Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT - 40))
        surface.blit(hint_text, hint_rect)