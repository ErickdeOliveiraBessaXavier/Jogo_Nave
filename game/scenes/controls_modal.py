from typing import TYPE_CHECKING, Callable

import pygame

from ..core import colors
from ..core.assets import get_font
from ..core.colors import BLACK, CUSTOM_GOLD, CUSTOM_PURPLE, WHITE
from ..core.config import config as Config
from ..core.sound import sound_manager
from ..core.state import Scene
from .ui_helpers import draw_bordered_button

if TYPE_CHECKING:
    from ..app import GameApp


class ControlsModalScene(Scene):
    """Modal de instruções exibido antes do início da gameplay."""

    def __init__(self, app: "GameApp", on_finish: Callable[[], None]):
        super().__init__(app)
        self.on_finish = on_finish
        self.timer = 10.0
        self.show_again = True  # Estado do checkbox (invertido para salvar em show_controls_modal)

        self.title_font = get_font(32)
        self.item_font = get_font(18)
        self.small_font = get_font(16)

        self._calculate_layout()

    def _calculate_layout(self):
        screen_w, screen_h = Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
        
        # Modal mais largo para garantir que as colunas não se sobreponham
        self.modal_w = 760
        self.modal_h = 420
        self.modal_rect = pygame.Rect(
            (screen_w - self.modal_w) // 2,
            (screen_h - self.modal_h) // 2,
            self.modal_w,
            self.modal_h
        )

        # Botão "Entendi" - Centralizado horizontalmente na parte inferior
        btn_w = 200
        btn_h = 45
        self.button_rect = pygame.Rect(
            self.modal_rect.centerx - btn_w // 2,
            self.modal_rect.bottom - 120,
            btn_w,
            btn_h
        )

        # Checkbox "Não mostrar mais" - Abaixo do botão
        cb_size = 18
        self.checkbox_rect = pygame.Rect(
            self.modal_rect.centerx - 110,
            self.button_rect.bottom + 15,
            cb_size,
            cb_size
        )

    def enter(self):
        pygame.mouse.set_visible(True)

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            # Checkbox (hitbox facilitada)
            click_rect = self.checkbox_rect.inflate(200, 10)
            if click_rect.collidepoint(pos):
                self.show_again = not self.show_again
                sound_manager.play_sound("button_hover")
            
            # Botão Entendi
            if self.button_rect.collidepoint(pos):
                self._finish()

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                self._finish()

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

    def _wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        """Quebra o texto em múltiplas linhas para caber na largura."""
        words = text.split(' ')
        lines: list[str] = []
        current_line: list[str] = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            if font.size(test_line)[0] <= max_width:
                current_line.append(word)
            else:
                lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines

    def render(self, surface: pygame.Surface):
        # Overlay escuro no fundo da tela toda
        overlay = pygame.Surface((surface.get_width(), surface.get_height()), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        # Fundo do modal (preto)
        pygame.draw.rect(surface, BLACK, self.modal_rect, border_radius=15)
        pygame.draw.rect(surface, CUSTOM_GOLD, self.modal_rect, 2, border_radius=15)

        # Título
        title_surf = self.title_font.render("Instruções de Voo", True, CUSTOM_GOLD)
        surface.blit(title_surf, (self.modal_rect.centerx - title_surf.get_width() // 2, self.modal_rect.y + 25))

        # Configuração das colunas
        left_x = self.modal_rect.x + 40
        right_x = self.modal_rect.centerx + 20
        max_col_w = (self.modal_w // 2) - 60

        # Instruções
        left_col_raw = [
            "• Mouse/WASD: Mover",
            "• Espaço: Atirar",
            "• P: Pausar | ESC: Sair",
        ]
        right_col_raw = [
            "• Ctrl: Girar Nave",
            "• Shift: Dash",
            "• Teclado Num: Poderes",
        ]

        def draw_column(items: list[str], start_x: int, start_y: int):
            curr_y = start_y
            for item in items:
                wrapped_lines = self._wrap_text(item, self.item_font, max_col_w)
                for line in wrapped_lines:
                    text_surf = self.item_font.render(line, True, WHITE)
                    surface.blit(text_surf, (start_x, curr_y))
                    curr_y += 25 # Espaço entre linhas da mesma instrução
                curr_y += 15 # Espaço extra entre instruções diferentes

        y_start = self.modal_rect.y + 90
        draw_column(left_col_raw, left_x, y_start)
        draw_column(right_col_raw, right_x, y_start)

        # Timer
        timer_text = f"Iniciando em: {max(0, int(self.timer + 0.9))}s"
        timer_surf = self.small_font.render(timer_text, True, colors.GRAY)
        surface.blit(timer_surf, (self.modal_rect.centerx - timer_surf.get_width() // 2, self.modal_rect.bottom - 25))

        # Botão Entendi
        draw_bordered_button(
            surface,
            self.button_rect,
            "Entendi",
            self.item_font,
            CUSTOM_PURPLE
        )

        # Checkbox "Não mostrar mais" abaixo do botão
        pygame.draw.rect(surface, CUSTOM_GOLD, self.checkbox_rect, 1, border_radius=3)
        if not self.show_again:
            inner_rect = self.checkbox_rect.inflate(-6, -6)
            pygame.draw.rect(surface, CUSTOM_GOLD, inner_rect, border_radius=1)
        
        # Fonte menor para o checkbox
        tiny_font = get_font(12)
        label_surf = tiny_font.render("Não mostrar novamente", True, colors.GRAY)
        surface.blit(label_surf, (self.checkbox_rect.right + 8, self.checkbox_rect.centery - label_surf.get_height() // 2))
