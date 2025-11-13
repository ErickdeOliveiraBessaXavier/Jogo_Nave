import pygame
import random
from typing import List, Tuple, TypedDict

from ..core import colors


class DeathParticle(TypedDict):
    pos: pygame.Vector2
    vel: pygame.Vector2
    size: float
    color: Tuple[int, int, int]
    lifespan: float


class EyeLaser:
    def __init__(
        self,
        x: float,
        y: float,
        target_x: float,
        target_y: float,
        max_w: int = 8,
        lifetime: float = 1.2,
    ):
        self.x = x
        self.y = y
        self.target_x = target_x
        self.target_y = target_y
        self.w = 0
        self.max_w = max_w
        self.dead = False

        self.lifetime = lifetime
        self.expand_time = 0.15  # Expansão um pouco mais lenta para dar tempo de reagir
        self.hold_time = 0.4  # Segura o laser por mais tempo
        self.timer = 0.0

        self.state = "alive"
        self.death_particles: List[DeathParticle] = []

        # Efeito de pulsação
        self.pulse_timer = 0.0

    def get_collision_line(self) -> tuple[tuple[float, float], tuple[float, float]]:
        return (self.x, self.y), (self.target_x, self.target_y)

    def update(self, dt: float):
        self.timer += dt
        self.pulse_timer += dt * 8  # Velocidade da pulsação

        if self.state == "alive":
            if self.timer >= self.lifetime:
                self.state = "dying"
                self.w = 0
                start_pos = pygame.Vector2(self.x, self.y)
                end_pos = pygame.Vector2(self.target_x, self.target_y)
                line_vec = end_pos - start_pos
                line_length = line_vec.length()
                if line_length > 0:
                    line_vec.normalize_ip()

                # Mais partículas para efeito mais bonito
                num_particles = int(line_length / 20)
                for i in range(num_particles):
                    pos_on_line = start_pos + line_vec * (
                        i * 20 + random.uniform(0, 20)
                    )
                    particle: DeathParticle = {
                        "pos": pos_on_line,
                        "vel": pygame.Vector2(
                            random.uniform(-100, 100), random.uniform(-100, 100)
                        ),
                        "size": random.uniform(2, 4),
                        "color": random.choice(
                            [colors.MAGENTA, colors.PURPLE, colors.WHITE]
                        ),
                        "lifespan": random.uniform(0.2, 0.5),
                    }
                    self.death_particles.append(particle)
                return

            # Cálculo da largura com suavização
            if self.timer < self.expand_time:
                # Expansão suave (ease-out)
                progress = self.timer / self.expand_time
                self.w = self.max_w * (1 - (1 - progress) ** 2)
            elif self.timer < self.expand_time + self.hold_time:
                self.w = self.max_w
            else:
                # Retração suave (ease-in)
                shrink_duration = self.lifetime - (self.expand_time + self.hold_time)
                if shrink_duration > 0:
                    progress = (
                        self.timer - (self.expand_time + self.hold_time)
                    ) / shrink_duration
                    self.w = self.max_w * (1 - progress**2)
            self.w = max(0, self.w)

        elif self.state == "dying":
            for p in self.death_particles[:]:
                p["pos"] += p["vel"] * dt
                p["lifespan"] -= dt
                p["size"] -= 3 * dt
                if p["lifespan"] <= 0 or p["size"] <= 0:
                    self.death_particles.remove(p)

            if not self.death_particles:
                self.dead = True

    def draw(self, surface: pygame.Surface):
        if self.state == "alive" and self.w > 0:
            # Efeito de pulsação na intensidade do brilho
            pulse = abs(pygame.math.Vector2(1, 0).rotate(self.pulse_timer * 360).x)
            glow_alpha = int(80 + 80 * pulse)  # Varia entre 80 e 160

            # Camada de brilho externo (maior)
            glow_surface = pygame.Surface(
                (surface.get_width(), surface.get_height()), pygame.SRCALPHA
            )
            pygame.draw.line(
                glow_surface,
                (255, 100, 255, glow_alpha // 2),
                (self.x, self.y),
                (self.target_x, self.target_y),
                int(self.w) + 8,
            )
            surface.blit(glow_surface, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

            # Camada de brilho médio
            glow_surface2 = pygame.Surface(
                (surface.get_width(), surface.get_height()), pygame.SRCALPHA
            )
            pygame.draw.line(
                glow_surface2,
                (255, 150, 255, glow_alpha),
                (self.x, self.y),
                (self.target_x, self.target_y),
                int(self.w) + 4,
            )
            surface.blit(glow_surface2, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

            # Núcleo do laser (branco brilhante)
            pygame.draw.line(
                surface,
                colors.WHITE,
                (self.x, self.y),
                (self.target_x, self.target_y),
                int(self.w),
            )

        elif self.state == "dying":
            for p in self.death_particles:
                if p["size"] > 0:
                    pygame.draw.circle(
                        surface,
                        p["color"],
                        (int(p["pos"].x), int(p["pos"].y)),
                        int(p["size"]),
                    )
