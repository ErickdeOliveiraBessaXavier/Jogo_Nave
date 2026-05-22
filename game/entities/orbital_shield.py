import math
import pygame
from typing import Any

class OrbitalShield:
    def __init__(self, ship: Any, duration: float):
        self.ship = ship
        self.timer = duration
        self.dead = False
        self.angle = 0.0
        self.radius = 80.0
        self.speed = 4.0
        self.size = 32
        self.damage = 150 # Dano por segundo de contato

    def update(self, dt: float):
        self.timer -= dt
        if self.timer <= 0 or getattr(self.ship, "dead", False):
            self.dead = True
            return
        
        self.angle += self.speed * dt

    def get_pos(self) -> tuple[float, float]:
        cx = self.ship.x + self.ship.w / 2
        cy = self.ship.y + self.ship.h / 2
        x = cx + math.cos(self.angle) * self.radius - self.size / 2
        y = cy + math.sin(self.angle) * self.radius - self.size / 2
        return x, y

    @property
    def rect(self) -> pygame.Rect:
        x, y = self.get_pos()
        return pygame.Rect(int(x), int(y), self.size, self.size)

    def draw(self, surface: pygame.Surface):
        x, y = self.get_pos()
        # Desenha um escudo de pedra/energia
        rect = self.rect
        pygame.draw.rect(surface, (100, 100, 100), rect, border_radius=5)
        pygame.draw.rect(surface, (150, 150, 150), rect.inflate(-4, -4), border_radius=3)
        # Brilho ciano nas bordas
        pygame.draw.rect(surface, (0, 200, 255), rect, 2, border_radius=5)
