import math
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

import pygame

from ..core import colors
from ..core.assets import get_font
from ..core.colors import BLACK, CUSTOM_GOLD, CUSTOM_PURPLE
from ..core.difficulty import DifficultyPreset
from ..core.meta_progression import (
    PerformanceState,
    PlayerProfile,
    WorldUnlockStatus,
)
from ..core.paths import get_profile_path
from ..core.state import Scene
from .ui_helpers import draw_bordered_button, render_with_fade

if TYPE_CHECKING:
    from ..app import GameApp


class StatTab(Enum):
    """Abas disponíveis na tela de estatísticas."""

    OVERVIEW = "Visão Geral"
    LEVELS = "Níveis"
    HIGH_SCORES = "Recordes"
    # HISTORY = "Histórico" # Desativado por enquanto para simplificar


_DIFFICULTY_DISPLAY_NAMES: Dict[Optional[DifficultyPreset], str] = {
    None: "Todas",
    DifficultyPreset.CASUAL: "Casual",
    DifficultyPreset.NORMAL: "Normal",
    DifficultyPreset.HARDCORE: "Hardcore",
    DifficultyPreset.NIGHTMARE: "Pesadelo",
}

_DIFFICULTY_TAG_COLORS: Dict[str, colors.Color] = {
    "casual": colors.LIGHT_BLUE,
    "normal": colors.WHITE,
    "hardcore": colors.ORANGE,
    "nightmare": colors.RED,
}


class StatisticsView:
    """View de estatísticas do jogador (pode ser usada dentro de outras cenas)."""

    def __init__(
        self, on_back: Callable[[], None], renderer: Any = None, app: Any = None
    ):
        """
        Args:
            on_back: Callback chamado quando o usuário quer voltar
            renderer: Renderer compartilhado (opcional)
        """
        self.on_back = on_back
        self.renderer = renderer
        self._app = app
        self.profile: PlayerProfile | None = None
        self.dialog: ConfirmationDialog | None = None

        # Fonts
        self.title_font = get_font(40)
        self.header_font = get_font(24)
        self.item_font = get_font(20)
        self.small_font = get_font(16)

        # Sistema de abas
        self.current_tab = StatTab.OVERVIEW
        self.layout_rects: Dict[str, Any] = {}
        self.scroll_y = 0  # Para rolagem na aba de níveis

        # Filtro da aba Recordes (None = "Todas")
        self.selected_difficulty_filter: Optional[DifficultyPreset] = None
        # Rects dos botões de filtro são calculados em _render_high_scores_tab
        self._difficulty_filter_rects: List[tuple[Optional[DifficultyPreset], pygame.Rect]] = []

        # Animação de entrada
        self.entry_progress = 0.0
        self.is_entering = True
        self.entry_duration = 0.4

        self._calculate_layout()

    def _calculate_layout(self):
        from ..core.config import config as Config

        screen_w, screen_h = Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT

        # Dimensões e espaçamentos consistentes com settings.py
        outer_pad = 40
        top_offset = 100

        # Largura disponível
        available_width = screen_w - (2 * outer_pad)

        # Abas
        tab_buttons: List[pygame.Rect] = []
        num_tabs = len(StatTab)
        # Tabs ocupam toda a largura disponível
        tab_w = (
            available_width - (num_tabs - 1) * 20
        ) / num_tabs  # 20px de gap entre abas
        tab_h = 50

        for i, _ in enumerate(StatTab):
            rect = pygame.Rect(outer_pad + i * (tab_w + 20), top_offset, tab_w, tab_h)
            tab_buttons.append(rect)
        self.layout_rects["tab_buttons"] = tab_buttons

        # Área de Conteúdo
        content_y = top_offset + tab_h + 20  # +20 gap
        self.layout_rects["content_area"] = pygame.Rect(
            outer_pad, content_y, available_width, screen_h - content_y - outer_pad - 60
        )

        # Botões de Ação
        btn_w = 160
        btn_h = 40

        self.layout_rects["back_button"] = pygame.Rect(
            outer_pad, screen_h - 60, btn_w, btn_h
        )
        self.layout_rects["reset_button"] = pygame.Rect(
            screen_w - outer_pad - btn_w, screen_h - 60, btn_w, btn_h
        )

    def _switch_tab(self, new_tab: StatTab):
        if self.current_tab != new_tab:
            self.current_tab = new_tab
            self.scroll_y = 0  # Reset scroll on tab switch

    def reset(self):
        """Reseta o estado da view para reiniciar animação."""
        self.entry_progress = 0.0
        self.is_entering = True
        if self._app and hasattr(self._app, "player_profile"):
            self.profile = self._app.player_profile
        else:
            self.profile = PlayerProfile(get_profile_path())
        self.dialog = None
        self.scroll_y = 0

    def update(self, dt: float):
        """Atualiza a lógica da view."""
        if self.is_entering and self.entry_progress < 1.0:
            self.entry_progress = min(
                1.0, self.entry_progress + dt / self.entry_duration
            )
            if self.entry_progress >= 1.0:
                self.is_entering = False

        if self.dialog:
            self.dialog.update()
        if self.profile:
            self.profile.auto_save()

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Processa eventos da view."""
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.dialog:
                self.close_confirmation()
            else:
                self.on_back()
            return True

        if self.dialog:
            self.dialog.handle_event(event)
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self.layout_rects["back_button"].collidepoint(pos):
                self.on_back()
                return True
            elif self.layout_rects["reset_button"].collidepoint(pos):
                self.show_confirmation()
                return True
            else:
                for i, rect in enumerate(self.layout_rects["tab_buttons"]):
                    if rect.collidepoint(pos):
                        self._switch_tab(list(StatTab)[i])
                        return True
                if self.current_tab == StatTab.HIGH_SCORES:
                    for diff, rect in self._difficulty_filter_rects:
                        if rect.collidepoint(pos):
                            if self.selected_difficulty_filter != diff:
                                self.selected_difficulty_filter = diff
                                self.scroll_y = 0
                            return True

        if event.type == pygame.MOUSEWHEEL:
            if self.current_tab in [
                StatTab.LEVELS,
                StatTab.OVERVIEW,
                StatTab.HIGH_SCORES,
            ]:
                self.scroll_y -= event.y * 20  # Ajusta a velocidade de rolagem
                return True

        return False

    def render(self, surface: pygame.Surface):
        """Renderiza a view."""
        # Calcular alpha baseado no progresso
        alpha = int(255 * self.entry_progress)
        offset_y = int(30 * (1.0 - self.entry_progress))

        # Título
        title_surf = self.title_font.render("Estatísticas", True, CUSTOM_GOLD)
        title_surf.set_alpha(alpha)
        # Centralizar título
        title_x = (surface.get_width() - title_surf.get_width()) // 2
        surface.blit(title_surf, (title_x, 20 + offset_y))

        if not self.profile:
            # Tratamento se o perfil não carregar
            error_text = self.header_font.render(
                "Perfil não encontrado.", True, colors.RED
            )
            error_text.set_alpha(alpha)
            surface.blit(
                error_text,
                (
                    surface.get_width() / 2 - error_text.get_width() / 2,
                    surface.get_height() / 2 - error_text.get_height() / 2 + offset_y,
                ),
            )
            return

        # Renderizar Abas e Conteúdo com alpha
        self._draw_tabs(surface, alpha, offset_y)
        self._draw_tab_content(surface, alpha, offset_y)

        # Botões de Ação com alpha
        self._draw_button(
            surface,
            self.layout_rects["back_button"],
            "Voltar",
            CUSTOM_PURPLE,
            alpha,
            offset_y,
        )
        self._draw_button(
            surface,
            self.layout_rects["reset_button"],
            "Resetar",
            colors.RED,
            alpha,
            offset_y,
        )

        if self.dialog:
            self.dialog.render(surface)

    def _draw_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        text: str,
        color: colors.Color,
        alpha: int = 255,
        offset_y: int = 0,
    ):
        draw_bordered_button(
            surface, rect, text, self.item_font, color, alpha, offset_y
        )

    def _draw_tabs(self, surface: pygame.Surface, alpha: int = 255, offset_y: int = 0):
        for i, tab in enumerate(StatTab):
            rect = self.layout_rects["tab_buttons"][i].copy()
            rect.y += offset_y

            is_active = self.current_tab == tab
            is_hovered = rect.collidepoint(pygame.mouse.get_pos())

            border_color = CUSTOM_PURPLE if (is_active or is_hovered) else colors.GRAY
            text_color = (
                CUSTOM_GOLD
                if is_active
                else (CUSTOM_GOLD if is_hovered else colors.GRAY)
            )

            # Criar surface temporária para aplicar alpha
            temp_surface = pygame.Surface(
                (rect.width + 4, rect.height + 4), pygame.SRCALPHA
            )
            temp_rect = pygame.Rect(2, 2, rect.width, rect.height)
            pygame.draw.rect(
                temp_surface,
                (*border_color, alpha),
                temp_rect,
                2,
                border_top_left_radius=8,
                border_top_right_radius=8,
            )
            surface.blit(temp_surface, (rect.x - 2, rect.y - 2))

            text_surf = self.item_font.render(tab.value, True, text_color)
            text_surf.set_alpha(alpha)
            surface.blit(
                text_surf,
                (
                    rect.centerx - text_surf.get_width() / 2,
                    rect.centery - text_surf.get_height() / 2,
                ),
            )

    def _draw_tab_content(
        self, surface: pygame.Surface, alpha: int = 255, offset_y: int = 0
    ):
        content_rect = self.layout_rects["content_area"].copy()
        content_rect.y += offset_y

        # Apenas a borda, sem fundo
        temp_surface = pygame.Surface(
            (content_rect.width + 2, content_rect.height + 2), pygame.SRCALPHA
        )
        pygame.draw.rect(
            temp_surface,
            (*colors.GRAY, alpha),
            pygame.Rect(1, 1, content_rect.width, content_rect.height),
            1,
            border_radius=8,
        )
        surface.blit(temp_surface, (content_rect.x - 1, content_rect.y - 1))

        # Clipping para garantir que o conteúdo não saia da área
        clip_area = content_rect.inflate(-20, -20)
        surface.set_clip(clip_area)

        if self.current_tab == StatTab.OVERVIEW:
            self._render_overview_tab(surface, clip_area, alpha)
        elif self.current_tab == StatTab.LEVELS:
            self._render_levels_tab(surface, clip_area, alpha)
        elif self.current_tab == StatTab.HIGH_SCORES:
            self._render_high_scores_tab(surface, clip_area, alpha)

        surface.set_clip(None)

    def _render_overview_tab(
        self, surface: pygame.Surface, area: pygame.Rect, alpha: int = 255
    ):
        if not self.profile:
            return
        summary = self.profile.get_statistics_summary()

        indent_x = 30

        # Dados para exibição
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

        # Configuração de Layout
        cols = 2 
        col_width = (area.width - 60) / cols # Ajustado para novo indent

        # Calcular altura do Card 1
        rows = (len(stats_data) + cols - 1) // cols
        card1_height = 60 + rows * 35 + 20 

        # Calcular altura do Card 2
        num_recom = len(summary["recommendations"]) if summary["recommendations"] else 1
        card2_height = 60 + num_recom * 28 + 20

        total_height = card1_height + 20 + card2_height

        visible_height = area.height
        if total_height > visible_height:
            self.scroll_y = max(0, min(self.scroll_y, total_height - visible_height))
        else:
            self.scroll_y = 0

        content_surface = pygame.Surface(
            (area.width, max(total_height, visible_height)), pygame.SRCALPHA
        )

        current_y = 0

        # --- Card 1: Resumo ---
        card_rect = pygame.Rect(0, current_y, area.width, card1_height)
        self._draw_card_background(content_surface, card_rect, alpha)

        header = self.header_font.render("Resumo do Piloto", True, CUSTOM_GOLD)
        header.set_alpha(alpha)
        content_surface.blit(header, (card_rect.x + indent_x, card_rect.y + 15))

        stats_y = card_rect.y + 60

        for i, (label, value) in enumerate(stats_data):
            col = i % cols
            row = i // cols
            x_pos = card_rect.x + indent_x + col * col_width
            y_pos = stats_y + row * 35

            label_surf = self.item_font.render(label, True, colors.GRAY)
            label_surf.set_alpha(alpha)
            content_surface.blit(label_surf, (x_pos, y_pos))

            value_surf = self.item_font.render(f" {value}", True, CUSTOM_PURPLE)
            value_surf.set_alpha(alpha)
            content_surface.blit(value_surf, (x_pos + label_surf.get_width(), y_pos))

        current_y += card1_height + 20

        # --- Card 2: Recomendações ---
        recom_rect = pygame.Rect(0, current_y, area.width, card2_height)
        self._draw_card_background(content_surface, recom_rect, alpha)

        header = self.header_font.render("Recomendações", True, CUSTOM_GOLD)
        header.set_alpha(alpha)
        content_surface.blit(header, (recom_rect.x + indent_x, recom_rect.y + 15))

        recom_y_inner = recom_rect.y + 60
        if summary["recommendations"]:
            for recom in summary["recommendations"]:
                recom_surf = self.small_font.render(f"• {recom}", True, colors.GRAY)
                recom_surf.set_alpha(alpha)
                content_surface.blit(recom_surf, (recom_rect.x + indent_x + 5, recom_y_inner))
                recom_y_inner += 28
        else:
            recom_surf = self.small_font.render(
                "Nenhuma recomendação no momento. Continue jogando!", True, colors.GRAY
            )
            recom_surf.set_alpha(alpha)
            content_surface.blit(recom_surf, (recom_rect.x + indent_x + 5, recom_y_inner))

        content_surface.set_alpha(alpha)
        surface.blit(
            content_surface,
            (area.x, area.y),
            area=(0, self.scroll_y, area.width, visible_height),
        )

    def _render_levels_tab(
        self, surface: pygame.Surface, area: pygame.Rect, alpha: int = 255
    ):
        if not self.profile:
            return

        indent_x = 30
        header = self.header_font.render("Performance por Nível", True, CUSTOM_GOLD)
        header.set_alpha(alpha)
        surface.blit(header, (area.x + indent_x, area.y))

        y = area.y + 50
        if not self.profile.level_stats:
            text = self.item_font.render(
                "Nenhum nível jogado ainda.", True, colors.GRAY
            )
            text.set_alpha(alpha)
            surface.blit(text, (area.x + indent_x, y))
            return

        sorted_levels = sorted(self.profile.level_stats.keys())

        total_height = 0
        for level_num in sorted_levels:
            stats = self.profile.level_stats[level_num]
            num_lines = 3 
            if stats.best_time:
                num_lines += 2 
            card_height = 20 + (num_lines * 25) + 10
            total_height += card_height + 15 

        visible_height = area.height - 50 
        if total_height > visible_height:
            self.scroll_y = max(0, min(self.scroll_y, total_height - visible_height))
        else:
            self.scroll_y = 0

        content_surface = pygame.Surface(
            (area.width, max(total_height, visible_height)), pygame.SRCALPHA
        )

        content_y = 0
        for level_num in sorted_levels:
            stats = self.profile.level_stats[level_num]
            num_lines = 3 
            if stats.best_time:
                num_lines += 2 
            card_height = 20 + (num_lines * 25) + 10
            card_rect = pygame.Rect(0, content_y, area.width, card_height)
            self._draw_card_background(content_surface, card_rect, alpha)

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
                content_surface,
                (*bar_color, alpha),
                (card_rect.x, card_rect.y, 10, card_rect.height),
                border_radius=8,
            )

            line_y = card_rect.y + 15
            line_spacing = 25

            level_label = self.item_font.render("Nível", True, colors.GRAY)
            level_label.set_alpha(alpha)
            level_value = self.item_font.render(str(level_num), True, CUSTOM_PURPLE)
            level_value.set_alpha(alpha)
            content_surface.blit(level_label, (card_rect.x + indent_x, line_y))
            content_surface.blit(
                level_value, (card_rect.x + indent_x + level_label.get_width() + 5, line_y)
            )
            line_y += line_spacing + 10 

            attempts_label = self.small_font.render("Tentativas:", True, colors.GRAY)
            attempts_label.set_alpha(alpha)
            attempts_value = self.small_font.render(
                str(stats.attempts), True, CUSTOM_PURPLE
            )
            attempts_value.set_alpha(alpha)
            content_surface.blit(attempts_label, (card_rect.x + indent_x, line_y))
            content_surface.blit(
                attempts_value,
                (card_rect.x + indent_x + attempts_label.get_width() + 5, line_y),
            )
            line_y += line_spacing

            success_label = self.small_font.render("Sucesso:", True, colors.GRAY)
            success_label.set_alpha(alpha)
            success_value = self.small_font.render(
                f"{stats.clear_rate:.0%}", True, CUSTOM_PURPLE
            )
            success_value.set_alpha(alpha)
            content_surface.blit(success_label, (card_rect.x + indent_x, line_y))
            content_surface.blit(
                success_value,
                (card_rect.x + indent_x + success_label.get_width() + 5, line_y),
            )
            line_y += line_spacing

            if stats.best_time:
                time_label = self.small_font.render("Melhor tempo:", True, colors.GRAY)
                time_label.set_alpha(alpha)
                time_value = self.small_font.render(
                    f"{stats.best_time:.1f}s", True, CUSTOM_PURPLE
                )
                time_value.set_alpha(alpha)
                content_surface.blit(time_label, (card_rect.x + indent_x, line_y))
                content_surface.blit(
                    time_value, (card_rect.x + indent_x + time_label.get_width() + 5, line_y)
                )
                line_y += line_spacing

                score_label = self.small_font.render(
                    "Melhor pontuação:", True, colors.GRAY
                )
                score_label.set_alpha(alpha)
                score_value = self.small_font.render(
                    f"{stats.best_score:,}", True, CUSTOM_PURPLE
                )
                score_value.set_alpha(alpha)
                content_surface.blit(score_label, (card_rect.x + indent_x, line_y))
                content_surface.blit(
                    score_value,
                    (card_rect.x + indent_x + score_label.get_width() + 5, line_y),
                )

            content_y += card_rect.height + 15

        # Aplicar alpha à superfície de conteúdo
        content_surface.set_alpha(alpha)

        # Blitar a parte visível da superfície de conteúdo
        surface.blit(
            content_surface,
            (area.x, area.y + 50),
            area=(0, self.scroll_y, area.width, visible_height),
        )

    def _render_high_scores_tab(
        self, surface: pygame.Surface, area: pygame.Rect, alpha: int = 255
    ):
        if not self.profile:
            return

        # Indentação padrão para alinhar com as colunas da tabela
        indent_x = 30
        
        header = self.header_font.render("HALL DA FAMA", True, CUSTOM_GOLD)
        header.set_alpha(alpha)
        surface.blit(header, (area.x + indent_x, area.y))

        # Filtros por dificuldade (Todas, Casual, Normal, Hardcore, Pesadelo)
        filters_y = area.y + 50 # Aumentado de 40 para 50 para mais respiro
        btn_h = 30
        btn_padding_x = 14
        btn_gap = 10
        cursor_x = area.x + indent_x
        self._difficulty_filter_rects = []
        filter_options: List[Optional[DifficultyPreset]] = [
            None,
            DifficultyPreset.CASUAL,
            DifficultyPreset.NORMAL,
            DifficultyPreset.HARDCORE,
            DifficultyPreset.NIGHTMARE,
        ]

        # Cores para os botões de filtro baseadas na dificuldade
        filter_colors: Dict[Optional[DifficultyPreset], colors.Color] = {
            None: colors.WHITE,
            DifficultyPreset.CASUAL: colors.LIGHT_BLUE,
            DifficultyPreset.NORMAL: colors.WHITE,
            DifficultyPreset.HARDCORE: colors.ORANGE,
            DifficultyPreset.NIGHTMARE: colors.RED,
        }

        for diff in filter_options:
            label = _DIFFICULTY_DISPLAY_NAMES[diff]
            text_w = self.small_font.size(label)[0]
            btn_w = text_w + btn_padding_x * 2
            rect = pygame.Rect(cursor_x, filters_y, btn_w, btn_h)
            self._difficulty_filter_rects.append((diff, rect))

            is_active = self.selected_difficulty_filter == diff
            is_hovered = rect.collidepoint(pygame.mouse.get_pos())

            target_color = filter_colors[diff]
            if is_active:
                bg_alpha = int(alpha * 0.3)
                bg_color = (*target_color, bg_alpha)
                border_color = CUSTOM_GOLD
                text_color = CUSTOM_GOLD
            elif is_hovered:
                bg_alpha = int(alpha * 0.15)
                bg_color = (*target_color, bg_alpha)
                border_color = CUSTOM_PURPLE
                text_color = colors.WHITE
            else:
                bg_color = (0, 0, 0, 0)
                border_color = (100, 100, 100)
                text_color = colors.LIGHT_GRAY

            if bg_color[3] > 0:
                bg_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
                pygame.draw.rect(bg_surf, bg_color, bg_surf.get_rect(), border_radius=6)
                surface.blit(bg_surf, rect.topleft)

            border_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(
                border_surf,
                (*border_color, alpha),
                border_surf.get_rect(),
                2 if is_active else 1,
                border_radius=6,
            )
            surface.blit(border_surf, rect.topleft)

            text_surf = self.small_font.render(label, True, text_color)
            text_surf.set_alpha(alpha)
            surface.blit(text_surf, text_surf.get_rect(center=rect.center))

            cursor_x += btn_w + btn_gap

        # Lista filtrada
        all_entries = self.profile.get_high_scores()
        if self.selected_difficulty_filter is not None:
            wanted = self.selected_difficulty_filter.value
            entries = [e for e in all_entries if e.difficulty == wanted]
        else:
            entries = all_entries

        list_top = filters_y + btn_h + 30 # Aumentado gap para a tabela
        list_visible_height = area.height - (list_top - area.y)

        # Frame estilo Arcade
        frame_rect = pygame.Rect(area.x, list_top - 5, area.width, list_visible_height + 5)
        frame_surf = pygame.Surface(frame_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(frame_surf, (20, 20, 30, alpha), frame_surf.get_rect(), border_radius=10)
        pygame.draw.rect(frame_surf, (*CUSTOM_PURPLE, alpha // 2), frame_surf.get_rect(), 2, border_radius=10)
        surface.blit(frame_surf, frame_rect.topleft)

        if not entries:
            empty = self.item_font.render(
                "Nenhum recorde ainda. Sobreviva, marque sua glória.",
                True,
                colors.GRAY,
            )
            empty.set_alpha(alpha)
            surface.blit(empty, (area.x + indent_x, list_top + 40))
            return

        # Layout de linha (Refinado para melhor espaçamento)
        row_h = 52
        col_rank_w = 80
        col_initials_w = 150
        col_score_w = 280
        col_level_w = 150
        col_diff_w = 220
        col_date_w = 150
        row_padding_x = indent_x

        # Cabeçalho da tabela
        header_h = 40
        header_y = list_top + 10
        header_color = CUSTOM_GOLD
        col_titles = [
            ("#", col_rank_w),
            ("PILOTO", col_initials_w),
            ("SCORE", col_score_w),
            ("NÍVEL", col_level_w),
            ("DIF.", col_diff_w),
            ("DATA", col_date_w),
        ]
        
        cx = area.x + row_padding_x
        for title, w in col_titles:
            txt = self.small_font.render(title, True, header_color)
            txt.set_alpha(alpha)
            # Centralizar título verticalmente no header_h
            txt_y = header_y + (header_h - txt.get_height()) // 2
            surface.blit(txt, (cx, txt_y))
            cx += w

        rows_top = header_y + header_h + 5
        total_height = row_h * len(entries)
        visible_rows_height = max(0, list_visible_height - (rows_top - list_top) - 10)
        if total_height > visible_rows_height:
            self.scroll_y = max(0, min(self.scroll_y, total_height - visible_rows_height))
        else:
            self.scroll_y = 0

        content_surface = pygame.Surface(
            (area.width, max(total_height, visible_rows_height)), pygame.SRCALPHA
        )

        t = pygame.time.get_ticks() / 1000.0

        for idx, entry in enumerate(entries):
            row_y = idx * row_h
            is_first = idx == 0 and self.selected_difficulty_filter is None

            # Animação para o #1 global
            row_alpha = alpha
            if is_first:
                pulse = 0.5 + 0.5 * math.sin(t * 10)
                row_color = CUSTOM_GOLD
                # Brilho de fundo para o primeiro lugar
                glow_alpha = int(40 * pulse * (alpha / 255))
                pygame.draw.rect(content_surface, (*CUSTOM_GOLD, glow_alpha), (0, row_y, area.width, row_h), border_radius=5)
            elif idx < 3:
                row_color = colors.LIGHT_GRAY
            else:
                row_color = colors.WHITE

            cx = row_padding_x

            # Rank
            rank_text = self.item_font.render(f"#{idx + 1}", True, row_color)
            rank_text.set_alpha(row_alpha)
            content_surface.blit(rank_text, (cx, row_y + (row_h - rank_text.get_height()) // 2))
            cx += col_rank_w

            # Iniciais (fonte maior estilo arcade)
            initials_text = self.header_font.render(entry.initials, True, row_color)
            initials_text.set_alpha(row_alpha)
            content_surface.blit(initials_text, (cx, row_y + (row_h - initials_text.get_height()) // 2))
            cx += col_initials_w

            # Score
            score_str = f"{entry.score:,}".replace(",", ".")
            score_text = self.item_font.render(score_str, True, CUSTOM_GOLD if is_first else CUSTOM_PURPLE)
            score_text.set_alpha(row_alpha)
            content_surface.blit(score_text, (cx, row_y + (row_h - score_text.get_height()) // 2))
            cx += col_score_w

            # Nível
            level_text = self.item_font.render(f"Lv {entry.level_reached:02d}", True, row_color)
            level_text.set_alpha(row_alpha)
            content_surface.blit(level_text, (cx, row_y + (row_h - level_text.get_height()) // 2))
            cx += col_level_w

            # Dificuldade (Badge estilizada)
            tag_color = _DIFFICULTY_TAG_COLORS.get(entry.difficulty, colors.WHITE)
            try:
                diff_preset = DifficultyPreset(entry.difficulty)
                diff_label = _DIFFICULTY_DISPLAY_NAMES[diff_preset].upper()
            except ValueError:
                diff_label = entry.difficulty.upper()

            # Desenhar fundo da badge
            badge_w = self.small_font.size(diff_label)[0] + 16
            badge_h = 26
            badge_rect = pygame.Rect(cx, row_y + (row_h - badge_h) // 2, badge_w, badge_h)
            pygame.draw.rect(content_surface, (*tag_color, int(row_alpha * 0.2)), badge_rect, border_radius=6)
            pygame.draw.rect(content_surface, (*tag_color, int(row_alpha * 0.5)), badge_rect, 1, border_radius=6)

            diff_text = self.small_font.render(diff_label, True, tag_color)
            diff_text.set_alpha(row_alpha)
            content_surface.blit(diff_text, (cx + 8, row_y + (row_h - diff_text.get_height()) // 2))
            cx += col_diff_w

            # Data
            date_text = self.small_font.render(entry.achieved_at.strftime("%d/%m/%y"), True, colors.GRAY)
            date_text.set_alpha(row_alpha)
            content_surface.blit(date_text, (cx, row_y + (row_h - date_text.get_height()) // 2))

        surface.blit(
            content_surface,
            (area.x, rows_top),
            area=(0, self.scroll_y, area.width, visible_rows_height),
        )

    def _draw_card_background(
        self, surface: pygame.Surface, rect: pygame.Rect, alpha: int = 255
    ):
        # Apenas a borda, sem fundo, para consistência com settings.py
        temp_surface = pygame.Surface(
            (rect.width + 2, rect.height + 2), pygame.SRCALPHA
        )
        pygame.draw.rect(
            temp_surface,
            (*colors.GRAY, alpha),
            pygame.Rect(1, 1, rect.width, rect.height),
            1,
            border_radius=8,
        )
        surface.blit(temp_surface, (rect.x - 1, rect.y - 1))

    def show_confirmation(self):
        self.dialog = ConfirmationDialog(
            [
                "Tem certeza?",
                "Estatísticas serão resetadas.",
                "A campanha voltará ao Mundo 1.",
            ],
            self.reset_profile,
            self.close_confirmation,
        )

    def close_confirmation(self):
        self.dialog = None

    def reset_profile(self):
        if self.profile:
            # Reset base do perfil (stats, upgrades, sessões, etc.).
            self.profile.reset()

            # Após reset, campanha retorna ao estado inicial: apenas Mundo 1.
            self.profile.world_unlocks = {
                1: WorldUnlockStatus(
                    world_id=1,
                    is_unlocked=True,
                    first_accessed_at=self.profile.profile_created,
                    checkpoint_set=True,
                )
            }
            self.profile.current_checkpoint_world = 1
            self.profile.highest_level_reached = 1
            self.profile.save()

        # Resetar preferências para os valores padrão
        from ..core.paths import get_preferences_path
        from ..core.preferences import UserPreferences

        prefs = UserPreferences(get_preferences_path())
        prefs.reset()

        # Sincronizar o estado vivo do app (volumes, input) sem precisar reiniciar
        if self._app is not None:
            self._app.preferences.reset()
            from ..core.sound import sound_manager

            sound_manager.load_config(
                self._app.preferences.music_volume,
                self._app.preferences.sfx_volume,
                self._app.preferences.shot_volume,
            )
            self._app.input.mouse_control = self._app.preferences.mouse_control
            self._app.input.auto_fire = self._app.preferences.auto_fire

        self.close_confirmation()


class StatisticsScene(Scene):
    """Cena de estatísticas do jogador (mantida para compatibilidade)."""

    def __init__(self, game_app: "GameApp"):
        super().__init__(game_app)
        self.r = game_app.renderer  # Usar renderer compartilhado
        self.view = StatisticsView(on_back=self._on_back, renderer=self.r, app=game_app)

        # Sistema de transição
        self.transitioning = False
        self.transition_progress = 0.0
        self.transition_duration = 0.3
        self.fade_out = False

    def _on_back(self):
        """Callback quando o usuário quer voltar."""
        # Iniciar transição de saída
        self.fade_out = True
        self.transitioning = True
        self.transition_progress = 0.0

    def enter(self):
        super().enter()
        self.view.reset()
        pygame.mouse.set_visible(True)

    def exit(self):
        if self.view.profile:
            self.view.profile.save()

    def update(self, dt: float):
        self.r.starfield.update(dt)

        # Atualizar transição
        if self.transitioning:
            self.transition_progress += dt / self.transition_duration

            if self.transition_progress >= 1.0:
                # Completou o fade out, voltar ao menu
                from .main_menu import MainMenuScene

                self.app.states.switch(MainMenuScene(self.app))
                return

        self.view.update(dt)

    def handle_event(self, event: pygame.event.Event):
        self.view.handle_event(event)

    def render(self, surface: pygame.Surface):
        render_with_fade(
            surface,
            self.view,
            self.r.starfield,
            self.transitioning,
            self.fade_out,
            self.transition_progress,
            BLACK,
        )


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
        self.small_font = get_font(16)

        # Box
        box_w, box_h = 450, 200
        screen_w, screen_h = pygame.display.get_surface().get_size()
        self.box_rect = pygame.Rect(
            screen_w / 2 - box_w / 2, screen_h / 2 - box_h / 2, box_w, box_h
        )

        # Botões
        btn_w, btn_h = 150, 40
        btn_y = self.box_rect.bottom - btn_h - 20
        self.yes_rect = pygame.Rect(
            self.box_rect.centerx - btn_w - 10, btn_y, btn_w, btn_h
        )
        self.no_rect = pygame.Rect(self.box_rect.centerx + 10, btn_y, btn_w, btn_h)

        # Texto com quebra automática para evitar overflow
        self.text_max_width = self.box_rect.width - 50
        message_text = " ".join(question_lines)
        self.message_font = self.item_font
        self.message_lines = self._wrap_text(
            self.message_font, message_text, self.text_max_width
        )

        line_gap = 8
        line_height = self.message_font.get_linesize()
        text_block_height = (len(self.message_lines) * line_height) + (
            max(0, len(self.message_lines) - 1) * line_gap
        )
        text_top = self.box_rect.y + 25
        text_bottom = self.yes_rect.y - 12
        available_height = max(0, text_bottom - text_top)

        if text_block_height > available_height:
            self.message_font = self.small_font
            self.message_lines = self._wrap_text(
                self.message_font, message_text, self.text_max_width
            )
            line_height = self.message_font.get_linesize()
            text_block_height = (len(self.message_lines) * line_height) + (
                max(0, len(self.message_lines) - 1) * line_gap
            )

        self.line_rects: List[pygame.Rect] = []
        y_offset = text_top + max(0, (available_height - text_block_height) // 2)
        for line in self.message_lines:
            rect = self.message_font.render(line, True, colors.WHITE).get_rect(
                centerx=self.box_rect.centerx,
                top=y_offset,
            )
            self.line_rects.append(rect)
            y_offset += line_height + line_gap

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
        for line_text, rect in zip(self.message_lines, self.line_rects):
            line_surface = self.message_font.render(line_text, True, colors.WHITE)
            surface.blit(line_surface, rect)

        # Botões
        self._draw_button(surface, self.yes_rect, "Sim", colors.GREEN)
        self._draw_button(surface, self.no_rect, "Não", colors.RED)

    def _wrap_text(
        self, font: pygame.font.Font, text: str, max_width: int
    ) -> list[str]:
        """Quebra texto em linhas para caber dentro do dialog."""
        words = text.split()
        if not words:
            return [""]

        lines: list[str] = []
        current = words[0]

        for word in words[1:]:
            candidate = f"{current} {word}"
            if font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word

        lines.append(current)
        return lines

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
