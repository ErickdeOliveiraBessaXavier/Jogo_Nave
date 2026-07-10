from typing import TYPE_CHECKING, Callable

import pygame

from ..core import colors
from ..core.assets import get_font
from ..core.colors import BLACK, CUSTOM_GOLD, CUSTOM_PURPLE, WHITE
from ..core.config import config as Config
from ..core.i18n import t
from ..core.sound import sound_manager
from ..core.state import Scene
from .ui_helpers import wrap_text, draw_bordered_button

if TYPE_CHECKING:
    from ..app import GameApp


class ControlsModalScene(Scene):
    """Modal de instruções exibido antes do início da gameplay."""

    def __init__(self, app: "GameApp", on_finish: Callable[[], None]):
        super().__init__(app)
        self.on_finish = on_finish
        self.timer = 10.0
        self.show_again = (
            True  # Estado do checkbox (invertido para salvar em show_controls_modal)
        )

        self.title_font = get_font(max(8, int(32 * self.ui_scale)))
        self.item_font = get_font(max(8, int(18 * self.ui_scale)))
        self.small_font = get_font(max(8, int(16 * self.ui_scale)))

        self._calculate_layout()

    def _calculate_layout(self):
        screen_w, screen_h = Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT

        # Modal mais largo para garantir que as colunas não se sobreponham
        self.modal_w = self._s(760)
        self.modal_h = self._s(420)
        self.modal_rect = pygame.Rect(
            (screen_w - self.modal_w) // 2,
            (screen_h - self.modal_h) // 2,
            self.modal_w,
            self.modal_h,
        )

        # Botão "Entendi" - Centralizado horizontalmente na parte inferior
        btn_w = self._s(200)
        btn_h = self._s(45)
        self.button_rect = pygame.Rect(
            self.modal_rect.centerx - btn_w // 2,
            self.modal_rect.bottom - self._s(120),
            btn_w,
            btn_h,
        )

        # Checkbox "Não mostrar mais" - Abaixo do botão
        cb_size = self._s(18)
        self.checkbox_rect = pygame.Rect(
            self.modal_rect.centerx - self._s(110),
            self.button_rect.bottom + self._s(15),
            cb_size,
            cb_size,
        )

    def enter(self):
        pygame.mouse.set_visible(True)

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            # Checkbox (hitbox facilitada)
            click_rect = self.checkbox_rect.inflate(self._s(200), self._s(10))
            if click_rect.collidepoint(pos):
                self._toggle_checkbox()
            # Botão Entendi
            if self.button_rect.collidepoint(pos):
                self._finish()

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                self._finish()

        if event.type == pygame.JOYBUTTONDOWN:
            from ..core.gamepad import XboxButton

            # A: ativa o item sob o cursor (checkbox ou botão). Se cursor
            # estiver fora, fecha o modal (ação padrão). X é atalho dedicado
            # para alternar o checkbox sem precisar mirar.
            if event.button == XboxButton.A:
                pos = pygame.mouse.get_pos()
                if self.checkbox_rect.inflate(self._s(200), self._s(10)).collidepoint(pos):
                    self._toggle_checkbox()
                else:
                    self._finish()
                return
            if event.button == XboxButton.X:
                self._toggle_checkbox()
                return
            if event.button in (XboxButton.B, XboxButton.BACK, XboxButton.START):
                self._finish()
                return

    def _toggle_checkbox(self) -> None:
        self.show_again = not self.show_again
        sound_manager.play_sound("button_hover")

    def get_focusable_rects(self):
        # Inflado igual ao hitbox de mouse pra DPad alternar entre checkbox e botão.
        return [self.button_rect, self.checkbox_rect.inflate(self._s(200), self._s(10))]

    def _finish(self):
        sound_manager.play_sound("button_click")
        # Salvar preferência
        self.app.preferences.show_controls_modal = self.show_again
        self.app.preferences.save()

        self.app.states.pop()  # Remove a si mesma do stack
        self.on_finish()

    def update(self, dt: float):
        self.timer -= dt
        if self.timer <= 0:
            self._finish()

    def render(self, surface: pygame.Surface):
        # Overlay escuro no fundo da tela toda
        overlay = pygame.Surface(
            (surface.get_width(), surface.get_height()), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        # Fundo do modal (preto)
        modal_radius = self._s(15)
        pygame.draw.rect(surface, BLACK, self.modal_rect, border_radius=modal_radius)
        pygame.draw.rect(
            surface, CUSTOM_GOLD, self.modal_rect, 2, border_radius=modal_radius
        )

        # Título
        title_surf = self.title_font.render(t("controls.title"), True, CUSTOM_GOLD)
        surface.blit(
            title_surf,
            (
                self.modal_rect.centerx - title_surf.get_width() // 2,
                self.modal_rect.y + self._s(25),
            ),
        )

        # Configuração das colunas
        left_x = self.modal_rect.x + self._s(40)
        right_x = self.modal_rect.centerx + self._s(20)
        max_col_w = (self.modal_w // 2) - self._s(60)

        # Instruções: trocam entre teclado e controle conforme o input ativo
        # (preferência ligada + gamepad conectado).
        gamepad_active = (
            self.app.gamepad.is_active if hasattr(self.app, "gamepad") else False
        )
        if gamepad_active:
            left_col_raw = [
                t("controls.gp.move"),
                t("controls.gp.shoot"),
                t("controls.gp.pause"),
            ]
            right_col_raw = [
                t("controls.gp.rotate"),
                t("controls.gp.dash"),
                t("controls.gp.powers"),
            ]
        else:
            left_col_raw = [
                t("controls.kb.move"),
                t("controls.kb.shoot"),
                t("controls.kb.pause"),
            ]
            right_col_raw = [
                t("controls.kb.rotate"),
                t("controls.kb.dash"),
                t("controls.kb.powers"),
            ]

        def draw_column(items: list[str], start_x: int, start_y: int):
            curr_y = start_y
            for item in items:
                wrapped_lines = wrap_text(self.item_font, item, max_col_w)
                for line in wrapped_lines:
                    text_surf = self.item_font.render(line, True, WHITE)
                    surface.blit(text_surf, (start_x, curr_y))
                    curr_y += self._s(25)  # Espaço entre linhas da mesma instrução
                curr_y += self._s(15)  # Espaço extra entre instruções diferentes

        y_start = self.modal_rect.y + self._s(90)
        draw_column(left_col_raw, left_x, y_start)
        draw_column(right_col_raw, right_x, y_start)

        # Timer
        timer_text = t("controls.starting_in", n=max(0, int(self.timer + 0.9)))
        timer_surf = self.small_font.render(timer_text, True, colors.GRAY)
        surface.blit(
            timer_surf,
            (
                self.modal_rect.centerx - timer_surf.get_width() // 2,
                self.modal_rect.bottom - self._s(25),
            ),
        )

        # Botão Entendi
        draw_bordered_button(
            surface, self.button_rect, t("controls.got_it"), self.item_font, CUSTOM_PURPLE
        )

        # Checkbox "Não mostrar mais" abaixo do botão
        pygame.draw.rect(
            surface, CUSTOM_GOLD, self.checkbox_rect, 1, border_radius=self._s(3)
        )
        if not self.show_again:
            inner_rect = self.checkbox_rect.inflate(-self._s(6), -self._s(6))
            pygame.draw.rect(surface, CUSTOM_GOLD, inner_rect, border_radius=self._s(1))

        # Fonte menor para o checkbox
        tiny_font = get_font(max(8, int(12 * self.ui_scale)))
        label_surf = tiny_font.render(t("controls.dont_show"), True, colors.GRAY)
        surface.blit(
            label_surf,
            (
                self.checkbox_rect.right + self._s(8),
                self.checkbox_rect.centery - label_surf.get_height() // 2,
            ),
        )
