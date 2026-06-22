"""Tesla Twins — "A Barreira Vertical" do bioma CITY.

Dupla de torres com bobinas de cobre, ligadas por um **arco elétrico vertical**
("Boundary Link"): um gêmeo ancora perto do topo, o outro perto da base, e o
feixe entre eles forma uma **parede** que avança devagar para a esquerda — uma
"linha de chegada" que o jogador precisa **romper destruindo um dos gêmeos**
(o feixe não tem brecha). O contato com o feixe causa dano (1 hit, via
`area_blast` no roteador de explosão de mina).

Movimento **"Mirroring"**: os dois entram pela direita à mesma velocidade e
avançam juntos, mantendo o arco vertical e tenso (a coordenação mora no
`TeslaLink`, §1). Morte **"Short Circuit"**: abater um gêmeo derruba o feixe e
joga o sobrevivente em **sobrecarga** — fica vermelho, cospe tiros aleatórios
por 2s e se autodestrói numa descarga.

Contratos (convenções do projeto): §5 update polimórfico via `update_in_context` (empurra
bolts/blasts/explosões nos buffers do ctx); §3 `draw` só lê estado; §8 dano via
`HitResult`/`area_blast`; §11 `aggressiveness`/`health_multiplier` propagados.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Tuple

import pygame

from ...core.config import config as Config
from ...entities.explosion import ExplosionType
from ..enemy_hit_mixin import EnemyHitMixin
from . import city_glow
from . import city_palette as pal
from .neon_bolt import NeonBolt
from .tesla_twin_pixel_map import (
    COIL_CELLS,
    COIL_NEON,
    CORE_CELLS,
    CORE_NEON,
    CORE_NEON_DIM,
    PIXEL_COLS,
    PIXEL_ROWS,
    build_tower_surface,
)

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult
    from .tesla_link import TeslaLink

_BEAM: pal.RGB = pal.ELECTRIC_BLUE
_BEAM_HOT: pal.RGB = (215, 245, 255)
_OVERLOAD: pal.RGB = (255, 60, 40)


def _point_seg_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """Distância do ponto (px,py) ao segmento A-B."""
    abx, aby = bx - ax, by - ay
    seg_sq = abx * abx + aby * aby
    if seg_sq < 1e-6:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * abx + (py - ay) * aby) / seg_sq
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + abx * t), py - (ay + aby * t))


class TeslaTwin(EnemyHitMixin):
    CELL: int = 5
    W: int = PIXEL_COLS * CELL  # 45px
    H: int = PIXEL_ROWS * CELL  # 75px
    SIZE: int = H  # eixo maior (usado por margens do spawner)

    HEALTH: int = 130
    POINTS: int = 210

    ENTER_SPEED: float = 165.0
    ADVANCE_SPEED: float = 40.0       # parede avança devagar p/ a esquerda
    ENTER_TARGET_FRAC: float = 0.86   # x-centro onde para de entrar (perto da direita)

    BEAM_HIT_RADIUS: float = 16.0     # tolerância de colisão do feixe (vs. nave)
    BEAM_BLOCK_RADIUS: float = 14.0   # tolerância p/ bloquear projéteis da nave
    BEAM_BLAST_RADIUS: int = 18       # raio do area_blast emitido no contato

    SHORT_CIRCUIT_TIME: float = 2.0
    SC_SHOT_INTERVAL: float = 0.16
    SC_BOLT_SPEED: float = 300.0

    _explosion_size_hit: int = 12
    _explosion_size_killed: int = 32

    def __init__(
        self,
        x: float,
        y: float,
        is_top: bool,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = True,
        health_multiplier: float = 1.0,
    ) -> None:
        self.is_top: bool = is_top
        self.side_scroll: bool = side_scroll
        self.cell: int = self.CELL
        self.w: int = self.W
        self.h: int = self.H

        self.x: float = float(x)
        self.y: float = float(y)

        self.dead: bool = False
        self.health_multiplier: float = health_multiplier
        self.health: int = max(1, int(self.HEALTH * health_multiplier))
        self.aggressiveness_multiplier: float = aggressiveness_multiplier

        # Coordenação da dupla (atribuída pelo TeslaLink no spawn).
        self.link: "TeslaLink | None" = None

        # "enter" → "hold" (espera o parceiro) → "advance" → "overload".
        self.state: str = "enter"
        self.enter_target: float = self.ENTER_TARGET_FRAC * Config.SCREEN_WIDTH

        # Sobrecarga (Short Circuit).
        self.sc_timer: float = 0.0
        self.sc_shot_timer: float = 0.0
        self._self_destructed: bool = False

        # Animação (alimentada pelo update; lida pelo draw — §3).
        self.pulse: float = random.uniform(0.0, math.tau)
        self.hit_timer: float = 0.0

    # ── Geometria ─────────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> Tuple[float, float, float]:
        return self.x + self.w / 2, self.y + self.h / 2, self.w * 0.42

    def _center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def emitter_point(self) -> Tuple[float, float]:
        """Ponta da bobina (origem do arco), apontando para o gêmeo parceiro.
        Topo: base do sprite (arco desce). Base: topo do sprite (arco sobe)."""
        cx = self.x + self.w / 2
        return (cx, self.y + self.h) if self.is_top else (cx, self.y)

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        if dt <= 0.0:
            return

        self.pulse += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        if self.state == "enter":
            cx = self.x + self.w / 2 - self.ENTER_SPEED * dt
            if cx <= self.enter_target:
                cx = self.enter_target
                self.state = "hold"
            self.x = cx - self.w / 2
        elif self.state == "hold":
            pass  # aguarda o parceiro; o TeslaLink libera os dois p/ "advance"
        elif self.state == "advance":
            self.x -= self.ADVANCE_SPEED * dt
            if self.x + self.w < -40.0:
                self.dead = True  # a parede atravessou e saiu pela esquerda
        else:  # overload
            self._update_overload(dt, ctx)

        # Coordenação (handoff de entrada + detecção de morte do parceiro).
        link = self.link
        if link is not None:
            link.tick(self, ctx)
            # Feixe: só o líder (topo) computa o dano, p/ não duplicar.
            if link.beam_active() and link.is_leader(self):
                self._beam_damage(ctx, link)

    def _beam_damage(self, ctx: "EnemyUpdateContext", link: "TeslaLink") -> None:
        partner = link.partner_of(self)
        if partner is None:
            return
        ax, ay = self.emitter_point()
        bx, by = partner.emitter_point()
        d = _point_seg_dist(ctx.player_x, ctx.player_y, ax, ay, bx, by)
        if d <= self.BEAM_HIT_RADIUS:
            # Blast one-shot na posição da nave (roteador de explosão de mina, com
            # invuln). O i-frame do jogador evita multi-hit em frames seguidos.
            ctx.new_area_blasts.append(
                (ctx.player_x, ctx.player_y, float(self.BEAM_BLAST_RADIUS))
            )

    def projectile_fields(self) -> list[tuple[object, ...]]:
        """Campos que bloqueiam projéteis da nave (contrato duck-typed do §5,
        consumido por `Collisions.projectiles_vs_blocker_fields`).

        O feixe vertical é uma parede sem brecha — bloqueia inclusive tiros. Só
        o líder (topo) reporta, para não duplicar. Lista vazia se inativo.
        """
        link = self.link
        if link is None or not link.beam_active() or not link.is_leader(self):
            return []
        partner = link.partner_of(self)
        if partner is None:
            return []
        ax, ay = self.emitter_point()
        bx, by = partner.emitter_point()
        return [("seg", ax, ay, bx, by, self.BEAM_BLOCK_RADIUS)]

    def begin_overload(self) -> None:
        """Short Circuit: o sobrevivente sobrecarrega e vai se autodestruir."""
        self.state = "overload"
        self.sc_timer = self.SHORT_CIRCUIT_TIME
        self.sc_shot_timer = 0.0

    def _update_overload(self, dt: float, ctx: "EnemyUpdateContext") -> None:
        self.sc_timer -= dt
        # Cospe tiros aleatórios (cadência acelera com a agressividade).
        self.sc_shot_timer -= dt
        if self.sc_shot_timer <= 0.0:
            self.sc_shot_timer = self.SC_SHOT_INTERVAL / max(
                0.5, self.aggressiveness_multiplier
            )
            cx, cy = self._center()
            ang = random.uniform(0.0, math.tau)
            speed = self.SC_BOLT_SPEED * (0.85 + 0.3 * self.aggressiveness_multiplier)
            ctx.new_neon_bolts.append(
                NeonBolt(
                    cx, cy,
                    math.cos(ang) * speed, math.sin(ang) * speed,
                    core=(255, 220, 200), glow=_OVERLOAD, radius=4, glow_radius=12,
                )
            )
        if self.sc_timer <= 0.0 and not self._self_destructed:
            self._self_destructed = True
            self.dead = True
            cx, cy = self._center()
            # Descarga final: explosão (pool) + blast de dano em área.
            ctx.new_explosions.append((cx, cy, 46, ExplosionType.CYBER))
            ctx.new_area_blasts.append((cx, cy, self.w * 0.75))

    # ── Dano / morte ──────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.07
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, damage: int, _hit_x: float, _hit_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        self.take_damage(damage)
        if self.dead:
            # O parceiro entra em "Short Circuit" no próximo frame (via TeslaLink).
            return HitResult(
                killed=True,
                points=self.get_points_value(),
                explosion_size=self._explosion_size_killed,
                explosion_type=ExplosionType.CYBER,
                sound=hit_sounds.EXPLOSION_ALIEN,
            )
        return HitResult(
            explosion_size=self._explosion_size_hit, sound=hit_sounds.BOSS_DAMAGE
        )

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        # Pilar-barreira: sobrevive ao contato (a nave leva dano pela camada de
        # colisão). Não pode ser derrubado por ramming — destrua-o com tiros.
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
        overloading = self.state == "overload"

        # 1. Feixe (atrás dos corpos): desenhado UMA vez pelo líder (topo).
        link = self.link
        if link is not None and link.beam_active() and link.is_leader(self):
            partner = link.partner_of(self)
            if partner is not None:
                self._draw_beam(surface, self.emitter_point(), partner.emitter_point())

        # 2. Chassi (espelhado na vertical p/ o gêmeo da base → bobina p/ cima).
        base = build_tower_surface(cell)
        if not self.is_top:
            base = pygame.transform.flip(base, False, True)
        if self.hit_timer > 0.0 or overloading:
            img = base.copy()
            if overloading:
                # Pisca vermelho cada vez mais forte conforme vai estourar.
                p = 1.0 - max(0.0, self.sc_timer) / self.SHORT_CIRCUIT_TIME
                flick = 0.5 + 0.5 * math.sin(self.pulse * 30.0)
                add = int(60 + 160 * p * flick)
                img.fill((add, 0, 0), special_flags=pygame.BLEND_RGB_ADD)
            else:
                img.fill((200, 200, 200), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(img, (int(self.x), int(self.y)))
        else:
            surface.blit(base, (int(self.x), int(self.y)))

        # 3. Glows do núcleo (azul) e da bobina (cobre). No overload viram vermelho.
        self._draw_glows(surface, cell, overloading)

    def _coil_rows_flipped(self, r: int) -> int:
        """Mapeia a linha do pixel-map para a linha desenhada (flip do gêmeo base)."""
        return r if self.is_top else (PIXEL_ROWS - 1 - r)

    def _draw_glows(self, surface: pygame.Surface, cell: int, overloading: bool) -> None:
        pulse = 0.5 + 0.5 * math.sin(self.pulse * 5.0)

        # Núcleo azul (vermelho no overload).
        core_col = _OVERLOAD if overloading else pal.lerp(CORE_NEON_DIM, CORE_NEON, pulse)
        core_r = int(cell * (1.3 + pulse))
        for c, r in CORE_CELLS:
            rr = self._coil_rows_flipped(r)
            gx = int(self.x + (c + 0.5) * cell)
            gy = int(self.y + (rr + 0.5) * cell)
            self._blit_glow(surface, gx, gy, core_r, core_col)

        # Bobina de cobre crepitando (mais intensa quando o feixe está ativo).
        link = self.link
        active = link is not None and link.beam_active()
        flick = 0.5 + 0.5 * math.sin(self.pulse * 18.0)
        coil_col = _OVERLOAD if overloading else pal.lerp(
            pal.TOXIC_ORANGE_DIM, COIL_NEON, 0.4 + 0.6 * (flick if active else 0.3)
        )
        coil_r = int(cell * (1.0 + 0.5 * flick))
        for c, r in COIL_CELLS:
            rr = self._coil_rows_flipped(r)
            gx = int(self.x + (c + 0.5) * cell)
            gy = int(self.y + (rr + 0.5) * cell)
            self._blit_glow(surface, gx, gy, coil_r, coil_col)

    def _draw_beam(
        self,
        surface: pygame.Surface,
        a: Tuple[float, float],
        b: Tuple[float, float],
    ) -> None:
        """Arco vertical crepitante entre os dois emissores (jitter por segmento)."""
        ax, ay = int(a[0]), int(a[1])
        bx, by = int(b[0]), int(b[1])
        segs = 10
        flick = 0.5 + 0.5 * math.sin(self.pulse * 26.0)
        amp = 4.0 + 5.0 * flick
        prev = (ax, ay)
        for k in range(1, segs + 1):
            t = k / segs
            mx = ax + (bx - ax) * t
            my = ay + (by - ay) * t
            if k < segs:
                mx += random.uniform(-amp, amp)
            pygame.draw.line(surface, _BEAM, prev, (int(mx), int(my)), 3)
            pygame.draw.line(surface, _BEAM_HOT, prev, (int(mx), int(my)), 1)
            prev = (int(mx), int(my))
        # Glow nos emissores.
        self._blit_glow(surface, ax, ay, int(self.cell * 2.4), _BEAM)
        self._blit_glow(surface, bx, by, int(self.cell * 2.4), _BEAM)
