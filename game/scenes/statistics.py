from typing import Optional, TYPE_CHECKING, Callable, List
from enum import Enum
import pygame

if TYPE_CHECKING:
    from ..app import GameApp

from ..core import colors
from ..core.colors import Color
from ..core.config import config as Config
from ..core.assets import get_font
from ..core.meta_progression import PlayerProfile, ProfileVisualizer
from ..core.state import Scene


class Button:
    """Um botão de UI simples."""

    def __init__(
        self,
        rect: pygame.Rect,
        text: str,
        on_click: Callable[[], None],
        text_color: Color = colors.WHITE,
        font_size: int = 24,
    ):
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

    def render(
        self, surface: pygame.Surface, color_normal: Color, color_hover: Color
    ) -> None:
        color = color_hover if self.hovered else color_normal
        pygame.draw.rect(surface, color, self.rect, border_radius=10)
        pygame.draw.rect(surface, colors.WHITE, self.rect, 2, border_radius=10)
        surface.blit(self.text_surf, self.text_rect)


class ConfirmationDialog:
    """Um diálogo de confirmação."""

    def __init__(
        self,
        question_lines: List[str],
        on_yes: Callable[[], None],
        on_no: Callable[[], None],
    ):
        self.on_yes = on_yes
        self.on_no = on_no
        self.font = get_font(24)

        self.lines = [
            self.font.render(line, True, colors.WHITE) for line in question_lines
        ]

        # Calculate text height
        text_height = (
            sum(line.get_height() for line in self.lines) + (len(self.lines) - 1) * 10
        )

        # Button dimensions
        button_width = 140
        button_height = 48
        button_font_size = 28

        # Spacing
        top_padding = 40
        text_button_spacing = 20
        bottom_padding = 24

        # Calculate total content height
        total_content_height = (
            top_padding
            + text_height
            + text_button_spacing
            + button_height
            + bottom_padding
        )

        # Box dimensions
        box_width = max(400, max(line.get_width() for line in self.lines) + 60)
        box_height = max(160, total_content_height)
        box_x = Config.SCREEN_WIDTH // 2 - box_width // 2
        box_y = Config.SCREEN_HEIGHT // 2 - box_height // 2
        self.box_rect = pygame.Rect(box_x, box_y, box_width, box_height)

        # Position text lines
        self.line_rects: List[pygame.Rect] = []
        current_y = box_y + top_padding
        for line in self.lines:
            rect = line.get_rect(
                center=(self.box_rect.centerx, current_y + line.get_height() // 2)
            )
            self.line_rects.append(rect)
            current_y += line.get_height() + 10

        # Position buttons at the bottom
        button_y = box_y + box_height - bottom_padding - button_height
        self.yes_button = Button(
            pygame.Rect(
                self.box_rect.centerx - button_width - 10,
                button_y,
                button_width,
                button_height,
            ),
            "Sim",
            self._on_yes_click,
            text_color=colors.BLACK,
            font_size=button_font_size,
        )
        self.no_button = Button(
            pygame.Rect(
                self.box_rect.centerx + 10, button_y, button_width, button_height
            ),
            "Não",
            self._on_no_click,
            text_color=colors.BLACK,
            font_size=button_font_size,
        )

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


class StatTab(Enum):
    """Abas disponíveis na tela de estatísticas."""

    OVERVIEW = "Visão Geral"
    LEVELS = "Níveis"
    HISTORY = "Histórico"
    ACHIEVEMENTS = "Conquistas"


class TabButton:
    """Botão de aba."""

    def __init__(self, x: int, y: int, width: int, height: int, tab: StatTab):
        self.rect = pygame.Rect(x, y, width, height)
        self.tab = tab
        self.font = get_font(20)
        self.text_surf = self.font.render(tab.value, True, colors.WHITE)
        self.text_rect = self.text_surf.get_rect(center=self.rect.center)
        self.active = False
        self.hovered = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Retorna True se foi clicado."""
        if event.type == pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos):
            return True
        return False

    def update(self) -> None:
        self.hovered = self.rect.collidepoint(pygame.mouse.get_pos())

    def render(self, surface: pygame.Surface) -> None:
        # Cor baseada no estado
        if self.active:
            bg_color = colors.DARK_GRAY
            border_color = colors.YELLOW
            text_color = colors.YELLOW
        elif self.hovered:
            bg_color = (60, 60, 60)
            border_color = colors.WHITE
            text_color = colors.WHITE
        else:
            bg_color = (40, 40, 40)
            border_color = colors.GRAY
            text_color = colors.GRAY

        # Desenhar fundo
        pygame.draw.rect(
            surface,
            bg_color,
            self.rect,
            border_top_left_radius=8,
            border_top_right_radius=8,
        )
        pygame.draw.rect(
            surface,
            border_color,
            self.rect,
            2,
            border_top_left_radius=8,
            border_top_right_radius=8,
        )

        # Desenhar texto
        text_surf = self.font.render(self.tab.value, True, text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)


class StatisticsScene(Scene):
    """Cena de estatísticas do jogador."""

    def __init__(self, game_app: "GameApp"):
        super().__init__(game_app)
        self.profile: Optional[PlayerProfile] = None
        self.dialog: Optional[ConfirmationDialog] = None

        # Sistema de abas
        self.current_tab = StatTab.OVERVIEW
        self.tab_buttons: List[TabButton] = []
        self.content_rect = pygame.Rect(0, 0, 0, 0)  # Definido em _init_layout

        self._init_layout()

        # Botões de ação já posicionados corretamente no rodapé
        margin_bottom = 40
        button_y = Config.SCREEN_HEIGHT - margin_bottom
        self.reset_button = Button(
            pygame.Rect(Config.SCREEN_WIDTH - 230, button_y - 50, 200, 50),
            "Resetar",
            self.show_confirmation,
            text_color=colors.WHITE,
        )
        self.back_button = Button(
            pygame.Rect(30, button_y - 50, 200, 50),
            "Voltar",
            self.app.states.pop,
            text_color=colors.WHITE,
        )

    def _init_layout(self):
        """Inicializa o layout com sistema de abas."""
        margin = 30
        tab_bar_y = 100
        tab_height = 50
        tab_spacing = 10

        # Calcular largura das abas
        num_tabs = len(StatTab)
        available_width = Config.SCREEN_WIDTH - 2 * margin
        tab_width = (available_width - (num_tabs - 1) * tab_spacing) // num_tabs

        # Criar botões de aba
        for i, tab in enumerate(StatTab):
            x = margin + i * (tab_width + tab_spacing)
            tab_button = TabButton(x, tab_bar_y, tab_width, tab_height, tab)
            self.tab_buttons.append(tab_button)

        # Definir primeiro como ativo
        if self.tab_buttons:
            self.tab_buttons[0].active = True

        # Área de conteúdo (abaixo das abas)
        content_y = tab_bar_y + tab_height
        content_height = Config.SCREEN_HEIGHT - content_y - 100
        self.content_rect = pygame.Rect(
            margin, content_y, Config.SCREEN_WIDTH - 2 * margin, content_height
        )

    def _switch_tab(self, new_tab: StatTab) -> None:
        """Muda para uma nova aba."""
        self.current_tab = new_tab

        # Atualizar estado ativo dos botões
        for tab_button in self.tab_buttons:
            tab_button.active = tab_button.tab == new_tab

    def enter(self) -> None:
        super().enter()
        self.load_profile()

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

            # Atualizar botões de aba
            for tab_button in self.tab_buttons:
                tab_button.update()

        if self.profile:
            self.profile.auto_save()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.dialog:
            self.dialog.handle_event(event)
            return

        # Verificar cliques nas abas
        for tab_button in self.tab_buttons:
            if tab_button.handle_event(event):
                self._switch_tab(tab_button.tab)
                return

        self.reset_button.handle_event(event)
        self.back_button.handle_event(event)

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

        # Renderizar abas
        for tab_button in self.tab_buttons:
            tab_button.render(surface)

        # Renderizar conteúdo da aba atual
        self._render_tab_content(surface)

        # Renderizar botões de ação
        self.reset_button.render(surface, colors.RED, colors.BRIGHT_RED)
        self.back_button.render(surface, colors.GRAY, colors.BRIGHT_GRAY)

        # Renderizar diálogo de confirmação por último
        if self.dialog:
            self.dialog.render(surface)

    def _render_tab_content(self, surface: pygame.Surface) -> None:
        """Renderiza o conteúdo da aba atual."""
        # Desenhar fundo da área de conteúdo
        pygame.draw.rect(
            surface,
            colors.DARK_GRAY,
            self.content_rect,
            border_bottom_left_radius=12,
            border_bottom_right_radius=12,
        )
        pygame.draw.rect(
            surface,
            colors.GRAY,
            self.content_rect,
            2,
            border_bottom_left_radius=12,
            border_bottom_right_radius=12,
        )

        # Definir clipping para não desenhar fora da área
        content_area_clone = self.content_rect.copy()
        content_area_clone.inflate_ip(-20, -20)
        surface.set_clip(content_area_clone)

        if self.current_tab == StatTab.OVERVIEW:
            self._render_overview_tab(surface)
        elif self.current_tab == StatTab.LEVELS:
            self._render_levels_tab(surface)
        elif self.current_tab == StatTab.HISTORY:
            self._render_history_tab(surface)
        elif self.current_tab == StatTab.ACHIEVEMENTS:
            self._render_achievements_tab(surface)

        # Limpar clipping
        surface.set_clip(None)

    def _render_overview_tab(self, surface: pygame.Surface) -> None:
        """Renderiza aba de visão geral."""
        if not self.profile:
            return

        summary = self.profile.get_statistics_summary()
        font_text = get_font(20)
        badge_font = get_font(28)

        x = self.content_rect.x + 30
        y = self.content_rect.y + 30

        # Skill Level Badge
        ProfileVisualizer.render_skill_badge(
            surface, summary["skill_level"], x, y, badge_font
        )

        # Estatísticas principais
        stats_y = y
        stats_x = x + 250
        stats = [
            f"Nível Mais Alto: {summary['highest_level']}",
            f"Tempo Total: {summary['total_playtime_hours']:.1f}h",
            f"Mortes: {self.profile.total_deaths}",
            f"Pontuação Total: {self.profile.total_score:,}",
            f"Taxa de Sucesso: {summary['avg_clear_rate']:.0%}",
        ]

        for stat in stats:
            text_surf = font_text.render(stat, True, colors.WHITE)
            surface.blit(text_surf, (stats_x, stats_y))
            stats_y += 35

        # Gráfico
        graph_y = self.content_rect.y + 200
        graph_rect = pygame.Rect(
            x,
            graph_y,
            self.content_rect.width - 60,
            self.content_rect.height - (graph_y - self.content_rect.y) - 20,
        )
        graph_font = get_font(14)
        ProfileVisualizer.render_performance_graph(
            surface,
            self.profile,
            graph_rect.x,
            graph_rect.y,
            graph_rect.width,
            graph_rect.height,
            graph_font,
        )

    def _render_levels_tab(self, surface: pygame.Surface) -> None:
        """Renderiza aba de níveis."""
        if not self.profile:
            return

        font = get_font(18)
        x = self.content_rect.x + 20
        y = self.content_rect.y + 20

        # Listar níveis jogados
        sorted_levels = sorted(self.profile.level_stats.keys())
        if not sorted_levels:
            text_surf = font.render("Nenhum nível jogado ainda.", True, colors.GRAY)
            surface.blit(text_surf, (x, y))
            return

        for level_num in sorted_levels:
            stats = self.profile.level_stats[level_num]

            text = f"Nível {level_num}: {stats.attempts} tentativas, {stats.clear_rate:.0%} sucesso"
            text_surf = font.render(text, True, colors.WHITE)
            surface.blit(text_surf, (x, y))
            y += 30

            if y > self.content_rect.bottom - 40:
                text_surf = font.render("...", True, colors.GRAY)
                surface.blit(text_surf, (x, y))
                break

    def _render_history_tab(self, surface: pygame.Surface) -> None:
        """Renderiza aba de histórico."""
        if not self.profile:
            return

        font_title = get_font(22)
        font_text = get_font(16)

        x = self.content_rect.x + 20
        y = self.content_rect.y + 20

        title = font_title.render("Últimas Sessões", True, colors.YELLOW)
        surface.blit(title, (x, y))
        y += 40

        if not self.profile.session_history:
            text_surf = font_text.render("Nenhuma sessão gravada.", True, colors.GRAY)
            surface.blit(text_surf, (x, y))
            return

        # Mostrar últimas 10 sessões
        for session in reversed(self.profile.session_history[-10:]):
            duration_mins = session.duration / 60
            text = f"Duração: {duration_mins:.1f}min | Mortes: {session.deaths} | Score: {session.score}"
            text_surf = font_text.render(text, True, colors.WHITE)
            surface.blit(text_surf, (x, y))
            y += 28

            if y > self.content_rect.bottom - 40:
                text_surf = font_text.render("...", True, colors.GRAY)
                surface.blit(text_surf, (x, y))
                break

    def _render_achievements_tab(self, surface: pygame.Surface) -> None:
        """Renderiza aba de conquistas."""
        font_title = get_font(22)
        font_text = get_font(18)

        x = self.content_rect.x + 20
        y = self.content_rect.y + 20

        title = font_title.render("Conquistas (Em breve!)", True, colors.YELLOW)
        surface.blit(title, (x, y))
        y += 50

        text = font_text.render(
            "Sistema de conquistas será implementado em breve.", True, colors.GRAY
        )
        surface.blit(text, (x, y))

    def show_confirmation(self) -> None:
        self.dialog = ConfirmationDialog(
            [
                "Tem certeza que deseja",
                "resetar seu perfil?",
                "Todo o progresso será perdido.",
            ],
            self.reset_profile,
            self.close_confirmation,
        )

    def close_confirmation(self) -> None:
        self.dialog = None

    def reset_profile(self) -> None:
        if self.profile:
            self.profile.reset()
            self.load_profile()
        self.close_confirmation()
