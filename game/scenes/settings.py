import pygame
from typing import TYPE_CHECKING, Optional

from ..core.state import Scene
from ..core.colors import WHITE, BLACK, GREEN, BRIGHT_GREEN, GRAY
from ..core.assets import get_font
from ..core.config import config as Config
from ..core.sound import sound_manager

if TYPE_CHECKING:
    from ..app import GameApp
    from .paused import PausedScene


class Slider:
    def __init__(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        min_val: float,
        max_val: float,
        initial_val: float,
    ):
        self.rect: pygame.Rect = pygame.Rect(x, y, w, h)
        self.min_val: float = min_val
        self.max_val: float = max_val
        self.val: float = initial_val
        self.knob_radius: int = h
        self.dragging: bool = False
        self.value_changed_this_frame: bool = False

    def get_value(self) -> float:
        return self.val

    def get_and_reset_value_changed_flag(self) -> bool:
        flag = self.value_changed_this_frame
        self.value_changed_this_frame = False
        return flag

    def handle_event(self, event: pygame.event.Event):
        self.value_changed_this_frame = (
            False  # Reset flag at the start of event handling
        )

        if event.type == pygame.MOUSEBUTTONDOWN:
            knob_x = self.rect.x + int(self.val * self.rect.w)
            knob_y = self.rect.centery
            distance = (
                (event.pos[0] - knob_x) ** 2 + (event.pos[1] - knob_y) ** 2
            ) ** 0.5
            if distance <= self.knob_radius:
                self.dragging = True
            elif self.rect.collidepoint(event.pos):
                # Jump the knob to the clicked position
                new_val = (event.pos[0] - self.rect.x) / self.rect.w
                new_val = max(0.0, min(1.0, new_val))
                if new_val != self.val:
                    self.val = new_val
                    self.value_changed_this_frame = True
                self.dragging = True  # Allow dragging from the new position
        elif event.type == pygame.MOUSEBUTTONUP:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging:
                new_val = (event.pos[0] - self.rect.x) / self.rect.w
                new_val = max(0.0, min(1.0, new_val))
                if new_val != self.val:
                    self.val = new_val
                    self.value_changed_this_frame = True

    def draw(self, surface: pygame.Surface):
        # Draw the slider bar
        pygame.draw.rect(surface, GRAY, self.rect, border_radius=5)
        # Draw the filled part of the slider
        fill_width: float = self.val * self.rect.w
        fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_width, self.rect.h)
        pygame.draw.rect(surface, GREEN, fill_rect, border_radius=5)
        # Draw the knob
        knob_x: int = self.rect.x + int(self.val * self.rect.w)
        pygame.draw.circle(
            surface, WHITE, (knob_x, self.rect.centery), self.knob_radius
        )


class SettingsScene(Scene):
    def __init__(self, app: "GameApp", paused_scene: Optional["PausedScene"] = None):
        super().__init__(app)
        self.paused_scene = paused_scene
        self.font = get_font(60)
        self.label_font = get_font(24)

        # Layout calculations
        total_height = 400  # Approximate total height of all elements
        start_y = (Config.SCREEN_HEIGHT - total_height) // 2

        self.title_text = self.font.render("Configurações", True, WHITE)
        self.title_rect = self.title_text.get_rect(
            center=(Config.SCREEN_WIDTH // 2, start_y)
        )

        y_offset = start_y + 80

        # Music Slider
        self.music_label = self.label_font.render("Music Volume", True, WHITE)
        self.music_label_rect = self.music_label.get_rect(
            center=(Config.SCREEN_WIDTH // 2, y_offset)
        )
        y_offset += 40
        self.music_slider = Slider(
            Config.SCREEN_WIDTH // 2 - 150,
            y_offset,
            300,
            20,
            0,
            1,
            sound_manager.music_volume,
        )

        y_offset += 80

        # SFX Slider
        self.sfx_label = self.label_font.render("SFX Volume", True, WHITE)
        self.sfx_label_rect = self.sfx_label.get_rect(
            center=(Config.SCREEN_WIDTH // 2, y_offset)
        )
        y_offset += 40
        self.sfx_slider = Slider(
            Config.SCREEN_WIDTH // 2 - 150,
            y_offset,
            300,
            20,
            0,
            1,
            sound_manager.sfx_volume,
        )

        y_offset += 80

        # Shot Slider
        self.shot_label = self.label_font.render("Shot Volume", True, WHITE)
        self.shot_label_rect = self.shot_label.get_rect(
            center=(Config.SCREEN_WIDTH // 2, y_offset)
        )
        y_offset += 40
        self.shot_slider = Slider(
            Config.SCREEN_WIDTH // 2 - 150,
            y_offset,
            300,
            20,
            0,
            1,
            sound_manager.shot_volume_base,
        )

        y_offset += 100

        # Back Button
        self.back_button_rect = pygame.Rect(0, 0, 150, 50)
        self.back_button_rect.center = (Config.SCREEN_WIDTH // 2, y_offset)
        self.back_button_text = self.label_font.render("Back", True, BLACK)
        self.back_button_text_rect = self.back_button_text.get_rect(
            center=self.back_button_rect.center
        )
        self.back_button_hovered = False
        self.prev_back_button_hovered = False

    def enter(self):
        pygame.mouse.set_visible(True)

    def handle_event(self, event: pygame.event.Event):
        self.music_slider.handle_event(event)
        self.sfx_slider.handle_event(event)
        self.shot_slider.handle_event(event)

        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.back_button_rect.collidepoint(event.pos):
                if self.paused_scene:
                    self.paused_scene.go_to_settings = False
                self.app.states.pop()
        elif event.type == pygame.MOUSEMOTION:
            self.back_button_hovered = self.back_button_rect.collidepoint(event.pos)
            if self.back_button_hovered and not self.prev_back_button_hovered:
                sound_manager.play_sound("button_hover")

        self.prev_back_button_hovered = self.back_button_hovered

    def update(self, dt: float):
        if self.music_slider.get_and_reset_value_changed_flag():
            sound_manager.play_sound("button_hover")
        sound_manager.set_music_volume(self.music_slider.get_value())

        if self.sfx_slider.get_and_reset_value_changed_flag():
            sound_manager.play_sound("button_hover")
        sound_manager.set_sfx_volume(self.sfx_slider.get_value())

        if self.shot_slider.get_and_reset_value_changed_flag():
            sound_manager.play_sound("button_hover")
        sound_manager.set_shot_volume(self.shot_slider.get_value())

    def render(self, surface: pygame.Surface):
        surface.fill(BLACK)
        surface.blit(self.title_text, self.title_rect)

        # Draw labels
        surface.blit(self.music_label, self.music_label_rect)
        surface.blit(self.sfx_label, self.sfx_label_rect)
        surface.blit(self.shot_label, self.shot_label_rect)

        # Draw sliders
        self.music_slider.draw(surface)
        self.sfx_slider.draw(surface)
        self.shot_slider.draw(surface)

        # Draw Back Button
        back_color = BRIGHT_GREEN if self.back_button_hovered else GREEN
        pygame.draw.rect(surface, back_color, self.back_button_rect, border_radius=10)
        pygame.draw.rect(surface, WHITE, self.back_button_rect, 2, border_radius=10)
        surface.blit(self.back_button_text, self.back_button_text_rect)
