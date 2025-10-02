import pygame
from ..core.config import Config
from ..core import colors


class Bullet:
    def __init__(self, x: float, y: float, damage: int = 10):
        self.x, self.y = x, y
        self.w, self.h = 3, 10
        self.damage = damage
        self.dead = False

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float):
        self.y -= Config.BULLET_SPEED * dt
        if self.y + self.h < 0:
            self.dead = True

    def draw(self, surface: pygame.Surface):
        pygame.draw.rect(surface, colors.YELLOW, self.rect)
