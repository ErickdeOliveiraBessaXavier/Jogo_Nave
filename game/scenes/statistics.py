from typing import Optional, TYPE_CHECKING, Callable, List, Any
import pygame

if TYPE_CHECKING:
    from ..app import GameApp

from ..core import colors
from ..core.colors import Color
from ..core.config import Config
from ..core.assets import get_font
from ..core.meta_progression import PlayerProfile, ProfileVisualizer
from ..core.state import Scene


class Button:
    """Um botão de UI simples."""

    def __init__(self, rect: pygame.Rect, text: str, on_click: Callable[[], None], text_color: Color = colors.WHITE, font_size: int = 24):
        self.rect = rect
        self.on_click = on_click
        self.font = get_font(font_size)
        self.text_surf = self.font.render(text, True, text_color)
        self.text_rect = self.text_surf.get_rect(center=self.rect.center)
        self.hovered = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos):
            self.on_click()
            return True
        return False

    def update(self) -> None:
        self.hovered = self.rect.collidepoint(pygame.mouse.get_pos())

    def render(self, surface: pygame.Surface, color_normal: Color, color_hover: Color) -> None:
        color = color_hover if self.hovered else color_normal
        pygame.draw.rect(surface, color, self.rect, border_radius=10)
        pygame.draw.rect(surface, colors.WHITE, self.rect, 2, border_radius=10)
        surface.blit(self.text_surf, self.text_rect)


class ConfirmationDialog:
    """Um diálogo de confirmação."""

    def __init__(self, question_lines: List[str], on_yes: Callable[[], None], on_no: Callable[[], None]):
        self.on_yes = on_yes
        self.on_no = on_no
        self.font = get_font(24)

        self.lines = [self.font.render(line, True, colors.WHITE) for line in question_lines]
        total_height = sum(line.get_height() for line in self.lines) + (len(self.lines) - 1) * 10
        start_y = Config.SCREEN_HEIGHT // 2 - 50 - total_height // 2

        self.line_rects: List[pygame.Rect] = []
        current_y = start_y
        for line in self.lines:
            rect = line.get_rect(center=(Config.SCREEN_WIDTH // 2, current_y + line.get_height() // 2))
            self.line_rects.append(rect)
            current_y += line.get_height() + 10

        self.yes_button = Button(
            pygame.Rect(Config.SCREEN_WIDTH // 2 - 110, Config.SCREEN_HEIGHT // 2 + 20, 100, 40),
            "Sim", self._on_yes_click, text_color=colors.BLACK
        )
        self.no_button = Button(
            pygame.Rect(Config.SCREEN_WIDTH // 2 + 10, Config.SCREEN_HEIGHT // 2 + 20, 100, 40),
            "Não", self._on_no_click, text_color=colors.BLACK
        )

        self.box_rect = pygame.Rect(Config.SCREEN_WIDTH // 2 - 250, Config.SCREEN_HEIGHT // 2 - 100, 500, 200)
        self.overlay = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))
        self.overlay.set_alpha(128)
        self.overlay.fill(colors.BLACK)

    def _on_yes_click(self) -> None:
        self.on_yes()

    def _on_no_click(self) -> None:
        self.on_no()

    def handle_event(self, event: pygame.event.Event) -> None:
        self.yes_button.handle_event(event)
        self.no_button.handle_event(event)

    def update(self) -> None:
        self.yes_button.update()
        self.no_button.update()

    def render(self, surface: pygame.Surface) -> None:
        surface.blit(self.overlay, (0, 0))
        pygame.draw.rect(surface, colors.GRAY, self.box_rect, border_radius=10)
        pygame.draw.rect(surface, colors.WHITE, self.box_rect, 3, border_radius=10)

        for line, rect in zip(self.lines, self.line_rects):
            surface.blit(line, rect)

        self.yes_button.render(surface, colors.GREEN, colors.BRIGHT_GREEN)
        self.no_button.render(surface, colors.RED, colors.BRIGHT_RED)


class Card:
    """Um contêiner retangular para agrupar elementos de UI."""

    def __init__(self, rect: pygame.Rect, title: str, title_font_size: int = 28, padding: int = 15):
        self.rect = rect
        self.title = title
        self.padding = padding
        self.title_font = get_font(title_font_size)
        self.title_surf = self.title_font.render(self.title, True, colors.YELLOW)
        self.title_rect = self.title_surf.get_rect(topleft=(self.rect.x + padding, self.rect.y + padding))
        self.content_rect = pygame.Rect(
            self.rect.x + padding,
            self.title_rect.bottom + 10,
            self.rect.width - 2 * padding,
            self.rect.height - (self.title_rect.bottom - self.rect.y) - padding
        )

    def render(self, surface: pygame.Surface) -> None:
        """Renderiza o card e seu título."""
        pygame.draw.rect(surface, colors.DARK_GRAY, self.rect, border_radius=12)
        pygame.draw.rect(surface, colors.GRAY, self.rect, 2, border_radius=12)
        surface.blit(self.title_surf, self.title_rect)


class ScrollableCard(Card):
    """Um card com conteúdo que pode ser rolado verticalmente."""

    def __init__(self, rect: pygame.Rect, title: str, content_height: int, **kwargs: Any):
        super().__init__(rect, title, **kwargs)
        self.content_height = content_height
        self.scroll_y = 0
        self.scroll_speed = 30
        self.visible_content_surf = pygame.Surface(self.content_rect.size)
        self.full_content_surf = pygame.Surface((self.content_rect.width, content_height))

    def handle_event(self, event: pygame.event.Event) -> None:
        if not self.rect.collidepoint(pygame.mouse.get_pos()):
            return
        if event.type == pygame.MOUSEWHEEL:
            self.scroll_y += event.y * self.scroll_speed
            self.clamp_scroll()

    def clamp_scroll(self) -> None:
        """Garante que o scroll permaneça dentro dos limites."""
        max_scroll = self.content_height - self.content_rect.height
        self.scroll_y = max(0, min(self.scroll_y, max_scroll))

    def render_content(self, surface: pygame.Surface) -> None:
        """Renderiza o conteúdo rolável."""
        self.visible_content_surf.blit(self.full_content_surf, (0, -self.scroll_y))
        surface.blit(self.visible_content_surf, self.content_rect.topleft)

    def render(self, surface: pygame.Surface) -> None:
        super().render(surface)
        self.render_content(surface)


class StatisticsScene(Scene):
    """Cena de estatísticas do jogador."""

    def __init__(self, game_app: "GameApp"):
        super().__init__(game_app)
        self.profile: Optional[PlayerProfile] = None
        self.dialog: Optional[ConfirmationDialog] = None
        self.cards: List[Card] = []
        self.scrollable_card: Optional[ScrollableCard] = None

        self._init_layout()

        self.reset_button = Button(
            pygame.Rect(0, 0, 200, 50),
            "Resetar Perfil",
            self.show_confirmation,
            text_color=colors.BLACK
        )
        self.back_button = Button(
            pygame.Rect(0, 0, 200, 50),
            "Voltar",
            self.app.states.pop,
            text_color=colors.BLACK
        )
        # Posicionar botões no rodapé
        margin_bottom = 40
        button_y = Config.SCREEN_HEIGHT - margin_bottom - self.reset_button.rect.height
        self.reset_button.rect.bottomright = (Config.SCREEN_WIDTH - 30, button_y)
        self.back_button.rect.bottomleft = (30, button_y)

    def _init_layout(self):
        """Inicializa o layout em colunas com cards."""
        margin = 30
        top_y = 100
        bottom_y = Config.SCREEN_HEIGHT - 120
        col_width = (Config.SCREEN_WIDTH - 3 * margin) // 2
        col1_x = margin
        col2_x = margin * 2 + col_width

        # Coluna 1
        card1_h = 250
        self.cards.append(Card(pygame.Rect(col1_x, top_y, col_width, card1_h), "Performance Geral"))

        card2_h = bottom_y - (top_y + card1_h + margin)
        self.cards.append(Card(pygame.Rect(col1_x, top_y + card1_h + margin, col_width, card2_h), "Recomendações"))

        # Coluna 2
        card3_h = 300
        self.cards.append(Card(pygame.Rect(col2_x, top_y, col_width, card3_h), "Taxa de Sucesso por Nível"))

        card4_h = bottom_y - (top_y + card3_h + margin)
        # A altura do conteúdo será definida dinamicamente
        self.scrollable_card = ScrollableCard(
            pygame.Rect(col2_x, top_y + card3_h + margin, col_width, card4_h),
            "Estatísticas por Nível", content_height=100
        )
        self.cards.append(self.scrollable_card)

    def enter(self) -> None:
        super().enter()
        self.load_profile()
        self._update_scrollable_content()

    def _update_scrollable_content(self):
        """Atualiza o conteúdo e a altura do card rolável."""
        if not self.profile or not self.scrollable_card:
            return
        
        # Estimar altura do conteúdo
        num_levels = len(self.profile.level_stats)
        content_height = max(self.scrollable_card.content_rect.height, num_levels * 130 + 20)
        
        self.scrollable_card.content_height = content_height
        self.scrollable_card.full_content_surf = pygame.Surface(
            (self.scrollable_card.content_rect.width, content_height)
        )
        self.scrollable_card.full_content_surf.fill(colors.DARK_GRAY)
        
        # Renderizar o conteúdo no surf de conteúdo completo
        ProfileVisualizer.render_level_details_list(
            self.scrollable_card.full_content_surf,
            self.profile
        )

    def load_profile(self) -> None:
        from pathlib import Path
        profile_path = Path("player_profile.json")
        self.profile = PlayerProfile(profile_path)

    def update(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        if not self.dialog and keys[pygame.K_ESCAPE]:
            self.app.states.pop()

        if self.dialog:
            self.dialog.update()
        else:
            self.reset_button.update()
            self.back_button.update()

        if self.profile:
            self.profile.auto_save()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.dialog:
            self.dialog.handle_event(event)
        else:
            self.reset_button.handle_event(event)
            self.back_button.handle_event(event)
            if self.scrollable_card:
                self.scrollable_card.handle_event(event)

    def render(self, surface: pygame.Surface) -> None:
        surface.fill(colors.BLACK)

        # Título da cena
        title_font = get_font(48)
        title_surf = title_font.render("Estatísticas", True, colors.WHITE)
        title_rect = title_surf.get_rect(center=(Config.SCREEN_WIDTH // 2, 50))
        surface.blit(title_surf, title_rect)

        if not self.profile:
            font = get_font(24)
            text = font.render("Erro ao carregar perfil!", True, colors.RED)
            surface.blit(text, (50, 150))
            return

        # Renderizar cards
        for card in self.cards:
            card.render(surface)

        # Renderizar conteúdo dos cards com clipping
        # Card 1: Geral
        surface.set_clip(self.cards[0].content_rect)
        ProfileVisualizer.render_geral_card(surface, self.profile, self.cards[0].content_rect)
        surface.set_clip(None)

        # Card 2: Recomendações
        surface.set_clip(self.cards[1].content_rect)
        ProfileVisualizer.render_recomendacoes_card(surface, self.profile, self.cards[1].content_rect)
        surface.set_clip(None)

        # Card 3: Gráfico
        surface.set_clip(self.cards[2].content_rect)
        ProfileVisualizer.render_graph_card(surface, self.profile, self.cards[2].content_rect)
        surface.set_clip(None)

        # Renderizar botões
        self.reset_button.render(surface, colors.RED, colors.BRIGHT_RED)
        self.back_button.render(surface, colors.GRAY, colors.BRIGHT_GRAY)
        
        # Renderizar diálogo de confirmação por último
        if self.dialog:
            self.dialog.render(surface)

    def show_confirmation(self) -> None:
        self.dialog = ConfirmationDialog(
            ["Tem certeza que deseja", "resetar seu perfil?", "Todo o progresso será perdido."],
            self.reset_profile,
            self.close_confirmation
        )


    def close_confirmation(self) -> None:
        self.dialog = None

    def reset_profile(self) -> None:
        if self.profile:
            self.profile.reset()
            self.load_profile()
        self.close_confirmation()