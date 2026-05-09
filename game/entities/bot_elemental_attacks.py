from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Tuple

import pygame

from ..core.config import config as Config

if TYPE_CHECKING:
    from ..entities.ship import Ship

RGB = Tuple[int, int, int]

_INFERNO_EFFECT_DURATION: float = 5.0
_TOXINA_EFFECT_DURATION: float = 4.0
_NEVASCA_EFFECT_DURATION: float = 3.0


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


class EnergyOrb:
    """
    Orbe de energia disparado pelo robô em direção ao jogador.

    Visual: Estrela de pixels multicamada (core, mid, outer) idêntica à aura
    de carregamento, mantendo o tamanho final atingido na antena.
    Causa 1 vida de dano por colisão.
    """

    SPEED = 420.0  # px/s

    def __init__(
        self,
        x: float,
        y: float,
        target_x: float,
        target_y: float,
        color_core: RGB,
        color_mid: RGB,
        color_outer: RGB,
        pixel_size: int,
        theme: str,
        speed_multiplier: float = 1.0,
    ):
        self.x = float(x)
        self.y = float(y)
        self.dead = False
        self.causes_damage = True
        self.theme = theme
        self.color_core = color_core
        self.color_mid = color_mid
        self.color_outer = color_outer
        self.p_s = pixel_size

        # Raio de colisão balanceado: cobre o núcleo e a camada média (2x pixel_size)
        self.size = pixel_size * 2

        dx = target_x - x
        dy = target_y - y
        dist = math.hypot(dx, dy) or 1.0
        actual_speed = self.SPEED * speed_multiplier
        self.vx = (dx / dist) * actual_speed
        self.vy = (dy / dist) * actual_speed

        self._angle = 0.0
        self._trail: list[list[float]] = []  # [x, y, alpha]

        self.rect = pygame.Rect(
            int(self.x) - self.size,
            int(self.y) - self.size,
            self.size * 2,
            self.size * 2,
        )

        # Pré-alocação de superfícies
        g_size = int(pixel_size * 3)
        self._glow_surf = pygame.Surface((g_size * 2, g_size * 2), pygame.SRCALPHA)
        pygame.draw.circle(
            self._glow_surf,
            (*self.color_outer, 40),
            (g_size, g_size),
            g_size,
        )
        self._trail_surf = pygame.Surface((self.p_s, self.p_s), pygame.SRCALPHA)

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt

        if random.random() < 0.4:
            self._trail.append([self.x, self.y, 180.0])
        for t in self._trail:
            t[2] -= 500.0 * dt
        self._trail = [t for t in self._trail if t[2] > 0]

        self.rect.x = int(self.x) - self.size
        self.rect.y = int(self.y) - self.size

        sw = getattr(Config, "SCREEN_WIDTH", 480)
        sh = getattr(Config, "SCREEN_HEIGHT", 800)
        if self.x < -100 or self.x > sw + 100 or self.y < -100 or self.y > sh + 100:
            self.dead = True

    def apply_effect(self, ship: "Ship") -> None:
        if self.theme == "inferno":
            ship.fire_rate_modifier_timer = _INFERNO_EFFECT_DURATION
        elif self.theme == "toxina":
            ship.invert_controls_timer = _TOXINA_EFFECT_DURATION
        elif self.theme == "nevasca":
            ship.speed_modifier_timer = _NEVASCA_EFFECT_DURATION

    def draw(self, surface: pygame.Surface) -> None:
        # Rastro
        r, g, b = self.color_outer
        for tx, ty, alpha in self._trail:
            self._trail_surf.fill((r, g, b, int(alpha * 0.4)))
            surface.blit(
                self._trail_surf,
                (int(tx) - self.p_s // 2, int(ty) - self.p_s // 2),
            )

        cx, cy = int(self.x), int(self.y)
        s = self.p_s

        # Glow (Halo)
        g_radius = self._glow_surf.get_width() // 2
        surface.blit(self._glow_surf, (cx - g_radius, cy - g_radius))

        # Estrela de energia pixelada (mesma geometria da aura)

        # 1. Camada OUTER: Diagonais ±1 e Pontas Axiais ±2
        for dx, dy in (
            (-s, -s),
            (s, -s),
            (-s, s),
            (s, s),  # diagonais
            (0, -s * 2),
            (0, s * 2),
            (-s * 2, 0),
            (s * 2, 0),  # pontas axiais
        ):
            pygame.draw.rect(
                surface, self.color_outer, (cx + dx - s // 2, cy + dy - s // 2, s, s)
            )

        # 2. Camada MID: Cruz central ±1
        for dx, dy in ((0, -s), (0, s), (-s, 0), (s, 0)):
            pygame.draw.rect(
                surface, self.color_mid, (cx + dx - s // 2, cy + dy - s // 2, s, s)
            )

        # 3. Camada CORE: Pixel central
        pygame.draw.rect(surface, self.color_core, (cx - s // 2, cy - s // 2, s, s))


class ChargeParticle:
    """Partícula que converge para a ponta da antena durante CHARGING.

    Forma e comportamento variam por tema para espelhar as animações CSS:
      inferno  → quadrado 4×4 com cruz de 'mid'     (suckInInferno)
      toxina   → quadrado 6×6 com dois diagonais    (suckInToxina)
      nevasca  → floco de neve 2×2 com 12 sombras   (suckInNevasca) + rotação
    """

    def __init__(
        self,
        antenna_x: float,
        antenna_y: float,
        palette: dict[str, RGB],
        theme: str,
    ):
        self.theme = theme
        self.angle = random.uniform(0, math.pi * 2)
        self.dist = 80.0 + random.uniform(0, 40)
        self._start_dist = self.dist
        self._orbit_speed = 0.06 + random.uniform(0, 0.07)
        self._radial_speed = 70.0 + random.uniform(0, 60)
        self._spin = 0.0

        if theme == "inferno":
            self.size = 4
        elif theme == "toxina":
            self.size = 6
        else:  # nevasca
            self.size = 2
            self._spin = random.uniform(1.5, 3.0)

        self.color_core = palette["core"]
        self.color_mid = palette["mid"]
        self.color_outer = palette["outer"]

        self.ax = antenna_x
        self.ay = antenna_y
        self.px = antenna_x + math.cos(self.angle) * self.dist
        self.py = antenna_y + math.sin(self.angle) * self.dist
        self.dead = False
        self._rot_angle = random.uniform(0, math.pi * 2)

        sz = max(self.size * 6, 20)
        self._surf = pygame.Surface((sz, sz), pygame.SRCALPHA)

    def _rebuild_surf(self, alpha: int) -> None:
        self._surf.fill((0, 0, 0, 0))
        sz = self._surf.get_width()
        cx = sz // 2
        cy = sz // 2
        s = self.size
        a = max(0, min(255, alpha))

        if self.theme == "inferno":
            pygame.draw.rect(
                self._surf, (*self.color_core, a), (cx - s // 2, cy - s // 2, s, s)
            )
            for dx, dy in ((s, 0), (-s, 0), (0, s), (0, -s)):
                pygame.draw.rect(
                    self._surf,
                    (*self.color_mid, a),
                    (cx + dx - s // 2, cy + dy - s // 2, s, s),
                )

        elif self.theme == "toxina":
            pygame.draw.rect(
                self._surf, (*self.color_core, a), (cx - s // 2, cy - s // 2, s, s)
            )
            pygame.draw.rect(
                self._surf,
                (*self.color_mid, a),
                (cx + 2 - s // 2, cy + 2 - s // 2, s, s),
            )
            pygame.draw.rect(
                self._surf,
                (*self.color_outer, a),
                (cx - 2 - s // 2, cy - 2 - s // 2, s, s),
            )

        else:  # nevasca
            pygame.draw.rect(self._surf, (*self.color_core, a), (cx - 1, cy - 1, 2, 2))
            for dist_px, col in ((4, self.color_mid), (8, self.color_outer)):
                for ddx, ddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                    pygame.draw.rect(
                        self._surf,
                        (*col, a),
                        (cx + ddx * dist_px - 1, cy + ddy * dist_px - 1, 2, 2),
                    )
            for ddx, ddy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                pygame.draw.rect(
                    self._surf,
                    (*self.color_outer, a),
                    (cx + ddx * 4 - 1, cy + ddy * 4 - 1, 2, 2),
                )

    def update(self, dt: float, antenna_x: float, antenna_y: float) -> None:
        speed_mul = 1.0 + (1.0 - clamp(self.dist / self._start_dist, 0, 1)) * 3.0

        self.dist -= self._radial_speed * speed_mul * dt
        self.angle += self._orbit_speed * speed_mul * (dt * 60)
        self._rot_angle += self._spin * dt

        if self.dist < 2:
            self.dead = True
            return
        self.ax = antenna_x
        self.ay = antenna_y
        self.px = antenna_x + math.cos(self.angle) * self.dist
        self.py = antenna_y + math.sin(self.angle) * self.dist

    def draw(self, surface: pygame.Surface) -> None:
        ratio = clamp(self.dist / self._start_dist * 2, 0, 1)
        if ratio < 0.05:
            return
        self._rebuild_surf(int(ratio * 220))
        sz = self._surf.get_width()

        if self.theme == "nevasca" and self._rot_angle != 0:
            rotated = pygame.transform.rotate(self._surf, math.degrees(self._rot_angle))
            rw, rh = rotated.get_size()
            surface.blit(rotated, (int(self.px) - rw // 2, int(self.py) - rh // 2))
        else:
            surface.blit(self._surf, (int(self.px) - sz // 2, int(self.py) - sz // 2))
