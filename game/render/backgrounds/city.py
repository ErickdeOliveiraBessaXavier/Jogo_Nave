"""Background de Cidade: prédios cyberpunk com janelas piscantes."""

import random
from typing import Any, Dict, List

import pygame

from .base import Background


class CityBackground(Background):
    """Background de cidade cyberpunk."""

    # Constantes
    NUM_BUILDINGS = 12
    WINDOW_SIZE = (12, 20)
    WINDOW_SPACING = 25
    BLINK_SPEED = 1.5

    def __init__(self, width: int, height: int):
        super().__init__(width, height)
        self.buildings: List[Dict[str, Any]] = []
        self.blink_timer: float = 0.0
        self._create_buildings()

    def _create_buildings(self) -> None:
        """Gera prédios com propriedades variadas."""
        neon_colors = [
            (0, 255, 255),  # Ciano
            (255, 0, 255),  # Magenta
            (255, 255, 0),  # Amarelo
            (0, 255, 127),  # Verde neon
        ]

        x_pos = 0
        min_spacing = 20

        for _ in range(self.NUM_BUILDINGS):
            width = random.randint(80, 180)
            height = random.randint(200, 500)

            self.buildings.append(
                {
                    "x": x_pos,
                    "y": self.height - height,
                    "width": width,
                    "height": height,
                    "color": (
                        random.randint(20, 40),
                        random.randint(20, 40),
                        random.randint(40, 60),
                    ),
                    "neon_color": random.choice(neon_colors),
                }
            )

            x_pos += width + min_spacing

    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        """Atualiza timer de piscar."""
        self.blink_timer += dt * self.BLINK_SPEED * speed_mult

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha cidade com janelas piscantes."""
        # Fundo escuro
        surface.fill((10, 10, 20))

        window_w, window_h = self.WINDOW_SIZE
        spacing = self.WINDOW_SPACING
        blink_time = int(self.blink_timer * 100)

        for bldg in self.buildings:
            x, y = bldg["x"], bldg["y"]

            # Corpo do prédio
            pygame.draw.rect(
                surface, bldg["color"], (x, y, bldg["width"], bldg["height"])
            )

            # Borda neon
            pygame.draw.rect(
                surface, bldg["neon_color"], (x, y, bldg["width"], bldg["height"]), 2
            )

            # Desenhar janelas de forma otimizada
            self._draw_windows(
                surface,
                x,
                y,
                bldg["width"],
                bldg["height"],
                window_w,
                window_h,
                spacing,
                blink_time,
            )

    def _draw_windows(
        self,
        surface: pygame.Surface,
        bldg_x: int,
        bldg_y: int,
        bldg_width: int,
        bldg_height: int,
        window_w: int,
        window_h: int,
        spacing: int,
        blink_time: int,
    ) -> None:
        """Desenha janelas com padrão de piscar otimizado."""
        lit_color = (255, 255, 200)
        dark_color = (40, 40, 60)

        y_start = bldg_y + 30
        y_end = bldg_y + bldg_height - 30
        x_start = bldg_x + 15
        x_end = bldg_x + bldg_width - 15

        for wy in range(y_start, y_end, spacing + window_h):
            for wx in range(x_start, x_end, spacing):
                color = (
                    lit_color
                    if (blink_time + (wx + wy) % 100) % 200 < 150
                    else dark_color
                )
                pygame.draw.rect(surface, color, (wx, wy, window_w, window_h))

    def reset(self) -> None:
        """Reseta cidade para estado inicial."""
        self.buildings.clear()
        self.blink_timer = 0.0
        self._create_buildings()
