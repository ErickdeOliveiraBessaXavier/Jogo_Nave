"""
Cena de Transição Entre Mundos

Mostra uma tela de apresentação do novo mundo quando o jogador avança para um.
"""

import logging
import math
import re
from typing import TYPE_CHECKING

import pygame

from ..core import colors
from ..core.assets import get_font
from ..core.state import Scene
from ..core.world_config import WorldConfig, WorldTheme

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..app import GameApp


class WorldTransitionScene(Scene):
    """Transição visual entre mundos."""

    def __init__(self, app: "GameApp", new_world: WorldConfig):
        super().__init__(app)
        self.new_world = new_world
        self.timer: float = 0.0
        self.duration: float = 3.0  # 3 segundos
        self.font_title = get_font(60)
        self.font_desc = get_font(24)
        self.font_hint = get_font(16)
        self.font_meta = get_font(20)
        self.font_small = get_font(16)

    def _get_mode_label(self) -> str:
        if self.new_world.theme == WorldTheme.STARFIELD:
            return "Modo: Top-Down"
        return "Modo: Side-Scroll"

    def _get_boss_label(self) -> str:
        boss_type = self.new_world.boss_type
        if boss_type is None:
            return "Boss: Procedural"

        boss_name = re.sub(r"(?<!^)(?=[A-Z])", " ", boss_type.__name__).replace(
            " Boss", " Boss"
        )
        return f"Boss: {boss_name}"

    def _get_modifier_label(self) -> str:
        modifiers = self.new_world.theme_modifiers
        if not modifiers:
            return "Modificadores: padrão"

        ordered = sorted(modifiers.items(), key=lambda item: item[1], reverse=True)
        key, value = ordered[0]
        readable_key = key.replace("_", " ").capitalize()
        return f"Ajuste principal: {readable_key} x{value:.2f}"

    def enter(self) -> None:
        """Ativada ao entrar na cena."""
        pygame.mouse.set_visible(True)
        logger.info(f"🌍 Entrando no mundo: {self.new_world.name}")

    def exit(self) -> None:
        """Ativada ao sair da cena."""
        pygame.mouse.set_visible(False)

    def update(self, dt: float) -> None:
        """Atualiza a transição."""
        self.timer += dt
        if self.timer >= self.duration:
            self.app.states.pop()  # Remove transição

    def handle_event(self, event: pygame.event.Event) -> None:
        """Permite pular a transição."""
        if event.type == pygame.KEYDOWN:
            if event.key in [pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE]:
                self.app.states.pop()  # Pular transição
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self.app.states.pop()  # Pular com clique

    def render(self, surface: pygame.Surface) -> None:
        """Renderiza a transição."""
        surface.fill(colors.BLACK)

        # Calcular alpha (fade in/out)
        alpha = 255
        fade_duration = 0.5
        time_factor = min(1.0, self.timer / self.duration)

        if self.timer < fade_duration:
            # Fade in
            alpha = int((self.timer / fade_duration) * 255)
        elif self.timer > self.duration - fade_duration:
            # Fade out
            alpha = int(((self.duration - self.timer) / fade_duration) * 255)

        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)

        # Fundo limpo e mais legível
        overlay.fill((*colors.BLACK, 230))
        center_x = surface.get_width() // 2
        center_y = surface.get_height() // 2

        # Cartão principal
        card_width = min(760, surface.get_width() - 80)
        card_height = 320
        card_x = center_x - card_width // 2
        card_y = center_y - card_height // 2
        card_rect = pygame.Rect(card_x, card_y, card_width, card_height)
        pygame.draw.rect(overlay, (12, 12, 18, 235), card_rect, border_radius=28)
        pygame.draw.rect(
            overlay,
            (*self.new_world.primary_color, 180),
            card_rect,
            width=3,
            border_radius=28,
        )

        # Faixa superior do cartão
        banner_rect = pygame.Rect(card_x, card_y, card_width, 12)
        pygame.draw.rect(overlay, self.new_world.primary_color, banner_rect)
        pygame.draw.rect(
            overlay,
            self.new_world.secondary_color,
            (card_x + card_width // 2, card_y, card_width // 2, 12),
        )

        # === TÍTULO DO MUNDO ===
        title_top = card_y + 28
        self._blit_wrapped_centered_text(
            overlay,
            self.font_title,
            self.new_world.name,
            self.new_world.primary_color,
            center_x,
            title_top,
            card_width - 80,
            alpha,
            max_lines=2,
            line_spacing=2,
        )

        # === DESCRIÇÃO ===
        desc_top = card_y + 96
        self._blit_wrapped_centered_text(
            overlay,
            self.font_desc,
            self.new_world.description,
            colors.WHITE,
            center_x,
            desc_top,
            card_width - 90,
            alpha,
            max_lines=3,
            line_spacing=4,
        )

        # === DETALHES ===
        details = [
            f"Estágios: {self.new_world.start_level}-{self.new_world.end_level}",
            self._get_mode_label(),
            self._get_boss_label(),
        ]
        detail_y = card_y + 178
        detail_gap = 32
        for index, text in enumerate(details):
            self._blit_wrapped_centered_text(
                overlay,
                self.font_meta,
                text,
                colors.WHITE,
                center_x,
                detail_y + index * detail_gap,
                card_width - 110,
                alpha,
                max_lines=1,
                line_spacing=0,
            )

        # === CORES DO MUNDO (visual) ===
        bar_height = 12
        bar_y = card_y + card_height - 48
        bar_width = 240
        bar_x = center_x - bar_width // 2

        # Barra cor primária
        pygame.draw.rect(
            overlay,
            self.new_world.primary_color,
            (bar_x, bar_y, bar_width // 2, bar_height),
            border_radius=6,
        )

        # Barra cor secundária
        pygame.draw.rect(
            overlay,
            self.new_world.secondary_color,
            (bar_x + bar_width // 2, bar_y, bar_width // 2, bar_height),
            border_radius=6,
        )

        modifier = self.font_small.render(self._get_modifier_label(), True, colors.GRAY)
        modifier.set_alpha(alpha)
        modifier_rect = modifier.get_rect(center=(center_x, bar_y + 34))
        overlay.blit(modifier, modifier_rect)

        # === INSTRUÇÕES ===
        if self.timer < self.duration - 1.0:
            # Mostrar dica enquanto a cena ainda está no início
            skip_text = self.font_hint.render(
                "Pressione ENTER ou ESPAÇO para continuar", True, colors.GRAY
            )
            skip_text.set_alpha(alpha)
            skip_rect = skip_text.get_rect(center=(center_x, surface.get_height() - 50))
            overlay.blit(skip_text, skip_rect)

        # Pulso sutil para dar sensação de movimento
        pulse_alpha = int(35 + 25 * (0.5 + 0.5 * math.sin(time_factor * math.pi * 4)))
        pulse_rect = pygame.Rect(
            card_x + 24, card_y + 24, card_width - 48, card_height - 48
        )
        pygame.draw.rect(
            overlay,
            (*self.new_world.secondary_color, pulse_alpha),
            pulse_rect,
            width=1,
            border_radius=20,
        )

        overlay.set_alpha(alpha)
        surface.blit(overlay, (0, 0))

    def _wrap_text(
        self, font: pygame.font.Font, text: str, max_width: int
    ) -> list[str]:
        words = text.split()
        if not words:
            return [text]

        lines: list[str] = []
        current_line = words[0]

        for word in words[1:]:
            candidate = f"{current_line} {word}"
            if font.size(candidate)[0] <= max_width:
                current_line = candidate
            else:
                lines.append(current_line)
                current_line = word

        lines.append(current_line)
        return lines

    def _blit_wrapped_centered_text(
        self,
        surface: pygame.Surface,
        font: pygame.font.Font,
        text: str,
        color: tuple[int, int, int],
        center_x: int,
        top_y: int,
        max_width: int,
        alpha: int,
        max_lines: int | None = None,
        line_spacing: int = 4,
    ) -> None:
        lines = self._wrap_text(font, text, max_width)
        if max_lines is not None:
            lines = lines[:max_lines]

        rendered_lines = []
        total_height = 0
        for line in lines:
            rendered = font.render(line, True, color)
            rendered.set_alpha(alpha)
            rendered_lines.append(rendered)
            total_height += rendered.get_height()

        if rendered_lines:
            total_height += line_spacing * (len(rendered_lines) - 1)

        current_y = top_y
        for rendered in rendered_lines:
            rect = rendered.get_rect(
                center=(center_x, current_y + rendered.get_height() // 2)
            )
            surface.blit(rendered, rect)
            current_y += rendered.get_height() + line_spacing
