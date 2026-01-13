import pygame
from typing import TYPE_CHECKING, Dict, Any, Callable

from ..core.state import Scene
from ..core import colors
from ..core.colors import CUSTOM_PURPLE, CUSTOM_GOLD, BLACK
from ..core.assets import get_font
from ..core.sound import sound_manager
from ..core.meta_progression import PlayerProfile
from ..core.paths import get_profile_path

if TYPE_CHECKING:
    from ..app import GameApp


class SettingsView:
    """View de configurações (pode ser usada dentro de outras cenas)."""

    def __init__(self, on_back: Callable[[], None], renderer: Any = None):
        """
        Args:
            on_back: Callback chamado quando o usuário quer voltar
            renderer: Renderer compartilhado (opcional)
        """
        self.on_back = on_back
        self.renderer = renderer
        self.player_profile = PlayerProfile(get_profile_path())

        # Fonts
        self.title_font = get_font(40)
        self.header_font = get_font(24)
        self.item_font = get_font(20)
        self.small_font = get_font(16)

        # Estado da UI
        self.sliders: Dict[str, float] = {
            "music": sound_manager.music_volume,
            "sfx": sound_manager.sfx_volume,
            "shot": sound_manager.shot_volume_base,
        }
        self.dragging_slider: str | None = None

        # Animação de entrada
        self.entry_progress = 0.0
        self.is_entering = True
        self.entry_duration = 0.4

        # Layout
        self.layout_rects: Dict[str, Any] = {}
        self._calculate_layout()

    def _calculate_layout(self):
        from ..core.config import config as Config

        screen_w, screen_h = Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
        pad = 20
        gap = 30  # Gap entre os cards

        # Card de Áudio
        audio_card_width = (screen_w - 2 * pad - gap) / 2
        audio_card_rect = pygame.Rect(pad, 100, audio_card_width, screen_h - 180)
        self.layout_rects["audio_card"] = audio_card_rect

        self.layout_rects["sliders"] = {}
        slider_w, slider_h = audio_card_rect.width - 40, 20
        y_offset = audio_card_rect.y + 80
        for key in self.sliders:
            self.layout_rects["sliders"][key] = pygame.Rect(
                audio_card_rect.x + 20, y_offset, slider_w, slider_h
            )
            y_offset += 100

        # Card de Controles
        controls_card_rect = pygame.Rect(
            pad + audio_card_width + gap, 100, audio_card_width, screen_h - 180
        )
        self.layout_rects["controls_card"] = controls_card_rect

        # Botão de Voltar
        self.layout_rects["back_button"] = pygame.Rect(pad, screen_h - 60, 150, 40)

    def reset(self):
        """Reseta o estado da view para reiniciar animação."""
        self.entry_progress = 0.0
        self.is_entering = True
        self.dragging_slider = None
        # Atualizar valores dos sliders
        self.sliders["music"] = sound_manager.music_volume
        self.sliders["sfx"] = sound_manager.sfx_volume
        self.sliders["shot"] = sound_manager.shot_volume_base

    def update(self, dt: float):
        """Atualiza a lógica da view."""
        if self.is_entering and self.entry_progress < 1.0:
            self.entry_progress = min(
                1.0, self.entry_progress + dt / self.entry_duration
            )
            if self.entry_progress >= 1.0:
                self.is_entering = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Processa eventos da view."""
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.on_back()
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self.layout_rects["back_button"].collidepoint(pos):
                self.on_back()
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
            sound_manager.set_music_volume(volume)
        elif key == "sfx":
            sound_manager.set_sfx_volume(volume)
        elif key == "shot":
            sound_manager.set_shot_volume(volume)

    def render(self, surface: pygame.Surface):
        """Renderiza a view."""
        # Calcular alpha baseado no progresso
        alpha = int(255 * self.entry_progress)
        offset_y = int(30 * (1.0 - self.entry_progress))

        # Título
        title_surf = self.title_font.render("Configurações", True, CUSTOM_GOLD)
        title_surf.set_alpha(alpha)
        surface.blit(title_surf, (20, 20 + offset_y))

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

            # Valor em % (ajustado para não extrapolar)
            percent_text = f"{int(val * 100)}%"
            percent_surf = self.small_font.render(percent_text, True, colors.GRAY)
            percent_surf.set_alpha(alpha)
            percent_x = min(
                rect.right + 10, card_rect.right - percent_surf.get_width() - 10
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
            surface, self.layout_rects["controls_card"], "Instruções", alpha, offset_y
        )

        # Criar clipping para o card
        clip_rect = card_rect.inflate(-10, -10)
        surface.set_clip(clip_rect)

        instructions = [
            "CONTROLES:",
            "• WASD ou Setas: Mover nave",
            "• Espaço: Atirar",
            "• P: Pausar jogo",
            "• ESC: Voltar/Menu",
            "",
            "OBJETIVO:",
            "• Derrote o boss final",
            "• Colete power-ups",
            "• Sobreviva o máximo possível",
            "",
            "DICAS:",
            "• Use os aprimoramentos",
            "• Evite os projéteis inimigos",
            "• Colete moedas para upgrades",
        ]

        y_offset = card_rect.y + 60
        for line in instructions:
            if line == "":
                y_offset += 10
                continue
            color = CUSTOM_GOLD if ":" in line else colors.WHITE
            text_surf = self.small_font.render(line, True, color)
            text_surf.set_alpha(alpha)
            surface.blit(text_surf, (card_rect.x + 20, y_offset))
            y_offset += 25

        surface.set_clip(None)


class SettingsScene(Scene):
    """Cena de configurações (mantida para compatibilidade)."""

    def __init__(self, app: "GameApp", return_to_game: bool = False):
        super().__init__(app)
        self.return_to_game = return_to_game  # Se True, volta para o jogo
        self.r = app.renderer  # Usar renderer compartilhado
        self.view = SettingsView(on_back=self._on_back, renderer=self.r)

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
        pygame.mouse.set_visible(True)
        self.view.reset()

    def exit(self):
        self.view.player_profile.save()

    def handle_event(self, event: pygame.event.Event):
        self.view.handle_event(event)

    def update(self, dt: float):
        # Atualiza o fundo animado para não ficar estático
        self.r.starfield.update(dt)

        # Atualizar transição
        if self.transitioning:
            self.transition_progress += dt / self.transition_duration

            if self.transition_progress >= 1.0:
                # Completou o fade out, executar ação
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

        # Aplicar fade de transição
        if self.transitioning:
            alpha_mult = (
                1.0 - self.transition_progress
                if self.fade_out
                else self.transition_progress
            )
            # Criar surface temporária para aplicar fade
            temp_surface = pygame.Surface(
                (surface.get_width(), surface.get_height()), pygame.SRCALPHA
            )
            self.view.render(temp_surface)
            temp_surface.set_alpha(int(255 * alpha_mult))
            surface.blit(temp_surface, (0, 0))
        else:
            self.view.render(surface)
