"""
Cena de Transição Entre Mundos

Mostra uma tela de apresentação do novo mundo quando o jogador avança para um.
"""

import logging
from typing import TYPE_CHECKING, Any, Sequence

import pygame

from ..core import colors
from ..core.assets import get_font
from ..core.state import Scene
from ..core.world_config import WorldConfig

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
        self.font_meta = get_font(20)

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

        if self.timer < fade_duration:
            # Fade in
            alpha = int((self.timer / fade_duration) * 255)
        elif self.timer > self.duration - fade_duration:
            # Fade out
            alpha = int(((self.duration - self.timer) / fade_duration) * 255)

        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        primary_rgb = self._normalize_rgb(self.new_world.primary_color)
        secondary_rgb = self._normalize_rgb(self.new_world.secondary_color)

        # Fundo limpo e mais legível
        overlay.fill((*colors.BLACK, 230))
        center_x = surface.get_width() // 2
        center_y = surface.get_height() // 2

        # Cartão principal (altura extra para acomodar títulos com 2 linhas)
        card_width = min(760, surface.get_width() - 80)
        card_height = 380
        card_x = center_x - card_width // 2
        card_y = center_y - card_height // 2
        card_rect = pygame.Rect(card_x, card_y, card_width, card_height)
        pygame.draw.rect(overlay, (16, 16, 22, 245), card_rect, border_radius=20)
        pygame.draw.rect(
            overlay,
            (*primary_rgb, 200),
            card_rect,
            width=2,
            border_radius=20,
        )

        # Faixa superior do cartão
        banner_rect = pygame.Rect(card_x, card_y, card_width, 10)
        pygame.draw.rect(
            overlay,
            primary_rgb,
            banner_rect,
            border_top_left_radius=20,
            border_top_right_radius=20,
        )
        pygame.draw.rect(
            overlay,
            secondary_rgb,
            (card_x + card_width // 2, card_y, card_width // 2, 10),
            border_top_right_radius=20,
        )

        current_y = card_y + 45

        # === TÍTULO DO MUNDO ===
        title_height = self._blit_wrapped_centered_text(
            overlay,
            self.font_title,
            self.new_world.name,
            colors.WHITE,
            center_x,
            current_y,
            card_width - 80,
            alpha,
            max_lines=2,
            line_spacing=2,
        )
        current_y += title_height + 15

        # Linha separadora minimalista para reforçar hierarquia visual.
        sep_width = 140
        sep_rect = pygame.Rect(center_x - sep_width // 2, current_y, sep_width, 2)
        pygame.draw.rect(overlay, (*primary_rgb, alpha), sep_rect)
        current_y += 20

        # === DESCRIÇÃO ===
        desc_height = self._blit_wrapped_centered_text(
            overlay,
            self.font_desc,
            self.new_world.description,
            (210, 210, 210),
            center_x,
            current_y,
            card_width - 90,
            alpha,
            max_lines=3,
            line_spacing=6,
        )
        current_y += desc_height + 30

        # Apenas informação essencial do progresso.
        stage_text = (
            f"Estágios {self.new_world.start_level} - {self.new_world.end_level}"
        )
        self._blit_wrapped_centered_text(
            overlay,
            self.font_meta,
            stage_text,
            colors.WHITE,
            center_x,
            current_y,
            card_width - 120,
            alpha,
            max_lines=1,
            line_spacing=0,
        )

        # === CORES DO MUNDO (visual) ===
        bar_height = 8
        bar_y = card_y + card_height - 48
        bar_width = 240
        bar_x = center_x - bar_width // 2

        # Barra cor primária
        pygame.draw.rect(
            overlay,
            primary_rgb,
            (bar_x, bar_y, bar_width // 2, bar_height),
            border_radius=4,
        )

        # Barra cor secundária
        pygame.draw.rect(
            overlay,
            secondary_rgb,
            (bar_x + bar_width // 2, bar_y, bar_width // 2, bar_height),
            border_radius=4,
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

    def _normalize_rgb(self, raw_color: Sequence[Any]) -> tuple[int, int, int]:
        """Normaliza cores para RGB válido aceito pelo pygame."""
        if len(raw_color) < 3:
            return (255, 255, 255)

        r = max(0, min(255, int(raw_color[0])))
        g = max(0, min(255, int(raw_color[1])))
        b = max(0, min(255, int(raw_color[2])))
        return (r, g, b)

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
    ) -> int:
        lines = self._wrap_text(font, text, max_width)
        if max_lines is not None:
            lines = lines[:max_lines]

        rendered_lines = []
        for line in lines:
            rendered = font.render(line, True, color)
            rendered.set_alpha(alpha)
            rendered_lines.append(rendered)

        current_y = top_y
        for rendered in rendered_lines:
            rect = rendered.get_rect(
                center=(center_x, current_y + rendered.get_height() // 2)
            )
            surface.blit(rendered, rect)
            current_y += rendered.get_height() + line_spacing

        return current_y - top_y
