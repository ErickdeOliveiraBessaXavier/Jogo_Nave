import pygame
import math
from typing import TYPE_CHECKING, TypedDict, List, Callable, Any, Optional
from enum import Enum

if TYPE_CHECKING:
    from ..app import GameApp

from ..core.state import Scene
from ..core.colors import WHITE, BLACK, GREEN, BRIGHT_GREEN, RED, DARK_RED, BLUE
from ..scenes.settings import SettingsScene
from ..scenes.difficulty_selection import DifficultySelectionScene
from ..scenes.statistics import StatisticsScene
from ..scenes.upgrades_selection import UpgradesSelectionScene
from ..core.assets import get_font
from ..core.config import config as Config
from ..render.renderer import Renderer
from ..core.sound import sound_manager
from ..core.sound_config import MusicState


class CharDict(TypedDict):
    render: pygame.Surface
    base_rect: pygame.Rect
    rect: pygame.Rect


class AnimationConfig:
    TITLE_ANIM_SPEED = 2.5
    TITLE_PHASE_SHIFT = 0.5
    TITLE_ANIM_RANGE = 15
    BUTTON_ANIM_RANGE = 5
    BUTTON_SCALE_FACTOR = 1.1
    BUTTON_SPACING = 80
    MENU_X_RATIO = 0.5  # Horizontal position as ratio of screen width (0.5 = center)
    MENU_Y_RATIO = 0.5  # Vertical position as ratio of screen height (0.5 = center)
    TITLE_TOP_MARGIN = 20  # Margin from top of menu container to title
    BUTTONS_TOP_MARGIN = 200  # Margin from title bottom to first button
    TITLE_HEIGHT = 60  # Approximate height of title text


class MenuStrings:
    START_GAME = "Iniciar Jogo"
    STATISTICS = "Estatísticas"
    UPGRADES = "Aprimoramentos"
    SETTINGS = "Configurações"
    EXIT = "Sair"
    TITLE = "Space Shooter"


class ButtonIndices:
    START_BUTTON = 0
    STATISTICS_BUTTON = 1
    SETTINGS_BUTTON = 2
    EXIT_BUTTON = 3


class ButtonState(Enum):
    NORMAL = 0
    HOVERED = 1
    PRESSED = 2
    FOCUSED = 3


class Button:
    def __init__(
        self,
        text: str,
        rect: pygame.Rect,
        font: Any,
        color: tuple[int, int, int],
        hover_color: tuple[int, int, int],
        action: Callable[[], None],
    ):
        self.text = text
        self.rect = rect
        self.font = font
        self.color = color
        self.hover_color = hover_color
        self.action = action
        self.state = ButtonState.NORMAL
        self.prev_state = ButtonState.NORMAL
        self.focused = False
        self.chars: List[CharDict] = []
        self.text_width = 0
        self._create_char_data()

    def _create_char_data(self):
        btn_char_renders = [self.font.render(char, True, BLACK) for char in self.text]
        self.text_width = sum(char.get_width() for char in btn_char_renders)

        text_start_x = self.rect.centerx - (self.text_width / 2)
        text_current_x = text_start_x

        for char_render in btn_char_renders:
            char_base_rect = char_render.get_rect(
                topleft=(
                    text_current_x,
                    self.rect.centery - char_render.get_height() / 2,
                )
            )
            self.chars.append(
                {
                    "render": char_render,
                    "base_rect": char_base_rect,
                    "rect": char_base_rect.copy(),
                }
            )
            text_current_x += char_render.get_width()

    def update_hover(self, mouse_pos: tuple[int, int]):
        self.prev_state = self.state
        if self.rect.collidepoint(mouse_pos):
            self.state = ButtonState.HOVERED
        elif self.focused:
            self.state = ButtonState.FOCUSED
        else:
            self.state = ButtonState.NORMAL

    def update_animation(
        self, time_ms: float, anim_speed: float, phase_shift: float, anim_range: float
    ):
        for i, char_data in enumerate(self.chars):
            if self.state in (ButtonState.HOVERED, ButtonState.FOCUSED):
                sine_wave = math.sin(
                    (time_ms / 1000.0 * anim_speed * 2) + (i * phase_shift)
                )
                char_data["rect"].y = int(
                    char_data["base_rect"].y + sine_wave * anim_range
                )
            else:
                char_data["rect"].y = char_data["base_rect"].y

    def render(
        self,
        surface: pygame.Surface,
        border_color: tuple[int, int, int],
        scale_factor: float,
    ):
        color = (
            self.hover_color
            if self.state in (ButtonState.HOVERED, ButtonState.FOCUSED)
            else self.color
        )

        if self.state == ButtonState.HOVERED:
            scaled_rect = pygame.Rect(
                0,
                0,
                int(self.rect.width * scale_factor),
                int(self.rect.height * scale_factor),
            )
            scaled_rect.center = self.rect.center

            pygame.draw.rect(surface, color, scaled_rect, border_radius=12)
            pygame.draw.rect(surface, border_color, scaled_rect, 2, border_radius=12)

            # Draw animated text
            start_x = scaled_rect.centerx - (self.text_width / 2)
            current_x = start_x
            for char_data in self.chars:
                char_pos = (current_x, char_data["rect"].y)
                surface.blit(char_data["render"], char_pos)
                current_x += char_data["render"].get_width()
        else:
            pygame.draw.rect(surface, color, self.rect, border_radius=10)
            pygame.draw.rect(surface, border_color, self.rect, 2, border_radius=10)

            text_rect = self.font.render(self.text, True, BLACK).get_rect(
                center=self.rect.center
            )
            surface.blit(self.font.render(self.text, True, BLACK), text_rect)


class MainMenuScene(Scene):
    """
    Main menu scene for the Space Shooter game.

    Handles the display and interaction of the main menu, including title animation,
    button interactions, and navigation to other scenes.
    """

    def __init__(self, app: "GameApp"):
        super().__init__(app)
        self.r = Renderer()
        self.font = get_font(60)
        self.button_font = get_font(22)
        self.border_color = WHITE
        self.focused_border_color = BLUE
        self.focused_button_index = 0

        # Menu container position - temporary, will be adjusted
        self.menu_x = int(Config.SCREEN_WIDTH * AnimationConfig.MENU_X_RATIO)
        self.menu_y = 0  # Temporary

        # Title animation
        self.title_chars: List[CharDict] = []
        self._create_title_chars()

        # Button definitions
        self.buttons: List[Button] = []
        self._create_buttons()

        # Calculate actual menu bounds and center vertically
        self._center_menu_vertically()

    def _center_menu_vertically(self):
        """Calculates the actual bounds of the menu and adjusts menu_y to center it vertically."""
        # Collect all Y positions
        all_y: List[int] = []
        
        # Title positions
        for char_data in self.title_chars:
            all_y.append(char_data["base_rect"].top)
            all_y.append(char_data["base_rect"].bottom)
        
        # Button positions
        for button in self.buttons:
            all_y.append(button.rect.top)
            all_y.append(button.rect.bottom)
        
        if all_y:
            menu_top = min(all_y)
            menu_bottom = max(all_y)
            menu_height = menu_bottom - menu_top
            
            # Center the menu vertically
            self.menu_y = (Config.SCREEN_HEIGHT - menu_height) // 2
            
            # Adjust all positions by the new menu_y offset
            offset = self.menu_y - menu_top
            
            # Adjust title positions
            for char_data in self.title_chars:
                char_data["base_rect"].y += offset
                char_data["rect"].y += offset
            
            # Adjust button positions
            for button in self.buttons:
                button.rect.y += offset
                # Adjust button's internal char positions
                for char in button.chars:
                    char["base_rect"].y += offset
                    char["rect"].y += offset

    def _create_title_chars(self):
        """Creates character data for title animation."""
        title_string = MenuStrings.TITLE
        char_renders = [self.font.render(char, True, WHITE) for char in title_string]
        total_width = sum(char_render.get_width() for char_render in char_renders)

        start_x = (Config.SCREEN_WIDTH - total_width) // 2
        base_y = self.menu_y + AnimationConfig.TITLE_TOP_MARGIN
        current_x = start_x

        for char_render in char_renders:
            base_rect = char_render.get_rect(topleft=(current_x, base_y))
            self.title_chars.append(
                {
                    "render": char_render,
                    "base_rect": base_rect,
                    "rect": base_rect.copy(),
                }
            )
            current_x += char_render.get_width()

    def _create_buttons(self):
        """Creates button instances with their actions."""
        buttons_y_start = (
            self.menu_y
            + AnimationConfig.TITLE_TOP_MARGIN
            + AnimationConfig.TITLE_HEIGHT
            + AnimationConfig.BUTTONS_TOP_MARGIN
        )

        button_configs = [
            (
                MenuStrings.START_GAME,
                GREEN,
                BRIGHT_GREEN,
                lambda: self.app.states.push(DifficultySelectionScene(self.app)),
            ),
            (
                MenuStrings.STATISTICS,
                GREEN,
                BRIGHT_GREEN,
                lambda: self.app.states.push(StatisticsScene(self.app)),
            ),
            (
                MenuStrings.UPGRADES,
                GREEN,
                BRIGHT_GREEN,
                lambda: self.app.states.push(UpgradesSelectionScene(self.app)),
            ),
            (
                MenuStrings.SETTINGS,
                GREEN,
                BRIGHT_GREEN,
                lambda: self.app.states.push(SettingsScene(self.app)),
            ),
            (
                MenuStrings.EXIT,
                DARK_RED,
                RED,
                lambda: setattr(self.app, "running", False),
            ),
        ]

        for i, (text, color, hover_color, action) in enumerate(button_configs):
            rect = pygame.Rect(0, 0, 380, 60)
            rect.center = (
                self.menu_x,
                buttons_y_start + i * AnimationConfig.BUTTON_SPACING,
            )
            button = Button(text, rect, self.button_font, color, hover_color, action)
            self.buttons.append(button)

    def _calculate_wave_offset(
        self,
        time_ms: float,
        index: int,
        amplitude: float,
        speed: Optional[float] = None,
    ) -> int:
        """Calculates offset based on sine wave for animation."""
        if speed is None:
            speed = AnimationConfig.TITLE_ANIM_SPEED
        sine_wave = math.sin(
            (time_ms / 1000.0 * speed) + (index * AnimationConfig.TITLE_PHASE_SHIFT)
        )
        return int(sine_wave * amplitude)

    def enter(self):
        """Called when entering the scene."""
        pygame.mouse.set_visible(True)
        sound_manager.music_state_manager.transition_to(MusicState.MENU)

    def exit(self):
        """Called when exiting the scene."""
        pass

    def handle_event(self, event: pygame.event.Event):
        """Handles user input events."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for button in self.buttons:
                if button.rect.collidepoint(event.pos):
                    button.action()
                    sound_manager.play_sound("button_click")
                    break
        elif event.type == pygame.MOUSEMOTION:
            for button in self.buttons:
                prev_state = button.state
                button.update_hover(event.pos)
                if (
                    button.state == ButtonState.HOVERED
                    and prev_state != ButtonState.HOVERED
                ):
                    sound_manager.play_sound("button_hover")
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_DOWN:
                self.focused_button_index = (self.focused_button_index + 1) % len(
                    self.buttons
                )
            elif event.key == pygame.K_UP:
                self.focused_button_index = (self.focused_button_index - 1) % len(
                    self.buttons
                )
            elif event.key == pygame.K_RETURN:
                self.buttons[self.focused_button_index].action()
                sound_manager.play_sound("button_click")
            elif event.key == pygame.K_ESCAPE:
                self.app.running = False
            # Update focused states
            for i, button in enumerate(self.buttons):
                button.focused = i == self.focused_button_index

    def update(self, dt: float):
        """Updates scene logic."""
        self.r.starfield.update(dt)
        time_ms = pygame.time.get_ticks()

        # Animate title
        for i, char_data in enumerate(self.title_chars):
            char_data["rect"].y = char_data[
                "base_rect"
            ].y + self._calculate_wave_offset(
                time_ms, i, AnimationConfig.TITLE_ANIM_RANGE
            )

        # Animate buttons
        for button in self.buttons:
            button.update_animation(
                time_ms,
                AnimationConfig.TITLE_ANIM_SPEED,
                AnimationConfig.TITLE_PHASE_SHIFT,
                AnimationConfig.BUTTON_ANIM_RANGE,
            )

    def render(self, surface: pygame.Surface):
        """Renders the scene."""
        surface.fill(BLACK)
        self.r.starfield.draw(surface)

        # Render title
        for char_data in self.title_chars:
            surface.blit(char_data["render"], char_data["rect"])

        # Render buttons
        for button in self.buttons:
            border_color = (
                self.focused_border_color
                if button.state == ButtonState.FOCUSED
                else self.border_color
            )
            button.render(surface, border_color, AnimationConfig.BUTTON_SCALE_FACTOR)
