"""CarrierDebris — destroços físicos do Cargueiro (CargoCarrier) ao ser destruído.

Cosmético puro (como `SplitterDebris`/`PoliceCrash`/`TankMeltdown`): ao morrer, o
chassi do cargueiro se estilhaça nos **fragmentos de pixel-art**
(`Cargueiro/Fragmentos_Cargueiro`) que voam para fora a partir do centro, ganham
gravidade, **giram** e **esmaecem**. São exatamente os pedaços recortados à mão
no Photoshop — **um caco por fragmento** (sem repetição), para o estilhaço bater
com a imagem original.

Interface duck-typed dos efeitos do EntityManager: `update(dt)`, `draw(surface)`,
`dead`, `rect`. Não entra na grid de colisão nem na lista de inimigos — não conta
como hostil para a progressão de fase.
"""

from __future__ import annotations

import math
import random
from typing import List

import pygame

from ....core.assets import BASE_DIR, get_image

_SHARD_DIR = BASE_DIR / "assets" / "images" / "Cargueiro" / "Fragmentos_Cargueiro"
_SHARD_FILE_COUNT: int = 7

GRAVITY: float = 520.0  # aceleração da queda dos cacos (px/s²)
DRAG: float = 0.5       # arrasto horizontal por segundo

# Um caco por fragmento recortado (7 ao todo); nave pesada → arremesso mais forte.
_SCALE: float = 1.9            # fator sobre o tamanho nativo (24px) → ~46px
_LIFE: float = 1.10            # tempo de vida (s) antes de esmaecer
_SPEED: tuple[float, float] = (110.0, 270.0)


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


class CarrierDebris:
    # Cacos crus (24px) carregados uma vez; escalados por caco no spawn (§7).
    _raw_frames: List[pygame.Surface] = []

    @classmethod
    def _frames(cls) -> List[pygame.Surface]:
        if not cls._raw_frames:
            cls._raw_frames = [
                get_image(_SHARD_DIR / f"PNG_Inimigo_Carga_Fragmentos ({i}).png")
                for i in range(1, _SHARD_FILE_COUNT + 1)
            ]
        return cls._raw_frames

    def __init__(self, cx: float, cy: float) -> None:
        frames = self._frames()
        self.dead: bool = False
        self.shards: List[_Shard] = []
        # Um caco por fragmento recortado (sem repetição) → o estilhaço usa
        # exatamente os pedaços da imagem original.
        for base in frames:
            # Escala o tamanho NATIVO do caco (24px); jitter por caco quebra a
            # uniformidade.
            bw, bh = base.get_size()
            f = _SCALE * random.uniform(0.85, 1.15)
            img = pygame.transform.scale(base, (max(2, int(bw * f)), max(2, int(bh * f))))
            ang = random.uniform(0.0, math.tau)
            spd = random.uniform(*_SPEED)
            self.shards.append(
                _Shard(
                    cx,
                    cy,
                    vx=math.cos(ang) * spd,
                    # Pequeno empuxo inicial pra cima → arco antes de cair.
                    vy=math.sin(ang) * spd - random.uniform(30.0, 90.0),
                    life=_LIFE * random.uniform(0.8, 1.2),
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
        return pygame.Rect(int(x0) - 24, int(y0) - 24, int(x1 - x0) + 48, int(y1 - y0) + 48)

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
