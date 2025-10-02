import pygame
from ..core.config import Config
from ..core import colors


class AlienBullet:
    def __init__(self, x: float, y: float):
        self.x, self.y = x, y
        self.w, self.h = 4, 12
        self.speed = 250
        self.dead = False

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float):
        self.y += self.speed * dt
        if self.y > Config.SCREEN_HEIGHT:
            self.dead = True

    def draw(self, surface: pygame.Surface):
        pygame.draw.rect(surface, colors.MAGENTA, self.rect)
