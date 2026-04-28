from typing import TYPE_CHECKING, Any, Callable, Dict

import pygame

from ..core.assets import get_font
from ..core.colors import (BLACK, CUSTOM_DARK_BG, CUSTOM_GOLD, CUSTOM_PURPLE,
                           GREEN, ORANGE, RED, YELLOW)
from ..core.config import config as Config
from ..core.difficulty import DifficultyPreset, DifficultySettings
from ..core.sound import sound_manager
from ..core.state import Scene

if TYPE_CHECKING:
    from ..app import GameApp


class DifficultySelectionView:
    """View para seleção de dificuldade (pode ser usada dentro de outras cenas)."""

    def __init__(
        self,
        on_select: Callable[[DifficultyPreset], None],
        on_back: Callable[[], None],
        renderer: Any = None,
    ):
        """
        Args:
            on_select: Callback chamado quando uma dificuldade é selecionada
            on_back: Callback chamado quando o usuário quer voltar
            renderer: Renderer compartilhado (opcional)
        """
        self.on_select = on_select
        self.on_back = on_back
        self.renderer = renderer

        self.title_font = get_font(48)
        self.button_font = get_font(20)
        self.desc_font = get_font(16)

        # Cores por dificuldade
        self.difficulty_colors = {
            DifficultyPreset.CASUAL: GREEN,
            DifficultyPreset.NORMAL: YELLOW,
            DifficultyPreset.HARDCORE: ORANGE,
            DifficultyPreset.NIGHTMARE: RED,
        }

        self.difficulty_buttons: Dict[DifficultyPreset, Dict[str, Any]] = {}
        self.selected_difficulty: DifficultyPreset | None = None
        self.hovered_difficulty: DifficultyPreset | None = None

        # Animação de entrada
        self.entry_progress = 0.0
        self.is_entering = True
        self.entry_duration = 0.4

        self.setup_ui()

    def setup_ui(self):
        """Configura elementos da interface."""
        center_x = Config.SCREEN_WIDTH // 2

        # Título
        self.title_text = self.title_font.render(
            "Selecione a Dificuldade", True, CUSTOM_GOLD
        )
        self.title_rect = self.title_text.get_rect(center=(center_x, 80))

        # Configurações dos botões
        button_width = 500
        button_height = 90
        spacing = 20  # Espaçamento entre botões
        num_buttons = len(DifficultyPreset)

        # Calcular altura total dos botões
        total_buttons_height = (button_height * num_buttons) + (
            spacing * (num_buttons - 1)
        )

        # Centralizar verticalmente na tela (considerando o título)
        available_height = (
            Config.SCREEN_HEIGHT - 160
        )  # Espaço disponível (título + margem)
        start_y = 120 + (available_height - total_buttons_height) // 2

        # Criar botões para cada dificuldade
        self.difficulty_buttons = {}

        for i, preset in enumerate(DifficultyPreset):
            settings = DifficultySettings.get_settings(preset)
            button_y = start_y + (i * (button_height + spacing))

            # Retângulo do botão centralizado horizontalmente
            button_rect = pygame.Rect(0, 0, button_width, button_height)
            button_rect.centerx = center_x
            button_rect.y = button_y

            # Textos
            name_text = self.button_font.render(settings["name"], True, BLACK)
            desc_text = self.desc_font.render(settings["description"], True, BLACK)

            # Informações extras
            lives_text = self.desc_font.render(
                f"Vidas: {settings['lives']}", True, BLACK
            )

            self.difficulty_buttons[preset] = {
                "rect": button_rect,
                "name_text": name_text,
                "desc_text": desc_text,
                "lives_text": lives_text,
                "color": self.difficulty_colors[preset],
            }

    def reset(self):
        """Reseta o estado da view para reiniciar animação."""
        self.entry_progress = 0.0
        self.is_entering = True
        self.selected_difficulty = None
        self.hovered_difficulty = None

    def handle_event(self, event: pygame.event.Event):
        """Processa eventos da view."""
        if event.type == pygame.MOUSEBUTTONDOWN:
            for preset, button_data in self.difficulty_buttons.items():
                if button_data["rect"].collidepoint(event.pos):
                    sound_manager.play_sound("button_click")
                    self.selected_difficulty = preset
                    self.on_select(preset)
                    return True  # Evento consumido

        elif event.type == pygame.MOUSEMOTION:
            prev_hovered = self.hovered_difficulty
            self.hovered_difficulty = None

            for preset, button_data in self.difficulty_buttons.items():
                if button_data["rect"].collidepoint(event.pos):
                    self.hovered_difficulty = preset

            # Som de hover
            if self.hovered_difficulty != prev_hovered and self.hovered_difficulty:
                sound_manager.play_sound("button_hover")

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.on_back()
                return True  # Evento consumido

        return False  # Evento não consumido

    def update(self, dt: float):
        """Atualiza a lógica da view."""
        if self.is_entering and self.entry_progress < 1.0:
            self.entry_progress = min(
                1.0, self.entry_progress + dt / self.entry_duration
            )
            if self.entry_progress >= 1.0:
                self.is_entering = False

    def render(self, surface: pygame.Surface):
        """Renderiza a view."""
        # Calcular alpha baseado no progresso
        alpha = int(255 * self.entry_progress)
        offset_y = int(30 * (1.0 - self.entry_progress))

        # Título
        title_surface = self.title_text.copy()
        title_surface.set_alpha(alpha)
        title_pos = (self.title_rect.x, self.title_rect.y + offset_y)
        surface.blit(title_surface, title_pos)

        # Botões de dificuldade
        for preset, button_data in self.difficulty_buttons.items():
            rect = button_data["rect"].copy()
            rect.y += offset_y
            color = button_data["color"]

            # Efeito de hover
            if preset == self.hovered_difficulty:
                color = tuple(min(c + 40, 255) for c in color)

            # Criar surface temporária para aplicar alpha
            temp_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)

            # Desenhar botão na surface temporária
            pygame.draw.rect(
                temp_surface, (*color, alpha), temp_surface.get_rect(), border_radius=10
            )
            pygame.draw.rect(
                temp_surface,
                (*CUSTOM_PURPLE, alpha),
                temp_surface.get_rect(),
                3,
                border_radius=10,
            )

            # Blit no surface principal
            surface.blit(temp_surface, rect.topleft)

            # Textos com alpha
            name_surface = button_data["name_text"].copy()
            name_surface.set_alpha(alpha)
            name_rect = name_surface.get_rect(centerx=rect.centerx, top=rect.top + 10)

            desc_surface = button_data["desc_text"].copy()
            desc_surface.set_alpha(alpha)
            desc_rect = desc_surface.get_rect(
                centerx=rect.centerx, centery=rect.centery - 5
            )

            lives_surface = button_data["lives_text"].copy()
            lives_surface.set_alpha(alpha)
            lives_rect = lives_surface.get_rect(
                centerx=rect.centerx, bottom=rect.bottom - 10
            )

            surface.blit(name_surface, name_rect)
            surface.blit(desc_surface, desc_rect)
            surface.blit(lives_surface, lives_rect)

        # Instrução
        hint_text = self.desc_font.render("ESC para voltar", True, CUSTOM_GOLD)
        hint_surface = hint_text.copy()
        hint_surface.set_alpha(alpha)
        hint_rect = hint_surface.get_rect(
            centerx=Config.SCREEN_WIDTH // 2,
            bottom=Config.SCREEN_HEIGHT - 30 + offset_y,
        )
        surface.blit(hint_surface, hint_rect)


class DifficultySelectionScene(Scene):
    """Cena para seleção de dificuldade antes de iniciar o jogo (mantida para compatibilidade)."""

    def __init__(self, app: "GameApp"):
        super().__init__(app)
        self.view = DifficultySelectionView(
            on_select=self._on_difficulty_selected, on_back=self._on_back
        )

    def _on_difficulty_selected(self, preset: DifficultyPreset):
        """Callback quando uma dificuldade é selecionada."""
        self.start_game(preset)

    def _on_back(self):
        """Callback quando o usuário quer voltar."""
        self.app.states.pop()

    def enter(self):
        pygame.mouse.set_visible(True)
        self.view.reset()

    def handle_event(self, event: pygame.event.Event):
        self.view.handle_event(event)

    def start_game(self, preset: DifficultyPreset):
        """Inicia o jogo com a dificuldade selecionada."""
        from ..scenes.playing import PlayingScene

        # Armazenar dificuldade no app
        self.app.selected_difficulty = preset

        # Criar e empurrar a cena de jogo
        self.app.states.pop()  # Remove difficulty selection
        self.app.states.push(
            PlayingScene(
                self.app,
                self.app.level_manager,
                difficulty_preset=preset,
            )
        )

    def update(self, dt: float):
        self.view.update(dt)

    def render(self, surface: pygame.Surface):
        surface.fill(CUSTOM_DARK_BG)
        self.view.render(surface)
