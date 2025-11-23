import pygame
from typing import TYPE_CHECKING, Dict, Any
from ..core.state import Scene
from ..core.colors import WHITE, BLACK, GREEN, YELLOW, ORANGE, RED
from ..core.assets import get_font
from ..core.config import Config
from ..core.difficulty import DifficultyPreset, DifficultySettings
from ..core.sound import sound_manager

if TYPE_CHECKING:
    from ..app import GameApp


class DifficultySelectionScene(Scene):
    """Cena para seleção de dificuldade antes de iniciar o jogo."""

    def __init__(self, app: "GameApp"):
        super().__init__(app)
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

        self.setup_ui()

    def setup_ui(self):
        """Configura elementos da interface."""
        center_x = Config.SCREEN_WIDTH // 2
        
        # Título
        self.title_text = self.title_font.render(
            "Selecione a Dificuldade", True, WHITE
        )
        self.title_rect = self.title_text.get_rect(center=(center_x, 80))

        # Configurações dos botões
        button_width = 500
        button_height = 90
        spacing = 20  # Espaçamento entre botões
        num_buttons = len(DifficultyPreset)
        
        # Calcular altura total dos botões
        total_buttons_height = (button_height * num_buttons) + (spacing * (num_buttons - 1))
        
        # Centralizar verticalmente na tela (considerando o título)
        available_height = Config.SCREEN_HEIGHT - 160  # Espaço disponível (título + margem)
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
            desc_text = self.desc_font.render(
                settings["description"], True, BLACK
            )

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

    def enter(self):
        pygame.mouse.set_visible(True)

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            for preset, button_data in self.difficulty_buttons.items():
                if button_data["rect"].collidepoint(event.pos):
                    sound_manager.play_sound("button_click")
                    self.selected_difficulty = preset
                    self.start_game()

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
                self.app.states.pop()  # Voltar ao menu

    def start_game(self):
        """Inicia o jogo com a dificuldade selecionada."""
        from ..scenes.playing import PlayingScene

        # Validar dificuldade selecionada
        if self.selected_difficulty is None:
            return  # Não deveria acontecer, mas previne erro

        # Armazenar dificuldade no app
        self.app.selected_difficulty = self.selected_difficulty

        # Criar e empurrar a cena de jogo
        self.app.states.pop()  # Remove difficulty selection
        self.app.states.push(PlayingScene(
            self.app,
            self.app.level_manager,
            difficulty_preset=self.selected_difficulty
        ))

    def update(self, dt: float):
        pass

    def render(self, surface: pygame.Surface):
        surface.fill(BLACK)

        # Título
        surface.blit(self.title_text, self.title_rect)

        # Botões de dificuldade (centralizados verticalmente)
        for preset, button_data in self.difficulty_buttons.items():
            rect = button_data["rect"]
            color = button_data["color"]

            # Efeito de hover
            if preset == self.hovered_difficulty:
                color = tuple(min(c + 40, 255) for c in color)

            # Desenhar botão
            pygame.draw.rect(surface, color, rect, border_radius=10)
            pygame.draw.rect(surface, WHITE, rect, 3, border_radius=10)

            # Textos - melhor alinhamento
            name_rect = button_data["name_text"].get_rect(
                centerx=rect.centerx, top=rect.top + 10
            )
            desc_rect = button_data["desc_text"].get_rect(
                centerx=rect.centerx, centery=rect.centery - 5
            )
            lives_rect = button_data["lives_text"].get_rect(
                centerx=rect.centerx, bottom=rect.bottom - 10
            )

            surface.blit(button_data["name_text"], name_rect)
            surface.blit(button_data["desc_text"], desc_rect)
            surface.blit(button_data["lives_text"], lives_rect)

        # Instrução
        hint_text = self.desc_font.render(
            "ESC para voltar", True, WHITE
        )
        hint_rect = hint_text.get_rect(
            centerx=Config.SCREEN_WIDTH // 2,
            bottom=Config.SCREEN_HEIGHT - 30
        )
        surface.blit(hint_text, hint_rect)