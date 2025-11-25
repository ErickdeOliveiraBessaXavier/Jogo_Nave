import math
import pygame
from typing import Tuple
from ..core.config import config as Config
from ..core import colors
from .meteor import Meteor


class GuidedMeteor(Meteor):
    """
    Meteoro teleguiado que persegue o jogador como um míssil.
    Tem velocidade inicial menor mas acelera em direção ao alvo.
    """

    def __init__(
        self,
        size: int = 20,
        x: float = 0,
        y: float = 0,
        vx: float = 0,
        vy: float = 0,
        target_x: float = 0,
        target_y: float = 0,
    ):
        """
        Initialize guided meteor.

        Args:
            size: Tamanho do meteoro
            x, y: Posição inicial
            vx, vy: Velocidade inicial (será modificada pelo sistema de guiamento)
            target_x, target_y: Posição inicial do alvo (será atualizada dinamicamente)
        """
        super().__init__(size, x, y, vx, vy)

        # Configurações de guiamento
        self.max_speed = Config.GUIDED_METEOR_MAX_SPEED
        self.acceleration = Config.GUIDED_METEOR_ACCELERATION
        self.turn_rate = Config.GUIDED_METEOR_TURN_RATE

        # Estado do meteoro
        self.target_x = target_x
        self.target_y = target_y
        # Note: self.guided sempre True, poderia ser removido se não houver planos futuros

        # Acelerar rotação para meteoros guiados
        self.rotation_speed *= 3.0  # 3x mais rápido que meteoros normais

        # Cor especial para meteoros guiados - Verde para destaque
        self.base_color: Tuple[int, int, int] = colors.GREEN

    def update(
        self, dt: float, target_x: float | None = None, target_y: float | None = None
    ) -> None:
        """
        Update guided meteor with seeking behavior.

        Args:
            dt: Delta time
            target_x, target_y: Current target position (player position)
        """
        # Atualizar posição do alvo se fornecida
        if target_x is not None and target_y is not None:
            self.target_x = target_x
            self.target_y = target_y

        # Sistema de guiamento (sempre ativo)
        self._update_guidance(dt)

        # Física normal do meteoro (movimento e rotação)
        super().update(dt)

    def _update_guidance(self, dt: float) -> None:
        """Update the guidance system to steer towards target."""
        # Calcular direção para o alvo
        dx = self.target_x - self.x
        dy = self.target_y - self.y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance > 0:
            # Direção desejada (normalizada)
            desired_dx = dx / distance
            desired_dy = dy / distance

            # Velocidade atual (normalizada)
            current_speed = math.sqrt(self.vx * self.vx + self.vy * self.vy)
            if current_speed > 0:
                current_dx = self.vx / current_speed
                current_dy = self.vy / current_speed
            else:
                current_dx = desired_dx
                current_dy = desired_dy

            # Interpolação suave para a nova direção (steering)
            turn_factor = min(self.turn_rate * dt, 1.0)
            new_dx = current_dx + (desired_dx - current_dx) * turn_factor
            new_dy = current_dy + (desired_dy - current_dy) * turn_factor

            # Normalizar nova direção
            new_length = math.sqrt(new_dx * new_dx + new_dy * new_dy)
            if new_length > 0:
                new_dx /= new_length
                new_dy /= new_length

            # Acelerar em direção ao alvo
            target_speed = min(current_speed + self.acceleration * dt, self.max_speed)

            # Aplicar nova velocidade
            self.vx = new_dx * target_speed
            self.vy = new_dy * target_speed

    def draw(self, screen: pygame.Surface) -> None:
        """Draw guided meteor with green colors."""
        points = self._rotated_points()

        # Cores verdes para meteoros guiados
        if self.size <= Config.MIN_METEOR_SIZE + 8:
            body_color = (
                int(50 * self.color_intensity),  # Verde escuro
                int(255 * self.color_intensity),  # Verde brilhante
                int(100 * self.color_intensity),  # Verde médio
            )
            border_color: Tuple[int, int, int] = colors.GUIDED_METEOR_GREEN
            core_color: Tuple[int, int, int] = colors.GREEN
        else:
            body_color = (
                int(30 * self.color_intensity),  # Verde muito escuro
                int(200 * self.color_intensity),  # Verde forte
                int(80 * self.color_intensity),  # Verde escuro
            )
            border_color = colors.GUIDED_METEOR_GREEN
            core_color = colors.GREEN

        pygame.draw.polygon(screen, body_color, points)
        pygame.draw.polygon(screen, border_color, points, 2)
        center = (int(self.x + self.w // 2), int(self.y + self.h // 2))
        pygame.draw.circle(screen, core_color, center, max(2, self.size // 4))

    def get_display_color(self) -> Tuple[int, int, int]:
        """Get color for the guided meteor (always green)."""
        return self.base_color
