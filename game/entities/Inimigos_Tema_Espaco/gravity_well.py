"""Gravity Well — "Poço Gravitacional" do bioma STARFIELD.

Papel `area_denial` (inédito no Espaço). Uma **singularidade compacta** que
**ancora** num ponto (não desce) e controla aquela região da tela. Em ciclo:
`entra → ancora → carrega (telegraph) → puxa → cooldown`. Durante o PUXÃO:

  - **arrasta a nave** para o centro (força radial com falloff), emitida em
    `ctx.new_gravity_wells` e aplicada pela cena ao movimento da nave; e
  - **causa dano contínuo** no núcleo via `ctx.new_area_blasts` (mesmo roteador
    de dano de área da mina / CyberTank / CyberCaptor).

Counterplay: sair do raio de influência (telegrafado por um anel fino) ou
destruí-la — a atração é vencível acelerando para fora. Estética SÓBRIA
(`space_palette`): disco escuro colapsado + anel de acreção fino, sem bloom.

Contratos: herda `EnemyHitMixin` (§9); update via `update_in_context` (§5);
`draw` sem efeitos colaterais (§3); dano/força por buffers do contexto.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Tuple

import pygame

from ...core.config import config as Config
from ..enemy_hit_mixin import EnemyHitMixin
from . import space_palette as pal
from .gravity_well_pixel_map import PIXEL_COLS, PIXEL_ROWS, build_disc_surface

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult

# Emissão de puxão: (cx, cy, raio_influência, força_px_s). A cena aplica à nave.
GravityPull = Tuple[float, float, float, float]


class GravityWell(EnemyHitMixin):
    CELL: int = 4
    SIZE: int = PIXEL_COLS * CELL  # 52px de corpo

    HEALTH: int = 120
    POINTS: int = 300

    # ── Ancoragem (não desce; fixa num ponto, com leve bob) ──────────────────
    ENTER_DURATION: float = 0.9  # deslize temporal do spawn até a âncora
    BOB_AMPL: float = 5.0

    # ── Ciclo de atração ─────────────────────────────────────────────────────
    AIM_TIME: float = 1.0        # telegraph antes de puxar
    PULL_TIME: float = 2.6       # janela de atração ativa
    COOLDOWN: float = 1.8
    DAMAGE_INTERVAL: float = 0.30  # cadência do dano no núcleo

    INFLUENCE_RADIUS: float = 200.0  # raio que arrasta a nave
    CORE_DAMAGE_RADIUS: float = 52.0  # raio interno que causa dano
    PULL_SPEED: float = 155.0        # força máx. de arrasto (px/s no centro)

    _explosion_size_killed: int = 30
    _explosion_size_hit: int = 8

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = False,
        anchor: Tuple[float, float] | None = None,
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
        self.aggressiveness_multiplier: float = max(0.5, aggressiveness_multiplier)

        # Ponto fixo onde ancora (clampeado à zona jogável, não no fundo da tela).
        ax, ay = anchor if anchor is not None else (x, max(y, Config.SCREEN_HEIGHT * 0.30))
        margin = self.INFLUENCE_RADIUS * 0.35
        self.anchor_x: float = max(margin, min(Config.SCREEN_WIDTH - margin, ax))
        self.anchor_y: float = max(
            margin, min(Config.SCREEN_HEIGHT * 0.72, ay)
        )
        self.spawn_x: float = float(x)
        self.spawn_y: float = float(y)
        self.enter_t: float = 0.0
        self.entering: bool = True

        self.state: str = "cooldown"
        self.aim_timer: float = 0.0
        self.pull_timer: float = 0.0
        self.cooldown_timer: float = self.COOLDOWN * 0.5
        self.dmg_timer: float = 0.0

        self.spin: float = random.uniform(0.0, math.tau)  # anel de acreção
        self.bob_phase: float = random.uniform(0.0, math.tau)
        self.hit_timer: float = 0.0

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> Tuple[float, float, float]:
        return self.x + self.w / 2, self.y + self.h / 2, self.w * 0.42

    def _center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    @property
    def _pulling(self) -> bool:
        return self.state == "pull"

    # ── Update ────────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        blast, pull = self.update(ctx.sdt)
        if blast is not None:
            ctx.new_area_blasts.append(blast)
        if pull is not None:
            ctx.new_gravity_wells.append(pull)

    def update(
        self, dt: float
    ) -> Tuple[Tuple[float, float, float] | None, GravityPull | None]:
        if dt <= 0.0:
            return None, None

        self.spin += dt * 1.2
        self.bob_phase += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        # Posição: desliza do spawn até a âncora (smoothstep temporal), depois bob.
        bob = math.sin(self.bob_phase * 1.4) * self.BOB_AMPL
        tx = self.anchor_x - self.w / 2
        ty = self.anchor_y - self.h / 2 + bob
        if self.entering:
            self.enter_t += dt
            p = min(1.0, self.enter_t / self.ENTER_DURATION)
            e = p * p * (3.0 - 2.0 * p)
            self.x = self.spawn_x + (tx - self.spawn_x) * e
            self.y = self.spawn_y + (ty - self.spawn_y) * e
            if p >= 1.0:
                self.entering = False
            return None, None
        self.x, self.y = tx, ty

        cx, cy = self._center()
        blast: Tuple[float, float, float] | None = None
        pull: GravityPull | None = None

        if self.state == "cooldown":
            self.cooldown_timer -= dt
            if self.cooldown_timer <= 0.0:
                self.state = "aim"
                self.aim_timer = self.AIM_TIME
        elif self.state == "aim":
            self.aim_timer -= dt
            if self.aim_timer <= 0.0:
                self.state = "pull"
                self.pull_timer = self.PULL_TIME
                self.dmg_timer = 0.0
        else:  # pull
            self.pull_timer -= dt
            pull = (cx, cy, self.INFLUENCE_RADIUS, self.PULL_SPEED)
            self.dmg_timer -= dt
            if self.dmg_timer <= 0.0:
                self.dmg_timer = self.DAMAGE_INTERVAL / self.aggressiveness_multiplier
                blast = (cx, cy, self.CORE_DAMAGE_RADIUS)
            if self.pull_timer <= 0.0:
                self.state = "cooldown"
                self.cooldown_timer = self.COOLDOWN

        return blast, pull

    # ── Dano / morte ────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.08
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def should_remove(self) -> bool:
        return self.dead

    # ── Render (sóbrio: sem bloom aditivo de várias camadas) ──────────────────
    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = self._center()
        icx, icy = int(cx), int(cy)

        if not self.entering:
            self._draw_influence_ring(surface, icx, icy)
            if self._pulling:
                self._draw_infall_streaks(surface, cx, cy)

        # Anel de acreção: duas elipses finas "achatadas" pela rotação (look 3D),
        # tom frio contido. Atrás do corpo.
        self._draw_accretion(surface, cx, cy)

        # Corpo (disco colapsado). Flash de hit discreto (BLEND_RGB_ADD).
        base = build_disc_surface(self.cell)
        if self.hit_timer > 0.0:
            img = base.copy()
            img.fill((60, 66, 78), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, (int(self.x), int(self.y)))
        else:
            surface.blit(base, (int(self.x), int(self.y)))

        # Núcleo: aro frio fino; no puxão, um ponto interno levemente mais claro.
        core_r = max(2, int(self.cell * 1.5))
        pygame.draw.circle(surface, pal.CORE_DARK, (icx, icy), core_r)
        rim = pal.CORE_HOT if self._pulling else pal.CORE_RIM
        pygame.draw.circle(surface, rim, (icx, icy), core_r, 1)

    def _draw_accretion(self, surface: pygame.Surface, cx: float, cy: float) -> None:
        rad = self.w * 0.66
        for i in range(2):
            a = self.spin + i * (math.pi / 2.0)
            squash = abs(math.sin(a))  # 0 de perfil .. 1 de frente
            col = pal.lerp(pal.CORE_RIM, pal.CORE_HOT, 0.2 + 0.5 * squash)
            if i == 0:
                rx, ry = rad, rad * (0.16 + 0.84 * squash)
            else:
                rx, ry = rad * (0.16 + 0.84 * squash), rad
            rx, ry = max(2.0, rx), max(2.0, ry)
            rect = pygame.Rect(int(cx - rx), int(cy - ry), int(rx * 2), int(ry * 2))
            pygame.draw.ellipse(surface, col, rect, 1)

    def _draw_influence_ring(
        self, surface: pygame.Surface, icx: int, icy: int
    ) -> None:
        """Anel fino telegrafando o raio de influência. Na mira, cresce/fade-in;
        no puxão, fica estável. Desenhado numa surface com alpha p/ ser discreto."""
        if self.state == "aim":
            p = 1.0 - max(0.0, self.aim_timer) / self.AIM_TIME
            alpha = int(70 * p)
        elif self._pulling:
            alpha = 95
        else:
            return
        r = int(self.INFLUENCE_RADIUS)
        ring = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(ring, (*pal.ACCENT_COLD, alpha), (r + 1, r + 1), r, 1)
        surface.blit(ring, (icx - r - 1, icy - r - 1))

    def _draw_infall_streaks(
        self, surface: pygame.Surface, cx: float, cy: float
    ) -> None:
        # Poucos traços curtos apontando para dentro (matéria caindo) — discretos.
        cos, sin = math.cos, math.sin
        for k in range(5):
            a = self.spin * 0.7 + k * (math.tau / 5.0)
            d_out = self.w * 0.9 + (k * 7)
            d_in = d_out - 9
            x0, y0 = cx + cos(a) * d_out, cy + sin(a) * d_out
            x1, y1 = cx + cos(a) * d_in, cy + sin(a) * d_in
            pygame.draw.line(
                surface, pal.ACCENT_COLD_DIM, (int(x0), int(y0)), (int(x1), int(y1)), 1
            )
