"""
Cena de Transição Entre Mundos

Mostra uma tela de apresentação do novo mundo quando o jogador avança para um.
"""

import pygame
import logging
from typing import TYPE_CHECKING

from ..core.state import Scene
from ..core import colors
from ..core.assets import get_font
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
        self.font_hint = get_font(16)

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

        # Criar surface temporária para fade
        temp_surface = pygame.Surface((surface.get_width(), surface.get_height()))
        temp_surface.fill(colors.BLACK)

        # === TÍTULO DO MUNDO ===
        title = self.font_title.render(
            self.new_world.name, True, self.new_world.primary_color
        )
        title.set_alpha(alpha)
        title_rect = title.get_rect(
            center=(surface.get_width() // 2, surface.get_height() // 2 - 80)
        )
        temp_surface.blit(title, title_rect)

        # === DESCRIÇÃO ===
        desc = self.font_desc.render(self.new_world.description, True, colors.WHITE)
        desc.set_alpha(alpha)
        desc_rect = desc.get_rect(
            center=(surface.get_width() // 2, surface.get_height() // 2 + 20)
        )
        temp_surface.blit(desc, desc_rect)

        # === CORES DO MUNDO (visual) ===
        # Barra visual dos temas
        bar_height = 10
        bar_y = surface.get_height() // 2 + 80
        bar_width = 200
        bar_x = surface.get_width() // 2 - bar_width // 2

        # Barra cor primária
        pygame.draw.rect(
            temp_surface,
            self.new_world.primary_color,
            (bar_x, bar_y, bar_width // 2, bar_height),
        )

        # Barra cor secundária
        pygame.draw.rect(
            temp_surface,
            self.new_world.secondary_color,
            (bar_x + bar_width // 2, bar_y, bar_width // 2, bar_height),
        )

        # === INSTRUÇÕES ===
        if self.timer < self.duration - 1.0:
            # Mostrar dica nos primeiros 2 segundos
            skip_text = self.font_hint.render(
                "Pressione ENTER ou ESPAÇO para continuar", True, colors.GRAY
            )
            skip_text.set_alpha(alpha)
            skip_rect = skip_text.get_rect(
                center=(surface.get_width() // 2, surface.get_height() - 50)
            )
            temp_surface.blit(skip_text, skip_rect)

        # Blit temp surface ao screen
        surface.blit(temp_surface, (0, 0))
