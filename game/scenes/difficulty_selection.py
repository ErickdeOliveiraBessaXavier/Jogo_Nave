import math
import random
from typing import TYPE_CHECKING, Any, Callable, Dict, List

import pygame

from ..core.assets import get_font
from ..core.colors import (
    CUSTOM_DARK_BG,
    CUSTOM_GOLD,
    CUSTOM_PURPLE,
    GREEN,
    ORANGE,
    RED,
    WHITE,
    YELLOW,
)
from ..core.config import config as Config
from ..core.difficulty import DifficultyPreset, DifficultySettings
from ..core.sound import sound_manager
from ..core.state import Scene
from .ui_helpers import UIParticle, draw_bordered_button

if TYPE_CHECKING:
    from ..app import GameApp


class DifficultySelectionView:
    """View para seleção de dificuldade (pode ser usada dentro de outras cenas)."""

    def __init__(
        self,
        on_select: Callable[[DifficultyPreset], None],
        on_back: Callable[[], None],
        renderer: Any = None,
    ):
        """
        Args:
            on_select: Callback chamado quando uma dificuldade é selecionada
            on_back: Callback chamado quando o usuário quer voltar
            renderer: Renderer compartilhado (opcional)
        """
        self.on_select = on_select
        self.on_back = on_back
        self.renderer = renderer

        self.title_font = get_font(36)
        self.button_font = get_font(16)
        self.desc_font = get_font(13)

        # Cores por dificuldade
        self.difficulty_colors = {
            DifficultyPreset.CASUAL: GREEN,
            DifficultyPreset.NORMAL: YELLOW,
            DifficultyPreset.HARDCORE: ORANGE,
            DifficultyPreset.NIGHTMARE: RED,
        }

        self.difficulty_buttons: Dict[DifficultyPreset, Dict[str, Any]] = {}
        self.selected_difficulty: DifficultyPreset | None = None
        self.hovered_difficulty: DifficultyPreset | None = None

        # Animação de entrada
        self.entry_progress: float = 0.0
        self.is_entering: bool = True
        self.entry_duration: float = 0.4

        # Sistema de partículas
        self.particles: List[UIParticle] = []

        # Tempo global para tremores
        self.time = 0.0

        self.setup_ui()

    def setup_ui(self):
        """Configura elementos da interface."""
        center_x = Config.SCREEN_WIDTH // 2

        # Título
        self.title_text = self.title_font.render(
            "Selecione a Dificuldade", True, CUSTOM_GOLD
        )
        self.title_rect = self.title_text.get_rect(center=(center_x, 80))

        # Configurações dos botões (agora como quadrados horizontais)
        card_size = 220
        spacing = 30  # Espaçamento entre cards
        num_cards = len(DifficultyPreset)

        # Calcular largura total dos cards
        total_width = (card_size * num_cards) + (spacing * (num_cards - 1))
        start_x = (Config.SCREEN_WIDTH - total_width) // 2
        card_y = (Config.SCREEN_HEIGHT - card_size) // 2

        # Criar botões para cada dificuldade
        self.difficulty_buttons = {}

        for i, preset in enumerate(DifficultyPreset):
            settings = DifficultySettings.get_settings(preset)
            card_x = start_x + (i * (card_size + spacing))

            # Retângulo do card
            button_rect = pygame.Rect(card_x, card_y, card_size, card_size)

            # Descrição com quebra de linha
            desc_lines = self._wrap_text(
                settings["description"], self.desc_font, card_size - 30
            )
            desc_surfaces = [
                self.desc_font.render(line, True, WHITE) for line in desc_lines
            ]

            # Informações extras
            lives_text = self.desc_font.render(
                f"Vidas: {settings['lives']}", True, WHITE
            )

            # Parâmetros de tremor unificados pelo estilo do Pesadelo (sutil mas energético)
            # (amplitude_x, amplitude_y, frequência, fase)
            shake_params = {
                DifficultyPreset.CASUAL: (1.5, 1.2, 3.0, i * 1.5),
                DifficultyPreset.NORMAL: (1.5, 1.2, 3.0, i * 2.0),
                DifficultyPreset.HARDCORE: (1.5, 1.2, 3.0, i * 2.5),
                DifficultyPreset.NIGHTMARE: (1.5, 1.2, 3.0, i * 3.0),
            }

            self.difficulty_buttons[preset] = {
                "rect": button_rect,
                "name": settings["name"],
                "desc_surfaces": desc_surfaces,
                "lives_text": lives_text,
                "color": self.difficulty_colors[preset],
                "hover_progress": 0.0,
                "shake_params": shake_params[preset],
                "shake_offset": [0, 0],
            }

        # Botão Voltar (Canto inferior esquerdo)
        btn_w = 160
        btn_h = 40
        self.back_button_rect = pygame.Rect(40, Config.SCREEN_HEIGHT - 60, btn_w, btn_h)

    def _wrap_text(
        self, text: str, font: pygame.font.Font, max_width: int
    ) -> list[str]:
        """Quebra texto em múltiplas linhas."""
        words = text.split(" ")
        lines: list[str] = []
        current_line: list[str] = []

        for word in words:
            test_line = " ".join(current_line + [word])
            if font.size(test_line)[0] <= max_width:
                current_line.append(word)
            else:
                lines.append(" ".join(current_line))
                current_line = [word]

        if current_line:
            lines.append(" ".join(current_line))

        return lines

    def reset(self):
        """Reseta o estado da view para reiniciar animação."""
        self.entry_progress = 0.0
        self.is_entering = True
        self.selected_difficulty = None
        self.hovered_difficulty = None
        self.particles.clear()
        self.time = 0.0
        for button_data in self.difficulty_buttons.values():
            button_data["hover_progress"] = 0.0
            button_data["shake_offset"] = [0, 0]

    def handle_event(self, event: pygame.event.Event):
        """Processa eventos da view."""
        if event.type == pygame.MOUSEBUTTONDOWN:
            # Verificar botão voltar
            if self.back_button_rect.collidepoint(event.pos):
                sound_manager.play_sound("button_click")
                self.on_back()
                return True

            for preset, button_data in self.difficulty_buttons.items():
                if button_data["rect"].collidepoint(event.pos):
                    sound_manager.play_sound("button_click")
                    self.selected_difficulty = preset
                    self.on_select(preset)
                    return True  # Evento consumido

        elif event.type == pygame.MOUSEMOTION:
            prev_hovered = self.hovered_difficulty
            self.hovered_difficulty = None

            for preset, button_data in self.difficulty_buttons.items():
                if button_data["rect"].collidepoint(event.pos):
                    self.hovered_difficulty = preset

            # Som de hover
            if self.hovered_difficulty != prev_hovered and self.hovered_difficulty:
                sound_manager.play_sound("button_hover")

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.on_back()
                return True  # Evento consumido

        elif event.type == pygame.JOYBUTTONDOWN:
            # Controle: A confirma no card sob o cursor virtual (movido pelo
            # RS no app.py). LB/RB ciclam entre dificuldades sem precisar
            # apontar com a mira — UX típica de menu de fighting/arcade.
            from ..core.gamepad import XboxButton

            if event.button == XboxButton.A:
                pos = pygame.mouse.get_pos()
                if self.back_button_rect.collidepoint(pos):
                    sound_manager.play_sound("button_click")
                    self.on_back()
                    return True
                for preset, button_data in self.difficulty_buttons.items():
                    if button_data["rect"].collidepoint(pos):
                        sound_manager.play_sound("button_click")
                        self.selected_difficulty = preset
                        self.on_select(preset)
                        return True
            elif event.button == XboxButton.B:
                self.on_back()
                return True
            elif event.button == XboxButton.LB:
                self._cycle_difficulty(-1)
                return True
            elif event.button == XboxButton.RB:
                self._cycle_difficulty(+1)
                return True

        return False  # Evento não consumido

    def _cycle_difficulty(self, direction: int) -> None:
        """Move o cursor para o card de dificuldade vizinho na direção dada.

        Quando a mira está fora dos cards (e.g. apertou LB/RB na primeira vez),
        ancora no primeiro card. ``direction`` +1 vai pra direita, -1 esquerda.
        Sem wrap entre extremos pra dar feedback claro do limite.
        """
        presets = list(self.difficulty_buttons.keys())
        if not presets:
            return
        pos = pygame.mouse.get_pos()
        current_idx = -1
        for i, preset in enumerate(presets):
            if self.difficulty_buttons[preset]["rect"].collidepoint(pos):
                current_idx = i
                break
        if current_idx == -1:
            target_idx = 0 if direction > 0 else len(presets) - 1
        else:
            target_idx = max(0, min(len(presets) - 1, current_idx + direction))
        if target_idx == current_idx:
            return
        target_rect = self.difficulty_buttons[presets[target_idx]]["rect"]
        try:
            pygame.mouse.set_pos(target_rect.center)
        except pygame.error:
            pass
        self.hovered_difficulty = presets[target_idx]
        sound_manager.play_sound("button_hover")

    def update(self, dt: float):
        """Atualiza a lógica da view."""
        self.time += dt

        # Animação de entrada
        if self.is_entering and self.entry_progress < 1.0:
            self.entry_progress = min(
                1.0, self.entry_progress + dt / self.entry_duration
            )
            if self.entry_progress >= 1.0:
                self.is_entering = False

        # Atualizar progresso de hover e tremor para cada card
        speed = 10.0  # Velocidade da animação
        for preset, button_data in self.difficulty_buttons.items():
            is_hovered = preset == self.hovered_difficulty

            # Interpolação de hover
            target = 1.0 if is_hovered else 0.0
            if button_data["hover_progress"] != target:
                if button_data["hover_progress"] < target:
                    button_data["hover_progress"] = min(
                        target, button_data["hover_progress"] + dt * speed
                    )
                else:
                    button_data["hover_progress"] = max(
                        target, button_data["hover_progress"] - dt * speed
                    )

            if is_hovered:
                # Tremor único apenas se selecionado (hover)
                amp_x, amp_y, freq, phase = button_data["shake_params"]
                # Aumentar tremor se hovered (que é o único caso aqui agora)
                mult = 1.0 + button_data["hover_progress"] * 0.1
                button_data["shake_offset"][0] = (
                    math.sin(self.time * freq + phase) * amp_x * mult
                )
                button_data["shake_offset"][1] = (
                    math.cos(self.time * freq * 1.1 + phase * 0.7) * amp_y * mult
                )

                # Emitir partículas nas bordas
                num_p = 2
                for _ in range(num_p):
                    # Calcular posição visual atual do rect para as partículas
                    # (ignorando o tremor instantâneo para evitar jitter nas partículas)
                    vis_offset_y = int(30 * (1.0 - self.entry_progress))
                    slide_off = int(15 * button_data["hover_progress"])
                    rect = button_data["rect"]

                    # Escolher um lado aleatório da borda
                    side = random.randint(0, 3)
                    if side == 0:  # Top
                        px = random.uniform(rect.left, rect.right)
                        py = rect.top + vis_offset_y - slide_off
                    elif side == 1:  # Bottom
                        px = random.uniform(rect.left, rect.right)
                        py = rect.bottom + vis_offset_y - slide_off
                    elif side == 2:  # Left
                        px = rect.left
                        py = random.uniform(
                            rect.top + vis_offset_y - slide_off,
                            rect.bottom + vis_offset_y - slide_off,
                        )
                    else:  # Right
                        px = rect.right
                        py = random.uniform(
                            rect.top + vis_offset_y - slide_off,
                            rect.bottom + vis_offset_y - slide_off,
                        )

                    self.particles.append(UIParticle(px, py, button_data["color"]))
            else:
                # Resetar tremor se não estiver selecionado
                button_data["shake_offset"] = [0, 0]

        # Atualizar partículas
        for p in self.particles[:]:
            p.update(dt)
            if p.life <= 0:
                self.particles.remove(p)

    def render(self, surface: pygame.Surface):
        """Renderiza a view."""
        # Calcular alpha baseado no progresso
        alpha = int(255 * self.entry_progress)
        offset_y = int(30 * (1.0 - self.entry_progress))

        # Título
        title_surface = self.title_text.copy()
        title_surface.set_alpha(alpha)
        title_pos = (self.title_rect.x, self.title_rect.y + offset_y)
        surface.blit(title_surface, title_pos)

        # Renderizar Partículas
        for p in self.particles:
            p.draw(surface, alpha / 255.0)

        # Botões de dificuldade (Quadrados)
        for button_data in self.difficulty_buttons.values():
            hover_p = button_data["hover_progress"]
            shake_off = button_data["shake_offset"]

            # Slide Up base
            slide_offset = int(15 * hover_p)

            rect = button_data["rect"].copy()
            rect.x += int(shake_off[0])
            rect.y += offset_y - slide_offset + int(shake_off[1])
            color = button_data["color"]

            # 1. Desenhar Glow se hovered
            if hover_p > 0:
                glow_size = int(12 * hover_p)
                glow_rect = rect.inflate(glow_size * 2, glow_size * 2)
                glow_surface = pygame.Surface(
                    (glow_rect.width, glow_rect.height), pygame.SRCALPHA
                )

                glow_alpha = int(120 * hover_p * (alpha / 255))
                for i in range(glow_size, 0, -2):
                    step_alpha = int(glow_alpha * (1 - i / (glow_size + 1)))
                    pygame.draw.rect(
                        glow_surface,
                        (*color, step_alpha),
                        (
                            glow_size - i,
                            glow_size - i,
                            rect.width + i * 2,
                            rect.height + i * 2,
                        ),
                        border_radius=15,
                    )
                surface.blit(glow_surface, glow_rect.topleft)

            # 2. Desenhar Quadrado Principal
            temp_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)

            # Cor de fundo (Preto translúcido para destacar o conteúdo sobre o background)
            pygame.draw.rect(
                temp_surface,
                (20, 20, 30, int(alpha * 0.8)),
                temp_surface.get_rect(),
                border_radius=12,
            )

            # Borda do quadrado (Agora com a cor da dificuldade)
            border_width = 3 + int(2 * hover_p)
            pygame.draw.rect(
                temp_surface,
                (*color, alpha),
                temp_surface.get_rect(),
                border_width,
                border_radius=12,
            )

            # Blit no surface principal
            surface.blit(temp_surface, rect.topleft)

            # 3. Textos do Card
            # Nome (Título da dificuldade) - Cor da dificuldade para o título tbm
            name_surface = self.button_font.render(button_data["name"], True, color)
            name_surface.set_alpha(alpha)
            name_rect = name_surface.get_rect(centerx=rect.centerx, top=rect.top + 20)
            surface.blit(name_surface, name_rect)

            # Descrição (centralizada verticalmente no quadrado)
            total_desc_h = sum(s.get_height() + 5 for s in button_data["desc_surfaces"])
            y_ptr = rect.centery - total_desc_h // 2
            for desc_surf in button_data["desc_surfaces"]:
                ds = desc_surf.copy()
                ds.set_alpha(alpha)
                dr = ds.get_rect(centerx=rect.centerx, top=y_ptr)
                surface.blit(ds, dr)
                y_ptr += ds.get_height() + 5

            # Vidas
            lives_surface = button_data["lives_text"].copy()
            lives_surface.set_alpha(alpha)
            lives_rect = lives_surface.get_rect(
                centerx=rect.centerx, bottom=rect.bottom - 20
            )
            surface.blit(lives_surface, lives_rect)

        # Botão Voltar
        draw_bordered_button(
            surface,
            self.back_button_rect,
            "Voltar",
            self.button_font,
            CUSTOM_PURPLE,
            alpha,
            offset_y,
        )


class DifficultySelectionScene(Scene):
    """Cena para seleção de dificuldade antes de iniciar o jogo (mantida para compatibilidade)."""

    def __init__(self, app: "GameApp"):
        super().__init__(app)
        self.view = DifficultySelectionView(
            on_select=self._on_difficulty_selected, on_back=self._on_back
        )

    def _on_difficulty_selected(self, preset: DifficultyPreset):
        """Callback quando uma dificuldade é selecionada."""
        self.start_game(preset)

    def _on_back(self):
        """Callback quando o usuário quer voltar."""
        self.app.states.pop()

    def enter(self):
        pygame.mouse.set_visible(True)
        self.view.reset()

    def handle_event(self, event: pygame.event.Event):
        self.view.handle_event(event)

    def get_focusable_rects(self) -> list[pygame.Rect]:
        """Cards de dificuldade + botão Voltar. App.py usa pra navegar via DPad."""
        rects = [data["rect"] for data in self.view.difficulty_buttons.values()]
        rects.append(self.view.back_button_rect)
        return rects

    def start_game(self, preset: DifficultyPreset):
        """Inicia o jogo com a dificuldade selecionada."""
        from ..scenes.controls_modal import ControlsModalScene
        from ..scenes.playing import PlayingScene

        # Armazenar dificuldade no app
        self.app.selected_difficulty = preset

        def _push_playing_scene():
            self.app.states.push(
                PlayingScene(
                    self.app,
                    self.app.level_manager,
                    difficulty_preset=preset,
                )
            )

        # Se as preferências indicarem para mostrar o modal de controles
        if self.app.preferences.show_controls_modal:
            # Substitui a seleção de dificuldade pelo modal
            self.app.states.switch(
                ControlsModalScene(self.app, on_finish=_push_playing_scene)
            )
        else:
            # Substitui a seleção de dificuldade pela cena de jogo
            self.app.states.switch(
                PlayingScene(
                    self.app,
                    self.app.level_manager,
                    difficulty_preset=preset,
                )
            )

    def update(self, dt: float):
        self.view.update(dt)

    def render(self, surface: pygame.Surface):
        surface.fill(CUSTOM_DARK_BG)
        self.view.render(surface)
