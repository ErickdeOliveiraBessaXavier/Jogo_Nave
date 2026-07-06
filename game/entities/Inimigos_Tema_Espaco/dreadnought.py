"""Dreadnought — "O Couraçado" do bioma STARFIELD.

Papel `tank` (inédito no Espaço): nave-capital pesada e **imparável**. Padrão
**"Juggernaut / Jockey"** (mesmo espírito do CyberTank): entra pela borda direita
precedida de um **aviso de entrada**, depois **jockeia** em torno do jogador
mantendo distância de combate — reposiciona sem parar, nunca sai sozinho, **só
morre por dano**. Contato não a mata (`on_ship_contact` → `killed=False`); a nave
leva dano pela camada de colisão.

**Duas torres nos flancos** miram sempre o jogador e cospem plasma (NeonBolt
parametrizado, projétil compartilhado): flanco de cima = **Autocanhão** (rajada),
flanco de baixo = **Canhão de Cerco** (carrega, tiro pesado). Morte = grande
explosão estrutural (sem meltdown neon — o Espaço é sóbrio).

Estética SÓBRIA (`space_palette`): casco fosco estático (o corpo NÃO gira),
poucos acentos frios, sem bloom. Contratos: §5 update via `update_in_context`
(empurra shells em `ctx.new_neon_bolts`); §3 `draw` só lê estado; §8 dano via
`HitResult`; §11 `aggressiveness_multiplier` propaga até cadência/velocidade.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List, Tuple

import pygame

from ...core.config import config as Config
from ..enemy_hit_mixin import EnemyHitMixin
from ..Inimigos_Tema_Cidade.neon_bolt import NeonBolt
from . import space_palette as pal
from .dreadnought_pixel_map import (
    BRIDGE_CELLS,
    CANNON_BARREL_CELLS,
    MOUNT_OFFSET_X,
    MOUNT_OFFSET_Y,
    PIXEL_COLS,
    PIXEL_ROWS,
    build_cannon_surface,
    build_hull_surface,
)

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult

# Plasma das torres (muted, não neon): aço-frio (Autocanhão) / âmbar (Cerco).
_AUTO_CORE: pal.RGB = (214, 224, 234)
_AUTO_GLOW: pal.RGB = pal.ACCENT_COLD
_SIEGE_CORE: pal.RGB = (234, 214, 176)
_SIEGE_GLOW: pal.RGB = pal.WARNING_AMBER

# ── Chevron-aviso pixel-art (telegraph de entrada, sóbrio: contorno âmbar) ────
_ARROW_COLS, _ARROW_ROWS = 11, 7
_arrow_cache: dict[int, pygame.Surface] = {}


def _build_warning_arrow(cell: int) -> pygame.Surface:
    """Chevron '>' fino (2px), âmbar apagado, sem contorno/bloom. Cacheado."""
    cached = _arrow_cache.get(cell)
    if cached is not None:
        return cached
    mid = _ARROW_ROWS // 2
    tip = _ARROW_COLS - 1
    surf = pygame.Surface((_ARROW_COLS * cell, _ARROW_ROWS * cell), pygame.SRCALPHA)
    for r in range(_ARROW_ROWS):
        c0 = tip - abs(r - mid)
        for c in (c0, c0 - 1):
            if 0 <= c < _ARROW_COLS:
                surf.fill(pal.WARNING_AMBER, (c * cell, r * cell, cell, cell))
    _arrow_cache[cell] = surf
    return surf


class _Turret:
    """Torre de flanco: mira SEMPRE o jogador. Encaixe fixo no casco (o corpo
    não gira, então `off_x/off_y` é a posição relativa constante ao centro)."""

    __slots__ = ("type", "off_x", "off_y", "angle", "fire_timer",
                 "flash", "recoil", "charge", "burst_count")

    def __init__(self, t_type: str, off_x: float, off_y: float, fire_timer: float) -> None:
        self.type = t_type
        self.off_x = off_x
        self.off_y = off_y
        self.angle = math.pi  # começa apontando à esquerda (nariz)
        self.fire_timer = fire_timer
        self.flash = 0.0
        self.recoil = 0.0
        self.charge = 0.0
        self.burst_count = 0


class Dreadnought(EnemyHitMixin):
    CELL: int = 5  # 27*5 = 135px largura, 15*5 = 75px altura — nave-capital
    SIZE: int = PIXEL_COLS * CELL

    HEALTH: int = 1600
    POINTS: int = 1800

    # ── Movimentação "Jockey" (mantém distância, reposiciona sem parar) ───────
    ENTER_SPEED: float = 100.0
    ENTER_FRAC: float = 0.84       # x-centro (fração) onde passa a jockear
    STANDOFF_MIN: float = 360.0
    STANDOFF_MAX: float = 430.0
    MAX_SPEED: float = 128.0       # pesado, pouco ágil
    STEER_GAIN: float = 2.2
    STEER_RESP: float = 3.4
    JOCKEY_SPAN: float = 1.0       # rad: cone à direita do jogador
    RETARGET_MIN: float = 0.9
    RETARGET_MAX: float = 1.9
    DART_CHANCE: float = 0.10
    ZONE_X_MIN_FRAC: float = 0.34
    ZONE_X_MAX_FRAC: float = 0.92
    EDGE_MARGIN: float = 30.0

    # ── Telegraph de entrada ─────────────────────────────────────────────────
    WARNING_DURATION: float = 4.5
    WARNING_SOUND_TIME: float = 1.0
    WARNING_ARROW_CELL: int = 6
    WARNING_EDGE_INSET: float = 30.0
    WARNING_SPIN_RATE: float = 3.6
    WARNING_GROW_MIN: float = 0.5
    WARNING_GROW_MAX: float = 1.45

    # ── Torres ────────────────────────────────────────────────────────────────
    AUTO_INTERVAL: float = 2.3
    AUTO_BURST: int = 4
    AUTO_BURST_GAP: float = 0.10
    SIEGE_INTERVAL: float = 4.4
    SIEGE_CHARGE_TIME: float = 1.3
    SHELL_SPEED: float = 280.0
    SIEGE_SPEED: float = 520.0

    _explosion_size_hit: int = 16

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
        self.active: bool = True
        self.aggressiveness_multiplier: float = aggressiveness_multiplier

        mx = MOUNT_OFFSET_X * self.w
        my = MOUNT_OFFSET_Y * self.h
        self.turrets: List[_Turret] = [
            _Turret("AUTOCANNON", mx, -my, self.AUTO_INTERVAL * 0.5),
            _Turret("SIEGE", mx, +my, self.SIEGE_INTERVAL),
        ]

        self.state: str = "warning"  # warning → enter → dominate
        self.vx: float = 0.0
        self.vy: float = 0.0
        self.jockey_angle: float = random.uniform(-0.5, 0.5)
        self.standoff: float = random.uniform(self.STANDOFF_MIN, self.STANDOFF_MAX)
        self.retarget_timer: float = 0.0

        self.warning_timer: float = 0.0
        self._warning_started: bool = False
        self._warning_sound_stopped: bool = False
        self.pulse: float = random.uniform(0.0, math.tau)
        self.hit_timer: float = 0.0

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        pad = int(self.cell * 4)
        return pygame.Rect(
            int(self.x) - pad, int(self.y) - self.cell,
            self.w + pad * 2, self.h + self.cell * 2,
        )

    def collision_circle(self) -> Tuple[float, float, float]:
        return self.x + self.w / 2, self.y + self.h / 2, self.w * 0.30

    def _center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    @property
    def draws_offscreen(self) -> bool:
        # No telegraph o corpo está fora da borda, mas o chevron precisa aparecer.
        return self.state == "warning"

    def _mount_pos(self, t: "_Turret") -> Tuple[float, float]:
        cx, cy = self._center()
        return cx + t.off_x, cy + t.off_y

    # ── Update ────────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        shells = self.update(ctx.sdt, ctx.player_x, ctx.player_y)
        if shells:
            ctx.new_neon_bolts.extend(shells)

    def update(
        self, dt: float, player_x: float, player_y: float
    ) -> List[NeonBolt] | None:
        if dt <= 0.0:
            return None

        self.pulse += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        if self.state == "warning":
            self._update_warning(dt)
            self._idle_turrets(dt)
            return None

        if self.state == "enter":
            self.x -= self.ENTER_SPEED * dt
            cy = self.y + self.h / 2
            self.y = cy + (player_y - cy) * min(1.0, dt * 1.6) - self.h / 2
            if self.x + self.w / 2 <= self.ENTER_FRAC * Config.SCREEN_WIDTH:
                self.state = "dominate"
                self.retarget_timer = 0.0
            self._idle_turrets(dt)
            return None

        self._jockey(dt, player_x, player_y)
        return self._update_turrets(dt, player_x, player_y)

    def _update_warning(self, dt: float) -> None:
        from ...systems import hit_sounds

        if not self._warning_started:
            self._warning_started = True
            hit_sounds.WARNING()

        self.warning_timer += dt
        if (
            not self._warning_sound_stopped
            and self.warning_timer >= self.WARNING_SOUND_TIME
        ):
            self._warning_sound_stopped = True
            hit_sounds.STOP_WARNING()

        if self.warning_timer >= self.WARNING_DURATION:
            self.state = "enter"

    def _jockey(self, dt: float, player_x: float, player_y: float) -> None:
        self.retarget_timer -= dt
        if self.retarget_timer <= 0.0:
            self.retarget_timer = random.uniform(self.RETARGET_MIN, self.RETARGET_MAX)
            if random.random() < self.DART_CHANCE:
                self.jockey_angle = random.uniform(-self.JOCKEY_SPAN, self.JOCKEY_SPAN)
                self.standoff = random.uniform(self.STANDOFF_MIN, self.STANDOFF_MAX)
            else:
                self.jockey_angle = max(
                    -self.JOCKEY_SPAN,
                    min(self.JOCKEY_SPAN, self.jockey_angle + random.uniform(-0.3, 0.3)),
                )
                self.standoff = max(
                    self.STANDOFF_MIN,
                    min(self.STANDOFF_MAX, self.standoff + random.uniform(-35.0, 35.0)),
                )

        cx, cy = self._center()
        bx, by = cx - player_x, cy - player_y
        cur_d = math.hypot(bx, by) or 1.0
        rad_x = player_x + (bx / cur_d) * self.standoff
        rad_y = player_y + (by / cur_d) * self.standoff
        ang = self.jockey_angle
        jx = player_x + math.cos(ang) * self.standoff
        jy = player_y + math.sin(ang) * self.standoff
        angular_pull = 0.18
        dx = rad_x + (jx - rad_x) * angular_pull + math.sin(self.pulse * 3.1) * 5.0
        dy = rad_y + (jy - rad_y) * angular_pull + math.cos(self.pulse * 3.7) * 5.0

        xmin = self.ZONE_X_MIN_FRAC * Config.SCREEN_WIDTH
        xmax = self.ZONE_X_MAX_FRAC * Config.SCREEN_WIDTH
        lo = self.EDGE_MARGIN + self.h / 2
        hi = Config.SCREEN_HEIGHT - self.EDGE_MARGIN - self.h / 2
        dx = max(xmin, min(xmax, dx))
        dy = max(lo, min(hi, dy))

        des_vx = max(-self.MAX_SPEED, min(self.MAX_SPEED, (dx - cx) * self.STEER_GAIN))
        des_vy = max(-self.MAX_SPEED, min(self.MAX_SPEED, (dy - cy) * self.STEER_GAIN))
        k = min(1.0, dt * self.STEER_RESP)
        self.vx += (des_vx - self.vx) * k
        self.vy += (des_vy - self.vy) * k

        ncx = max(xmin, min(xmax, cx + self.vx * dt))
        ncy = max(lo, min(hi, cy + self.vy * dt))
        self.x = ncx - self.w / 2
        self.y = ncy - self.h / 2

    def _idle_turrets(self, dt: float) -> None:
        for t in self.turrets:
            if t.flash > 0.0:
                t.flash = max(0.0, t.flash - dt * 5.0)
            if t.recoil > 0.0:
                t.recoil = max(0.0, t.recoil - dt * 4.0)

    def _update_turrets(
        self, dt: float, player_x: float, player_y: float
    ) -> List[NeonBolt] | None:
        agg = max(0.5, self.aggressiveness_multiplier)
        shells: List[NeonBolt] | None = None

        for t in self.turrets:
            mx, my = self._mount_pos(t)
            t.angle = math.atan2(player_y - my, player_x - mx)

            if t.flash > 0.0:
                t.flash = max(0.0, t.flash - dt * 5.0)
            if t.recoil > 0.0:
                t.recoil = max(0.0, t.recoil - dt * 4.0)

            t.fire_timer -= dt

            if t.type == "AUTOCANNON":
                if t.burst_count > 0:
                    if t.fire_timer <= 0.0:
                        if shells is None:
                            shells = []
                        shells.append(self._fire(t, mx, my))
                        t.burst_count -= 1
                        t.fire_timer = (
                            self.AUTO_BURST_GAP / agg
                            if t.burst_count > 0
                            else self.AUTO_INTERVAL / agg
                        )
                elif t.fire_timer <= 0.0:
                    t.burst_count = self.AUTO_BURST
                    t.fire_timer = 0.0
            else:  # SIEGE
                t.charge = min(1.0, max(0.0, 1.0 - t.fire_timer / self.SIEGE_CHARGE_TIME))
                if t.fire_timer <= 0.0:
                    if shells is None:
                        shells = []
                    shells.append(self._fire(t, mx, my))
                    t.fire_timer = self.SIEGE_INTERVAL / agg
                    t.charge = 0.0

        return shells

    def _fire(self, t: _Turret, mx: float, my: float) -> NeonBolt:
        t.flash = 1.0
        t.recoil = 1.0
        barrel = CANNON_BARREL_CELLS * self.cell
        mux = mx + math.cos(t.angle) * barrel
        muy = my + math.sin(t.angle) * barrel
        agg = self.aggressiveness_multiplier
        if t.type == "AUTOCANNON":
            speed = self.SHELL_SPEED * (0.9 + 0.2 * agg)
            return NeonBolt(
                mux, muy,
                math.cos(t.angle) * speed, math.sin(t.angle) * speed,
                core=_AUTO_CORE, glow=_AUTO_GLOW, radius=4, glow_radius=9,
            )
        speed = self.SIEGE_SPEED * (0.95 + 0.1 * agg)
        return NeonBolt(
            mux, muy,
            math.cos(t.angle) * speed, math.sin(t.angle) * speed,
            core=_SIEGE_CORE, glow=_SIEGE_GLOW, radius=7, glow_radius=16,
        )

    # ── Dano / morte ──────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.06
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            # Falha estrutural: uma grande explosão sóbria (sem meltdown neon).
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=int(self.w * 0.8),
                sound=hit_sounds.EXPLOSION_BOSS,
            )
        return HitResult(
            explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        # Imparável: sobrevive ao contato (a nave leva dano pela colisão).
        return HitResult(killed=False, explosion_size=10, sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool:
        return self.dead

    # ── Render (sóbrio) ───────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        if self.state == "warning":
            self._draw_warning(surface)
            return

        cx, cy = self._center()

        # Casco estático (não gira). Flash de hit discreto (BLEND_RGB_ADD).
        hull = build_hull_surface(self.cell)
        if self.hit_timer > 0.0:
            hull = hull.copy()
            hull.fill((70, 76, 88), special_flags=pygame.BLEND_RGB_ADD)
        surface.blit(hull, (int(self.x), int(self.y)))

        # Ponte/luzes de comando: acento frio pulsando de leve (1 disco tênue).
        self._draw_bridge(surface)

        # Torres nos flancos, sempre mirando o jogador.
        for t in self.turrets:
            self._draw_turret(surface, t)

    def _draw_bridge(self, surface: pygame.Surface) -> None:
        cell = self.cell
        pulse = 0.5 + 0.5 * math.sin(self.pulse * 3.0)
        col = pal.lerp(pal.ACCENT_COLD_DIM, pal.ACCENT_COLD, 0.3 + 0.4 * pulse)
        for c, r in BRIDGE_CELLS:
            surface.fill(
                col, (int(self.x + c * cell), int(self.y + r * cell), cell, cell)
            )

    def _draw_turret(self, surface: pygame.Surface, t: _Turret) -> None:
        cell = self.cell
        mx, my = self._mount_pos(t)
        ang = t.angle
        ca, sa = math.cos(ang), math.sin(ang)
        recoil_px = t.recoil * cell * 2.0

        cannon = build_cannon_surface(cell)
        rot = pygame.transform.rotate(cannon, -math.degrees(ang))
        pivot_x = mx - ca * recoil_px
        pivot_y = my - sa * recoil_px
        surface.blit(rot, rot.get_rect(center=(int(pivot_x), int(pivot_y))))

        barrel = CANNON_BARREL_CELLS * cell - recoil_px
        mux = int(mx + ca * barrel)
        muy = int(my + sa * barrel)

        # Carga do Cerco: um pequeno anel âmbar crescente na boca (sem bloom).
        if t.type == "SIEGE" and t.charge > 0.15:
            cr = max(2, int(cell * 1.6 * t.charge))
            pygame.draw.circle(surface, pal.WARNING_AMBER, (mux, muy), cr, 1)

        # Clarão do disparo: 1 disco pequeno e discreto (não halo de várias camadas).
        if t.flash > 0.0:
            fcol = _AUTO_GLOW if t.type == "AUTOCANNON" else _SIEGE_GLOW
            fr = max(2, int(cell * (1.2 + 2.2 * t.flash)))
            pygame.draw.circle(surface, fcol, (mux, muy), fr, 1)

    def _draw_warning(self, surface: pygame.Surface) -> None:
        arrow = _build_warning_arrow(self.WARNING_ARROW_CELL)
        aw, ah = arrow.get_size()
        p = min(1.0, self.warning_timer / self.WARNING_DURATION)
        g = self.WARNING_GROW_MIN + (self.WARNING_GROW_MAX - self.WARNING_GROW_MIN) * p
        cx = Config.SCREEN_WIDTH - self.WARNING_EDGE_INSET - aw / 2
        cy = self.y + self.h / 2
        sy = math.cos(self.pulse * self.WARNING_SPIN_RATE)
        w = max(1, int(aw * g))
        h = max(1, int(ah * g * abs(sy)))
        img = pygame.transform.scale(arrow, (w, h))
        if sy < 0:
            img = pygame.transform.flip(img, False, True)
        surface.blit(img, (int(cx - w / 2), int(cy - h / 2)))
