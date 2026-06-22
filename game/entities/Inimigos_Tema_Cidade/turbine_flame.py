"""TurbineFlame — chama de turbina por partículas (bioma CITY).

Emissor de uma chama de **foguete em duas camadas**: um **núcleo amarelo-claro**
(quente, perto do bocal) envolto por um **envelope azul** — leitura de chama azul
estilizada. Usado pela turbina única do `PoliceInterceptor` (e reutilizável por
outros propulsores do tema).

Convenções (convenções do projeto): a simulação (emitir/envelhecer/mover) roda no `update()`
de quem possui o emissor; o `draw()` só desenha (§3). Os halos reusam o cache
aditivo bucketizado de `city_glow` (§7: sem alocar surface por partícula/frame).
O nº de partículas é limitado (`MAX_PARTICLES`) — emissor de unidade especial de
baixa contagem, não entidade de hot path.
"""

from __future__ import annotations

import math
import random
from typing import List

import pygame

from . import city_glow

# Camadas da chama: núcleo amarelo-claro, envelope azul.
INNER: tuple[int, int, int] = (255, 244, 190)
OUTER: tuple[int, int, int] = (40, 120, 255)
MAX_PARTICLES: int = 96


class _Particle:
    __slots__ = ("x", "y", "vx", "vy", "age", "life", "size")

    def __init__(
        self, x: float, y: float, vx: float, vy: float, life: float, size: float
    ) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.age = 0.0
        self.life = life
        self.size = size


class TurbineFlame:
    def __init__(self) -> None:
        self.particles: List[_Particle] = []

    def update(
        self,
        dt: float,
        nozzle_x: float,
        nozzle_y: float,
        dir_x: float,
        dir_y: float,
        intensity: float,
    ) -> None:
        """Envelhece/move as partículas vivas e emite novas no bocal.

        `dir_x/dir_y` = direção do escapamento (oposta ao nariz); `intensity`
        0..1 controla quantidade/velocidade/tamanho (idle baixo → dash cheio).
        """
        if dt <= 0.0:
            return

        for p in self.particles:
            p.age += dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            damp = 1.0 - min(1.0, dt * 2.4)
            p.vx *= damp
            p.vy *= damp
        if self.particles:
            self.particles = [p for p in self.particles if p.age < p.life]

        intensity = 0.0 if intensity < 0.0 else 1.0 if intensity > 1.0 else intensity
        count = int(1 + intensity * 4)
        speed = 70.0 + 300.0 * intensity
        base = math.atan2(dir_y, dir_x)
        # Cone de emissão mais fechado conforme acelera (jato mais focado).
        spread = 0.55 * (0.6 + 0.4 * (1.0 - intensity))
        for _ in range(count):
            if len(self.particles) >= MAX_PARTICLES:
                break
            a = base + random.uniform(-spread, spread)
            sp = speed * random.uniform(0.6, 1.1)
            self.particles.append(
                _Particle(
                    nozzle_x + random.uniform(-2.0, 2.0),
                    nozzle_y + random.uniform(-2.0, 2.0),
                    math.cos(a) * sp,
                    math.sin(a) * sp,
                    life=random.uniform(0.16, 0.30),
                    size=random.uniform(3.0, 6.0) * (0.7 + 0.6 * intensity),
                )
            )

    def draw(self, surface: pygame.Surface) -> None:
        blit = surface.blit
        add = pygame.BLEND_RGBA_ADD
        get_glow = city_glow.get_glow
        for p in self.particles:
            frac = p.age / p.life
            frac = 0.0 if frac < 0.0 else 1.0 if frac > 1.0 else frac
            fade = 1.0 - frac

            # Envelope azul: cresce e esmaece com a idade.
            ro = max(2, int(p.size * (1.0 + 1.1 * frac)))
            ob = (int(OUTER[0] * fade), int(OUTER[1] * fade), int(OUTER[2] * fade))
            go = get_glow(ro, ob)
            blit(go, (int(p.x) - ro, int(p.y) - ro), special_flags=add)

            # Núcleo amarelo-claro: menor e some mais rápido (só o "miolo" quente).
            cf = fade ** 1.5
            ri = max(1, int(p.size * 0.55 * (1.0 - 0.5 * frac)))
            ic = (int(INNER[0] * cf), int(INNER[1] * cf), int(INNER[2] * cf))
            gi = get_glow(ri, ic)
            blit(gi, (int(p.x) - ri, int(p.y) - ri), special_flags=add)

    def clear(self) -> None:
        self.particles.clear()
