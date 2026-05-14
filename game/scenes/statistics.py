from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List

import pygame

from ..core import colors
from ..core.assets import get_font
from ..core.colors import BLACK, CUSTOM_GOLD, CUSTOM_PURPLE
from ..core.meta_progression import PerformanceState, PlayerProfile, WorldUnlockStatus
from ..core.paths import get_profile_path
from ..core.state import Scene
from .ui_helpers import draw_bordered_button, render_with_fade

if TYPE_CHECKING:
    from ..app import GameApp


class StatTab(Enum):
    """Abas disponíveis na tela de estatísticas."""

    OVERVIEW = "Visão Geral"
    LEVELS = "Níveis"
    # HISTORY = "Histórico" # Desativado por enquanto para simplificar


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

        if event.type == pygame.MOUSEWHEEL:
            if self.current_tab in [StatTab.LEVELS, StatTab.OVERVIEW]:
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

        surface.set_clip(None)

    def _render_overview_tab(
        self, surface: pygame.Surface, area: pygame.Rect, alpha: int = 255
    ):
        if not self.profile:
            return
        summary = self.profile.get_statistics_summary()

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
        cols = 2  # Forçado para 2 colunas como solicitado
        col_width = (area.width - 40) / cols

        # Calcular altura do Card 1
        rows = (len(stats_data) + cols - 1) // cols
        card1_height = 60 + rows * 35 + 20  # Header + Rows + Padding

        # Calcular altura do Card 2
        num_recom = len(summary["recommendations"]) if summary["recommendations"] else 1
        card2_height = 60 + num_recom * 28 + 20

        # Altura total do conteúdo
        total_height = card1_height + 20 + card2_height

        # Ajuste de Scroll
        visible_height = area.height
        if total_height > visible_height:
            self.scroll_y = max(0, min(self.scroll_y, total_height - visible_height))
        else:
            self.scroll_y = 0

        # Criar superfície de conteúdo
        content_surface = pygame.Surface(
            (area.width, max(total_height, visible_height)), pygame.SRCALPHA
        )

        current_y = 0

        # --- Card 1: Resumo ---
        card_rect = pygame.Rect(0, current_y, area.width, card1_height)
        self._draw_card_background(content_surface, card_rect, alpha)

        header = self.header_font.render("Resumo do Piloto", True, CUSTOM_GOLD)
        header.set_alpha(alpha)
        content_surface.blit(header, (card_rect.x + 20, card_rect.y + 15))

        stats_y = card_rect.y + 60

        for i, (label, value) in enumerate(stats_data):
            col = i % cols
            row = i // cols
            x_pos = card_rect.x + 20 + col * col_width
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
        content_surface.blit(header, (recom_rect.x + 20, recom_rect.y + 15))

        recom_y_inner = recom_rect.y + 60
        if summary["recommendations"]:
            for recom in summary["recommendations"]:
                recom_surf = self.small_font.render(f"• {recom}", True, colors.GRAY)
                recom_surf.set_alpha(alpha)
                content_surface.blit(recom_surf, (recom_rect.x + 25, recom_y_inner))
                recom_y_inner += 28
        else:
            recom_surf = self.small_font.render(
                "Nenhuma recomendação no momento. Continue jogando!", True, colors.GRAY
            )
            recom_surf.set_alpha(alpha)
            content_surface.blit(recom_surf, (recom_rect.x + 25, recom_y_inner))

        # Blitar conteúdo com scroll
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

        header = self.header_font.render("Performance por Nível", True, CUSTOM_GOLD)
        header.set_alpha(alpha)
        surface.blit(header, (area.x, area.y))

        y = area.y + 50
        if not self.profile.level_stats:
            text = self.item_font.render(
                "Nenhum nível jogado ainda.", True, colors.GRAY
            )
            text.set_alpha(alpha)
            surface.blit(text, (area.x, y))
            return

        sorted_levels = sorted(self.profile.level_stats.keys())

        # Calcular altura total do conteúdo
        total_height = 0
        for level_num in sorted_levels:
            stats = self.profile.level_stats[level_num]
            num_lines = 3  # Nível, Tentativas, Sucesso
            if stats.best_time:
                num_lines += 2  # Melhor tempo, Melhor pontuação
            card_height = (
                20 + (num_lines * 25) + 10
            )  # padding top + lines + padding bottom
            total_height += card_height + 15  # + spacing

        # Ajustar scroll_y
        visible_height = area.height - 50  # subtrair espaço do header
        if total_height > visible_height:
            self.scroll_y = max(0, min(self.scroll_y, total_height - visible_height))
        else:
            self.scroll_y = 0

        # Criar superfície de conteúdo
        content_surface = pygame.Surface(
            (area.width, max(total_height, visible_height)), pygame.SRCALPHA
        )

        # Renderizar conteúdo na superfície
        content_y = 0
        for level_num in sorted_levels:
            stats = self.profile.level_stats[level_num]
            # Calculate card height based on content (each line is ~25px)
            num_lines = 3  # Nível, Tentativas, Sucesso
            if stats.best_time:
                num_lines += 2  # Melhor tempo, Melhor pontuação
            card_height = (
                20 + (num_lines * 25) + 10
            )  # padding top + lines + padding bottom
            card_rect = pygame.Rect(0, content_y, area.width, card_height)
            self._draw_card_background(content_surface, card_rect, alpha)

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
                content_surface,
                (*bar_color, alpha),
                (card_rect.x, card_rect.y, 10, card_rect.height),
                border_radius=8,
            )

            # Cada informação em sua própria linha
            line_y = card_rect.y + 15
            line_spacing = 25

            # Linha 1: Nível
            level_label = self.item_font.render("Nível", True, colors.GRAY)
            level_label.set_alpha(alpha)
            level_value = self.item_font.render(str(level_num), True, CUSTOM_PURPLE)
            level_value.set_alpha(alpha)
            content_surface.blit(level_label, (card_rect.x + 25, line_y))
            content_surface.blit(
                level_value, (card_rect.x + 25 + level_label.get_width() + 5, line_y)
            )
            line_y += line_spacing + 10  # Extra margin before line 2

            # Linha 2: Tentativas
            attempts_label = self.small_font.render("Tentativas:", True, colors.GRAY)
            attempts_label.set_alpha(alpha)
            attempts_value = self.small_font.render(
                str(stats.attempts), True, CUSTOM_PURPLE
            )
            attempts_value.set_alpha(alpha)
            content_surface.blit(attempts_label, (card_rect.x + 25, line_y))
            content_surface.blit(
                attempts_value,
                (card_rect.x + 25 + attempts_label.get_width() + 5, line_y),
            )
            line_y += line_spacing

            # Linha 3: Sucesso
            success_label = self.small_font.render("Sucesso:", True, colors.GRAY)
            success_label.set_alpha(alpha)
            success_value = self.small_font.render(
                f"{stats.clear_rate:.0%}", True, CUSTOM_PURPLE
            )
            success_value.set_alpha(alpha)
            content_surface.blit(success_label, (card_rect.x + 25, line_y))
            content_surface.blit(
                success_value,
                (card_rect.x + 25 + success_label.get_width() + 5, line_y),
            )
            line_y += line_spacing

            if stats.best_time:
                # Linha 4: Melhor tempo
                time_label = self.small_font.render("Melhor tempo:", True, colors.GRAY)
                time_label.set_alpha(alpha)
                time_value = self.small_font.render(
                    f"{stats.best_time:.1f}s", True, CUSTOM_PURPLE
                )
                time_value.set_alpha(alpha)
                content_surface.blit(time_label, (card_rect.x + 25, line_y))
                content_surface.blit(
                    time_value, (card_rect.x + 25 + time_label.get_width() + 5, line_y)
                )
                line_y += line_spacing

                # Linha 5: Melhor pontuação
                score_label = self.small_font.render(
                    "Melhor pontuação:", True, colors.GRAY
                )
                score_label.set_alpha(alpha)
                score_value = self.small_font.render(
                    f"{stats.best_score:,}", True, CUSTOM_PURPLE
                )
                score_value.set_alpha(alpha)
                content_surface.blit(score_label, (card_rect.x + 25, line_y))
                content_surface.blit(
                    score_value,
                    (card_rect.x + 25 + score_label.get_width() + 5, line_y),
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
