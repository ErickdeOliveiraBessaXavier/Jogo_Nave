import pygame
from ..core.config import config as Config
from ..core import colors


class AlienBullet:
    def __init__(self, x: float, y: float):
        self.x, self.y = x, y
        self.w, self.h = 4, 12
        self.speed = 250
        self.dead = False
        self.color = colors.MAGENTA
        self.light_magenta = (255, 100, 255)
        self.flash_timer = 0.0
        self.flash_interval = 0.1

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float):
        self.y += self.speed * dt
        if self.y > Config.SCREEN_HEIGHT:
            self.dead = True

        self.flash_timer += dt
        if self.flash_timer >= self.flash_interval:
            if self.color == colors.MAGENTA:
                self.color = self.light_magenta
            else:
                self.color = colors.MAGENTA
            self.flash_timer = 0.0

    def draw(self, surface: pygame.Surface):
        pygame.draw.rect(surface, self.color, self.rect)
