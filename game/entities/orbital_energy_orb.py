"""Orbe de energia disparado por uma esfera da Torreta Orbital.

Comportamento de **negação de espaço**: ao ser disparado, memoriza a posição do
jogador naquele instante (`target_x/target_y`) e viaja em linha reta até lá —
**não** persegue. O jogador pode destruí-lo com tiros antes que chegue
(`destructible`); se sobreviver e alcançar o ponto memorizado, converte-se num
`ElectricFieldZone` (a conversão é orquestrada pelo `EntityManager`, que lê
`landed`).

Distinção importante para o `EntityManager`:
  - morre por tiro do jogador  → `dead=True`, `landed=False`  → nenhum campo;
  - alcança o destino          → `landed=True`               → spawna o campo.

Visual: esfera de energia com instabilidade elétrica — núcleo branco pulsante,
halo ciano, pequenos arcos e um rastro curto. `draw()` só desenha (§3); o
acumulador de animação é alimentado pelo `update`.
"""

from __future__ import annotations

import math
import random

import pygame

from ..core.config import config as Config

_CORE = (240, 250, 255)
_MID = (140, 205, 255)
_HALO = (90, 160, 240)
_ARC = (210, 240, 255)


def _lerp_color(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


class OrbitalEnergyOrb:
    SPEED = 250.0
    RADIUS = 9
    FIELD_RADIUS = 70
    HEALTH = 2  # alguns tiros: destrutível, mas exige atenção (ritmo previsível)

    # Rastro: emite por distância percorrida (espaçamento estável, independente
    # de FPS), não por probabilidade/frame — evita o amontoado artificial.
    _TRAIL_SPACING = 13.0           # px entre partículas ao longo da trajetória
    _TRAIL_LIFE = (0.25, 0.45)      # vida (s) de cada partícula
    _TRAIL_DRIFT = (8.0, 26.0)      # faixa de velocidade de deriva (energia solta)

    def __init__(
        self,
        x: float,
        y: float,
        target_x: float,
        target_y: float,
        aggressiveness_multiplier: float = 1.0,
        field_radius: int | None = None,
    ):
        self.x = float(x)
        self.y = float(y)
        self.target_x = float(target_x)
        self.target_y = float(target_y)
        self.field_radius = int(field_radius if field_radius is not None else self.FIELD_RADIUS)

        self.dead = False
        self.landed = False
        self.health = self.HEALTH
        self.hit_flash = 0.0
        self.causes_damage = True

        aggr = max(0.5, aggressiveness_multiplier)
        speed = self.SPEED * (0.85 + 0.3 * (aggr - 1.0))
        dx = self.target_x - x
        dy = self.target_y - y
        dist = math.hypot(dx, dy) or 1.0
        self._total_dist = dist
        self.vx = (dx / dist) * speed
        self.vy = (dy / dist) * speed

        self.anim_time = random.uniform(0.0, math.tau)
        self._speed = math.hypot(self.vx, self.vy)
        self._emit_dist = 0.0
        # Partícula: [x, y, vx, vy, life, max_life, size].
        self._particles: list[list[float]] = []
        # rect persistente atualizado in-place (§7).
        r = self.RADIUS
        self._rect = pygame.Rect(int(x) - r, int(y) - r, r * 2, r * 2)

    @property
    def rect(self) -> pygame.Rect:
        r = self.RADIUS
        self._rect.update(int(self.x) - r, int(self.y) - r, r * 2, r * 2)
        return self._rect

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x, self.y, float(self.RADIUS)

    def update(self, dt: float) -> None:
        if self.dead:
            return
        self.anim_time += dt
        if self.hit_flash > 0.0:
            self.hit_flash = max(0.0, self.hit_flash - dt)

        prev_dx = self.target_x - self.x
        prev_dy = self.target_y - self.y
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Chegou ao ponto memorizado? Detecta cruzamento (o produto escalar com
        # a direção de chegada troca de sinal) ou proximidade — robusto a dt alto.
        new_dx = self.target_x - self.x
        new_dy = self.target_y - self.y
        crossed = (prev_dx * new_dx + prev_dy * new_dy) <= 0.0
        close = (new_dx * new_dx + new_dy * new_dy) <= (self.RADIUS * self.RADIUS)
        if crossed or close:
            self.x, self.y = self.target_x, self.target_y
            self.landed = True
            self.dead = True
            return

        self._update_trail(dt)

        # Safety: fora da tela com folga, descarta sem virar campo.
        margin = 120
        if (
            self.x < -margin
            or self.x > Config.SCREEN_WIDTH + margin
            or self.y < -margin
            or self.y > Config.SCREEN_HEIGHT + margin
        ):
            self.dead = True

    def _update_trail(self, dt: float) -> None:
        # Emite partículas espaçadas pela distância percorrida.
        self._emit_dist += self._speed * dt
        while self._emit_dist >= self._TRAIL_SPACING:
            self._emit_dist -= self._TRAIL_SPACING
            ang = random.uniform(0.0, math.tau)
            spd = random.uniform(*self._TRAIL_DRIFT)
            off = random.uniform(0.0, self.RADIUS * 0.5)
            life = random.uniform(*self._TRAIL_LIFE)
            self._particles.append(
                [
                    self.x + math.cos(ang) * off,
                    self.y + math.sin(ang) * off,
                    math.cos(ang) * spd,  # deriva radial leve
                    math.sin(ang) * spd,
                    life,
                    life,
                    random.uniform(2.0, 4.0),
                ]
            )
        # Avança e expira.
        for p in self._particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] -= dt
        self._particles = [p for p in self._particles if p[4] > 0.0]

    def take_damage(self, amount: int = 1) -> None:
        self.health -= amount
        self.hit_flash = 0.08
        if self.health <= 0:
            # Destruído pelo jogador: morre SEM converter em campo.
            self.dead = True
            self.landed = False

    def draw(self, surface: pygame.Surface) -> None:
        # Rastro: partículas esparsas que encolhem e esfriam de cor ao envelhecer
        # (centelha branca recém-solta → ciano apagado), sugerindo energia se
        # dispersando sem formar um rastro denso.
        for px, py, _vx, _vy, life, max_life, size in self._particles:
            ratio = life / max_life
            rad = max(1, int(size * ratio))
            col = _lerp_color(_HALO, _CORE, ratio)
            pygame.draw.circle(surface, col, (int(px), int(py)), rad)

        cx, cy = int(self.x), int(self.y)
        pulse = 0.5 + 0.5 * math.sin(self.anim_time * 12.0)
        flash = self.hit_flash > 0.0

        # Halo externo.
        halo_r = int(self.RADIUS + 3 + pulse * 3)
        pygame.draw.circle(surface, _HALO, (cx, cy), halo_r, 1)

        # Corpo.
        body_col = (255, 255, 255) if flash else _MID
        pygame.draw.circle(surface, body_col, (cx, cy), self.RADIUS)
        pygame.draw.circle(surface, _CORE, (cx, cy), max(2, int(self.RADIUS * 0.5)))

        # Arcos elétricos instáveis em volta.
        if random.random() < 0.7:
            cos, sin = math.cos, math.sin
            for _ in range(random.randint(1, 3)):
                a0 = random.uniform(0.0, math.tau)
                a1 = a0 + random.uniform(0.3, 1.0)
                r0 = self.RADIUS + 1
                r1 = self.RADIUS + random.uniform(3, 7)
                amid = (a0 + a1) * 0.5
                p0 = (cx + cos(a0) * r0, cy + sin(a0) * r0)
                pm = (cx + cos(amid) * r1, cy + sin(amid) * r1)
                p1 = (cx + cos(a1) * r0, cy + sin(a1) * r0)
                pygame.draw.lines(surface, _ARC, False, [p0, pm, p1], 1)
