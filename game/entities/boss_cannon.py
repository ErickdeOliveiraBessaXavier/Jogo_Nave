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
        self.base_radius: int = 14
        self.barrel_length: int = 28
        self.barrel_width: int = 8
        self.barrel_tip_width: int = 6

        # Cores do canhão
        self.base_color = (80, 80, 100)
        self.base_highlight = (120, 120, 150)
        self.base_shadow = (50, 50, 70)
        self.barrel_color = (100, 100, 120)
        self.barrel_highlight = (150, 150, 180)
        self.barrel_inner = (60, 60, 80)
        self.tip_glow_color = (255, 200, 100)

        # Estado de carregamento (para efeito de brilho)
        self.charging = False
        self.charge_progress = 0.0

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
        """Retorna a posição atual do canhão (base)."""
        return (self.x, self.y)

    def get_barrel_tip_position(self) -> Tuple[float, float]:
        """Retorna a posição da base do canhão (onde o laser sai)."""
        # Laser sai da base circular, não da ponta do cano
        return (self.x, self.y)

    def get_direction(self) -> pygame.Vector2:
        """Retorna o vetor de direção normalizado."""
        return self.facing_direction.copy()

    def set_charging(self, charging: bool, progress: float = 0.0) -> None:
        """Define o estado de carregamento para efeito visual."""
        self.charging = charging
        self.charge_progress = progress

    def create_laser(self, lifetime: float) -> BossLaser:
        """Cria um laser na direção atual do canhão."""
        tip_x, tip_y = self.get_barrel_tip_position()
        target_x = tip_x + self.facing_direction.x * Config.LASER_DISTANCE
        target_y = tip_y + self.facing_direction.y * Config.LASER_DISTANCE
        return BossLaser(tip_x, tip_y, target_x, target_y, lifetime=lifetime)

    def draw(
        self, surface: pygame.Surface, offset_x: float = 0, offset_y: float = 0
    ) -> None:
        """Desenha o canhão com design mais elaborado."""
        cx = self.x + offset_x
        cy = self.y + offset_y

        # Calcular pontos do cano
        cos_r = math.cos(self.rotation)
        sin_r = math.sin(self.rotation)

        # Vetor perpendicular para largura do cano
        perp_x = -sin_r
        perp_y = cos_r

        # Ponta do cano
        tip_x = cx + cos_r * self.barrel_length
        tip_y = cy + sin_r * self.barrel_length

        # === DESENHAR CANO (formato cônico) ===
        # Base do cano (mais larga)
        base_half_width = self.barrel_width / 2
        # Ponta do cano (mais estreita)
        tip_half_width = self.barrel_tip_width / 2

        # Pontos do cano (trapézio)
        barrel_points = [
            (cx + perp_x * base_half_width, cy + perp_y * base_half_width),
            (cx - perp_x * base_half_width, cy - perp_y * base_half_width),
            (tip_x - perp_x * tip_half_width, tip_y - perp_y * tip_half_width),
            (tip_x + perp_x * tip_half_width, tip_y + perp_y * tip_half_width),
        ]

        # Cano principal (sombra/corpo)
        pygame.draw.polygon(surface, self.barrel_color, barrel_points)

        # Linha de destaque no cano (borda superior)
        pygame.draw.line(
            surface, self.barrel_highlight, barrel_points[0], barrel_points[3], 2
        )

        # Linha interna do cano (sulco central)
        inner_start = (cx + cos_r * 4, cy + sin_r * 4)
        inner_end = (tip_x - cos_r * 2, tip_y - sin_r * 2)
        pygame.draw.line(surface, self.barrel_inner, inner_start, inner_end, 2)

        # === ABERTURA DO CANO (círculo na ponta) ===
        # Círculo externo da abertura
        pygame.draw.circle(
            surface,
            self.barrel_highlight,
            (int(tip_x), int(tip_y)),
            int(tip_half_width + 1),
        )
        # Círculo interno (buraco do cano)
        pygame.draw.circle(
            surface,
            self.barrel_inner,
            (int(tip_x), int(tip_y)),
            int(tip_half_width - 1),
        )

        # === BASE DO CANHÃO ===
        # Sombra da base (círculo maior atrás)
        pygame.draw.circle(
            surface, self.base_shadow, (int(cx), int(cy)), self.base_radius + 2
        )

        # Base principal
        pygame.draw.circle(
            surface, self.base_color, (int(cx), int(cy)), self.base_radius
        )

        # === EFEITO DE BRILHO NA BASE (quando carregando) ===
        if self.charging and self.charge_progress > 0:
            glow_radius = int(self.base_radius + 2 + self.charge_progress * 6)
            glow_alpha = int(100 + self.charge_progress * 155)

            # Criar surface com alpha para o brilho
            glow_size = glow_radius * 2 + 4
            glow_surface = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)

            # Brilho externo (mais transparente)
            glow_color_outer = (*self.tip_glow_color, int(glow_alpha * 0.3))
            pygame.draw.circle(
                glow_surface,
                glow_color_outer,
                (glow_size // 2, glow_size // 2),
                glow_radius,
            )

            # Brilho interno (mais intenso)
            glow_color_inner = (*self.tip_glow_color, glow_alpha)
            pygame.draw.circle(
                glow_surface,
                glow_color_inner,
                (glow_size // 2, glow_size // 2),
                max(4, int(self.base_radius * 0.7)),
            )

            surface.blit(
                glow_surface, (int(cx - glow_size // 2), int(cy - glow_size // 2))
            )

            # Núcleo brilhante no centro
            core_radius = int(3 + self.charge_progress * 4)
            pygame.draw.circle(
                surface, (255, 255, 200), (int(cx), int(cy)), core_radius
            )

        # Anel de destaque
        pygame.draw.circle(
            surface, self.base_highlight, (int(cx), int(cy)), self.base_radius, 2
        )

        # Anel interno decorativo
        pygame.draw.circle(
            surface, self.base_shadow, (int(cx), int(cy)), self.base_radius - 4, 1
        )

        # Ponto central (pivot) - só mostra se não estiver carregando
        if not self.charging or self.charge_progress < 0.1:
            pygame.draw.circle(surface, self.barrel_highlight, (int(cx), int(cy)), 3)
