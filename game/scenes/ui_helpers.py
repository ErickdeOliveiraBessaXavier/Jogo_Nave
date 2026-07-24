import math
import random
from typing import Any, Callable

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


def layout_flow_buttons(
    button_states: list[list[str]],
    font_getter: Callable[[int], pygame.font.Font],
    base_font_size: int,
    *,
    avail_w: int,
    btn_h: int,
    gap_x: int,
    gap_y: int,
    pad_x: int,
    min_font: int = 8,
) -> tuple[list[pygame.Rect], pygame.font.Font, int, int, int]:
    """Layout tipo *flex-wrap* para uma fileira de botões de largura UNIFORME.

    Substitui larguras fixas por dimensionamento pelo conteúdo, de forma
    genérica (robusto a novos botões e a qualquer idioma/resolução):

    - Cada botão recebe a MESMA largura = maior rótulo possível (entre TODOS os
      estados de TODOS os botões) + ``2*pad_x``. Assim os botões ficam
      proporcionais entre si e não mudam de tamanho quando o rótulo troca de
      estado em runtime (ex.: "Ligado" ↔ "Desligado").
    - Se a fileira inteira não couber em ``avail_w``, quebra em várias linhas
      (grid centralizado). Se um único botão ainda não couber, a fonte encolhe
      até caber — o texto nunca é cortado nem ultrapassa o botão.

    ``button_states`` é uma lista por botão, cada uma com todos os rótulos que
    aquele botão pode exibir. Retorna ``(rects, font, block_w, block_h, rows)``,
    com ``rects`` relativos ao canto superior-esquerdo do bloco (origem 0,0) —
    o chamador só translada o bloco para a posição final.
    """
    size = max(min_font, base_font_size)
    while True:
        font = font_getter(size)
        text_w = max(font.size(s)[0] for states in button_states for s in states)
        uniform_w = text_w + 2 * pad_x
        if uniform_w <= avail_w or size <= min_font:
            break
        size -= 1
    uniform_w = min(uniform_w, avail_w)

    n = len(button_states)
    cols = max(1, (avail_w + gap_x) // (uniform_w + gap_x))
    cols = min(cols, n)
    rows = math.ceil(n / cols)
    block_w = cols * uniform_w + (cols - 1) * gap_x

    rects: list[pygame.Rect] = []
    for i in range(n):
        r, c = divmod(i, cols)
        row_start = r * cols
        row_n = min(cols, n - row_start)
        row_w = row_n * uniform_w + (row_n - 1) * gap_x
        row_x0 = (block_w - row_w) // 2  # centraliza uma linha curta no bloco
        x = row_x0 + c * (uniform_w + gap_x)
        y = r * (btn_h + gap_y)
        rects.append(pygame.Rect(x, y, uniform_w, btn_h))
    block_h = rows * btn_h + (rows - 1) * gap_y
    return rects, font, block_w, block_h, rows


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
        from ..core.visual_quality import visual_quality

        self.transitioning = False
        self.transition_progress = 0.0
        # Animações off: duração ~instantânea (transição completa em 1 frame,
        # sem o fade de tela cheia por vários frames).
        self.transition_duration = (
            duration if visual_quality.ui_animations else 0.0001
        )
        self.fade_out = False

    def _on_back(self) -> None:
        """Inicia a transição de fade out."""
        self.fade_out = True
        self.transitioning = True
        self.transition_progress = 0.0
