"""Drone Reparador — inimigo "support" do bioma STARFIELD.

Caça o aliado ferido mais próximo, mantém distância do jogador e emite em ciclo
um **pulso de reparo** que cura inimigos próximos. Counterplay: priorizá-lo —
sozinho é frágil, mas prolonga a vida do resto do encontro.

Decisão de design (CLAUDE.md §1): o drone lê/escreve apenas o `health` **público**
dos aliados (via `ctx.other_enemies`) e mantém **no próprio drone** o teto de cura
(`_max_seen[id(ally)]` = maior health já observado). Não toca em atributo privado
de terceiros.
"""

import math
import random
from typing import TYPE_CHECKING, Any, List

import pygame

from ..core import colors
from ..core.config import config as Config
from .enemy_hit_mixin import EnemyHitMixin

if TYPE_CHECKING:
    from ..systems.entity_context import EnemyUpdateContext
    from ..systems.hit_result import HitResult


class RepairDrone(EnemyHitMixin):
    SIZE = 30
    SPEED = 200.0
    FLEE_RADIUS = 220.0
    HEAL_RADIUS = 150.0
    HEAL_AMOUNT = 6
    HEAL_INTERVAL = 1.6
    KEEP_DISTANCE = 70.0

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = False,
    ):
        self.w = self.SIZE
        self.h = self.SIZE
        self.x = x
        self.y = y
        self.side_scroll = side_scroll

        self.dead = False
        self.health = 50
        self.active = True
        self.hit_timer = 0.0

        self._aggr = max(0.5, aggressiveness_multiplier)
        self.heal_timer = self.HEAL_INTERVAL
        self._max_seen: dict[int, int] = {}
        self._heal_ring = 0.0  # 0..1 anim do pulso (decai)
        self.anim_time = 0.0
        self.bob_phase = random.uniform(0.0, math.tau)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def _center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt, ctx.player_x, ctx.player_y, ctx.other_enemies)

    def update(
        self,
        dt: float,
        player_x: float,
        player_y: float,
        other_enemies: List[Any],
    ) -> None:
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)
        if self._heal_ring > 0.0:
            self._heal_ring = max(0.0, self._heal_ring - dt * 1.4)

        cx, cy = self._center

        # Observa health dos aliados e registra o teto de cura.
        wounded = self._observe_and_find_wounded(other_enemies, cx, cy)

        # Movimento: foge do jogador se perto; senão acompanha o aliado ferido.
        pdx, pdy = cx - player_x, cy - player_y
        pdist = math.hypot(pdx, pdy)
        if pdist < self.FLEE_RADIUS and pdist > 1.0:
            self.x += (pdx / pdist) * self.SPEED * dt
            self.y += (pdy / pdist) * self.SPEED * dt
        elif wounded is not None:
            wx, wy, _ = wounded
            dx, dy = wx - cx, wy - cy
            dist = math.hypot(dx, dy)
            if dist > self.KEEP_DISTANCE:
                self.x += (dx / dist) * self.SPEED * dt
                self.y += (dy / dist) * self.SPEED * dt
        else:
            # Sem ferido: deriva suave numa banda alta.
            self.y += (90.0 - cy) * 0.4 * dt
            self.x += math.sin(self.anim_time * 0.8 + self.bob_phase) * 30.0 * dt

        self.x = max(0.0, min(Config.SCREEN_WIDTH - self.w, self.x))
        self.y = max(0.0, min(Config.SCREEN_HEIGHT * 0.7, self.y))

        # Pulso de reparo periódico.
        self.heal_timer -= dt
        if self.heal_timer <= 0.0:
            self.heal_timer = self.HEAL_INTERVAL
            self._emit_repair_pulse(other_enemies)

    def _observe_and_find_wounded(
        self, others: List[Any], cx: float, cy: float
    ) -> tuple[float, float, Any] | None:
        nearest: tuple[float, float, Any] | None = None
        best_dist = float("inf")
        seen_now: set[int] = set()
        for ally in others:
            if ally is self or getattr(ally, "dead", False):
                continue
            hp = getattr(ally, "health", None)
            if hp is None:
                continue
            aid = id(ally)
            seen_now.add(aid)
            cap = self._max_seen.get(aid, 0)
            if hp > cap:
                self._max_seen[aid] = hp
                cap = hp
            if hp < cap:  # ferido
                acx, acy = self._ally_center(ally)
                d = (acx - cx) ** 2 + (acy - cy) ** 2
                if d < best_dist:
                    best_dist = d
                    nearest = (acx, acy, ally)
        # Poda ids de aliados que já saíram de cena (evita crescer sem limite).
        if len(self._max_seen) > len(seen_now):
            for stale in [k for k in self._max_seen if k not in seen_now]:
                del self._max_seen[stale]
        return nearest

    def _emit_repair_pulse(self, others: List[Any]) -> None:
        cx, cy = self._center
        healed_any = False
        for ally in others:
            if ally is self or getattr(ally, "dead", False):
                continue
            hp = getattr(ally, "health", None)
            if hp is None:
                continue
            cap = self._max_seen.get(id(ally), hp)
            if hp >= cap:
                continue
            acx, acy = self._ally_center(ally)
            if (acx - cx) ** 2 + (acy - cy) ** 2 <= self.HEAL_RADIUS**2:
                ally.health = min(cap, hp + self.HEAL_AMOUNT)
                healed_any = True
        if healed_any:
            self._heal_ring = 1.0

    @staticmethod
    def _ally_center(ally: Any) -> tuple[float, float]:
        r = getattr(ally, "rect", None)
        if r is not None:
            return r.centerx, r.centery
        return getattr(ally, "x", 0.0), getattr(ally, "y", 0.0)

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = self._center
        icx, icy = int(cx), int(cy)
        hit = self.hit_timer > 0.0

        # Anel de reparo expandindo.
        if self._heal_ring > 0.0:
            r = int(self.HEAL_RADIUS * (1.0 - self._heal_ring))
            if r > 2:
                pygame.draw.circle(surface, (120, 255, 170), (icx, icy), r, 2)

        body_col = colors.WHITE if hit else (60, 170, 110)
        pygame.draw.circle(surface, body_col, (icx, icy), int(self.w * 0.5))
        pygame.draw.circle(surface, (180, 255, 210), (icx, icy), int(self.w * 0.5), 2)
        pygame.draw.circle(surface, colors.BLACK, (icx, icy), int(self.w * 0.5), 1)

        # Cruz de reparo.
        arm = int(self.w * 0.28)
        cross = (235, 255, 245)
        pygame.draw.rect(surface, cross, (icx - 2, icy - arm, 4, arm * 2))
        pygame.draw.rect(surface, cross, (icx - arm, icy - 2, arm * 2, 4))

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return 220

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead
