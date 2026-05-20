import math
import random
from typing import Final, List, Tuple

import pygame

from ..core import colors

LIGHTNING_SEGMENT_LENGTH: Final[int] = 16
LIGHTNING_MAX_OFFSET: Final[int] = 8


class ChainLightning:
    """Efeito visual de raio que conecta dois pontos por um breve instante."""

    LIFETIME: Final[float] = 0.15  # Flash muito rápido
    _shared_overlay: pygame.Surface | None = None

    @classmethod
    def get_shared_overlay(cls, w: int, h: int) -> pygame.Surface:
        if cls._shared_overlay is None or cls._shared_overlay.get_size() != (w, h):
            cls._shared_overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        return cls._shared_overlay

    def __init__(
        self,
        start_pos: Tuple[float, float],
        end_pos: Tuple[float, float],
        color: Tuple[int, int, int] = colors.CYAN,
    ) -> None:
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.color = color
        self.dead = False
        self.timer = 0.0
        self.lightning_points: List[Tuple[int, int]] = []
        self._generate_lightning_points()

    # ------------------------------------------------------------------
    # Geração da linha irregular
    # ------------------------------------------------------------------

    def _generate_lightning_points(self) -> None:
        dx = self.end_pos[0] - self.start_pos[0]
        dy = self.end_pos[1] - self.start_pos[1]
        distance_sq = dx * dx + dy * dy

        if distance_sq < 1:
            self.lightning_points = [
                (int(self.start_pos[0]), int(self.start_pos[1])),
                (int(self.end_pos[0]), int(self.end_pos[1])),
            ]
            return

        distance = math.sqrt(distance_sq)
        num_segments = max(2, int(distance / LIGHTNING_SEGMENT_LENGTH))
        inv_segments = 1.0 / num_segments

        # Vetor perpendicular normalizado
        perp_x = -dy / distance
        perp_y = dx / distance

        points: List[Tuple[int, int]] = [
            (int(self.start_pos[0]), int(self.start_pos[1]))
        ]
        for i in range(1, num_segments):
            t = i * inv_segments
            offset = random.uniform(-LIGHTNING_MAX_OFFSET, LIGHTNING_MAX_OFFSET)
            px = self.start_pos[0] + dx * t + perp_x * offset
            py = self.start_pos[1] + dy * t + perp_y * offset
            points.append((int(px), int(py)))

        points.append((int(self.end_pos[0]), int(self.end_pos[1])))
        self.lightning_points = points

    # ------------------------------------------------------------------
    # Update / Draw
    # ------------------------------------------------------------------

    def update(self, dt: float) -> None:
        self.timer += dt
        if self.timer >= self.LIFETIME:
            self.dead = True

    def draw_to_surface(self, surface: pygame.Surface) -> None:
        if self.dead or len(self.lightning_points) < 2:
            return

        # Fator de fade out
        progress = self.timer / self.LIFETIME
        alpha = int(255 * (1.0 - progress))
        if alpha < 10:
            return

        r, g, b = self.color

        # Cores com alpha
        glow_color = (r, g, b, alpha // 4)
        mid_color = (min(255, r + 50), min(255, g + 50), min(255, b + 50), alpha)
        core_color = (255, 255, 255, alpha)

        # Desenhar os segmentos direto na surface (overlay compartilhado)
        pygame.draw.lines(
            surface, glow_color, False, self.lightning_points, 5
        )  # brilho
        pygame.draw.lines(
            surface, mid_color, False, self.lightning_points, 2
        )  # cor principal
        pygame.draw.lines(
            surface, core_color, False, self.lightning_points, 1
        )  # núcleo
