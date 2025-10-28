import pygame
from ..core.config import Config
from ..core import colors

class MiniShipBullet:
    def __init__(self, x: float, y: float, vx: float, vy: float, damage: int = 5):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.w = 4
        self.h = 4
        self.damage = damage
        self.dead = False
        self.piercing = False # Mini-ship bullets are not piercing by default

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float):
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.y + self.h < 0 or self.y > Config.SCREEN_HEIGHT or self.x + self.w < 0 or self.x > Config.SCREEN_WIDTH:
            self.dead = True

    def draw(self, surface: pygame.Surface):
        pygame.draw.rect(surface, colors.CYAN, self.rect)
