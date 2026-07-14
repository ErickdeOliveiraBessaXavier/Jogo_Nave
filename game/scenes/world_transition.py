"""
Cena de Transição Entre Mundos

Mostra uma tela de apresentação do novo mundo quando o jogador avança para um.
"""

import logging
from typing import TYPE_CHECKING, Any, Sequence

import pygame
from .ui_helpers import wrap_text

from ..core import colors
from ..core.assets import get_font
from ..core.i18n import t, t_or
from ..core.state import Scene
from ..core.world_config import WorldConfig

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..app import GameApp


class WorldTransitionScene(Scene):
    """Transição visual entre mundos."""

    def __init__(
        self,
        app: "GameApp",
        new_world: WorldConfig,
        *,
        title_override: str | None = None,
        description_override: str | None = None,
        stage_text_override: str | None = None,
    ):
        super().__init__(app)
        self.new_world = new_world
        # Overrides opcionais — a fase de atmosfera reaproveita este painel
        # (fundo preto + texto central) sem ser um WorldConfig de verdade.
        # `stage_text_override=""` esconde a linha de estágios.
        self.title_override = title_override
        self.description_override = description_override
        self.stage_text_override = stage_text_override
        self.timer: float = 0.0
        self.duration: float = 3.0  # 3 segundos
        self.font_title = get_font(max(8, int(60 * self.ui_scale)))
        self.font_desc = get_font(max(8, int(24 * self.ui_scale)))
        self.font_meta = get_font(max(8, int(20 * self.ui_scale)))

    def enter(self) -> None:
        """Ativada ao entrar na cena."""
        pygame.mouse.set_visible(True)
        logger.info("🌍 Entrando no mundo: %s", self.new_world.name)

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

        # Calcular alpha (fade in/out). Animações off: sem fade (alpha cheio).
        from ..core.visual_quality import visual_quality

        alpha = 255
        fade_duration = 0.5

        if visual_quality.ui_animations:
            if self.timer < fade_duration:
                # Fade in
                alpha = int((self.timer / fade_duration) * 255)
            elif self.timer > self.duration - fade_duration:
                # Fade out
                alpha = int(((self.duration - self.timer) / fade_duration) * 255)

        alpha = max(0, min(255, alpha))

        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        primary_rgb = self._normalize_rgb(self.new_world.primary_color)
        secondary_rgb = self._normalize_rgb(self.new_world.secondary_color)

        # Fundo limpo e mais legível
        overlay.fill((*colors.BLACK, 230))
        center_x = surface.get_width() // 2
        center_y = surface.get_height() // 2

        # Cartão principal. A altura adapta ao título: nomes longos — caso dos
        # mundos procedurais ("Setor N - <tema>") — quebram em 2 linhas na fonte
        # do título e empurravam o conteúdo para fora do cartão (overflow sobre
        # as barras de cor). Pré-medimos as linhas (mesma largura/limite do blit
        # do título abaixo) e somamos a altura de uma linha extra quando há duas.
        card_width = min(self._s(760), surface.get_width() - self._s(80))
        title_wrap_w = card_width - self._s(80)
        title_text = self.title_override or t_or(f"world.{self.new_world.world_id}.name", self.new_world.name)
        title_line_count = len(wrap_text(self.font_title, title_text, title_wrap_w)[:2])
        extra_title_height = (
            (self.font_title.get_height() + self._s(2)) if title_line_count > 1 else 0
        )
        card_height = self._s(380) + extra_title_height
        card_x = center_x - card_width // 2
        card_y = center_y - card_height // 2
        card_radius = self._s(20)
        banner_h = self._s(10)
        card_rect = pygame.Rect(card_x, card_y, card_width, card_height)
        pygame.draw.rect(overlay, (16, 16, 22, 245), card_rect, border_radius=card_radius)
        pygame.draw.rect(
            overlay,
            (*primary_rgb, 200),
            card_rect,
            width=2,
            border_radius=card_radius,
        )

        # Faixa superior do cartão
        banner_rect = pygame.Rect(card_x, card_y, card_width, banner_h)
        pygame.draw.rect(
            overlay,
            primary_rgb,
            banner_rect,
            border_top_left_radius=card_radius,
            border_top_right_radius=card_radius,
        )
        pygame.draw.rect(
            overlay,
            secondary_rgb,
            (card_x + card_width // 2, card_y, card_width // 2, banner_h),
            border_top_right_radius=card_radius,
        )

        current_y = card_y + self._s(45)

        # === TÍTULO DO MUNDO ===
        title_height = self._blit_wrapped_centered_text(
            overlay,
            self.font_title,
            self.title_override or t_or(f"world.{self.new_world.world_id}.name", self.new_world.name),
            colors.WHITE,
            center_x,
            current_y,
            title_wrap_w,
            alpha,
            max_lines=2,
            line_spacing=self._s(2),
        )
        current_y += title_height + self._s(15)

        # Linha separadora minimalista para reforçar hierarquia visual.
        sep_width = self._s(140)
        sep_rect = pygame.Rect(center_x - sep_width // 2, current_y, sep_width, 2)
        pygame.draw.rect(overlay, primary_rgb, sep_rect)
        current_y += self._s(20)

        # === DESCRIÇÃO ===
        desc_height = self._blit_wrapped_centered_text(
            overlay,
            self.font_desc,
            self.description_override
            or t_or(
                f"world.{self.new_world.world_id}.desc", self.new_world.description
            ),
            (210, 210, 210),
            center_x,
            current_y,
            card_width - self._s(90),
            alpha,
            max_lines=3,
            line_spacing=self._s(6),
        )
        current_y += desc_height + self._s(30)

        # Apenas informação essencial do progresso.
        stage_text = (
            self.stage_text_override
            if self.stage_text_override is not None
            else t(
                "world_transition.stages",
                start=self.new_world.start_level,
                end=self.new_world.end_level,
            )
        )
        if stage_text:
            self._blit_wrapped_centered_text(
                overlay,
                self.font_meta,
                stage_text,
                colors.WHITE,
                center_x,
                current_y,
                card_width - self._s(120),
                alpha,
                max_lines=1,
                line_spacing=0,
            )

        # === CORES DO MUNDO (visual) ===
        bar_height = self._s(8)
        bar_y = card_y + card_height - self._s(48)
        bar_width = self._s(240)
        bar_x = center_x - bar_width // 2
        bar_radius = self._s(4)

        # Barra cor primária
        pygame.draw.rect(
            overlay,
            primary_rgb,
            (bar_x, bar_y, bar_width // 2, bar_height),
            border_radius=bar_radius,
        )

        # Barra cor secundária
        pygame.draw.rect(
            overlay,
            secondary_rgb,
            (bar_x + bar_width // 2, bar_y, bar_width // 2, bar_height),
            border_radius=bar_radius,
        )

        overlay.set_alpha(alpha)
        surface.blit(overlay, (0, 0))

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
        lines = wrap_text(font, text, max_width)
        if max_lines is not None:
            lines = lines[:max_lines]

        rendered_lines: list[pygame.Surface] = []
        for line in lines:
            rendered: pygame.Surface = font.render(line, True, color)
            rendered.set_alpha(alpha)
            rendered_lines.append(rendered)

        current_y: int = top_y
        for rendered in rendered_lines:
            rendered_height: int = rendered.get_height()
            rect: pygame.Rect = rendered.get_rect(
                center=(center_x, current_y + rendered_height // 2)
            )
            surface.blit(rendered, rect)
            current_y += rendered_height + line_spacing

        return current_y - top_y
