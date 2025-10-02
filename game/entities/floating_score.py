import pygame
from typing import Tuple
from ..core.assets import get_font


class FloatingScore:
    def __init__(
        self,
        x: float,
        y: float,
        value: int,
        color: Tuple[int, int, int] = (255, 255, 0),
    ):
        self.x = x
        self.y = y
        self.value = value
        self.color = color
        self.alpha = 255
        self.lifetime = 60
        self.dy = -0.5

        self.font = get_font(28)

    def update(self, dt: float = 0.0) -> None:
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
