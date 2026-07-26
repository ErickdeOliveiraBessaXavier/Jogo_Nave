import math
import random
from typing import TYPE_CHECKING, Any, Callable, Dict, List

import pygame

from ..core.assets import get_font
from ..core.colors import (
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
from ..core.i18n import t
from ..core.sound import sound_manager
from .ui_helpers import UIParticle, draw_bordered_button, wrap_text

if TYPE_CHECKING:
    pass


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

        # Escala de UI relativa ao design base (1280×720). Todas as resoluções
        # ofertadas são 16:9, então um único fator (largura) cobre os dois
        # eixos. Mantém cards, fontes e botões proporcionais fora de 720p
        # (consistente com a seleção de mundos e o loadout).
        self.ui_scale = Config.SCREEN_WIDTH / 1280.0

        self.title_font = get_font(max(12, int(36 * self.ui_scale)))
        self.button_font = get_font(max(8, int(16 * self.ui_scale)))
        self.desc_font = get_font(max(8, int(13 * self.ui_scale)))

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
        s = self.ui_scale
        center_x = Config.SCREEN_WIDTH // 2

        # Título
        self.title_text = self.title_font.render(
            t("difficulty.title"), True, CUSTOM_GOLD
        )
        self.title_rect = self.title_text.get_rect(center=(center_x, int(80 * s)))

        # Configurações dos botões (agora como quadrados horizontais), escaladas.
        card_size = int(220 * s)
        spacing = int(30 * s)  # Espaçamento entre cards
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
            desc_lines = wrap_text(
                self.desc_font, t(f"difficulty.{preset.value}.desc"), card_size - int(30 * s)
            )
            desc_surfaces = [
                self.desc_font.render(line, True, WHITE) for line in desc_lines
            ]

            # Informações extras
            lives_text = self.desc_font.render(
                t("difficulty.lives", n=settings["lives"]), True, WHITE
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
                "name": t(f"difficulty.{preset.value}.name"),
                "desc_surfaces": desc_surfaces,
                "lives_text": lives_text,
                "color": self.difficulty_colors[preset],
                "hover_progress": 0.0,
                "shake_params": shake_params[preset],
                "shake_offset": [0, 0],
            }

        # Botão Voltar (Canto inferior esquerdo)
        btn_w = int(160 * s)
        btn_h = int(40 * s)
        self.back_button_rect = pygame.Rect(
            int(40 * s), Config.SCREEN_HEIGHT - int(60 * s), btn_w, btn_h
        )

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
        s = self.ui_scale
        radius = max(4, int(12 * s))
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
                glow_size = max(1, int(12 * hover_p * s))
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
                        border_radius=max(4, int(15 * s)),
                    )
                surface.blit(glow_surface, glow_rect.topleft)

            # 2. Desenhar Quadrado Principal
            temp_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)

            # Cor de fundo (Preto translúcido para destacar o conteúdo sobre o background)
            pygame.draw.rect(
                temp_surface,
                (20, 20, 30, int(alpha * 0.8)),
                temp_surface.get_rect(),
                border_radius=radius,
            )

            # Borda do quadrado (Agora com a cor da dificuldade)
            border_width = max(2, int((3 + 2 * hover_p) * s))
            pygame.draw.rect(
                temp_surface,
                (*color, alpha),
                temp_surface.get_rect(),
                border_width,
                border_radius=radius,
            )

            # Blit no surface principal
            surface.blit(temp_surface, rect.topleft)

            # 3. Textos do Card
            # Nome (Título da dificuldade) - Cor da dificuldade para o título tbm
            name_surface = self.button_font.render(button_data["name"], True, color)
            name_surface.set_alpha(alpha)
            name_rect = name_surface.get_rect(
                centerx=rect.centerx, top=rect.top + int(20 * s)
            )
            surface.blit(name_surface, name_rect)

            # Descrição (centralizada verticalmente no quadrado)
            desc_gap = int(5 * s)
            total_desc_h = sum(
                surf.get_height() + desc_gap for surf in button_data["desc_surfaces"]
            )
            y_ptr = rect.centery - total_desc_h // 2
            for desc_surf in button_data["desc_surfaces"]:
                ds = desc_surf.copy()
                ds.set_alpha(alpha)
                dr = ds.get_rect(centerx=rect.centerx, top=y_ptr)
                surface.blit(ds, dr)
                y_ptr += ds.get_height() + desc_gap

            # Vidas
            lives_surface = button_data["lives_text"].copy()
            lives_surface.set_alpha(alpha)
            lives_rect = lives_surface.get_rect(
                centerx=rect.centerx, bottom=rect.bottom - int(20 * s)
            )
            surface.blit(lives_surface, lives_rect)

        # Botão Voltar
        draw_bordered_button(
            surface,
            self.back_button_rect,
            t("common.back"),
            self.button_font,
            CUSTOM_PURPLE,
            alpha,
            offset_y,
        )
