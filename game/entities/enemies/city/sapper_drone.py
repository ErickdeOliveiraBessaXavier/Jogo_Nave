"""Sapper Drone (Rebocador) — suporte defensivo do bioma CITY.

Variante de apoio da linhagem do City Drone. Não ataca: a cada `PULSE_INTERVAL`
segundos emite um **pulso de energia**. Todo aliado dentro de `PULSE_RADIUS`
ganha um **escudo temporário** de 25% do HP atual (no instante do pulso), que
absorve dano antes da vida. O counterplay é **abatê-lo** (vida baixa, alvo
prioritário): sem o Rebocador, o grupo deixa de ser blindado.

A mecânica de escudo é genérica e reutilizável (`systems/enemy_shield.py`, §9):
o drone só chama `grant_shield`; a absorção vive no roteador de dano (§8) e o
render num passe central (§3). O drone não toca no estado interno dos aliados —
comunica pelo contrato público `health`/`shield_hp` (§1).

Contratos (convenções do projeto): §5 update polimórfico; §3 `draw` só lê estado; §8 dano via
`HitResult`; §11 `aggressiveness`/`health_multiplier`.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any, List, Tuple

import pygame

from ....core.config import config as Config
from ...effects.explosion import ExplosionType
from ....systems import enemy_shield
from .._shared.enemy_hit_mixin import EnemyHitMixin
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
    build_sapper_surface,
)

if TYPE_CHECKING:
    from ....systems.entity_context import EnemyUpdateContext
    from ....systems.hit_result import HitResult


class SapperDrone(EnemyHitMixin):
    CELL: int = 4
    SIZE: int = PIXEL_COLS * CELL  # 52px

    HEALTH: int = 50
    POINTS: int = 220

    PULSE_INTERVAL: float = 8.0      # intervalo entre pulsos de escudo
    PULSE_RADIUS: float = 260.0      # alcance do pulso
    SHIELD_FRACTION: float = 0.25    # escudo = 25% do HP atual do alvo
    PULSE_ANIM_DUR: float = 0.6      # duração da onda visual do pulso

    PACK_RANGE: float = 340.0        # raio para detectar/seguir o grupo
    HOVER_DIST: float = 120.0        # distância que paira do centro do grupo
    MOVE_SPEED: float = 120.0
    DRIFT_SPEED: float = 60.0        # deriva quando sem grupo (avança p/ esquerda)

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

        # Primeiro pulso cedo e dessincronizado entre múltiplos drones.
        self._pulse_timer: float = random.uniform(1.5, self.PULSE_INTERVAL)
        self._pulse_anim: float = -1.0          # <0 inativo; senão tempo da onda

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
        if self._pulse_anim >= 0.0:
            self._pulse_anim += dt
            if self._pulse_anim > self.PULSE_ANIM_DUR:
                self._pulse_anim = -1.0

        cx, cy = self._center()

        self._pulse_timer -= dt
        if self._pulse_timer <= 0.0:
            self._pulse_timer += self.PULSE_INTERVAL
            self._emit_pulse(other_enemies, cx, cy)

        self._seek_pack(dt, cx, cy, other_enemies)

    def _is_ally(self, e: Any) -> bool:
        # Aliado = qualquer inimigo com HP atacável, exceto outro Rebocador e bosses.
        if e is self or isinstance(e, SapperDrone):
            return False
        if getattr(e, "dead", False) or getattr(e, "is_boss", False):
            return False
        return isinstance(getattr(e, "health", None), int)

    def _ally_center(self, e: Any, fx: float, fy: float) -> Tuple[float, float]:
        return (
            getattr(e, "x", fx) + getattr(e, "w", 0) / 2,
            getattr(e, "y", fy) + getattr(e, "h", 0) / 2,
        )

    def _emit_pulse(self, others: List[Any], cx: float, cy: float) -> None:
        """Blinda todos os aliados no raio com 25% do HP atual deles."""
        self._pulse_anim = 0.0
        r2 = self.PULSE_RADIUS * self.PULSE_RADIUS
        granted = False
        for e in others:
            if not self._is_ally(e):
                continue
            ex, ey = self._ally_center(e, cx, cy)
            if (ex - cx) ** 2 + (ey - cy) ** 2 > r2:
                continue
            hp = getattr(e, "health", 0)
            if hp > 0:
                enemy_shield.grant_shield(e, hp * self.SHIELD_FRACTION)
                granted = True
        # Som uma única vez por pulso, só se blindou alguém (padrão de chamada
        # direta a hit_sounds, como o WARNING do CyberTank).
        if granted:
            from ....systems import hit_sounds

            hit_sounds.SHIELD_ACTIVATE()

    def _seek_pack(
        self, dt: float, cx: float, cy: float, others: List[Any]
    ) -> None:
        """Paira junto ao centro do grupo de aliados; sem grupo, deriva."""
        sx = sy = 0.0
        n = 0
        rng2 = self.PACK_RANGE * self.PACK_RANGE
        for e in others:
            if not self._is_ally(e):
                continue
            ex, ey = self._ally_center(e, cx, cy)
            if (ex - cx) ** 2 + (ey - cy) ** 2 <= rng2:
                sx += ex
                sy += ey
                n += 1
        if n == 0:
            self._drift(dt)
            return

        tx, ty = sx / n, sy / n
        dx, dy = tx - cx, ty - cy
        dist = math.hypot(dx, dy) or 1.0
        if dist > self.HOVER_DIST:
            step = min(self.MOVE_SPEED * dt, dist - self.HOVER_DIST)
            self.x += dx / dist * step
            self.y += dy / dist * step
        # Avanço lento p/ acompanhar o scroll e não ficar preso eternamente.
        if self.side_scroll:
            self.x -= self.DRIFT_SPEED * 0.35 * dt

    def _drift(self, dt: float) -> None:
        # Sem grupo: deriva devagar na direção de avanço do bioma.
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
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

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
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

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

        # Onda do pulso (anel expansível) atrás do corpo — feedback do disparo.
        if self._pulse_anim >= 0.0:
            self._draw_pulse_ring(surface, icx, icy)

        base = build_sapper_surface(cell)
        if self.hit_timer > 0.0:
            img = base.copy()
            img.fill((200, 200, 200), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, (int(self.x), int(self.y)))
        else:
            surface.blit(base, (int(self.x), int(self.y)))

        # Núcleo verde pulsante (mais forte logo após emitir o pulso).
        pulse = 0.5 + 0.5 * math.sin(self.pulse * 5.0)
        boost = 0.0
        if self._pulse_anim >= 0.0:
            boost = max(0.0, 1.0 - self._pulse_anim / self.PULSE_ANIM_DUR) * 0.6
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

    def _draw_pulse_ring(self, surface: pygame.Surface, icx: int, icy: int) -> None:
        # Anel transiente: só vive ~PULSE_ANIM_DUR a cada 8s, fora do hot path
        # estável — a alocação da surface por frame durante a onda é aceitável.
        f = self._pulse_anim / self.PULSE_ANIM_DUR  # 0..1
        radius = int(self.PULSE_RADIUS * f)
        if radius < 2:
            return
        alpha = int(140 * (1.0 - f))
        if alpha <= 0:
            return
        size = radius * 2 + 4
        ring = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(
            ring, (*pal.ELECTRIC_BLUE, alpha), (radius + 2, radius + 2), radius, 3
        )
        surface.blit(
            ring,
            (icx - radius - 2, icy - radius - 2),
            special_flags=pygame.BLEND_RGBA_ADD,
        )
