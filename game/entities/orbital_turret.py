"""Torreta Orbital — sentinela "sniper" do bioma STARFIELD.

Estação fixa que entra pelo topo, ancora numa banda alta e dispara em ciclo uma
**rajada de plasma mirada** (3 bolts com leve dispersão) na posição do jogador,
com telegrama de carga. Counterplay: sair da linha de tiro durante a carga.

Contratos (CLAUDE.md): herda `EnemyHitMixin` (§9), update via
`update_in_context` (§5), `draw` sem efeitos colaterais (§3).
"""

import math
import random
from typing import TYPE_CHECKING, List

import pygame

from ..core import colors
from ..core.sound import sound_manager
from .alien_bullet import AlienBullet
from .enemy_hit_mixin import EnemyHitMixin

if TYPE_CHECKING:
    from ..systems.entity_context import EnemyUpdateContext
    from ..systems.hit_result import HitResult


class PlasmaBolt(AlienBullet):
    """Projétil de plasma azul da Torreta Orbital (mais rápido que o tiro alien)."""

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.color_1 = (120, 200, 255)
        self.color_2 = (210, 245, 255)
        self.current_color = self.color_1
        self.min_radius = 7
        self.max_radius = 10
        self.current_radius = 8


class OrbitalTurret(EnemyHitMixin):
    SIZE = 44
    BOLT_SPEED = 320.0
    BURST_COUNT = 3
    BURST_SPREAD = 0.20  # rad entre bolts

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
        self.target_y = float(random.randint(50, 150))
        self.entry_speed = 130.0
        self._entry_done = False
        self.side_scroll = side_scroll

        self.dead = False
        self.health = 60
        self.active = True
        self.hit_timer = 0.0

        self._aggr = max(0.5, aggressiveness_multiplier)
        self.aim_angle = math.pi / 2  # aponta p/ baixo até travar no jogador
        self.shoot_cycle = random.uniform(2.6, 3.6) / self._aggr
        self.shoot_timer = self.shoot_cycle
        self.charge_duration = 0.9

        self.body_rotation = random.uniform(0.0, 360.0)
        self.body_spin = random.uniform(-25.0, 25.0)
        self.float_phase = random.uniform(0.0, math.tau)
        self.anim_time = 0.0

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def _center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    @property
    def charge_ratio(self) -> float:
        if self._entry_done and 0.0 < self.shoot_timer <= self.charge_duration:
            return 1.0 - (self.shoot_timer / self.charge_duration)
        return 0.0

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        emitted = self.update(ctx.sdt, ctx.player_x, ctx.player_y)
        if emitted:
            ctx.new_alien_bullets.extend(emitted)

    def update(
        self, dt: float, player_x: float, player_y: float
    ) -> List[PlasmaBolt]:
        self.anim_time += dt
        self.body_rotation += self.body_spin * dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        if not self._entry_done:
            self.y += self.entry_speed * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self._entry_done = True
            return []

        # Flutuação cosmética suave (acumulador próprio, nunca time.time() — §3).
        self.y = self.target_y + math.sin(self.anim_time * 1.6 + self.float_phase) * 6.0

        # Trava a mira no jogador (mais ágil durante a carga).
        cx, cy = self._center
        target = math.atan2(player_y - cy, player_x - cx)
        track = 6.0 if self.charge_ratio > 0.0 else 2.5
        diff = (target - self.aim_angle + math.pi) % math.tau - math.pi
        self.aim_angle += diff * min(1.0, track * dt)

        bolts: List[PlasmaBolt] = []
        self.shoot_timer -= dt
        if self.shoot_timer <= 0.0 and not self.dead:
            bolts = self._fire_burst()
            self.shoot_cycle = random.uniform(2.6, 3.6) / self._aggr
            self.shoot_timer = self.shoot_cycle
        return bolts

    def _fire_burst(self) -> List[PlasmaBolt]:
        cx, cy = self._center
        muzzle = (
            cx + math.cos(self.aim_angle) * self.w * 0.55,
            cy + math.sin(self.aim_angle) * self.h * 0.55,
        )
        sound_manager.play_shot()
        bolts: List[PlasmaBolt] = []
        start = -(self.BURST_COUNT - 1) / 2.0
        for i in range(self.BURST_COUNT):
            angle = self.aim_angle + (start + i) * self.BURST_SPREAD
            bolt = PlasmaBolt(muzzle[0], muzzle[1])
            bolt.vx = math.cos(angle) * self.BOLT_SPEED
            bolt.vy = math.sin(angle) * self.BOLT_SPEED
            bolts.append(bolt)
        return bolts

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = self._center
        icx, icy = int(cx), int(cy)
        hit = self.hit_timer > 0.0
        cr = self.charge_ratio

        # Barril apontado para a mira (desenhado atrás do corpo).
        barrel_len = self.w * 0.62
        bx = cx + math.cos(self.aim_angle) * barrel_len
        by = cy + math.sin(self.aim_angle) * barrel_len
        barrel_col = (90, 150, 200) if not hit else colors.WHITE
        pygame.draw.line(surface, barrel_col, (icx, icy), (int(bx), int(by)), 7)
        pygame.draw.line(surface, colors.BLACK, (icx, icy), (int(bx), int(by)), 1)

        # Corpo octogonal rotativo.
        radius = self.w * 0.45
        rot = math.radians(self.body_rotation)
        pts = [
            (
                icx + math.cos(rot + math.tau * k / 8) * radius,
                icy + math.sin(rot + math.tau * k / 8) * radius,
            )
            for k in range(8)
        ]
        body_col = colors.WHITE if hit else (70, 92, 120)
        pygame.draw.polygon(surface, body_col, pts)
        pygame.draw.polygon(surface, (150, 190, 230), pts, 2)
        pygame.draw.polygon(surface, colors.BLACK, pts, 1)

        # Núcleo / olho que acende durante a carga.
        core_r = int(self.w * 0.18)
        if cr > 0.0:
            glow = int(120 + 135 * cr)
            core_col = (glow, 220, 255)
            # Glow de telegrama na boca do barril.
            gr = int(4 + 9 * cr)
            pygame.draw.circle(surface, (120, 200, 255), (int(bx), int(by)), gr, 1)
        else:
            core_col = (120, 180, 240)
        pygame.draw.circle(surface, core_col, (icx, icy), core_r)
        pygame.draw.circle(surface, colors.BLACK, (icx, icy), core_r, 1)

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return 200

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead
