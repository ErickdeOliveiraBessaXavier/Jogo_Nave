"""CaptorEMP — efeito de morte "EMP Discharge" do Cyber-Captor.

Cosmético: uma **onda amarela** que se expande rápido a partir do ponto da morte
(o "pulso" do EMP). A neutralização real dos projéteis próximos é feita pelo
`EntityManager.trigger_death_sequence` no instante da morte (limpa os projéteis
inimigos no raio). Interface duck-typed: `update(dt)`, `draw(surface)`, `dead`,
`rect`.
"""

from __future__ import annotations

import pygame

from . import city_palette as pal

DURATION: float = 0.5  # 0.5s (combina com a janela de "desativar projéteis")
_YELLOW: pal.RGB = (255, 225, 90)
_YELLOW_HOT: pal.RGB = (255, 248, 200)


class CaptorEMP:
    def __init__(self, cx: float, cy: float, radius: float) -> None:
        self.cx: float = cx
        self.cy: float = cy
        self.max_radius: float = radius
        self.t: float = 0.0
        self.dead: bool = False

    @property
    def rect(self) -> pygame.Rect:
        r = int(self.max_radius)
        return pygame.Rect(int(self.cx) - r, int(self.cy) - r, r * 2, r * 2)

    def update(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self.t += dt
        if self.t >= DURATION:
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        f = min(1.0, self.t / DURATION)
        r = int(self.max_radius * (1.0 - (1.0 - f) ** 2))  # ease-out: rápido no início
        if r < 2:
            return
        intensity = 1.0 - f
        cx, cy = int(self.cx), int(self.cy)
        # Anel duplo amarelo expandindo + miolo claro esmaecendo.
        outer = (int(_YELLOW[0] * intensity), int(_YELLOW[1] * intensity), int(_YELLOW[2] * intensity))
        pygame.draw.circle(surface, outer, (cx, cy), r, max(2, int(6 * intensity)))
        inner_r = int(r * 0.78)
        if inner_r > 2:
            hot = (
                int(_YELLOW_HOT[0] * intensity),
                int(_YELLOW_HOT[1] * intensity),
                int(_YELLOW_HOT[2] * intensity),
            )
            pygame.draw.circle(surface, hot, (cx, cy), inner_r, max(1, int(3 * intensity)))
