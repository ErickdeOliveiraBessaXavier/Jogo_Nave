"""Mirror Pylon (Refletor) — pilar refletor do bioma CITY.

Variante da linhagem do Tesla Twin: um pilar que **avança devagar** com uma
**face espelhada frontal** (lado do jogador) que **reflete os tiros da nave** —
devolve cada projétil como um `NeonBolt` inimigo voltando para o jogador. O
counterplay é **flanquear** (atirar de cima/baixo, fora da face) ou furar o pilar
pelas costas; atirar de frente só alimenta o contra-ataque.

O design atual é uma **estrutura triangular equilibrada** (31x41) com
emiissores mecânicos menores e um núcleo energético dominante.

Contratos (convenções do projeto): §5 update polimórfico; §3 `draw` só lê estado; §8 dano via
`HitResult`; §11 `aggressiveness`/`health_multiplier`.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List, Tuple

import pygame

from ...core.config import config as Config
from ...entities.explosion import ExplosionType
from ..enemy_hit_mixin import EnemyHitMixin
from . import city_glow
from . import city_palette as pal
from .mirror_pylon_pixel_map import (
    CORE_CELLS,
    CORE_NEON,
    CORE_NEON_DIM,
    MIRROR_CELLS,
    MIRROR_NEON,
    PIXEL_COLS,
    PIXEL_ROWS,
    build_pylon_surface,
)

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult

_MIRROR: pal.RGB = (200, 240, 255)


class MirrorPylon(EnemyHitMixin):
    CELL: int = 5
    W: int = PIXEL_COLS * CELL  # 160px (32x5)
    H: int = PIXEL_ROWS * CELL  # 205px (41x5)
    SIZE: int = H

    HEALTH: int = 130
    POINTS: int = 400

    ENTER_SPEED: float = 160.0
    ADVANCE_SPEED: float = 38.0
    ENTER_TARGET_FRAC: float = 0.8
    BOB_AMP: float = 15.0
    BOB_SPEED: float = 1.0

    # Face refletora (alinhada à frente dos emissores)
    MIRROR_BLOCK_RADIUS: float = 18.0
    REFLECT_SPEED: float = 350.0

    _explosion_size_hit: int = 16
    _explosion_size_killed: int = 42

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = True,
        health_multiplier: float = 1.0,
    ) -> None:
        self.side_scroll: bool = side_scroll
        self.cell: int = self.CELL
        self.w: int = self.W
        self.h: int = self.H

        self.x: float = float(x)
        self.base_y: float = float(y)
        self.y: float = float(y)

        self.dead: bool = False
        self.health: int = max(1, int(self.HEALTH * health_multiplier))
        self.aggressiveness_multiplier: float = aggressiveness_multiplier

        self.state: str = "enter"
        self.enter_target: float = self.ENTER_TARGET_FRAC * Config.SCREEN_WIDTH
        self.reflect_flash: float = 0.0

        self.pulse: float = random.uniform(0.0, math.tau)
        self.hit_timer: float = 0.0

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> Tuple[float, float, float]:
        # Círculo envolvente (bounding) que começa em x=11.5 (limite da reflexão)
        # Centrado aproximadamente no Core para abranger a estrutura vulnerável.
        return self.x + 26.5 * self.cell, self.y + 20.5 * self.cell, 15 * self.cell

    def collision_circles(self) -> List[Tuple[float, float, float]]:
        """Hitboxes circulares precisas para cada esfera (contrato §5 estendido)."""
        c = self.cell
        return [
            (self.x + 24.5 * c, self.y + 20.5 * c, 6.0 * c), # Core
            (self.x + 11.5 * c, self.y + 5.5 * c, 3.2 * c),  # Emitter Top
            (self.x + 11.5 * c, self.y + 35.5 * c, 3.2 * c), # Emitter Bot
        ]

    def get_ship_contact_hitboxes(self) -> List[pygame.Rect]:
        """Hitboxes retangulares para o passo AABB (contrato §5)."""
        c = self.cell
        return [
            pygame.Rect(int(self.x + 18 * c), int(self.y + 14 * c), 13 * c, 13 * c), # Core
            pygame.Rect(int(self.x + 8 * c), int(self.y + 2 * c), 7 * c, 7 * c),      # Top
            pygame.Rect(int(self.x + 8 * c), int(self.y + 32 * c), 7 * c, 7 * c),     # Bot
        ]

    def _center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def _mirror_segment(self) -> Tuple[float, float, float, float]:
        # Face frontal de reflexão energética perfeitamente alinhada com o raio visual
        # Verticalmente estritamente entre os emissores (y=5 e y=35, raio 3)
        fx = self.x + 11.5 * self.cell
        ty = self.y + 8.5 * self.cell
        by = self.y + 31.5 * self.cell
        return fx, ty, fx, by
    def reflect_field(self) -> List[Tuple[object, ...]]:
        """Contrato duck-typed (§5): retorna segmento de reflexão."""
        if self.state == "enter":
            return []
        ax, ay, bx, by = self._mirror_segment()
        return [("seg", ax, ay, bx, by, self.MIRROR_BLOCK_RADIUS, self.REFLECT_SPEED)]

    def notify_reflected(self) -> None:
        self.reflect_flash = 0.2

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt, ctx.player_x, ctx.player_y)

    def update(self, dt: float, _player_x: float, _player_y: float) -> None:
        if dt <= 0.0:
            return
        self.pulse += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)
        if self.reflect_flash > 0.0:
            self.reflect_flash = max(0.0, self.reflect_flash - dt)

        if self.state == "enter":
            cx = self.x + self.w / 2 - self.ENTER_SPEED * dt
            if cx <= self.enter_target:
                cx = self.enter_target
                self.state = "advance"
            self.x = cx - self.w / 2
        else:
            self.x -= self.ADVANCE_SPEED * dt
            if self.x + self.w < -60.0:
                self.dead = True

        self.y = self.base_y + math.sin(self.pulse * self.BOB_SPEED) * self.BOB_AMP

    # ── Dano / morte ──────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.07
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=self._explosion_size_killed,
                explosion_type=ExplosionType.CYBER,
                sound=hit_sounds.EXPLOSION_ALIEN,
            )
        return HitResult(
            explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        return HitResult(killed=False, explosion_size=12, sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool:
        return self.dead

    # ── Render ──────────────────────────────────────────────────────────────
    def _blit_glow(
        self, surface: pygame.Surface, cx: int, cy: int, radius: int, color: pal.RGB
    ) -> None:
        glow = city_glow.get_glow(radius, color)
        surface.blit(
            glow, (cx - radius, cy - radius), special_flags=pygame.BLEND_RGBA_ADD
        )

    def draw(self, surface: pygame.Surface) -> None:
        cell = self.cell

        # 1. Raios de energia dinâmicos - Agora a principal conexão visual e de feedback
        self._draw_dynamic_rays(surface)

        # 2. Base (esferas isoladas)
        base = build_pylon_surface(cell)
        if self.hit_timer > 0.0:
            img = base.copy()
            img.fill((200, 200, 200), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, (int(self.x), int(self.y)))
        else:
            surface.blit(base, (int(self.x), int(self.y)))

        # 3. Glow do Núcleo (Sutil e contido)
        p = 0.5 + 0.5 * math.sin(self.pulse * 6.0)
        core_col = pal.lerp(CORE_NEON_DIM, CORE_NEON, 0.4 + 0.6 * p)
        for c, r in CORE_CELLS:
            self._blit_glow(
                surface,
                int(self.x + (c + 0.5) * cell),
                int(self.y + (r + 0.5) * cell),
                int(cell * (0.8 + p * 0.7)),  # Reduzido para não poluir
                core_col,
            )

        # 4. Glow dos Emiissores (Discreto)
        shine = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(self.pulse * 10.0))
        for c, r in MIRROR_CELLS:
            self._blit_glow(
                surface,
                int(self.x + (c + 0.5) * cell),
                int(self.y + (r + 0.5) * cell),
                int(cell * (0.6 + 0.4 * shine)),
                MIRROR_NEON,
            )

    def _draw_dynamic_rays(self, surface: pygame.Surface) -> None:
        """Conexões elétricas instáveis entre os três pontos."""
        cell = self.cell
        # Centros baseados no novo mapa 31x41 (com distância 1.5x)
        core_pos = (self.x + 24.5 * cell, self.y + 20.5 * cell)
        top_pos = (self.x + 11.5 * cell, self.y + 5.5 * cell)
        bot_pos = (self.x + 11.5 * cell, self.y + 35.5 * cell)

        self._draw_arc(surface, core_pos, top_pos)
        self._draw_arc(surface, core_pos, bot_pos)
        # O feixe frontal (espelho) reage visualmente à reflexão
        self._draw_arc(surface, top_pos, bot_pos, is_mirror_face=True)

    def _draw_arc(
        self,
        surface: pygame.Surface,
        a: Tuple[float, float],
        b: Tuple[float, float],
        is_mirror_face: bool = False,
    ) -> None:
        ax, ay = a
        bx, by = b
        segs = 10
        flick = 0.5 + 0.5 * math.sin(self.pulse * 22.0)

        # Jitter aumenta durante a reflexão
        flash = self.reflect_flash * 5.0  # 0..1
        amp = 6.0 + 8.0 * flick
        if is_mirror_face:
            amp = 4.0 + 8.0 * flick + flash * 15.0

        main_col = (100, 220, 255)
        hot_col = (210, 250, 255)
        # Espessura dinâmica: aumenta quando reflete tiros (de 2 até 6 pixels)
        thickness = 2
        if is_mirror_face and flash > 0.0:
            thickness = int(2 + flash * 4)

        # Se estiver refletindo, o raio brilha intensamente
        if is_mirror_face and flash > 0.0:
            main_col = pal.lerp(main_col, (255, 255, 255), flash)
            hot_col = (255, 255, 255)
        prev = (int(ax), int(ay))
        for k in range(1, segs + 1):
            t = k / segs
            mx = ax + (bx - ax) * t
            my = ay + (by - ay) * t
            if k < segs:
                mx += (random.random() - 0.5) * amp
                my += (random.random() - 0.5) * amp

            pygame.draw.line(surface, main_col, prev, (int(mx), int(my)), thickness)
            pygame.draw.line(surface, hot_col, prev, (int(mx), int(my)), 1)
            prev = (int(mx), int(my))

        glow_r = int(self.cell * (0.6 + 0.4 * flick))
        if is_mirror_face and flash > 0.0:
            glow_r = int(glow_r * (1.0 + flash * 2.0))

        self._blit_glow(surface, int(ax), int(ay), glow_r, main_col)
        self._blit_glow(surface, int(bx), int(by), glow_r, main_col)
