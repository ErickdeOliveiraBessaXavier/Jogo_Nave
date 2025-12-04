from typing import Optional, TYPE_CHECKING, Callable, List, Dict, Any
from enum import Enum
import pygame

if TYPE_CHECKING:
    from ..app import GameApp

from ..core import colors
from ..core.assets import get_font
from ..render.renderer import Renderer
from ..core.meta_progression import PlayerProfile, PerformanceState
from ..core.state import Scene


class StatTab(Enum):
    """Abas disponíveis na tela de estatísticas."""

    OVERVIEW = "Visão Geral"
    LEVELS = "Níveis"
    # HISTORY = "Histórico" # Desativado por enquanto para simplificar


class StatisticsScene(Scene):
    """Cena de estatísticas do jogador com design renovado."""

    def __init__(self, game_app: "GameApp"):
        super().__init__(game_app)
        self.profile: Optional[PlayerProfile] = None
        self.dialog: Optional[ConfirmationDialog] = None
        self.r = Renderer()

        # Fonts
        self.title_font = get_font(40)
        self.header_font = get_font(24)
        self.item_font = get_font(20)
        self.small_font = get_font(16)

        # Sistema de abas
        self.current_tab = StatTab.OVERVIEW
        self.layout_rects: Dict[str, Any] = {}
        self._calculate_layout()

    def _calculate_layout(self):
        screen_w, screen_h = self.app.screen.get_size()
        pad = 20
        top_offset = 100

        # Abas
        tab_buttons: List[pygame.Rect] = []
        num_tabs = len(StatTab)
        tab_w = (screen_w - (num_tabs + 1) * pad) / num_tabs
        tab_h = 50
        for i, _ in enumerate(StatTab):
            rect = pygame.Rect(pad + i * (tab_w + pad), top_offset, tab_w, tab_h)
            tab_buttons.append(rect)
        self.layout_rects["tab_buttons"] = tab_buttons

        # Área de Conteúdo
        content_y = top_offset + tab_h
        self.layout_rects["content_area"] = pygame.Rect(
            pad, content_y, screen_w - 2 * pad, screen_h - content_y - pad - 80
        )

        # Botões de Ação
        self.layout_rects["back_button"] = pygame.Rect(pad, screen_h - 60, 150, 40)
        self.layout_rects["reset_button"] = pygame.Rect(
            screen_w - pad - 150, screen_h - 60, 150, 40
        )

    def _switch_tab(self, new_tab: StatTab):
        if self.current_tab != new_tab:
            self.current_tab = new_tab

    def enter(self):
        from pathlib import Path

        super().enter()
        self.profile = PlayerProfile(Path("player_profile.json"))
        pygame.mouse.set_visible(True)

    def exit(self):
        if self.profile:
            self.profile.save()

    def update(self, dt: float):
        # Atualiza fundo animado
        self.r.starfield.update(dt)

        if self.dialog:
            self.dialog.update()
        if self.profile:
            self.profile.auto_save()

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.dialog:
                self.close_confirmation()
            else:
                self._return_to_menu()
            return

        if self.dialog:
            self.dialog.handle_event(event)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self.layout_rects["back_button"].collidepoint(pos):
                self._return_to_menu()
            elif self.layout_rects["reset_button"].collidepoint(pos):
                self.show_confirmation()
            else:
                for i, rect in enumerate(self.layout_rects["tab_buttons"]):
                    if rect.collidepoint(pos):
                        self._switch_tab(list(StatTab)[i])
                        break

    def _return_to_menu(self):
        """Retorna ao menu principal de forma segura."""
        from .main_menu import MainMenuScene
        # Usar switch para substituir toda a pilha pelo menu
        self.app.states.switch(MainMenuScene(self.app))

    def render(self, surface: pygame.Surface):
        surface.fill(colors.BLACK)
        # Fundo com mesma lógica das outras cenas
        self.r.starfield.draw(surface)

        # Título
        title_surf = self.title_font.render("Estatísticas", True, colors.WHITE)
        surface.blit(title_surf, (20, 20))

        if not self.profile:
            # Tratamento se o perfil não carregar
            error_text = self.header_font.render(
                "Perfil não encontrado.", True, colors.RED
            )
            surface.blit(
                error_text,
                (
                    surface.get_width() / 2 - error_text.get_width() / 2,
                    surface.get_height() / 2 - error_text.get_height() / 2,
                ),
            )
            return

        # Renderizar Abas e Conteúdo
        self._draw_tabs(surface)
        self._draw_tab_content(surface)

        # Botões de Ação
        self._draw_button(
            surface, self.layout_rects["back_button"], "Voltar", colors.GRAY
        )
        self._draw_button(
            surface, self.layout_rects["reset_button"], "Resetar", colors.RED
        )

        if self.dialog:
            self.dialog.render(surface)

    def _draw_button(
        self, surface: pygame.Surface, rect: pygame.Rect, text: str, color: colors.Color
    ):
        is_hovered = rect.collidepoint(pygame.mouse.get_pos())
        bg_color = tuple(min(c + 20, 255) for c in color) if is_hovered else color
        pygame.draw.rect(surface, bg_color, rect, border_radius=8)
        pygame.draw.rect(surface, colors.WHITE, rect, 2, border_radius=8)
        text_surf = self.item_font.render(text, True, colors.WHITE)
        surface.blit(
            text_surf,
            (
                rect.centerx - text_surf.get_width() / 2,
                rect.centery - text_surf.get_height() / 2,
            ),
        )

    def _draw_tabs(self, surface: pygame.Surface):
        for i, tab in enumerate(StatTab):
            rect = self.layout_rects["tab_buttons"][i]
            is_active = self.current_tab == tab
            is_hovered = rect.collidepoint(pygame.mouse.get_pos())

            border_color = colors.GRAY
            if is_active:
                border_color = colors.BLUE
            elif is_hovered:
                border_color = colors.WHITE

            # Remove background fill for a cleaner look
            # pygame.draw.rect(surface, bg_color, rect, ...)

            pygame.draw.rect(
                surface,
                border_color,
                rect,
                2,
                border_top_left_radius=8,
                border_top_right_radius=8,
            )

            text_color = colors.WHITE if is_active or is_hovered else colors.GRAY
            text_surf = self.item_font.render(tab.value, True, text_color)
            surface.blit(
                text_surf,
                (
                    rect.centerx - text_surf.get_width() / 2,
                    rect.centery - text_surf.get_height() / 2,
                ),
            )

    def _draw_tab_content(self, surface: pygame.Surface):
        content_rect = self.layout_rects["content_area"]
        # Apenas a borda, sem fundo
        pygame.draw.rect(surface, colors.GRAY, content_rect, 1, border_radius=8)

        # Clipping para garantir que o conteúdo não saia da área
        clip_area = content_rect.inflate(-20, -20)
        surface.set_clip(clip_area)

        if self.current_tab == StatTab.OVERVIEW:
            self._render_overview_tab(surface, clip_area)
        elif self.current_tab == StatTab.LEVELS:
            self._render_levels_tab(surface, clip_area)

        surface.set_clip(None)

    def _render_overview_tab(self, surface: pygame.Surface, area: pygame.Rect):
        if not self.profile:
            return
        summary = self.profile.get_statistics_summary()
        y = area.y + 10

        # Card: Resumo (aumentado para acomodar mais estatísticas)
        card_rect = pygame.Rect(area.x, y, area.width, 220)
        self._draw_card_background(surface, card_rect)

        # Título do Card - em azul para destaque
        header = self.header_font.render("Resumo do Piloto", True, colors.BLUE)
        surface.blit(header, (card_rect.x + 15, card_rect.y + 10))

        # Conteúdo do card - labels em cinza, valores em azul
        stats_y = card_rect.y + 50
        stats_data = [
            ("Nível Mais Alto:", f"{summary['highest_level']}"),
            ("Tempo Total de Jogo:", f"{summary['total_playtime_hours']:.1f}h"),
            ("Mortes Totais:", f"{self.profile.total_deaths}"),
            ("Pontuação Total:", f"{self.profile.total_score:,}"),
            ("Taxa de Sucesso Média:", f"{summary['avg_clear_rate']:.0%}"),
            ("Estrelas Coletadas:", f"{self.profile.stars_collected}"),
            ("Estrelas Gastas:", f"{self.profile.stars_spent}"),
            ("Estrelas Disponíveis:", f"{self.profile.available_stars}"),
            ("Slots Desbloqueados:", f"{self.profile.unlocked_slots}/9"),
        ]
        for i, (label, value) in enumerate(stats_data):
            col = i % 2
            row = i // 2
            x_pos = card_rect.x + 20 + col * (area.width / 2)
            y_pos = stats_y + row * 35
            
            # Label em cinza
            label_surf = self.item_font.render(label, True, colors.GRAY)
            surface.blit(label_surf, (x_pos, y_pos))
            
            # Valor em azul ao lado do label
            value_surf = self.item_font.render(f" {value}", True, colors.BLUE)
            surface.blit(value_surf, (x_pos + label_surf.get_width(), y_pos))

        # Card: Recomendações
        recom_y = card_rect.bottom + 20
        recom_rect = pygame.Rect(area.x, recom_y, area.width, area.bottom - recom_y)
        self._draw_card_background(surface, recom_rect)

        header = self.header_font.render("Recomendações", True, colors.BLUE)
        surface.blit(header, (recom_rect.x + 15, recom_rect.y + 10))

        recom_y_inner = recom_rect.y + 50
        if summary["recommendations"]:
            for recom in summary["recommendations"]:
                recom_surf = self.small_font.render(f"• {recom}", True, colors.GRAY)
                surface.blit(recom_surf, (recom_rect.x + 20, recom_y_inner))
                recom_y_inner += 25
        else:
            recom_surf = self.small_font.render(
                "Nenhuma recomendação no momento. Continue jogando!", True, colors.GRAY
            )
            surface.blit(recom_surf, (recom_rect.x + 20, recom_y_inner))

    def _render_levels_tab(self, surface: pygame.Surface, area: pygame.Rect):
        if not self.profile:
            return

        header = self.header_font.render("Performance por Nível", True, colors.BLUE)
        surface.blit(header, (area.x, area.y))

        y = area.y + 50
        if not self.profile.level_stats:
            text = self.item_font.render(
                "Nenhum nível jogado ainda.", True, colors.GRAY
            )
            surface.blit(text, (area.x, y))
            return

        sorted_levels = sorted(self.profile.level_stats.keys())
        for level_num in sorted_levels:
            if y > area.bottom - 40:
                text = self.small_font.render("...", True, colors.GRAY)
                surface.blit(text, (area.x, y))
                break

            stats = self.profile.level_stats[level_num]
            # Calculate card height based on content (each line is ~25px)
            num_lines = 3  # Nível, Tentativas, Sucesso
            if stats.best_time:
                num_lines += 2  # Melhor tempo, Melhor pontuação
            card_height = 20 + (num_lines * 25) + 10  # padding top + lines + padding bottom
            card_rect = pygame.Rect(area.x, y, area.width, card_height)
            self._draw_card_background(surface, card_rect)

            # Cor baseada na performance
            state = stats.get_performance_state()
            state_colors = {
                PerformanceState.STRUGGLING: colors.RED,
                PerformanceState.LEARNING: colors.YELLOW,
                PerformanceState.COMFORTABLE: colors.GREEN,
                PerformanceState.DOMINATING: colors.BLUE,
                PerformanceState.INCONSISTENT: colors.ORANGE,
            }
            bar_color = state_colors.get(state, colors.GRAY)
            pygame.draw.rect(
                surface,
                bar_color,
                (card_rect.x, card_rect.y, 10, card_rect.height),
                border_radius=8,
            )

            # Cada informação em sua própria linha
            line_y = card_rect.y + 15
            line_spacing = 25
            
            # Linha 1: Nível
            level_label = self.item_font.render("Nível", True, colors.GRAY)
            level_value = self.item_font.render(str(level_num), True, colors.BLUE)
            surface.blit(level_label, (card_rect.x + 25, line_y))
            surface.blit(level_value, (card_rect.x + 25 + level_label.get_width() + 5, line_y))
            line_y += line_spacing + 10  # Extra margin before line 2

            # Linha 2: Tentativas
            attempts_label = self.small_font.render("Tentativas:", True, colors.GRAY)
            attempts_value = self.small_font.render(str(stats.attempts), True, colors.BLUE)
            surface.blit(attempts_label, (card_rect.x + 25, line_y))
            surface.blit(attempts_value, (card_rect.x + 25 + attempts_label.get_width() + 5, line_y))
            line_y += line_spacing
            
            # Linha 3: Sucesso
            success_label = self.small_font.render("Sucesso:", True, colors.GRAY)
            success_value = self.small_font.render(f"{stats.clear_rate:.0%}", True, colors.BLUE)
            surface.blit(success_label, (card_rect.x + 25, line_y))
            surface.blit(success_value, (card_rect.x + 25 + success_label.get_width() + 5, line_y))
            line_y += line_spacing

            if stats.best_time:
                # Linha 4: Melhor tempo
                time_label = self.small_font.render("Melhor tempo:", True, colors.GRAY)
                time_value = self.small_font.render(f"{stats.best_time:.1f}s", True, colors.BLUE)
                surface.blit(time_label, (card_rect.x + 25, line_y))
                surface.blit(time_value, (card_rect.x + 25 + time_label.get_width() + 5, line_y))
                line_y += line_spacing
                
                # Linha 5: Melhor pontuação
                score_label = self.small_font.render("Melhor pontuação:", True, colors.GRAY)
                score_value = self.small_font.render(f"{stats.best_score:,}", True, colors.BLUE)
                surface.blit(score_label, (card_rect.x + 25, line_y))
                surface.blit(score_value, (card_rect.x + 25 + score_label.get_width() + 5, line_y))

            y += card_rect.height + 15

    def _draw_card_background(self, surface: pygame.Surface, rect: pygame.Rect):
        # Apenas a borda, sem fundo, para consistência com settings.py
        pygame.draw.rect(surface, colors.GRAY, rect, 1, border_radius=8)

    def show_confirmation(self):
        self.dialog = ConfirmationDialog(
            ["Tem certeza?", "Todo o progresso", "será perdido."],
            self.reset_profile,
            self.close_confirmation,
        )

    def close_confirmation(self):
        self.dialog = None

    def reset_profile(self):
        if self.profile:
            self.profile.reset()
        self.close_confirmation()


class ConfirmationDialog:
    """Um diálogo de confirmação com o novo estilo."""

    def __init__(
        self,
        question_lines: List[str],
        on_yes: Callable[[], None],
        on_no: Callable[[], None],
    ):
        self.on_yes = on_yes
        self.on_no = on_no
        self.header_font = get_font(24)
        self.item_font = get_font(20)

        # Box
        box_w, box_h = 450, 200
        screen_w, screen_h = pygame.display.get_surface().get_size()
        self.box_rect = pygame.Rect(
            screen_w / 2 - box_w / 2, screen_h / 2 - box_h / 2, box_w, box_h
        )

        # Texto
        self.lines = [
            self.header_font.render(line, True, colors.WHITE) for line in question_lines
        ]
        self.line_rects: List[pygame.Rect] = []
        y_offset = self.box_rect.y + 30
        for line in self.lines:
            rect = line.get_rect(centerx=self.box_rect.centerx, top=y_offset)
            self.line_rects.append(rect)
            y_offset += line.get_height() + 10

        # Botões
        btn_w, btn_h = 150, 40
        btn_y = self.box_rect.bottom - btn_h - 20
        self.yes_rect = pygame.Rect(
            self.box_rect.centerx - btn_w - 10, btn_y, btn_w, btn_h
        )
        self.no_rect = pygame.Rect(self.box_rect.centerx + 10, btn_y, btn_w, btn_h)

        # Overlay
        self.overlay = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        self.overlay.fill((0, 0, 0, 180))

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.yes_rect.collidepoint(event.pos):
                self.on_yes()
            elif self.no_rect.collidepoint(event.pos):
                self.on_no()

    def update(self):
        pass  # Hover é tratado no render

    def render(self, surface: pygame.Surface):
        surface.blit(self.overlay, (0, 0))
        # Caixa
        pygame.draw.rect(surface, colors.DARK_GRAY, self.box_rect, border_radius=12)
        pygame.draw.rect(surface, colors.WHITE, self.box_rect, 2, border_radius=12)

        # Texto
        for line, rect in zip(self.lines, self.line_rects):
            surface.blit(line, rect)

        # Botões
        self._draw_button(surface, self.yes_rect, "Sim", colors.GREEN)
        self._draw_button(surface, self.no_rect, "Não", colors.RED)

    def _draw_button(
        self, surface: pygame.Surface, rect: pygame.Rect, text: str, color: colors.Color
    ):
        is_hovered = rect.collidepoint(pygame.mouse.get_pos())
        bg_color = tuple(min(c + 20, 255) for c in color) if is_hovered else color
        pygame.draw.rect(surface, bg_color, rect, border_radius=8)
        pygame.draw.rect(surface, colors.WHITE, rect, 1, border_radius=8)
        text_surf = self.item_font.render(text, True, colors.WHITE)
        surface.blit(
            text_surf,
            (
                rect.centerx - text_surf.get_width() / 2,
                rect.centery - text_surf.get_height() / 2,
            ),
        )
