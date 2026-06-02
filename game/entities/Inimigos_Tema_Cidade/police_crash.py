"""PoliceCrash — efeito de morte "Crash & Burn" do Police Interceptor.

Cosmético puro (como o `CoreImplosion` do Neon Sniper): a viatura **não explode
na hora**. Ela perde o controle, **gira** descontrolada e **cai em diagonal**
soltando **fumaça negra**, até estourar numa labareda laranja na parte de baixo.

O destroço carrega a velocidade que a unidade tinha na morte (passada pelo
EntityManager via `trigger_death_sequence`) e ganha gravidade própria, então o
"diagonal" emerge do impulso lateral + queda. Interface duck-typed dos efeitos
do EntityManager: `update(dt)`, `draw(surface)`, `dead`, `rect`. Não entra em
grid de colisão nem na lista de inimigos — não conta como hostil para a
progressão de fase.
"""

from __future__ import annotations

import math
import random
from typing import List

import pygame

from ...core.config import config as Config
from . import city_glow
from . import city_palette as pal
from .police_interceptor_pixel_map import (
    PIXEL_COLS,
    PIXEL_ROWS,
    build_interceptor_surface,
)

GRAVITY: float = 560.0  # aceleração da queda (px/s²)
MAX_FALL_TIME: float = 1.6  # fallback caso nunca alcance a base
BURST_TIME: float = 0.42  # duração da labareda final
SMOKE_INTERVAL: float = 0.045  # cadência de emissão de baforadas
SMOKE_MAX_AGE: float = 0.7
DRAG: float = 0.6  # arrasto horizontal por segundo (a queda "sobe" na vertical)


class _Smoke:
    __slots__ = ("x", "y", "vx", "vy", "age", "max_age", "r0")

    def __init__(self, x: float, y: float, vx: float, vy: float, r0: float) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.age = 0.0
        self.max_age = SMOKE_MAX_AGE * random.uniform(0.7, 1.2)
        self.r0 = r0

    def update(self, dt: float) -> None:
        self.age += dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        # Fumaça desacelera e sobe levemente (empuxo térmico).
        self.vx *= 1.0 - min(1.0, dt * 1.4)
        self.vy += -20.0 * dt


class PoliceCrash:
    def __init__(
        self, cx: float, cy: float, cell: int, vx: float, vy: float
    ) -> None:
        self.cx: float = cx
        self.cy: float = cy
        self.cell: int = cell
        # Impulso lateral remanescente + queda por gravidade = diagonal.
        self.vx: float = vx * 0.5
        self.vy: float = vy * 0.4
        self.t: float = 0.0
        self.dead: bool = False
        self.state: str = "falling"
        self.burst_t: float = 0.0

        self.angle: float = 0.0
        self.spin: float = random.uniform(4.5, 8.0) * random.choice((-1.0, 1.0))
        self._smoke_timer: float = 0.0
        self.smoke: List[_Smoke] = []

        self._w = PIXEL_COLS * cell
        self._h = PIXEL_ROWS * cell
        self._floor = float(Config.SCREEN_HEIGHT) + self._h * 0.5

    @property
    def rect(self) -> pygame.Rect:
        r = max(self._w, self._h)
        return pygame.Rect(int(self.cx) - r, int(self.cy) - r, r * 2, r * 2)

    def update(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self.t += dt

        if self.state == "falling":
            self.vy += GRAVITY * dt
            self.vx *= 1.0 - min(1.0, dt * DRAG)
            self.cx += self.vx * dt
            self.cy += self.vy * dt
            self.angle += self.spin * dt

            # Emite baforadas de fumaça negra a partir do destroço.
            self._smoke_timer -= dt
            if self._smoke_timer <= 0.0:
                self._smoke_timer = SMOKE_INTERVAL
                self._emit_smoke()

            if self.cy >= self._floor or self.t >= MAX_FALL_TIME:
                self.state = "burst"
                self.burst_t = 0.0
                # Crava a labareda na altura visível (não fora da tela).
                self.cy = min(self.cy, float(Config.SCREEN_HEIGHT) - self._h * 0.3)
        else:  # burst
            self.burst_t += dt
            if self.burst_t >= BURST_TIME:
                self.dead = True

        for s in self.smoke:
            s.update(dt)
        if self.smoke:
            self.smoke = [s for s in self.smoke if s.age < s.max_age]

    def _emit_smoke(self) -> None:
        # Baforada saindo das turbinas (lado direito/traseiro do destroço).
        ox = random.uniform(-self._w * 0.2, self._w * 0.35)
        oy = random.uniform(-self._h * 0.25, self._h * 0.25)
        self.smoke.append(
            _Smoke(
                self.cx + ox,
                self.cy + oy,
                vx=random.uniform(-30.0, -90.0),
                vy=random.uniform(-10.0, 30.0),
                r0=random.uniform(self.cell * 1.4, self.cell * 2.4),
            )
        )

    # ── Render ──────────────────────────────────────────────────────────────
    def _draw_smoke(self, surface: pygame.Surface) -> None:
        for s in self.smoke:
            frac = s.age / s.max_age
            r = int(s.r0 * (0.6 + 1.2 * frac))
            if r < 1:
                continue
            alpha = int(150 * (1.0 - frac))
            if alpha <= 0:
                continue
            puff = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            # Cinza-escuro esfumaçando para preto conforme esfria.
            shade = int(70 * (1.0 - frac) + 24)
            pygame.draw.circle(puff, (shade, shade, shade + 4, alpha), (r, r), r)
            surface.blit(puff, (int(s.x) - r, int(s.y) - r))

    def draw(self, surface: pygame.Surface) -> None:
        self._draw_smoke(surface)

        if self.state == "falling":
            base = build_interceptor_surface(self.cell)
            # Destroço escurecido (sem energia) — multiplica o RGB por cinza.
            wreck = base.copy()
            wreck.fill((120, 120, 130), special_flags=pygame.BLEND_RGB_MULT)
            rotated = pygame.transform.rotate(wreck, math.degrees(self.angle))
            rrect = rotated.get_rect(center=(int(self.cx), int(self.cy)))
            surface.blit(rotated, rrect)

            # Brasa laranja piscando no chassi (incêndio começando).
            ember = 0.5 + 0.5 * math.sin(self.t * 26.0)
            ecol = pal.lerp(pal.TOXIC_ORANGE_DIM, pal.TOXIC_ORANGE, ember)
            glow = city_glow.get_glow(int(self.cell * 2.0), ecol)
            r = int(self.cell * 2.0)
            surface.blit(
                glow,
                (int(self.cx) - r, int(self.cy) - r),
                special_flags=pygame.BLEND_RGBA_ADD,
            )
        else:
            self._draw_burst(surface)

    def _draw_burst(self, surface: pygame.Surface) -> None:
        frac = min(1.0, self.burst_t / BURST_TIME)
        # Flash cheio no impacto (cobre o sumiço do destroço) com fade-out suave
        # (ease-out) — a labareda nunca "pop"a ao terminar.
        intensity = (1.0 - frac) ** 0.6
        flame_r = int(self.cell * (3.0 + 12.0 * frac))
        if flame_r > 0 and intensity > 0.01:
            if frac < 0.35:
                base = pal.lerp((255, 255, 255), pal.TOXIC_ORANGE, frac / 0.35)
            else:
                base = pal.lerp(pal.TOXIC_ORANGE, (150, 30, 10), (frac - 0.35) / 0.65)
            color = (
                int(base[0] * intensity),
                int(base[1] * intensity),
                int(base[2] * intensity),
            )
            glow = city_glow.get_glow(flame_r, color)
            surface.blit(
                glow,
                (int(self.cx) - flame_r, int(self.cy) - flame_r),
                special_flags=pygame.BLEND_RGBA_ADD,
            )
        # Estilhaços como glows aditivos que esmaecem (sem o piso de 1px que
        # fazia eles sumirem de repente) — cor escala a 0 = invisível no fim.
        shard_fade = (1.0 - frac) ** 1.3
        if shard_fade > 0.02:
            scol = (
                int(pal.TOXIC_ORANGE[0] * shard_fade),
                int(pal.TOXIC_ORANGE[1] * shard_fade),
                int(pal.TOXIC_ORANGE[2] * shard_fade),
            )
            shard_n = 8
            for i in range(shard_n):
                ang = i * (math.tau / shard_n) + self.spin
                dist = flame_r * 0.9 * frac
                sx = int(self.cx + math.cos(ang) * dist)
                sy = int(self.cy + math.sin(ang) * dist)
                sr = max(2, int(self.cell * (0.5 + 1.1 * shard_fade)))
                g = city_glow.get_glow(sr, scol)
                surface.blit(
                    g, (sx - sr, sy - sr), special_flags=pygame.BLEND_RGBA_ADD
                )
