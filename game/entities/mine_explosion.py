import pygame


class MineExplosion:
    def __init__(self, x: float, y: float, size: int = 20):
        self.x, self.y = x, y
        self.max_radius = size
        self.duration = 0.5
        self.time = self.duration
        self.current_radius = 1.0
        self.hit_ids: set[int] = set()
        # Surface pré-alocada — reutilizada a cada frame
        self._surface = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)

    def update(self, dt: float):
        self.time = max(0.0, self.time - dt)
        progress = 1 - (self.time / self.duration)
        self.current_radius = self.max_radius * progress

    def finished(self) -> bool:
        return self.time <= 0

    def draw(self, screen: pygame.Surface):
        if self.finished():
            return

        radius = int(self.current_radius)
        if radius < 2:
            return

        progress = 1 - (self.time / self.duration)
        alpha = int(200 * (1 - progress))

        self._surface.fill((0, 0, 0, 0))
        pygame.draw.circle(
            self._surface,
            (255, 140, 0, alpha),
            (self.max_radius, self.max_radius),
            radius,
        )
        screen.blit(self._surface, (int(self.x) - self.max_radius, int(self.y) - self.max_radius))
