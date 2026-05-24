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
from .ui_helpers import (
    FadeTransitionMixin,
    wrap_text,
    draw_bordered_button,
    render_with_fade,
)

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
        runtime_scene: Any = None,
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
        self._runtime_scene = runtime_scene

        # Agora usamos ambos: preferências para sistema e profile para progressão (se necessário)
        self.preferences = UserPreferences(get_preferences_path())
        self.player_profile = PlayerProfile(get_profile_path())

        # Fonts
        self.title_font = get_font(36)
        self.header_font = get_font(18)
        self.item_font = get_font(16)
        self.small_font = get_font(13)
        self.percent_font = get_font(13)

        # Estado da UI
        self.sliders: Dict[str, float] = {
            "music": self.preferences.music_volume,
            "sfx": self.preferences.sfx_volume,
            "shot": self.preferences.shot_volume,
        }
        self.toggles: Dict[str, bool] = {
            "p1_prefers_keyboard": self.preferences.p1_prefers_keyboard,
            "mouse_control": self.preferences.mouse_control,
            "auto_fire": self.preferences.auto_fire,
            "gamepad_enabled": self.preferences.gamepad_enabled,
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
        # Pop-up informativo (texto livre + botão OK). Usado quando o usuário
        # tenta alterar configs sensíveis ao modo coop durante uma partida
        # multiplayer ativa.
        self.info_popup_text: str | None = None

        self._calculate_layout()

    def _calculate_layout(self):
        from ..core.config import config as Config

        screen_w, screen_h = Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT

        # Dimensões e espaçamentos
        outer_pad = 40
        card_gap = 40
        card_inner_pad_x = 30

        # Calcular largura dinâmica para ocupar a tela toda
        available_width = screen_w - (2 * outer_pad)
        card_width = (available_width - card_gap) / 2
        card_height = screen_h - 180

        # Centralizar cards verticalmente
        card_y = (screen_h - card_height) // 2 + 20

        # Posição inicial X
        start_x = outer_pad

        # Card de Áudio (Esquerda)
        audio_card_rect = pygame.Rect(start_x, card_y, card_width, card_height)
        self.layout_rects["audio_card"] = audio_card_rect

        self.layout_rects["sliders"] = {}
        slider_w = card_width - 60
        slider_h = 20
        y_offset = audio_card_rect.y + 80

        for key in ["music", "sfx", "shot"]:
            self.layout_rects["sliders"][key] = pygame.Rect(
                audio_card_rect.x + card_inner_pad_x, y_offset, slider_w, slider_h
            )
            y_offset += 100

        # Card de Controles (Direita)
        controls_card_rect = pygame.Rect(
            start_x + card_width + card_gap, card_y, card_width, card_height
        )
        self.layout_rects["controls_card"] = controls_card_rect

        # Toggles de controle
        self.layout_rects["toggles"] = {}
        toggle_w, toggle_h = 30, 30
        y_offset = controls_card_rect.y + 60

        # Agrupar toggles
        for key in [
            "p1_prefers_keyboard",
            "mouse_control",
            "auto_fire",
            "gamepad_enabled",
        ]:
            self.layout_rects["toggles"][key] = pygame.Rect(
                controls_card_rect.x + card_inner_pad_x, y_offset, toggle_w, toggle_h
            )
            y_offset += 50

        # Seletor de resolução
        y_offset += 20
        self.layout_rects["resolution_label"] = pygame.Rect(
            controls_card_rect.x + card_inner_pad_x,
            y_offset,
            controls_card_rect.width - (2 * card_inner_pad_x),
            30,
        )

        # Grid de botões de resolução
        self.layout_rects["resolution_buttons"] = []

        # Configuração do grid
        cols = 3
        button_gap_x = 10
        button_gap_y = 10
        available_width_for_buttons = controls_card_rect.width - (2 * card_inner_pad_x)
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

            x = (
                controls_card_rect.x
                + card_inner_pad_x
                + col * (button_w + button_gap_x)
            )
            y = grid_start_y + row * (button_h + button_gap_y)

            resolution_buttons.append(pygame.Rect(x, y, button_w, button_h))

        # Botão de Voltar (Canto inferior esquerdo)
        back_text_width = self.item_font.size("Voltar")[0]
        back_btn_width = back_text_width + 60
        self.layout_rects["back_button"] = pygame.Rect(
            outer_pad, screen_h - 60, back_btn_width, 40
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

        # Pop-up informativo (mesmo bounding-box, apenas 1 botão "OK").
        info_btn_x = popup_x + (popup_w - btn_w) // 2
        self.layout_rects["info_popup_ok_button"] = pygame.Rect(
            info_btn_x, btn_y, btn_w, btn_h
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
        self.toggles["gamepad_enabled"] = self.preferences.gamepad_enabled
        self.toggles["p1_prefers_keyboard"] = self.preferences.p1_prefers_keyboard

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
            if self.info_popup_text is not None:
                self.info_popup_text = None
                return True
            if self.show_restart_popup:
                self.show_restart_popup = False
                return True
            self.preferences.save()
            self.on_back()
            return True

        # Info popup é modal — qualquer click ou botão fecha.
        if self.info_popup_text is not None:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Click em qualquer lugar fecha; verificar o botão OK só pra
                # UX consistente com outros popups.
                self.info_popup_text = None
                return True
            if event.type == pygame.JOYBUTTONDOWN:
                from ..core.gamepad import XboxButton

                if event.button in (XboxButton.A, XboxButton.B, XboxButton.BACK):
                    self.info_popup_text = None
                    return True
            # Consumir demais eventos pra bloquear click-through.
            if event.type in (
                pygame.MOUSEBUTTONUP,
                pygame.MOUSEMOTION,
                pygame.MOUSEWHEEL,
                pygame.KEYDOWN,
            ):
                return True

        # Enquanto o pop-up estiver aberto, bloquear interação com o restante da tela.
        if self.show_restart_popup:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos
                if self.layout_rects["popup_yes_button"].collidepoint(pos):
                    self._popup_confirm()
                    return True
                if self.layout_rects["popup_no_button"].collidepoint(pos):
                    self.show_restart_popup = False
                return True
            if event.type == pygame.JOYBUTTONDOWN:
                from ..core.gamepad import XboxButton

                if event.button == XboxButton.A:
                    pos = pygame.mouse.get_pos()
                    if self.layout_rects["popup_yes_button"].collidepoint(pos):
                        self._popup_confirm()
                    else:
                        # Default A no popup = não (mais seguro contra apertar sem mirar).
                        self.show_restart_popup = False
                    return True
                if event.button in (XboxButton.B, XboxButton.BACK):
                    self.show_restart_popup = False
                    return True
            # Consumir os demais eventos para evitar click-through.
            if event.type in (
                pygame.MOUSEBUTTONUP,
                pygame.MOUSEMOTION,
                pygame.MOUSEWHEEL,
                pygame.KEYDOWN,
            ):
                return True

        if event.type == pygame.JOYBUTTONDOWN:
            from ..core.gamepad import XboxButton

            if event.button == XboxButton.A:
                pos = pygame.mouse.get_pos()
                self._activate_at(pos)
                return True
            if event.button in (XboxButton.B, XboxButton.BACK):
                self.preferences.save()
                self.on_back()
                return True
            if event.button in (XboxButton.LB, XboxButton.RB):
                # LB/RB ajustam o slider sob o cursor — UX similar à de
                # ajuste de áudio em consoles.
                direction = -1 if event.button == XboxButton.LB else +1
                self._adjust_slider_under_cursor(direction)
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
                    if self._try_show_coop_block(key):
                        return True
                    self.toggles[key] = not self.toggles[key]
                    # Salvar nas preferências
                    if key == "p1_prefers_keyboard":
                        self.preferences.p1_prefers_keyboard = self.toggles[key]
                        self._apply_live_control_settings()
                    if key == "mouse_control":
                        self.preferences.mouse_control = self.toggles[key]
                        self._apply_live_control_settings()
                    elif key == "auto_fire":
                        self.preferences.auto_fire = self.toggles[key]
                        self._apply_live_control_settings()
                    elif key == "gamepad_enabled":
                        self.preferences.gamepad_enabled = self.toggles[key]
                        self._apply_live_control_settings()
                    self.preferences.save()
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

    def _popup_confirm(self) -> None:
        """Confirma o reinício solicitado pelo popup de mudança de resolução."""
        import sys

        self.show_restart_popup = False
        pygame.quit()
        sys.exit(0)

    def _is_runtime_coop_active(self) -> bool:
        """True quando há partida coop em andamento (2+ slots no roster).

        Usado para travar toggles que reorganizam slots de gamepad mid-game
        (ex.: `gamepad_enabled`, `p1_prefers_keyboard`). Trocar o roteamento
        de input com P2 já ativo deixaria a nave dele sem input até o usuário
        voltar e religar — UX ruim. Pedimos pra voltar ao menu antes.
        """
        rs = self._runtime_scene
        if rs is None:
            return False
        roster = getattr(rs, "roster", None)
        if roster is None:
            return False
        try:
            return roster.count() >= 2
        except (AttributeError, TypeError):
            return False

    def _try_show_coop_block(self, key: str) -> bool:
        """Se o toggle `key` é sensível e coop está ativo, mostra info popup.

        Retorna True quando o toggle foi bloqueado (o handler deve abortar
        a aplicação da mudança SEM flipar o valor).
        """
        if key not in ("gamepad_enabled", "p1_prefers_keyboard"):
            return False
        if not self._is_runtime_coop_active():
            return False
        self.info_popup_text = (
            "Essa opção só pode ser alterada fora de uma partida "
            "cooperativa. Volte ao menu principal e ajuste antes "
            "de iniciar o coop."
        )
        return True

    def _activate_at(self, pos: tuple[int, int]) -> bool:
        """Aciona o elemento de UI sob ``pos`` (botão, toggle, slider center).

        Reutiliza a mesma lógica do click do mouse — DPad já moveu o cursor
        até o elemento via snap-focus, então basta replicar o efeito do click.
        """
        from typing import List, cast

        if self.layout_rects["back_button"].collidepoint(pos):
            self.preferences.save()
            self.on_back()
            return True

        resolution_buttons = cast(
            List[pygame.Rect], self.layout_rects["resolution_buttons"]
        )
        for i, button_rect in enumerate(resolution_buttons):
            if button_rect.collidepoint(pos):
                self.selected_resolution_index = i
                w, h, _ = self.available_resolutions[i]
                self.preferences.resolution = (w, h)
                self.preferences.save()
                self.show_restart_popup = True
                return True

        for key, rect in self.layout_rects["toggles"].items():
            if rect.inflate(60, 0).collidepoint(pos):
                # Hitbox inflado horizontalmente cobre rótulo — torna a
                # mira do controle mais perdoadora ao apontar pro toggle.
                if self._try_show_coop_block(key):
                    return True
                self.toggles[key] = not self.toggles[key]
                if key == "p1_prefers_keyboard":
                    self.preferences.p1_prefers_keyboard = self.toggles[key]
                    self._apply_live_control_settings()
                elif key == "mouse_control":
                    self.preferences.mouse_control = self.toggles[key]
                    self._apply_live_control_settings()
                elif key == "auto_fire":
                    self.preferences.auto_fire = self.toggles[key]
                    self._apply_live_control_settings()
                elif key == "gamepad_enabled":
                    self.preferences.gamepad_enabled = self.toggles[key]
                    self._apply_live_control_settings()
                self.preferences.save()
                return True

        # Slider: A em cima do slider seta o valor pra posição da mira.
        for key, rect in self.layout_rects["sliders"].items():
            if rect.collidepoint(pos):
                new_val = (pos[0] - rect.x) / rect.w
                self.sliders[key] = max(0.0, min(1.0, new_val))
                self._update_volume(key)
                self.preferences.save()
                return True
        return False

    def _adjust_slider_under_cursor(self, direction: int) -> None:
        """LB/RB no settings ajusta volume em passos de 5%."""
        pos = pygame.mouse.get_pos()
        for key, rect in self.layout_rects["sliders"].items():
            if rect.inflate(40, 30).collidepoint(pos):
                self.sliders[key] = max(
                    0.0, min(1.0, self.sliders[key] + direction * 0.05)
                )
                self._update_volume(key)
                self.preferences.save()
                return

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

    def _apply_live_control_settings(self) -> None:
        """Aplica mouse_control/auto_fire/gamepad_enabled imediatamente no runtime."""
        if self._app is None:
            return

        # Sincroniza preferências em memória do app.
        self._app.preferences.mouse_control = self.preferences.mouse_control
        self._app.preferences.auto_fire = self.preferences.auto_fire
        self._app.preferences.gamepad_enabled = self.preferences.gamepad_enabled
        self._app.preferences.p1_prefers_keyboard = self.preferences.p1_prefers_keyboard

        # Sincroniza sistema de input global.
        self._app.input.mouse_control = self.preferences.mouse_control
        self._app.input.auto_fire = self.preferences.auto_fire

        # Liga/desliga gamepad em tempo real sem precisar reiniciar.
        gamepad = getattr(self._app, "gamepad", None)
        if gamepad is not None:
            gamepad.set_enabled(self.preferences.gamepad_enabled)
            gamepad.set_primary_keyboard_preference(
                self.preferences.p1_prefers_keyboard
            )

        # Se houver cena de gameplay ativa por baixo (abrindo settings via pause),
        # atualiza também a nave existente sem exigir reinício.
        runtime_ship = getattr(self._runtime_scene, "ship", None)
        if runtime_ship is not None:
            runtime_ship.mouse_control = self.preferences.mouse_control
            runtime_ship.auto_fire = self.preferences.auto_fire
            runtime_ship.auto_fire_timer = 0.0

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
        if self.info_popup_text is not None:
            self._draw_info_popup(surface)

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

        # Instruções de controles na coluna da esquerda.
        gamepad_active = (
            self._app.gamepad.is_active
            if (self._app is not None and hasattr(self._app, "gamepad"))
            else False
        )
        if gamepad_active:
            instructions = [
                "CONTROLES:",
                "• LS: Mover",
                "• RT: Atirar | X: Girar",
                "• LT: Dash/Charge | D-pad+LB/RB: Poderes",
                "• START: Pausar | BACK: Sair",
                "",
                "DICA: Ative 'P1 no teclado / P2 no controle'",
                "para deixar o controle livre para o segundo jogador.",
            ]
        else:
            instructions = [
                "CONTROLES:",
                "• Mouse ou WASD/Setas: Mover",
                "• Espaço: Atirar | Ctrl: Girar",
                "• Shift: Dash | Teclado Num: Poderes",
                "• P: Pausar | ESC: Sair",
                "",
                "DICA: Ative 'P1 no teclado / P2 no controle'",
                "para usar o controle no segundo jogador.",
            ]

        slider_bottom = max(
            (
                slider_rect.bottom
                for slider_rect in self.layout_rects["sliders"].values()
            ),
            default=card_rect.y + 80,
        )
        instruction_start_y = slider_bottom + 18 + offset_y
        instruction_x = card_rect.x + 30
        instruction_max_width = card_rect.width - 60
        instruction_font = self.small_font
        for line in instructions:
            if line == "":
                instruction_start_y += 8
                continue
            color = CUSTOM_GOLD if ":" in line or "DICA" in line else colors.WHITE
            wrapped_lines = wrap_text(instruction_font, line, instruction_max_width)
            for wrapped_line in wrapped_lines:
                text_surf = instruction_font.render(wrapped_line, True, color)
                text_surf.set_alpha(alpha)
                surface.blit(text_surf, (instruction_x, instruction_start_y))
                instruction_start_y += 18

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
        labels = {
            "p1_prefers_keyboard": "P1 no teclado / P2 no controle",
            "mouse_control": "Controle por Mouse",
            "auto_fire": "Tiro Automático",
            "gamepad_enabled": "Controle Xbox",
        }
        gamepad = getattr(self._app, "gamepad", None) if self._app is not None else None
        gamepad_connected = bool(gamepad is not None and gamepad.connected)
        # Contadores reais por slot — refletem estado pós-fix do add_device.
        slot0_active = bool(gamepad is not None and gamepad.is_slot_connected(0))
        slot1_active = bool(gamepad is not None and gamepad.is_slot_connected(1))
        physical_count = (
            int(pygame.joystick.get_count()) if pygame.joystick.get_init() else 0
        )
        coop_active = self._is_runtime_coop_active()

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

            # Label (com sufixo de status para os toggles de gamepad)
            label_text = labels[key]
            label_color = colors.WHITE
            if key == "gamepad_enabled":
                if not gamepad_connected:
                    suffix = " (desconectado)"
                    label_color = colors.GRAY
                elif slot0_active and slot1_active:
                    suffix = " (2 controles — P1 + P2)"
                else:
                    suffix = " (1 controle conectado)"
                label_text += suffix
            elif key == "p1_prefers_keyboard":
                # Sinaliza quando há controle físico ocioso por causa desta
                # preferência (fix do add_device: prefer_slot_1 + 2 ctrls
                # deixa o 2º controle de fora pra preservar teclado em slot 0).
                used = (1 if slot0_active else 0) + (1 if slot1_active else 0)
                if is_checked and physical_count > used:
                    suffix = f" ({physical_count - used} controle ocioso)"
                    label_text += suffix
            if coop_active and key in ("gamepad_enabled", "p1_prefers_keyboard"):
                label_text += " (bloqueado em coop)"
                label_color = colors.GRAY
            label_surf = self.item_font.render(label_text, True, label_color)
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

        message_text = (
            "As alterações só serão vistas ao reiniciar o jogo. "
            "Deseja fazer isso agora?"
        )
        text_max_width = popup_rect.width - 60
        message_lines = wrap_text(self.item_font, message_text, text_max_width)

        line_height = self.item_font.get_linesize()
        line_gap = 4
        block_height = (len(message_lines) * line_height) + (
            max(0, len(message_lines) - 1) * line_gap
        )
        message_top = popup_rect.y + 60
        message_bottom = self.layout_rects["popup_yes_button"].y - 12
        available_height = max(0, message_bottom - message_top)

        if block_height > available_height:
            # Fallback para garantir que nunca estoure verticalmente.
            msg_font = self.small_font
            line_height = msg_font.get_linesize()
            message_lines = wrap_text(msg_font, message_text, text_max_width)
            block_height = (len(message_lines) * line_height) + (
                max(0, len(message_lines) - 1) * line_gap
            )
        else:
            msg_font = self.item_font

        y_offset = message_top + max(0, (available_height - block_height) // 2)
        for line in message_lines:
            text_surf = msg_font.render(line, True, colors.WHITE)
            surface.blit(
                text_surf, (popup_rect.centerx - text_surf.get_width() // 2, y_offset)
            )
            y_offset += line_height + line_gap

        self._draw_button(
            surface, self.layout_rects["popup_yes_button"], "Sim", colors.RED, 255, 0
        )
        self._draw_button(
            surface, self.layout_rects["popup_no_button"], "Não", CUSTOM_PURPLE, 255, 0
        )

    def _draw_info_popup(self, surface: pygame.Surface):
        """Desenha popup informativo (1 botão OK) — usado para bloqueios mid-coop."""
        popup_rect = self.layout_rects["popup_rect"]
        message = self.info_popup_text or ""

        overlay = pygame.Surface((surface.get_width(), surface.get_height()))
        overlay.fill((0, 0, 0))
        overlay.set_alpha(128)
        surface.blit(overlay, (0, 0))

        pygame.draw.rect(surface, colors.DARK_GRAY, popup_rect, border_radius=10)
        pygame.draw.rect(surface, CUSTOM_GOLD, popup_rect, 2, border_radius=10)

        title_surf = self.header_font.render("Aviso", True, CUSTOM_GOLD)
        surface.blit(
            title_surf,
            (popup_rect.centerx - title_surf.get_width() // 2, popup_rect.y + 20),
        )

        text_max_width = popup_rect.width - 60
        message_lines = wrap_text(self.item_font, message, text_max_width)

        line_height = self.item_font.get_linesize()
        line_gap = 4
        block_height = (len(message_lines) * line_height) + (
            max(0, len(message_lines) - 1) * line_gap
        )
        message_top = popup_rect.y + 60
        message_bottom = self.layout_rects["info_popup_ok_button"].y - 12
        available_height = max(0, message_bottom - message_top)

        if block_height > available_height:
            msg_font = self.small_font
            line_height = msg_font.get_linesize()
            message_lines = wrap_text(msg_font, message, text_max_width)
            block_height = (len(message_lines) * line_height) + (
                max(0, len(message_lines) - 1) * line_gap
            )
        else:
            msg_font = self.item_font

        y_offset = message_top + max(0, (available_height - block_height) // 2)
        for line in message_lines:
            text_surf = msg_font.render(line, True, colors.WHITE)
            surface.blit(
                text_surf, (popup_rect.centerx - text_surf.get_width() // 2, y_offset)
            )
            y_offset += line_height + line_gap

        self._draw_button(
            surface, self.layout_rects["info_popup_ok_button"], "OK", CUSTOM_PURPLE, 255, 0
        )


class SettingsScene(Scene, FadeTransitionMixin):
    """Cena de configurações."""

    def __init__(
        self,
        app: "GameApp",
        return_to_game: bool = False,
        runtime_scene: Any = None,
    ):
        super().__init__(app)
        self.return_to_game = return_to_game
        self.r = app.renderer
        self.view = SettingsView(
            on_back=self._on_back,
            renderer=self.r,
            app=app,
            runtime_scene=runtime_scene,
        )
        self._init_transition(duration=0.3)

    def enter(self):
        pygame.mouse.set_visible(True)
        self.view.reset()

    def exit(self):
        self.view.preferences.save()
        self.view.player_profile.save()

    def handle_event(self, event: pygame.event.Event):
        self.view.handle_event(event)

    def get_focusable_rects(self) -> list[pygame.Rect]:
        # Quando popup de reinício está aberto, foco fica restrito aos
        # botões dele — bloqueia DPad de vazar pra controles atrás.
        if self.view.info_popup_text is not None:
            return [self.view.layout_rects["info_popup_ok_button"]]
        if self.view.show_restart_popup:
            return [
                self.view.layout_rects["popup_yes_button"],
                self.view.layout_rects["popup_no_button"],
            ]
        rects: list[pygame.Rect] = []
        from typing import List, cast

        for r in cast(
            List[pygame.Rect], self.view.layout_rects.get("resolution_buttons", [])
        ):
            rects.append(r)
        # Toggles e sliders viram alvos do DPad. Inflo o toggle horizontalmente
        # pra cobrir o rótulo (mesmo padrão do _activate_at).
        for r in self.view.layout_rects.get("toggles", {}).values():
            rects.append(r.inflate(60, 0))
        for r in self.view.layout_rects.get("sliders", {}).values():
            rects.append(r)
        if "back_button" in self.view.layout_rects:
            rects.append(self.view.layout_rects["back_button"])
        return rects

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
        render_with_fade(
            surface,
            self.view,
            self.r.starfield,
            self.transitioning,
            self.fade_out,
            self.transition_progress,
            BLACK,
        )
