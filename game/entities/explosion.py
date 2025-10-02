import pygame
import random
import math
from ..core.config import Config


class Explosion:
    def __init__(self, x: float, y: float, size: int = 20):
        self.x, self.y = x, y
        self.time = Config.EXPLOSION_DURATION * (
            size / 40
        )  # Explosões maiores duram mais
        self.size = size
        count = min(20 + size // 4, 40)
        self.particles: list[list[float]] = []

        for _ in range(count):
            angle = random.uniform(0, 360)
            rad_angle = math.radians(angle)
            base_speed = random.uniform(150, 300) * (size / 20)

            vx = base_speed * math.cos(rad_angle)
            vy = base_speed * math.sin(rad_angle)

            # Partículas começam no centro e se movem para fora
            px, py = self.x, self.y

            life = random.uniform(self.time * 0.6, self.time)
            self.particles.append([px, py, vx, vy, life])

    def update(self, dt: float):
        self.time = max(0.0, self.time - dt)
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[2] *= 0.96  # Atrito um pouco mais forte
            p[3] *= 0.96
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]

    def finished(self) -> bool:
        return self.time <= 0 and not self.particles

    def draw(self, screen: pygame.Surface):
        if self.finished():
            return

        for _, p in enumerate(self.particles):
            life_ratio = p[4] / max(self.time, 1e-6)

            # Cor muda de amarelo/laranja para vermelho/fumaça
            if life_ratio > 0.5:
                r = 255
                g = int(255 * ((life_ratio - 0.5) * 2))
            else:
                r = int(255 * (life_ratio * 2))
                g = 0
            color = (r, g, 0)

            pos = (int(p[0]), int(p[1]))
            radius = max(1, self.size / 10 * life_ratio)
            pygame.draw.circle(screen, color, pos, radius)
