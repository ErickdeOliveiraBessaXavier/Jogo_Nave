"""Segmentos do Metropolis Overlord — Fase 3 (SEGMENTAÇÃO final).

Ao perder a estrutura, o Overlord NÃO morre: a mesma inteligência sobrevive em três
FRAGMENTOS VIVOS, cada um guardando um dos núcleos de plasma. Não são inimigos novos
— são o último estágio evolutivo do boss, herdando sua identidade visual (núcleo de
plasma + fluxos de energia + borda neon viva + estética tecno-alienígena) e atacando
de forma COORDENADA, como partes de uma única mente central.

Coordenação (`SegmentNetwork`): os três orbitam um ponto invisível em sincronia
(120° apart, raio respirando junto) e disparam em ONDA defasada (volley coordenada)
a cada ciclo, com breves momentos de REORGANIZAÇÃO em grupo (sem volley) — pressão
ritmada e legível, nunca caótica.

Ataques: reaproveitam a linguagem já construída (projéteis das sentinelas) em versões
MENORES/menos opressoras — pequenos drones/feixes (`EnergyDrone`) e triângulos
energéticos com leve perseguição (`TriShard`). Roteados via `ctx.new_enemies`.
`draw` sem efeitos colaterais (§3): mutação só no `update`.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List

import pygame

from ...core.config import config as Config
from ..enemy_hit_mixin import EnemyHitMixin
from . import metropolis_overlord_pixel_map as pmap
from .city_thruster import EnergyThruster
from .metropolis_projectiles import EnergyDrone, TriShard

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult

_WHITE = (255, 255, 255)
_TAU = 2.0 * math.pi


def _jagged(x1: float, y1: float, x2: float, y2: float, jitter: float, segs: int = 3):
    """Polilinha em ziguezague (descarga elétrica). Para `draw` puro (§3)."""
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    pts = [(x1, y1)]
    for i in range(1, segs):
        t = i / segs
        off = random.uniform(-jitter, jitter)
        pts.append((x1 + dx * t + nx * off, y1 + dy * t + ny * off))
    pts.append((x2, y2))
    return pts


def _lerp(a: tuple, b: tuple, f: float) -> tuple:
    return (
        int(a[0] + (b[0] - a[0]) * f),
        int(a[1] + (b[1] - a[1]) * f),
        int(a[2] + (b[2] - a[2]) * f),
    )


class SegmentNetwork:
    """Inteligência central RESIDUAL: coordena os 3 fragmentos como uma só mente.

    Um relógio compartilhado (avançado 1×/frame pelo boss-coordenador) ritma:
      • respiração de raio sincronizada (movimentos pequenos em grupo);
      • volley em ONDA a cada `CYCLE` (cada fragmento dispara defasado por `STAGGER`,
        em ordem — ataques complementares lendo como um pulso único);
      • REORGANIZAÇÃO em grupo a cada `REORG_EVERY` ciclos (sem volley: o grupo
        contrai/expande o anel e respira) — breve janela de descanso, não caos.

    Contrato explícito (§1): o segmento só lê `cycle/fire_phase/is_reorg/radius_scale`
    e nunca toca no estado das irmãs.
    """

    CYCLE = 2.6        # intervalo entre volleys coordenadas (s)
    STAGGER = 0.2      # defasagem da onda entre fragmentos (s)
    REORG_EVERY = 4    # a cada N ciclos, um ciclo de reorganização (sem volley)

    def __init__(self) -> None:
        self.clock = 0.0
        self.cycle = 0
        self._t = 0.0

    def update(self, dt: float) -> None:
        self.clock += dt
        self._t += dt
        if self._t >= self.CYCLE:
            self._t -= self.CYCLE
            self.cycle += 1

    @property
    def is_reorg(self) -> bool:
        return self.cycle > 0 and self.cycle % self.REORG_EVERY == 0

    def fire_phase(self) -> float:
        return self._t

    def radius_scale(self) -> float:
        """Modulação SINCRONIZADA do raio de órbita (todos leem o mesmo valor)."""
        s = 1.0 + 0.05 * math.sin(self.clock * 1.3)  # respiração sutil contínua
        if self.is_reorg and self._t < 1.1:
            s *= 1.0 - 0.18 * math.sin((self._t / 1.1) * math.pi)  # contrai e volta
        return s


class MetropolisSegment(EnemyHitMixin):
    """Fragmento vivo do Overlord (um núcleo de plasma), coordenado pela rede residual."""

    is_boss: bool = False
    POINTS = 400
    ORBIT_SPEED = 0.55  # rad/s ao redor do ponto invisível (suave/coordenado)
    ENTRY_TIME = 0.6    # ease da posição de split até o anel de órbita
    COLLISION_RADIUS = 40.0
    _THRUSTER_Y = 32.0  # offset da base (de onde sai o propulsor)

    _explosion_size_killed = 60
    _explosion_size_hit = 12

    # Fallback (sem rede): intervalo de disparo por papel (s).
    _FIRE_INTERVAL = {"drone": 2.4, "shard": 2.2, "pulse": 2.8}

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
        index: int = 0,
        network: "SegmentNetwork | None" = None,
    ) -> None:
        self.theme = theme
        self.role = role
        self.center = center
        self.base_angle = base_angle
        self.orbit_radius = orbit_radius
        self._aggr = max(0.5, aggressiveness_multiplier)
        self._index = index
        self._net = network

        # Paleta do PRÓPRIO núcleo (dark, mid, bright) — toda a silhueta herda a cor
        # do plasma: o fragmento parece um pedaço vivo da mesma entidade.
        self._dark, self._mid, self._bright = pmap.PLASMA_THEMES.get(
            theme, pmap.PLASMA_THEMES["cyan"]
        )

        self.health = max(1, health)
        self.max_health = self.health
        self.dead = False
        self.hit_timer = 0.0
        self.anim_time = 0.0
        self._phase = base_angle  # fase de plasma única por fragmento
        self._fire_flash = 0.0    # brilho ao disparar (feedback)

        # Thruster herdado do Overlord (proporção menor): o fragmento também é uma
        # entidade energética suspensa, com propulsão azul/ciano na base.
        self._thruster = EnergyThruster(scale=0.42)
        self._thruster_intensity = 0.0

        self._orbit_angle = base_angle
        self._entry_t = self.ENTRY_TIME
        self._start_x, self._start_y = start_pos
        self.x, self.y = start_pos

        self._last_cycle = -1  # último ciclo de volley em que ESTE fragmento atirou
        self._fire_timer = self._FIRE_INTERVAL.get(role, 2.4) / self._aggr
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
        if self._fire_flash > 0.0:
            self._fire_flash = max(0.0, self._fire_flash - dt)

        # Órbita SINCRONIZADA: mesmo centro/velocidade, raio respira em grupo (rede).
        self._orbit_angle += self.ORBIT_SPEED * dt
        rscale = self._net.radius_scale() if self._net is not None else 1.0
        radius = self.orbit_radius * rscale
        ox = self.center[0] + math.cos(self._orbit_angle) * radius
        oy = self.center[1] + math.sin(self._orbit_angle) * radius
        if self._entry_t > 0.0:
            self._entry_t = max(0.0, self._entry_t - dt)
            k = 1.0 - (self._entry_t / self.ENTRY_TIME)
            self.x = self._start_x + (ox - self._start_x) * k
            self.y = self._start_y + (oy - self._start_y) * k
        else:
            self.x, self.y = ox, oy
        self._sync_rect()

        self._update_fire(dt, ctx)

        # Thruster (escala menor): intensidade base baixa + pulso sutil + reforço ao
        # disparar. Emite da base do fragmento e acompanha sua órbita.
        inten = min(1.0, 0.26 + 0.12 * math.sin(self.anim_time * 5.0) + 0.4 * (self._fire_flash / 0.3))
        self._thruster_intensity = inten
        self._thruster.update(dt, self.x, self.y + self._THRUSTER_Y, inten)

    def _update_fire(self, dt: float, ctx: "EnemyUpdateContext") -> None:
        """Disparo COORDENADO em onda via rede (defasado por índice); fallback por
        timer independente quando não há rede (testes)."""
        net = self._net
        if net is not None:
            if (
                not net.is_reorg
                and net.cycle != self._last_cycle
                and net.fire_phase() >= self._index * net.STAGGER
            ):
                self._last_cycle = net.cycle
                self._fire_flash = 0.3
                ctx.new_enemies.extend(self._fire(ctx.player_x, ctx.player_y))
            return
        self._fire_timer -= dt
        if self._fire_timer <= 0.0:
            self._fire_timer = self._FIRE_INTERVAL.get(self.role, 2.4) / self._aggr
            self._fire_flash = 0.3
            ctx.new_enemies.extend(self._fire(ctx.player_x, ctx.player_y))

    def _fire(self, px: float, py: float) -> List[object]:
        """Ataques MENORES reaproveitando a linguagem visual nova. Complementares
        entre os papéis → a volley coordenada lê como um pulso único."""
        if self.role == "drone":  # pequeno feixe/drone preciso
            return [EnergyDrone(self.x, self.y, px, py)]
        if self.role == "shard":  # triângulo energético com leve perseguição
            return [TriShard(self.x, self.y, px, py)]
        if self.role == "pulse":  # pequeno pulso: leque curto de drones (descarga)
            out: List[object] = []
            base = math.atan2(py - self.y, px - self.x)
            for s in (-0.26, 0.26):
                a = base + s
                out.append(EnergyDrone(self.x, self.y, self.x + math.cos(a) * 100.0, self.y + math.sin(a) * 100.0))
            return out
        return []

    # ── Render (§3) ───────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x), int(self.y)
        t = self.anim_time
        hit = self.hit_timer > 0.0
        boost = self._fire_flash / 0.3  # 1→0 logo após disparar

        # Thruster ATRÁS do fragmento (flare + partículas na base).
        self._thruster.draw(surface, self.x, self.y + self._THRUSTER_Y, self._thruster_intensity)

        # Silhueta com respiração sutil de tamanho (vivo, não rígido).
        s = 1.0 + 0.04 * math.sin(t * 3.0) + 0.05 * boost
        up, dn, hw = int(48 * s), int(32 * s), int(46 * s)
        apex = (cx, cy - up)
        bl = (cx - hw, cy + dn)
        br = (cx + hw, cy + dn)
        pts = [apex, bl, br]

        # 1) Base de energia (NÃO chapada): escuro do tema com leve tinta migrando.
        m = 0.5 + 0.5 * math.sin(t * 0.6 + self._phase)
        base = _lerp(self._dark, self._mid, 0.12 + 0.10 * m)
        pygame.draw.polygon(surface, base, pts)

        # 2) Veias de energia do núcleo → vértices (fluxo interno) + nós correndo.
        for k, vtx in enumerate(pts):
            vg = 0.5 + 0.5 * math.sin(t * 4.0 + k * 2.1)
            pygame.draw.line(surface, _lerp(self._dark, self._bright, 0.35 + 0.4 * vg), (cx, cy), vtx, 1)
            frac = (t * 0.7 + k / 3.0) % 1.0  # nó de energia escorrendo p/ fora
            nx = int(cx + (vtx[0] - cx) * frac)
            ny = int(cy + (vtx[1] - cy) * frac)
            pygame.draw.circle(surface, self._bright, (nx, ny), 2)

        # 3) Pequena descarga elétrica interna ocasional (crepitar — §3).
        if random.random() < 0.18 + 0.5 * boost:
            ang = random.uniform(0.0, _TAU)
            ex = cx + math.cos(ang) * hw * 0.7
            ey = cy + math.sin(ang) * (up * 0.6)
            arc = _jagged(cx, cy, ex, ey, jitter=4.0, segs=3)
            pygame.draw.lines(surface, self._bright, False, [(int(ax), int(ay)) for ax, ay in arc], 1)

        # 4) Núcleo de plasma — o foco (mesma linguagem das Fases 1/2).
        intensity = 1.05 + 0.15 * (0.5 + 0.5 * math.sin(t * 4.0)) + 0.25 * boost
        pmap.draw_plasma_sphere(surface, cx, cy, 26.0, self.theme, self._phase, intensity, t)

        # 5) Borda neon VIVA: corrente pulsando + nó branco-quente circulando o perímetro.
        self._draw_living_edge(surface, pts, t, hit, boost)

        # 6) Barra de vida do fragmento (cor do tema).
        bw = 72
        bx = cx - bw // 2
        by = max(2, min(Config.SCREEN_HEIGHT - 7, cy - up - 12))
        pygame.draw.rect(surface, (30, 30, 30), (bx, by, bw, 5))
        frac = max(0.0, self.health / self.max_health)
        pygame.draw.rect(surface, self._bright, (bx, by, int(bw * frac), 5))

    def _draw_living_edge(self, surface: pygame.Surface, pts: list, t: float, hit: bool, boost: float) -> None:
        """Contorno energizado: cor pulsando (corrente) + um nó branco-quente que
        VIAJA pelo perímetro do triângulo (energia circulando o fragmento)."""
        glow = 0.55 + 0.45 * math.sin(t * 3.5 + self._phase)
        edge = _WHITE if hit else _lerp(self._mid, self._bright, min(1.0, glow + 0.4 * boost))
        pygame.draw.polygon(surface, edge, pts, 3)
        # Nó viajando: parametriza o perímetro (apex→bl→br→apex).
        perim = ((pts[0], pts[1]), (pts[1], pts[2]), (pts[2], pts[0]))
        pos = (t * 0.22) % 3.0
        i = int(pos)
        f = pos - i
        a, b = perim[i]
        nx = int(a[0] + (b[0] - a[0]) * f)
        ny = int(a[1] + (b[1] - a[1]) * f)
        pygame.draw.circle(surface, self._bright, (nx, ny), 4)
        pygame.draw.circle(surface, _WHITE, (nx, ny), 2)
