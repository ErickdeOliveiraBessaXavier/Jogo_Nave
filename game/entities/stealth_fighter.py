"""Caça Furtivo — inimigo "rush" do bioma STARFIELD.

Alterna **cloak** (quase invisível, reposiciona acima do jogador) e **investida**
(decloak, mergulho diagonal rápido na posição travada do jogador). Dano por
colisão. A janela de vulnerabilidade é a investida — visível e previsível; o
cloak é só camuflagem visual (continua destrutível, para ser justo).

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


class StealthFighter(EnemyHitMixin):
    W = 40
    H = 30
    HUNT_SPEED = 240.0
    DASH_SPEED = 560.0
    CLOAK_ALPHA = 70
    DASH_DURATION = 0.55

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
        self.side_scroll = side_scroll

        self.dead = False
        self.health = 40
        self.active = True
        self.hit_timer = 0.0

        self._aggr = max(0.5, aggressiveness_multiplier)
        self.state = "enter"
        self.target_y = float(random.randint(70, 150))
        self.hunt_timer = random.uniform(1.0, 1.8) / self._aggr
        self.dash_timer = 0.0
        self.dash_vx = 0.0
        self.dash_vy = 0.0
        self.facing = math.pi / 2  # aponta p/ baixo
        self.alpha = float(self.CLOAK_ALPHA)
        self._surface = pygame.Surface((self.w + 8, self.h + 8), pygame.SRCALPHA)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def _center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        self.update(ctx.sdt, ctx.player_x, ctx.player_y)

    def update(self, dt: float, player_x: float, player_y: float) -> None:
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        if self.state == "enter":
            self.y += self.HUNT_SPEED * dt
            self.alpha += (self.CLOAK_ALPHA - self.alpha) * min(1.0, 4.0 * dt)
            if self.y >= self.target_y:
                self.state = "hunt"
            return

        if self.state == "hunt":
            # Reposiciona acima do jogador, camuflado.
            self.alpha += (self.CLOAK_ALPHA - self.alpha) * min(1.0, 4.0 * dt)
            cx, cy = self._center
            hover_x = player_x
            hover_y = max(60.0, player_y - 170.0)
            dx, dy = hover_x - cx, hover_y - cy
            dist = math.hypot(dx, dy)
            if dist > 1.0:
                self.facing = math.atan2(dy, dx)
                step = min(dist, self.HUNT_SPEED * dt)
                self.x += (dx / dist) * step
                self.y += (dy / dist) * step
            self.hunt_timer -= dt
            if self.hunt_timer <= 0.0:
                self._begin_dash(player_x, player_y)
            return

        # state == "dash"
        self.alpha += (255.0 - self.alpha) * min(1.0, 12.0 * dt)
        self.x += self.dash_vx * dt
        self.y += self.dash_vy * dt
        self.dash_timer -= dt
        cx, _ = self._center
        # Quica nas bordas laterais para não sair voando da arena.
        if cx < 0 or cx > Config.SCREEN_WIDTH:
            self.dash_vx = -self.dash_vx
        if self.dash_timer <= 0.0:
            if self.y > Config.SCREEN_HEIGHT + 40 or self.y < -40:
                # Saiu de cena: re-entra pelo topo, camuflado.
                self.x = random.uniform(40.0, Config.SCREEN_WIDTH - 40.0 - self.w)
                self.y = -self.h
                self.target_y = float(random.randint(70, 150))
                self.alpha = float(self.CLOAK_ALPHA)
                self.state = "enter"
            else:
                self.hunt_timer = random.uniform(1.0, 1.8) / self._aggr
                self.state = "hunt"

    def _begin_dash(self, player_x: float, player_y: float) -> None:
        cx, cy = self._center
        angle = math.atan2(player_y - cy, player_x - cx)
        self.facing = angle
        self.dash_vx = math.cos(angle) * self.DASH_SPEED
        self.dash_vy = math.sin(angle) * self.DASH_SPEED
        self.dash_timer = self.DASH_DURATION
        self.state = "dash"

    def draw(self, surface: pygame.Surface) -> None:
        s = self._surface
        s.fill((0, 0, 0, 0))
        ox, oy = (self.w + 8) / 2, (self.h + 8) / 2
        nose = self.w * 0.5
        wing = self.h * 0.5
        hit = self.hit_timer > 0.0
        # Dardo: nariz à frente, asas atrás, orientado por self.facing.
        local = [(nose, 0.0), (-wing, -wing), (-wing * 0.4, 0.0), (-wing, wing)]
        ca, sa = math.cos(self.facing), math.sin(self.facing)
        pts = [(ox + px * ca - py * sa, oy + px * sa + py * ca) for px, py in local]
        body = colors.WHITE if hit else (150, 60, 180)
        pygame.draw.polygon(s, body, pts)
        pygame.draw.polygon(s, (220, 160, 255), pts, 1)
        # Motor brilhante na traseira.
        tail = (ox - wing * ca, oy - wing * sa)
        pygame.draw.circle(s, (255, 120, 240), (int(tail[0]), int(tail[1])), 3)

        s.set_alpha(int(max(0, min(255, self.alpha))))
        surface.blit(s, (int(self.x - 4), int(self.y - 4)))

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return 180

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead
