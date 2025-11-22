import math
import random
from typing import Tuple, List
import pygame
from ..core.config import Config
from .boss_laser import BossLaser
from .meteor import Meteor
from .meteor_pool import MeteorPool
from .guided_meteor import GuidedMeteor


def apply_aim_spread(
    dx: float, dy: float, spread_degrees: float
) -> Tuple[float, float]:
    """Apply random spread to direction vector.

    Args:
        dx, dy: Normalized direction vector
        spread_degrees: Maximum deviation in degrees (±)

    Returns:
        New direction vector with spread applied
    """
    # Converte spread para radianos
    spread_radians = math.radians(spread_degrees)

    # Gera um ângulo aleatório dentro do spread
    random_angle = random.uniform(-spread_radians, spread_radians)

    # Aplica rotação ao vetor de direção
    cos_angle = math.cos(random_angle)
    sin_angle = math.sin(random_angle)

    new_dx = dx * cos_angle - dy * sin_angle
    new_dy = dx * sin_angle + dy * cos_angle

    return new_dx, new_dy


class BossAttackSystem:
    """Manages all attack patterns and projectile spawning for the boss."""

    # Constants for better maintainability
    FRENZY_LASER_ANGLES: List[float] = [-0.349, 0, 0.349]  # 20 degrees in radians
    LASER_DISTANCE: int = 2000  # Maximum laser reach

    @staticmethod
    def spawn_aimed_meteor(
        boss_x: float,
        boss_y: float,
        boss_w: float,
        boss_h: float,
        target_x: float,
        target_y: float,
        meteor_pool: MeteorPool,
    ) -> "Meteor":
        """Spawns a meteor aimed at the player's position with some inaccuracy."""
        # Posição de spawn (a partir do boss)
        spawn_x = boss_x + boss_w / 2
        spawn_y = boss_y + boss_h / 2

        # Calcula a direção para o alvo
        dx = target_x - spawn_x
        dy = target_y - spawn_y
        length = math.sqrt(dx * dx + dy * dy)

        if length > 0:
            dx = dx / length
            dy = dy / length

            # Aplica imprecisão para balanceamento
            dx, dy = apply_aim_spread(dx, dy, Config.BOSS_METEOR_AIM_SPREAD)

            # Garantir que meteoro sempre vá para baixo ou horizontal (nunca para cima)
            if dy < 0:
                dy = abs(dy) * 0.2  # Forçar direção para baixo com velocidade reduzida

        # Velocidade base do meteoro
        base_speed = 200

        # Cria o meteoro com velocidade direcionada (com imprecisão)
        meteor = meteor_pool.get(
            size=random.randint(15, 25),
            x=spawn_x,
            y=spawn_y,
            vx=dx * base_speed,
            vy=dy * base_speed,
        )

        return meteor

    @staticmethod
    def spawn_side_meteors(
        boss_x: float,
        boss_y: float,
        boss_w: float,
        boss_h: float,
        player_x: float,
        player_y: float,
        meteor_pool: MeteorPool,
    ) -> List["Meteor"]:
        """Spawns meteors from both sides of the boss in an arc motion towards the player."""
        meteors: List["Meteor"] = []

        # Posições dentro do boss, na parte inferior
        left_spawn_x = boss_x + boss_w * 0.25  # 25% da largura do boss
        right_spawn_x = boss_x + boss_w * 0.75  # 75% da largura do boss
        spawn_y = boss_y + boss_h * 0.8  # 80% da altura do boss (parte inferior)

        # Velocidade base reduzida para curva mais longa
        base_speed = 120

        # Meteoro da esquerda - curva longa como míssil
        left_dx = player_x - left_spawn_x
        left_dy = player_y - spawn_y
        left_length = math.sqrt(left_dx * left_dx + left_dy * left_dy)

        if left_length > 0:
            # Normaliza a direção
            left_dx = left_dx / left_length
            left_dy = left_dy / left_length

            # Aplica imprecisão antes da curva
            left_dx, left_dy = apply_aim_spread(
                left_dx, left_dy, Config.BOSS_SIDE_METEOR_AIM_SPREAD
            )

            # Curva moderada para movimento tipo míssil (reduzido para evitar ir para cima)
            arc_factor = 0.4  # Reduzido para curva mais suave
            curved_left_dx = left_dx + arc_factor * left_dy
            curved_left_dy = left_dy - arc_factor * left_dx

            # Garantir que meteoro sempre vá para baixo
            if curved_left_dy < 0:
                curved_left_dy = abs(curved_left_dy) * 0.3  # Força direção para baixo

            # Renormaliza
            curved_length = math.sqrt(
                curved_left_dx * curved_left_dx + curved_left_dy * curved_left_dy
            )
            if curved_length > 0:
                curved_left_dx = curved_left_dx / curved_length
                curved_left_dy = curved_left_dy / curved_length

            left_meteor = meteor_pool.get(
                size=random.randint(20, 30),
                x=left_spawn_x,
                y=spawn_y,
                vx=curved_left_dx * base_speed,
                vy=curved_left_dy * base_speed,
            )
            meteors.append(left_meteor)

        # Meteoro da direita - curva longa como míssil
        right_dx = player_x - right_spawn_x
        right_dy = player_y - spawn_y
        right_length = math.sqrt(right_dx * right_dx + right_dy * right_dy)

        if right_length > 0:
            # Normaliza a direção
            right_dx = right_dx / right_length
            right_dy = right_dy / right_length

            # Aplica imprecisão antes da curva
            right_dx, right_dy = apply_aim_spread(
                right_dx, right_dy, Config.BOSS_SIDE_METEOR_AIM_SPREAD
            )

            # Curva moderada para movimento tipo míssil (reduzido para evitar ir para cima)
            arc_factor = 0.4  # Reduzido para curva mais suave
            curved_right_dx = right_dx - arc_factor * right_dy
            curved_right_dy = right_dy + arc_factor * right_dx

            # Garantir que meteoro sempre vá para baixo
            if curved_right_dy < 0:
                curved_right_dy = abs(curved_right_dy) * 0.3  # Força direção para baixo

            # Renormaliza
            curved_length = math.sqrt(
                curved_right_dx * curved_right_dx + curved_right_dy * curved_right_dy
            )
            if curved_length > 0:
                curved_right_dx = curved_right_dx / curved_length
                curved_right_dy = curved_right_dy / curved_length

            right_meteor = meteor_pool.get(
                size=random.randint(20, 30),
                x=right_spawn_x,
                y=spawn_y,
                vx=curved_right_dx * base_speed,
                vy=curved_right_dy * base_speed,
            )
            meteors.append(right_meteor)

        return meteors

    @staticmethod
    def spawn_guided_meteor(
        boss_x: float,
        boss_y: float,
        boss_w: float,
        boss_h: float,
        target_x: float,
        target_y: float,
    ) -> GuidedMeteor:
        """Spawns a guided meteor that seeks the player."""
        # Posição de spawn (centro do boss)
        spawn_x = boss_x + boss_w / 2
        spawn_y = boss_y + boss_h / 2

        # Velocidade inicial baixa em direção ao alvo
        dx = target_x - spawn_x
        dy = target_y - spawn_y
        length = math.sqrt(dx * dx + dy * dy)

        initial_speed = 80  # Velocidade inicial baixa
        if length > 0:
            vx = (dx / length) * initial_speed
            vy = (dy / length) * initial_speed
        else:
            vx = 0
            vy = initial_speed

        # Criar meteoro guiado
        guided_meteor = GuidedMeteor(
            size=random.randint(18, 25),
            x=spawn_x,
            y=spawn_y,
            vx=vx,
            vy=vy,
            target_x=target_x,
            target_y=target_y,
        )

        return guided_meteor


class BossCannon:
    """Canhão do boss que gira e dispara lasers."""

    def __init__(self):
        self.x: float = 0
        self.y: float = 0
        self.rotation: float = 0  # Ângulo em radianos
        self.facing_direction = pygame.Vector2(0, 1)
        self.base_radius: int = 10
        self.barrel_length: int = 20
        self.barrel_width: int = 4

    def update_position(
        self, boss_x: float, boss_y: float, boss_width: float, boss_height: float
    ) -> None:
        """Atualiza a posição do canhão para ficar na parte inferior do boss."""
        self.x = boss_x + boss_width / 2
        self.y = boss_y + boss_height

    def aim_at(self, target_x: float, target_y: float) -> None:
        """Atualiza a rotação do canhão para mirar no alvo."""
        dx = target_x - self.x
        dy = target_y - self.y

        # Normalizar direção
        length = math.sqrt(dx * dx + dy * dy)
        if length > 0:
            self.facing_direction.x = dx / length
            self.facing_direction.y = dy / length
            self.rotation = math.atan2(dy, dx)

    def get_position(self) -> Tuple[float, float]:
        """Retorna a posição atual do canhão."""
        return (self.x, self.y)

    def get_direction(self) -> pygame.Vector2:
        """Retorna o vetor de direção normalizado."""
        return self.facing_direction.copy()

    def create_laser(self, lifetime: float) -> BossLaser:
        """Cria um laser na direção atual do canhão."""
        target_x = self.x + self.facing_direction.x * Config.LASER_DISTANCE
        target_y = self.y + self.facing_direction.y * Config.LASER_DISTANCE
        return BossLaser(self.x, self.y, target_x, target_y, lifetime=lifetime)

    def draw(
        self, surface: pygame.Surface, offset_x: float = 0, offset_y: float = 0
    ) -> None:
        """Desenha o canhão."""
        # Base circular do canhão
        pygame.draw.circle(
            surface,
            (200, 200, 200),
            (int(self.x + offset_x), int(self.y + offset_y)),
            self.base_radius,
        )

        # Cano do canhão
        end_x = self.x + math.cos(self.rotation) * self.barrel_length
        end_y = self.y + math.sin(self.rotation) * self.barrel_length

        pygame.draw.line(
            surface,
            (200, 200, 200),
            (int(self.x + offset_x), int(self.y + offset_y)),
            (int(end_x + offset_x), int(end_y + offset_y)),
            self.barrel_width,
        )
