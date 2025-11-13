import pygame
from ..core.config import Config


class MineExplosion:
    def __init__(self, x: float, y: float, size: int = 20):
        self.x, self.y = x, y
        self.max_radius = size
        self.duration = (Config.EXPLOSION_DURATION * (size / 40)) / 4
        self.time = self.duration
        self.current_radius = 0

    def update(self, dt: float):
        self.time = max(0.0, self.time - dt)
        progress = 1 - (self.time / self.duration)
        self.current_radius = self.max_radius * progress

    def finished(self) -> bool:
        return self.time <= 0

    def draw(self, screen: pygame.Surface):
        if self.finished():
            return

        progress = 1 - (self.time / self.duration)
        alpha = int(255 * (1 - progress))

        # Desenha um círculo que expande
        s = pygame.Surface((self.max_radius * 2, self.max_radius * 2), pygame.SRCALPHA)
        color = (255, int(255 * (1 - progress)), 0, alpha)
        pygame.draw.circle(
            s, color, (self.max_radius, self.max_radius), int(self.current_radius)
        )
        screen.blit(s, (self.x - self.max_radius, self.y - self.max_radius))
