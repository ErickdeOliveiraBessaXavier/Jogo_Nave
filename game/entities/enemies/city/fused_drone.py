"""FusedDrone — mini-chefe dinâmico nascido da fusão de 4 City Drones.

Gerado quando uma `ChannelingGroup` completa a transformação. É uma criatura
bem mais perigosa: disco grande e brilhante, muita vida, cospe drones homing
periodicamente e **sobrevive ao contato** (diferente dos drones comuns). Seu
diferencial é de **suporte**: mantém distância do jogador (não vai para o
corpo-a-corpo) enquanto "dá luz" aos outros inimigos. Não é um boss formal
(não usa BossHitMixin nem música de boss) — é um inimigo tanky gerado em runtime.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List

import pygame

from ....core.config import config as Config
from ....core.sound import sound_manager
from .._shared.enemy_hit_mixin import EnemyHitMixin
from . import city_glow
from . import city_palette as pal
from .city_drone import CityDrone
from .city_drone_pixel_map import PIXEL_COLS, build_static_surface
from ....core.fire_timer import carry_interval

if TYPE_CHECKING:
    from ....systems.entity_context import EnemyUpdateContext
    from ....systems.hit_result import HitResult

# Cores do anel de estilhaços (cicla os 3 acentos da proposta).
_RING_COLORS = [pal.ELECTRIC_BLUE, pal.CYBER_MAGENTA, pal.TOXIC_ORANGE]


class FusedDrone(EnemyHitMixin):
    # Marca de tipo lida por getattr (§5), não por isinstance: é assim que o
    # `FusionGovernor` conta quantas fusões já estão em jogo sem importar esta
    # classe (o que fecharia um ciclo systems → entities → systems).
    is_fused_drone = True

    CELL = 5
    SIZE = PIXEL_COLS * CELL  # 75px
    HEALTH = 240
    POINTS = 600

    MAX_SPEED = 165.0
    SPRING_K = 6.0
    SPRING_DAMPING = 4.5
    EDGE = 30.0
    # Suporte, não perseguidor: orbita a esta distância do jogador (px),
    # recuando se ele se aproxima e reaproximando se fica longe demais.
    STANDOFF_DISTANCE = 300.0

    ATTACK_INTERVAL = 3.2  # intervalo entre rajadas de drones homing
    SPAWN_COUNT = 2

    _explosion_size_killed = 80
    _explosion_size_hit = 14

    def __init__(
        self,
        center_x: float,
        center_y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = True,
        health_multiplier: float = 1.0,
    ) -> None:
        self.w = self.SIZE
        self.h = self.SIZE
        self.x = center_x - self.w / 2
        self.y = center_y - self.h / 2

        self.dead = False
        # §11: escala a vida-base pelo multiplicador da dificuldade (o FusedDrone
        # nasce fora do spawner, via canalização) e propaga aos bebês homing.
        self.health_multiplier = health_multiplier
        scaled_health = max(1, int(self.HEALTH * health_multiplier))
        self.health = scaled_health
        self.max_health = scaled_health
        self.aggressiveness_multiplier = aggressiveness_multiplier
        self.side_scroll = side_scroll

        self._max_speed = self.MAX_SPEED * aggressiveness_multiplier
        self.vx = 0.0
        self.vy = 0.0

        self.pulse = random.uniform(0.0, math.tau)
        self.spin = 0.0
        self.hit_timer = 0.0
        # Pequeno atraso antes da primeira rajada (deixa o jogador reagir ao spawn).
        self.attack_timer = self.ATTACK_INTERVAL * 0.6

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x + self.w / 2, self.y + self.h / 2, self.w * 0.45

    # ── Update ────────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        babies = self.update(ctx.sdt, ctx.player_x, ctx.player_y)
        if babies:
            ctx.new_enemies.extend(babies)

    def update(self, dt: float, player_x: float, player_y: float) -> List[CityDrone] | None:
        if dt <= 0.0:
            return None

        self.pulse += dt
        self.spin += 1.2 * dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        cx = self.x + self.w / 2
        cy = self.y + self.h / 2

        # Standoff/kite (mola mole + teto de velocidade): o alvo fica sobre a
        # linha jogador→drone, a STANDOFF_DISTANCE do jogador. Recua quando o
        # jogador se aproxima e reaproxima quando fica longe — sem corpo-a-corpo.
        dx = cx - player_x
        dy = cy - player_y
        dist = math.hypot(dx, dy)
        if dist > 1e-3:
            ux, uy = dx / dist, dy / dist
        else:
            ux, uy = 0.0, -1.0  # jogador exatamente em cima → escolhe subir
        wobble = math.sin(self.pulse * 1.3) * 40.0
        tx = player_x + ux * self.STANDOFF_DISTANCE
        ty = player_y + uy * self.STANDOFF_DISTANCE + wobble
        ax = self.SPRING_K * (tx - cx) - self.SPRING_DAMPING * self.vx
        ay = self.SPRING_K * (ty - cy) - self.SPRING_DAMPING * self.vy
        self.vx += ax * dt
        self.vy += ay * dt

        speed_sq = self.vx * self.vx + self.vy * self.vy
        if speed_sq > self._max_speed * self._max_speed:
            scale = self._max_speed / math.sqrt(speed_sq)
            self.vx *= scale
            self.vy *= scale

        self.x += self.vx * dt
        self.y += self.vy * dt

        # Fica na arena (mini-chefe não some pela borda).
        self.x = max(self.EDGE, min(Config.SCREEN_WIDTH - self.EDGE - self.w, self.x))
        self.y = max(self.EDGE, min(Config.SCREEN_HEIGHT - self.EDGE - self.h, self.y))

        # Rajada periódica de drones homing.
        self.attack_timer -= dt
        if self.attack_timer <= 0.0:
            # Preserva a sobra do frame (ver `carry_interval`): o intervalo é
            # longo e o ganho é pequeno, mas o padrão de reagendamento do
            # projeto é este — atribuição direta é o que produz deriva.
            self.attack_timer = carry_interval(self.attack_timer, self.ATTACK_INTERVAL)
            return self._spawn_homing(cx, cy)
        return None

    def _spawn_homing(self, cx: float, cy: float) -> List[CityDrone]:
        sound_manager.play_shot()
        babies: List[CityDrone] = []
        for _ in range(self.SPAWN_COUNT):
            baby = CityDrone(
                cx,
                cy,
                aggressiveness_multiplier=self.aggressiveness_multiplier,
                side_scroll=self.side_scroll,
                size_tier=0,
                homing=True,
                health_multiplier=self.health_multiplier,
            )
            baby.x = cx - baby.w / 2
            baby.y = cy - baby.h / 2
            angle = random.uniform(0.0, math.tau)
            burst = random.uniform(150.0, 240.0)
            baby.vx = math.cos(angle) * burst
            baby.vy = math.sin(angle) * burst
            babies.append(baby)
        return babies

    # ── Dano / morte ──────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.06
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ...effects.explosion import ExplosionType
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=self.POINTS,
                explosion_size=self._explosion_size_killed,
                explosion_type=ExplosionType.CYBER,
                sound=hit_sounds.EXPLOSION_BOSS,
            )
        return HitResult(
            explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ...effects.explosion import ExplosionType
        from ....systems.hit_result import HitResult

        # Mini-chefe sobrevive ao contato; o dano ao jogador é aplicado pelo
        # sistema de colisão (ship_vs_enemies) independentemente de killed.
        return HitResult(explosion_size=20, explosion_type=ExplosionType.CYBER)

    def should_remove(self) -> bool:
        return self.dead

    # ── Render ──────────────────────────────────────────────────────────────
    def _blit_glow(
        self,
        surface: pygame.Surface,
        cx: int,
        cy: int,
        radius: int,
        color: tuple[int, int, int],
    ) -> None:
        glow = city_glow.get_glow(radius, color)
        surface.blit(
            glow, (cx - radius, cy - radius), special_flags=pygame.BLEND_RGBA_ADD
        )

    def draw(self, surface: pygame.Surface) -> None:
        cell = self.CELL
        base = build_static_surface(cell, 0)
        pos = (int(self.x), int(self.y))

        if self.hit_timer > 0.0:
            img = base.copy()
            img.fill((220, 220, 220), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, pos)
        else:
            surface.blit(base, pos)

        cx = int(self.x + self.w / 2)
        cy = int(self.y + self.h / 2)

        # Anel de estilhaços girando (ameaça).
        ring_r = self.w * 0.6
        for k in range(6):
            ang = self.spin + k * (math.tau / 6.0)
            ex = int(cx + math.cos(ang) * ring_r)
            ey = int(cy + math.sin(ang) * ring_r)
            self._blit_glow(surface, ex, ey, max(3, int(cell * 1.4)), _RING_COLORS[k % 3])

        # Núcleo pulsante intenso (energia fundida).
        pulse = 0.5 + 0.5 * math.sin(self.pulse * 5.0)
        core = pal.lerp(pal.ELECTRIC_BLUE, (255, 255, 255), pulse)
        self._blit_glow(surface, cx, cy, int(cell * 3.0 + cell * pulse), core)
