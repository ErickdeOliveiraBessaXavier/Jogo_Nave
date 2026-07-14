"""Tela de seleção de idioma — mostrada apenas no 1º boot (idioma não escolhido).

Bilíngue/neutra de propósito: como ainda não há idioma definido, o título aparece
nos dois ("Idioma / Language") e cada botão traz o nome nativo do idioma. Ao
confirmar, persiste a escolha, aplica no `i18n` e troca para o menu (que então
monta seus textos já no idioma certo).
"""

from typing import TYPE_CHECKING

import pygame

from ..core.assets import get_font
from ..core.colors import CUSTOM_DARK_BG, CUSTOM_GOLD, CUSTOM_PURPLE
from ..core.config import config as Config
from ..core.sound import sound_manager
from ..core.state import Scene
from ..core.translations import LANGUAGES
from .ui_helpers import draw_bordered_button

if TYPE_CHECKING:
    from ..app import GameApp


class LanguageSelectionScene(Scene):
    """Escolha inicial de idioma (Português / English)."""

    def __init__(self, app: "GameApp"):
        super().__init__(app)
        self.title_font = get_font(max(12, int(30 * self.ui_scale)))
        self.button_font = get_font(max(8, int(20 * self.ui_scale)))
        self.hint_font = get_font(max(8, int(11 * self.ui_scale)))

        self.entry_progress = 0.0
        self.entry_duration = 0.4

        # (código, rótulo nativo, rect) para cada idioma suportado.
        self.buttons: list[tuple[str, str, pygame.Rect]] = []
        self._build_layout()

    def _build_layout(self) -> None:
        cx = Config.SCREEN_WIDTH // 2
        cy = Config.SCREEN_HEIGHT // 2

        bw, bh = self._s(300), self._s(96)
        gap = self._s(40)
        total_w = len(LANGUAGES) * bw + (len(LANGUAGES) - 1) * gap
        start_x = cx - total_w // 2
        y = cy - bh // 2

        self.buttons = []
        for i, (code, label) in enumerate(LANGUAGES):
            rect = pygame.Rect(start_x + i * (bw + gap), y, bw, bh)
            self.buttons.append((code, label, rect))

    def enter(self) -> None:
        pygame.mouse.set_visible(True)
        self.entry_progress = 0.0
        # Foco inicial no 1º idioma (dá highlight p/ teclado/controle de cara).
        if self.buttons:
            try:
                pygame.mouse.set_pos(self.buttons[0][2].center)
            except pygame.error:
                pass

    # ── Navegação ────────────────────────────────────────────────────────────
    def _focus(self, index: int) -> None:
        """Move a mira para o botão `index` (highlight compartilha o hover)."""
        if not self.buttons:
            return
        index = max(0, min(len(self.buttons) - 1, index))
        try:
            pygame.mouse.set_pos(self.buttons[index][2].center)
        except pygame.error:
            pass
        sound_manager.play_sound("button_hover")

    def _current_index(self) -> int:
        pos = pygame.mouse.get_pos()
        for i, (_code, _label, rect) in enumerate(self.buttons):
            if rect.collidepoint(pos):
                return i
        return -1

    def _cycle(self, direction: int) -> None:
        idx = self._current_index()
        if idx == -1:
            self._focus(0 if direction > 0 else len(self.buttons) - 1)
        else:
            self._focus(idx + direction)

    def _select(self, code: str) -> None:
        sound_manager.play_sound("button_click")
        self.app.preferences.language = code
        self.app.preferences.save()

        from ..core.i18n import i18n

        i18n.set_language(code)

        from .main_menu import MainMenuScene

        self.app.states.switch(MainMenuScene(self.app))

    def _select_under_cursor(self) -> bool:
        pos = pygame.mouse.get_pos()
        for code, _label, rect in self.buttons:
            if rect.collidepoint(pos):
                self._select(code)
                return True
        return False

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._select_under_cursor()
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_LEFT, pygame.K_a):
                self._cycle(-1)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                self._cycle(+1)
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                if not self._select_under_cursor():
                    self._select(self.buttons[0][0])
        elif event.type == pygame.JOYBUTTONDOWN:
            from ..core.gamepad import XboxButton

            if event.button == XboxButton.A:
                if not self._select_under_cursor():
                    self._select(self.buttons[0][0])
            elif event.button == XboxButton.LB:
                self._cycle(-1)
            elif event.button == XboxButton.RB:
                self._cycle(+1)

    def get_focusable_rects(self) -> list[pygame.Rect]:
        """Botões de idioma — app.py usa pra snap-focus via DPad."""
        return [rect for _code, _label, rect in self.buttons]

    def update(self, dt: float) -> None:
        from ..core.visual_quality import visual_quality

        if not visual_quality.ui_animations:
            self.entry_progress = 1.0
        elif self.entry_progress < 1.0:
            self.entry_progress = min(1.0, self.entry_progress + dt / self.entry_duration)

    def render(self, surface: pygame.Surface) -> None:
        surface.fill(CUSTOM_DARK_BG)

        alpha = int(255 * self.entry_progress)
        offset_y = int(self._s(30) * (1.0 - self.entry_progress))

        # Título bilíngue (nenhum idioma escolhido ainda).
        title_surf = self.title_font.render("Idioma / Language", True, CUSTOM_GOLD)
        title_surf.set_alpha(alpha)
        surface.blit(
            title_surf,
            (
                Config.SCREEN_WIDTH // 2 - title_surf.get_width() // 2,
                self._s(150) + offset_y,
            ),
        )

        # Botões de idioma (highlight de hover/foco via draw_bordered_button).
        for _code, label, rect in self.buttons:
            draw_bordered_button(
                surface, rect, label, self.button_font, CUSTOM_PURPLE, alpha, offset_y
            )

        # Dica de navegação, também bilíngue.
        hint = "Selecione o idioma  ·  Select your language"
        hint_surf = self.hint_font.render(hint, True, (170, 170, 190))
        hint_surf.set_alpha(alpha)
        surface.blit(
            hint_surf,
            (
                Config.SCREEN_WIDTH // 2 - hint_surf.get_width() // 2,
                self.buttons[0][2].bottom + self._s(50) + offset_y,
            ),
        )
