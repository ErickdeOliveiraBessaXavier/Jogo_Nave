"""TankMeltdown — colapso do núcleo do Cyber Tank (estilo estrela colapsando).

A explosão NORMAL da nave (que destrói a estrutura externa) é disparada pelo
`HitResult` da morte. Este efeito é só o **núcleo energético azul** que sobra no
lugar e entra em estado crítico:

  1-3. `critical` (~3s): estático, **acumula energia** — cresce gradualmente,
       com tremores e instabilidade crescentes (partículas atraídas para dentro,
       estática elétrica e pulsos luminosos cada vez mais intensos).
  4-5. `collapse` (~0.2s): **contração súbita** — encolhe rápido para um ponto,
       como toda a energia comprimida (colapso de estrela).
  6-7. `explode` (~0.7s): **explosão azul** principal + onda de choque expandindo
       rápido para fora (liberação colossal de uma vez).

Cosmético puro. Interface duck-typed dos efeitos do EntityManager: `update(dt)`,
`draw(surface)`, `dead`, `rect`.
"""

from __future__ import annotations

import math
import random
from typing import List

import pygame

from ....core.config import config as Config
from . import city_glow
from . import city_palette as pal

CRITICAL_TIME: float = 3.0
COLLAPSE_TIME: float = 0.20
EXPLODE_TIME: float = 0.42  # explosão rápida e violenta (referência: MineExplosion)

_BLUE: pal.RGB = pal.ELECTRIC_BLUE
_HOT: pal.RGB = (210, 245, 255)  # azul-branco quente


def _scale(color: pal.RGB, f: float) -> pal.RGB:
    f = 0.0 if f < 0.0 else 1.0 if f > 1.0 else f
    return (int(color[0] * f), int(color[1] * f), int(color[2] * f))


class _Spark:
    """Partícula de energia atraída para o núcleo (acreção)."""

    __slots__ = ("angle", "dist", "swirl", "size")

    def __init__(self, angle: float, dist: float, swirl: float, size: float) -> None:
        self.angle = angle
        self.dist = dist
        self.swirl = swirl
        self.size = size


class _Pulse:
    """Anel de luz expandindo (pulso luminoso)."""

    __slots__ = ("age", "life")

    def __init__(self, life: float) -> None:
        self.age = 0.0
        self.life = life


class TankMeltdown:
    def __init__(self, cx: float, cy: float, cell: int) -> None:
        self.cx: float = cx
        self.cy: float = cy
        self.cell: int = cell
        self.t: float = 0.0
        self.dead: bool = False
        self.phase: str = "critical"

        self.base_r: float = cell * 1.8
        self.peak_r: float = cell * 7.5  # tamanho máximo da sobrecarga
        self.collapse_from: float = self.peak_r  # raio capturado ao iniciar o colapso
        # Raio da explosão = raio do DANO = raio do indicador (WYSIWYG). Grande,
        # mas reduzido p/ não comprometer a jogabilidade.
        self.max_shock: float = min(
            Config.SCREEN_WIDTH * 0.38, Config.SCREEN_HEIGHT * 0.56
        )
        # Surface translúcida pré-alocada (reusada por frame, à la MineExplosion).
        d = int(self.max_shock) * 2 + 4
        self._boom_surf: pygame.Surface = pygame.Surface((d, d), pygame.SRCALPHA)
        self._boom_half: int = d // 2

        # Blast one-shot consumido pelo EntityManager/cena no instante da detonação
        # (aplica o dano de área via handle_mine_explosion). (cx, cy, raio).
        self._blast: tuple[float, float, float] | None = None

        self.sparks: List[_Spark] = []
        self.pulses: List[_Pulse] = []
        self._spark_timer: float = 0.0
        self._pulse_timer: float = 0.0
        self.phase_t: float = 0.0  # tempo dentro de collapse/explode

    @property
    def rect(self) -> pygame.Rect:
        r = int(self.max_shock)
        return pygame.Rect(int(self.cx) - r, int(self.cy) - r, r * 2, r * 2)

    # ── Update ──────────────────────────────────────────────────────────────
    def update(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self.t += dt

        if self.phase == "critical":
            self._update_critical(dt)
            if self.t >= CRITICAL_TIME:
                self.phase = "collapse"
                self.phase_t = 0.0
                self.collapse_from = self._critical_radius()
        elif self.phase == "collapse":
            self.phase_t += dt
            # Partículas sugadas violentamente para o ponto central.
            for s in self.sparks:
                s.dist = max(0.0, s.dist - dt * 900.0)
                s.angle += s.swirl * dt * 2.0
            if self.phase_t >= COLLAPSE_TIME:
                self.phase = "explode"
                self.phase_t = 0.0
                self.sparks.clear()
                # Dispara o dano de área de uma só vez (no raio telegrafado).
                self._blast = (self.cx, self.cy, self.max_shock)
        else:  # explode
            self.phase_t += dt
            if self.phase_t >= EXPLODE_TIME:
                self.dead = True

    def pop_blast(self) -> "tuple[float, float, float] | None":
        """Devolve (cx, cy, raio) do dano da explosão uma única vez (no instante
        da detonação) — consumido pelo EntityManager para aplicar o dano de área."""
        b = self._blast
        self._blast = None
        return b

    def _update_critical(self, dt: float) -> None:
        prog = min(1.0, self.t / CRITICAL_TIME)

        # Emissão de partículas de acreção (cada vez mais frequente).
        self._spark_timer -= dt
        if self._spark_timer <= 0.0:
            self._spark_timer = 0.05 * (1.0 - 0.7 * prog) + 0.008
            for _ in range(1 + int(prog * 3)):
                self.sparks.append(
                    _Spark(
                        angle=random.uniform(0.0, math.tau),
                        dist=self.cell * random.uniform(7.0, 14.0),
                        swirl=random.uniform(1.5, 4.0) * random.choice((-1.0, 1.0)),
                        size=random.uniform(1.5, 3.5),
                    )
                )
        inward = self.cell * (3.0 + 9.0 * prog)
        alive: List[_Spark] = []
        for s in self.sparks:
            s.dist -= inward * dt
            s.angle += s.swirl * dt
            if s.dist > 1.5:
                alive.append(s)
        self.sparks = alive

        # Pulsos luminosos (intervalo encurta com a sobrecarga).
        self._pulse_timer -= dt
        if self._pulse_timer <= 0.0:
            self._pulse_timer = 0.55 - 0.42 * prog
            self.pulses.append(_Pulse(life=random.uniform(0.4, 0.6)))
        for p in self.pulses:
            p.age += dt
        if self.pulses:
            self.pulses = [p for p in self.pulses if p.age < p.life]

    def _critical_radius(self) -> float:
        prog = min(1.0, self.t / CRITICAL_TIME)
        return self.base_r + (self.peak_r - self.base_r) * (prog ** 1.6)

    # ── Render ──────────────────────────────────────────────────────────────
    def _blit_glow(self, surface: pygame.Surface, x: float, y: float, radius: float, color: pal.RGB) -> None:
        if radius < 1:
            return
        glow = city_glow.get_glow(int(radius), color)
        surface.blit(
            glow, (int(x) - int(radius), int(y) - int(radius)),
            special_flags=pygame.BLEND_RGBA_ADD,
        )

    def draw(self, surface: pygame.Surface) -> None:
        if self.phase == "critical":
            self._draw_critical(surface)
        elif self.phase == "collapse":
            self._draw_collapse(surface)
        else:
            self._draw_explode(surface)

    def _draw_danger_zone(self, surface: pygame.Surface, prog: float) -> None:
        half = self._boom_half
        r = int(self.max_shock)
        surf = self._boom_surf
        surf.fill((0, 0, 0, 0))
        # Preenchimento leve (lê como "área"), intensifica com a sobrecarga.
        pygame.draw.circle(surf, (60, 150, 255, int(10 + 26 * prog)), (half, half), r)
        # Anel de borda pulsante — mais brilhante/urgente perto da detonação.
        pulse = 0.5 + 0.5 * math.sin(self.t * (4.0 + 12.0 * prog))
        ring_a = min(255, int((90 + 130 * prog) * (0.45 + 0.55 * pulse)))
        pygame.draw.circle(
            surf, (150, 225, 255, ring_a), (half, half), r, max(2, int(self.cell * 0.7))
        )
        surface.blit(surf, (int(self.cx) - half, int(self.cy) - half))

    def _draw_critical(self, surface: pygame.Surface) -> None:
        cell = self.cell
        prog = min(1.0, self.t / CRITICAL_TIME)

        # INDICADOR DA ZONA DE PERIGO: mostra até onde o dano vai chegar, durante
        # toda a instabilidade. Fica mais nítido/urgente conforme a detonação se
        # aproxima (pulso mais rápido). Raio == raio real do dano (WYSIWYG).
        self._draw_danger_zone(surface, prog)

        # Tremor crescente.
        amp = int(1 + 11 * prog * prog)
        ccx = int(self.cx + random.randint(-amp, amp))
        ccy = int(self.cy + random.randint(-amp, amp))

        # Pulsos luminosos (anéis expandindo).
        for p in self.pulses:
            f = p.age / p.life
            rr = int(cell * (1.5 + 7.0 * f))
            self._blit_glow(surface, self.cx, self.cy, rr, _scale(_BLUE, (1.0 - f) * 0.6))

        # Partículas de acreção (energia sendo puxada para dentro).
        for s in self.sparks:
            sx = self.cx + math.cos(s.angle) * s.dist
            sy = self.cy + math.sin(s.angle) * s.dist
            self._blit_glow(surface, sx, sy, int(s.size + cell * 0.4), _HOT)

        # Núcleo: cresce + halo pulsante + estática elétrica em volta.
        core_r = self._critical_radius()
        flick = 0.5 + 0.5 * math.sin(self.t * (8.0 + 30.0 * prog))
        self._blit_glow(surface, ccx, ccy, int(core_r * 1.9 + cell * flick), _BLUE)
        pygame.draw.circle(surface, pal.DEEP_SLATE, (ccx, ccy), int(core_r))
        pygame.draw.circle(surface, _scale(_BLUE, 0.5 + 0.5 * flick), (ccx, ccy), int(core_r * 0.8))
        pygame.draw.circle(surface, _HOT, (ccx, ccy), max(2, int(core_r * 0.4)))
        self._draw_arcs(surface, ccx, ccy, core_r, prog)

    def _draw_arcs(self, surface: pygame.Surface, ccx: float, ccy: float, core_r: float, prog: float) -> None:
        # Estática elétrica: raios irregulares saindo do núcleo, mais densos
        # e longos conforme a instabilidade cresce.
        n = int(2 + prog * 5)
        for _ in range(n):
            a = random.uniform(0.0, math.tau)
            segs = 4
            r0 = core_r * 0.7
            r1 = core_r * (1.4 + prog * 2.2)
            pts: list[tuple[int, int]] = []
            for k in range(segs + 1):
                rr = r0 + (r1 - r0) * (k / segs)
                jitter = random.uniform(-core_r * 0.35, core_r * 0.35)
                pa = a + jitter / max(1.0, rr)
                pts.append((int(ccx + math.cos(pa) * rr), int(ccy + math.sin(pa) * rr)))
            col = _HOT if random.random() < 0.4 else _BLUE
            pygame.draw.lines(surface, col, False, pts, 1)

    def _draw_collapse(self, surface: pygame.Surface) -> None:
        cell = self.cell
        f = min(1.0, self.phase_t / COLLAPSE_TIME)
        # Contração súbita: encolhe MUITO rápido para um ponto (ease-out forte).
        cr = self.collapse_from * (1.0 - f) ** 2.2 + cell * 0.4
        # Partículas restantes convergindo.
        for s in self.sparks:
            sx = self.cx + math.cos(s.angle) * s.dist
            sy = self.cy + math.sin(s.angle) * s.dist
            self._blit_glow(surface, sx, sy, int(cell * 0.5), _HOT)
        # Halo encolhendo + ponto comprimido brilhante (energia indo a um ponto).
        self._blit_glow(surface, self.cx, self.cy, int(cr * 1.6), _BLUE)
        pygame.draw.circle(surface, _HOT, (int(self.cx), int(self.cy)), max(2, int(cr)))
        # Brilho-semente intensificando no fim do colapso (prestes a estourar).
        seed = int(cell * (1.0 + 3.0 * f))
        self._blit_glow(surface, self.cx, self.cy, seed, (255, 255, 255))

    def _draw_explode(self, surface: pygame.Surface) -> None:
        cell = self.cell
        icx, icy = int(self.cx), int(self.cy)
        f = min(1.0, self.phase_t / EXPLODE_TIME)
        # Expansão ESTOURADA: ease-out forte → quase todo o raio em poucos frames.
        exp = 1.0 - (1.0 - f) ** 3.5

        # 1. Disco azul translúcido GIGANTE (referência MineExplosion) — desabrocha
        #    e some rápido; cobre boa parte da tela. Surface reaproveitada.
        half = self._boom_half
        self._boom_surf.fill((0, 0, 0, 0))
        radius = int(self.max_shock * exp)
        if radius > 2:
            disc_a = int(150 * (1.0 - f))
            if disc_a > 0:
                pygame.draw.circle(self._boom_surf, (*_BLUE, disc_a), (half, half), radius)
            # Frente de onda quente (anel brilhante grosso) na borda do disco.
            ring_a = int(235 * (1.0 - f) ** 0.5)
            if ring_a > 0:
                pygame.draw.circle(
                    self._boom_surf, (*_HOT, ring_a), (half, half), radius,
                    max(2, int(cell * 2.4 * (1.0 - f))),
                )
            surface.blit(self._boom_surf, (icx - half, icy - half))

        # 2. Núcleo da descarga: clarão aditivo quente e instantâneo, esmaece veloz.
        flash_i = (1.0 - f) ** 1.4
        self._blit_glow(surface, icx, icy, int(cell * (5.0 + 16.0 * (1.0 - f))), _scale(_HOT, flash_i))
        self._blit_glow(surface, icx, icy, int(self.max_shock * 0.45 * exp), _scale(_BLUE, flash_i))

        # 3. Raios de energia disparando para fora (só no instante inicial).
        if f < 0.3:
            si = 1.0 - f / 0.3
            r1 = self.max_shock * (0.55 + 0.45 * f)
            for k in range(12):
                a = k * (math.tau / 12)
                p1 = (int(icx + math.cos(a) * r1), int(icy + math.sin(a) * r1))
                pygame.draw.line(surface, _scale(_HOT, si), (icx, icy), p1, max(1, int(cell * 0.7)))
