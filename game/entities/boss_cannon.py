import math
from typing import Tuple, List
import pygame
from ..core.config import config as Config
from .boss_laser import BossLaser


class BossAttackSystem:
    """Manages all attack patterns and projectile spawning for the boss."""

    # Constants for better maintainability
    FRENZY_LASER_ANGLES: List[float] = [-0.349, 0, 0.349]  # 20 degrees in radians
    LASER_DISTANCE: int = 2000  # Maximum laser reach


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
