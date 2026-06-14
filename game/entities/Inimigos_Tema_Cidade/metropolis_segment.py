"""Segmento do Metropolis Overlord — fase de SEGMENTAÇÃO (final).

Ao chegar no núcleo, o grande triângulo se **divide em três triângulos menores**,
cada um contendo um dos núcleos de plasma. Os três orbitam um **ponto invisível**
(centro da arena), 120° apart, cada um com um **padrão de ataque diferente**:

  "cyan"    → feixes verticais (VerticalLaser) que varrem colunas.
  "magenta" → salvas de mísseis seguidores (MicroMissile).
  "amber"   → pulsos EMP + leque de tiros neon (EMPPulse + NeonBurstShot).

Cada segmento é destrutível por conta própria (vive em `em.enemies`); o boss-
coordenador morre quando os três caem. Projéteis roteados via `ctx.new_enemies`
(reuso dos projéteis custom — zero plumbing nova). `draw` sem efeitos colaterais (§3).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, List

import pygame

from ...core.config import config as Config
from ..enemy_hit_mixin import EnemyHitMixin
from . import metropolis_overlord_pixel_map as pmap
from .metropolis_projectiles import (
    EMPPulse,
    MicroMissile,
    NeonBurstShot,
    VerticalLaser,
)

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult


class MetropolisSegment(EnemyHitMixin):
    """Triângulo menor com um núcleo, orbitando o ponto invisível e atacando."""

    is_boss: bool = False
    POINTS = 400
    ORBIT_SPEED = 0.6  # rad/s ao redor do ponto invisível
    ENTRY_TIME = 0.6   # ease da posição de split até o anel de órbita
    COLLISION_RADIUS = 40.0

    _explosion_size_killed = 60
    _explosion_size_hit = 12

    # papel → intervalo de disparo (s)
    _FIRE_INTERVAL = {"laser": 2.0, "missile": 1.7, "emp": 2.4}

    def __init__(
        self,
        theme: str,
        role: str,
        center: tuple[float, float],
        base_angle: float,
        orbit_radius: float,
        start_pos: tuple[float, float],
        health: int,
        aggressiveness_multiplier: float = 1.0,
    ) -> None:
        self.theme = theme
        self.role = role
        self.center = center
        self.base_angle = base_angle
        self.orbit_radius = orbit_radius
        self._aggr = max(0.5, aggressiveness_multiplier)

        self.health = max(1, health)
        self.max_health = self.health
        self.dead = False
        self.hit_timer = 0.0
        self.anim_time = 0.0
        self._phase = base_angle  # fase de plasma única por segmento

        self._orbit_angle = base_angle
        self._entry_t = self.ENTRY_TIME
        self._start_x, self._start_y = start_pos
        self.x, self.y = start_pos

        self._fire_timer = self._FIRE_INTERVAL.get(role, 2.0) / self._aggr
        self._rect = pygame.Rect(0, 0, int(self.COLLISION_RADIUS * 2), int(self.COLLISION_RADIUS * 2))
        self._sync_rect()

    # ── Geometria / colisão ───────────────────────────────────────────────
    def _sync_rect(self) -> None:
        self._rect.center = (int(self.x), int(self.y))

    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    @property
    def causes_damage(self) -> bool:
        return True

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x, self.y, self.COLLISION_RADIUS

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        return HitResult(sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool:
        return self.dead

    # ── Update ────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        if dt <= 0.0:
            return
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        # Órbita ao redor do ponto invisível.
        self._orbit_angle += self.ORBIT_SPEED * dt
        ox = self.center[0] + math.cos(self._orbit_angle) * self.orbit_radius
        oy = self.center[1] + math.sin(self._orbit_angle) * self.orbit_radius
        if self._entry_t > 0.0:
            # Ease da posição de split (onde o núcleo estava) até o anel.
            self._entry_t = max(0.0, self._entry_t - dt)
            k = 1.0 - (self._entry_t / self.ENTRY_TIME)
            self.x = self._start_x + (ox - self._start_x) * k
            self.y = self._start_y + (oy - self._start_y) * k
        else:
            self.x, self.y = ox, oy
        self._sync_rect()

        self._fire_timer -= dt
        if self._fire_timer <= 0.0:
            self._fire_timer = self._FIRE_INTERVAL.get(self.role, 2.0) / self._aggr
            ctx.new_enemies.extend(self._fire(ctx.player_x, ctx.player_y))

    def _fire(self, px: float, py: float) -> List[object]:
        if self.role == "laser":
            col = max(40.0, min(Config.SCREEN_WIDTH - 40.0, px))
            return [VerticalLaser(col), NeonBurstShot(self.x, self.y, px, py)]
        if self.role == "missile":
            return [
                MicroMissile(self.x, self.y, px, py),
                MicroMissile(self.x, self.y, px, py),
            ]
        if self.role == "emp":
            shots: List[object] = [EMPPulse(self.x, self.y)]
            for k in (-1, 0, 1):
                shots.append(NeonBurstShot(self.x, self.y, px + k * 70, py))
            return shots
        return []

    # ── Render (§3) ───────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x), int(self.y)
        # Triângulo pequeno (ápice no topo): frame escuro + contorno neon.
        hw, up, dn = 46, 48, 32
        pts = [(cx, cy - up), (cx - hw, cy + dn), (cx + hw, cy + dn)]
        edge = pmap.COLORS["E"] if self.hit_timer <= 0.0 else (255, 255, 255)
        pygame.draw.polygon(surface, pmap.COLORS["G"], pts)
        pygame.draw.polygon(surface, edge, pts, 3)

        # Núcleo de plasma (foco), centralizado no triângulo.
        intensity = 1.05 + 0.15 * (0.5 + 0.5 * math.sin(self.anim_time * 4.0))
        pmap.draw_plasma_sphere(surface, cx, cy, 26.0, self.theme, self._phase, intensity, self.anim_time)

        # Barra de vida do segmento.
        bw = 72
        bx = cx - bw // 2
        by = max(2, min(Config.SCREEN_HEIGHT - 7, cy - up - 12))
        pygame.draw.rect(surface, (30, 30, 30), (bx, by, bw, 5))
        frac = max(0.0, self.health / self.max_health)
        pygame.draw.rect(surface, pmap.COLORS["E"], (bx, by, int(bw * frac), 5))
