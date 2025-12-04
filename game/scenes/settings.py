import pygame
from typing import TYPE_CHECKING, Optional, Dict, Any
from pathlib import Path

from ..core.state import Scene
from ..core.colors import WHITE, BLACK, GRAY, BLUE, Color
from ..core.assets import get_font
from ..render.renderer import Renderer
from ..core.sound import sound_manager
from ..core.meta_progression import PlayerProfile

if TYPE_CHECKING:
    from ..app import GameApp


class SettingsScene(Scene):
    """Cena de configurações com design renovado."""

    def __init__(self, app: "GameApp", return_to_game: bool = False):
        super().__init__(app)
        self.player_profile = PlayerProfile(Path("player_profile.json"))
        self.r = Renderer()
        self.return_to_game = return_to_game  # Se True, volta para o jogo

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
        self.dragging_slider: Optional[str] = None
        # Removido: lógica de alterar hotkeys

        # Layout
        self.layout_rects: Dict[str, Any] = {}
        self._calculate_layout()

    def _calculate_layout(self):
        screen_w, screen_h = self.app.screen.get_size()
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

        # Removido: botões para alterar hotkeys

        # Botão de Voltar
        self.layout_rects["back_button"] = pygame.Rect(pad, screen_h - 60, 150, 40)

    def enter(self):
        pygame.mouse.set_visible(True)
        self.dragging_slider = None

    def exit(self):
        self.player_profile.save()

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._return_to_menu()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self.layout_rects["back_button"].collidepoint(pos):
                self._return_to_menu()
                return

            # Sliders
            for key, rect in self.layout_rects["sliders"].items():
                if rect.collidepoint(pos):
                    self.dragging_slider = key
                    # Atualizar valor no clique
                    new_val = (pos[0] - rect.x) / rect.w
                    self.sliders[key] = max(0.0, min(1.0, new_val))
                    self._update_volume(key)
                    return

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging_slider = None

        if event.type == pygame.MOUSEMOTION:
            if self.dragging_slider:
                key = self.dragging_slider
                rect = self.layout_rects["sliders"][key]
                pos = event.pos
                new_val = (pos[0] - rect.x) / rect.w
                self.sliders[key] = max(0.0, min(1.0, new_val))
                self._update_volume(key)

    def _update_volume(self, key: str):
        volume = self.sliders[key]
        if key == "music":
            sound_manager.set_music_volume(volume)
        elif key == "sfx":
            sound_manager.set_sfx_volume(volume)
        elif key == "shot":
            sound_manager.set_shot_volume(volume)

    def update(self, dt: float):
        # Atualiza o fundo animado para não ficar estático
        if hasattr(self, "r"):
            self.r.starfield.update(dt)

    def render(self, surface: pygame.Surface):
        surface.fill(BLACK)
        # Fundo com o mesmo estilo de upgrades_selection
        self.r.starfield.draw(surface)

        # Título
        title_surf = self.title_font.render("Configurações", True, WHITE)
        surface.blit(title_surf, (20, 20))

        # Desenhar Cards
        self._draw_audio_card(surface)
        self._draw_controls_card(surface)

        # Botão Voltar
        self._draw_button(surface, self.layout_rects["back_button"], "Voltar", GRAY)

    def _draw_button(
        self, surface: pygame.Surface, rect: pygame.Rect, text: str, color: Color
    ):
        is_hovered = rect.collidepoint(pygame.mouse.get_pos())
        bg_color = tuple(min(c + 20, 255) for c in color) if is_hovered else color
        pygame.draw.rect(surface, bg_color, rect, border_radius=8)
        pygame.draw.rect(surface, WHITE, rect, 2, border_radius=8)
        text_surf = self.item_font.render(text, True, WHITE)
        surface.blit(
            text_surf,
            (
                rect.centerx - text_surf.get_width() / 2,
                rect.centery - text_surf.get_height() / 2,
            ),
        )

    def _draw_card(self, surface: pygame.Surface, rect: pygame.Rect, title: str):
        # Apenas a borda, sem fundo
        pygame.draw.rect(surface, GRAY, rect, 1, border_radius=8)
        title_surf = self.header_font.render(title, True, WHITE)
        surface.blit(title_surf, (rect.x + 15, rect.y + 15))

    def _draw_audio_card(self, surface: pygame.Surface):
        card_rect = self.layout_rects["audio_card"]
        self._draw_card(surface, card_rect, "Áudio")

        labels = {"music": "Música", "sfx": "Efeitos (SFX)", "shot": "Tiros"}

        # Criar clipping para o card
        clip_rect = card_rect.inflate(-10, -10)
        surface.set_clip(clip_rect)

        for key, rect in self.layout_rects["sliders"].items():
            # Label
            label_surf = self.item_font.render(labels[key], True, WHITE)
            surface.blit(label_surf, (rect.x, rect.y - 30))

            # Slider
            val = self.sliders[key]
            # Barra de fundo
            pygame.draw.rect(surface, (10, 10, 10), rect, border_radius=10)
            # Barra de preenchimento
            fill_width = val * rect.width
            fill_rect = pygame.Rect(rect.x, rect.y, fill_width, rect.height)
            pygame.draw.rect(surface, BLUE, fill_rect, border_radius=10)
            # Borda
            pygame.draw.rect(surface, GRAY, rect, 1, border_radius=10)
            # Knob
            knob_x = rect.x + int(val * rect.w)
            knob_rect = pygame.Rect(0, 0, 10, rect.height + 10)
            knob_rect.center = (knob_x, rect.centery)
            pygame.draw.rect(surface, WHITE, knob_rect, border_radius=3)
            
            # Valor em % (ajustado para não extrapolar)
            percent_text = f"{int(val * 100)}%"
            percent_surf = self.small_font.render(percent_text, True, GRAY)
            percent_x = min(rect.right + 10, card_rect.right - percent_surf.get_width() - 10)
            surface.blit(percent_surf, (percent_x, rect.centery - percent_surf.get_height()/2))

        surface.set_clip(None)


    def _draw_controls_card(self, surface: pygame.Surface):
        card_rect = self.layout_rects["controls_card"]
        self._draw_card(surface, card_rect, "Instruções")

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
            "• Colete moedas para upgrades"
        ]

        y_offset = card_rect.y + 60
        for line in instructions:
            if line == "":
                y_offset += 10
                continue
            color = BLUE if ":" in line else WHITE
            text_surf = self.small_font.render(line, True, color)
            surface.blit(text_surf, (card_rect.x + 20, y_offset))
            y_offset += 25

        surface.set_clip(None)

    def _return_to_menu(self):
        """Retorna ao menu principal ou ao jogo, dependendo do contexto."""
        if self.return_to_game:
            # Se estava jogando, apenas remove a cena de configurações da pilha
            self.app.states.pop()
        else:
            # Se veio do menu, substitui pela tela do menu
            from .main_menu import MainMenuScene
            self.app.states.switch(MainMenuScene(self.app))
