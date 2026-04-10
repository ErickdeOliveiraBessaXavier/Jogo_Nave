from typing import TYPE_CHECKING, Any, Callable, Dict

import pygame

from ..core import colors
from ..core.assets import get_font
from ..core.colors import BLACK, CUSTOM_GOLD, CUSTOM_PURPLE
from ..core.meta_progression import PlayerProfile
from ..core.paths import get_preferences_path, get_profile_path
from ..core.preferences import UserPreferences
from ..core.sound import sound_manager
from ..core.state import Scene

if TYPE_CHECKING:
    from ..app import GameApp


class SettingsView:
    """View de configurações (pode ser usada dentro de outras cenas)."""

    def __init__(
        self,
        on_back: Callable[[], None],
        renderer: Any = None,
        on_restart: Callable[[], None] | None = None,
        app: Any = None,
    ):
        """
        Args:
            on_back: Callback chamado quando o usuário quer voltar
            renderer: Renderer compartilhado (opcional)
            on_restart: Callback chamado quando o usuário quer reiniciar o jogo (opcional)
        """
        self.on_back = on_back
        self.on_restart = on_restart
        self.renderer = renderer
        self._app = app

        # Agora usamos ambos: preferências para sistema e profile para progressão (se necessário)
        self.preferences = UserPreferences(get_preferences_path())
        self.player_profile = PlayerProfile(get_profile_path())

        # Fonts
        self.title_font = get_font(40)
        self.header_font = get_font(24)
        self.item_font = get_font(20)
        self.small_font = get_font(16)
        self.percent_font = get_font(14)

        # Estado da UI
        self.sliders: Dict[str, float] = {
            "music": self.preferences.music_volume,
            "sfx": self.preferences.sfx_volume,
            "shot": self.preferences.shot_volume,
        }
        self.toggles: Dict[str, bool] = {
            "mouse_control": self.preferences.mouse_control,
            "auto_fire": self.preferences.auto_fire,
        }
        self.dragging_slider: str | None = None

        # Resoluções disponíveis (mantendo 16:9)
        self.available_resolutions = [
            (1024, 576, "576p"),
            (1280, 720, "720p"),
            (1366, 768, "768p"),
            (1600, 900, "900p"),
            (1920, 1080, "1080p"),
            (2048, 1152, "1152p"),
            (2560, 1440, "1440p"),
            (3200, 1800, "1800p"),
            (3840, 2160, "4K"),
            (5120, 2880, "5K"),
        ]

        # Carregar resolução salva das preferências
        saved_res = self.preferences.resolution
        self.selected_resolution_index = 1  # default
        for i, (w, h, _) in enumerate(self.available_resolutions):
            if w == saved_res[0] and h == saved_res[1]:
                self.selected_resolution_index = i
                break

        # Animação de entrada
        self.entry_progress = 0.0
        self.is_entering = True
        self.entry_duration = 0.4

        # Tooltip para resoluções
        self.hovered_resolution_index: int | None = None
        self.layout_rects: Dict[str, Any] = {}

        # Estado do pop-up de confirmação
        self.show_restart_popup = False

        self._calculate_layout()

    def _calculate_layout(self):
        from ..core.config import config as Config

        screen_w, screen_h = Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT

        # Dimensões e espaçamentos
        outer_pad = 40
        card_gap = 40

        # Calcular largura dinâmica para ocupar a tela toda
        available_width = screen_w - (2 * outer_pad)
        card_width = (available_width - card_gap) / 2
        card_height = screen_h - 180

        # Posição inicial X
        start_x = outer_pad

        # Card de Áudio (Esquerda)
        audio_card_rect = pygame.Rect(start_x, 100, card_width, card_height)
        self.layout_rects["audio_card"] = audio_card_rect

        self.layout_rects["sliders"] = {}
        slider_w = card_width - 60
        slider_h = 20
        y_offset = audio_card_rect.y + 80

        for key in ["music", "sfx", "shot"]:
            self.layout_rects["sliders"][key] = pygame.Rect(
                audio_card_rect.x + 30, y_offset, slider_w, slider_h
            )
            y_offset += 100

        # Card de Controles (Direita)
        controls_card_rect = pygame.Rect(
            start_x + card_width + card_gap, 100, card_width, card_height
        )
        self.layout_rects["controls_card"] = controls_card_rect

        # Toggles de controle
        self.layout_rects["toggles"] = {}
        toggle_w, toggle_h = 30, 30
        y_offset = controls_card_rect.y + 60

        # Agrupar toggles
        for key in ["mouse_control", "auto_fire"]:
            self.layout_rects["toggles"][key] = pygame.Rect(
                controls_card_rect.x + 30, y_offset, toggle_w, toggle_h
            )
            y_offset += 50

        # Seletor de resolução
        y_offset += 20
        self.layout_rects["resolution_label"] = pygame.Rect(
            controls_card_rect.x + 30,
            y_offset,
            controls_card_rect.width - 60,
            30,
        )

        # Grid de botões de resolução
        self.layout_rects["resolution_buttons"] = []

        # Configuração do grid
        cols = 3
        button_gap_x = 10
        button_gap_y = 10
        available_width_for_buttons = controls_card_rect.width - 60
        button_w = (available_width_for_buttons - (cols - 1) * button_gap_x) / cols
        button_h = 35

        grid_start_y = y_offset + 40

        from typing import List, cast

        resolution_buttons = cast(
            List[pygame.Rect], self.layout_rects["resolution_buttons"]
        )

        for i in range(len(self.available_resolutions)):
            row = i // cols
            col = i % cols

            x = controls_card_rect.x + 30 + col * (button_w + button_gap_x)
            y = grid_start_y + row * (button_h + button_gap_y)

            resolution_buttons.append(pygame.Rect(x, y, button_w, button_h))

        # Botão de Voltar (Canto inferior esquerdo, alinhado com card)
        back_text_width = self.item_font.size("Voltar")[0]
        back_btn_width = back_text_width + 60
        self.layout_rects["back_button"] = pygame.Rect(
            start_x, screen_h - 60, back_btn_width, 40
        )

        # Pop-up de confirmação (Centralizado na tela)
        popup_w, popup_h = 500, 220
        popup_x = (screen_w - popup_w) // 2
        popup_y = (screen_h - popup_h) // 2
        self.layout_rects["popup_rect"] = pygame.Rect(
            popup_x, popup_y, popup_w, popup_h
        )

        # Botões do pop-up
        btn_w = 100
        btn_h = 40
        btn_gap = 20
        total_btn_width = (btn_w * 2) + btn_gap

        start_btn_x = popup_x + (popup_w - total_btn_width) // 2
        btn_y = popup_y + popup_h - btn_h - 25

        self.layout_rects["popup_yes_button"] = pygame.Rect(
            start_btn_x, btn_y, btn_w, btn_h
        )
        self.layout_rects["popup_no_button"] = pygame.Rect(
            start_btn_x + btn_w + btn_gap, btn_y, btn_w, btn_h
        )

    def reset(self):
        """Reseta o estado da view para reiniciar animação."""
        self.entry_progress = 0.0
        self.is_entering = True
        self.dragging_slider = None

        # Recarregar das preferências
        self.preferences.load()
        self.sliders["music"] = self.preferences.music_volume
        self.sliders["sfx"] = self.preferences.sfx_volume
        self.sliders["shot"] = self.preferences.shot_volume

        self.toggles["mouse_control"] = self.preferences.mouse_control
        self.toggles["auto_fire"] = self.preferences.auto_fire

        saved_res = self.preferences.resolution
        for i, (w, h, _) in enumerate(self.available_resolutions):
            if w == saved_res[0] and h == saved_res[1]:
                self.selected_resolution_index = i
                break

    def update(self, dt: float):
        """Atualiza a lógica da view."""
        if self.is_entering and self.entry_progress < 1.0:
            self.entry_progress = min(
                1.0, self.entry_progress + dt / self.entry_duration
            )
            if self.entry_progress >= 1.0:
                self.is_entering = False

        # Detectar hover nos botões de resolução
        if not self.is_entering:
            mouse_pos = pygame.mouse.get_pos()
            from typing import List, cast

            resolution_buttons = cast(
                List[pygame.Rect], self.layout_rects["resolution_buttons"]
            )
            self.hovered_resolution_index = None
            for i, button_rect in enumerate(resolution_buttons):
                if button_rect.collidepoint(mouse_pos):
                    self.hovered_resolution_index = i
                    break

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Processa eventos da view."""
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.preferences.save()
            self.on_back()
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self.layout_rects["back_button"].collidepoint(pos):
                self.preferences.save()
                self.on_back()
                return True

            # Botões de resolução
            from typing import List, cast

            resolution_buttons = cast(
                List[pygame.Rect], self.layout_rects["resolution_buttons"]
            )
            for i, button_rect in enumerate(resolution_buttons):
                if button_rect.collidepoint(pos):
                    self.selected_resolution_index = i
                    # Salvar nas preferências
                    w, h, _ = self.available_resolutions[i]
                    self.preferences.resolution = (w, h)
                    self.preferences.save()
                    # Mostrar pop-up de aviso
                    self.show_restart_popup = True
                    return True

            # Toggles
            for key, rect in self.layout_rects["toggles"].items():
                if rect.collidepoint(pos):
                    self.toggles[key] = not self.toggles[key]
                    # Salvar nas preferências
                    if key == "mouse_control":
                        self.preferences.mouse_control = self.toggles[key]
                        # Aplica imediatamente ao input em execução
                        if self._app is not None:
                            self._app.input.mouse_control = self.toggles[key]
                    elif key == "auto_fire":
                        self.preferences.auto_fire = self.toggles[key]
                        # Aplica imediatamente ao input em execução
                        if self._app is not None:
                            self._app.input.auto_fire = self.toggles[key]
                    self.preferences.save()
                    return True

            # Pop-up de confirmação
            if self.show_restart_popup:
                if self.layout_rects["popup_yes_button"].collidepoint(pos):
                    self.show_restart_popup = False
                    import sys

                    pygame.quit()
                    sys.exit(0)
                    return True
                elif self.layout_rects["popup_no_button"].collidepoint(pos):
                    self.show_restart_popup = False
                    return True

            # Sliders
            for key, rect in self.layout_rects["sliders"].items():
                if rect.collidepoint(pos):
                    self.dragging_slider = key
                    # Atualizar valor no clique
                    new_val = (pos[0] - rect.x) / rect.w
                    self.sliders[key] = max(0.0, min(1.0, new_val))
                    self._update_volume(key)
                    return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging_slider:
                self.preferences.save()
            self.dragging_slider = None
            return True

        if event.type == pygame.MOUSEMOTION:
            if self.dragging_slider:
                key = self.dragging_slider
                rect = self.layout_rects["sliders"][key]
                pos = event.pos
                new_val = (pos[0] - rect.x) / rect.w
                self.sliders[key] = max(0.0, min(1.0, new_val))
                self._update_volume(key)
                return True

        return False

    def _update_volume(self, key: str):
        volume = self.sliders[key]
        if key == "music":
            self.preferences.music_volume = volume
            sound_manager.set_music_volume(volume)
        elif key == "sfx":
            self.preferences.sfx_volume = volume
            sound_manager.set_sfx_volume(volume)
        elif key == "shot":
            self.preferences.shot_volume = volume
            sound_manager.set_shot_volume(volume)

    def render(self, surface: pygame.Surface):
        """Renderiza a view."""
        # Calcular alpha baseado no progresso
        alpha = int(255 * self.entry_progress)
        offset_y = int(30 * (1.0 - self.entry_progress))

        # Título
        title_surf = self.title_font.render("Configurações", True, CUSTOM_GOLD)
        title_surf.set_alpha(alpha)
        # Centralizar título
        title_x = (surface.get_width() - title_surf.get_width()) // 2
        surface.blit(title_surf, (title_x, 20 + offset_y))

        # Desenhar Cards com alpha
        self._draw_audio_card(surface, alpha, offset_y)
        self._draw_controls_card(surface, alpha, offset_y)

        # Botão Voltar com alpha
        self._draw_button(
            surface,
            self.layout_rects["back_button"],
            "Voltar",
            CUSTOM_PURPLE,
            alpha,
            offset_y,
        )

        # Pop-up de confirmação
        if self.show_restart_popup:
            self._draw_restart_popup(surface)

    def _draw_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        text: str,
        color: colors.Color,
        alpha: int = 255,
        offset_y: int = 0,
    ):
        adjusted_rect = rect.copy()
        adjusted_rect.y += offset_y

        is_hovered = adjusted_rect.collidepoint(pygame.mouse.get_pos())
        # Inverter cores ao passar o mouse
        if color == CUSTOM_PURPLE:
            border_color = CUSTOM_GOLD if is_hovered else CUSTOM_PURPLE
        else:
            border_color = color

        # Criar surface temporária para aplicar alpha
        temp_surface = pygame.Surface(
            (adjusted_rect.width + 4, adjusted_rect.height + 4), pygame.SRCALPHA
        )
        temp_rect = pygame.Rect(2, 2, adjusted_rect.width, adjusted_rect.height)
        pygame.draw.rect(
            temp_surface, (*border_color, alpha), temp_rect, 2, border_radius=8
        )
        surface.blit(temp_surface, (adjusted_rect.x - 2, adjusted_rect.y - 2))

        text_surf = self.item_font.render(text, True, colors.WHITE)
        text_surf.set_alpha(alpha)
        surface.blit(
            text_surf,
            (
                adjusted_rect.centerx - text_surf.get_width() / 2,
                adjusted_rect.centery - text_surf.get_height() / 2,
            ),
        )

    def _draw_card(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        title: str,
        alpha: int = 255,
        offset_y: int = 0,
    ):
        adjusted_rect = rect.copy()
        adjusted_rect.y += offset_y

        # Apenas a borda, sem fundo
        temp_surface = pygame.Surface(
            (adjusted_rect.width + 2, adjusted_rect.height + 2), pygame.SRCALPHA
        )
        pygame.draw.rect(
            temp_surface,
            (*colors.GRAY, alpha),
            pygame.Rect(1, 1, adjusted_rect.width, adjusted_rect.height),
            1,
            border_radius=8,
        )
        surface.blit(temp_surface, (adjusted_rect.x - 1, adjusted_rect.y - 1))

        title_surf = self.header_font.render(title, True, CUSTOM_GOLD)
        title_surf.set_alpha(alpha)
        surface.blit(title_surf, (adjusted_rect.x + 15, adjusted_rect.y + 15))

    def _draw_audio_card(
        self, surface: pygame.Surface, alpha: int = 255, offset_y: int = 0
    ):
        card_rect = self.layout_rects["audio_card"].copy()
        card_rect.y += offset_y
        self._draw_card(
            surface, self.layout_rects["audio_card"], "Áudio", alpha, offset_y
        )

        labels = {"music": "Música", "sfx": "Efeitos (SFX)", "shot": "Tiros"}

        # Criar clipping para o card
        clip_rect = card_rect.inflate(-10, -10)
        surface.set_clip(clip_rect)

        for key in self.sliders:
            rect = self.layout_rects["sliders"][key].copy()
            rect.y += offset_y

            # Label
            label_surf = self.item_font.render(labels[key], True, colors.WHITE)
            label_surf.set_alpha(alpha)
            surface.blit(label_surf, (rect.x, rect.y - 30))

            # Slider
            val = self.sliders[key]
            # Barra de fundo
            temp_bg = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            pygame.draw.rect(
                temp_bg, (10, 10, 10, alpha), temp_bg.get_rect(), border_radius=10
            )
            surface.blit(temp_bg, rect.topleft)

            # Barra de preenchimento
            fill_width = val * rect.width
            fill_rect = pygame.Rect(0, 0, fill_width, rect.height)
            temp_fill = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            pygame.draw.rect(
                temp_fill, (*CUSTOM_PURPLE, alpha), fill_rect, border_radius=10
            )
            surface.blit(temp_fill, rect.topleft)

            # Borda
            temp_border = pygame.Surface(
                (rect.width + 2, rect.height + 2), pygame.SRCALPHA
            )
            pygame.draw.rect(
                temp_border,
                (*colors.GRAY, alpha),
                pygame.Rect(1, 1, rect.width, rect.height),
                1,
                border_radius=10,
            )
            surface.blit(temp_border, (rect.x - 1, rect.y - 1))

            # Knob
            knob_x = rect.x + int(val * rect.w)
            knob_rect = pygame.Rect(0, 0, 10, rect.height + 10)
            knob_rect.center = (knob_x, rect.centery)
            temp_knob = pygame.Surface(
                (knob_rect.width + 2, knob_rect.height + 2), pygame.SRCALPHA
            )
            pygame.draw.rect(
                temp_knob,
                (*CUSTOM_GOLD, alpha),
                pygame.Rect(1, 1, knob_rect.width, knob_rect.height),
                border_radius=3,
            )
            surface.blit(temp_knob, (knob_rect.x - 1, knob_rect.y - 1))

            # Valor em %
            percent_text = f"{int(val * 100)}%"
            percent_surf = self.percent_font.render(percent_text, True, colors.GRAY)
            percent_surf.set_alpha(alpha)
            percent_x = min(
                rect.right + 5, card_rect.right - percent_surf.get_width() - 25
            )
            surface.blit(
                percent_surf, (percent_x, rect.centery - percent_surf.get_height() / 2)
            )

        surface.set_clip(None)

    def _draw_controls_card(
        self, surface: pygame.Surface, alpha: int = 255, offset_y: int = 0
    ):
        card_rect = self.layout_rects["controls_card"].copy()
        card_rect.y += offset_y
        self._draw_card(
            surface,
            self.layout_rects["controls_card"],
            "Controles & Resolução",
            alpha,
            offset_y,
        )

        # Criar clipping para o card
        clip_rect = card_rect.inflate(-10, -10)
        surface.set_clip(clip_rect)

        # Toggles
        labels = {"mouse_control": "Controle por Mouse", "auto_fire": "Tiro Automático"}
        for key in self.toggles:
            rect = self.layout_rects["toggles"][key].copy()
            rect.y += offset_y

            # Checkbox
            is_checked = self.toggles[key]
            checkbox_color = CUSTOM_GOLD if is_checked else colors.GRAY
            pygame.draw.rect(
                surface, (*checkbox_color, alpha), rect, 2, border_radius=5
            )
            if is_checked:
                # Checkmark
                check_surf = pygame.Surface((rect.width - 6, rect.height - 6))
                check_surf.fill((*CUSTOM_GOLD, alpha))
                surface.blit(check_surf, (rect.x + 3, rect.y + 3))

            # Label
            label_surf = self.item_font.render(labels[key], True, colors.WHITE)
            label_surf.set_alpha(alpha)
            surface.blit(
                label_surf,
                (rect.right + 10, rect.centery - label_surf.get_height() / 2),
            )

        # Label da resolução
        label_rect = self.layout_rects["resolution_label"].copy()
        label_rect.y += offset_y
        label_surf = self.item_font.render("Resolução:", True, CUSTOM_GOLD)
        label_surf.set_alpha(alpha)
        surface.blit(label_surf, (label_rect.x, label_rect.y))

        # Botões de resolução
        from typing import List, cast

        resolution_buttons = cast(
            List[pygame.Rect], self.layout_rects["resolution_buttons"]
        )
        for i, (w, h, label) in enumerate(self.available_resolutions):
            button_rect = resolution_buttons[i].copy()
            button_rect.y += offset_y

            is_selected = i == self.selected_resolution_index
            color = CUSTOM_GOLD if is_selected else CUSTOM_PURPLE

            self._draw_button(
                surface,
                button_rect,
                label,
                color,
                alpha,
                0,
            )

        # Tooltip para resolução hoverada
        if self.hovered_resolution_index is not None:
            from ..core.config import config as Config

            w, h, label = self.available_resolutions[self.hovered_resolution_index]
            tooltip_text = f"{w}×{h} pixels"

            tooltip_font = self.small_font
            tooltip_surf = tooltip_font.render(tooltip_text, True, CUSTOM_GOLD)
            tooltip_surf.set_alpha(int(alpha * 0.9))

            mouse_x, mouse_y = pygame.mouse.get_pos()
            tooltip_x = mouse_x - tooltip_surf.get_width() // 2
            tooltip_y = mouse_y - 35

            tooltip_x = max(
                10, min(tooltip_x, Config.SCREEN_WIDTH - tooltip_surf.get_width() - 10)
            )
            tooltip_y = max(10, tooltip_y)

            bg_rect = pygame.Rect(
                tooltip_x - 5,
                tooltip_y - 3,
                tooltip_surf.get_width() + 10,
                tooltip_surf.get_height() + 6,
            )
            bg_surf = pygame.Surface((bg_rect.width, bg_rect.height))
            bg_surf.fill(BLACK)
            bg_surf.set_alpha(int(alpha * 0.7))
            surface.blit(bg_surf, bg_rect)

            surface.blit(tooltip_surf, (tooltip_x, tooltip_y))

        # Instruções de controles
        instructions = [
            "CONTROLES:",
            "• WASD / Setas: Mover",
            "• Espaço: Atirar",
            "• P: Pausar | ESC: Sair",
            "",
            "NOTA: Mudar resolução",
            "requer reiniciar.",
        ]

        resolution_buttons = cast(
            List[pygame.Rect], self.layout_rects["resolution_buttons"]
        )
        if resolution_buttons:
            max_button_y = max(r.y + r.height for r in resolution_buttons)
        else:
            max_button_y = card_rect.y + 250

        y_offset = max_button_y + 30 + offset_y

        for line in instructions:
            if line == "":
                y_offset += 8
                continue
            color = CUSTOM_GOLD if ":" in line or "NOTA" in line else colors.WHITE
            text_surf = self.small_font.render(line, True, color)
            text_surf.set_alpha(alpha)
            text_x = card_rect.centerx - text_surf.get_width() // 2
            surface.blit(text_surf, (text_x, y_offset))
            y_offset += 22

        surface.set_clip(None)

    def _draw_restart_popup(self, surface: pygame.Surface):
        """Desenha o pop-up de confirmação para reiniciar o jogo."""
        popup_rect = self.layout_rects["popup_rect"]

        overlay = pygame.Surface((surface.get_width(), surface.get_height()))
        overlay.fill((0, 0, 0))
        overlay.set_alpha(128)
        surface.blit(overlay, (0, 0))

        pygame.draw.rect(surface, colors.DARK_GRAY, popup_rect, border_radius=10)
        pygame.draw.rect(surface, CUSTOM_GOLD, popup_rect, 2, border_radius=10)

        title_surf = self.header_font.render("Reinício Necessário", True, CUSTOM_GOLD)
        surface.blit(
            title_surf,
            (popup_rect.centerx - title_surf.get_width() // 2, popup_rect.y + 20),
        )

        message_lines = [
            "As alterações só serão",
            "vistas ao reiniciar o jogo.",
            "Deseja fazer isso agora?",
        ]
        y_offset = popup_rect.y + 60
        for line in message_lines:
            text_surf = self.item_font.render(line, True, colors.WHITE)
            surface.blit(
                text_surf, (popup_rect.centerx - text_surf.get_width() // 2, y_offset)
            )
            y_offset += 25

        self._draw_button(
            surface, self.layout_rects["popup_yes_button"], "Sim", colors.RED, 255, 0
        )
        self._draw_button(
            surface, self.layout_rects["popup_no_button"], "Não", CUSTOM_PURPLE, 255, 0
        )


class SettingsScene(Scene):
    """Cena de configurações."""

    def __init__(self, app: "GameApp", return_to_game: bool = False):
        super().__init__(app)
        self.return_to_game = return_to_game
        self.r = app.renderer
        self.view = SettingsView(on_back=self._on_back, renderer=self.r, app=app)

        self.transitioning = False
        self.transition_progress = 0.0
        self.transition_duration = 0.3
        self.fade_out = False

    def _on_back(self):
        self.fade_out = True
        self.transitioning = True
        self.transition_progress = 0.0

    def enter(self):
        pygame.mouse.set_visible(True)
        self.view.reset()

    def exit(self):
        self.view.preferences.save()
        self.view.player_profile.save()

    def handle_event(self, event: pygame.event.Event):
        self.view.handle_event(event)

    def update(self, dt: float):
        self.r.starfield.update(dt)

        if self.transitioning:
            self.transition_progress += dt / self.transition_duration

            if self.transition_progress >= 1.0:
                if self.return_to_game:
                    self.app.states.pop()
                else:
                    from .main_menu import MainMenuScene

                    self.app.states.switch(MainMenuScene(self.app))
                return

        self.view.update(dt)

    def render(self, surface: pygame.Surface):
        surface.fill(BLACK)
        self.r.starfield.draw(surface)

        if self.transitioning:
            alpha_mult = (
                1.0 - self.transition_progress
                if self.fade_out
                else self.transition_progress
            )
            temp_surface = pygame.Surface(
                (surface.get_width(), surface.get_height()), pygame.SRCALPHA
            )
            self.view.render(temp_surface)
            temp_surface.set_alpha(int(255 * alpha_mult))
            surface.blit(temp_surface, (0, 0))
        else:
            self.view.render(surface)
