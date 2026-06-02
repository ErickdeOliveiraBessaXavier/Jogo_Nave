"""Cyber Tank — "O Colosso Urbano" do bioma CITY.

Fortaleza móvel com padrão **"Juggernaut"**: avança **devagar e constante** para
a esquerda (entra pela direita no side-scroll), **imparável** — não toma recuo e
**não morre por contato** com a nave (só por dano).

Silhueta em **ampulheta horizontal** (ver `cyber_tank_pixel_map`): duas vagens
largas nas pontas, cintura estreita no centro com o reator. **Dois canhões**
integrados às pontas **giram para mirar** o jogador, cada um cobrindo a sua
metade (arco), e cospem plasma pesado (NeonBolt parametrizado). Esquerda =
**Gatling** (rajadas rápidas), direita = **Railcannon** (carrega, tiro forte).

Spawn **"Gatekeeper"** (sozinho) precedido por um **aviso** ("Heavy Unit
Incoming": som + chevrons na borda enquanto entra). Morte **"Structural
Failure"**: o EntityManager dispara `TankMeltdown` (via `triggers_special_death`)
— placas voam (estilhaços visuais) + poça de metal fundido neon.

Contratos (CLAUDE.md): §5 update polimórfico via `update_in_context` (empurra
shells em `ctx.new_neon_bolts`); §3 `draw` só lê estado (timers/pulso/heading
alimentados pelo update); §8 dano via `HitResult`; §11 `aggressiveness_multiplier`
propaga até cadência/velocidade do tiro.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List, Tuple

import pygame

from ...core.config import config as Config
from ..enemy_hit_mixin import EnemyHitMixin
from . import city_glow
from . import city_palette as pal
from .cyber_tank_pixel_map import (
    CANNON_BARREL_CELLS,
    CORE_NEON,
    CORE_NEON_DIM,
    ENGINE_CELLS,
    ENGINE_NEON,
    ENGINE_NEON_DIM,
    MOUNT_OFFSET_X,
    PIXEL_COLS,
    PIXEL_ROWS,
    build_cannon_surface,
    build_tank_surface,
)
from .neon_bolt import NeonBolt

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult

# Plasma das torres: núcleo claro + halo laranja (Gatling) / azul (Railcannon).
_SHELL_CORE: pal.RGB = (255, 236, 205)
_SHELL_GLOW: pal.RGB = pal.TOXIC_ORANGE
_RAIL_CORE: pal.RGB = (235, 250, 255)
_RAIL_GLOW: pal.RGB = pal.ELECTRIC_BLUE


class _Turret:
    """Canhão de ponta: mira **sempre** o jogador. Fica num encaixe que orbita o
    centro junto com o giro do chassi (`off_x/off_y` é o encaixe em repouso)."""

    __slots__ = (
        "type",
        "off_x",
        "off_y",
        "angle",
        "fire_timer",
        "flash",
        "recoil",
        "charge",
        "burst_count",
    )

    def __init__(
        self, t_type: str, off_x: float, off_y: float, fire_timer: float
    ) -> None:
        self.type = t_type
        self.off_x = off_x
        self.off_y = off_y
        self.angle = math.pi  # apontando à esquerda no início
        self.fire_timer = fire_timer
        self.flash = 0.0  # 0..1, clarão do disparo (decai)
        self.recoil = 0.0  # 0..1, recuo visual do cano (decai)
        self.charge = 0.0  # 0..1, carga do Railcannon
        self.burst_count = 0  # tiros restantes da rajada (Gatling)


class CyberTank(EnemyHitMixin):
    CELL: int = 4
    SIZE: int = PIXEL_COLS * CELL  # 100px (largura)

    HEALTH: int = 1400  # Fortaleza móvel
    POINTS: int = 1500

    # ── Juggernaut ──────────────────────────────────────────────────────────
    ADVANCE_SPEED: float = 48.0
    MAX_VERTICAL_SPEED: float = 22.0
    EDGE_MARGIN: float = 28.0
    EXIT_MARGIN: float = 140.0
    BODY_SPIN_RATE: float = 0.7  # rad/s — a ampulheta gira no próprio eixo

    # ── Canhões (miram sempre o jogador) ─────────────────────────────────────
    # Gatling (uma ponta): rajada rápida.
    GATLING_INTERVAL: float = 2.4
    GATLING_BURST: int = 5
    GATLING_BURST_GAP: float = 0.08
    # Railcannon (outra ponta): tiro pesado, carrega.
    RAIL_INTERVAL: float = 4.2
    RAIL_CHARGE_TIME: float = 1.2

    SHELL_SPEED: float = 290.0
    RAIL_SPEED: float = 540.0

    _explosion_size_hit: int = 18

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

        # Canhões integrados às duas pontas da ampulheta (encaixe em repouso no
        # eixo horizontal; orbitam o centro junto com o giro do chassi).
        mx = MOUNT_OFFSET_X * self.w
        self.turrets: List[_Turret] = [
            _Turret("GATLING", -mx, 0.0, self.GATLING_INTERVAL * 0.5),
            _Turret("RAILCANNON", +mx, 0.0, self.RAIL_INTERVAL),
        ]

        self._warned: bool = False  # toca o aviso "Heavy Unit Incoming" 1×
        self.pulse: float = random.uniform(0.0, math.tau)
        self.body_spin: float = random.uniform(0.0, math.tau)  # giro contínuo
        self.hit_timer: float = 0.0

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        # Rect um pouco maior p/ abranger os canhões que projetam das pontas.
        pad = int(self.cell * 5)
        return pygame.Rect(
            int(self.x) - pad, int(self.y) - self.cell,
            self.w + pad * 2, self.h + self.cell * 2,
        )

    def collision_circle(self) -> Tuple[float, float, float]:
        # Círculo cobrindo a massa central do corpo (pontas/canhões projetam fora).
        return self.x + self.w / 2, self.y + self.h / 2, self.w * 0.30

    def _center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def _mount_pos(self, t: "_Turret") -> Tuple[float, float]:
        """Posição do encaixe do canhão, orbitando o centro com o giro do chassi.
        Usa a mesma convenção de `pygame.transform.rotate(body_spin)` do draw."""
        cx, cy = self._center()
        rad = self.body_spin
        cos_r, sin_r = math.cos(rad), math.sin(rad)
        mx = cx + t.off_x * cos_r + t.off_y * sin_r
        my = cy - t.off_x * sin_r + t.off_y * cos_r
        return mx, my

    def _is_entering(self) -> bool:
        # Ainda surgindo pela direita — fase de aviso/telegraph.
        return self.x > Config.SCREEN_WIDTH * 0.72

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        shells = self.update(ctx.sdt, ctx.player_x, ctx.player_y)
        if shells:
            ctx.new_neon_bolts.extend(shells)

    def update(
        self, dt: float, player_x: float, player_y: float
    ) -> List[NeonBolt] | None:
        if dt <= 0.0:
            return None

        if not self._warned:
            self._warned = True
            from ...systems import hit_sounds

            hit_sounds.WARNING()

        self.pulse += dt
        self.body_spin = (self.body_spin + self.BODY_SPIN_RATE * dt) % math.tau
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        # Avanço constante para a esquerda (juggernaut).
        self.x -= self.ADVANCE_SPEED * dt

        # Rastreio vertical preguiçoso do jogador (limitado).
        cx, cy = self._center()
        lo = self.EDGE_MARGIN + self.h / 2
        hi = Config.SCREEN_HEIGHT - self.EDGE_MARGIN - self.h / 2
        desired = max(lo, min(hi, player_y))
        dvy = desired - cy
        step = min(self.MAX_VERTICAL_SPEED * dt, abs(dvy))
        self.y += math.copysign(step, dvy)

        self._check_exit()

        # Canhões só miram/atiram depois de surgir na tela.
        if self._is_entering():
            self._idle_turrets(dt)
            return None
        return self._update_turrets(dt, player_x, player_y)

    def _check_exit(self) -> None:
        if self.x + self.w < -self.EXIT_MARGIN:
            self.dead = True

    def _idle_turrets(self, dt: float) -> None:
        # Enquanto entra: só decai os timers visuais (sem mirar/atirar).
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
            # Sempre apontado para o jogador (sem arco, sem limite de giro).
            t.angle = math.atan2(player_y - my, player_x - mx)

            if t.flash > 0.0:
                t.flash = max(0.0, t.flash - dt * 5.0)
            if t.recoil > 0.0:
                t.recoil = max(0.0, t.recoil - dt * 4.0)

            t.fire_timer -= dt

            if t.type == "GATLING":
                if t.burst_count > 0:
                    if t.fire_timer <= 0.0:
                        if shells is None:
                            shells = []
                        shells.append(self._fire(t, mx, my))
                        t.burst_count -= 1
                        t.fire_timer = (
                            self.GATLING_BURST_GAP / agg
                            if t.burst_count > 0
                            else self.GATLING_INTERVAL / agg
                        )
                elif t.fire_timer <= 0.0:
                    t.burst_count = self.GATLING_BURST
                    t.fire_timer = 0.0
            else:  # RAILCANNON
                # Carga clampeada a 1.0 (antes crescia sem limite quando o timer
                # ficava negativo → "carregando pra sempre"). Dispara assim que o
                # timer zera — a mira já está sempre no jogador.
                t.charge = min(1.0, max(0.0, 1.0 - t.fire_timer / self.RAIL_CHARGE_TIME))
                if t.fire_timer <= 0.0:
                    if shells is None:
                        shells = []
                    shells.append(self._fire(t, mx, my))
                    t.fire_timer = self.RAIL_INTERVAL / agg
                    t.charge = 0.0

        return shells

    def _fire(self, t: _Turret, mx: float, my: float) -> NeonBolt:
        t.flash = 1.0
        t.recoil = 1.0
        barrel = CANNON_BARREL_CELLS * self.cell
        mux = mx + math.cos(t.angle) * barrel
        muy = my + math.sin(t.angle) * barrel
        agg = self.aggressiveness_multiplier
        if t.type == "GATLING":
            speed = self.SHELL_SPEED * (0.9 + 0.2 * agg)
            return NeonBolt(
                mux, muy, math.cos(t.angle) * speed, math.sin(t.angle) * speed,
                core=_SHELL_CORE, glow=_SHELL_GLOW, radius=5, glow_radius=14,
            )
        speed = self.RAIL_SPEED * (0.95 + 0.1 * agg)
        return NeonBolt(
            mux, muy, math.cos(t.angle) * speed, math.sin(t.angle) * speed,
            core=_RAIL_CORE, glow=_RAIL_GLOW, radius=9, glow_radius=26,
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
            # explosion_size=0: o "Structural Failure" (via triggers_special_death)
            # substitui a explosão — placas voam + poça de metal fundido.
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=0,
                sound=hit_sounds.EXPLOSION_BOSS,
                triggers_special_death=True,
            )
        return HitResult(
            explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        # Juggernaut imparável: sobrevive ao contato (a nave é quem leva dano,
        # aplicado pela camada de colisão). Só solta faísca (killed=False).
        return HitResult(killed=False, explosion_size=10, sound=hit_sounds.BOSS_DAMAGE)

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
        cx, cy = self._center()
        rad = self.body_spin
        cos_r, sin_r = math.cos(rad), math.sin(rad)

        if self._is_entering():
            self._draw_warning(surface)

        # 1. Chassi (ampulheta) GIRANDO no próprio eixo. Flash de hit com
        # BLEND_RGB_ADD (preserva alpha dos cantos transparentes).
        base = build_tank_surface(cell)
        if self.hit_timer > 0.0:
            base = base.copy()
            base.fill((180, 180, 180), special_flags=pygame.BLEND_RGB_ADD)
        rotated = pygame.transform.rotate(base, math.degrees(rad))
        surface.blit(rotated, rotated.get_rect(center=(int(cx), int(cy))))

        # 2. Conduítes/vents laranja — acompanham o giro do chassi.
        eflick = 0.5 + 0.5 * math.sin(self.pulse * 16.0)
        ecol = pal.lerp(ENGINE_NEON_DIM, ENGINE_NEON, 0.4 + 0.6 * eflick)
        for c, r in ENGINE_CELLS:
            ox = (c + 0.5) * cell - self.w / 2
            oy = (r + 0.5) * cell - self.h / 2
            gx = int(cx + ox * cos_r + oy * sin_r)
            gy = int(cy - ox * sin_r + oy * cos_r)
            self._blit_glow(surface, gx, gy, int(cell * 1.4), ecol)

        # 3. Reator central ESTÁTICO (não gira) — pulsa no centro do eixo.
        pulse = 0.5 + 0.5 * math.sin(self.pulse * 5.0)
        core_col = pal.lerp(CORE_NEON_DIM, CORE_NEON, pulse)
        self._blit_glow(surface, int(cx), int(cy), int(cell * 3.4 + cell * pulse), core_col)
        pygame.draw.circle(surface, (235, 250, 255), (int(cx), int(cy)), max(2, int(cell * 0.9)))

        # 4. Canhões nas pontas (orbitam com o giro), sempre mirando o jogador.
        for t in self.turrets:
            self._draw_turret(surface, t)

    def _draw_turret(self, surface: pygame.Surface, t: _Turret) -> None:
        cell = self.cell
        mx, my = self._mount_pos(t)
        ang = t.angle
        ca, sa = math.cos(ang), math.sin(ang)
        recoil_px = t.recoil * cell * 2.5

        # Pivô = centro do sprite do canhão; aplica recuo ao longo de -mira.
        cannon = build_cannon_surface(cell)
        rot = pygame.transform.rotate(cannon, -math.degrees(ang))
        pivot_x = mx - ca * recoil_px
        pivot_y = my - sa * recoil_px
        surface.blit(rot, rot.get_rect(center=(int(pivot_x), int(pivot_y))))

        barrel = CANNON_BARREL_CELLS * cell - recoil_px
        mux = mx + ca * barrel
        muy = my + sa * barrel

        # Railcannon: glow de carga crescente na boca + arcos elétricos.
        if t.type == "RAILCANNON" and t.charge > 0.1:
            self._blit_glow(
                surface, int(mux), int(muy), int(cell * 3.0 * t.charge), _RAIL_GLOW
            )
            if t.charge > 0.6:
                for _ in range(2):
                    back = random.uniform(0.3, 1.0) * barrel
                    ex = int(mx + ca * back + random.uniform(-4, 4))
                    ey = int(my + sa * back + random.uniform(-4, 4))
                    self._blit_glow(surface, ex, ey, int(cell * 1.3), (200, 255, 255))

        # Clarão do disparo na boca.
        if t.flash > 0.0:
            fcol = _SHELL_GLOW if t.type == "GATLING" else _RAIL_GLOW
            self._blit_glow(
                surface, int(mux), int(muy), int(cell * (2.5 + 6.0 * t.flash)), fcol
            )

    def _draw_warning(self, surface: pygame.Surface) -> None:
        # Chevrons ">" piscando na borda direita, na faixa vertical do tanque.
        blink = 0.5 + 0.5 * math.sin(self.pulse * 12.0)
        if blink < 0.45:
            return
        cy = int(self.y + self.h / 2)
        edge = Config.SCREEN_WIDTH - 14
        col = pal.lerp((120, 40, 20), (255, 90, 30), blink)
        for k in range(3):
            ox = edge - k * 12
            pts = [(ox - 10, cy - 14), (ox, cy), (ox - 10, cy + 14)]
            pygame.draw.lines(surface, col, False, pts, 3)
