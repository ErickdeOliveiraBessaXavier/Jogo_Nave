from typing import TYPE_CHECKING, Any, Callable, Dict

import pygame

from ..core import colors
from ..core.assets import get_font
from ..core.colors import BLACK, CUSTOM_GOLD, CUSTOM_PURPLE
from ..core.i18n import t
from ..core.meta_progression import PlayerProfile
from ..core.paths import get_preferences_path, get_profile_path
from ..core.preferences import UserPreferences
from ..core.sound import sound_manager
from ..core.state import Scene
from .ui_helpers import (
    CONFIRM_KEYS,
    get_fade_scratch,
    wrap_text,
    draw_bordered_button,
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

        # As preferências do app são as MESMAS que esta tela edita — não uma
        # cópia. Construir um `UserPreferences` próprio aqui criava dois
        # objetos sobre o mesmo arquivo: a tela mexia no dela (e salvava), o
        # resto do jogo continuava lendo o do app com o valor antigo, e
        # qualquer `app.preferences.save()` posterior (ex.: hot-plug de
        # controle) regravava o valor velho por cima do escolhido.
        self.preferences = (
            app.preferences
            if app is not None and getattr(app, "preferences", None) is not None
            else UserPreferences(get_preferences_path())
        )
        self.player_profile = PlayerProfile(get_profile_path())

        # Escala de UI (convenções do projeto §12). Esta View não é uma Scene, mantém o
        # próprio fator/helper.
        from ..core.config import config as Config

        self.ui_scale = Config.SCREEN_WIDTH / 1280.0

        # Fonts
        self.title_font = get_font(max(8, int(36 * self.ui_scale)))
        self.header_font = get_font(max(8, int(18 * self.ui_scale)))
        self.item_font = get_font(max(8, int(16 * self.ui_scale)))
        self.small_font = get_font(max(8, int(13 * self.ui_scale)))
        self.percent_font = get_font(max(8, int(13 * self.ui_scale)))

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
            "touch_mode": self.preferences.touch_mode,
            "virtual_joystick": self.preferences.virtual_joystick,
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

        # Qualidade visual: seletor de 3 níveis (aplicado ao vivo, sem reinício).
        self.quality_levels: list[tuple[str, str]] = [
            ("high", "Alto"),
            ("medium", "Médio"),
            ("low", "Baixo"),
        ]
        self.selected_quality: str = self.preferences.visual_quality

        # Pixelização (pós-processamento): seletor Off/Leve/Médio/Forte,
        # aplicado ao vivo. Rótulos vêm da fonte única em visual_quality.
        from ..core.visual_quality import PIXELIZATION_LEVELS

        self.pixelization_levels: list[tuple[str, str]] = list(PIXELIZATION_LEVELS)
        self.selected_pixelization: str = self.preferences.pixelization

        # Fundo retrô (meia-resolução): seletor Ligado/Desligado, aplicado ao vivo.
        self.retro_bg_levels: list[tuple[bool, str]] = [(True, "on"), (False, "off")]
        self.selected_retro_bg: bool = self.preferences.retro_background

        # Animações da UI: seletor Ligado/Desligado (desempenho).
        self.ui_anim_levels: list[tuple[bool, str]] = [(True, "on"), (False, "off")]
        self.selected_ui_anim: bool = self.preferences.ui_animations

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

    def _s(self, value: float) -> int:
        """Escala um valor de pixel do design base (1280×720)."""
        return int(value * self.ui_scale)

    def _calculate_layout(self):
        from ..core.config import config as Config

        screen_w, screen_h = Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT

        # Dimensões e espaçamentos
        outer_pad = self._s(40)
        card_gap = self._s(30)
        card_inner_pad_x = self._s(25)

        # Calcular larguras assimétricas para dar mais espaço ao card de Controles (que possui textos longos)
        available_width = screen_w - (2 * outer_pad)
        audio_width = self._s(320)
        video_width = self._s(350)
        controls_width = available_width - audio_width - video_width - (2 * card_gap)
        card_height = screen_h - self._s(180)

        # Centralizar cards verticalmente
        card_y = (screen_h - card_height) // 2 - self._s(15)

        # Card de Áudio (Esquerda)
        audio_card_rect = pygame.Rect(outer_pad, card_y, audio_width, card_height)
        self.layout_rects["audio_card"] = audio_card_rect

        self.layout_rects["sliders"] = {}
        slider_w = audio_width - (2 * card_inner_pad_x)
        slider_h = self._s(20)
        # Mais espaçamento vertical para preencher o card harmoniosamente, já que não temos texto de dica nele
        y_offset = audio_card_rect.y + self._s(110)

        for key in ["music", "sfx", "shot"]:
            self.layout_rects["sliders"][key] = pygame.Rect(
                audio_card_rect.x + card_inner_pad_x, y_offset, slider_w, slider_h
            )
            y_offset += self._s(110)

        # Card de Controles (Meio)
        controls_x = outer_pad + audio_width + card_gap
        controls_card_rect = pygame.Rect(
            controls_x, card_y, controls_width, card_height
        )
        self.layout_rects["controls_card"] = controls_card_rect

        # Toggles de controle
        self.layout_rects["toggles"] = {}
        toggle_w, toggle_h = self._s(26), self._s(26)
        y_offset = controls_card_rect.y + self._s(70)

        # Agrupar toggles
        for key in [
            "p1_prefers_keyboard",
            "mouse_control",
            "auto_fire",
            "touch_mode",
            "virtual_joystick",
            "gamepad_enabled",
        ]:
            self.layout_rects["toggles"][key] = pygame.Rect(
                controls_card_rect.x + card_inner_pad_x, y_offset, toggle_w, toggle_h
            )
            y_offset += self._s(45)

        # Card de Vídeo/Gráficos (Direita)
        video_x = controls_x + controls_width + card_gap
        video_card_rect = pygame.Rect(
            video_x, card_y, video_width, card_height
        )
        self.layout_rects["video_card"] = video_card_rect

        # Elementos do Card de Vídeo/Gráficos:
        # 1. Seletor de Resolução
        y_offset = video_card_rect.y + self._s(60)
        self.layout_rects["resolution_label"] = pygame.Rect(
            video_card_rect.x + card_inner_pad_x,
            y_offset,
            video_card_rect.width - (2 * card_inner_pad_x),
            self._s(25),
        )

        # Grid de botões de resolução (3 colunas, 4 linhas)
        self.layout_rects["resolution_buttons"] = []
        cols = 3
        button_gap_x = self._s(8)
        button_gap_y = self._s(8)
        available_width_for_buttons = video_card_rect.width - (2 * card_inner_pad_x)
        button_w = (available_width_for_buttons - (cols - 1) * button_gap_x) / cols
        button_h = self._s(28)

        grid_start_y = y_offset + self._s(30)
        from typing import List, cast
        resolution_buttons = cast(
            List[pygame.Rect], self.layout_rects["resolution_buttons"]
        )

        for i in range(len(self.available_resolutions)):
            row = i // cols
            col = i % cols
            x = (
                video_card_rect.x
                + card_inner_pad_x
                + col * (button_w + button_gap_x)
            )
            y = grid_start_y + row * (button_h + button_gap_y)
            resolution_buttons.append(pygame.Rect(x, y, button_w, button_h))

        # Fim do grid de resoluções.
        # Agora vamos posicionar os seletores de qualidade, pixelização e fundo retrô abaixo do grid
        y_offset = grid_start_y + 4 * (button_h + button_gap_y) + self._s(15)

        # 2. Seletor de Fundo Retrô (Ligado/Desligado)
        self.layout_rects["retro_bg_label"] = pygame.Rect(
            video_card_rect.x + card_inner_pad_x,
            y_offset,
            video_card_rect.width - (2 * card_inner_pad_x),
            self._s(22),
        )
        y_offset += self._s(24)

        rb_btn_w = (available_width_for_buttons - button_gap_x) / 2
        rb_btn_h = self._s(28)
        retro_bg_buttons: list[pygame.Rect] = []
        bx = video_card_rect.x + card_inner_pad_x
        for _i in range(2):
            retro_bg_buttons.append(pygame.Rect(bx, y_offset, rb_btn_w, rb_btn_h))
            bx += rb_btn_w + button_gap_x
        self.layout_rects["retro_bg_buttons"] = retro_bg_buttons

        y_offset += rb_btn_h + self._s(15)

        # 3. Seletor de Pixelização (Leve/Médio/Forte)
        self.layout_rects["pixelization_label"] = pygame.Rect(
            video_card_rect.x + card_inner_pad_x,
            y_offset,
            video_card_rect.width - (2 * card_inner_pad_x),
            self._s(22),
        )
        y_offset += self._s(24)

        p_btn_w = (available_width_for_buttons - 2 * button_gap_x) / 3
        p_btn_h = self._s(28)
        pixelization_buttons: list[pygame.Rect] = []
        bx = video_card_rect.x + card_inner_pad_x
        for _i in range(len(self.pixelization_levels)):
            pixelization_buttons.append(pygame.Rect(bx, y_offset, p_btn_w, p_btn_h))
            bx += p_btn_w + button_gap_x
        self.layout_rects["pixelization_buttons"] = pixelization_buttons

        y_offset += p_btn_h + self._s(15)

        # 4. Seletor de Qualidade Visual (Alto/Médio/Baixo)
        self.layout_rects["quality_label"] = pygame.Rect(
            video_card_rect.x + card_inner_pad_x,
            y_offset,
            video_card_rect.width - (2 * card_inner_pad_x),
            self._s(22),
        )
        y_offset += self._s(24)

        q_btn_w = p_btn_w
        q_btn_h = self._s(28)
        quality_buttons: list[pygame.Rect] = []
        bx = video_card_rect.x + card_inner_pad_x
        for _i in range(3):
            quality_buttons.append(pygame.Rect(bx, y_offset, q_btn_w, q_btn_h))
            bx += q_btn_w + button_gap_x
        self.layout_rects["quality_buttons"] = quality_buttons

        y_offset += q_btn_h + self._s(15)

        # 5. Seletor de Animações da UI (Ligado/Desligado)
        self.layout_rects["ui_anim_label"] = pygame.Rect(
            video_card_rect.x + card_inner_pad_x,
            y_offset,
            video_card_rect.width - (2 * card_inner_pad_x),
            self._s(22),
        )
        y_offset += self._s(24)

        ua_btn_w = (available_width_for_buttons - button_gap_x) / 2
        ua_btn_h = self._s(28)
        ui_anim_buttons: list[pygame.Rect] = []
        bx = video_card_rect.x + card_inner_pad_x
        for _i in range(2):
            ui_anim_buttons.append(pygame.Rect(bx, y_offset, ua_btn_w, ua_btn_h))
            bx += ua_btn_w + button_gap_x
        self.layout_rects["ui_anim_buttons"] = ui_anim_buttons

        # Botão de Voltar (Canto inferior esquerdo)
        back_text_width = self.item_font.size(t("common.back"))[0]
        back_btn_width = back_text_width + self._s(60)
        self.layout_rects["back_button"] = pygame.Rect(
            outer_pad, screen_h - self._s(60), back_btn_width, self._s(40)
        )

        # Pop-up de confirmação (Centralizado na tela)
        popup_w, popup_h = self._s(500), self._s(220)
        popup_x = (screen_w - popup_w) // 2
        popup_y = (screen_h - popup_h) // 2
        self.layout_rects["popup_rect"] = pygame.Rect(
            popup_x, popup_y, popup_w, popup_h
        )

        # Botões do pop-up
        btn_w = self._s(100)
        btn_h = self._s(40)
        btn_gap = self._s(20)
        total_btn_width = (btn_w * 2) + btn_gap

        start_btn_x = popup_x + (popup_w - total_btn_width) // 2
        btn_y = popup_y + popup_h - btn_h - self._s(25)

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
        self.toggles["touch_mode"] = self.preferences.touch_mode
        self.toggles["virtual_joystick"] = self.preferences.virtual_joystick
        self.toggles["gamepad_enabled"] = self.preferences.gamepad_enabled
        self.toggles["p1_prefers_keyboard"] = self.preferences.p1_prefers_keyboard
        self.selected_quality = self.preferences.visual_quality
        self.selected_pixelization = self.preferences.pixelization
        self.selected_retro_bg = self.preferences.retro_background
        self.selected_ui_anim = self.preferences.ui_animations

        saved_res = self.preferences.resolution
        for i, (w, h, _) in enumerate(self.available_resolutions):
            if w == saved_res[0] and h == saved_res[1]:
                self.selected_resolution_index = i
                break

    def update(self, dt: float):
        """Atualiza a lógica da view."""
        from ..core.visual_quality import visual_quality

        if not visual_quality.ui_animations:
            self.entry_progress = 1.0
            self.is_entering = False
        elif self.is_entering and self.entry_progress < 1.0:
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
        if event.type == pygame.KEYDOWN and event.key in (
            pygame.K_LEFT,
            pygame.K_RIGHT,
        ):
            # Só chega aqui com a mira sobre um slider: fora dele, o app já
            # consumiu a seta para navegar (ver `arrow_keys_navigate_focus`).
            if self.slider_under_cursor() is not None:
                self._adjust_slider_under_cursor(
                    -1 if event.key == pygame.K_LEFT else 1
                )
                return True

        if event.type == pygame.KEYDOWN and event.key in CONFIRM_KEYS:
            # Enter aciona o que as setas/TAB destacaram — mesmo caminho do A do
            # controle, popups inclusive (eles são modais: precisam responder
            # antes, senão o Enter atravessaria para a tela de trás).
            if self.info_popup_text is not None:
                self.info_popup_text = None
                return True
            if self.show_restart_popup:
                pos = pygame.mouse.get_pos()
                if self.layout_rects["popup_yes_button"].collidepoint(pos):
                    self._popup_confirm()
                else:
                    # Mesmo default do A: sem mirar o "sim", fecha sem reiniciar.
                    self.show_restart_popup = False
                return True
            return self._activate_at(pygame.mouse.get_pos())

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

            # Botões de Qualidade Visual
            for i, rect in enumerate(self.layout_rects.get("quality_buttons", [])):
                if rect.collidepoint(pos):
                    self._select_quality(self.quality_levels[i][0])
                    return True

            # Botões de Pixelização
            for i, rect in enumerate(
                self.layout_rects.get("pixelization_buttons", [])
            ):
                if rect.collidepoint(pos):
                    self._select_pixelization(self.pixelization_levels[i][0])
                    return True

            for i, rect in enumerate(
                self.layout_rects.get("retro_bg_buttons", [])
            ):
                if rect.collidepoint(pos):
                    self._select_retro_bg(self.retro_bg_levels[i][0])
                    return True

            for i, rect in enumerate(
                self.layout_rects.get("ui_anim_buttons", [])
            ):
                if rect.collidepoint(pos):
                    self._select_ui_anim(self.ui_anim_levels[i][0])
                    return True

            # Toggles (clique tolerante em toda a largura do rótulo correspondente)
            for key, rect in self.layout_rects["toggles"].items():
                card_rect = self.layout_rects["controls_card"]
                click_rect = pygame.Rect(
                    rect.x,
                    rect.y,
                    card_rect.right - self._s(25) - rect.x,
                    rect.height,
                )
                if click_rect.collidepoint(pos):
                    self._flip_toggle(key)
                    return True

            # Sliders (clique verticalmente tolerante)
            for key, rect in self.layout_rects["sliders"].items():
                if rect.inflate(0, 10).collidepoint(pos):
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

    def _flip_toggle(self, key: str) -> bool:
        """Inverte um toggle de controle e aplica ao vivo. Caminho ÚNICO.

        Mouse e controle chegavam aqui por dois blocos idênticos (o clique e o
        `_activate_at` do gamepad), e a regra nova de exclusão precisaria ser
        escrita duas vezes — que é como as duas cópias divergem.
        """
        if self._try_show_coop_block(key):
            return False
        if self._is_toggle_locked(key):
            self.info_popup_text = t("settings.mouse_locked_msg")
            return False

        self.toggles[key] = not self.toggles[key]
        prefs = self.preferences
        # Mexer em qualquer ajuste de controle conta como "já defini como quero
        # jogar": o modal pré-jogo para de repetir a pergunta (ver
        # `ControlsModalScene.show_quick_toggles`).
        prefs.controls_configured = True
        if key == "p1_prefers_keyboard":
            prefs.p1_prefers_keyboard = self.toggles[key]
        elif key == "mouse_control":
            prefs.mouse_control = self.toggles[key]
        elif key == "auto_fire":
            prefs.auto_fire = self.toggles[key]
        elif key == "virtual_joystick":
            prefs.virtual_joystick = self.toggles[key]
        elif key == "touch_mode":
            prefs.touch_mode = self.toggles[key]
        elif key == "gamepad_enabled":
            # Pelo setter: ligar o controle desliga o mouse (§ exclusão mútua).
            prefs.set_gamepad_enabled(self.toggles[key])
            # Escolha explícita: trava o auto-ligar do gamepad.
            prefs.gamepad_choice_made = True
            # A caixa do mouse tem de refletir o que o setter fez, no mesmo
            # frame — senão fica marcada descrevendo algo que já não vale.
            self.toggles["mouse_control"] = prefs.mouse_control

        self._apply_live_control_settings()
        prefs.save()
        return True

    def _is_toggle_locked(self, key: str) -> bool:
        """True quando o toggle está travado por outra preferência.

        Hoje só o `mouse_control`, travado pelo Modo Controle Xbox. O toggle
        continua VISÍVEL (esmaecido) em vez de sumir: uma opção que desaparece
        deixa o jogador procurando o que ele lembra de ter visto.
        """
        return key == "mouse_control" and self.preferences.mouse_control_locked

    def _try_show_coop_block(self, key: str) -> bool:
        """Se o toggle `key` é sensível e coop está ativo, mostra info popup.

        Retorna True quando o toggle foi bloqueado (o handler deve abortar
        a aplicação da mudança SEM flipar o valor).
        """
        if key not in ("gamepad_enabled", "p1_prefers_keyboard"):
            return False
        if not self._is_runtime_coop_active():
            return False
        self.info_popup_text = t("settings.coop_block_msg")
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

        for i, rect in enumerate(self.layout_rects.get("quality_buttons", [])):
            if rect.collidepoint(pos):
                self._select_quality(self.quality_levels[i][0])
                return True

        for i, rect in enumerate(self.layout_rects.get("pixelization_buttons", [])):
            if rect.collidepoint(pos):
                self._select_pixelization(self.pixelization_levels[i][0])
                return True

        for i, rect in enumerate(self.layout_rects.get("retro_bg_buttons", [])):
            if rect.collidepoint(pos):
                self._select_retro_bg(self.retro_bg_levels[i][0])
                return True

        for i, rect in enumerate(self.layout_rects.get("ui_anim_buttons", [])):
            if rect.collidepoint(pos):
                self._select_ui_anim(self.ui_anim_levels[i][0])
                return True

        for key, rect in self.layout_rects["toggles"].items():
            card_rect = self.layout_rects["controls_card"]
            click_rect = pygame.Rect(
                rect.x,
                rect.y,
                card_rect.right - self._s(25) - rect.x,
                rect.height,
            )
            if click_rect.collidepoint(pos):
                self._flip_toggle(key)
                return True

        # Slider: A em cima do slider seta o valor pra posição da mira.
        for key, rect in self.layout_rects["sliders"].items():
            if rect.inflate(0, 10).collidepoint(pos):
                new_val = (pos[0] - rect.x) / rect.w
                self.sliders[key] = max(0.0, min(1.0, new_val))
                self._update_volume(key)
                self.preferences.save()
                return True
        return False

    def slider_under_cursor(self) -> str | None:
        """Slider sob a mira, se houver. Mesma área de tolerância do ajuste.

        Público porque a CENA consulta (ver `SettingsScene.
        arrow_keys_navigate_focus`) para decidir se ←/→ ajustam ou navegam.
        """
        pos = pygame.mouse.get_pos()
        for key, rect in self.layout_rects.get("sliders", {}).items():
            if rect.inflate(40, 30).collidepoint(pos):
                return key
        return None

    def _adjust_slider_under_cursor(self, direction: int) -> None:
        """LB/RB (e ←/→ no teclado) ajustam o volume em passos de 5%."""
        key = self.slider_under_cursor()
        if key is None:
            return
        self.sliders[key] = max(0.0, min(1.0, self.sliders[key] + direction * 0.05))
        self._update_volume(key)
        self.preferences.save()

    def _select_quality(self, name: str) -> None:
        """Aplica o nível de qualidade visual ao vivo (sem reinício) e persiste."""
        from ..core.visual_quality import visual_quality

        self.selected_quality = name
        self.preferences.visual_quality = name
        visual_quality.set_from_name(name)
        self.preferences.save()

    def _select_pixelization(self, name: str) -> None:
        """Aplica a intensidade de pixelização ao vivo (sem reinício) e persiste."""
        from ..core.visual_quality import visual_quality

        self.selected_pixelization = name
        self.preferences.pixelization = name
        visual_quality.set_pixelization(name)
        self.preferences.save()

    def _select_retro_bg(self, enabled: bool) -> None:
        """Liga/desliga o fundo retrô (meia-resolução) ao vivo e persiste.

        O background do tema é construído já na resolução final, então mudar a
        opção exige reconstruí-lo — `refresh_background_quality` faz isso no
        tema ativo (no-op no menu/starfield). A tela de seleção de mundos se
        adapta sozinha: o memo dela é chaveado pelas dims de construção.
        """
        from ..core.visual_quality import visual_quality

        self.selected_retro_bg = enabled
        self.preferences.retro_background = enabled
        visual_quality.set_lowres_background(enabled)
        if self.renderer is not None:
            self.renderer.refresh_background_quality()
        self.preferences.save()

    def _select_ui_anim(self, enabled: bool) -> None:
        """Liga/desliga as animações da UI e persiste (aplicado ao vivo)."""
        from ..core.visual_quality import visual_quality

        self.selected_ui_anim = enabled
        self.preferences.ui_animations = enabled
        visual_quality.set_ui_animations(enabled)
        self.preferences.save()

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

        # Sem cópia campo a campo para o app: `self.preferences` **é**
        # `app.preferences` (mesma instância, ver o construtor e §18). O bloco
        # que existia aqui atribuía cada campo a si mesmo — e uma dessas linhas
        # escrevia `gamepad_enabled` cru, por fora do `set_gamepad_enabled`, que
        # é onde mora a exclusão com o mouse.

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
            runtime_ship.touch_offset = self.preferences.touch_mode

    def render(self, surface: pygame.Surface):
        """Renderiza a view."""
        # Calcular alpha baseado no progresso
        alpha = int(255 * self.entry_progress)
        offset_y = int(self._s(30) * (1.0 - self.entry_progress))

        # Título
        title_surf = self.title_font.render(t("common.settings"), True, CUSTOM_GOLD)
        title_surf.set_alpha(alpha)
        # Centralizar título
        title_x = (surface.get_width() - title_surf.get_width()) // 2
        surface.blit(title_surf, (title_x, self._s(20) + offset_y))

        # Desenhar Cards com alpha
        self._draw_audio_card(surface, alpha, offset_y)
        self._draw_controls_card(surface, alpha, offset_y)
        self._draw_video_card(surface, alpha, offset_y)

        # Botão Voltar com alpha
        self._draw_button(
            surface,
            self.layout_rects["back_button"],
            t("common.back"),
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

    def _draw_video_card(
        self, surface: pygame.Surface, alpha: int = 255, offset_y: int = 0
    ):
        """Desenha o card de vídeo contendo a resolução e os seletores gráficos."""
        card_rect = self.layout_rects["video_card"].copy()
        card_rect.y += offset_y
        self._draw_card(
            surface,
            self.layout_rects["video_card"],
            t("settings.video_title"),
            alpha,
            offset_y,
        )

        # Criar clipping para o card
        clip_inset = self._s(10)
        clip_rect = card_rect.inflate(-clip_inset, -clip_inset)
        surface.set_clip(clip_rect)

        # Label da resolução
        label_rect = self.layout_rects["resolution_label"]
        label_surf = self.item_font.render(t("settings.resolution_label"), True, CUSTOM_GOLD)
        label_surf.set_alpha(alpha)
        surface.blit(label_surf, (label_rect.x, label_rect.y + offset_y))

        # Botões de resolução
        from typing import List, cast

        resolution_buttons = cast(
            List[pygame.Rect], self.layout_rects["resolution_buttons"]
        )
        for i, (w, h, label) in enumerate(self.available_resolutions):
            button_rect = resolution_buttons[i]
            is_selected = i == self.selected_resolution_index
            color = CUSTOM_GOLD if is_selected else CUSTOM_PURPLE

            self._draw_button(
                surface,
                button_rect,
                label,
                color,
                alpha,
                offset_y,
            )

        # Seletores gráficos internos
        self._draw_retro_bg_selector(surface, alpha, offset_y)
        self._draw_pixelization_selector(surface, alpha, offset_y)
        self._draw_quality_selector(surface, alpha, offset_y)
        self._draw_ui_anim_selector(surface, alpha, offset_y)

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
            tooltip_y = mouse_y - self._s(35)

            tooltip_x = max(
                self._s(10),
                min(tooltip_x, Config.SCREEN_WIDTH - tooltip_surf.get_width() - self._s(10)),
            )
            tooltip_y = max(self._s(10), tooltip_y)

            bg_rect = pygame.Rect(
                tooltip_x - self._s(5),
                tooltip_y - self._s(3),
                tooltip_surf.get_width() + self._s(10),
                tooltip_surf.get_height() + self._s(6),
            )
            bg_surf = pygame.Surface((bg_rect.width, bg_rect.height))
            bg_surf.fill(BLACK)
            bg_surf.set_alpha(int(alpha * 0.7))
            surface.blit(bg_surf, bg_rect)

            surface.blit(tooltip_surf, (tooltip_x, tooltip_y))

        surface.set_clip(None)

    def _draw_quality_selector(
        self, surface: pygame.Surface, alpha: int = 255, offset_y: int = 0
    ):
        """Desenha o seletor 'Qualidade Visual:' com o nível ativo."""
        label_rect = self.layout_rects["quality_label"]
        label_surf = self.item_font.render(t("settings.quality_label"), True, CUSTOM_GOLD)
        label_surf.set_alpha(alpha)
        surface.blit(
            label_surf,
            (label_rect.x, label_rect.y + offset_y),
        )

        buttons = self.layout_rects["quality_buttons"]
        for i, rect in enumerate(buttons):
            name, _label = self.quality_levels[i]
            is_selected = name == self.selected_quality
            color = CUSTOM_GOLD if is_selected else CUSTOM_PURPLE
            self._draw_button(
                surface, rect, t(f"settings.quality.{name}"), color, alpha, offset_y
            )

    def _draw_pixelization_selector(
        self, surface: pygame.Surface, alpha: int = 255, offset_y: int = 0
    ):
        """Desenha o seletor 'Pixelização:' com o nível ativo em destaque."""
        label_rect = self.layout_rects["pixelization_label"]
        label_surf = self.item_font.render(t("settings.pixelization_label"), True, CUSTOM_GOLD)
        label_surf.set_alpha(alpha)
        surface.blit(
            label_surf,
            (label_rect.x, label_rect.y + offset_y),
        )

        buttons = self.layout_rects["pixelization_buttons"]
        for i, rect in enumerate(buttons):
            name, _label = self.pixelization_levels[i]
            is_selected = name == self.selected_pixelization
            color = CUSTOM_GOLD if is_selected else CUSTOM_PURPLE
            self._draw_button(
                surface, rect, t(f"settings.pixelization.{name}"), color, alpha, offset_y
            )

    def _draw_retro_bg_selector(
        self, surface: pygame.Surface, alpha: int = 255, offset_y: int = 0
    ):
        """Desenha o seletor 'Fundo Retrô:' (Ligado/Desligado)."""
        label_rect = self.layout_rects["retro_bg_label"]
        label_surf = self.item_font.render(
            t("settings.retro_bg_label"), True, CUSTOM_GOLD
        )
        label_surf.set_alpha(alpha)
        surface.blit(
            label_surf,
            (label_rect.x, label_rect.y + offset_y),
        )

        buttons = self.layout_rects["retro_bg_buttons"]
        for i, rect in enumerate(buttons):
            value, key = self.retro_bg_levels[i]
            is_selected = value == self.selected_retro_bg
            color = CUSTOM_GOLD if is_selected else CUSTOM_PURPLE
            self._draw_button(
                surface, rect, t(f"settings.retro_bg.{key}"), color, alpha, offset_y
            )

    def _draw_ui_anim_selector(
        self, surface: pygame.Surface, alpha: int = 255, offset_y: int = 0
    ):
        """Desenha o seletor 'Animações:' (Ligado/Desligado)."""
        label_rect = self.layout_rects["ui_anim_label"]
        label_surf = self.item_font.render(
            t("settings.ui_anim_label"), True, CUSTOM_GOLD
        )
        label_surf.set_alpha(alpha)
        surface.blit(
            label_surf,
            (label_rect.x, label_rect.centery - label_surf.get_height() // 2 + offset_y),
        )
        buttons = self.layout_rects["ui_anim_buttons"]
        for i, rect in enumerate(buttons):
            value, key = self.ui_anim_levels[i]
            is_selected = value == self.selected_ui_anim
            color = CUSTOM_GOLD if is_selected else CUSTOM_PURPLE
            self._draw_button(
                surface, rect, t(f"settings.ui_anim.{key}"), color, alpha, offset_y
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
            border_radius=self._s(8),
        )
        surface.blit(temp_surface, (adjusted_rect.x - 1, adjusted_rect.y - 1))

        title_surf = self.header_font.render(title, True, CUSTOM_GOLD)
        title_surf.set_alpha(alpha)
        surface.blit(title_surf, (adjusted_rect.x + self._s(15), adjusted_rect.y + self._s(15)))

    def _draw_audio_card(
        self, surface: pygame.Surface, alpha: int = 255, offset_y: int = 0
    ):
        card_rect = self.layout_rects["audio_card"].copy()
        card_rect.y += offset_y
        self._draw_card(
            surface, self.layout_rects["audio_card"], t("settings.audio_title"), alpha, offset_y
        )

        labels = {
            "music": t("settings.audio.music"),
            "sfx": t("settings.audio.sfx"),
            "shot": t("settings.audio.shot"),
        }

        # Criar clipping para o card
        clip_inset = self._s(10)
        clip_rect = card_rect.inflate(-clip_inset, -clip_inset)
        surface.set_clip(clip_rect)

        slider_radius = self._s(10)
        for key in self.sliders:
            rect = self.layout_rects["sliders"][key].copy()
            rect.y += offset_y

            # Label
            # Detecta hover com tolerância vertical para acender o label correspondente
            is_hovered = rect.inflate(0, 16).collidepoint(pygame.mouse.get_pos())
            label_color = CUSTOM_GOLD if is_hovered else colors.WHITE
            label_surf = self.item_font.render(labels[key], True, label_color)
            label_surf.set_alpha(alpha)
            surface.blit(label_surf, (rect.x, rect.y - self._s(30)))

            # Slider
            val = self.sliders[key]
            # Barra de fundo
            temp_bg = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            pygame.draw.rect(
                temp_bg, (10, 10, 10, alpha), temp_bg.get_rect(), border_radius=slider_radius
            )
            surface.blit(temp_bg, rect.topleft)

            # Barra de preenchimento
            fill_width = val * rect.width
            fill_rect = pygame.Rect(0, 0, fill_width, rect.height)
            temp_fill = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            pygame.draw.rect(
                temp_fill, (*CUSTOM_PURPLE, alpha), fill_rect, border_radius=slider_radius
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
                border_radius=slider_radius,
            )
            surface.blit(temp_border, (rect.x - 1, rect.y - 1))

            # Knob
            knob_x = rect.x + int(val * rect.w)
            knob_rect = pygame.Rect(0, 0, self._s(10), rect.height + self._s(10))
            knob_rect.center = (knob_x, rect.centery)
            temp_knob = pygame.Surface(
                (knob_rect.width + 2, knob_rect.height + 2), pygame.SRCALPHA
            )
            pygame.draw.rect(
                temp_knob,
                (*CUSTOM_GOLD, alpha),
                pygame.Rect(1, 1, knob_rect.width, knob_rect.height),
                border_radius=self._s(3),
            )
            surface.blit(temp_knob, (knob_rect.x - 1, knob_rect.y - 1))

            # Valor em %
            percent_text = f"{int(val * 100)}%"
            percent_surf = self.percent_font.render(percent_text, True, colors.GRAY)
            percent_surf.set_alpha(alpha)
            percent_x = min(
                rect.right + self._s(5),
                card_rect.right - percent_surf.get_width() - self._s(25),
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
            t("settings.controls_card_title"),
            alpha,
            offset_y,
        )

        # Criar clipping para o card
        clip_inset = self._s(10)
        clip_rect = card_rect.inflate(-clip_inset, -clip_inset)
        surface.set_clip(clip_rect)

        # Toggles
        labels = {
            "p1_prefers_keyboard": t("settings.toggle.p1_keyboard"),
            "mouse_control": t("settings.toggle.mouse"),
            "auto_fire": t("settings.toggle.auto_fire"),
            "touch_mode": t("settings.toggle.touch_mode"),
            "virtual_joystick": t("settings.toggle.joystick"),
            "gamepad_enabled": t("settings.toggle.gamepad"),
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

            # Área de colisão estendida (inclui o rótulo) para hover e clique
            click_rect = pygame.Rect(
                rect.x,
                rect.y,
                card_rect.right - self._s(25) - rect.x,
                rect.height,
            )
            locked = self._is_toggle_locked(key)
            is_hovered = (
                click_rect.collidepoint(pygame.mouse.get_pos())
                and not coop_active
                and not locked
            )

            # Checkbox
            is_checked = self.toggles[key]
            # Borda fica dourada se estiver checado ou se estiver sob hover do mouse
            checkbox_color = CUSTOM_GOLD if (is_checked or is_hovered) else colors.GRAY
            if locked:
                checkbox_color = colors.GRAY
            pygame.draw.rect(
                surface, (*checkbox_color, alpha), rect, 2, border_radius=self._s(5)
            )
            if is_checked:
                # Checkmark
                inset = self._s(6)
                check_surf = pygame.Surface((rect.width - inset, rect.height - inset))
                check_surf.fill((*CUSTOM_GOLD, alpha))
                surface.blit(check_surf, (rect.x + inset // 2, rect.y + inset // 2))

            # Label (com sufixo de status para os toggles de gamepad e quebra de linhas para evitar overflow)
            label_text = labels[key]
            label_color = colors.WHITE
            if key == "gamepad_enabled":
                if not gamepad_connected:
                    suffix = t("settings.status.disconnected")
                    label_color = colors.GRAY
                elif slot0_active and slot1_active:
                    suffix = t("settings.status.two_pads")
                else:
                    suffix = t("settings.status.one_pad")
                label_text += suffix
            elif key == "p1_prefers_keyboard":
                # Sinaliza quando há controle físico ocioso por causa desta
                # preferência (fix do add_device: prefer_slot_1 + 2 ctrls
                # deixa o 2º controle de fora pra preservar teclado em slot 0).
                used = (1 if slot0_active else 0) + (1 if slot1_active else 0)
                if is_checked and physical_count > used:
                    suffix = t("settings.status.idle_pad", n=physical_count - used)
                    label_text += suffix
            if coop_active and key in ("gamepad_enabled", "p1_prefers_keyboard"):
                label_text += t("settings.status.coop_locked")
                label_color = colors.GRAY
            if locked:
                # Só esmaece — SEM sufixo no rótulo. A linha tem 45px de passo
                # fixo e o rótulo já quebra em duas linhas; um "(desligado pelo
                # Controle Xbox)" empurrava para três e escrevia por cima do
                # toggle de baixo. O porquê é dito no popup ao tentar marcar.
                label_color = colors.GRAY

            # Mudar a cor do texto para dourado se passar o mouse sobre ele (e não estiver desabilitado)
            if is_hovered and label_color == colors.WHITE:
                label_color = CUSTOM_GOLD

            # Quebra de texto inteligente para acomodar labels longos sem overflow
            max_text_width = card_rect.right - self._s(25) - rect.right - self._s(10)
            wrapped_lines = wrap_text(self.item_font, label_text, max_text_width)
            line_height = self.item_font.get_linesize()
            total_text_height = len(wrapped_lines) * line_height
            text_y = rect.centery - total_text_height // 2

            for line in wrapped_lines:
                label_surf = self.item_font.render(line, True, label_color)
                label_surf.set_alpha(alpha)
                surface.blit(label_surf, (rect.right + self._s(10), text_y))
                text_y += line_height

        # Instruções de controles na coluna do meio (Controles)
        gamepad_active = (
            self._app.gamepad.is_active
            if (self._app is not None and hasattr(self._app, "gamepad"))
            else False
        )
        if gamepad_active:
            instructions = [
                t("settings.controls_header"),
                t("controls.gp.move"),
                t("settings.gp.shoot_rotate"),
                t("settings.gp.dash_powers"),
                t("controls.gp.pause"),
                "",
                t("settings.tip"),
                t("settings.tip_gamepad"),
            ]
        else:
            instructions = [
                t("settings.controls_header"),
                t("settings.kb.move"),
                t("settings.kb.shoot_rotate"),
                t("settings.kb.dash_powers"),
                t("controls.kb.pause"),
                "",
                t("settings.tip"),
                t("settings.tip_keyboard"),
            ]

        toggle_bottom = max(
            (
                rect.bottom
                for rect in self.layout_rects["toggles"].values()
            ),
            default=card_rect.y + self._s(70),
        )
        instruction_start_y = toggle_bottom + self._s(30) + offset_y
        instruction_x = card_rect.x + self._s(25)
        instruction_max_width = card_rect.width - self._s(50)
        instruction_font = self.small_font
        instruction_lh = self._s(18)
        for line in instructions:
            if line == "":
                instruction_start_y += self._s(8)
                continue
            color = CUSTOM_GOLD if ":" in line or "DICA" in line or "TIP" in line else colors.WHITE
            wrapped_lines = wrap_text(instruction_font, line, instruction_max_width)
            for wrapped_line in wrapped_lines:
                text_surf = instruction_font.render(wrapped_line, True, color)
                text_surf.set_alpha(alpha)
                surface.blit(text_surf, (instruction_x, instruction_start_y))
                instruction_start_y += instruction_lh

        surface.set_clip(None)

    def _draw_restart_popup(self, surface: pygame.Surface):
        """Desenha o pop-up de confirmação para reiniciar o jogo."""
        popup_rect = self.layout_rects["popup_rect"]

        # Dim reutilizado (não aloca por frame enquanto o modal está aberto).
        overlay = get_fade_scratch(
            (surface.get_width(), surface.get_height()), per_pixel_alpha=False
        )
        overlay.fill((0, 0, 0))
        overlay.set_alpha(128)
        surface.blit(overlay, (0, 0))

        popup_radius = self._s(10)
        pygame.draw.rect(surface, colors.DARK_GRAY, popup_rect, border_radius=popup_radius)
        pygame.draw.rect(surface, CUSTOM_GOLD, popup_rect, 2, border_radius=popup_radius)

        title_surf = self.header_font.render(t("settings.restart_title"), True, CUSTOM_GOLD)
        surface.blit(
            title_surf,
            (popup_rect.centerx - title_surf.get_width() // 2, popup_rect.y + self._s(20)),
        )

        message_text = t("settings.restart_msg")
        text_max_width = popup_rect.width - self._s(60)
        message_lines = wrap_text(self.item_font, message_text, text_max_width)

        line_height = self.item_font.get_linesize()
        line_gap = self._s(4)
        block_height = (len(message_lines) * line_height) + (
            max(0, len(message_lines) - 1) * line_gap
        )
        message_top = popup_rect.y + self._s(60)
        message_bottom = self.layout_rects["popup_yes_button"].y - self._s(12)
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
            surface, self.layout_rects["popup_yes_button"], t("common.yes"), colors.RED, 255, 0
        )
        self._draw_button(
            surface, self.layout_rects["popup_no_button"], t("common.no"), CUSTOM_PURPLE, 255, 0
        )

    def _draw_info_popup(self, surface: pygame.Surface):
        """Desenha popup informativo (1 botão OK) — usado para bloqueios mid-coop."""
        popup_rect = self.layout_rects["popup_rect"]
        message = self.info_popup_text or ""

        # Dim reutilizado (não aloca por frame enquanto o modal está aberto).
        overlay = get_fade_scratch(
            (surface.get_width(), surface.get_height()), per_pixel_alpha=False
        )
        overlay.fill((0, 0, 0))
        overlay.set_alpha(128)
        surface.blit(overlay, (0, 0))

        popup_radius = self._s(10)
        pygame.draw.rect(surface, colors.DARK_GRAY, popup_rect, border_radius=popup_radius)
        pygame.draw.rect(surface, CUSTOM_GOLD, popup_rect, 2, border_radius=popup_radius)

        title_surf = self.header_font.render(t("settings.info_title"), True, CUSTOM_GOLD)
        surface.blit(
            title_surf,
            (popup_rect.centerx - title_surf.get_width() // 2, popup_rect.y + self._s(20)),
        )

        text_max_width = popup_rect.width - self._s(60)
        message_lines = wrap_text(self.item_font, message, text_max_width)

        line_height = self.item_font.get_linesize()
        line_gap = self._s(4)
        block_height = (len(message_lines) * line_height) + (
            max(0, len(message_lines) - 1) * line_gap
        )
        message_top = popup_rect.y + self._s(60)
        message_bottom = self.layout_rects["info_popup_ok_button"].y - self._s(12)
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
            surface, self.layout_rects["info_popup_ok_button"], t("common.ok"), CUSTOM_PURPLE, 255, 0
        )


class SettingsScene(Scene):
    """Cena de configurações.

    O fade de entrada/saída é do `SceneTransition` (global) — esta cena não
    desenha transição nenhuma.
    """

    @property
    def arrow_keys_navigate_focus(self) -> "bool | str":
        """Setas navegam — mas ←/→ viram ajuste em cima de um slider.

        Ali o eixo horizontal é do volume (o mesmo que LB/RB fazem no controle),
        e é a única forma de o teclado alcançar os sliders; ↑/↓ seguem navegando
        e tiram a mira de cima deles. Sem a exceção, a tela ganharia navegação e
        continuaria sem ajuste por teclado."""
        return "vertical" if self.view.slider_under_cursor() else True

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

    def _on_back(self) -> None:
        """Volta desempilhando — tanto vinda do menu quanto da pausa, a cena de
        origem continua viva embaixo.

        Antes fazia `switch(MainMenuScene(...))` quando vinha do menu: como
        `SettingsScene` foi EMPILHADA sobre o menu, o switch trocava as
        configurações por um menu NOVO e deixava o antigo preso embaixo. A
        pilha crescia [Menu, Menu, Menu…] a cada visita, e o menu recriado
        perdia a `view_stack` (voltava sempre para a raiz).
        """
        self.app.go_back()

    def enter(self):
        # O ponteiro NÃO é forçado a aparecer aqui: quem manda na visibilidade
        # é o modo de navegação do app (`_sync_cursor_visibility`, chamado na
        # troca de cena). Forçar `set_visible(True)` deixava o cursor na tela
        # durante a navegação por controle, e o app não o escondia de volta
        # porque, para ele, o modo não tinha mudado.
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

        # 1. Sliders (Card de Áudio - Esquerda)
        for r in self.view.layout_rects.get("sliders", {}).values():
            rects.append(r)

        # 2. Toggles (Card de Controles - Meio)
        # Inflo o toggle horizontalmente pra cobrir o rótulo (mesmo padrão do _activate_at).
        for r in self.view.layout_rects.get("toggles", {}).values():
            rects.append(r.inflate(60, 0))

        # 3. Elementos do Card de Vídeo/Gráficos (Direita)
        # Grid de Resoluções
        for r in cast(
            List[pygame.Rect], self.view.layout_rects.get("resolution_buttons", [])
        ):
            rects.append(r)
        # Fundo Retrô
        for r in cast(
            List[pygame.Rect], self.view.layout_rects.get("retro_bg_buttons", [])
        ):
            rects.append(r)
        # Pixelização
        for r in cast(
            List[pygame.Rect], self.view.layout_rects.get("pixelization_buttons", [])
        ):
            rects.append(r)
        # Qualidade Visual
        for r in cast(
            List[pygame.Rect], self.view.layout_rects.get("quality_buttons", [])
        ):
            rects.append(r)

        # 4. Botão Voltar (Inferior)
        if "back_button" in self.view.layout_rects:
            rects.append(self.view.layout_rects["back_button"])
        return rects

    def update(self, dt: float):
        self.r.starfield.update(dt)
        self.view.update(dt)

    def render(self, surface: pygame.Surface):
        surface.fill(BLACK)
        self.r.starfield.draw(surface)
        self.view.render(surface)
