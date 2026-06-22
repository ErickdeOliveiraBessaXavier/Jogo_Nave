"""Mortar Drone (Artilheiro) — bombardeio de área telegrafado do bioma CITY.

Variante "de cerco" do Neon Sniper. Em vez do tiro de linha hitscan, **ancora no
alto** e dispara em ciclo um **morteiro de área**: durante o *aim* (windup)
desenha um **círculo-alvo no chão** (telegrama) na posição prevista do jogador;
ao fim do windup **detona** ali um blast de área (dano via `ctx.new_area_blasts`,
mesmo roteador da mina/Captor) + explosão visual. O counterplay é **sair do
círculo** antes da detonação — pressão posicional, não de mira.

Reusa infra existente (sem novos buffers): o telegrama é desenhado pela própria
entidade durante o windup; o dano é um `area_blast` one-shot. Contratos
(convenções do projeto): §5 update polimórfico; §3 `draw` só lê estado; §8 dano via
`area_blast`/`HitResult`; §11 `aggressiveness`/`health_multiplier`.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any, Tuple

import pygame

from ...core.config import config as Config
from ...entities.explosion import ExplosionType
from ..enemy_hit_mixin import EnemyHitMixin
from . import city_glow
from . import city_palette as pal
from .mortar_drone_pixel_map import (
    BARREL_NEON,
    CORE_CELLS,
    CORE_NEON,
    CORE_NEON_DIM,
    MUZZLE_CELL,
    PIXEL_COLS,
    PIXEL_ROWS,
    build_mortar_surface,
)

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult

_TARGET: pal.RGB = pal.TOXIC_ORANGE


class MortarDrone(EnemyHitMixin):
    CELL: int = 4
    SIZE: int = PIXEL_COLS * CELL  # 60px

    HEALTH: int = 60
    POINTS: int = 230

    PERCH_INSET: float = 80.0   # quão fundo ancora (centro, no eixo de profundidade)
    ENTER_SPEED: float = 150.0
    DRIFT_SPEED: float = 36.0   # deriva lenta no eixo de slide (vaivém)

    AIM_TIME: float = 1.35      # windup/telegrama (dividido por aggressiveness)
    FIRE_FLASH_TIME: float = 0.18
    COOLDOWN: float = 1.7
    BLAST_RADIUS: float = 72.0  # raio do dano == raio do telegrama (WYSIWYG)
    EDGE_MARGIN: float = 30.0

    _explosion_size_hit: int = 12

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

        # Eixo de profundidade (entra/ancora) vs. slide (deriva lenta), como o sniper.
        if side_scroll:
            self.perch_target: float = Config.SCREEN_WIDTH - self.PERCH_INSET
        else:
            self.perch_target = float(self.PERCH_INSET)
        self.drift_dir: float = random.choice((-1.0, 1.0))

        self.state: str = "enter"
        self.aim_timer: float = 0.0
        self.cooldown_timer: float = self.COOLDOWN * random.uniform(0.4, 0.9)
        self.fire_flash: float = 0.0
        self.aim_p: float = 0.0  # 0..1 progresso do telegrama (lido no draw)
        self.target: Tuple[float, float] | None = None

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

    def _set_center(self, cx: float, cy: float) -> None:
        self.x = cx - self.w / 2
        self.y = cy - self.h / 2

    def _muzzle_pos(self) -> Tuple[float, float]:
        col, row = MUZZLE_CELL
        return self.x + (col + 0.5) * self.cell, self.y + (row + 0.5) * self.cell

    def _slide_bounds(self) -> Tuple[float, float]:
        if self.side_scroll:
            return (
                self.EDGE_MARGIN + self.h / 2,
                Config.SCREEN_HEIGHT - self.EDGE_MARGIN - self.h / 2,
            )
        return (
            self.EDGE_MARGIN + self.w / 2,
            Config.SCREEN_WIDTH - self.EDGE_MARGIN - self.w / 2,
        )

    def _aim_duration(self) -> float:
        return self.AIM_TIME / max(0.5, self.aggressiveness_multiplier)

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        result = self.update(ctx.sdt, ctx.player_x, ctx.player_y)
        if result is not None:
            blast, explosion = result
            ctx.new_area_blasts.append(blast)
            ctx.new_explosions.append(explosion)

    def update(
        self, dt: float, player_x: float, player_y: float
    ) -> Tuple[
        Tuple[float, float, float], Tuple[float, float, int, Any]
    ] | None:
        if dt <= 0.0:
            return None

        self.pulse += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)
        if self.fire_flash > 0.0:
            self.fire_flash = max(0.0, self.fire_flash - dt)

        cx, cy = self._center()
        depth = cx if self.side_scroll else cy
        slide = cy if self.side_scroll else cx

        result = None

        if self.state == "enter":
            if depth < self.perch_target:
                depth = min(self.perch_target, depth + self.ENTER_SPEED * dt)
            else:
                depth = max(self.perch_target, depth - self.ENTER_SPEED * dt)
            if abs(depth - self.perch_target) < 1.5:
                depth = self.perch_target
                self.state = "cooldown"
        else:
            # Deriva lenta de vaivém no eixo de slide (não fica congelado).
            lo, hi = self._slide_bounds()
            slide += self.drift_dir * self.DRIFT_SPEED * dt
            if slide <= lo:
                slide = lo
                self.drift_dir = 1.0
            elif slide >= hi:
                slide = hi
                self.drift_dir = -1.0
            depth = self.perch_target

            if self.state == "cooldown":
                self.cooldown_timer -= dt
                if self.cooldown_timer <= 0.0:
                    self.state = "aim"
                    self.aim_timer = self._aim_duration()
                    self.aim_p = 0.0
                    self.target = (player_x, player_y)  # trava o alvo no início
            elif self.state == "aim":
                self.aim_timer -= dt
                self.aim_p = 1.0 - max(0.0, self.aim_timer) / self._aim_duration()
                if self.aim_timer <= 0.0:
                    result = self._fire()
                    self.state = "cooldown"
                    self.cooldown_timer = self.COOLDOWN
                    self.aim_p = 0.0

        if self.side_scroll:
            self._set_center(depth, slide)
        else:
            self._set_center(slide, depth)

        return result

    def _fire(
        self,
    ) -> Tuple[
        Tuple[float, float, float], Tuple[float, float, int, Any]
    ] | None:
        if self.target is None:
            return None
        tx, ty = self.target
        self.fire_flash = self.FIRE_FLASH_TIME
        blast = (tx, ty, self.BLAST_RADIUS)
        explosion = (tx, ty, int(self.BLAST_RADIUS * 0.9), ExplosionType.CYBER)
        return blast, explosion

    # ── Dano / morte ──────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.08
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=34,
                explosion_type=ExplosionType.CYBER,
                sound=hit_sounds.EXPLOSION_ALIEN,
            )
        return HitResult(
            explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        self.dead = True
        return HitResult(
            killed=True,
            explosion_size=34,
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
        base = build_mortar_surface(cell)

        # Telegrama no chão durante o windup (atrás do corpo p/ leitura clara).
        if self.state == "aim" and self.target is not None:
            self._draw_telegraph(surface)

        # Flash de hit OU brilho do windup.
        if self.hit_timer > 0.0 or self.aim_p > 0.0:
            add = 210 if self.hit_timer > 0.0 else int(30 + 130 * self.aim_p)
            img = base.copy()
            img.fill((add, add, add), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, (int(self.x), int(self.y)))
        else:
            surface.blit(base, (int(self.x), int(self.y)))

        # Núcleo laranja pulsante (mais forte conforme carrega).
        pulse = 0.5 + 0.5 * math.sin(self.pulse * 5.0)
        core_t = min(1.0, pulse * 0.6 + self.aim_p)
        core_col = pal.lerp(CORE_NEON_DIM, CORE_NEON, core_t)
        core_r = int(cell * 1.4 + cell * (pulse + self.aim_p))
        for c, r in CORE_CELLS:
            gx = int(self.x + (c + 0.5) * cell)
            gy = int(self.y + (r + 0.5) * cell)
            self._blit_glow(surface, gx, gy, core_r, core_col)

        # Boca do barril: pisca branco no disparo.
        mx, my = self._muzzle_pos()
        if self.fire_flash > 0.0:
            self._blit_glow(
                surface, int(mx), int(my),
                int(cell * (1.6 + 6.0 * self.fire_flash)), (255, 255, 255),
            )
        else:
            self._blit_glow(surface, int(mx), int(my), int(cell * 1.1), BARREL_NEON)

    def _draw_telegraph(self, surface: pygame.Surface) -> None:
        if self.target is None:
            return
        tx, ty = int(self.target[0]), int(self.target[1])
        p = self.aim_p
        r = int(self.BLAST_RADIUS)
        # Surface translúcida para o preenchimento + anel (alpha cresce com o windup).
        d = r * 2 + 4
        surf = pygame.Surface((d, d), pygame.SRCALPHA)
        half = d // 2
        pygame.draw.circle(surf, (*_TARGET, int(20 + 50 * p)), (half, half), r)
        pulse = 0.5 + 0.5 * math.sin(self.pulse * (6.0 + 16.0 * p))
        ring_a = min(255, int((110 + 130 * p) * (0.5 + 0.5 * pulse)))
        pygame.draw.circle(surf, (255, 200, 120, ring_a), (half, half), r, 3)
        surface.blit(surf, (tx - half, ty - half))
        # Cruz de mira no centro.
        pygame.draw.line(surface, (255, 220, 160), (tx - 6, ty), (tx + 6, ty), 1)
        pygame.draw.line(surface, (255, 220, 160), (tx, ty - 6), (tx, ty + 6), 1)
