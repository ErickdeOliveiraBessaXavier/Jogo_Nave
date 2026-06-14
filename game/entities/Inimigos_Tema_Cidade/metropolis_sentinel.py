"""Sentinela Orbital do Metropolis Overlord (Fase 1, tema CITY).

Quatro esferas de energia que percorrem as laterais da tela (perímetro), criando
um escudo dinâmico e forçando o jogador a se mover. Enquanto qualquer uma vive,
o corpo do Overlord é invulnerável; destruir as quatro abre a Fase 2.

Cada sentinela tem um papel com projétil custom dedicado:
  "neon"    → rajadas retas rápidas.
  "missile" → mísseis seguidores.
  "laser"   → feixes verticais.
  "emp"     → pulsos EMP em anel.

A sentinela percorre as bordas (Top -> Right -> Bottom -> Left) em loop.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List

import pygame

from ...core.config import config as Config
from ..enemy_hit_mixin import EnemyHitMixin
from .metropolis_projectiles import (
    EMPPulse,
    MicroMissile,
    NeonBurstShot,
    VerticalLaser,
)

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult

_NEON_MAGENTA = (255, 70, 200)
_NEON_BLUE = (90, 200, 255)
_NEON_WHITE = (255, 255, 255)
_NEON_AMBER = (255, 190, 80)

# Inset do trajeto em relação à borda real da tela. ~RADIUS para a esfera ficar
# ENCOSTADA na borda (ancorada ao perímetro) e ainda 100% visível/alcançável.
# Aplica-se igualmente a topo, base e laterais — o trajeto é o perímetro inteiro.
_EDGE_INSET = 28.0


class MetropolisSentinel(EnemyHitMixin):
    """Esfera de energia que patrulha o perímetro da tela e ataca."""

    is_boss: bool = False
    RADIUS = 22.0
    HEALTH = 100
    POINTS = 250
    BASE_SPEED = 0.12  # t por segundo (uma volta a cada ~8s)

    _ROLE_FIRE_INTERVAL = {
        "neon": 0.5,
        "missile": 1.8,
        "laser": 2.5,
        "emp": 3.0,
    }
    _ROLE_COLOR = {
        "neon": _NEON_MAGENTA,
        "missile": _NEON_AMBER,
        "laser": _NEON_BLUE,
        "emp": (180, 120, 255),
    }

    def __init__(
        self,
        role: str,
        start_t: float = 0.0,
        aggressiveness_multiplier: float = 1.0,
        activation_delay: float = 0.0,
    ) -> None:
        self.role = role
        self._t = start_t % 1.0
        self._aggr = max(0.5, aggressiveness_multiplier)
        self.health = self.HEALTH
        self.dead = False
        self.hit_timer = 0.0
        self.anim_time = 0.0

        self._activation_timer = activation_delay
        self._fire_timer = self._ROLE_FIRE_INTERVAL.get(role, 2.0) / self._aggr

        self.x, self.y = self._calculate_pos(self._t)
        self._rect = pygame.Rect(0, 0, int(self.RADIUS * 2), int(self.RADIUS * 2))
        self._sync_rect()

    def _calculate_pos(self, t: float) -> tuple[float, float]:
        """(x, y) ao longo do PERÍMETRO da arena, parametrizado por comprimento.

        A esfera desliza ancorada às bordas (topo → direita → base → esquerda) em
        loop contínuo, nunca cruzando o centro. Como caminhamos por distância de
        arco (e não ¼ de tempo por lado), a velocidade é UNIFORME mesmo com topo/
        base mais longos que as laterais — deslize suave de conduíte.
        """
        w, h = Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
        left, right = _EDGE_INSET, w - _EDGE_INSET
        top, bottom = _EDGE_INSET, h - _EDGE_INSET
        seg_w = right - left  # comprimento das bordas horizontais (topo/base)
        seg_h = bottom - top  # comprimento das bordas verticais (laterais)
        perim = 2.0 * (seg_w + seg_h)
        d = (t % 1.0) * perim

        if d <= seg_w:  # topo: TL → TR
            return left + d, top
        d -= seg_w
        if d <= seg_h:  # direita: TR → BR
            return right, top + d
        d -= seg_h
        if d <= seg_w:  # base: BR → BL
            return right - d, bottom
        d -= seg_w
        return left, bottom - d  # esquerda: BL → TL

    def _sync_rect(self) -> None:
        self._rect.center = (int(self.x), int(self.y))

    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    @property
    def causes_damage(self) -> bool:
        return True

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x, self.y, self.RADIUS

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

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        if dt <= 0.0:
            return
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        # Atualiza posição no perímetro.
        self._t = (self._t + self.BASE_SPEED * dt) % 1.0
        self.x, self.y = self._calculate_pos(self._t)
        self._sync_rect()

        if self._activation_timer > 0.0:
            self._activation_timer = max(0.0, self._activation_timer - dt)
            return

        self._fire_timer -= dt
        if self._fire_timer <= 0.0:
            self._fire_timer = self._ROLE_FIRE_INTERVAL.get(self.role, 2.0) / self._aggr
            ctx.new_enemies.extend(self._fire(ctx.player_x, ctx.player_y))

    def _fire(self, px: float, py: float) -> List[object]:
        if self.role == "neon":
            return [NeonBurstShot(self.x, self.y, px, py)]
        if self.role == "missile":
            return [MicroMissile(self.x, self.y, px, py)]
        if self.role == "laser":
            col = max(40.0, min(Config.SCREEN_WIDTH - 40.0, px))
            return [VerticalLaser(col)]
        if self.role == "emp":
            return [EMPPulse(self.x, self.y)]
        return []

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x), int(self.y)
        col = self._ROLE_COLOR.get(self.role, _NEON_BLUE)
        if self.hit_timer > 0.0:
            col = _NEON_WHITE

        pulse = 0.6 + 0.4 * math.sin(self.anim_time * 6.0)
        halo_r = int(self.RADIUS + 8 + 4 * pulse)
        halo = pygame.Surface((halo_r * 2, halo_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(halo, (*col, 80), (halo_r, halo_r), halo_r)
        surface.blit(halo, (cx - halo_r, cy - halo_r))

        pygame.draw.circle(surface, col, (cx, cy), int(self.RADIUS))
        pygame.draw.circle(surface, _NEON_WHITE, (cx, cy), int(self.RADIUS * 0.4))
        pygame.draw.circle(surface, _NEON_WHITE, (cx, cy), int(self.RADIUS), 2)

        # Barra de vida. Clampada na tela: como a esfera encosta nas bordas
        # (inclusive topo/base), a barra acima dela sairia da tela — então o y é
        # preso à área visível.
        bw = int(self.RADIUS * 2)
        by = max(2, min(Config.SCREEN_HEIGHT - 7, cy - int(self.RADIUS) - 10))
        bx = cx - bw // 2
        pygame.draw.rect(surface, (30, 30, 30), (bx, by, bw, 5))
        frac = max(0.0, self.health / self.HEALTH)
        pygame.draw.rect(surface, col, (bx, by, int(bw * frac), 5))
