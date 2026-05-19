from typing import TYPE_CHECKING, Optional

import pygame

from ..core.assets import get_font
from ..core.colors import CUSTOM_GOLD, CUSTOM_PURPLE, WHITE
from ..core.config import config as Config
from ..core.sound import sound_manager
from ..core.state import Scene

if TYPE_CHECKING:
    from ..app import GameApp


class PausedScene(Scene):
    def __init__(self, app: "GameApp", previous_scene: Optional[Scene] = None):
        super().__init__(app)
        self.r = app.renderer  # Usar renderer compartilhado
        self.previous_scene = previous_scene
        self.title_font = get_font(60)
        self.button_font = get_font(22)
        self.hint_font = get_font(14)
        self.go_to_settings = False
        self.go_to_menu = False
        self.first_entry = True

        # Button Rects and Texts
        self.continue_button_rect = pygame.Rect(0, 0, 280, 60)
        self.continue_button_rect.center = (
            Config.SCREEN_WIDTH // 2,
            Config.SCREEN_HEIGHT // 2 - 40,
        )

        self.settings_button_rect = pygame.Rect(0, 0, 280, 60)
        self.settings_button_rect.center = (
            Config.SCREEN_WIDTH // 2,
            Config.SCREEN_HEIGHT // 2 + 40,
        )

        self.menu_button_rect = pygame.Rect(0, 0, 280, 60)
        self.menu_button_rect.center = (
            Config.SCREEN_WIDTH // 2,
            Config.SCREEN_HEIGHT // 2 + 120,
        )

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

    def get_focusable_rects(self) -> list[pygame.Rect]:
        return [
            self.continue_button_rect,
            self.settings_button_rect,
            self.menu_button_rect,
        ]

    def _activate_continue(self) -> None:
        self.app.states.pop()

    def _activate_settings(self) -> None:
        from .settings import SettingsScene

        self.go_to_settings = True
        self.app.states.push(
            SettingsScene(
                self.app,
                return_to_game=True,
                runtime_scene=self.previous_scene,
            )
        )

    def _activate_menu(self) -> None:
        self.go_to_menu = True
        sound_manager.stop_music()
        from ..core.sound_config import MusicState

        sound_manager.music_state_manager.transition_to(MusicState.MENU, force=True)
        from .main_menu import MainMenuScene

        self.app.states.switch(MainMenuScene(self.app))

    def update(self, dt: float):
        pass

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_p:
            self.app.states.pop()
            return

        if event.type == pygame.JOYBUTTONDOWN:
            from ..core.gamepad import XboxButton

            if event.button == XboxButton.A:
                pos = pygame.mouse.get_pos()
                if self.continue_button_rect.collidepoint(pos):
                    self._activate_continue()
                elif self.settings_button_rect.collidepoint(pos):
                    self._activate_settings()
                elif self.menu_button_rect.collidepoint(pos):
                    self._activate_menu()
                else:
                    # Sem botão sob a mira: A age como ``Continuar`` por
                    # ser a ação padrão na pausa.
                    self._activate_continue()
                return
            if event.button in (XboxButton.B, XboxButton.START):
                self.app.states.pop()
                return

        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.continue_button_rect.collidepoint(event.pos):
                self._activate_continue()
            elif self.settings_button_rect.collidepoint(event.pos):
                self._activate_settings()
            elif self.menu_button_rect.collidepoint(event.pos):
                self._activate_menu()

        elif event.type == pygame.MOUSEMOTION:
            self.continue_button_hovered = self.continue_button_rect.collidepoint(
                event.pos
            )
            self.settings_button_hovered = self.settings_button_rect.collidepoint(
                event.pos
            )
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

        overlay = pygame.Surface(
            (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        # Título
        title = self.title_font.render("PAUSADO", True, CUSTOM_GOLD)
        title_rect = title.get_rect(
            center=(Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 4)
        )
        surface.blit(title, title_rect)

        # Draw Buttons (estilo moderno - apenas bordas)
        self._draw_button(
            surface,
            self.continue_button_rect,
            "Continuar",
            CUSTOM_GOLD,
            self.continue_button_hovered,
        )

        self._draw_button(
            surface,
            self.settings_button_rect,
            "Configurações",
            CUSTOM_PURPLE,
            self.settings_button_hovered,
        )

        self._draw_button(
            surface,
            self.menu_button_rect,
            "Menu",
            CUSTOM_PURPLE,
            self.menu_button_hovered,
        )

        # Hint
        hint_text = self.hint_font.render("Pressione P para continuar", True, WHITE)
        hint_rect = hint_text.get_rect(
            center=(Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT - 40)
        )
        surface.blit(hint_text, hint_rect)

    def _draw_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        text: str,
        color: tuple[int, int, int],
        is_hovered: bool,
    ):
        """Desenha um botão com estilo moderno (apenas borda, sem fundo)."""
        # Inverter cores ao passar o mouse
        if color == CUSTOM_GOLD:
            border_color = CUSTOM_PURPLE if is_hovered else CUSTOM_GOLD
        else:
            border_color = CUSTOM_GOLD if is_hovered else CUSTOM_PURPLE

        # Apenas borda, sem fundo
        pygame.draw.rect(surface, border_color, rect, 2, border_radius=10)

        # Texto centralizado
        text_surf = self.button_font.render(text, True, WHITE)
        text_rect = text_surf.get_rect(center=rect.center)
        surface.blit(text_surf, text_rect)
