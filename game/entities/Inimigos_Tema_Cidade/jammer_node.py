"""Jammer Node — "O Glitch" (simplificado) do bioma CITY.

Nó de interferência da linhagem do Cyber-Captor. Não desce: **orbita um ponto
fixo** no alto da tela e projeta um **campo estático circular** que **suprime os
tiros da nave** (os projéteis que entram no campo fizzlam, sem causar dano). O
campo **pisca** num ciclo curto (glitch), abrindo micro-janelas de fogo — o
counterplay é atirar de um ângulo livre ou furar o nó (vida baixa, alvo
prioritário). Morte **"EMP pop"**: o EntityManager dispara um `CaptorEMP` curto.

Diferente do Captor, **não tem raio de dano** — sua pressão é puramente negar a
ofensiva por área, forçando reposicionamento. O bloqueio em si mora no sistema
de colisão: este expõe `projectile_fields()` (contrato duck-typed do §5),
consumido por `Collisions.projectiles_vs_blocker_fields`.

Contratos (convenções do projeto): §5 update polimórfico via `update_in_context`; §3 `draw`
só lê estado; §8 dano via `HitResult`; §11 `aggressiveness`/`health_multiplier`.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List, Tuple

import pygame

from ...core.config import config as Config
from ..enemy_hit_mixin import EnemyHitMixin
from . import city_glow
from . import city_palette as pal
from .jammer_node_pixel_map import (
    ANTENNA_CELLS,
    ANTENNA_NEON,
    CORE_CELLS,
    CORE_NEON,
    CORE_NEON_DIM,
    PIXEL_COLS,
    PIXEL_ROWS,
    build_node_surface,
)

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult

_FIELD: pal.RGB = pal.CYBER_MAGENTA
_FIELD_DIM: pal.RGB = pal.CYBER_MAGENTA_DIM


class JammerNode(EnemyHitMixin):
    CELL: int = 5
    SIZE: int = PIXEL_COLS * CELL  # 65px

    HEALTH: int = 70
    POINTS: int = 240

    # ── Órbita (não desce; orbita um ponto fixo no alto) ─────────────────────
    ORBIT_RX: float = 70.0
    ORBIT_RY: float = 40.0
    ORBIT_SPEED: float = 0.7   # rad/s
    ENTER_DURATION: float = 0.8

    # ── Campo estático (suprime tiros da nave) ───────────────────────────────
    JAM_RADIUS: float = 92.0   # raio do campo de bloqueio
    FIELD_ON_TIME: float = 2.6  # campo ativo
    FIELD_OFF_TIME: float = 0.9  # flicker glitch (janela de fogo)

    EMP_RADIUS: int = 110      # raio do EMP pop na morte

    _explosion_size_hit: int = 10

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = True,
        anchor: Tuple[float, float] | None = None,
        health_multiplier: float = 1.0,
    ) -> None:
        self.side_scroll: bool = side_scroll
        self.cell: int = self.CELL
        self.w: int = PIXEL_COLS * self.cell
        self.h: int = PIXEL_ROWS * self.cell

        self.x: float = float(x)
        self.y: float = float(y)

        self.dead: bool = False
        self.health: int = max(1, int(self.HEALTH * health_multiplier))
        self.aggressiveness_multiplier: float = aggressiveness_multiplier

        # Ponto fixo que orbita (alto da tela por padrão).
        ax, ay = anchor if anchor is not None else (x, y)
        self.anchor_x: float = max(
            self.ORBIT_RX + 20.0, min(Config.SCREEN_WIDTH - self.ORBIT_RX - 20.0, ax)
        )
        self.anchor_y: float = max(
            self.ORBIT_RY + 40.0, min(Config.SCREEN_HEIGHT * 0.45, ay)
        )
        self.orbit_angle: float = random.uniform(0.0, math.tau)
        self.spawn_x: float = float(x)
        self.spawn_y: float = float(y)
        self.enter_t: float = 0.0
        self.entering: bool = True

        # Ciclo do campo (glitch flicker). Começa ligado.
        self.field_on: bool = True
        self.field_timer: float = self.FIELD_ON_TIME

        self.pulse: float = random.uniform(0.0, math.tau)
        self.hit_timer: float = 0.0

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> Tuple[float, float, float]:
        return self.x + self.w / 2, self.y + self.h / 2, self.w * 0.40

    def _center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def projectile_fields(self) -> List[Tuple[object, ...]]:
        """Campo circular que suprime tiros da nave (contrato duck-typed do §5,
        consumido por `Collisions.projectiles_vs_blocker_fields`). Vazio enquanto
        entra ou durante o flicker (off) — quando há janela de fogo."""
        if self.entering or not self.field_on:
            return []
        cx, cy = self._center()
        return [("circle", cx, cy, self.JAM_RADIUS)]

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt, ctx.player_x, ctx.player_y)

    def update(self, dt: float, _player_x: float, _player_y: float) -> None:
        if dt <= 0.0:
            return

        self.pulse += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        # Posição na órbita (ponto fixo no alto da tela).
        self.orbit_angle += self.ORBIT_SPEED * dt
        ox = self.anchor_x + math.cos(self.orbit_angle) * self.ORBIT_RX
        oy = self.anchor_y + math.sin(self.orbit_angle) * self.ORBIT_RY
        target_x = ox - self.w / 2
        target_y = oy - self.h / 2
        if self.entering:
            self.enter_t += dt
            p = min(1.0, self.enter_t / self.ENTER_DURATION)
            e = p * p * (3.0 - 2.0 * p)  # smoothstep
            self.x = self.spawn_x + (target_x - self.spawn_x) * e
            self.y = self.spawn_y + (target_y - self.spawn_y) * e
            if p >= 1.0:
                self.entering = False
            return

        self.x, self.y = target_x, target_y

        # Ciclo do campo (glitch flicker).
        self.field_timer -= dt
        if self.field_timer <= 0.0:
            self.field_on = not self.field_on
            self.field_timer = self.FIELD_ON_TIME if self.field_on else self.FIELD_OFF_TIME

    # ── Dano / morte ──────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.08
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
                explosion_size=0,  # a morte é o EMP pop (special death)
                sound=hit_sounds.EXPLOSION_ALIEN,
                triggers_special_death=True,
            )
        return HitResult(
            explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        self.dead = True
        return HitResult(
            killed=True,
            explosion_size=0,
            sound=hit_sounds.EXPLOSION_ALIEN,
            triggers_special_death=True,
        )

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
        cx, cy = self._center()
        icx, icy = int(cx), int(cy)

        # Campo estático (atrás do corpo): haze + anel crepitante quando ativo.
        if not self.entering and self.field_on:
            self._draw_field(surface, icx, icy)

        # Corpo-nó (flash de hit com BLEND_RGB_ADD).
        base = build_node_surface(cell)
        if self.hit_timer > 0.0:
            img = base.copy()
            img.fill((200, 200, 200), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, (int(self.x), int(self.y)))
        else:
            surface.blit(base, (int(self.x), int(self.y)))

        # Núcleo magenta pulsante (mais intenso com o campo ligado).
        pulse = 0.5 + 0.5 * math.sin(self.pulse * 6.0)
        boost = 0.6 if (self.field_on and not self.entering) else 0.0
        core_col = pal.lerp(CORE_NEON_DIM, CORE_NEON, min(1.0, pulse + boost))
        cr = int(cell * (1.4 + pulse) + cell * 1.5 * boost)
        for c, r in CORE_CELLS:
            self._blit_glow(
                surface,
                int(self.x + (c + 0.5) * cell),
                int(self.y + (r + 0.5) * cell),
                cr,
                core_col,
            )

        # Antenas emissoras (azul), crepitando mais rápido que o núcleo.
        flick = 0.5 + 0.5 * math.sin(self.pulse * 16.0)
        ant_r = int(cell * (1.0 + 0.6 * flick))
        for c, r in ANTENNA_CELLS:
            self._blit_glow(
                surface,
                int(self.x + (c + 0.5) * cell),
                int(self.y + (r + 0.5) * cell),
                ant_r,
                ANTENNA_NEON,
            )

    def _draw_field(self, surface: pygame.Surface, icx: int, icy: int) -> None:
        radius = int(self.JAM_RADIUS)
        # Haze radial (glow magenta) preenchendo o campo.
        haze = 0.5 + 0.5 * math.sin(self.pulse * 4.0)
        self._blit_glow(
            surface, icx, icy, radius, pal.lerp(_FIELD_DIM, _FIELD, 0.3 + 0.4 * haze)
        )
        # Anel crepitante (jitter por segmento → estática glitch).
        segs = 18
        flick = 0.5 + 0.5 * math.sin(self.pulse * 24.0)
        amp = 2.0 + 4.0 * flick
        prev: Tuple[int, int] | None = None
        first: Tuple[int, int] | None = None
        for k in range(segs):
            a = (k / segs) * math.tau
            rr = radius + random.uniform(-amp, amp)
            px = int(icx + math.cos(a) * rr)
            py = int(icy + math.sin(a) * rr)
            if prev is not None:
                pygame.draw.line(surface, _FIELD, prev, (px, py), 2)
            else:
                first = (px, py)
            prev = (px, py)
        if prev is not None and first is not None:
            pygame.draw.line(surface, _FIELD, prev, first, 2)
