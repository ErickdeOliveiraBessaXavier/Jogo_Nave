"""Neon Sniper — sentinela de longa distância do bioma CITY.

"O Olho de Longa Distância" da proposta. Nasce numa borda superior ("Perch
Unit"), desliza ao longo da borda para se alinhar ao jogador ("Slide & Lock"),
**ancora**, carrega um tiro (telegraph puramente visual — sem som, igual aos
irmãos não-boss `MountainMage`/`EyeEnemy`) e dispara um `NeonBolt` mirado.
Ao morrer faz "Core Implosion": o núcleo magenta colapsa para dentro (efeito
`CoreImplosion`, disparado pelo EntityManager via `triggers_special_death`).

Composição com o restante do tema: chassi/glow do pixel-map
(`neon_sniper_pixel_map`), glow compartilhado (`city_glow`), paleta
(`city_palette`). Update polimórfico via `update_in_context` (§5); `draw` sem
efeitos colaterais (§3); dano via `HitResult` (§8).
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List, Tuple

import pygame

from ....core.config import config as Config
from .._shared.enemy_hit_mixin import EnemyHitMixin
from . import city_glow
from . import city_palette as pal
from .neon_bolt import NeonBolt
from .neon_sniper_pixel_map import (
    ACCENT_CELLS,
    ACCENT_NEON,
    ACCENT_NEON_DIM,
    CORE_NEON,
    CORE_NEON_DIM,
    MUZZLE_CELL,
    NEON_CELLS,
    PIXEL_COLS,
    PIXEL_ROWS,
    build_sniper_surface,
)

if TYPE_CHECKING:
    from ....systems.entity_context import EnemyUpdateContext
    from ....systems.hit_result import HitResult


class NeonSniper(EnemyHitMixin):
    CELL: int = 4
    SIZE: int = PIXEL_COLS * CELL  # 60px

    HEALTH: int = 55
    POINTS: int = 200

    PERCH_INSET: float = 72.0  # quão fundo na tela a unidade ancora (centro)
    ENTER_SPEED: float = 150.0
    MAX_SLIDE_SPEED: float = 150.0
    SLIDE_GAIN: float = 3.2  # ganho do alinhamento (1/s)
    ALIGN_TOL: float = 10.0  # tolerância de alinhamento p/ travar
    EDGE_MARGIN: float = 28.0

    SETTLE_TIME: float = 0.22  # pausa curta ao travar antes de carregar
    CHARGE_DURATION: float = 1.4  # telegraph (dividido por aggressiveness)
    COOLDOWN: float = 1.6
    MAX_SLIDE_TIME: float = 2.4  # desiste de perseguir e trava mesmo assim

    BOLT_SPEED: float = 340.0

    _explosion_size_hit: int = 12

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = True,
    ) -> None:
        self.side_scroll: bool = side_scroll
        self.cell: int = self.CELL
        self.w: int = PIXEL_COLS * self.cell
        self.h: int = PIXEL_ROWS * self.cell

        self.x: float = float(x)
        self.y: float = float(y)

        self.dead: bool = False
        self.health: int = self.HEALTH
        self.aggressiveness_multiplier: float = aggressiveness_multiplier

        # Eixo de "profundidade" (entra/ancora) vs. eixo de "slide" (alinha):
        #   side_scroll → ancora perto da direita, desliza no eixo Y.
        #   vertical    → ancora perto do topo,    desliza no eixo X.
        if side_scroll:
            self.perch_target: float = Config.SCREEN_WIDTH - self.PERCH_INSET
        else:
            self.perch_target = float(self.PERCH_INSET)

        self.state: str = "enter"
        self.vslide: float = 0.0
        self.slide_timer: float = 0.0
        self.settle_timer: float = 0.0
        self.charge_timer: float = 0.0
        self.cooldown_timer: float = 0.0
        self.charge_p: float = 0.0  # 0..1 progresso do telegraph (lido no draw)
        self.locked_target: Tuple[float, float] | None = None
        self.fire_flash: float = 0.0

        # Animação (alimentada pelo update; lida pelo draw — §3).
        self.pulse: float = random.uniform(0.0, math.tau)
        self.hit_timer: float = 0.0

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> Tuple[float, float, float]:
        # Corpo estreito alongado: disco um pouco menor que a meia-largura.
        return self.x + self.w / 2, self.y + self.h / 2, self.w * 0.36

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
            return self.EDGE_MARGIN + self.h / 2, Config.SCREEN_HEIGHT - self.EDGE_MARGIN - self.h / 2
        return self.EDGE_MARGIN + self.w / 2, Config.SCREEN_WIDTH - self.EDGE_MARGIN - self.w / 2

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        bolts = self.update(ctx.sdt, ctx.player_x, ctx.player_y)
        if bolts:
            ctx.new_neon_bolts.extend(bolts)

    def update(
        self, dt: float, player_x: float, player_y: float
    ) -> List[NeonBolt] | None:
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

        emitted: List[NeonBolt] | None = None

        if self.state == "enter":
            depth = self._approach(depth, self.perch_target, self.ENTER_SPEED * dt)
            if abs(depth - self.perch_target) < 1.5:
                depth = self.perch_target
                self.state = "slide"
                self.slide_timer = 0.0
                self.vslide = 0.0

        elif self.state == "slide":
            slide = self._slide_toward(slide, player_y if self.side_scroll else player_x, dt)
            self.slide_timer += dt
            target = self._clamp_slide(player_y if self.side_scroll else player_x)
            if abs(slide - target) < self.ALIGN_TOL or self.slide_timer >= self.MAX_SLIDE_TIME:
                self.state = "lock"
                self.settle_timer = self.SETTLE_TIME

        elif self.state == "lock":
            self.settle_timer -= dt
            if self.settle_timer <= 0.0:
                self.state = "charge"
                self.charge_timer = self.CHARGE_DURATION / max(0.5, self.aggressiveness_multiplier)
                self.locked_target = (player_x, player_y)
                self.charge_p = 0.0

        elif self.state == "charge":
            self.charge_timer -= dt
            self.charge_p = 1.0 - max(0.0, self.charge_timer) / (
                self.CHARGE_DURATION / max(0.5, self.aggressiveness_multiplier)
            )
            if self.charge_timer <= 0.0:
                emitted = self._fire()
                self.state = "cooldown"
                self.cooldown_timer = self.COOLDOWN
                self.charge_p = 0.0

        elif self.state == "cooldown":
            self.cooldown_timer -= dt
            if self.cooldown_timer <= 0.0:
                self.state = "slide"
                self.slide_timer = 0.0
                self.vslide = 0.0

        # Mantém a profundidade travada na linha de perch (exceto durante a entrada).
        if self.state != "enter":
            depth = self.perch_target

        if self.side_scroll:
            self._set_center(depth, slide)
        else:
            self._set_center(slide, depth)

        return emitted

    @staticmethod
    def _approach(value: float, target: float, step: float) -> float:
        if value < target:
            return min(target, value + step)
        return max(target, value - step)

    def _clamp_slide(self, target: float) -> float:
        lo, hi = self._slide_bounds()
        return max(lo, min(hi, target))

    def _slide_toward(self, slide: float, raw_target: float, dt: float) -> float:
        target = self._clamp_slide(raw_target)
        desired_v = max(
            -self.MAX_SLIDE_SPEED,
            min(self.MAX_SLIDE_SPEED, (target - slide) * self.SLIDE_GAIN),
        )
        # Suaviza a velocidade (aceleração limitada) para um deslize fluido.
        self.vslide += (desired_v - self.vslide) * min(1.0, dt * 9.0)
        return slide + self.vslide * dt

    def _fire(self) -> List[NeonBolt]:
        mx, my = self._muzzle_pos()
        tx, ty = self.locked_target if self.locked_target is not None else (mx, my + 1.0)
        dx, dy = tx - mx, ty - my
        d = math.hypot(dx, dy) or 1.0
        vx, vy = dx / d * self.BOLT_SPEED, dy / d * self.BOLT_SPEED
        self.fire_flash = 0.12
        return [NeonBolt(mx, my, vx, vy)]

    # ── Dano / morte ──────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.08
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            # explosion_size=0: a "Core Implosion" (via triggers_special_death)
            # substitui a explosão padrão para leitura do colapso para dentro.
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=0,
                sound=hit_sounds.EXPLOSION_ALIEN,
                triggers_special_death=True,
            )
        return HitResult(
            explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        self.dead = True
        return HitResult(
            killed=True,
            explosion_size=0,
            sound=hit_sounds.EXPLOSION_ALIEN,
            triggers_special_death=True,
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
        base = build_sniper_surface(cell)

        # Flash de hit OU brilho crescente do "charging" — BLEND_RGB_ADD preserva
        # o alpha dos cantos transparentes (ver nota no City Drone).
        if self.hit_timer > 0.0 or self.charge_p > 0.0:
            add = 210 if self.hit_timer > 0.0 else int(30 + 140 * self.charge_p)
            img = base.copy()
            img.fill((add, add, add), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, (int(self.x), int(self.y)))
        else:
            surface.blit(base, (int(self.x), int(self.y)))

        # Telegraph: linha de mira + reticle no alvo travado, durante o charge.
        if self.state == "charge" and self.locked_target is not None:
            self._draw_telegraph(surface)

        # Glow do núcleo magenta (luneta) — mais forte conforme carrega.
        pulse = 0.5 + 0.5 * math.sin(self.pulse * 5.0)
        core_t = min(1.0, pulse * 0.6 + self.charge_p)
        neon = pal.lerp(CORE_NEON_DIM, CORE_NEON, core_t)
        core_r = int(cell * 1.4 + cell * (pulse + self.charge_p))
        for c, r in NEON_CELLS:
            gx = int(self.x + (c + 0.5) * cell)
            gy = int(self.y + (r + 0.5) * cell)
            self._blit_glow(surface, gx, gy, core_r, neon)

        # Acentos azuis (asas + boca); a boca pisca no disparo.
        flick = 0.5 + 0.5 * math.sin(self.pulse * 14.0)
        accent = pal.lerp(ACCENT_NEON_DIM, ACCENT_NEON, 0.4 + 0.6 * flick)
        for c, r in ACCENT_CELLS:
            gx = int(self.x + (c + 0.5) * cell)
            gy = int(self.y + (r + 0.5) * cell)
            ar = int(cell * 1.1)
            if (c, r) == MUZZLE_CELL and self.fire_flash > 0.0:
                ar = int(cell * (1.6 + 6.0 * self.fire_flash))
                self._blit_glow(surface, gx, gy, ar, (255, 255, 255))
            else:
                self._blit_glow(surface, gx, gy, ar, accent)

    def _draw_telegraph(self, surface: pygame.Surface) -> None:
        if self.locked_target is None:
            return
        mx, my = self._muzzle_pos()
        tx, ty = self.locked_target
        p = self.charge_p
        # Linha de mira fina, intensificando com o charge.
        line_col = pal.lerp((60, 10, 50), CORE_NEON, p)
        pygame.draw.line(surface, line_col, (int(mx), int(my)), (int(tx), int(ty)), 1)
        # Reticle que encolhe em direção ao "lock" (de 18px até 6px).
        reticle_r = int(18 - 12 * p)
        if reticle_r > 1:
            pygame.draw.circle(surface, CORE_NEON, (int(tx), int(ty)), reticle_r, 1)
        # Ponto central do alvo cresce conforme trava.
        pygame.draw.circle(surface, (255, 255, 255), (int(tx), int(ty)), max(1, int(1 + 3 * p)))
