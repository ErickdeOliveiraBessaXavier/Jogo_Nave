import random
from typing import Any, List, Set, Tuple

import pygame

from ...core.config import config as Config
from ..effects.particle_types import DeathParticle


Color = Tuple[int, int, int]

# Cores PADRÃO do feixe (vermelho). Ficam como default porque esta classe tem
# mais de um dono: além do boss, ela é o laser carregado do Caçador
# (`EntityManager.spawn_cacador_laser`) — recolorir a classe inteira pintaria o
# tiro do JOGADOR junto. Quem quer outra identidade passa as cores no construtor;
# é o que o `Boss` faz para o azul dele. (`MetropolisOrbitalBeam` e `FenceBeam`
# são subclasses que sobrescrevem `draw` por completo, então não passam por aqui.)
DEFAULT_GLOW_COLOR: Color = (255, 100, 100)
DEFAULT_CORE_COLOR: Color = (255, 255, 255)
DEFAULT_SPARK_COLORS: Tuple[Color, ...] = (
    (255, 255, 200),
    (255, 220, 150),
    (255, 255, 255),
)


class BossLaser:
    def __init__(
        self,
        x: float,
        y: float,
        target_x: float,
        target_y: float,
        lifetime: float = Config.BOSS_LASER_LIFETIME,
        damage: int = 0,
        owner_ship: Any | None = None,
        owner: Any | None = None,
        start_delay: float = 0.0,
        glow_color: Color = DEFAULT_GLOW_COLOR,
        core_color: Color = DEFAULT_CORE_COLOR,
        spark_colors: Tuple[Color, ...] = DEFAULT_SPARK_COLORS,
    ):
        self.glow_color = glow_color
        self.core_color = core_color
        self.spark_colors = spark_colors
        self.x = x
        self.y = y
        self.target_x = target_x
        self.target_y = target_y
        self.owner = owner
        
        # Guarda offsets se houver dono
        if owner:
            self.offset_x = x - owner.x
            self.offset_y = y - owner.y
            self.target_offset_x = target_x - owner.x
            self.target_offset_y = target_y - owner.y

        self.w = 0
        self.max_w = 18
        self.dead = False
        self.damage = damage
        self.hit_enemies: Set[int] = set()
        # Para o caso de uso como cacador_laser (charge shot do Magneto),
        # rastreia a nave de origem para atribuição de kill no combo.
        self.owner_ship = owner_ship

        self.lifetime = lifetime
        self.expand_time = 0.1
        self.hold_time = 0.3
        # timer can be started negative to implement a start delay
        self.timer = -float(start_delay)

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
        
        # Seguir o dono se ele existir
        if self.owner and not getattr(self.owner, "dead", False):
            self.x = self.owner.x + self.offset_x
            self.y = self.owner.y + self.offset_y
            self.target_x = self.owner.x + self.target_offset_x
            self.target_y = self.owner.y + self.target_offset_y

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
                            "color": random.choice(self.spark_colors),
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
            for p in self.death_particles:
                p["pos"] += p["vel"] * dt
                p["lifespan"] -= dt
                p["size"] -= 3 * dt  # Encolhem rapidamente

            self.death_particles = [
                p for p in self.death_particles if p["lifespan"] > 0 and p["size"] > 0
            ]

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
                glow = (*self.glow_color, alpha)
                pygame.draw.line(
                    surface, glow, start_point, end_point, line_width + 6
                )

            # Núcleo do raio (linha sólida)
            pygame.draw.line(
                surface, self.core_color, start_point, end_point, line_width
            )

        elif self.state == "dying":
            # Desenha as partículas de dissipação
            for p in self.death_particles:
                pygame.draw.circle(surface, p["color"], p["pos"], p["size"])
