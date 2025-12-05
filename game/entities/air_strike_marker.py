import pygame


class AirStrikeMarker:
    """Marcador simples que indica onde a bomba vai cair."""

    def __init__(self, x: float, y: float, radius: float = 50.0, delay: float = 1.0):
        self.x = x
        self.y = y
        self.max_radius = radius
        self.delay = delay
        self.timer = 0.0
        self.dead = False
        self.exploded = False

    @property
    def target_x(self) -> float:
        return self.x

    @property
    def target_y(self) -> float:
        return self.y

    @property
    def progress(self) -> float:
        return min(1.0, self.timer / self.delay)

    def update(self, dt: float) -> None:
        self.timer += dt
        if self.timer >= self.delay:
            self.exploded = True
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        # Círculo cresce de 0 até max_radius
        radius = int(self.max_radius * self.progress)
        if radius <= 0:
            return

        alpha = int(100 + 155 * self.progress)
        size = int(self.max_radius * 2)

        s = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(s, (255, 255, 255, alpha), (size // 2, size // 2), radius, 2)
        surface.blit(s, (int(self.x) - size // 2, int(self.y) - size // 2))
