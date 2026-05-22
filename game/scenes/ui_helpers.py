import math
import random
from typing import Any

import pygame

from ..core import colors
from ..core.colors import CUSTOM_GOLD, CUSTOM_PURPLE


class UIParticle:
    """Simples sistema de partículas para UI."""

    def __init__(self, x: float, y: float, color: tuple[int, int, int]):
        self.x = x
        self.y = y
        self.color = color
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(20, 80)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = 1.0
        self.size = random.randint(2, 4)

    def update(self, dt: float):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt * 0.8

    def draw(self, surface: pygame.Surface, alpha_mult: float = 1.0):
        if self.life <= 0:
            return
        alpha = int(255 * self.life * alpha_mult)
        p_surf = pygame.Surface((self.size * 2, self.size * 2), pygame.SRCALPHA)
        pygame.draw.circle(
            p_surf, (*self.color, alpha), (self.size, self.size), self.size
        )
        surface.blit(p_surf, (self.x - self.size, self.y - self.size))


def draw_bordered_button(
    surface: pygame.Surface,
    rect: pygame.Rect,
    text: str,
    font: pygame.font.Font,
    color: tuple[int, int, int],
    alpha: int = 255,
    offset_y: int = 0,
) -> None:
    adjusted = rect.copy()
    adjusted.y += offset_y

    is_hovered = adjusted.collidepoint(pygame.mouse.get_pos())
    border_color = CUSTOM_GOLD if (is_hovered and color == CUSTOM_PURPLE) else color

    temp = pygame.Surface((adjusted.width + 4, adjusted.height + 4), pygame.SRCALPHA)
    pygame.draw.rect(
        temp,
        (*border_color, alpha),
        pygame.Rect(2, 2, adjusted.width, adjusted.height),
        2,
        border_radius=8,
    )
    surface.blit(temp, (adjusted.x - 2, adjusted.y - 2))

    text_surf = font.render(text, True, colors.WHITE)
    text_surf.set_alpha(alpha)
    surface.blit(
        text_surf,
        (
            adjusted.centerx - text_surf.get_width() / 2,
            adjusted.centery - text_surf.get_height() / 2,
        ),
    )


def render_with_fade(
    surface: pygame.Surface,
    view: Any,
    starfield: Any,
    transitioning: bool,
    fade_out: bool,
    transition_progress: float,
    background: tuple[int, int, int],
) -> None:
    surface.fill(background)
    starfield.draw(surface)

    if transitioning:
        alpha_mult = (1.0 - transition_progress) if fade_out else transition_progress
        temp = pygame.Surface(
            (surface.get_width(), surface.get_height()), pygame.SRCALPHA
        )
        view.render(temp)
        temp.set_alpha(int(255 * alpha_mult))
        surface.blit(temp, (0, 0))
    else:
        view.render(surface)


def wrap_text(font: pygame.font.Font, text: str, max_width: int) -> list[str]:
    """Quebra texto em múltiplas linhas para caber na largura máxima."""
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current_line = words[0]

    for word in words[1:]:
        candidate = f"{current_line} {word}"
        width = font.size(candidate)[0]
        if width <= max_width:
            current_line = candidate
        else:
            lines.append(current_line)
            current_line = word

    lines.append(current_line)
    return lines


class FadeTransitionMixin:
    """Mixin para propriedades e métodos de transição fade."""

    transitioning: bool
    transition_progress: float
    transition_duration: float
    fade_out: bool

    def _init_transition(self, duration: float = 0.3) -> None:
        self.transitioning = False
        self.transition_progress = 0.0
        self.transition_duration = duration
        self.fade_out = False

    def _on_back(self) -> None:
        """Inicia a transição de fade out."""
        self.fade_out = True
        self.transitioning = True
        self.transition_progress = 0.0
