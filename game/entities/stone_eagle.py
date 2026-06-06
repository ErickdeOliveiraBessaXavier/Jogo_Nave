"""Águia de Pedra — inimigo "rush" do bioma MOUNTAINS.

Planador de pedra que circula no alto, **telegrafa** (asas erguidas) e então
**mergulha rápido** na posição travada do jogador, subindo de volta em seguida.
Dano por colisão. Counterplay: ler o telegrama e desviar do eixo do mergulho.

Contratos (CLAUDE.md): herda `EnemyHitMixin` (§9), update via
`update_in_context` (§5), `draw` sem efeitos colaterais (§3).
"""

import math
import random
from typing import TYPE_CHECKING

import pygame

from ..core import colors
from ..core.config import config as Config
from ..core.sound import sound_manager
from .enemy_hit_mixin import EnemyHitMixin

if TYPE_CHECKING:
    from ..systems.entity_context import EnemyUpdateContext
    from ..systems.hit_result import HitResult


class StoneEagle(EnemyHitMixin):
    W = 52
    H = 36
    CIRCLE_SPEED = 170.0
    DIVE_SPEED = 600.0
    CLIMB_SPEED = 320.0
    TELEGRAPH_TIME = 0.55
    DIVE_TIME = 0.7

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = False,
    ):
        self.w = self.W
        self.h = self.H
        self.x = x
        self.y = y
        self.band_y = float(random.randint(50, 120))
        self.side_scroll = side_scroll

        self.dead = False
        self.health = 45
        self.active = True
        self.hit_timer = 0.0

        self._aggr = max(0.5, aggressiveness_multiplier)
        self.state = "enter"
        self.circle_timer = random.uniform(1.4, 2.4) / self._aggr
        self.telegraph_timer = 0.0
        self.dive_timer = 0.0
        self.dive_vx = 0.0
        self.dive_vy = 0.0
        self._lock = (0.0, 0.0)  # posição do jogador travada no telegrama
        self.facing = math.pi / 2
        self.anim_time = 0.0
        self.wing_phase = random.uniform(0.0, math.tau)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def _center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    @property
    def _wing_spread(self) -> float:
        """1.0 = asas abertas (circular/subir), 0.2 = recolhidas (mergulho)."""
        if self.state == "dive":
            return 0.2
        if self.state == "telegraph":
            return 1.0 + 0.3 * math.sin(self.anim_time * 30.0)  # vibra no telegrama
        return 1.0

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt, ctx.player_x, ctx.player_y)

    def update(self, dt: float, player_x: float, player_y: float) -> None:
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        if self.state == "enter":
            self.y += self.CLIMB_SPEED * dt
            if self.y >= self.band_y:
                self.y = self.band_y
                self.state = "circle"
            return

        if self.state == "circle":
            self.facing = math.pi / 2
            cx, _ = self._center
            dx = player_x - cx
            if abs(dx) > 4.0:
                self.x += math.copysign(self.CIRCLE_SPEED * dt, dx)
            self.x = max(0.0, min(Config.SCREEN_WIDTH - self.w, self.x))
            self.y = self.band_y + math.sin(self.anim_time * 2.2 + self.wing_phase) * 8.0
            self.circle_timer -= dt
            if self.circle_timer <= 0.0:
                self.state = "telegraph"
                self.telegraph_timer = self.TELEGRAPH_TIME
                self._lock = (player_x, player_y)
            return

        if self.state == "telegraph":
            self.telegraph_timer -= dt
            if self.telegraph_timer <= 0.0:
                cx, cy = self._center
                tx, ty = self._lock
                angle = math.atan2(ty - cy, tx - cx)
                self.facing = angle
                self.dive_vx = math.cos(angle) * self.DIVE_SPEED
                self.dive_vy = math.sin(angle) * self.DIVE_SPEED
                self.dive_timer = self.DIVE_TIME
                self.state = "dive"
                sound_manager.play_shot()
            return

        if self.state == "dive":
            self.x += self.dive_vx * dt
            self.y += self.dive_vy * dt
            self.dive_timer -= dt
            if self.x < 0 or self.x > Config.SCREEN_WIDTH - self.w:
                self.dive_vx = -self.dive_vx
                self.x = max(0.0, min(Config.SCREEN_WIDTH - self.w, self.x))
            if self.dive_timer <= 0.0 or self.y > Config.SCREEN_HEIGHT - self.h:
                self.y = min(self.y, Config.SCREEN_HEIGHT - self.h)
                self.state = "climb"
            return

        # state == "climb"
        self.facing = -math.pi / 2
        self.y -= self.CLIMB_SPEED * dt
        if self.y <= self.band_y:
            self.y = self.band_y
            self.circle_timer = random.uniform(1.4, 2.4) / self._aggr
            self.state = "circle"

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = self._center
        hit = self.hit_timer > 0.0
        ca, sa = math.cos(self.facing), math.sin(self.facing)

        def place(px: float, py: float) -> tuple[int, int]:
            return int(cx + px * ca - py * sa), int(cy + px * sa + py * ca)

        flap = math.sin(self.anim_time * 9.0 + self.wing_phase) * 5.0
        spread = self._wing_spread
        wy = self.h * 0.5 * spread + flap

        stone = colors.WHITE if hit else (96, 88, 78)
        stone_hi = (150, 140, 126)

        # Asas (dois triângulos saindo do corpo).
        left = [place(-4, 0), place(-self.w * 0.18, -wy), place(self.w * 0.12, -6)]
        right = [place(-4, 0), place(-self.w * 0.18, wy), place(self.w * 0.12, 6)]
        pygame.draw.polygon(surface, stone, left)
        pygame.draw.polygon(surface, stone, right)
        pygame.draw.polygon(surface, colors.BLACK, left, 1)
        pygame.draw.polygon(surface, colors.BLACK, right, 1)

        # Corpo + cabeça (apontando p/ facing).
        body = [place(self.w * 0.5, 0), place(-self.w * 0.18, -6), place(-self.w * 0.18, 6)]
        pygame.draw.polygon(surface, stone_hi, body)
        pygame.draw.polygon(surface, colors.BLACK, body, 1)

        # Olho/bico que acende no telegrama.
        eye = (255, 120, 60) if self.state == "telegraph" else colors.YELLOW
        ex, ey = place(self.w * 0.42, 0)
        pygame.draw.circle(surface, eye, (ex, ey), 3)

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
