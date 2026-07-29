from typing import Tuple

import pygame

from ...core.assets import get_font

Color = Tuple[int, int, int]

# Amarelo de combate: a cor de todo abate desde sempre, e a referência contra a
# qual o vermelho do crítico se lê como exceção.
COMBAT_COLOR: Color = (255, 255, 0)
# Vermelho do Critical Core. É o segundo (e último) feedback do upgrade, ao lado
# do impacto aumentado (`CRITICAL_CORE_IMPACT_SCALE`): o pico de dano acontece
# no instante do abate, quando o impacto já virou explosão de morte e some. Sem
# uma marca no número, o crítico que MATA é justamente o que não dá para ver.
#
# Vermelho quente e claro (não o vermelho puro): o número é pequeno, fica sobre
# explosões e fundo escuro, e (255, 0, 0) some contra o laranja do burst.
CRITICAL_COLOR: Color = (255, 70, 70)


def score_color(critical: bool) -> Color:
    """Cor do número de um abate. Fonte única do par amarelo/vermelho."""
    return CRITICAL_COLOR if critical else COMBAT_COLOR


class FloatingScore:
    def __init__(
        self,
        x: float,
        y: float,
        value: int,
        color: Color = COMBAT_COLOR,
    ):
        self.x = x
        self.y = y
        self.value = value
        self.color = color
        self.alpha = 255
        self.lifetime = 60
        self.dy = -0.5

        self.font = get_font(28)

    def update(self, _dt: float = 0.0) -> None:
        self.y += self.dy
        self.lifetime -= 1
        self.alpha = max(0, int(255 * (self.lifetime / 60)))

    def draw(self, screen: pygame.Surface) -> None:
        surf = self.font.render(str(self.value), True, self.color)
        surf.set_alpha(self.alpha)
        rect = surf.get_rect(center=(int(self.x), int(self.y)))
        screen.blit(surf, rect)

    def is_dead(self) -> bool:
        return self.lifetime <= 0
