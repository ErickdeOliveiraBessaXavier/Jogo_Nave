import math
import random
from typing import Any, Dict, List, Tuple

import pygame


class OrbitalShield:
    """
    Escudo Orbital com design de energia estática e núcleo pulsante.
    Agora suporta múltiplos escudos orbitando a nave.
    """

    def __init__(self, ship: Any, duration: float, index: int = 0, total: int = 1):
        self.ship = ship
        self.timer = duration
        self.dead = False
        self.total = total
        self.index = index

        # Lógica de órbita
        self.angle = (index / total) * (2.0 * math.pi)
        self.radius = 90.0
        self.speed = 3.5
        self.size = 28
        self.damage = 180

        # Lógica visual
        self.pulse_timer = random.uniform(0, 10)
        self.rotation_inner = random.uniform(0, 360)
        self.sparks: List[Dict[str, Any]] = []  # Partículas de estática

    def update(self, dt: float):
        self.timer -= dt
        if self.timer <= 0 or getattr(self.ship, "dead", False):
            self.dead = True
            return

        # Girar ao redor da nave
        self.angle += self.speed * dt

        # Animação interna
        self.pulse_timer += dt * 8
        self.rotation_inner += dt * 200

        # Gerar faíscas de estática
        if random.random() < 0.3:
            self._spawn_spark()

        # Atualizar faíscas
        for s in self.sparks[:]:
            s["life"] -= dt
            if s["life"] <= 0:
                self.sparks.remove(s)
            else:
                s["x"] += s["vx"] * dt
                s["y"] += s["vy"] * dt

    def _spawn_spark(self):
        angle = random.uniform(0, math.pi * 2)
        dist = self.size / 2
        sx = math.cos(angle) * dist
        sy = math.sin(angle) * dist
        self.sparks.append(
            {
                "x": sx,
                "y": sy,
                "vx": sx * 2,
                "vy": sy * 2,
                "life": 0.2,
                "color": random.choice(
                    [(0, 200, 255), (200, 255, 255), (255, 255, 255)]
                ),
            }
        )

    def get_pos(self) -> tuple[float, float]:
        cx = self.ship.x + self.ship.w / 2
        cy = self.ship.y + self.ship.h / 2
        # Posição do CENTRO do escudo
        x = cx + math.cos(self.angle) * self.radius
        y = cy + math.sin(self.angle) * self.radius
        return x, y

    @property
    def rect(self) -> pygame.Rect:
        x, y = self.get_pos()
        # Rect usado para colisões (centrado)
        return pygame.Rect(
            int(x - self.size / 2), int(y - self.size / 2), self.size, self.size
        )

    def draw(self, surface: pygame.Surface):
        cx, cy = self.get_pos()

        # 1. Desenhar faíscas de estática (atrás do escudo)
        for s in self.sparks:
            pygame.draw.line(
                surface,
                s["color"],
                (int(cx + s["x"]), int(cy + s["y"])),
                (int(cx + s["x"] + s["vx"] * 0.02), int(cy + s["y"] + s["vy"] * 0.02)),
                1,
            )

        # 2. Brilho de fundo (Glow)
        pulse = math.sin(self.pulse_timer) * 0.2 + 0.8

        # Desenha círculo de energia (Branco/Ciano)
        # Como draw.circle não suporta alpha direto na surface principal sem SRCALPHA,
        # desenhamos um círculo sutil com borda.
        pygame.draw.circle(
            surface, (0, 100, 200), (int(cx), int(cy)), int(self.size / 2 + 2), 1
        )

        # 3. Núcleo Tecnológico (Quadrado rotacionado)
        self._draw_rotated_rect(
            surface, cx, cy, self.size * 0.6, self.rotation_inner, (50, 50, 60)
        )
        self._draw_rotated_rect(
            surface, cx, cy, self.size * 0.4, -self.rotation_inner * 1.5, (0, 200, 255)
        )

        # 4. Ponto central pulsante
        core_r = max(2, int(4 * pulse))
        pygame.draw.circle(surface, (255, 255, 255), (int(cx), int(cy)), core_r)

    def _draw_rotated_rect(
        self,
        surface: pygame.Surface,
        x: float,
        y: float,
        size: float,
        angle: float,
        color: tuple[int, int, int],
    ):
        # Helper para desenhar um quadrado rotacionado simples
        points: List[Tuple[float, float]] = []
        angle_rad = math.radians(angle)
        for i in range(4):
            # 4 cantos do quadrado
            a = angle_rad + (i * math.pi / 2) + (math.pi / 4)
            px = x + math.cos(a) * (size * 0.707)
            py = y + math.sin(a) * (size * 0.707)
            points.append((px, py))
        pygame.draw.polygon(surface, color, points)
        pygame.draw.polygon(surface, (255, 255, 255), points, 1)  # Borda branca sutil
