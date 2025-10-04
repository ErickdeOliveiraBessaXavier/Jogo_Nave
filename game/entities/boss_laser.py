import random
from typing import List, Tuple, TypedDict

import pygame

from ..core.config import Config


class DeathParticle(TypedDict):
    """Type definition for laser death particles."""

    pos: pygame.Vector2
    vel: pygame.Vector2
    size: float
    color: Tuple[int, int, int]
    lifespan: float


class BossLaser:
    def __init__(
        self,
        x: float,
        y: float,
        target_x: float,
        target_y: float,
        lifetime: float = Config.BOSS_LASER_LIFETIME,
    ):
        self.x = x
        self.y = y
        self.target_x = target_x
        self.target_y = target_y
        self.w = 0
        self.max_w = 18
        self.dead = False

        self.lifetime = Config.BOSS_LASER_LIFETIME
        self.expand_time = 0.1
        self.hold_time = 0.3
        self.timer = 0.0

        self.state = "alive"
        self.death_particles: List[DeathParticle] = []

    @property
    def rect(self) -> pygame.Rect:
        # Retorna um rect simples para propósitos de desenho (bounding box)
        min_x = min(self.x, self.target_x)
        max_x = max(self.x, self.target_x)
        min_y = min(self.y, self.target_y)
        max_y = max(self.y, self.target_y)
        return pygame.Rect(min_x, min_y, max_x - min_x, max_y - min_y)

    def get_collision_line(self) -> tuple[tuple[float, float], tuple[float, float]]:
        return (self.x, self.y), (self.target_x, self.target_y)

    def update(self, dt: float) -> None:
        self.timer += dt

        if self.state == "alive":
            if self.timer >= self.lifetime:
                self.state = "dying"
                self.w = 0  # O raio do laser desaparece
                # Gera uma explosão de partículas ao longo do caminho do laser
                # Ajustar a geração de partículas para seguir a linha inclinada
                start_pos = pygame.Vector2(self.x, self.y)
                end_pos = pygame.Vector2(self.target_x, self.target_y)
                line_vec = end_pos - start_pos
                line_length = line_vec.length()
                if line_length > 0:
                    line_vec.normalize_ip()

                num_particles_along_line = int(line_length / 25)
                for i in range(num_particles_along_line):
                    pos_on_line = start_pos + line_vec * (
                        i * 25 + random.uniform(0, 25)
                    )
                    for _ in range(2):
                        particle: DeathParticle = {
                            "pos": pos_on_line
                            + pygame.Vector2(
                                random.uniform(-self.max_w / 2, self.max_w / 2),
                                random.uniform(-self.max_w / 2, self.max_w / 2),
                            ),
                            "vel": pygame.Vector2(
                                random.uniform(-180, 180), random.uniform(-80, 80)
                            ),
                            "size": random.uniform(2, 5),
                            "color": random.choice(
                                [(255, 255, 200), (255, 220, 150), (255, 255, 255)]
                            ),
                            "lifespan": random.uniform(0.2, 0.4),
                        }
                        self.death_particles.append(particle)
                return

            # Lógica da animação de largura
            if self.timer < self.expand_time:
                progress = self.timer / self.expand_time
                self.w = self.max_w * progress
            elif self.timer < self.expand_time + self.hold_time:
                self.w = self.max_w
            else:
                shrink_duration = self.lifetime - (self.expand_time + self.hold_time)
                progress = (
                    self.timer - (self.expand_time + self.hold_time)
                ) / shrink_duration
                self.w = self.max_w * (1 - progress)
            self.w = max(0, self.w)

        elif self.state == "dying":
            # Atualiza as partículas de dissipação
            for p in self.death_particles[:]:
                p["pos"] += p["vel"] * dt
                p["lifespan"] -= dt
                p["size"] -= 3 * dt  # Encolhem rapidamente
                if p["lifespan"] <= 0 or p["size"] <= 0:
                    self.death_particles.remove(p)

            # Quando todas as partículas somem, a entidade pode ser removida
            if not self.death_particles:
                self.dead = True

    def is_animation_finished(self) -> bool:
        return self.dead

    def draw(self, surface: pygame.Surface) -> None:
        if self.state == "alive" and self.w > 0:
            start_point = (int(self.x), int(self.y))
            end_point = (int(self.target_x), int(self.target_y))
            line_width = int(self.w)

            # Efeito de brilho (linha mais grossa e transparente)
            if line_width > 0:
                alpha = 100  # Transparência
                glow_color = (255, 100, 100, alpha)
                pygame.draw.line(
                    surface, glow_color, start_point, end_point, line_width + 6
                )

            # Núcleo do raio (linha sólida)
            pygame.draw.line(
                surface, (255, 255, 255), start_point, end_point, line_width
            )

        elif self.state == "dying":
            # Desenha as partículas de dissipação
            for p in self.death_particles:
                pygame.draw.circle(surface, p["color"], p["pos"], p["size"])
