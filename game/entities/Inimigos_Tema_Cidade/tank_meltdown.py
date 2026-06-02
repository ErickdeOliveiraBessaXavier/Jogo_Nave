"""TankMeltdown — efeito de morte "Structural Failure" do Cyber Tank.

Cosmético puro (como o `CoreImplosion`/`PoliceCrash`): as **placas de blindagem
voam em todas as direções** (estilhaços girando, meramente visuais) e o chassi
**derrete numa poça de metal fundido neon** que brilha quente e esfria. Sem dano.

Interface duck-typed dos efeitos do EntityManager: `update(dt)`, `draw(surface)`,
`dead`, `rect`. Não entra em grid de colisão nem na lista de inimigos.
"""

from __future__ import annotations

import math
import random
from typing import List

import pygame

from . import city_glow
from . import city_palette as pal

DURATION: float = 1.5
PLATE_COUNT_MIN: int = 12
PLATE_COUNT_MAX: int = 18


def _scale(color: pal.RGB, factor: float) -> pal.RGB:
    """Escurece uma cor por um fator 0..1 (para fade aditivo → preto = invisível)."""
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


class _Plate:
    __slots__ = ("x", "y", "vx", "vy", "angle", "spin", "size", "color", "age", "life")

    def __init__(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        spin: float,
        size: float,
        color: pal.RGB,
        life: float,
    ) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.angle = random.uniform(0.0, math.tau)
        self.spin = spin
        self.size = size
        self.color = color
        self.age = 0.0
        self.life = life  # vida própria (escalonada) → não somem todos juntos


class TankMeltdown:
    def __init__(self, cx: float, cy: float, cell: int) -> None:
        self.cx: float = cx
        self.cy: float = cy
        self.cell: int = cell
        self.t: float = 0.0
        self.dead: bool = False
        self.puddle_r: float = float(cell) * 5.0

        plate_colors = (pal.HULL_LIGHT, pal.GUNMETAL, pal.HULL_SHADOW)
        count = random.randint(PLATE_COUNT_MIN, PLATE_COUNT_MAX)
        self.plates: List[_Plate] = []
        for _ in range(count):
            ang = random.uniform(0.0, math.tau)
            sp = random.uniform(120.0, 320.0)
            self.plates.append(
                _Plate(
                    x=cx + random.uniform(-cell * 2, cell * 2),
                    y=cy + random.uniform(-cell * 2, cell * 2),
                    vx=math.cos(ang) * sp,
                    vy=math.sin(ang) * sp,
                    spin=random.uniform(-8.0, 8.0),
                    size=random.uniform(cell * 0.9, cell * 2.0),
                    color=random.choice(plate_colors),
                    life=random.uniform(0.85, 1.35),
                )
            )

    @property
    def rect(self) -> pygame.Rect:
        r = int(self.puddle_r + self.cell * 8)
        return pygame.Rect(int(self.cx) - r, int(self.cy) - r, r * 2, r * 2)

    def update(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self.t += dt
        for p in self.plates:
            p.age += dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            damp = 1.0 - min(1.0, dt * 1.6)
            p.vx *= damp
            p.vy *= damp
            p.angle += p.spin * dt
        if self.t >= DURATION:
            self.dead = True

    def _frac(self) -> float:
        return min(1.0, self.t / DURATION)

    # ── Render ──────────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        frac = self._frac()

        # Poça de metal fundido: brilha branco-quente, vira laranja e esfria;
        # halo aditivo + rim azul neon ("metal fundido neon" da proposta).
        if frac < 0.3:
            heat = frac / 0.3
            core = pal.lerp(pal.TOXIC_ORANGE, (255, 255, 235), heat)
        else:
            heat = 1.0 - (frac - 0.3) / 0.7
            core = pal.lerp((70, 32, 18), pal.TOXIC_ORANGE, heat)
        # Fade global da poça nos últimos 30% para não "estourar" ao sumir.
        end_fade = 1.0 if frac < 0.7 else 1.0 - (frac - 0.7) / 0.3
        pr = int(self.puddle_r * (0.7 + 0.5 * frac))
        if pr > 0 and end_fade > 0.0:
            glow = city_glow.get_glow(pr, _scale(core, end_fade))
            surface.blit(
                glow,
                (int(self.cx) - pr, int(self.cy) - pr),
                special_flags=pygame.BLEND_RGBA_ADD,
            )
            rim = pal.lerp(pal.ELECTRIC_BLUE, (20, 40, 70), frac)
            rr = int(pr * 0.62)
            rglow = city_glow.get_glow(rr, _scale(rim, end_fade))
            surface.blit(
                rglow,
                (int(self.cx) - rr, int(self.cy) - rr),
                special_flags=pygame.BLEND_RGBA_ADD,
            )

        # Estilhaços de placa girando (meramente visuais): fade de alpha suave +
        # leve encolhimento ao longo da vida própria de cada placa.
        for p in self.plates:
            pf = min(1.0, p.age / p.life)
            af = (1.0 - pf) ** 1.4  # ease-out: cheio no início, esmaece no fim
            if af <= 0.0:
                continue
            alpha = int(255 * af)
            scale = 0.6 + 0.4 * af  # recua um pouco enquanto some
            self._blit_plate(surface, p, scale, alpha)
            # Brilho "quente" só enquanto jovem, acompanhando o fade.
            if pf < 0.5:
                heat = (1.0 - pf * 2.0) * af
                hot = int(self.cell * 0.9 * heat)
                if hot > 0:
                    g = city_glow.get_glow(hot, _scale(pal.TOXIC_ORANGE, heat))
                    surface.blit(
                        g,
                        (int(p.x) - hot, int(p.y) - hot),
                        special_flags=pygame.BLEND_RGBA_ADD,
                    )

    def _blit_plate(
        self, surface: pygame.Surface, p: "_Plate", scale: float, alpha: int
    ) -> None:
        """Desenha a placa rotacionada com alpha (fade real, sem 'pop')."""
        s = p.size * scale
        ca, sa = math.cos(p.angle), math.sin(p.angle)
        corners = ((-s, -s * 0.6), (s, -s * 0.6), (s, s * 0.6), (-s, s * 0.6))
        pts = [
            (p.x + cx * ca - cy * sa, p.y + cx * sa + cy * ca) for cx, cy in corners
        ]
        xs = [q[0] for q in pts]
        ys = [q[1] for q in pts]
        minx, miny = int(min(xs)) - 1, int(min(ys)) - 1
        w, h = int(max(xs)) - minx + 2, int(max(ys)) - miny + 2
        if w <= 0 or h <= 0:
            return
        tmp = pygame.Surface((w, h), pygame.SRCALPHA)
        local = [(q[0] - minx, q[1] - miny) for q in pts]
        pygame.draw.polygon(tmp, (*p.color, alpha), local)
        pygame.draw.polygon(tmp, (*pal.OUTLINE, alpha), local, 1)
        surface.blit(tmp, (minx, miny))
