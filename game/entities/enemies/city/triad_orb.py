"""Esferas de energia da Tríade — o vocabulário de ataque inteiro do chefe.

**Uma classe, seis comportamentos.** O boss não tem seis projéteis: tem UM, com
um `behavior` que troca só a função de movimento. É o que mantém a leitura do
encontro coesa — o jogador aprende "esfera de energia" uma vez, e depois aprende
*como cada uma se move*, que é informação nova de verdade.

Despacho por atributo, nunca por cascata de `isinstance` (§5): o construtor liga
`self._move` à função do comportamento e o `update_in_context` só a chama.
Comportamento novo = uma função e uma entrada no mapa.

## A assinatura visual

Núcleo brilhante com pequenos raios circulando — a esfera parece *energizada*.
Uma rotina de desenho só, e a DENSIDADE dos raios comunica o comportamento:
âncora crepita denso e parado, seeker arrasta os raios para trás, tether joga o
arco para o par. O efeito é estético, como pedido no conceito, mas carrega
informação de graça.

## Onde elas vivem

Em `em.enemies`, via `BossUpdateResult.spawned_enemies` — mesmo caminho dos
projéteis do Metropolis Overlord (`metropolis_projectiles`). Isso lhes dá de
graça colisão com a nave, grade espacial, limpeza de fim de fase e — de
propósito — **serem destrutíveis a tiro**. A Convergência da Fase 3 recompensa
quem limpou as âncoras, então a esfera precisa ser um alvo.
"""

from __future__ import annotations

import math
import random
from enum import Enum, auto
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

import pygame

from ....core.config import config as Config
from ....core.scale import gameplay_scale, scaled
from ....core.visual_quality import visual_quality as vq
from .._shared.enemy_hit_mixin import EnemyHitMixin
from . import triad_pixel_map as pmap

if TYPE_CHECKING:
    from ....systems.entity_context import EnemyUpdateContext
    from ....systems.hit_result import HitResult


class OrbBehavior(Enum):
    """Como a esfera se move. A aparência é a mesma; o movimento é o conteúdo."""

    SEEKER = auto()  # curva fraca por um tempo, depois segue reto
    LOB = auto()  # arco para cima e queda irregular
    ERRATIC = auto()  # senoide + correções em espasmos ("míssil burro")
    ANCHOR = auto()  # parada, crepita, expira — negação de espaço
    TETHER = auto()  # par ligado por arco elétrico (o arco é o hitbox)
    RING = auto()  # radial, velocidade constante


# ── Tuning por comportamento (px/s no design base 1280×720) ───────────────────
_SEEKER_SPEED = 190.0
_SEEKER_TURN_RATE = 1.15  # rad/s — angular, NÃO escala com resolução
_SEEKER_HOMING_TIME = 1.2  # depois disso desiste e segue reto

_LOB_RISE = -300.0
_LOB_GRAVITY = 430.0
_LOB_DRIFT = 55.0

_ERRATIC_SPEED = 135.0
_ERRATIC_CORRECTION_INTERVAL = 0.5
_ERRATIC_TURN_STEP = 0.42  # rad por espasmo
_ERRATIC_WOBBLE_FREQ = 5.5
_ERRATIC_WOBBLE_AMP = 62.0

_ANCHOR_LIFETIME = 6.0
_ANCHOR_FADE = 0.7  # últimos segundos: pisca avisando que vai sumir

_RING_SPEED = 165.0

_TETHER_SAMPLES = 5  # círculos de colisão distribuídos ao longo do arco


class TriadOrb(EnemyHitMixin):
    """Uma esfera de energia. O `behavior` decide só como ela anda."""

    is_boss: bool = False
    HEALTH: int = 4
    POINTS: int = 0
    RADIUS: float = 9.0
    ANCHOR_RADIUS: float = 11.0

    def __init__(
        self,
        x: float,
        y: float,
        behavior: OrbBehavior,
        *,
        angle: float = 0.0,
        speed: float | None = None,
        lifetime: float = 8.0,
        color: Tuple[int, int, int] = pmap.CYAN,
        target: Optional[Tuple[float, float]] = None,
    ) -> None:
        sc = gameplay_scale()
        self.behavior = behavior
        self.x = float(x)
        self.y = float(y)
        self.color = color
        self.health = self.HEALTH
        self.dead = False
        self.anim = 0.0  # acumulador do draw, alimentado pelo update (§3)

        base_radius = self.ANCHOR_RADIUS if behavior is OrbBehavior.ANCHOR else self.RADIUS
        self.radius = base_radius * sc

        self.angle = angle
        self.speed = (speed if speed is not None else self._default_speed()) * sc
        self.vx = math.cos(angle) * self.speed
        self.vy = math.sin(angle) * self.speed
        self.lifetime = _ANCHOR_LIFETIME if behavior is OrbBehavior.ANCHOR else lifetime

        # Estado específico de comportamento. Mora aqui (e não numa subclasse)
        # porque a esfera é UMA entidade: subclassear por movimento traria de
        # volta a cascata de tipo que o §5 proíbe.
        self._homing_left = _SEEKER_HOMING_TIME
        self._correction_timer = 0.0
        self._wobble_phase = random.uniform(0.0, math.tau)
        self._birth = 0.0
        self.target = target
        self.partner: "TriadOrb | None" = None
        self._is_tether_master = False

        self._rect = pygame.Rect(0, 0, int(self.radius * 2), int(self.radius * 2))
        self._sync_rect()

        # Despacho por atributo (§5): a função de movimento é escolhida UMA vez.
        self._move: Callable[["TriadOrb", float, "EnemyUpdateContext"], None] = _MOVERS[
            behavior
        ]

    def _default_speed(self) -> float:
        return {
            OrbBehavior.SEEKER: _SEEKER_SPEED,
            OrbBehavior.LOB: 0.0,
            OrbBehavior.ERRATIC: _ERRATIC_SPEED,
            OrbBehavior.ANCHOR: 0.0,
            OrbBehavior.TETHER: 0.0,
            OrbBehavior.RING: _RING_SPEED,
        }[self.behavior]

    # ── Par do TETHER ────────────────────────────────────────────────────────
    @classmethod
    def link_pair(cls, a: "TriadOrb", b: "TriadOrb") -> None:
        """Liga duas esferas pelo arco. Só UMA das duas carrega o hitbox do arco.

        Sem o `master`, os círculos do arco existiriam em dobro e o segmento
        cobraria dano duas vezes no mesmo frame.
        """
        a.partner, b.partner = b, a
        a._is_tether_master = True
        b._is_tether_master = False

    # ── Contrato de entidade ─────────────────────────────────────────────────
    def _sync_rect(self) -> None:
        if self.behavior is OrbBehavior.TETHER and self._is_tether_master and self.partner:
            # O rect precisa cobrir o ARCO inteiro: é o pré-filtro AABB de quem
            # colide com o segmento, não só com as duas pontas.
            p = self.partner
            left, right = min(self.x, p.x), max(self.x, p.x)
            top, bottom = min(self.y, p.y), max(self.y, p.y)
            r = int(self.radius)
            self._rect.update(
                int(left) - r, int(top) - r,
                int(right - left) + r * 2, int(bottom - top) + r * 2,
            )
            return
        self._rect.update(
            int(self.x - self.radius), int(self.y - self.radius),
            int(self.radius * 2), int(self.radius * 2),
        )

    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    @property
    def causes_damage(self) -> bool:
        return True

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x, self.y, self.radius

    def collision_circles(self) -> List[tuple[float, float, float]]:
        """Silhueta real (§8). No TETHER, **o arco é o hitbox** — não as pontas.

        É o que transforma dois projéteis numa LINHA móvel: o melhor retorno de
        complexidade por projétil no kit do chefe.
        """
        if not (self.behavior is OrbBehavior.TETHER and self._is_tether_master):
            return [(self.x, self.y, self.radius)]
        p = self.partner
        if p is None or p.dead:
            return [(self.x, self.y, self.radius)]
        circles: List[tuple[float, float, float]] = []
        r = self.radius * 0.75
        for i in range(_TETHER_SAMPLES + 1):
            t = i / _TETHER_SAMPLES
            circles.append((self.x + (p.x - self.x) * t, self.y + (p.y - self.y) * t, r))
        return circles

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

    # ── Tick ─────────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        self.anim += dt
        self._birth += dt
        self.lifetime -= dt
        if self.lifetime <= 0.0:
            self.dead = True
            return

        self._move(self, dt, ctx)
        self._sync_rect()

        # Fora da tela com folga: some. A âncora é a exceção — ela nasce dentro
        # da arena e some por tempo, não por posição.
        if self.behavior is not OrbBehavior.ANCHOR:
            margin = scaled(90.0)
            if (
                self.x < -margin
                or self.x > Config.SCREEN_WIDTH + margin
                or self.y > Config.SCREEN_HEIGHT + margin
                or self.y < -Config.SCREEN_HEIGHT
            ):
                self.dead = True

    # ── Render ───────────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        """Núcleo + raios circulando. `draw` não muta estado (§3).

        O `random` aqui é crepitar puramente cosmético — mesmo padrão já aceito
        nos drones da CITY. Posição e vida avançam só no `update`.
        """
        alpha_scale = 1.0
        if self.behavior is OrbBehavior.ANCHOR and self.lifetime < _ANCHOR_FADE:
            # Pisca no fim: a âncora some, e sumir sem aviso é armadilha.
            alpha_scale = 0.35 + 0.65 * abs(math.sin(self.anim * 18.0))

        if self.behavior is OrbBehavior.TETHER and self._is_tether_master and self.partner:
            self._draw_link(surface)

        cx, cy = int(self.x), int(self.y)
        r = int(self.radius)
        core = self.color
        bright = (
            min(255, core[0] + 90), min(255, core[1] + 60), min(255, core[2] + 40)
        )

        halo = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
        pygame.draw.circle(halo, (*core, int(70 * alpha_scale)), (r * 2, r * 2), r * 2)
        pygame.draw.circle(halo, (*core, int(150 * alpha_scale)), (r * 2, r * 2), r)
        pygame.draw.circle(
            halo, (*bright, int(235 * alpha_scale)), (r * 2, r * 2), max(1, r // 2)
        )
        surface.blit(halo, (cx - r * 2, cy - r * 2))

        self._draw_arcs(surface, cx, cy, r, bright, alpha_scale)

    def _draw_arcs(
        self,
        surface: pygame.Surface,
        cx: int,
        cy: int,
        r: int,
        bright: Tuple[int, int, int],
        alpha_scale: float,
    ) -> None:
        """Os pequenos raios em volta. A DENSIDADE identifica o comportamento."""
        count = vq.particles(_ARC_COUNT.get(self.behavior, 4))
        if count <= 0:
            return
        # Âncora crepita parada e densa; seeker arrasta os raios para trás.
        drift = 0.0
        if self.behavior in (OrbBehavior.SEEKER, OrbBehavior.RING, OrbBehavior.ERRATIC):
            drift = math.atan2(self.vy, self.vx) + math.pi
        spin = self.anim * 3.4
        for i in range(count):
            base = spin + i * (math.tau / count)
            if drift:
                base = drift + math.sin(self.anim * 6.0 + i) * 0.9
            inner = r * 0.85
            outer = r * (1.45 + random.random() * 0.55)
            mid_a = base + random.uniform(-0.35, 0.35)
            pts = [
                (cx + math.cos(base) * inner, cy + math.sin(base) * inner),
                (
                    cx + math.cos(mid_a) * (inner + outer) * 0.5,
                    cy + math.sin(mid_a) * (inner + outer) * 0.5,
                ),
                (cx + math.cos(base) * outer, cy + math.sin(base) * outer),
            ]
            pygame.draw.lines(surface, bright, False, pts, 1)
        if alpha_scale < 1.0:
            return

    def _draw_link(self, surface: pygame.Surface) -> None:
        """Arco elétrico entre o par — é ele que causa dano, então tem que LER."""
        p = self.partner
        if p is None or p.dead:
            return
        segments = 7
        pts: List[Tuple[float, float]] = []
        dx, dy = p.x - self.x, p.y - self.y
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        for i in range(segments + 1):
            t = i / segments
            jitter = 0.0 if i in (0, segments) else random.uniform(-1.0, 1.0) * self.radius
            pts.append((self.x + dx * t + nx * jitter, self.y + dy * t + ny * jitter))
        bright = (min(255, self.color[0] + 90), min(255, self.color[1] + 60), min(255, self.color[2] + 40))
        pygame.draw.lines(surface, self.color, False, pts, max(2, int(self.radius * 0.5)))
        pygame.draw.lines(surface, bright, False, pts, 1)


# ── Movimentos ────────────────────────────────────────────────────────────────
# Funções livres, e não métodos, para o mapa `_MOVERS` ser a fonte única do
# despacho: comportamento novo entra aqui e em `OrbBehavior`, sem tocar na classe.


def _move_seeker(orb: TriadOrb, dt: float, ctx: "EnemyUpdateContext") -> None:
    """Curva fraca por `_SEEKER_HOMING_TIME`, depois desiste e segue reto.

    Desistir é o que a torna justa: teleguiado eterno não tem esquiva, só
    atrito. Com prazo, o jogador aprende que basta sobreviver à curva.
    """
    if orb._homing_left > 0.0:
        orb._homing_left -= dt
        desired = math.atan2(ctx.player_y - orb.y, ctx.player_x - orb.x)
        diff = (desired - orb.angle + math.pi) % math.tau - math.pi
        step = _SEEKER_TURN_RATE * dt
        orb.angle += max(-step, min(step, diff))
        orb.vx = math.cos(orb.angle) * orb.speed
        orb.vy = math.sin(orb.angle) * orb.speed
    orb.x += orb.vx * dt
    orb.y += orb.vy * dt


def _move_lob(orb: TriadOrb, dt: float, _ctx: "EnemyUpdateContext") -> None:
    """Sobe, perde força e cai. A queda é irregular — deriva lateral própria."""
    orb.vy += _LOB_GRAVITY * gameplay_scale() * dt
    orb.x += orb.vx * dt
    orb.y += orb.vy * dt


def _move_erratic(orb: TriadOrb, dt: float, ctx: "EnemyUpdateContext") -> None:
    """Míssil BURRO: deriva senoidal + correção em espasmos discretos.

    A correção acontece em passos de `_ERRATIC_TURN_STEP` a cada meio segundo,
    não continuamente — é o que faz ele parecer errático em vez de teleguiado.
    """
    orb._correction_timer -= dt
    if orb._correction_timer <= 0.0:
        orb._correction_timer = _ERRATIC_CORRECTION_INTERVAL
        desired = math.atan2(ctx.player_y - orb.y, ctx.player_x - orb.x)
        diff = (desired - orb.angle + math.pi) % math.tau - math.pi
        orb.angle += max(-_ERRATIC_TURN_STEP, min(_ERRATIC_TURN_STEP, diff))
    orb._wobble_phase += _ERRATIC_WOBBLE_FREQ * dt
    wobble = math.sin(orb._wobble_phase) * _ERRATIC_WOBBLE_AMP * gameplay_scale()
    nx, ny = -math.sin(orb.angle), math.cos(orb.angle)
    orb.x += (math.cos(orb.angle) * orb.speed + nx * wobble) * dt
    orb.y += (math.sin(orb.angle) * orb.speed + ny * wobble) * dt


def _move_anchor(_orb: TriadOrb, _dt: float, _ctx: "EnemyUpdateContext") -> None:
    """Não anda. Só ocupa espaço — e é esse o ataque.

    A âncora é a melhor ferramenta de dificuldade sem volume do chefe: ela torna
    todo o resto mais difícil sem colocar um projétil em movimento a mais.
    """
    return


def _move_tether(orb: TriadOrb, dt: float, _ctx: "EnemyUpdateContext") -> None:
    """As duas pontas seguem reto; a distância entre elas respira.

    O par morre junto: um arco com uma ponta só não é nada, e deixar a órfã viva
    daria um projétil invisível (o hitbox mora no arco).
    """
    p = orb.partner
    if p is not None and p.dead:
        orb.dead = True
        return
    orb.x += orb.vx * dt
    orb.y += orb.vy * dt


def _move_ring(orb: TriadOrb, dt: float, _ctx: "EnemyUpdateContext") -> None:
    """Radial, velocidade constante. Leitura puramente posicional."""
    orb.x += orb.vx * dt
    orb.y += orb.vy * dt


_MOVERS: Dict[OrbBehavior, Callable[[TriadOrb, float, "EnemyUpdateContext"], None]] = {
    OrbBehavior.SEEKER: _move_seeker,
    OrbBehavior.LOB: _move_lob,
    OrbBehavior.ERRATIC: _move_erratic,
    OrbBehavior.ANCHOR: _move_anchor,
    OrbBehavior.TETHER: _move_tether,
    OrbBehavior.RING: _move_ring,
}

# Quantidade de raios por comportamento — a densidade é o "sotaque" de cada um.
_ARC_COUNT: Dict[OrbBehavior, int] = {
    OrbBehavior.SEEKER: 4,
    OrbBehavior.LOB: 3,
    OrbBehavior.ERRATIC: 5,
    OrbBehavior.ANCHOR: 8,  # crepita denso e parado: "não chegue perto"
    OrbBehavior.TETHER: 3,
    OrbBehavior.RING: 3,
}


def make_lob(x: float, y: float, drift_dir: float, color: Tuple[int, int, int]) -> TriadOrb:
    """Esfera lançada para cima, que volta em queda irregular."""
    sc = gameplay_scale()
    orb = TriadOrb(x, y, OrbBehavior.LOB, color=color, lifetime=9.0)
    orb.vx = drift_dir * random.uniform(0.4, 1.0) * _LOB_DRIFT * sc
    orb.vy = _LOB_RISE * random.uniform(0.85, 1.15) * sc
    return orb
