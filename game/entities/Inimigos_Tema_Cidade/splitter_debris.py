"""SplitterDebris — destroços físicos do Splitter Tank ao ser destruído.

Cosmético puro (como `PoliceCrash`/`TankMeltdown`): ao morrer, o chassi se
estilhaça em **cacos de pixel-art** (`Splitter_Tank_Shattered`) que voam para
fora a partir do centro, ganham gravidade, **giram** e **esmaecem**. Vale para
os dois tiers — o **mini** gera cacos **menores e em menor quantidade**.

Interface duck-typed dos efeitos do EntityManager: `update(dt)`, `draw(surface)`,
`dead`, `rect`. Não entra na grid de colisão nem na lista de inimigos — não conta
como hostil para a progressão de fase.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Tuple

import pygame

from ...core.assets import BASE_DIR, get_image

_SHARD_DIR = (
    BASE_DIR / "assets" / "images" / "Sprites_Splitter_Tank" / "Splitter_Tank_Shattered"
)
_SHARD_FILE_COUNT: int = 6

GRAVITY: float = 520.0  # aceleração da queda dos cacos (px/s²)
DRAG: float = 0.5       # arrasto horizontal por segundo

# Por tier: quantidade de cacos, FATOR de escala sobre o tamanho nativo do caco
# (preserva a diferença 12×12 vs 16×16 dos sprites — os 16 saem maiores), tempo
# de vida (s) e faixa de velocidade de arremesso. Mini (tier 1): menos e menores.
@dataclass(frozen=True)
class _DebrisConfig:
    count: int
    scale: float
    life: float
    speed: Tuple[float, float]


_DEBRIS_BY_TIER: Dict[int, _DebrisConfig] = {
    0: _DebrisConfig(count=7, scale=1.6, life=0.95, speed=(90.0, 220.0)),
    1: _DebrisConfig(count=3, scale=0.8, life=0.60, speed=(70.0, 160.0)),
}


class _Shard:
    __slots__ = ("x", "y", "vx", "vy", "angle", "spin", "age", "life", "img")

    def __init__(
        self, x: float, y: float, vx: float, vy: float, life: float, img: pygame.Surface
    ) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.angle = random.uniform(0.0, 360.0)
        self.spin = random.uniform(-300.0, 300.0)
        self.age = 0.0
        self.life = life
        self.img = img

    def update(self, dt: float) -> None:
        self.age += dt
        self.vy += GRAVITY * dt
        self.vx *= 1.0 - min(1.0, dt * DRAG)
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle += self.spin * dt


class SplitterDebris:
    # Cacos crus (12/16 px) carregados uma vez; escalados por caco no spawn (§7).
    _raw_frames: List[pygame.Surface] = []

    @classmethod
    def _frames(cls) -> List[pygame.Surface]:
        if not cls._raw_frames:
            cls._raw_frames = [
                get_image(_SHARD_DIR / f"splitter_tank_sprite_shattered_{i:02d}.png")
                for i in range(1, _SHARD_FILE_COUNT + 1)
            ]
        return cls._raw_frames

    def __init__(self, cx: float, cy: float, tier: int) -> None:
        cfg = _DEBRIS_BY_TIER[tier]
        count = cfg.count
        scale = cfg.scale
        life = cfg.life
        lo, hi = cfg.speed

        frames = self._frames()
        self.dead: bool = False
        self.shards: List[_Shard] = []
        for _ in range(count):
            base = random.choice(frames)
            # Escala o tamanho NATIVO do caco (12 ou 16 px) → mantém a diferença
            # entre os sprites; jitter por caco quebra a uniformidade.
            bw, bh = base.get_size()
            f = scale * random.uniform(0.85, 1.15)
            img = pygame.transform.scale(base, (max(2, int(bw * f)), max(2, int(bh * f))))
            ang = random.uniform(0.0, math.tau)
            spd = random.uniform(lo, hi)
            self.shards.append(
                _Shard(
                    cx,
                    cy,
                    vx=math.cos(ang) * spd,
                    # Pequeno empuxo inicial pra cima → arco antes de cair.
                    vy=math.sin(ang) * spd - random.uniform(20.0, 80.0),
                    life=life * random.uniform(0.8, 1.2),
                    img=img,
                )
            )

    @property
    def rect(self) -> pygame.Rect:
        # Bounding box dos cacos vivos, para o culling de visibilidade não cortar.
        if not self.shards:
            return pygame.Rect(0, 0, 0, 0)
        xs = [s.x for s in self.shards]
        ys = [s.y for s in self.shards]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        return pygame.Rect(int(x0) - 16, int(y0) - 16, int(x1 - x0) + 32, int(y1 - y0) + 32)

    def update(self, dt: float) -> None:
        if dt <= 0.0:
            return
        alive = False
        for s in self.shards:
            if s.age < s.life:
                s.update(dt)
                alive = True
        if not alive:
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        for s in self.shards:
            frac = s.age / s.life
            if frac >= 1.0:
                continue
            alpha = int(255 * (1.0 - frac) ** 0.8)
            if alpha <= 0:
                continue
            rot = pygame.transform.rotate(s.img, s.angle)
            rot.set_alpha(alpha)
            r = rot.get_rect(center=(int(s.x), int(s.y)))
            surface.blit(rot, r)
