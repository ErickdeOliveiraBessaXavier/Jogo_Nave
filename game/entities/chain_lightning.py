import math
import random
from typing import Final, List, Tuple

import pygame

from ..core import colors

LIGHTNING_SEGMENT_LENGTH: Final[int] = 12
LIGHTNING_MAX_OFFSET: Final[int] = 10


class ChainLightning:
    """Efeito visual de raio que conecta dois pontos por um breve instante."""

    LIFETIME: Final[float] = 0.15  # Flash muito rápido

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
        self.lightning_points: List[Tuple[float, float]] = []
        self._generate_lightning_points()

    # ------------------------------------------------------------------
    # Geração da linha irregular
    # ------------------------------------------------------------------

    def _generate_lightning_points(self) -> None:
        dx = self.end_pos[0] - self.start_pos[0]
        dy = self.end_pos[1] - self.start_pos[1]
        distance = math.sqrt(dx * dx + dy * dy)

        if distance < 1:
            self.lightning_points = [self.start_pos, self.end_pos]
            return

        num_segments = max(2, int(distance / LIGHTNING_SEGMENT_LENGTH))
        inv_segments = 1.0 / num_segments

        # Vetor perpendicular normalizado
        perp_x = -dy / distance
        perp_y = dx / distance

        points: List[Tuple[float, float]] = [self.start_pos]
        for i in range(1, num_segments):
            t = i * inv_segments
            offset = random.uniform(-LIGHTNING_MAX_OFFSET, LIGHTNING_MAX_OFFSET)
            px = self.start_pos[0] + dx * t + perp_x * offset
            py = self.start_pos[1] + dy * t + perp_y * offset
            points.append((px, py))

        points.append(self.end_pos)
        self.lightning_points = points

    # ------------------------------------------------------------------
    # Update / Draw
    # ------------------------------------------------------------------

    def update(self, dt: float) -> None:
        self.timer += dt
        if self.timer >= self.LIFETIME:
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead or len(self.lightning_points) < 2:
            return

        alpha = int(255 * max(0.0, 1.0 - self.timer / self.LIFETIME))
        if alpha == 0:
            return

        r, g, b = self.color
        glow_r = min(255, r + 60)
        glow_g = min(255, g + 60)
        glow_b = min(255, b + 60)

        # Blitter em superfície SRCALPHA para suportar alpha por linha
        # evita criar nova Surface por segmento — uma única Surface overlay.
        w = surface.get_width()
        h = surface.get_height()
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)

        glow_color = (glow_r, glow_g, glow_b, alpha // 3)
        core_color = (255, 255, 255, alpha)
        mid_color = (r, g, b, alpha)

        points_len = len(self.lightning_points)
        for i in range(points_len - 1):
            p1_f = self.lightning_points[i]
            p2_f = self.lightning_points[i + 1]
            p1 = (int(p1_f[0]), int(p1_f[1]))
            p2 = (int(p2_f[0]), int(p2_f[1]))

            pygame.draw.line(overlay, glow_color, p1, p2, 6)   # brilho externo
            pygame.draw.line(overlay, mid_color, p1, p2, 3)    # cor do raio
            pygame.draw.line(overlay, core_color, p1, p2, 1)   # núcleo branco

        surface.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)