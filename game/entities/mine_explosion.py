import pygame


class MineExplosion:
    def __init__(self, x: float, y: float, size: int = 20):
        self.x, self.y = x, y
        self.max_radius = size
        # Duração rápida: 0.3s fixo para onda de choque
        self.duration = 0.5
        self.time = self.duration
        self.current_radius = 1.0
        self.hit_ids: set[int] = set()

    def update(self, dt: float):
        self.time = max(0.0, self.time - dt)
        progress = 1 - (self.time / self.duration)
        # Expansão rápida
        self.current_radius = self.max_radius * progress

    def finished(self) -> bool:
        return self.time <= 0

    def draw(self, screen: pygame.Surface):
        if self.finished():
            return

        progress = 1 - (self.time / self.duration)
        # Alpha diminui conforme expande
        alpha = int(200 * (1 - progress))

        # Onda de choque simples: anel laranja expandindo
        radius = int(self.current_radius)
        if radius < 2:
            return

        s = pygame.Surface((self.max_radius * 2, self.max_radius * 2), pygame.SRCALPHA)
        center = (self.max_radius, self.max_radius)

        # Onda de choque preenchida - círculo laranja expandindo
        orange = (255, 140, 0, alpha)
        pygame.draw.circle(s, orange, center, radius)

        screen.blit(s, (int(self.x) - self.max_radius, int(self.y) - self.max_radius))
