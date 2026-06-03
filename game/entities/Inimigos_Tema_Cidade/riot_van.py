"""Riot Van (Escudeiro) — escolta blindada do bioma CITY.

Variante de suporte da linhagem do Police Interceptor: um furgão de choque que
**avança devagar** projetando um **escudo de energia frontal** (uma barra
vertical à frente, do lado do jogador) que **bloqueia os tiros da nave** — e, por
ser uma parede, **protege também os aliados atrás dele**. O counterplay é
**flanquear** (atirar de cima/baixo, fora da barra) ou furar o próprio furgão.

O bloqueio reusa a infra da Fase 0: a entidade expõe `projectile_fields()` (um
segmento vertical), consumido por `Collisions.projectiles_vs_blocker_fields`.
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
from .riot_van_pixel_map import (
    CORE_CELLS,
    CORE_NEON,
    CORE_NEON_DIM,
    EMITTER_CELLS,
    EMITTER_NEON,
    PIXEL_COLS,
    PIXEL_ROWS,
    build_van_surface,
)

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult

_SHIELD: pal.RGB = pal.ELECTRIC_BLUE
_SHIELD_HOT: pal.RGB = (215, 245, 255)


class RiotVan(EnemyHitMixin):
    CELL: int = 5
    W: int = PIXEL_COLS * CELL  # 85px
    H: int = PIXEL_ROWS * CELL  # 55px
    SIZE: int = W

    HEALTH: int = 150
    POINTS: int = 320

    ENTER_SPEED: float = 150.0
    ADVANCE_SPEED: float = 42.0       # avança devagar p/ a esquerda (escolta)
    ENTER_TARGET_FRAC: float = 0.88   # x-centro onde para de entrar
    BOB_AMP: float = 18.0             # amplitude do bob vertical
    BOB_SPEED: float = 1.6

    SHIELD_OFFSET: float = 16.0       # distância do escudo à frente do corpo
    SHIELD_HALF: float = 42.0         # meia-altura da barra de escudo
    SHIELD_BLOCK_RADIUS: float = 12.0

    _explosion_size_hit: int = 12
    _explosion_size_killed: int = 40

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
        self.pulse: float = random.uniform(0.0, math.tau)
        self.hit_timer: float = 0.0

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> Tuple[float, float, float]:
        return self.x + self.w / 2, self.y + self.h / 2, self.h * 0.46

    def _center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def _shield_segment(self) -> Tuple[float, float, float, float]:
        """Barra vertical do escudo à frente do furgão (lado do jogador)."""
        cx, cy = self._center()
        if self.side_scroll:
            sx = self.x - self.SHIELD_OFFSET  # frente = esquerda
            return sx, cy - self.SHIELD_HALF, sx, cy + self.SHIELD_HALF
        sy = self.y + self.h + self.SHIELD_OFFSET  # frente = baixo
        return cx - self.SHIELD_HALF, sy, cx + self.SHIELD_HALF, sy

    def projectile_fields(self) -> List[Tuple[object, ...]]:
        """Escudo frontal que bloqueia tiros da nave (contrato duck-typed do §5).
        Ativo enquanto vivo e já posicionado (após a entrada)."""
        if self.state == "enter":
            return []
        ax, ay, bx, by = self._shield_segment()
        return [("seg", ax, ay, bx, by, self.SHIELD_BLOCK_RADIUS)]

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt, ctx.player_x, ctx.player_y)

    def update(self, dt: float, _player_x: float, _player_y: float) -> None:
        if dt <= 0.0:
            return

        self.pulse += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        if self.state == "enter":
            cx = self.x + self.w / 2 - self.ENTER_SPEED * dt
            if cx <= self.enter_target:
                cx = self.enter_target
                self.state = "advance"
            self.x = cx - self.w / 2
        else:  # advance
            self.x -= self.ADVANCE_SPEED * dt
            if self.x + self.w < -40.0:
                self.dead = True  # escolta atravessou e saiu pela esquerda

        # Bob vertical (vida; não muda a defesa frontal).
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

        # Furgão pesado: sobrevive ao contato (a nave leva dano pela camada de
        # colisão). Não pode ser derrubado por ramming — destrua-o com tiros.
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

        # Escudo (à frente do corpo): barra crepitante quando ativo.
        if self.state != "enter":
            self._draw_shield(surface)

        base = build_van_surface(cell)
        if self.hit_timer > 0.0:
            img = base.copy()
            img.fill((200, 200, 200), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, (int(self.x), int(self.y)))
        else:
            surface.blit(base, (int(self.x), int(self.y)))

        # Glows: núcleo + emissores (azul pulsante).
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
        flick = 0.5 + 0.5 * math.sin(self.pulse * 14.0)
        for c, r in EMITTER_CELLS:
            self._blit_glow(
                surface,
                int(self.x + (c + 0.5) * cell),
                int(self.y + (r + 0.5) * cell),
                int(cell * (1.2 + 0.6 * flick)),
                EMITTER_NEON,
            )

    def _draw_shield(self, surface: pygame.Surface) -> None:
        ax, ay, bx, by = self._shield_segment()
        iax, iay, ibx, iby = int(ax), int(ay), int(bx), int(by)
        flick = 0.5 + 0.5 * math.sin(self.pulse * 22.0)
        # Barra crepitante (jitter por segmento) + halo nos emissores.
        segs = 10
        prev = (iax, iay)
        amp = 2.0 + 3.0 * flick
        for k in range(1, segs + 1):
            t = k / segs
            mx = ax + (bx - ax) * t
            my = ay + (by - ay) * t
            if k < segs:
                mx += random.uniform(-amp, amp)
            pygame.draw.line(surface, _SHIELD, prev, (int(mx), int(my)), 3)
            pygame.draw.line(surface, _SHIELD_HOT, prev, (int(mx), int(my)), 1)
            prev = (int(mx), int(my))
        self._blit_glow(surface, iax, iay, int(self.cell * 1.8), _SHIELD)
        self._blit_glow(surface, ibx, iby, int(self.cell * 1.8), _SHIELD)
