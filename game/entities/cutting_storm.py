"""Tempestade Cortante — inimigo "area_denial" do bioma MOUNTAINS.

Nuvem de detritos cortantes que deriva pela tela com leve perseguição ao jogador
e causa **dano de área contínuo** enquanto a nave estiver dentro dela. O dano
passa por `ctx.new_area_blasts` (mesmo roteador do raio do Cyber-Captor / morteiro
— CLAUDE.md §8), drenado pelo `EntityManager` e aplicado pela cena com os i-frames
da nave. Counterplay: sair da nuvem; ela é lenta e destrutível.

Contratos (CLAUDE.md): herda `EnemyHitMixin` (§9), update via
`update_in_context` (§5), `draw` sem efeitos colaterais (§3).
"""

import math
import random
from typing import TYPE_CHECKING

import pygame

from ..core import colors
from ..core.config import config as Config
from .enemy_hit_mixin import EnemyHitMixin

if TYPE_CHECKING:
    from ..systems.entity_context import EnemyUpdateContext
    from ..systems.hit_result import HitResult


class CuttingStorm(EnemyHitMixin):
    RADIUS = 46
    DAMAGE_RADIUS = 44.0
    DRIFT_SPEED = 70.0
    HOMING = 0.6  # fração da velocidade que mira no jogador

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = False,
    ):
        self.w = self.RADIUS * 2
        self.h = self.RADIUS * 2
        self.x = x
        self.y = y
        self.side_scroll = side_scroll

        self.dead = False
        self.health = 70
        self.active = True
        self.hit_timer = 0.0

        self._aggr = max(0.5, aggressiveness_multiplier)
        angle = random.uniform(0.0, math.tau)
        self.vx = math.cos(angle) * self.DRIFT_SPEED
        self.vy = abs(math.sin(angle)) * self.DRIFT_SPEED * 0.5 + 20.0
        self.anim_time = 0.0
        self._entered = False
        # Lâminas de detrito (ângulo, raio, velocidade) para o visual giratório.
        self._blades = [
            (
                random.uniform(0.0, math.tau),
                random.uniform(0.35, 0.95),
                random.uniform(-2.2, 2.2),
            )
            for _ in range(7)
        ]

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def _center(self) -> tuple[float, float]:
        return self.x + self.RADIUS, self.y + self.RADIUS

    def collision_circle(self) -> tuple[float, float, float]:
        cx, cy = self._center
        return cx, cy, float(self.RADIUS)

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        blast = self.update(ctx.sdt, ctx.player_x, ctx.player_y)
        if blast is not None:
            ctx.new_area_blasts.append(blast)

    def update(
        self, dt: float, player_x: float, player_y: float
    ) -> tuple[float, float, float] | None:
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        cx, cy = self._center
        # Leve homing: enviesa a deriva na direção do jogador.
        dx, dy = player_x - cx, player_y - cy
        dist = math.hypot(dx, dy)
        if dist > 1.0:
            hx, hy = dx / dist, dy / dist
            self.vx += (hx * self.DRIFT_SPEED - self.vx) * self.HOMING * dt
            self.vy += (hy * self.DRIFT_SPEED - self.vy) * self.HOMING * dt

        self.x += self.vx * dt
        self.y += self.vy * dt

        # Mantém na arena (quica nas bordas). Antes de entrar, deixa descer do topo.
        if self.y > 0:
            self._entered = True
        if self._entered:
            if self.x < 0:
                self.x = 0
                self.vx = abs(self.vx)
            elif self.x > Config.SCREEN_WIDTH - self.w:
                self.x = Config.SCREEN_WIDTH - self.w
                self.vx = -abs(self.vx)
            if self.y < 0:
                self.y = 0
                self.vy = abs(self.vy)
            elif self.y > Config.SCREEN_HEIGHT - self.h:
                self.y = Config.SCREEN_HEIGHT - self.h
                self.vy = -abs(self.vy)

        if not self._entered:
            return None
        cx, cy = self._center
        return (cx, cy, self.DAMAGE_RADIUS)

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = self._center
        icx, icy = int(cx), int(cy)
        hit = self.hit_timer > 0.0

        # Halo da nuvem.
        halo = colors.WHITE if hit else (120, 110, 95)
        pygame.draw.circle(surface, halo, (icx, icy), self.RADIUS, 2)

        # Lâminas/detritos girando.
        for base_ang, rad_frac, spin in self._blades:
            ang = base_ang + self.anim_time * spin
            r = self.RADIUS * rad_frac
            px = icx + math.cos(ang) * r
            py = icy + math.sin(ang) * r
            tang = ang + math.pi / 2
            tip = (px + math.cos(tang) * 9, py + math.sin(tang) * 9)
            col = colors.WHITE if hit else (200, 200, 210)
            pygame.draw.line(surface, col, (int(px), int(py)), (int(tip[0]), int(tip[1])), 2)
            pygame.draw.circle(surface, (150, 140, 120), (int(px), int(py)), 3)

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return 250

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        # A nuvem persiste no contato; o dano contínuo já vem do area_blast.
        return HitResult(sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool:
        return self.dead
