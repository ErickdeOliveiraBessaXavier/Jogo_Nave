import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable, Optional, Set, Union

import pygame

if TYPE_CHECKING:
    from ..entities.alien import Alien
    from ..entities.bot_elemental import ElementalRobot
    from ..entities.explosive_mine import ExplosiveMine
    from ..entities.eye_enemy import EyeEnemy
    from ..entities.meteor import Meteor
    from ..entities.square_minion_boss import SquareMinionBoss

EnemyType = Union[
    "Meteor", "Alien", "ExplosiveMine", "EyeEnemy", "SquareMinionBoss", "ElementalRobot"
]


class MineState(Enum):
    """Estados possíveis da mina."""

    FLYING = "flying"
    LANDED = "landed"
    ARMED = "armed"
    EXPLODING = "exploding"
    DONE = "done"


@dataclass
class DamageInfo:
    """Informações sobre dano em área."""

    x: float
    y: float
    radius: float
    damage: int


class MineConfig:
    """Constantes de configuração da mina."""

    EXPLOSION_DURATION = 0.3
    DAMAGE_DURATION = 0.15
    ARMING_DURATION = 2.5
    TRAVEL_TIME = 1.5
    ARC_HEIGHT = 150
    BASE_RADIUS = 12
    MAX_SPIKE_LENGTH = 8
    TRAIL_MAX_LENGTH = 8
    PROGRESS_POINTS = 32


class CannonMine:
    """Mina tática com visual de energia e efeitos de partículas."""

    def __init__(
        self,
        target_x: float,
        target_y: float,
        launch_x: float,
        launch_y: float,
        explosion_radius: float = 70.0,  # Aumentei um pouco
        damage: int = 80,
        on_explode: Optional[Callable[[], None]] = None,
    ):
        self.target_x = target_x
        self.target_y = target_y
        self.explosion_radius = explosion_radius
        self.damage = damage
        self.on_explode = on_explode

        self.launch_x = launch_x
        self.launch_y = launch_y
        self.x = launch_x
        self.y = launch_y

        self.distance = ((target_x - launch_x) ** 2 + (target_y - launch_y) ** 2) ** 0.5
        self.travel_time = MineConfig.TRAVEL_TIME
        self.time_elapsed = 0.0

        self.vx = (target_x - launch_x) / self.travel_time
        self.vy = (target_y - launch_y) / self.travel_time

        self.state = MineState.FLYING
        self.arming_timer = 0.0
        self.arming_duration = MineConfig.ARMING_DURATION
        self.dead = False
        self.exploded = False

        self.explosion_timer = 0.0
        self.explosion_duration = MineConfig.EXPLOSION_DURATION

        # Duração estendida para causar dano aos fragmentos
        self.damage_duration = MineConfig.DAMAGE_DURATION
        self.damage_timer = 0.0

        self.hit_enemies: Set[int] = set()
        self.hit_enemies_extended: Set[int] = set()  # Para dano estendido
        self.w = 24
        self.h = 24

        # Histórico de posições para o rastro (trail)
        self.trail_positions: list[tuple[float, float]] = []

        # Animação dos espinhos
        self.spike_rotation = 0.0
        self.spike_emerge_timer = 0.0

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(
            int(self.x - self.w // 2), int(self.y - self.h // 2), self.w, self.h
        )

    def update(self, dt: float) -> None:
        if self.dead:
            return

        # Atualizar animação dos espinhos
        self.spike_rotation += dt * 2.0  # Rotação contínua
        self.spike_emerge_timer += dt * 3.0  # Velocidade de emergir/imergir

        if self.state == MineState.FLYING:
            self.time_elapsed += dt

            # Atualizar rastro (manter os últimos frames)
            self.trail_positions.append((self.x, self.y))
            if len(self.trail_positions) > MineConfig.TRAIL_MAX_LENGTH:
                self.trail_positions.pop(0)

            if self.time_elapsed >= self.travel_time:
                self.x = self.target_x
                self.y = self.target_y
                self.state = MineState.LANDED
                self.arming_timer = 0.0
                self.trail_positions.clear()
            else:
                progress = self.time_elapsed / self.travel_time
                self.x = self.launch_x + self.vx * self.time_elapsed
                base_y = self.launch_y + self.vy * self.time_elapsed
                parabolic_offset = (
                    -4 * MineConfig.ARC_HEIGHT * progress * (progress - 1)
                )
                self.y = base_y - parabolic_offset

        elif self.state == MineState.LANDED:
            self.arming_timer += dt
            if self.arming_timer >= self.arming_duration:
                self.state = MineState.ARMED

        elif self.state == MineState.EXPLODING:
            self.explosion_timer += dt
            self.damage_timer += dt
            if self.explosion_timer >= self.explosion_duration:
                self.state = MineState.DONE
                # Usar novo set para dano estendido
                self.hit_enemies_extended = set()

        elif self.state == MineState.DONE:
            self.damage_timer += dt
            if self.damage_timer >= self.explosion_duration + self.damage_duration:
                self.dead = True

    def check_enemy_collision(self, enemy: EnemyType) -> bool:
        if self.state != MineState.ARMED or self.dead:
            return False

        enemy_id = id(enemy)
        if enemy_id in self.hit_enemies:
            return False

        enemy_rect = getattr(enemy, "rect", None)
        if enemy_rect and self.rect.colliderect(enemy_rect):
            self.explode()
            return True
        return False

    def explode(self) -> None:
        if self.state == MineState.EXPLODING or self.dead:
            return
        self.state = MineState.EXPLODING
        self.explosion_timer = 0.0
        self.damage_timer = 0.0  # Reset damage timer
        self.exploded = True
        if self.on_explode:
            self.on_explode()

    @property
    def damage_info(self) -> DamageInfo:
        """Informações sobre dano em área da mina."""
        total_damage_time = self.explosion_duration + self.damage_duration
        if self.state == MineState.EXPLODING or (
            self.state == MineState.DONE and self.damage_timer < total_damage_time
        ):
            return DamageInfo(self.x, self.y, self.explosion_radius, self.damage)
        return DamageInfo(0, 0, 0, 0)

    @property
    def hit_tracking_set(self) -> Set[int]:
        """Retorna o set apropriado para tracking de hits."""
        return (
            self.hit_enemies
            if self.state == MineState.EXPLODING
            else self.hit_enemies_extended
        )

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead or self.state == MineState.DONE:
            return

        # Paleta de cores consistente - apenas tons de azul
        if self.state == MineState.FLYING:
            base_color = (100, 150, 255)  # Azul claro
            spike_color = (150, 180, 255)  # Azul muito claro
            center_color = (60, 100, 200)  # Azul médio
        elif self.state == MineState.LANDED:
            base_color = (80, 120, 255)  # Azul meio
            spike_color = (120, 150, 255)  # Azul claro
            center_color = (40, 80, 200)  # Azul escuro
        elif self.state == MineState.ARMED:
            base_color = (60, 100, 200)  # Azul escuro
            spike_color = (100, 130, 220)  # Azul médio-claro
            center_color = (30, 60, 150)  # Azul muito escuro
        else:
            base_color = (80, 120, 255)  # Azul para explosão
            spike_color = (120, 150, 255)
            center_color = (40, 80, 200)

        if self.state == MineState.EXPLODING:
            progress = self.explosion_timer / self.explosion_duration

            # Explosão simples - círculo azul preenchido expandindo
            radius = int(self.explosion_radius * progress)
            if radius > 0:
                # Círculo preenchido com fade
                alpha = int(255 * (1 - progress))  # Fade out conforme expande
                explosion_surf = pygame.Surface(
                    (radius * 2, radius * 2), pygame.SRCALPHA
                )
                pygame.draw.circle(
                    explosion_surf, (*base_color, alpha), (radius, radius), radius
                )
                surface.blit(
                    explosion_surf, (int(self.x - radius), int(self.y - radius))
                )

        elif self.state == MineState.FLYING:
            # Rastro simples
            for i, (tx, ty) in enumerate(self.trail_positions):
                factor = i / len(self.trail_positions)
                size = int(2 + factor * 4)
                alpha = int(150 * factor)

                trail_surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
                pygame.draw.circle(trail_surf, (*base_color, alpha), (size, size), size)
                surface.blit(trail_surf, (tx - size, ty - size))

            # Núcleo simples
            pygame.draw.circle(surface, (255, 255, 255), (int(self.x), int(self.y)), 3)
            pygame.draw.circle(surface, base_color, (int(self.x), int(self.y)), 6, 2)

        else:
            # Desenhar mina com espinhos rotativos
            center_x, center_y = int(self.x), int(self.y)
            base_radius = MineConfig.BASE_RADIUS

            # PRIMEIRO: Desenhar espinhos triangulares rotativos (camada inferior)
            emerge_factor = abs(math.sin(self.spike_emerge_timer))  # Oscila entre 0 e 1

            for i in range(4):
                # Ângulo do espinho (90 graus entre cada um + rotação)
                angle = (math.pi / 2) * i + self.spike_rotation

                if emerge_factor > 0.1:  # Só desenha quando está emergindo
                    # Tamanho do espinho baseado na emergência
                    spike_length = int(emerge_factor * MineConfig.MAX_SPIKE_LENGTH)

                    # Posição da base do espinho (na circunferência do círculo)
                    base_x = center_x + math.cos(angle) * base_radius
                    base_y = center_y + math.sin(angle) * base_radius

                    # Ponta do espinho (para fora do círculo)
                    tip_x = center_x + math.cos(angle) * (base_radius + spike_length)
                    tip_y = center_y + math.sin(angle) * (base_radius + spike_length)

                    # Criar triângulo/cone do espinho
                    # Calcular pontos perpendiculares para a base do triângulo
                    perp_angle = angle + math.pi / 2
                    base_width = spike_length * 0.4  # Largura da base do triângulo

                    # Três pontos do triângulo
                    p1 = (int(tip_x), int(tip_y))  # Ponta
                    p2 = (
                        int(base_x + math.cos(perp_angle) * base_width),
                        int(base_y + math.sin(perp_angle) * base_width),
                    )  # Base esquerda
                    p3 = (
                        int(base_x + math.cos(perp_angle + math.pi) * base_width),
                        int(base_y + math.sin(perp_angle + math.pi) * base_width),
                    )  # Base direita

                    # Desenhar triângulo preenchido
                    pygame.draw.polygon(surface, spike_color, [p1, p2, p3])
                    # Contorno do triângulo
                    pygame.draw.polygon(surface, (255, 255, 255), [p1, p2, p3], 1)

            # SEGUNDO: Desenhar círculo base (camada superior)
            pygame.draw.circle(surface, base_color, (center_x, center_y), base_radius)
            pygame.draw.circle(
                surface, (255, 255, 255), (center_x, center_y), base_radius, 2
            )

            # TERCEIRO: Centro da mina
            pygame.draw.circle(surface, center_color, (center_x, center_y), 4)

            # Indicador de estado
            if self.state == MineState.LANDED:
                # Animação de carregamento - círculo de pontos azuis
                progress = self.arming_timer / self.arming_duration
                if progress > 0:
                    arc_radius = base_radius + 4
                    total_points = MineConfig.PROGRESS_POINTS
                    points_to_draw = int(total_points * progress)

                    for i in range(points_to_draw):
                        angle = (
                            i / total_points
                        ) * 2 * math.pi - math.pi / 2  # Começar do topo
                        point_x = center_x + math.cos(angle) * arc_radius
                        point_y = center_y + math.sin(angle) * arc_radius
                        pygame.draw.circle(
                            surface, spike_color, (int(point_x), int(point_y)), 2
                        )

            elif self.state == MineState.ARMED:
                # Área de perigo - círculo azul transparente
                danger_surf = pygame.Surface(
                    (self.explosion_radius * 2, self.explosion_radius * 2),
                    pygame.SRCALPHA,
                )
                pygame.draw.circle(
                    danger_surf,
                    (*base_color, 30),
                    (int(self.explosion_radius), int(self.explosion_radius)),
                    int(self.explosion_radius),
                )
                pygame.draw.circle(
                    danger_surf,
                    (*base_color, 100),
                    (int(self.explosion_radius), int(self.explosion_radius)),
                    int(self.explosion_radius),
                    1,
                )
                surface.blit(
                    danger_surf,
                    (self.x - self.explosion_radius, self.y - self.explosion_radius),
                )
