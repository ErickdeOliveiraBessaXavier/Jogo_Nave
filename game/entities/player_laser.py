import pygame
import random
import math
from typing import List, Tuple, TypedDict, Set, TYPE_CHECKING, Optional

from ..core import colors

if TYPE_CHECKING:
    from ..entities.ship import Ship


# Constantes para configuração visual
LIGHTNING_SEGMENT_LENGTH = 15
LIGHTNING_MAX_OFFSET = 15
PARTICLE_VELOCITY_RANGE = (-80, 80)
PARTICLE_SIZE_RANGE = (2, 5)
PARTICLE_LIFETIME_RANGE = (0.15, 0.4)
GLOW_ALPHA_BASE = 100
GLOW_ALPHA_AMPLITUDE = 100
SPARK_CHANCE_PER_FRAME = 0.3
SPARK_CHANCE_PER_POINT = 0.2
SPARK_LENGTH_RANGE = (5, 12)
LIGHTNING_REGENERATE_INTERVAL = (
    0.05  # Regenerar pontos a cada 50ms para efeito dinâmico
)


class DeathParticle(TypedDict):
    pos: pygame.Vector2
    vel: pygame.Vector2
    size: float
    color: Tuple[int, int, int]
    lifespan: float


class PlayerLaser:
    """Laser disparado pelo jogador que atravessa múltiplos inimigos."""

    def __init__(
        self,
        x: float,
        y: float,
        target_x: float,
        target_y: float,
        damage: int = 50,
        max_w: int = 10,
        lifetime: float = 0.8,
        ship: Optional["Ship"] = None,  # Referência à nave (opcional)
        ball_index: int = -1,  # Índice da bolinha orbital (opcional)
    ):
        self.x = x
        self.y = y
        self.target_x = target_x
        self.target_y = target_y
        self.damage = damage
        self.w = 0
        self.max_w = max_w
        self.dead = False

        # Referência para rastreamento dinâmico
        self.ship = ship
        self.ball_index = ball_index

        self.lifetime = lifetime
        self.expand_time = 0.1  # Tempo de expansão rápida
        self.hold_time = 0.5  # Tempo que mantém a largura máxima
        self.timer = 0.0

        self.state = "alive"
        self.death_particles: List[DeathParticle] = []

        # Efeito de pulsação
        self.pulse_timer = 0.0

        # Rastrear inimigos já atingidos (para não aplicar dano múltiplo)
        self.hit_enemies: Set[int] = set()

        # Gerar pontos do raio (zigzag)
        self.lightning_points = self._generate_lightning_points()
        self.lightning_regen_timer = 0.0  # Timer para regenerar pontos dinamicamente

    def _update_origin_position(self) -> None:
        """Atualiza a posição de origem do laser para seguir a bolinha orbital."""
        if self.ship is not None and self.ball_index >= 0:
            # Calcular posição atual da bolinha orbital
            angle = self.ship.orbital_angle + (
                self.ball_index * 2 * math.pi / self.ship.num_orbital_balls
            )
            self.x = (
                self.ship.x
                + self.ship.w / 2
                + math.cos(angle) * self.ship.orbital_radius
            )
            self.y = (
                self.ship.y
                + self.ship.h / 2
                + math.sin(angle) * self.ship.orbital_radius
            )

    def _generate_lightning_points(self) -> List[Tuple[float, float]]:
        """Gera pontos para criar efeito de raio zigzag."""
        points = [(self.x, self.y)]

        # Calcular direção e distância
        dx = self.target_x - self.x
        dy = self.target_y - self.y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance < 1:
            return points + [(self.target_x, self.target_y)]

        # Normalizar direção
        dir_x = dx / distance
        dir_y = dy / distance

        # Direção perpendicular para o zigzag
        perp_x = -dir_y
        perp_y = dir_x

        # Criar segmentos ao longo do raio
        num_segments = max(3, int(distance / LIGHTNING_SEGMENT_LENGTH))

        for i in range(1, num_segments):
            t = i / num_segments
            # Posição base ao longo da linha
            base_x = self.x + dx * t
            base_y = self.y + dy * t

            # Adicionar desvio perpendicular aleatório (zigzag)
            offset = random.uniform(-LIGHTNING_MAX_OFFSET, LIGHTNING_MAX_OFFSET)
            point_x = base_x + perp_x * offset
            point_y = base_y + perp_y * offset

            points.append((point_x, point_y))

        points.append((self.target_x, self.target_y))
        return points

    def get_collision_line(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Retorna a linha do laser para cálculo de colisão."""
        return (self.x, self.y), (self.target_x, self.target_y)

    def update(self, dt: float):
        self.timer += dt
        self.pulse_timer += dt * 10  # Velocidade da pulsação

        # Atualizar posição de origem se estiver vinculado a uma bolinha orbital
        if self.state == "alive":
            self._update_origin_position()

        # Regenerar pontos do raio periodicamente para efeito dinâmico
        if self.state == "alive":
            self.lightning_regen_timer += dt
            if self.lightning_regen_timer >= LIGHTNING_REGENERATE_INTERVAL:
                self.lightning_points = self._generate_lightning_points()
                self.lightning_regen_timer = 0.0

        if self.state == "alive":
            if self.timer >= self.lifetime:
                self.state = "dying"
                self.w = 0
                # Gerar partículas de morte ao longo da linha
                start_pos = pygame.Vector2(self.x, self.y)
                end_pos = pygame.Vector2(self.target_x, self.target_y)
                line_vec = end_pos - start_pos
                line_length = line_vec.length()
                if line_length > 0:
                    line_vec.normalize_ip()

                # Criar partículas ao longo do laser
                num_particles = int(line_length / LIGHTNING_SEGMENT_LENGTH)
                for i in range(num_particles):
                    pos_on_line = start_pos + line_vec * (
                        i * LIGHTNING_SEGMENT_LENGTH
                        + random.uniform(0, LIGHTNING_SEGMENT_LENGTH)
                    )
                    particle: DeathParticle = {
                        "pos": pos_on_line,
                        "vel": pygame.Vector2(
                            random.uniform(*PARTICLE_VELOCITY_RANGE),
                            random.uniform(*PARTICLE_VELOCITY_RANGE),
                        ),
                        "size": random.uniform(*PARTICLE_SIZE_RANGE),
                        "color": random.choice(
                            [colors.CYAN, colors.BLUE, (100, 200, 255)]
                        ),
                        "lifespan": random.uniform(*PARTICLE_LIFETIME_RANGE),
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
            # Atualizar partículas
            for p in self.death_particles:
                p["pos"] += p["vel"] * dt
                p["lifespan"] -= dt
                p["size"] -= 5 * dt

            # Remover partículas mortas (list comprehension é mais eficiente que remove())
            self.death_particles = [
                p for p in self.death_particles if p["lifespan"] > 0 and p["size"] > 0
            ]

            if not self.death_particles:
                self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        if self.state == "alive" and self.w > 0:
            # Verificação de segurança
            if len(self.lightning_points) < 2:
                return

            # Efeito de pulsação simplificado (mais eficiente)
            pulse = abs(math.sin(self.pulse_timer))
            glow_alpha = int(GLOW_ALPHA_BASE + GLOW_ALPHA_AMPLITUDE * pulse)

            # Calcular bounding box do raio para criar superfície otimizada
            min_x = min(p[0] for p in self.lightning_points) - 15
            max_x = max(p[0] for p in self.lightning_points) + 15
            min_y = min(p[1] for p in self.lightning_points) - 15
            max_y = max(p[1] for p in self.lightning_points) + 15

            # Criar superfície apenas do tamanho necessário (otimização crítica)
            width = int(max_x - min_x)
            height = int(max_y - min_y)

            if width > 0 and height > 0:
                glow_surface = pygame.Surface((width, height), pygame.SRCALPHA)

                # Ajustar coordenadas dos pontos para a nova superfície
                offset_x = min_x
                offset_y = min_y

                # Desenhar todos os segmentos na superfície local
                for i in range(len(self.lightning_points) - 1):
                    start = (
                        self.lightning_points[i][0] - offset_x,
                        self.lightning_points[i][1] - offset_y,
                    )
                    end = (
                        self.lightning_points[i + 1][0] - offset_x,
                        self.lightning_points[i + 1][1] - offset_y,
                    )

                    # Brilho externo (azul claro)
                    pygame.draw.line(
                        glow_surface,
                        (100, 200, 255, glow_alpha // 3),
                        start,
                        end,
                        int(self.w) + 6,
                    )

                    # Brilho médio (ciano)
                    pygame.draw.line(
                        glow_surface,
                        (150, 255, 255, glow_alpha // 2),
                        start,
                        end,
                        int(self.w) + 3,
                    )

                # Aplicar brilho na posição correta da tela
                surface.blit(
                    glow_surface,
                    (int(min_x), int(min_y)),
                    special_flags=pygame.BLEND_RGBA_ADD,
                )

                # Desenhar núcleo do raio diretamente na superfície principal
                for i in range(len(self.lightning_points) - 1):
                    start = self.lightning_points[i]
                    end = self.lightning_points[i + 1]
                    pygame.draw.line(
                        surface, colors.WHITE, start, end, max(2, int(self.w))
                    )

                # Adicionar pequenos "sparks" ocasionais
                if random.random() < SPARK_CHANCE_PER_FRAME:
                    for point in self.lightning_points[1:-1]:
                        if random.random() < SPARK_CHANCE_PER_POINT:
                            spark_length = random.uniform(*SPARK_LENGTH_RANGE)
                            spark_angle = random.uniform(0, 360)
                            spark_vec = pygame.math.Vector2(spark_length, 0).rotate(
                                spark_angle
                            )
                            spark_end = (point[0] + spark_vec.x, point[1] + spark_vec.y)
                            pygame.draw.line(
                                surface, (200, 240, 255), point, spark_end, 1
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
