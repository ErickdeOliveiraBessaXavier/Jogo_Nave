import pygame
from typing import TYPE_CHECKING

from ..core.state import Scene
from ..core.colors import WHITE, BLACK, GREEN, BRIGHT_GREEN
from ..scenes.playing import PlayingScene
from ..scenes.settings import SettingsScene
from ..core.assets import get_font
from ..core.config import Config
from ..render.renderer import Renderer

if TYPE_CHECKING:
    from ..app import GameApp


class MainMenuScene(Scene):
    def __init__(self, app: "GameApp"):
        super().__init__(app)
        self.r = Renderer()
        self.font = get_font(48)
        self.button_font = get_font(22)

        self.title_text = self.font.render("Space Shooter", True, WHITE)
        self.title_rect = self.title_text.get_rect(center=(Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 4))

        # Button colors
        self.button_color = GREEN
        self.button_hover_color = BRIGHT_GREEN
        self.border_color = WHITE

        # Start Button
        self.start_button_rect = pygame.Rect(0, 0, 250, 60)
        self.start_button_rect.center = (Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 2)
        self.start_button_text = self.button_font.render("Start Game", True, BLACK)
        self.start_button_text_rect = self.start_button_text.get_rect(center=self.start_button_rect.center)

        # Settings Button
        self.settings_button_rect = pygame.Rect(0, 0, 250, 60)
        self.settings_button_rect.center = (Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 2 + 80)
        self.settings_button_text = self.button_font.render("Settings", True, BLACK)
        self.settings_button_text_rect = self.settings_button_text.get_rect(center=self.settings_button_rect.center)
        
        # Track hover state
        self.start_button_hovered = False
        self.settings_button_hovered = False

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.start_button_rect.collidepoint(event.pos):
                self.app.states.push(PlayingScene(self.app, self.app.level_manager))
            elif self.settings_button_rect.collidepoint(event.pos):
                self.app.states.push(SettingsScene(self.app))
        
        elif event.type == pygame.MOUSEMOTION:
            self.start_button_hovered = self.start_button_rect.collidepoint(event.pos)
            self.settings_button_hovered = self.settings_button_rect.collidepoint(event.pos)

    def update(self, dt: float):
        self.r.starfield.update(dt)

    def render(self, surface: pygame.Surface):
        surface.fill(BLACK)
        self.r.starfield.draw(surface)
        surface.blit(self.title_text, self.title_rect)

        # Draw Start Button
        start_color = self.button_hover_color if self.start_button_hovered else self.button_color
        pygame.draw.rect(surface, start_color, self.start_button_rect, border_radius=10)
        pygame.draw.rect(surface, self.border_color, self.start_button_rect, 2, border_radius=10)
        surface.blit(self.start_button_text, self.start_button_text_rect)

        # Draw Settings Button
        settings_color = self.button_hover_color if self.settings_button_hovered else self.button_color
        pygame.draw.rect(surface, settings_color, self.settings_button_rect, border_radius=10)
        pygame.draw.rect(surface, self.border_color, self.settings_button_rect, 2, border_radius=10)
        surface.blit(self.settings_button_text, self.settings_button_text_rect)
