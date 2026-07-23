import random
from typing import List, Optional, TYPE_CHECKING

import pygame

from ...core import colors
from .laser_utils import compute_laser_width
from ..effects.particle_types import DeathParticle

if TYPE_CHECKING:
    from ..bosses.spike_boss import SpikeBoss


class SpikeBossLaser:
    """
    Laser gigante disparado pelo SpikeBoss no modo frenzy.
    Similar ao EyeLaser mas com largura maior (mesma do boss).
    """

    def __init__(
        self,
        x: float,
        y: float,
        target_y: float,
        width: int = 120,
        lifetime: float = 1.5,
        owner: Optional["SpikeBoss"] = None,
    ):
        """
        Args:
            x: Posição X inicial (centro do laser)
            y: Posição Y inicial (parte inferior da abertura)
            target_y: Posição Y final (fundo da tela)
            width: Largura do laser (mesma do boss)
            lifetime: Duração total do laser
            owner: Referência ao SpikeBoss para seguir sua posição
        """
        self.x = x
        self.y = y
        self.target_y = target_y
        self.owner = owner
        
        # Guarda offsets se houver dono
        if owner:
            self.offset_x = x - owner.x
            self.offset_y = y - owner.y

        self.w = 0
        self.max_w = width * 0.70
        self.dead = False

        self.lifetime = lifetime
        self.expand_time = 0.2  # Expansão rápida
        self.hold_time = 0.8  # Segura o laser por um tempo
        self.timer = 0.0

        self.state = "alive"
        self.death_particles: List[DeathParticle] = []

        # Efeito de pulsação
        self.pulse_timer = 0.0

    def get_collision_rect(self) -> pygame.Rect:
        """Retorna retângulo para detecção de colisão."""
        # Criar retângulo vertical do laser
        left = self.x - self.w / 2
        top = self.y
        height = self.target_y - self.y
        return pygame.Rect(int(left), int(top), int(self.w), int(height))

    def update(self, dt: float):
        self.timer += dt
        self.pulse_timer += dt * 10  # Velocidade da pulsação

        # Seguir o dono se ele existir
        if self.owner and not self.owner.dead:
            self.x = self.owner.x + self.offset_x
            self.y = self.owner.y + self.offset_y

        if self.state == "alive":
            if self.timer >= self.lifetime:
                self.state = "dying"
                self.w = 0

                # Criar partículas de morte ao longo do laser
                num_particles = 30
                for i in range(num_particles):
                    y_pos = self.y + (self.target_y - self.y) * (i / num_particles)
                    particle: DeathParticle = {
                        "pos": pygame.Vector2(
                            self.x + random.uniform(-self.max_w / 2, self.max_w / 2),
                            y_pos,
                        ),
                        "vel": pygame.Vector2(
                            random.uniform(-150, 150), random.uniform(-100, 100)
                        ),
                        "size": random.uniform(3, 6),
                        "color": random.choice(
                            [colors.RED, colors.DARK_RED, colors.YELLOW, colors.WHITE]
                        ),
                        "lifespan": random.uniform(0.3, 0.6),
                    }
                    self.death_particles.append(particle)
                return

            self.w = compute_laser_width(
                self.timer, self.expand_time, self.hold_time, self.lifetime, self.max_w
            )

        elif self.state == "dying":
            for p in self.death_particles:  # §6: update in-place, rebuild abaixo
                p["pos"] += p["vel"] * dt
                p["lifespan"] -= dt
                p["size"] -= 4 * dt
            self.death_particles = [
                p
                for p in self.death_particles
                if p["lifespan"] > 0 and p["size"] > 0
            ]

            if not self.death_particles:
                self.dead = True

    def draw(self, surface: pygame.Surface):
        if self.state == "alive" and self.w > 0:
            # Efeito de pulsação na intensidade do brilho
            pulse = abs(pygame.math.Vector2(1, 0).rotate(self.pulse_timer * 360).x)
            glow_alpha = int(100 + 100 * pulse)  # Varia entre 100 e 200

            # Camada de brilho externo (maior) - vermelho
            glow_surface = pygame.Surface(
                (surface.get_width(), surface.get_height()), pygame.SRCALPHA
            )
            pygame.draw.rect(
                glow_surface,
                (255, 50, 50, glow_alpha // 3),
                (
                    int(self.x - self.w / 2 - 15),
                    int(self.y),
                    int(self.w + 30),
                    int(self.target_y - self.y),
                ),
            )
            surface.blit(glow_surface, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

            # Camada de brilho médio - vermelho/laranja
            glow_surface2 = pygame.Surface(
                (surface.get_width(), surface.get_height()), pygame.SRCALPHA
            )
            pygame.draw.rect(
                glow_surface2,
                (255, 100, 50, glow_alpha // 2),
                (
                    int(self.x - self.w / 2 - 8),
                    int(self.y),
                    int(self.w + 16),
                    int(self.target_y - self.y),
                ),
            )
            surface.blit(glow_surface2, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

            # Núcleo do laser (vermelho intenso para amarelo)
            core_rect = pygame.Rect(
                int(self.x - self.w / 2),
                int(self.y),
                int(self.w),
                int(self.target_y - self.y),
            )
            pygame.draw.rect(surface, colors.RED, core_rect)

            # Centro mais claro (amarelo)
            inner_rect = pygame.Rect(
                int(self.x - self.w / 4),
                int(self.y),
                int(self.w / 2),
                int(self.target_y - self.y),
            )
            pygame.draw.rect(surface, colors.YELLOW, inner_rect)

        elif self.state == "dying":
            for p in self.death_particles:
                if p["size"] > 0:
                    pygame.draw.circle(
                        surface,
                        p["color"],
                        (int(p["pos"].x), int(p["pos"].y)),
                        int(p["size"]),
                    )
