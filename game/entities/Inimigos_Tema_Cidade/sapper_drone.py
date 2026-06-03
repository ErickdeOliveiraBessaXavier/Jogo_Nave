"""Sapper Drone (Rebocador) — suporte de blindagem do bioma CITY.

Variante de apoio da linhagem do City Drone. Não ataca: **engata um cabo** num
aliado próximo e o **blinda** — injeta HP de armadura (overheal) até um teto por
alvo, deixando-o mais resistente. O counterplay é **abatê-lo** (vida baixa, alvo
prioritário): sem o Rebocador, os aliados deixam de ganhar blindagem.

Sem nova infra: a blindagem é incremento direto de `health` do aliado (atributo
público — mesmo padrão do `ChannelingGroup`, §1); o cabo é desenhado no draw. O
teto por alvo evita pump infinito.

Contratos (CLAUDE.md): §5 update polimórfico; §3 `draw` só lê estado; §8 dano via
`HitResult`; §11 `aggressiveness`/`health_multiplier`.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

import pygame

from ...core.config import config as Config
from ...entities.explosion import ExplosionType
from ..enemy_hit_mixin import EnemyHitMixin
from . import city_glow
from . import city_palette as pal
from .sapper_drone_pixel_map import (
    CLAW_CELLS,
    CLAW_NEON,
    CORE_CELLS,
    CORE_NEON,
    CORE_NEON_DIM,
    PIXEL_COLS,
    PIXEL_ROWS,
    REPAIR,
    build_sapper_surface,
)

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult


class SapperDrone(EnemyHitMixin):
    CELL: int = 4
    SIZE: int = PIXEL_COLS * CELL  # 52px

    HEALTH: int = 50
    POINTS: int = 220

    CABLE_RANGE: float = 230.0       # alcance p/ engatar/manter o cabo
    HOVER_DIST: float = 90.0         # distância que paira do alvo
    MOVE_SPEED: float = 130.0
    DRIFT_SPEED: float = 70.0        # deriva quando sem alvo (avança p/ esquerda)
    ARMOR_RATE: float = 14.0         # HP de blindagem por segundo
    ARMOR_PER_TARGET: float = 60.0   # teto de blindagem injetada por aliado
    RESCAN_INTERVAL: Tuple[float, float] = (0.4, 0.8)

    _explosion_size_hit: int = 10

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
        self.w: int = PIXEL_COLS * self.cell
        self.h: int = PIXEL_ROWS * self.cell

        self.x: float = float(x)
        self.y: float = float(y)

        self.dead: bool = False
        self.health: int = max(1, int(self.HEALTH * health_multiplier))
        self.aggressiveness_multiplier: float = aggressiveness_multiplier

        self.target: Any | None = None
        self._granted: Dict[int, float] = {}   # id(alvo) -> blindagem já dada
        self._heal_accum: float = 0.0          # acúmulo fracionário p/ health int
        self._scan_timer: float = random.uniform(*self.RESCAN_INTERVAL)
        self.beaming: bool = False             # cabo ativo neste frame (lido no draw)

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

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt, ctx.other_enemies)

    def update(self, dt: float, other_enemies: List[Any]) -> None:
        if dt <= 0.0:
            return
        self.pulse += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        cx, cy = self._center()

        # Re-seleciona alvo periodicamente (ou se o atual morreu/saiu/encheu).
        self._scan_timer -= dt
        if self.target is not None and not self._target_valid(self.target, cx, cy):
            self.target = None
        if self.target is None and self._scan_timer <= 0.0:
            self._scan_timer = random.uniform(*self.RESCAN_INTERVAL)
            self.target = self._pick_target(other_enemies, cx, cy)

        self.beaming = False
        if self.target is not None:
            self._tend_target(dt, cx, cy)
        else:
            self._drift(dt)

    def _is_ally(self, e: Any) -> bool:
        # Aliado = qualquer inimigo com HP atacável, exceto outro Rebocador e bosses.
        if e is self or isinstance(e, SapperDrone):
            return False
        if getattr(e, "dead", False) or getattr(e, "is_boss", False):
            return False
        return isinstance(getattr(e, "health", None), int)

    def _pick_target(self, others: List[Any], cx: float, cy: float) -> Any | None:
        best: Any | None = None
        best_d2 = self.CABLE_RANGE * self.CABLE_RANGE
        for e in others:
            if not self._is_ally(e):
                continue
            if self._granted.get(id(e), 0.0) >= self.ARMOR_PER_TARGET:
                continue
            ex = getattr(e, "x", cx) + getattr(e, "w", 0) / 2
            ey = getattr(e, "y", cy) + getattr(e, "h", 0) / 2
            d2 = (ex - cx) ** 2 + (ey - cy) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best = e
        return best

    def _target_valid(self, t: Any, cx: float, cy: float) -> bool:
        if not self._is_ally(t):
            return False
        if self._granted.get(id(t), 0.0) >= self.ARMOR_PER_TARGET:
            return False
        tx = getattr(t, "x", cx) + getattr(t, "w", 0) / 2
        ty = getattr(t, "y", cy) + getattr(t, "h", 0) / 2
        return (tx - cx) ** 2 + (ty - cy) ** 2 <= self.CABLE_RANGE * self.CABLE_RANGE

    def _tend_target(self, dt: float, cx: float, cy: float) -> None:
        t = self.target
        assert t is not None
        tx = t.x + getattr(t, "w", 0) / 2
        ty = t.y + getattr(t, "h", 0) / 2
        dx, dy = tx - cx, ty - cy
        dist = math.hypot(dx, dy) or 1.0

        # Paira a HOVER_DIST do alvo (aproxima se longe, recua se colado).
        desired = (dist - self.HOVER_DIST)
        step = max(-self.MOVE_SPEED, min(self.MOVE_SPEED, desired * 2.0)) * dt
        self.x += dx / dist * step
        self.y += dy / dist * step

        # Injeta blindagem (HP) até o teto por alvo, dentro do alcance.
        if dist <= self.CABLE_RANGE:
            self.beaming = True
            room = self.ARMOR_PER_TARGET - self._granted.get(id(t), 0.0)
            add = min(room, self.ARMOR_RATE * dt)
            if add > 0.0:
                self._heal_accum += add
                self._granted[id(t)] = self._granted.get(id(t), 0.0) + add
                whole = int(self._heal_accum)
                if whole >= 1:
                    self._heal_accum -= whole
                    t.health = int(getattr(t, "health", 0)) + whole
                    if hasattr(t, "max_health"):
                        t.max_health = max(int(t.max_health), int(t.health))

    def _drift(self, dt: float) -> None:
        # Sem alvo: deriva devagar na direção de avanço do bioma.
        if self.side_scroll:
            self.x -= self.DRIFT_SPEED * dt
            if self.x + self.w < -40.0:
                self.dead = True
        else:
            self.y += self.DRIFT_SPEED * dt
            if self.y - self.h > Config.SCREEN_HEIGHT + 40.0:
                self.dead = True

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
                explosion_size=26,
                explosion_type=ExplosionType.CYBER,
                sound=hit_sounds.EXPLOSION_ALIEN,
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
            explosion_size=26,
            explosion_type=ExplosionType.CYBER,
            sound=hit_sounds.EXPLOSION_ALIEN,
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

        # Cabo de reparo até o alvo (atrás do corpo).
        if self.beaming and self.target is not None and not self.target.dead:
            self._draw_cable(surface, icx, icy)

        base = build_sapper_surface(cell)
        if self.hit_timer > 0.0:
            img = base.copy()
            img.fill((200, 200, 200), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, (int(self.x), int(self.y)))
        else:
            surface.blit(base, (int(self.x), int(self.y)))

        # Núcleo verde pulsante (mais forte enquanto reboca).
        pulse = 0.5 + 0.5 * math.sin(self.pulse * 5.0)
        boost = 0.5 if self.beaming else 0.0
        core_col = pal.lerp(CORE_NEON_DIM, CORE_NEON, min(1.0, pulse + boost))
        core_r = int(cell * (1.3 + pulse) + cell * 1.4 * boost)
        for c, r in CORE_CELLS:
            self._blit_glow(
                surface,
                int(self.x + (c + 0.5) * cell),
                int(self.y + (r + 0.5) * cell),
                core_r,
                core_col,
            )
        # Garras.
        flick = 0.5 + 0.5 * math.sin(self.pulse * 14.0)
        for c, r in CLAW_CELLS:
            self._blit_glow(
                surface,
                int(self.x + (c + 0.5) * cell),
                int(self.y + (r + 0.5) * cell),
                int(cell * (1.0 + 0.5 * flick)),
                CLAW_NEON,
            )

    def _draw_cable(self, surface: pygame.Surface, icx: int, icy: int) -> None:
        t = self.target
        if t is None:
            return
        tx = int(t.x + getattr(t, "w", 0) / 2)
        ty = int(t.y + getattr(t, "h", 0) / 2)
        # Cabo crepitante (jitter por segmento) verde-ciano.
        segs = 8
        flick = 0.5 + 0.5 * math.sin(self.pulse * 22.0)
        amp = 2.0 + 3.0 * flick
        prev = (icx, icy)
        for k in range(1, segs + 1):
            f = k / segs
            mx = icx + (tx - icx) * f
            my = icy + (ty - icy) * f
            if k < segs:
                mx += random.uniform(-amp, amp)
                my += random.uniform(-amp, amp)
            pygame.draw.line(surface, REPAIR, prev, (int(mx), int(my)), 2)
            prev = (int(mx), int(my))
        # Halo no ponto de reparo do aliado.
        self._blit_glow(surface, tx, ty, int(self.cell * 2.0), REPAIR)
