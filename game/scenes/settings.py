import pygame
from typing import TYPE_CHECKING, Optional

from ..core.state import Scene
from ..core.colors import WHITE, BLACK, GREEN, BRIGHT_GREEN, GRAY
from ..core.assets import get_font
from ..core.config import config as Config
from ..core.sound import sound_manager
from ..core.meta_progression import PlayerProfile
from ..core.upgrades_config import UPGRADE_SLOT_COUNT
from pathlib import Path

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
        self.small_font = get_font(18)

        # Player profile for keybindings
        self.player_profile = PlayerProfile(Path("player_profile.json"))

        # Keybinding state
        self.waiting_for_key: Optional[int] = None  # Which slot is waiting for rebind

        # Layout calculations
        total_height = 550  # Increased for upgrade keybindings
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

        # Upgrade Keybindings
        y_offset = self.back_button_rect.bottom + 40
        self.keybind_title = self.label_font.render(
            "Teclas de Aprimoramentos", True, WHITE
        )
        self.keybind_title_rect = self.keybind_title.get_rect(
            center=(Config.SCREEN_WIDTH // 2, y_offset)
        )
        y_offset += 40
        self.keybind_buttons: list[pygame.Rect] = []
        self.keybind_texts: list[pygame.Surface] = []
        for i in range(UPGRADE_SLOT_COUNT):
            rect = pygame.Rect(0, 0, 240, 40)
            rect.center = (Config.SCREEN_WIDTH // 2, y_offset + i * 60)
            self.keybind_buttons.append(rect)
            key_name = pygame.key.name(
                self.player_profile.upgrade_keybindings[i]
            ).upper()
            label = self.small_font.render(f"Slot {i+1}: {key_name}", True, BLACK)
            self.keybind_texts.append(label)

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
            else:
                # Check keybinding buttons
                for i, rect in enumerate(self.keybind_buttons):
                    if rect.collidepoint(event.pos):
                        sound_manager.play_sound("button_hover")
                        self.waiting_for_key = i
                        break
        elif event.type == pygame.MOUSEMOTION:
            self.back_button_hovered = self.back_button_rect.collidepoint(event.pos)
            if self.back_button_hovered and not self.prev_back_button_hovered:
                sound_manager.play_sound("button_hover")

        # Capture next key for rebinding
        if event.type == pygame.KEYDOWN and self.waiting_for_key is not None:
            new_key = event.key
            # Avoid binding ESC to prevent locking out settings
            if new_key != pygame.K_ESCAPE:
                self.player_profile.upgrade_keybindings[self.waiting_for_key] = new_key
                self.player_profile.save()
                # Update button label
                key_name = pygame.key.name(new_key).upper()
                self.keybind_texts[self.waiting_for_key] = self.small_font.render(
                    f"Slot {self.waiting_for_key+1}: {key_name}", True, BLACK
                )
                sound_manager.play_sound("button_hover")
            self.waiting_for_key = None

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

        # Draw keybinding section
        surface.blit(self.keybind_title, self.keybind_title_rect)
        for i, rect in enumerate(self.keybind_buttons):
            color = (80, 80, 80) if (self.waiting_for_key == i) else (60, 60, 60)
            pygame.draw.rect(surface, color, rect, border_radius=8)
            pygame.draw.rect(surface, WHITE, rect, 2, border_radius=8)
            text = self.keybind_texts[i]
            text_rect = text.get_rect(center=rect.center)
            surface.blit(text, text_rect)
