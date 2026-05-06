from typing import Any

import pygame

from ..core import colors
from ..core.colors import CUSTOM_GOLD, CUSTOM_PURPLE


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
        temp, (*border_color, alpha), pygame.Rect(2, 2, adjusted.width, adjusted.height), 2, border_radius=8
    )
    surface.blit(temp, (adjusted.x - 2, adjusted.y - 2))

    text_surf = font.render(text, True, colors.WHITE)
    text_surf.set_alpha(alpha)
    surface.blit(
        text_surf,
        (adjusted.centerx - text_surf.get_width() / 2, adjusted.centery - text_surf.get_height() / 2),
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
        temp = pygame.Surface((surface.get_width(), surface.get_height()), pygame.SRCALPHA)
        view.render(temp)
        temp.set_alpha(int(255 * alpha_mult))
        surface.blit(temp, (0, 0))
    else:
        view.render(surface)
