import math
import random
from typing import TYPE_CHECKING, Any, List, Literal, Optional, Set, Tuple, TypedDict

import pygame

from ..core import colors

if TYPE_CHECKING:
    from ..entities.ship import Ship


# Constantes para configuração visual
LIGHTNING_SEGMENT_LENGTH: int = 15
LIGHTNING_MAX_OFFSET: int = 15
PARTICLE_VELOCITY_RANGE: Tuple[int, int] = (-80, 80)
PARTICLE_SIZE_RANGE: Tuple[int, int] = (2, 5)
PARTICLE_LIFETIME_RANGE: Tuple[float, float] = (0.15, 0.4)
GLOW_ALPHA_BASE: int = 100
GLOW_ALPHA_AMPLITUDE: int = 100
SPARK_CHANCE_PER_FRAME: float = 0.3
SPARK_CHANCE_PER_POINT: float = 0.2
SPARK_LENGTH_RANGE: Tuple[int, int] = (5, 12)
LIGHTNING_REGENERATE_INTERVAL: float = 0.05

# Pré-computar valores para otimização
TWO_PI = 2 * math.pi
PARTICLE_SIZE_DECAY = 5.0
MIN_POSITION_CHANGE = 1.0


class DeathParticle(TypedDict):
    pos: Tuple[float, float]
    vel: Tuple[float, float]
    size: float
    color: Tuple[int, int, int]
    lifespan: float


class PlayerLaser:
    """Laser disparado pelo jogador que atravessa múltiplos inimigos."""

    # Cache de superfícies para reutilização (class-level)
    _glow_cache: dict[str, pygame.Surface] = {}
    _max_cache_size: int = 10

    def __init__(
        self,
        x: float,
        y: float,
        target_x: float,
        target_y: float,
        damage: int = 50,
        max_w: int = 10,
        lifetime: float = 0.8,
        ship: Optional["Ship"] = None,
        ball_index: int = -1,
        target_entity: Optional[Any] = None,
    ) -> None:
        self.x: float = x
        self.y: float = y
        self.target_x: float = target_x
        self.target_y: float = target_y
        self.damage: int = damage
        self.w: float = max_w * 0.3  # Começar com 30% da largura para colisão imediata
        self.max_w: int = max_w
        self.dead: bool = False

        self.ship: Optional["Ship"] = ship
        self.ball_index: int = ball_index
        self.target_entity: Optional[Any] = target_entity

        self.lifetime: float = lifetime
        self.expand_time: float = 0.1
        self.hold_time: float = 0.5
        self.timer: float = 0.0

        self.state: Literal["alive", "dying"] = "alive"
        self.death_particles: List[DeathParticle] = []

        self.pulse_timer: float = 0.0
        self.hit_enemies: Set[int] = set()

        # Cache para cálculos repetidos
        self._last_distance: float = 0.0
        self._dir_x: float = 0.0
        self._dir_y: float = 0.0
        self._perp_x: float = 0.0
        self._perp_y: float = 0.0

        # Otimização: pré-alocar lista de pontos com tamanho fixo estimado
        self.lightning_points: List[Tuple[float, float]] = []
        self.lightning_regen_timer: float = 0.0

        # Inicializar pontos
        self._generate_lightning_points()

    def _update_origin_position(self) -> None:
        """Atualiza a posição de origem do laser para seguir a bolinha orbital."""
        if self.ship is not None and self.ball_index >= 0:
            # Cache de valores para evitar recálculos
            angle = self.ship.orbital_angle + (
                self.ball_index * TWO_PI / self.ship.num_orbital_balls
            )
            cos_angle = math.cos(angle)
            sin_angle = math.sin(angle)

            half_w = self.ship.w * 0.5
            half_h = self.ship.h * 0.5

            self.x = self.ship.x + half_w + cos_angle * self.ship.orbital_radius
            self.y = self.ship.y + half_h + sin_angle * self.ship.orbital_radius

    def _update_target_position(self) -> None:
        """Atualiza a posição do alvo se houver uma entidade alvo para rastreamento dinâmico."""
        if self.target_entity is None:
            return

        try:
            # Verificar se o alvo está morto - parar de rastrear
            if hasattr(self.target_entity, "dead") and self.target_entity.dead:
                self.target_entity = None
                return

            old_target_x, old_target_y = self.target_x, self.target_y

            # Otimização: usar hasattr uma única vez
            entity = self.target_entity
            if hasattr(entity, "w"):
                self.target_x = entity.x + entity.w * 0.5
                self.target_y = entity.y + entity.h * 0.5
            elif hasattr(entity, "radius"):
                self.target_x = entity.x
                self.target_y = entity.y
            else:
                self.target_entity = None
                return

            # Otimização: usar diferença ao quadrado para evitar abs()
            dx_sq = (self.target_x - old_target_x) ** 2
            dy_sq = (self.target_y - old_target_y) ** 2

            if dx_sq > MIN_POSITION_CHANGE or dy_sq > MIN_POSITION_CHANGE:
                self._generate_lightning_points()
                self.lightning_regen_timer = 0.0
        except (AttributeError, TypeError):
            self.target_entity = None

    def _generate_lightning_points(self) -> None:
        """Gera pontos para criar efeito de raio zigzag."""
        dx = self.target_x - self.x
        dy = self.target_y - self.y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance < 1:
            self.lightning_points = [(self.x, self.y), (self.target_x, self.target_y)]
            return

        # Cache de valores calculados
        inv_distance = 1.0 / distance
        self._dir_x = dx * inv_distance
        self._dir_y = dy * inv_distance
        self._perp_x = -self._dir_y
        self._perp_y = self._dir_x
        self._last_distance = distance

        # Calcular número de segmentos
        num_segments = max(3, int(distance / LIGHTNING_SEGMENT_LENGTH))
        inv_segments = 1.0 / num_segments

        # Pré-alocar lista com tamanho exato
        points = [(self.x, self.y)]

        # Otimização: usar operações mais simples no loop
        for i in range(1, num_segments):
            t = i * inv_segments
            offset = random.uniform(-LIGHTNING_MAX_OFFSET, LIGHTNING_MAX_OFFSET)

            # Calcular ponto diretamente
            point_x = self.x + dx * t + self._perp_x * offset
            point_y = self.y + dy * t + self._perp_y * offset
            points.append((point_x, point_y))

        points.append((self.target_x, self.target_y))
        self.lightning_points = points

    def get_collision_line(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Retorna a linha do laser para cálculo de colisão."""
        return (self.x, self.y), (self.target_x, self.target_y)

    def update(self, dt: float) -> None:
        self.timer += dt
        self.pulse_timer += dt * 10

        if self.state == "alive":
            self._update_origin_position()
            self._update_target_position()

            # Regenerar pontos do raio periodicamente
            self.lightning_regen_timer += dt
            if self.lightning_regen_timer >= LIGHTNING_REGENERATE_INTERVAL:
                self._generate_lightning_points()
                self.lightning_regen_timer = 0.0

            if self.timer >= self.lifetime:
                self._start_death_animation()
                return

            # Calcular largura com suavização
            self._update_width()

        elif self.state == "dying":
            # Otimização: atualizar e filtrar partículas em um único loop
            alive_particles: List[DeathParticle] = []
            for p in self.death_particles:
                old_pos = p["pos"]
                vel = p["vel"]
                new_lifespan = p["lifespan"] - dt
                new_size = p["size"] - PARTICLE_SIZE_DECAY * dt

                if new_lifespan > 0 and new_size > 0:
                    p["pos"] = (old_pos[0] + vel[0] * dt, old_pos[1] + vel[1] * dt)
                    p["lifespan"] = new_lifespan
                    p["size"] = new_size
                    alive_particles.append(p)

            self.death_particles = alive_particles

            if not self.death_particles:
                self.dead = True

    def _update_width(self) -> None:
        """Atualiza a largura do laser com suavização."""
        if self.timer < self.expand_time:
            progress = self.timer / self.expand_time
            # Expandir de 30% até 100% da largura máxima
            self.w = self.max_w * (0.3 + 0.7 * (1 - (1 - progress) ** 2))
        elif self.timer < self.expand_time + self.hold_time:
            self.w = self.max_w
        else:
            shrink_duration = self.lifetime - (self.expand_time + self.hold_time)
            if shrink_duration > 0:
                progress = (
                    self.timer - (self.expand_time + self.hold_time)
                ) / shrink_duration
                self.w = self.max_w * (1 - progress**2)
        self.w = max(0, self.w)

    def _start_death_animation(self) -> None:
        """Inicia a animação de morte do laser."""
        self.state = "dying"
        self.w = 0

        # Otimização: calcular valores uma única vez
        dx = self.target_x - self.x
        dy = self.target_y - self.y
        line_length = math.sqrt(dx * dx + dy * dy)

        if line_length > 0:
            inv_length = 1.0 / line_length
            norm_x = dx * inv_length
            norm_y = dy * inv_length

            num_particles = int(line_length / LIGHTNING_SEGMENT_LENGTH)

            # Pré-computar cores possíveis
            particle_colors = [colors.CYAN, colors.BLUE, (100, 200, 255)]

            for i in range(num_particles):
                dist = i * LIGHTNING_SEGMENT_LENGTH + random.uniform(
                    0, LIGHTNING_SEGMENT_LENGTH
                )
                pos_x = self.x + norm_x * dist
                pos_y = self.y + norm_y * dist

                particle: DeathParticle = {
                    "pos": (pos_x, pos_y),
                    "vel": (
                        random.uniform(*PARTICLE_VELOCITY_RANGE),
                        random.uniform(*PARTICLE_VELOCITY_RANGE),
                    ),
                    "size": random.uniform(*PARTICLE_SIZE_RANGE),
                    "color": random.choice(particle_colors),
                    "lifespan": random.uniform(*PARTICLE_LIFETIME_RANGE),
                }
                self.death_particles.append(particle)

    def draw(self, surface: pygame.Surface) -> None:
        if self.state == "alive" and self.w > 0:
            if len(self.lightning_points) < 2:
                return

            # Otimização: calcular pulsação mais eficientemente
            pulse = abs(math.sin(self.pulse_timer))
            glow_alpha = int(GLOW_ALPHA_BASE + GLOW_ALPHA_AMPLITUDE * pulse)

            # Calcular bounding box (otimizado com list comprehension)
            x_coords = [p[0] for p in self.lightning_points]
            y_coords = [p[1] for p in self.lightning_points]

            min_x = min(x_coords) - 15
            max_x = max(x_coords) + 15
            min_y = min(y_coords) - 15
            max_y = max(y_coords) + 15

            width = int(max_x - min_x)
            height = int(max_y - min_y)

            if width > 0 and height > 0:
                # Criar superfície de brilho
                glow_surface = pygame.Surface((width, height), pygame.SRCALPHA)

                offset_x = min_x
                offset_y = min_y

                # Pré-calcular espessuras
                w_int = int(self.w)
                thick1 = w_int + 6
                thick2 = w_int + 3
                thick3 = max(2, w_int)

                # Pré-calcular cores com alpha
                color1 = (100, 200, 255, glow_alpha // 3)
                color2 = (150, 255, 255, glow_alpha // 2)

                # Desenhar todos os segmentos
                points_len = len(self.lightning_points)
                for i in range(points_len - 1):
                    p1 = self.lightning_points[i]
                    p2 = self.lightning_points[i + 1]

                    start = (p1[0] - offset_x, p1[1] - offset_y)
                    end = (p2[0] - offset_x, p2[1] - offset_y)

                    pygame.draw.line(glow_surface, color1, start, end, thick1)
                    pygame.draw.line(glow_surface, color2, start, end, thick2)

                # Aplicar brilho
                surface.blit(
                    glow_surface,
                    (int(min_x), int(min_y)),
                    special_flags=pygame.BLEND_RGBA_ADD,
                )

                # Desenhar núcleo do raio
                for i in range(points_len - 1):
                    pygame.draw.line(
                        surface,
                        colors.WHITE,
                        self.lightning_points[i],
                        self.lightning_points[i + 1],
                        thick3,
                    )

                # Adicionar sparks ocasionais
                if random.random() < SPARK_CHANCE_PER_FRAME:
                    for point in self.lightning_points[1:-1]:
                        if random.random() < SPARK_CHANCE_PER_POINT:
                            spark_length = random.uniform(*SPARK_LENGTH_RANGE)
                            spark_angle = random.uniform(0, 360)

                            # Otimização: usar radianos diretamente
                            angle_rad = math.radians(spark_angle)
                            spark_x = point[0] + spark_length * math.cos(angle_rad)
                            spark_y = point[1] + spark_length * math.sin(angle_rad)

                            pygame.draw.line(
                                surface, (200, 240, 255), point, (spark_x, spark_y), 1
                            )

        elif self.state == "dying":
            # Otimização: desenhar partículas com menos conversões
            for p in self.death_particles:
                size = int(p["size"])
                if size > 0:
                    pos = p["pos"]
                    pygame.draw.circle(
                        surface,
                        p["color"],
                        (int(pos[0]), int(pos[1])),
                        size,
                    )
