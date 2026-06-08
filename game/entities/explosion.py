import math
import random

import pygame

from ..core.config import config as Config


class ExplosionType:
    """Define tipos de explosão com suas paletas de cores."""

    DEFAULT = None  # Laranja/vermelho padrão
    SLIME = [(80, 57, 89), (204, 176, 217), (38, 2, 89), (77, 13, 166), (65, 11, 140)]
    ALIEN = [(37, 217, 166), (78, 217, 74)]  # Verde
    # CITY: "static pop" — descarga elétrica azul → magenta → branco.
    CYBER = [(40, 200, 255), (180, 220, 255), (255, 50, 200), (255, 255, 255)]
    # ICE_GOLEM: colapso de núcleo glacial energético. A paleta vai do azul
    # profundo (partícula se dissipando) ao branco-gelo brilhante (energia
    # cristalina recém-liberada), passando por ciano. Ordem [morte → nascimento]
    # porque _get_color indexa por life_ratio (1 = recém-criada).
    ICE_CORE = [
        (28, 78, 168),  # azul profundo (energia esfriando)
        (44, 134, 224),  # azul elétrico
        (96, 204, 255),  # ciano gelo
        (168, 236, 255),  # ciano claro
        (228, 250, 255),  # branco-gelo (núcleo estilhaçando)
    ]


class Explosion:
    def __init__(
        self,
        x: float,
        y: float,
        size: int = 20,
        explosion_type: list[tuple[int, int, int]] | None = None,
    ):
        """
        Cria uma explosão de partículas.

        Args:
            x, y: Posição central da explosão
            size: Tamanho da explosão (afeta duração e número de partículas)
            explosion_type: Paleta de cores (ExplosionType.ALIEN, ExplosionType.SLIME, etc)
                          Se None, usa explosão padrão laranja/vermelho
        """
        self.x, self.y = x, y
        self.size = size
        self.explosion_type = explosion_type
        self.time = Config.EXPLOSION_DURATION * (size / 40)

        # Inicializar partículas
        self.particles: list[list[float]] = []
        self._create_particles()

    def _create_particles(self):
        """Cria partículas da explosão (método separado para reuso no pool)."""
        # Aumentado o limite para 100 para explosões mais dramáticas
        count = min(30 + self.size // 2, 100)
        self.particles.clear()

        for _ in range(count):
            angle = random.uniform(0, 360)
            rad_angle = math.radians(angle)
            # Velocidade baseada no tamanho
            base_speed = random.uniform(150, 350) * (self.size / 30)

            vx = base_speed * math.cos(rad_angle)
            vy = base_speed * math.sin(rad_angle)

            life = random.uniform(self.time * 0.6, self.time)
            self.particles.append([self.x, self.y, vx, vy, life])

    def reset(
        self,
        x: float,
        y: float,
        size: int = 20,
        explosion_type: list[tuple[int, int, int]] | None = None,
    ):
        """Reconfigura explosão para reuso (usado pelo pool)."""
        self.x = x
        self.y = y
        self.size = size
        self.explosion_type = explosion_type
        self.time = Config.EXPLOSION_DURATION * (size / 40)
        self._create_particles()

    def update(self, dt: float):
        self.time = max(0.0, self.time - dt)
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[2] *= 0.96
            p[3] *= 0.96
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]

    def finished(self) -> bool:
        return self.time <= 0 and not self.particles

    def _get_color(self, life_ratio: float) -> tuple[int, int, int]:
        """Calcula cor da partícula baseada no tipo de explosão e vida restante."""
        if self.explosion_type:
            # Interpolar entre cores da paleta
            color_index = int(life_ratio * (len(self.explosion_type) - 1))
            next_index = min(color_index + 1, len(self.explosion_type) - 1)
            t = (life_ratio * (len(self.explosion_type) - 1)) - color_index

            r = int(
                self.explosion_type[color_index][0]
                + t
                * (
                    self.explosion_type[next_index][0]
                    - self.explosion_type[color_index][0]
                )
            )
            g = int(
                self.explosion_type[color_index][1]
                + t
                * (
                    self.explosion_type[next_index][1]
                    - self.explosion_type[color_index][1]
                )
            )
            b = int(
                self.explosion_type[color_index][2]
                + t
                * (
                    self.explosion_type[next_index][2]
                    - self.explosion_type[color_index][2]
                )
            )
            return (r, g, b)
        else:
            # Explosão padrão: amarelo/laranja -> vermelho
            if life_ratio > 0.5:
                r = 255
                g = int(255 * ((life_ratio - 0.5) * 2))
            else:
                r = int(255 * (life_ratio * 2))
                g = 0
            return (r, g, 0)

    def draw(self, screen: pygame.Surface):
        if self.finished():
            return

        for p in self.particles:
            life_ratio = p[4] / max(self.time, 1e-6)
            color = self._get_color(life_ratio)

            pos = (int(p[0]), int(p[1]))
            # Aumentado o raio base (divisor de 10 para 6) para partículas mais encorpadas
            radius = max(1, self.size / 6 * life_ratio)
            pygame.draw.circle(screen, color, pos, radius)
