"""Mirror Pylon (Refletor) — pilar refletor do bioma CITY.

Variante da linhagem do Tesla Twin: um pilar que **avança devagar** com uma
**face espelhada frontal** (lado do jogador) que **reflete os tiros da nave** —
devolve cada projétil como um `NeonBolt` inimigo voltando para o jogador. O
counterplay é **flanquear** (atirar de cima/baixo, fora da face) ou furar o pilar
pelas costas; atirar de frente só alimenta o contra-ataque.

A reflexão mora no sistema de colisão (que tem acesso aos projéteis e ao buffer
de bolts): a entidade expõe `reflect_field()` (segmento da face espelhada,
duck-typed §5), consumido por `Collisions.projectiles_vs_reflectors`.

Contratos (CLAUDE.md): §5 update polimórfico; §3 `draw` só lê estado; §8 dano via
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
    W: int = PIXEL_COLS * CELL  # 55px
    H: int = PIXEL_ROWS * CELL  # 85px
    SIZE: int = H

    HEALTH: int = 110
    POINTS: int = 300

    ENTER_SPEED: float = 150.0
    ADVANCE_SPEED: float = 34.0
    ENTER_TARGET_FRAC: float = 0.85
    BOB_AMP: float = 22.0
    BOB_SPEED: float = 1.3

    MIRROR_OFFSET: float = 14.0       # face espelhada à frente do corpo
    MIRROR_HALF: float = 46.0         # meia-altura da face
    MIRROR_BLOCK_RADIUS: float = 13.0
    REFLECT_SPEED: float = 330.0      # velocidade do bolt refletido

    _explosion_size_hit: int = 12
    _explosion_size_killed: int = 38

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
        self.reflect_flash: float = 0.0  # pisca a face ao refletir (lido no draw)

        self.pulse: float = random.uniform(0.0, math.tau)
        self.hit_timer: float = 0.0

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> Tuple[float, float, float]:
        return self.x + self.w / 2, self.y + self.h / 2, self.w * 0.46

    def _center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def _mirror_segment(self) -> Tuple[float, float, float, float]:
        cx, cy = self._center()
        if self.side_scroll:
            sx = self.x - self.MIRROR_OFFSET
            return sx, cy - self.MIRROR_HALF, sx, cy + self.MIRROR_HALF
        sy = self.y + self.h + self.MIRROR_OFFSET
        return cx - self.MIRROR_HALF, sy, cx + self.MIRROR_HALF, sy

    def reflect_field(self) -> List[Tuple[object, ...]]:
        """Face espelhada que reflete tiros (contrato duck-typed do §5, consumido
        por `Collisions.projectiles_vs_reflectors`). Vazio enquanto entra.

        Formato: ("seg", ax, ay, bx, by, raio, refl_speed). A direção do bolt
        refletido (de volta ao jogador) é decidida pelo sistema de colisão a
        partir da orientação (side_scroll)."""
        if self.state == "enter":
            return []
        ax, ay, bx, by = self._mirror_segment()
        return [("seg", ax, ay, bx, by, self.MIRROR_BLOCK_RADIUS, self.REFLECT_SPEED)]

    def notify_reflected(self) -> None:
        """Chamado pelo sistema de colisão quando reflete um tiro (feedback visual)."""
        self.reflect_flash = 0.12

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
            if self.x + self.w < -40.0:
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

        return HitResult(killed=False, explosion_size=10, sound=hit_sounds.BOSS_DAMAGE)

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

        if self.state != "enter":
            self._draw_mirror(surface)

        base = build_pylon_surface(cell)
        if self.hit_timer > 0.0:
            img = base.copy()
            img.fill((200, 200, 200), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, (int(self.x), int(self.y)))
        else:
            surface.blit(base, (int(self.x), int(self.y)))

        pulse = 0.5 + 0.5 * math.sin(self.pulse * 5.0)
        core_col = pal.lerp(CORE_NEON_DIM, CORE_NEON, 0.4 + 0.6 * pulse)
        core_r = int(cell * (1.2 + pulse))
        for c, r in CORE_CELLS:
            self._blit_glow(
                surface,
                int(self.x + (c + 0.5) * cell),
                int(self.y + (r + 0.5) * cell),
                core_r,
                core_col,
            )
        # Células de espelho brilham (clarão extra ao refletir).
        shine = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(self.pulse * 10.0))
        shine = min(1.0, shine + (3.0 * self.reflect_flash))
        for c, r in MIRROR_CELLS:
            self._blit_glow(
                surface,
                int(self.x + (c + 0.5) * cell),
                int(self.y + (r + 0.5) * cell),
                int(cell * (1.0 + 0.8 * shine)),
                MIRROR_NEON,
            )

    def _draw_mirror(self, surface: pygame.Surface) -> None:
        ax, ay, bx, by = self._mirror_segment()
        w = max(2, int(self.cell * (0.7 + 1.5 * self.reflect_flash * 8.0)))
        col = (255, 255, 255) if self.reflect_flash > 0.0 else _MIRROR
        pygame.draw.line(surface, col, (int(ax), int(ay)), (int(bx), int(by)), w)
        self._blit_glow(surface, int(ax), int(ay), int(self.cell * 1.6), _MIRROR)
        self._blit_glow(surface, int(bx), int(by), int(self.cell * 1.6), _MIRROR)
