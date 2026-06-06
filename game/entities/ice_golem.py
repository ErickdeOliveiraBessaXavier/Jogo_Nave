"""Golem de Gelo — inimigo "tank" do bioma MOUNTAINS.

Massa lenta de muito HP que entra, persegue o jogador devagar e em ciclo executa
um **slam**: na batida cria uma `IcePoisonZone` (campo de slow) sob si, via o
buffer `ctx.new_ice_zones` (drenado pelo `EntityManager` — CLAUDE.md §2/§5). O
counterplay é posicional: sair das zonas e focar fogo no colosso.

Contratos (CLAUDE.md): herda `EnemyHitMixin` (§9), update via
`update_in_context` (§5), `draw` sem efeitos colaterais (§3). A emissão de zona
passa pelo contexto — o golem não toca no `EntityManager` por dentro.
"""

import math
import random
from typing import TYPE_CHECKING, List

import pygame

from ..core import colors
from ..core.config import config as Config
from ..core.sound import sound_manager
from .enemy_hit_mixin import EnemyHitMixin

if TYPE_CHECKING:
    from ..systems.entity_context import EnemyUpdateContext
    from ..systems.hit_result import HitResult


# Tupla emitida em ctx.new_ice_zones: (x, y, raio, duração).
IceZoneRequest = tuple[float, float, int, float]


class IceGolem(EnemyHitMixin):
    W = 72
    H = 84
    MOVE_SPEED = 55.0
    SLAM_CYCLE = 4.2
    WINDUP = 0.8
    ZONE_RADIUS = 78
    ZONE_DURATION = 4.5
    _explosion_size_killed = 55

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
        self.target_y = float(random.randint(40, 110))
        self.entry_speed = 90.0
        self._entry_done = False
        self.side_scroll = side_scroll

        self.dead = False
        self.health = 150
        self.active = True
        self.hit_timer = 0.0

        self._aggr = max(0.5, aggressiveness_multiplier)
        self.slam_timer = self.SLAM_CYCLE
        self.slamming = False  # em windup
        self.slam_progress = 0.0  # 0..1 durante o windup
        self.anim_time = 0.0
        self.bob_phase = random.uniform(0.0, math.tau)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def _center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        zones = self.update(ctx.sdt, ctx.player_x, ctx.player_y)
        if zones:
            ctx.new_ice_zones.extend(zones)

    def update(
        self, dt: float, player_x: float, player_y: float
    ) -> List[IceZoneRequest]:
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        if not self._entry_done:
            self.y += self.entry_speed * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self._entry_done = True
            return []

        # Flutuação cosmética e perseguição horizontal lenta.
        bob = math.sin(self.anim_time * 1.2 + self.bob_phase) * 4.0
        self.y = self.target_y + bob
        cx, _ = self._center
        if not self.slamming:
            dx = player_x - cx
            if abs(dx) > 4.0:
                self.x += math.copysign(self.MOVE_SPEED * dt, dx)
            self.x = max(0.0, min(Config.SCREEN_WIDTH - self.w, self.x))

        zones: List[IceZoneRequest] = []
        if self.slamming:
            self.slam_progress += dt / self.WINDUP
            if self.slam_progress >= 1.0:
                self.slamming = False
                self.slam_progress = 0.0
                zones.append(self._slam_impact())
        else:
            self.slam_timer -= dt
            if self.slam_timer <= 0.0:
                self.slam_timer = self.SLAM_CYCLE / self._aggr
                self.slamming = True
                self.slam_progress = 0.0
        return zones

    def _slam_impact(self) -> IceZoneRequest:
        cx = self.x + self.w / 2
        base_y = self.y + self.h * 0.92
        sound_manager.play_shot()
        return (cx, base_y, self.ZONE_RADIUS, self.ZONE_DURATION)

    def draw(self, surface: pygame.Surface) -> None:
        hit = self.hit_timer > 0.0
        # "Agachamento" durante o windup do slam (telegrama).
        squash = math.sin(self.slam_progress * math.pi) * 8.0 if self.slamming else 0.0
        bx = int(self.x)
        by = int(self.y + squash)
        bw = self.w
        bh = int(self.h - squash)

        ice = colors.WHITE if hit else (130, 180, 220)
        ice_dark = (80, 120, 165)
        edge = (200, 235, 255)

        # Corpo (bloco de gelo) com ombros largos.
        body = pygame.Rect(bx + 6, by + 14, bw - 12, bh - 14)
        pygame.draw.rect(surface, ice, body, border_radius=8)
        pygame.draw.rect(surface, edge, body, 2, border_radius=8)
        pygame.draw.rect(surface, colors.BLACK, body, 1, border_radius=8)

        # Cabeça/núcleo gélido que brilha no windup.
        core_glow = 0.4 + 0.6 * (self.slam_progress if self.slamming else 0.0)
        head_cx = bx + bw // 2
        head_cy = by + 16
        pygame.draw.circle(surface, ice_dark, (head_cx, head_cy), 14)
        pygame.draw.circle(
            surface,
            (int(150 + 90 * core_glow), int(220 * core_glow + 30), 255),
            (head_cx, head_cy),
            8,
        )
        pygame.draw.circle(surface, colors.BLACK, (head_cx, head_cy), 14, 1)

        # Cristais nos ombros.
        for sx in (bx + 12, bx + bw - 12):
            pygame.draw.polygon(
                surface,
                edge,
                [(sx, by + 18), (sx - 6, by + 30), (sx + 6, by + 30)],
            )

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return 350

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        # Colosso: não morre no contato, mas pune a nave (dano padrão de contato).
        return HitResult(sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool:
        return self.dead
