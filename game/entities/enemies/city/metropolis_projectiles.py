"""Projéteis do tema CITY usados pelo Metropolis Overlord e seus satélites.

Dois conjuntos coexistem aqui:

**Conjunto clássico** (compartilhado por `metropolis_drone` e `metropolis_segment`
— NÃO alterar sem revisar aqueles inimigos):

  NeonBurstShot   — Rajada reta de neon, rápida, mirada na pose do disparo.
  MicroMissile    — Míssil seguidor com **turn-rate limitado** (desviável) e vida curta.
  VerticalLaser   — Feixe vertical que telegrafa e cai cruzando a coluna. Indestrutível.
  EMPPulse        — Pulso EMP em anel com dano de contato.

**Conjunto das Sentinelas Orbitais** (`MetropolisSentinel`, identidade Cidade Neon
— formas geométricas + energia/eletricidade, com ciclo visual completo
disparo→persistência→dissipação). Um por papel, com personalidade própria:

  EnergyDrone     — Papel PRESSÃO DIRETA. Drone/fragmento energético geométrico
                    (pipa com ponta frontal), grande, com surgimento, rotação e
                    rastro. Disparado em trio preciso.
  LightningStrike — Papel DESCARGA ATMOSFÉRICA (sentinela amarela/âmbar). Raio
                    massivo do topo com coluna translúcida de antecipação que
                    alarga até a área de dano; ramificações só visuais.
  TriShard        — (legado) Estilhaço triangular geométrico em leque. Não usado
                    pelas sentinelas atuais; mantido para reuso eventual.
  ElectricPulse   — Papel CONTROLE DE ESPAÇO. Sobrecarga elétrica que nasce (rede
                    sendo montada), estabiliza (instável/viva) e colapsa (implode),
                    num ponto travado; nasce no início da mira (mira = hitbox).
  GridSnare       — Papel SUPORTE. Grade holográfica energizada que materializa no
                    ponto travado, eletrifica por um instante (controle de área) e dissipa.

Todos aderem ao contrato de "inimigo comum" do EntityManager: vivem em
`em.enemies` (roteados via `ctx.new_enemies` pela sentinela), implementam
`update_in_context`, `rect`, `collision_circle`, `on_hit`/`causes_damage` e
`draw` sem efeitos colaterais (§3). Assim ganham colisão/desenho/cleanup de graça,
sem nova plumbing no EntityManager.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import pygame

from ....core.config import config as Config
from ....core.scale import gameplay_scale, scaled
from ....core.visual_quality import visual_quality as vq
from .._shared.enemy_hit_mixin import EnemyHitMixin

if TYPE_CHECKING:
    from ....core.events import EventBus
    from ....systems.entity_context import EnemyUpdateContext
    from ....systems.hit_result import HitResult

# Paleta neon da Cidade (magenta/azul-elétrico) — coerente com o Overlord.
_NEON_MAGENTA = (255, 70, 200)
_NEON_BLUE = (90, 200, 255)
_NEON_WHITE = (255, 255, 255)
_NEON_AMBER = (255, 190, 80)


def _off_screen(x: float, y: float, margin: float = 60.0) -> bool:
    # Margem de culling escala com a resolução (§12): em telas grandes os projéteis
    # são maiores, então não devem sumir cedo demais (glow cortado na borda).
    m = margin * gameplay_scale()
    return (
        x < -m
        or x > Config.SCREEN_WIDTH + m
        or y < -m
        or y > Config.SCREEN_HEIGHT + m
    )


class _CityProjectile(EnemyHitMixin):
    """Base enxuta dos projéteis das sentinelas (estado + colisão padrão)."""

    is_boss: bool = False
    HEALTH: int = 6
    POINTS: int = 0
    RADIUS: float = 7.0

    # Constantes de TAMANHO/VELOCIDADE (px do design base 1280×720) escaladas para a
    # resolução atual no __init__ (§12, FONTE ÚNICA em core.scale). Cada subclasse
    # declara as suas; o valor vira atributo de instância que SOMBREIA a constante de
    # classe, então todo `self.X` passa a usar o valor escalado sem tocar draw/colisão.
    _SCALE_ATTRS: tuple[str, ...] = ("RADIUS",)

    def __init__(self, x: float, y: float) -> None:
        sc = gameplay_scale()
        for _name in self._SCALE_ATTRS:
            setattr(self, _name, getattr(self, _name) * sc)
        self.x = float(x)
        self.y = float(y)
        self.health = self.HEALTH
        self.dead = False
        self.lifetime = 8.0
        self.anim = 0.0  # acumulador p/ draw animado (§3: alimentado pelo update)
        self._rect = pygame.Rect(0, 0, int(self.RADIUS * 2), int(self.RADIUS * 2))
        self._sync_rect()

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
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ....systems import hit_sounds
        from ....systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead


class NeonBurstShot(_CityProjectile):
    """Rajada reta de neon: mira fixa no alvo do disparo, voa em linha."""

    HEALTH = 4
    RADIUS = 6.0
    SPEED = 460.0
    _SCALE_ATTRS = ("RADIUS", "SPEED")

    def __init__(self, x: float, y: float, target_x: float, target_y: float) -> None:
        super().__init__(x, y)
        ang = math.atan2(target_y - y, target_x - x)
        self.vx = math.cos(ang) * self.SPEED
        self.vy = math.sin(ang) * self.SPEED
        self.lifetime = 4.0

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.lifetime -= dt
        self._sync_rect()
        if self.lifetime <= 0 or _off_screen(self.x, self.y):
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x), int(self.y)
        pygame.draw.circle(surface, _NEON_MAGENTA, (cx, cy), int(self.RADIUS))
        pygame.draw.circle(surface, _NEON_WHITE, (cx, cy), int(self.RADIUS * 0.45))


class MicroMissile(_CityProjectile):
    """Míssil seguidor com turn-rate limitado (justo de desviar) e vida curta."""

    HEALTH = 5
    RADIUS = 7.0
    SPEED = 300.0
    MAX_TURN_RATE = 2.6  # rad/s — teto do giro; quanto menor, mais desviável (angular: não escala)
    LIFETIME = 6.0
    _SCALE_ATTRS = ("RADIUS", "SPEED")

    def __init__(self, x: float, y: float, target_x: float, target_y: float) -> None:
        super().__init__(x, y)
        self.angle = math.atan2(target_y - y, target_x - x)
        self.lifetime = self.LIFETIME

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        desired = math.atan2(ctx.player_y - self.y, ctx.player_x - self.x)
        # Diferença angular normalizada para [-pi, pi], clampada ao turn-rate.
        diff = (desired - self.angle + math.pi) % (2 * math.pi) - math.pi
        max_step = self.MAX_TURN_RATE * dt
        self.angle += max(-max_step, min(max_step, diff))
        self.x += math.cos(self.angle) * self.SPEED * dt
        self.y += math.sin(self.angle) * self.SPEED * dt
        self.lifetime -= dt
        self._sync_rect()
        if self.lifetime <= 0 or _off_screen(self.x, self.y):
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x), int(self.y)
        # Corpo + chama traseira apontando contra o movimento.
        tail_x = cx - int(math.cos(self.angle) * self.RADIUS * 1.8)
        tail_y = cy - int(math.sin(self.angle) * self.RADIUS * 1.8)
        pygame.draw.line(surface, _NEON_AMBER, (cx, cy), (tail_x, tail_y), 3)
        pygame.draw.circle(surface, _NEON_BLUE, (cx, cy), int(self.RADIUS))
        pygame.draw.circle(surface, _NEON_WHITE, (cx, cy), int(self.RADIUS * 0.4))


class VerticalLaser(_CityProjectile):
    """Feixe vertical: telegrafa numa coluna, depois desce cruzando a tela.

    Indestrutível — não pode ser destruído a tiro, só desviado. Dano só na fase
    `active` (telegrafo é seguro), na largura da coluna.
    """

    WIDTH = 18.0
    TELEGRAPH_TIME = 0.7
    FALL_SPEED = 720.0
    _SCALE_ATTRS = ("RADIUS", "WIDTH", "FALL_SPEED")

    def __init__(self, column_x: float) -> None:
        super().__init__(column_x, 0.0)
        self.column_x = float(column_x)
        self.phase = "telegraph"  # telegraph | active
        self.phase_t = 0.0
        self.beam_y = 0.0  # frente do feixe descendo
        self.lifetime = 6.0

    @property
    def causes_damage(self) -> bool:
        return self.phase == "active"

    def collision_circle(self) -> tuple[float, float, float]:
        # Disco na frente do feixe (aproxima a coluna para o broadphase).
        return self.column_x, self.beam_y, self.WIDTH / 2

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        self.phase_t += dt
        if self.phase == "telegraph":
            if self.phase_t >= self.TELEGRAPH_TIME:
                self.phase = "active"
                self.phase_t = 0.0
        else:
            self.beam_y += self.FALL_SPEED * dt
            if self.beam_y > Config.SCREEN_HEIGHT + 40:
                self.dead = True
        self.x, self.y = self.column_x, self.beam_y
        self._sync_rect()

    def on_hit(self, _damage: int, _hx: float, _hy: float) -> "HitResult":
        from ....systems.hit_result import HitResult

        return HitResult()  # indestrutível: tiros do jogador passam direto

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ....systems.hit_result import HitResult

        return HitResult()  # não morre ao tocar a nave (continua descendo)

    def draw(self, surface: pygame.Surface) -> None:
        x = int(self.column_x)
        half = int(self.WIDTH / 2)
        if self.phase == "telegraph":
            # Linha fina pulsante de aviso, da borda superior ao fim da tela.
            pulse = 0.5 + 0.5 * math.sin(self.phase_t * 24.0)
            col = (
                int(_NEON_BLUE[0] * pulse),
                int(_NEON_BLUE[1] * pulse),
                int(_NEON_BLUE[2]),
            )
            pygame.draw.line(surface, col, (x, 0), (x, Config.SCREEN_HEIGHT), 2)
        else:
            top = max(0, int(self.beam_y) - Config.SCREEN_HEIGHT)
            rect = pygame.Rect(x - half, top, half * 2, int(self.beam_y) - top)
            pygame.draw.rect(surface, _NEON_BLUE, rect)
            pygame.draw.rect(surface, _NEON_WHITE, rect.inflate(-half, 0))


class EMPPulse(_CityProjectile):
    """Pulso EMP em anel expansivo. Dano de contato na frente do anel.

    TODO (ver parecer): aplicar lentidão temporária aos PROJÉTEIS do jogador é
    uma mecânica reversa do EMP atual (jogador→inimigos). Fica como stub: por
    enquanto o pulso só ameaça por contato. Implementar o debuff exige plumbing
    novo em Ship/bullets + colisão dedicada.
    """

    MAX_RADIUS = 150.0
    GROWTH = 260.0  # px/s
    THICKNESS = 14.0
    _SCALE_ATTRS = ("RADIUS", "MAX_RADIUS", "GROWTH", "THICKNESS")

    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y)
        self.radius = scaled(6.0)
        self.lifetime = 3.0

    @property
    def causes_damage(self) -> bool:
        return True

    def collision_circle(self) -> tuple[float, float, float]:
        # Aproxima a frente do anel; TODO: validação em anel (annulus) fina.
        return self.x, self.y, self.radius

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        self.radius += self.GROWTH * dt
        self.lifetime -= dt
        self._sync_rect()
        if self.radius >= self.MAX_RADIUS or self.lifetime <= 0:
            self.dead = True

    def on_hit(self, _damage: int, _hx: float, _hy: float) -> "HitResult":
        from ....systems.hit_result import HitResult

        return HitResult()  # o pulso não é destrutível a tiro

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ....systems.hit_result import HitResult

        return HitResult()  # passa pela nave (dano vem do contato, não morre)

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x), int(self.y)
        r = int(self.radius)
        fade = max(0.0, 1.0 - self.radius / self.MAX_RADIUS)
        col = (
            min(255, int(_NEON_MAGENTA[0] * fade + 60)),
            min(255, int(_NEON_BLUE[1] * fade)),
            min(255, int(_NEON_BLUE[2])),
        )
        pygame.draw.circle(surface, col, (cx, cy), r, max(2, int(self.THICKNESS * fade)))


# ─────────────────────────────────────────────────────────────────────────────
# Projéteis DEDICADOS das Sentinelas Orbitais. Identidade Cidade Neon: formas
# geométricas simples + energia/eletricidade, com ciclo visual completo
# (disparo → persistência curta → dissipação). Separados do conjunto clássico
# acima para não tocar no drone/segmento que dependem dele.
# ─────────────────────────────────────────────────────────────────────────────

_PULSE_VIOLET = (180, 120, 255)
_PULSE_BRIGHT = (225, 205, 255)
_GRID_BLUE = (90, 200, 255)
_GRID_BRIGHT = (190, 240, 255)


def _jagged(x1: float, y1: float, x2: float, y2: float, jitter: float, segs: int = 4):
    """Polilinha em ziguezague entre dois pontos (arco elétrico). Para `draw` (§3)."""
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


class EnergyDrone(_CityProjectile):
    """Fragmento energético INTELIGENTE (papel PRESSÃO DIRETA, sentinela magenta).

    Não é um projétil genérico: é um pequeno drone de energia com silhueta de
    PIPA/seta (ponta frontal bem definida), energia interna distribuída, rotação
    perceptível (núcleo girando + nós orbitando) e RASTRO energético curto. Antes
    de partir há uma animação de SURGIMENTO (materializa crescendo); voa reto e
    preciso; ao expirar, DISSIPA fragmentando. Grande e fácil de identificar como
    ameaça individual.
    """

    HEALTH = 5
    RADIUS = 12.0          # bem maior que o feixe antigo (6) — leitura clara
    SPEED = 330.0
    SPAWN = 0.22           # surgimento (materializa) antes de mover — sem dano
    LIFETIME = 4.0
    DISSIPATE = 0.2
    TRAIL_MAX = 6
    COLOR = _NEON_MAGENTA
    BRIGHT = (255, 175, 235)
    _SCALE_ATTRS = ("RADIUS", "SPEED")

    def __init__(self, x: float, y: float, target_x: float, target_y: float) -> None:
        super().__init__(x, y)
        self.angle = math.atan2(target_y - y, target_x - x)
        self.vx = math.cos(self.angle) * self.SPEED
        self.vy = math.sin(self.angle) * self.SPEED
        self.spin = random.uniform(0.0, 2.0 * math.pi)
        self.spin_speed = random.choice((-1.0, 1.0)) * random.uniform(2.6, 3.8)
        self.lifetime = self.LIFETIME
        self._spawn_t = self.SPAWN
        self._diss = 0.0
        self._trail: list[tuple[int, int]] = []
        self._diss_pts: list[tuple[float, float]] = []

    @property
    def causes_damage(self) -> bool:
        return self._spawn_t <= 0.0 and self._diss <= 0.0  # só ameaça em voo

    def collision_circle(self) -> tuple[float, float, float]:
        if self._spawn_t > 0.0 or self._diss > 0.0:
            return -1000.0, -1000.0, 0.0
        return self.x, self.y, self.RADIUS * 0.8

    def _kite(self, scale: float = 1.0) -> list[tuple[float, float]]:
        """Pipa/seta apontando ao rumo: ponta frontal alongada + base recuada."""
        r = self.RADIUS * scale
        a = self.angle
        return [
            (self.x + math.cos(a) * r * 1.5, self.y + math.sin(a) * r * 1.5),          # ponta
            (self.x + math.cos(a + 2.25) * r, self.y + math.sin(a + 2.25) * r),        # lateral
            (self.x + math.cos(a + math.pi) * r * 0.55, self.y + math.sin(a + math.pi) * r * 0.55),  # cauda
            (self.x + math.cos(a - 2.25) * r, self.y + math.sin(a - 2.25) * r),        # lateral
        ]

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        self.anim += dt
        self.spin += self.spin_speed * dt
        if self._spawn_t > 0.0:  # surgindo (parado, materializando)
            self._spawn_t -= dt
            return
        if self._diss > 0.0:
            self._diss -= dt
            if self._diss <= 0.0:
                self.dead = True
            return
        self._trail.append((int(self.x), int(self.y)))
        if len(self._trail) > self.TRAIL_MAX:
            self._trail.pop(0)
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.lifetime -= dt
        self._sync_rect()
        if _off_screen(self.x, self.y):
            self.dead = True
        elif self.lifetime <= 0.0:
            self._diss = self.DISSIPATE
            self._diss_pts = self._kite()

    def draw(self, surface: pygame.Surface) -> None:
        if self._spawn_t > 0.0:  # SURGIMENTO: pipa crescendo + faíscas convergindo
            p = 1.0 - self._spawn_t / self.SPAWN
            for k in range(5):
                ang = self.spin + k * (2.0 * math.pi / 5.0)
                d = self.RADIUS * (1.6 - 1.2 * p)
                surface.fill(self.BRIGHT, (int(self.x + math.cos(ang) * d), int(self.y + math.sin(ang) * d), 2, 2))
            pts = [(int(px), int(py)) for px, py in self._kite(0.3 + 0.7 * p)]
            sc = 0.4 + 0.6 * p
            col = (int(self.COLOR[0] * sc), int(self.COLOR[1] * sc), int(self.COLOR[2] * sc))
            pygame.draw.polygon(surface, col, pts)
            pygame.draw.polygon(surface, _NEON_WHITE, pts, 1)
            return
        if self._diss > 0.0:  # DISSIPAÇÃO: arestas se afastam e somem
            f = self._diss / self.DISSIPATE
            push = (1.0 - f) * 18.0
            col = (int(self.COLOR[0] * f), int(self.COLOR[1] * f), int(self.COLOR[2] * f))
            p = self._diss_pts
            for i in range(len(p)):
                ax, ay = p[i]
                bx, by = p[(i + 1) % len(p)]
                mx, my = (ax + bx) * 0.5 - self.x, (ay + by) * 0.5 - self.y
                n = math.hypot(mx, my) or 1.0
                ox, oy = mx / n * push, my / n * push
                pygame.draw.line(surface, col, (int(ax + ox), int(ay + oy)), (int(bx + ox), int(by + oy)), 2)
            return
        # Rastro energético curto (atrás), afinando do mais antigo ao atual.
        if len(self._trail) >= 2:
            n = len(self._trail)
            for i in range(n - 1):
                g = (i + 1) / n
                tc = (int(self.COLOR[0] * g), int(self.COLOR[1] * g), int(self.COLOR[2] * g))
                pygame.draw.line(surface, tc, self._trail[i], self._trail[i + 1], 1 + int(g * 2))
        pts = [(int(px), int(py)) for px, py in self._kite()]
        pygame.draw.polygon(surface, self.COLOR, pts)
        # Energia interna distribuída: pipa clara menor.
        in_pts = [(int(px), int(py)) for px, py in self._kite(0.5)]
        pygame.draw.polygon(surface, self.BRIGHT, in_pts)
        # Nós orbitando (rotação perceptível) + núcleo quente.
        for k in range(3):
            a = self.spin + k * (2.0 * math.pi / 3.0)
            nx = int(self.x + math.cos(a) * self.RADIUS * 0.85)
            ny = int(self.y + math.sin(a) * self.RADIUS * 0.85)
            pygame.draw.circle(surface, _NEON_WHITE, (nx, ny), 2)
        pygame.draw.circle(surface, _NEON_WHITE, (int(self.x), int(self.y)), 3)
        # Contorno evidente + ponta frontal destacada.
        pygame.draw.polygon(surface, _NEON_WHITE, pts, 2)
        pygame.draw.circle(surface, _NEON_WHITE, pts[0], 3)


class TriShard(_CityProjectile):
    """Papel PERSEGUIÇÃO/SATURAÇÃO: estilhaço triangular GRANDE que persegue de leve
    o jogador (turn-rate limitado, justo) e satura a arena em leque.

    Silhueta de SETA nítida — ponta frontal alongada e clara, contorno evidente,
    energia interna distribuída (triângulo claro + acentos girando = rotação
    perceptível). Ciclo: voo perseguindo → dissipação fragmentando as arestas.
    """

    HEALTH = 5
    RADIUS = 13.0
    SPEED = 230.0
    MAX_TURN_RATE = 1.5  # rad/s — perseguição leve e desviável (§11/bem-estar; angular: não escala)
    LIFETIME = 4.6
    DISSIPATE = 0.24
    COLOR = _NEON_AMBER
    BRIGHT = (255, 225, 170)
    _SCALE_ATTRS = ("RADIUS", "SPEED")

    def __init__(self, x: float, y: float, target_x: float, target_y: float) -> None:
        super().__init__(x, y)
        self.angle = math.atan2(target_y - y, target_x - x)
        self.inner_spin = random.uniform(0.0, 2.0 * math.pi)
        self.inner_spin_speed = random.choice((-1.0, 1.0)) * random.uniform(2.2, 3.4)
        self.lifetime = self.LIFETIME
        self._diss = 0.0
        self._diss_pts: list[tuple[float, float]] = []

    @property
    def causes_damage(self) -> bool:
        return self._diss <= 0.0

    def collision_circle(self) -> tuple[float, float, float]:
        if self._diss > 0.0:
            return -1000.0, -1000.0, 0.0
        return self.x, self.y, self.RADIUS * 0.8

    def _silhouette(self) -> list[tuple[float, float]]:
        """Seta apontando ao rumo: ponta frontal alongada + base recuada (front claro)."""
        tip = (self.x + math.cos(self.angle) * self.RADIUS * 1.35,
               self.y + math.sin(self.angle) * self.RADIUS * 1.35)
        bl = (self.x + math.cos(self.angle + 2.5) * self.RADIUS,
              self.y + math.sin(self.angle + 2.5) * self.RADIUS)
        br = (self.x + math.cos(self.angle - 2.5) * self.RADIUS,
              self.y + math.sin(self.angle - 2.5) * self.RADIUS)
        return [tip, bl, br]

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        self.anim += dt
        if self._diss > 0.0:
            self._diss -= dt
            if self._diss <= 0.0:
                self.dead = True
            return
        # Perseguição leve: gira o rumo em direção ao jogador, limitado ao turn-rate.
        desired = math.atan2(ctx.player_y - self.y, ctx.player_x - self.x)
        diff = (desired - self.angle + math.pi) % (2.0 * math.pi) - math.pi
        step = self.MAX_TURN_RATE * dt
        self.angle += max(-step, min(step, diff))
        self.inner_spin += self.inner_spin_speed * dt
        self.x += math.cos(self.angle) * self.SPEED * dt
        self.y += math.sin(self.angle) * self.SPEED * dt
        self.lifetime -= dt
        self._sync_rect()
        if _off_screen(self.x, self.y):
            self.dead = True
        elif self.lifetime <= 0.0:
            self._diss = self.DISSIPATE
            self._diss_pts = self._silhouette()

    def draw(self, surface: pygame.Surface) -> None:
        if self._diss > 0.0:
            f = self._diss / self.DISSIPATE
            push = (1.0 - f) * 18.0
            col = (int(self.COLOR[0] * f), int(self.COLOR[1] * f), int(self.COLOR[2] * f))
            p = self._diss_pts
            for i in range(3):
                ax, ay = p[i]
                bx, by = p[(i + 1) % 3]
                mx, my = (ax + bx) * 0.5 - self.x, (ay + by) * 0.5 - self.y
                n = math.hypot(mx, my) or 1.0
                ox, oy = mx / n * push, my / n * push
                pygame.draw.line(surface, col, (int(ax + ox), int(ay + oy)), (int(bx + ox), int(by + oy)), 2)
            return
        pts = [(int(px), int(py)) for px, py in self._silhouette()]
        pygame.draw.polygon(surface, self.COLOR, pts)
        # Energia interna distribuída: triângulo claro menor alinhado à seta.
        in_pts = []
        for k in range(3):
            a = self.angle + k * (2.0 * math.pi / 3.0)
            r = self.RADIUS * 0.6 if k == 0 else self.RADIUS * 0.42
            in_pts.append((int(self.x + math.cos(a) * r), int(self.y + math.sin(a) * r)))
        pygame.draw.polygon(surface, self.BRIGHT, in_pts)
        # Acentos girando (rotação perceptível) + núcleo quente.
        for k in range(3):
            a = self.inner_spin + k * (2.0 * math.pi / 3.0)
            ex = int(self.x + math.cos(a) * self.RADIUS * 0.72)
            ey = int(self.y + math.sin(a) * self.RADIUS * 0.72)
            pygame.draw.line(surface, _NEON_WHITE, (int(self.x), int(self.y)), (ex, ey), 1)
        pygame.draw.circle(surface, _NEON_WHITE, (int(self.x), int(self.y)), 3)
        # Contorno evidente por cima + ponta frontal destacada.
        pygame.draw.polygon(surface, _NEON_WHITE, pts, 2)
        pygame.draw.circle(surface, _NEON_WHITE, pts[0], 3)


class ElectricPulse(_CityProjectile):
    """Papel CONTROLE DE ESPAÇO: sobrecarga elétrica que NASCE, se ESTABILIZA e
    COLAPSA num ponto travado da arena (não um disco que só aparece e some).

    Nasce já no INÍCIO da mira da sentinela (ela trava o alvo e spawna a zona);
    assim marcação, construção e hitbox ficam SEMPRE no MESMO ponto — a antecipação
    casa exatamente com o ataque. Três fases legíveis:
      GATHER   — rede sendo montada: nós surgem ao redor, CONVERGEM ao centro, arcos
                 começam a conectar, o brilho sobe e a zona se estabiliza. SEM dano.
      OVERLOAD — viva e instável: borda irregular (nunca círculo perfeito) pulsando,
                 arcos aleatórios, pequenas falhas, intensidade oscilando. Dano.
      COLLAPSE — arcos falham, o brilho cai, partes deixam de existir, os nós se
                 desconectam e IMPLODEM ao centro; sobram partículas residuais.

    Justiça (regra global): a borda só oscila p/ FORA (raio≥RADIUS) e o halo cobre
    todo o disco — a área VISÍVEL nunca é menor que a hitbox. Dano só no OVERLOAD.
    `rect` dimensionado ao raio p/ a broadphase enxergar a zona inteira.
    """

    RADIUS = 96.0  # raio de dano na sobrecarga (= base do rect/broadphase)
    WOBBLE = 7.0   # instabilidade da borda — SÓ para fora (visível ≥ hitbox)
    GATHER = 0.8
    OVERLOAD = 0.6
    COLLAPSE = 0.5
    TOTAL = GATHER + OVERLOAD + COLLAPSE
    COLOR = _PULSE_VIOLET
    BRIGHT = _PULSE_BRIGHT
    _SCALE_ATTRS = ("RADIUS", "WOBBLE")

    def __init__(self, cx: float, cy: float) -> None:
        # super() escala RADIUS pela resolução; o clamp da borda usa o RADIUS já
        # escalado (+margem escalada) p/ a zona inteira caber on-screen em qualquer res.
        super().__init__(cx, cy)  # base dimensiona o rect a RADIUS*2 e centra aqui
        m = self.RADIUS + scaled(8.0)
        self.x = max(m, min(Config.SCREEN_WIDTH - m, self.x))
        self.y = max(m, min(Config.SCREEN_HEIGHT - m, self.y))
        self._sync_rect()
        self.phase = "gather"  # gather | overload | collapse
        self.phase_t = 0.0
        self.lifetime = 4.0
        self._nodes = random.randint(7, 8)
        self._node_phase = [random.uniform(0.0, 2.0 * math.pi) for _ in range(self._nodes)]
        self._node_dist = [random.uniform(1.8, 2.4) for _ in range(self._nodes)]  # ×RADIUS (origem)
        # Halo de área pré-renderado uma vez (reuso; sem alocar Surface por frame).
        hr = int(self.RADIUS) + 2
        self._halo_surf = pygame.Surface((hr * 2, hr * 2), pygame.SRCALPHA)
        pygame.draw.circle(self._halo_surf, (*self.COLOR, 60), (hr, hr), int(self.RADIUS))
        self._halo_r = hr

    @property
    def causes_damage(self) -> bool:
        return self.phase == "overload"

    def collision_circle(self) -> tuple[float, float, float]:
        if self.phase != "overload":
            return -1000.0, -1000.0, 0.0
        return self.x, self.y, self.RADIUS

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        self.anim += dt
        self.phase_t += dt
        if self.phase == "gather":
            if self.phase_t >= self.GATHER:
                self.phase, self.phase_t = "overload", 0.0
        elif self.phase == "overload":
            if self.phase_t >= self.OVERLOAD:
                self.phase, self.phase_t = "collapse", 0.0
        else:
            if self.phase_t >= self.COLLAPSE:
                self.dead = True

    def on_hit(self, _damage: int, _hx: float, _hy: float) -> "HitResult":
        from ....systems.hit_result import HitResult

        return HitResult()  # não destrutível a tiro

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ....systems.hit_result import HitResult

        return HitResult()  # passa pela nave (controle de área, não morre)

    def _jagged_ring(self, surface, cx, cy, r, col, gaps=0.0, outward=True):
        """Anel poligonal IRREGULAR (nunca círculo perfeito), com falhas opcionais."""
        npts = self._nodes * 3
        prev = None
        first = None
        for k in range(npts + 1):
            a = (k % npts) * (2.0 * math.pi / npts) + self.anim * 0.3
            off = random.uniform(0.0, self.WOBBLE) if outward else random.uniform(-self.WOBBLE, self.WOBBLE)
            rr = r + off
            p = (int(cx + math.cos(a) * rr), int(cy + math.sin(a) * rr))
            if first is None:
                first = p
            if prev is not None and random.random() >= gaps:  # 'gaps' = prob. de falha
                pygame.draw.line(surface, col, prev, p, 2)
            prev = p

    def draw(self, surface: pygame.Surface) -> None:
        if self.phase == "gather":
            self._draw_gather(surface)
        elif self.phase == "overload":
            self._draw_overload(surface)
        else:
            self._draw_collapse(surface)

    def _draw_gather(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x), int(self.y)
        gp = min(1.0, self.phase_t / self.GATHER)
        sc = 0.3 + 0.55 * gp  # brilho subindo
        col = (int(self.COLOR[0] * sc), int(self.COLOR[1] * sc), int(self.COLOR[2] * sc))
        # Marcação central (cruz de mira) desde o início — alvo travado.
        cross = int(7 + 5 * gp)
        for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            pygame.draw.line(surface, col, (cx + sx * 3, cy + sy * 3), (cx + sx * cross, cy + sy * cross), 1)
        # Nós surgem ao redor e CONVERGEM ao centro (raio final = RADIUS = hitbox).
        for k in range(self._nodes):
            a = self._node_phase[k] + self.anim * 0.5
            d = self.RADIUS * (self._node_dist[k] * (1.0 - gp) + gp)
            nx, ny = int(cx + math.cos(a) * d), int(cy + math.sin(a) * d)
            pygame.draw.circle(surface, self.BRIGHT, (nx, ny), 2 + int(gp * 1.5))
            # Arcos começam a conectar nó→centro conforme a rede é montada.
            if gp > 0.35 and random.random() < (gp - 0.2):
                pts = _jagged(nx, ny, cx, cy, jitter=3.0 + 6.0 * gp, segs=4)
                pygame.draw.lines(surface, self.COLOR, False, [(int(px), int(py)) for px, py in pts], 1)
        # Estabilização: anel irregular tênue no raio final (prévia da borda; SEM dano).
        if gp > 0.7:
            es = (gp - 0.7) / 0.3
            ec = (int(self.COLOR[0] * es), int(self.COLOR[1] * es), int(self.COLOR[2] * es))
            self._jagged_ring(surface, cx, cy, self.RADIUS, ec, gaps=0.5)

    def _draw_overload(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x), int(self.y)
        op = self.phase_t / self.OVERLOAD
        # Falha aleatória ocasional: a zona "pisca" por um frame (instabilidade).
        glitch = random.random() < 0.08
        flick = (0.55 if glitch else 1.0) * (0.85 + 0.15 * math.sin(self.anim * 28.0))
        pulse = 0.95 + 0.05 * math.sin(self.anim * 12.0)  # pulso constante
        # Halo de área cobrindo TODO o disco (garante visível ≥ hitbox).
        if vq.glow_enabled and not glitch:
            surface.blit(self._halo_surf, (cx - self._halo_r, cy - self._halo_r))
        # Clarão de ATIVAÇÃO nos primeiros instantes — marca o "ficou perigoso AGORA".
        if op < 0.16:
            f = 1.0 - op / 0.16
            pygame.draw.circle(surface, _NEON_WHITE, (cx, cy), int(self.RADIUS * (0.7 + 0.5 * f)), max(1, int(4 * f)))
        # Borda IRREGULAR pulsando (nunca círculo perfeito), com pequenas falhas.
        cc = (int(self.BRIGHT[0] * flick), int(self.BRIGHT[1] * flick), int(self.BRIGHT[2] * flick))
        self._jagged_ring(surface, cx, cy, self.RADIUS * pulse, cc, gaps=0.12)
        self._jagged_ring(surface, cx, cy, self.RADIUS * 0.6 * pulse, self.COLOR, gaps=0.25)
        # Arcos elétricos aleatórios (vivos) — contidos ao raio.
        if not glitch:
            for _ in range(vq.electric(4)):
                ang = random.uniform(0.0, 2.0 * math.pi)
                reach = self.RADIUS * random.uniform(0.55, 1.0)
                ex, ey = cx + math.cos(ang) * reach, cy + math.sin(ang) * reach
                lc = _NEON_WHITE if random.random() < 0.5 else self.BRIGHT
                pts = _jagged(cx, cy, ex, ey, jitter=8.0, segs=5)
                pygame.draw.lines(surface, lc, False, [(int(px), int(py)) for px, py in pts], 1)
        # Nós orbitando pulsando em intensidades diferentes + núcleo branco.
        for k in range(self._nodes):
            a = self._node_phase[k] + self.anim * 1.2
            np_ = 0.5 + 0.5 * math.sin(self.anim * 6.0 + k)
            nc = (int(self.BRIGHT[0] * np_), int(self.BRIGHT[1] * np_), self.BRIGHT[2])
            pygame.draw.circle(surface, nc, (int(cx + math.cos(a) * self.RADIUS), int(cy + math.sin(a) * self.RADIUS)), 2)
        pygame.draw.circle(surface, _NEON_WHITE, (cx, cy), max(1, int(self.RADIUS * 0.16 * (0.7 + 0.3 * flick))))

    def _draw_collapse(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x), int(self.y)
        cp = min(1.0, self.phase_t / self.COLLAPSE)
        f = 1.0 - cp  # brilho caindo (clampado em [0,1])
        fade = (int(self.BRIGHT[0] * f), int(self.BRIGHT[1] * f), int(self.BRIGHT[2] * f))
        # Anel irregular CONTRAINDO com muitas falhas (estrutura deixando de existir).
        r = self.RADIUS * f
        if r > 3.0:
            self._jagged_ring(surface, cx, cy, r, fade, gaps=0.35 + 0.4 * cp, outward=False)
        # Nós se DESCONECTAM e IMPLODEM ao centro (alguns somem).
        for k in range(self._nodes):
            if random.random() < 0.55 + 0.4 * f:
                a = self._node_phase[k] + self.anim * 0.5
                d = self.RADIUS * f * random.uniform(0.85, 1.0)
                nx, ny = int(cx + math.cos(a) * d), int(cy + math.sin(a) * d)
                pygame.draw.circle(surface, fade, (nx, ny), 2)
                if random.random() < f:  # rastro curto implodindo p/ o centro
                    pygame.draw.line(surface, fade, (nx, ny), (cx, cy), 1)
        # Arcos falhando (cada vez menos).
        for _ in range(vq.electric(max(0, int(3 * f)))):
            ang = random.uniform(0.0, 2.0 * math.pi)
            reach = r * random.uniform(0.4, 1.0)
            pts = _jagged(cx, cy, cx + math.cos(ang) * reach, cy + math.sin(ang) * reach, jitter=6.0, segs=4)
            pygame.draw.lines(surface, fade, False, [(int(px), int(py)) for px, py in pts], 1)
        # Implosão final + partículas residuais persistindo.
        if cp > 0.55:
            pygame.draw.circle(surface, fade, (cx, cy), max(1, int(self.RADIUS * 0.5 * (1.0 - cp))), 1)
        for _ in range(vq.particles(int(5 * f) + 1)):
            ang = random.uniform(0.0, 2.0 * math.pi)
            d = self.RADIUS * 0.35 * random.uniform(0.1, 1.0)
            surface.fill(fade, (int(cx + math.cos(ang) * d), int(cy + math.sin(ang) * d), 2, 2))


class GridSnare(_CityProjectile):
    """Papel SUPORTE: grade holográfica energizada (controle de área).

    Materializa no ponto travado do telegrafo, eletrifica por um instante e
    dissipa. Ciclo legível: FORMAÇÃO (holograma desenhando, seguro) → ATIVA
    (grade elétrica, dano de contato) → DISSIPAÇÃO (apaga). Dodge-only — não
    some a tiro nem ao tocar a nave; o jogador sai da célula a tempo.
    """

    # 64 base × 1.3 = 83.2: +30% de área de controle (mais presença em combate). A
    # escala por resolução (_SCALE_ATTRS) é aplicada por cima no __init__.
    HALF = 83.2
    RADIUS = 83.2  # = HALF: dimensiona o rect/broadphase à grade inteira
    FORM = 0.3
    ACTIVE = 0.85
    DISSIPATE = 0.4
    COLOR = _GRID_BLUE
    BRIGHT = _GRID_BRIGHT
    CELLS = 4
    _SCALE_ATTRS = ("RADIUS", "HALF")

    def __init__(self, cx: float, cy: float) -> None:
        # super() escala HALF/RADIUS pela resolução; clamp usa o HALF já escalado
        # (+margem escalada) p/ a grade inteira caber on-screen em qualquer res.
        super().__init__(cx, cy)
        m = self.HALF + scaled(6.0)
        self.x = max(m, min(Config.SCREEN_WIDTH - m, self.x))
        self.y = max(m, min(Config.SCREEN_HEIGHT - m, self.y))
        self._sync_rect()
        self.phase = "form"  # form | active | dissipate
        self.phase_t = 0.0
        self.lifetime = 4.0

    @property
    def causes_damage(self) -> bool:
        return self.phase == "active"

    def collision_circle(self) -> tuple[float, float, float]:
        if self.phase != "active":
            return -1000.0, -1000.0, 0.0
        return self.x, self.y, self.HALF * 0.95  # disco aproxima o quadrado

    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        self.anim += dt
        self.phase_t += dt
        if self.phase == "form":
            if self.phase_t >= self.FORM:
                self.phase, self.phase_t = "active", 0.0
        elif self.phase == "active":
            if self.phase_t >= self.ACTIVE:
                self.phase, self.phase_t = "dissipate", 0.0
        else:
            if self.phase_t >= self.DISSIPATE:
                self.dead = True

    def on_hit(self, _damage: int, _hx: float, _hy: float) -> "HitResult":
        from ....systems.hit_result import HitResult

        return HitResult()  # indestrutível a tiro

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ....systems.hit_result import HitResult

        return HitResult()  # não morre ao tocar a nave (zona de controle)

    def _wline(self, surface: pygame.Surface, x1: float, y1: float, x2: float, y2: float,
               col: tuple[int, int, int], jitter: float) -> None:
        """Linha levemente irregular com FALHA ocasional (rede instável, não malha digital)."""
        if random.random() < 0.12:  # interrupção/glitch ocasional
            return
        pts = _jagged(x1, y1, x2, y2, jitter, segs=3)
        pygame.draw.lines(surface, col, False, [(int(px), int(py)) for px, py in pts], 1)

    def _draw_grid(self, surface: pygame.Surface, scale: float, electric: bool) -> None:
        size = self.HALF * 2.0
        x0, y0 = self.x - self.HALF, self.y - self.HALF
        col = (int(self.COLOR[0] * scale), int(self.COLOR[1] * scale), int(self.COLOR[2] * scale))
        jit = 2.2 if electric else 1.2
        osc = math.sin(self.anim * 6.0) * (1.6 if electric else 0.6)  # oscilação sutil
        # Bordas menos rígidas (jagged + oscilando).
        self._wline(surface, x0, y0 + osc, x0 + size, y0 + osc, col, jit)
        self._wline(surface, x0, y0 + size - osc, x0 + size, y0 + size - osc, col, jit)
        self._wline(surface, x0 + osc, y0, x0 + osc, y0 + size, col, jit)
        self._wline(surface, x0 + size - osc, y0, x0 + size - osc, y0 + size, col, jit)
        # Linhas internas (irregulares, com falhas).
        for i in range(1, self.CELLS):
            gx = x0 + size * i / self.CELLS + osc * 0.5
            gy = y0 + size * i / self.CELLS + osc * 0.5
            self._wline(surface, gx, y0, gx, y0 + size, col, jit)
            self._wline(surface, x0, gy, x0 + size, gy, col, jit)
        # Nós pulsando em intensidades diferentes (rede sustentada artificialmente).
        for i in range(self.CELLS + 1):
            for j in range(self.CELLS + 1):
                pulse = 0.5 + 0.5 * math.sin(self.anim * 5.0 + (i * 3 + j * 7))
                nx = int(x0 + size * i / self.CELLS)
                ny = int(y0 + size * j / self.CELLS)
                if electric:
                    nc = (int(self.BRIGHT[0] * (0.5 + 0.5 * pulse)),
                          int(self.BRIGHT[1] * (0.5 + 0.5 * pulse)), self.BRIGHT[2])
                    pygame.draw.circle(surface, nc, (nx, ny), 1 + int(pulse * 2.0))
                else:
                    pygame.draw.circle(surface, col, (nx, ny), 2)
        # Arcos elétricos surgindo aleatoriamente entre nós (só ativa).
        if electric:
            for _ in range(vq.electric(3)):
                i1, j1 = random.randint(0, self.CELLS), random.randint(0, self.CELLS)
                i2, j2 = random.randint(0, self.CELLS), random.randint(0, self.CELLS)
                ax, ay = x0 + size * i1 / self.CELLS, y0 + size * j1 / self.CELLS
                bx, by = x0 + size * i2 / self.CELLS, y0 + size * j2 / self.CELLS
                pts = _jagged(ax, ay, bx, by, jitter=4.0, segs=4)
                pygame.draw.lines(surface, _NEON_WHITE, False, [(int(px), int(py)) for px, py in pts], 1)

    def draw(self, surface: pygame.Surface) -> None:
        if self.phase == "form":
            self._draw_grid(surface, 0.35 + 0.55 * min(1.0, self.phase_t / self.FORM), False)
        elif self.phase == "active":
            flick = 0.85 + 0.15 * math.sin(self.anim * 22.0)
            self._draw_grid(surface, flick, True)
        else:
            self._draw_grid(surface, max(0.0, 1.0 - self.phase_t / self.DISSIPATE) * 0.8, False)


_BOLT_YELLOW = (255, 230, 120)
_BOLT_BRIGHT = (255, 245, 200)


def _vbolt(col_x: float, jitter: float, segs: int, x_off: float = 0.0):
    """Polilinha vertical irregular do topo ao fundo da tela (raio). Para `draw` (§3)."""
    h = Config.SCREEN_HEIGHT
    pts = [(col_x + x_off, 0.0)]
    for i in range(1, segs):
        y = h * i / segs
        pts.append((col_x + x_off + random.uniform(-jitter, jitter), y))
    pts.append((col_x + x_off, float(h)))
    return pts


class LightningStrike(EnemyHitMixin):
    """Descarga atmosférica massiva (especialidade da sentinela AMARELA/âmbar).

    Não é um projétil: a sentinela canaliza a rede elétrica da Cidade e ATRAI um
    raio vindo do topo sobre uma coluna da arena. Ciclo fortíssimo de antecipação:
      CHARGE   — coluna amarela TRANSLÚCIDA (energia atmosférica acumulando) que
                 começa estreita e ALARGA até a largura exata da área de dano;
                 bordas instáveis, partículas subindo, arcos internos, brilho
                 crescente nos instantes finais. SEM dano (telegrafo honesto).
      STRIKE   — o raio cai: feixe principal espesso e irregular, branco/âmbar,
                 com RAMIFICAÇÕES secundárias (só visuais, sem hitbox). Dano
                 LIMITADO ao feixe principal = largura da coluna (justo e simples).
      DISSIPATE— a descarga se dissipa antes da sentinela voltar ao normal.

    Colisão = pilha de círculos cobrindo a coluna (hitbox vertical fiel à largura),
    ativa só no STRIKE. Indestrutível a tiro (só desvio).
    """

    is_boss: bool = False
    HEALTH = 1
    POINTS = 0
    WIDTH = 72.0          # largura da coluna = área de dano (exata)
    CHARGE = 1.1
    STRIKE = 0.2
    DISSIPATE = 0.45
    TOTAL = CHARGE + STRIKE + DISSIPATE
    COLOR = _BOLT_YELLOW
    BRIGHT = _BOLT_BRIGHT

    def __init__(self, col_x: float, event_bus: "EventBus | None" = None) -> None:
        # Largura da coluna escala pela resolução (§12): presença/legibilidade
        # consistentes. Vira instância → todo `self.WIDTH` (haze, colisão, rect) segue.
        self.WIDTH = self.WIDTH * gameplay_scale()
        hw = self.WIDTH * 0.5
        self.col_x = max(hw, min(Config.SCREEN_WIDTH - hw, float(col_x)))
        h = Config.SCREEN_HEIGHT
        self.x, self.y = self.col_x, h * 0.5
        self.dead = False
        self.health = self.HEALTH
        self.phase = "charge"  # charge | strike | dissipate
        self.phase_t = 0.0
        self.anim = 0.0
        self._bus = event_bus  # p/ screen shake ao atingir o jogador
        self._shook = False    # garante 1 tremor por descarga (não acumula)
        self._rect = pygame.Rect(int(self.col_x - hw), 0, int(self.WIDTH), int(h))
        # Haze translúcido da coluna pré-renderado UMA vez (soft edges) — reuso por
        # frame via sub-strip; sem alocar Surface no hot path (§7).
        self._col = pygame.Surface((int(self.WIDTH), h), pygame.SRCALPHA)
        for ix in range(int(self.WIDTH)):
            fall = 1.0 - abs(ix - hw) / hw  # 1 no centro → 0 nas bordas
            a = int(70 * (fall ** 1.6))
            if a > 0:
                self._col.fill((*self.COLOR, a), (ix, 0, 1, h))
        # Partículas elétricas subindo dentro da coluna: [dx, y, vel].
        self._motes = [[random.uniform(-hw, hw), random.uniform(0.0, h), random.uniform(60.0, 150.0)]
                       for _ in range(vq.particles(10))]
        # Som de antecipação (carga): a coluna de telegrafo nasce AGORA. O som do
        # impacto é emitido na transição p/ STRIKE (update). §2: via EventBus.
        self._emit_sound("metropolis_lightning_charge")

    def _emit_sound(self, name: str) -> None:
        """Emite um pedido de SFX pelo EventBus (no-op sem bus, ex.: testes)."""
        if self._bus is not None:
            from ....events import game_events as events
            self._bus.emit(events.PlaySound(sound_name=name))

    # ── Colisão (feixe vertical fiel à largura, só no STRIKE) ──────────────────
    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    @property
    def causes_damage(self) -> bool:
        return self.phase == "strike"

    def get_ship_contact_hitboxes(self):
        if self.phase != "strike":
            return ()
        return (self._rect,)

    def collision_circles(self):
        if self.phase != "strike":
            return ()
        r = self.WIDTH * 0.5
        step = self.WIDTH * 0.9
        h = Config.SCREEN_HEIGHT
        circles = []
        y = r
        while y < h:
            circles.append((self.col_x, y, r))
            y += step
        circles.append((self.col_x, h - r, r))
        return circles

    def collision_circle(self) -> tuple[float, float, float]:
        return -1000.0, -1000.0, 0.0  # usa collision_circles (pilha); singular desativado

    def take_damage(self, _amount: int) -> None:
        pass  # indestrutível

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, _damage: int, _hx: float, _hy: float) -> "HitResult":
        from ....systems.hit_result import HitResult

        return HitResult()  # tiros do jogador passam direto

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ....systems.hit_result import HitResult

        # Descarga massiva atingindo a arena: tremor curto e moderado, UMA vez.
        if self._bus is not None and not self._shook:
            self._shook = True
            from ....events import game_events as events
            self._bus.emit(events.ScreenShake(intensity=9, duration=0.2))
        return HitResult()  # não morre ao tocar a nave

    def should_remove(self) -> bool:
        return self.dead

    # ── Update ─────────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        self.anim += dt
        self.phase_t += dt
        # Partículas sobem (energia atmosférica sendo puxada para cima).
        h = Config.SCREEN_HEIGHT
        for m in self._motes:
            m[1] -= m[2] * dt
            if m[1] < 0.0:
                m[1] = h
                m[0] = random.uniform(-self.WIDTH * 0.5, self.WIDTH * 0.5)
        if self.phase == "charge":
            if self.phase_t >= self.CHARGE:
                self.phase, self.phase_t = "strike", 0.0
                self._emit_sound("metropolis_lightning_strike")  # raio caindo (impacto)
        elif self.phase == "strike":
            if self.phase_t >= self.STRIKE:
                self.phase, self.phase_t = "dissipate", 0.0
        else:
            if self.phase_t >= self.DISSIPATE:
                self.dead = True

    # ── Render (§3) ─────────────────────────────────────────────────────────────
    def _blit_haze(self, surface: pygame.Surface, w: float, jx: int = 0) -> None:
        w = max(4, int(w))
        src = pygame.Rect((int(self.WIDTH) - w) // 2, 0, w, Config.SCREEN_HEIGHT)
        surface.blit(self._col, (int(self.col_x - w / 2) + jx, 0), src)

    def draw(self, surface: pygame.Surface) -> None:
        if self.phase == "charge":
            self._draw_charge(surface)
        elif self.phase == "strike":
            self._draw_strike(surface)
        else:
            self._draw_dissipate(surface)

    def _draw_charge(self, surface: pygame.Surface) -> None:
        gp = self.phase_t / self.CHARGE
        ease = gp * gp * (3.0 - 2.0 * gp)
        w = self.WIDTH * (0.12 + 0.88 * ease)  # estreita → largura máx (área de dano)
        jx = random.randint(-1, 1) if gp > 0.5 else 0  # tremulação sutil
        self._blit_haze(surface, w, jx)
        # Bordas levemente instáveis (jagged) subindo dos dois lados.
        es = 0.4 + 0.6 * gp
        ec = (int(self.COLOR[0] * es), int(self.COLOR[1] * es), int(self.COLOR[2] * es))
        for side in (-1, 1):
            pts = _vbolt(self.col_x, jitter=1.5 + 2.0 * gp, segs=10, x_off=side * w * 0.5)
            pygame.draw.lines(surface, ec, False, [(int(px), int(py)) for px, py in pts], 1)
        # Partículas elétricas subindo (dentro da largura atual).
        half = w * 0.5
        for m in self._motes:
            if abs(m[0]) <= half:
                pygame.draw.circle(surface, self.BRIGHT, (int(self.col_x + m[0]), int(m[1])), 2)
        # Arcos internos crescendo + brilho final (luminosidade nos instantes finais).
        if gp > 0.4:
            for _ in range(vq.electric(1 + int(gp * 2))):
                y = random.uniform(0.0, Config.SCREEN_HEIGHT)
                pts = _jagged(self.col_x - half, y, self.col_x + half, y + random.uniform(-30, 30), jitter=6.0, segs=3)
                pygame.draw.lines(surface, self.BRIGHT, False, [(int(px), int(py)) for px, py in pts], 1)
        if gp > 0.75:
            flick = 0.6 + 0.4 * math.sin(self.anim * 40.0)
            cc = (int(self.BRIGHT[0] * flick), int(self.BRIGHT[1] * flick), int(self.BRIGHT[2] * flick))
            pygame.draw.line(surface, cc, (int(self.col_x), 0), (int(self.col_x), Config.SCREEN_HEIGHT), 2)

    def _draw_strike(self, surface: pygame.Surface) -> None:
        # Coluna iluminada de fundo (flash de impacto) — largura máx = área de dano.
        self._blit_haze(surface, self.WIDTH)
        # Feixe principal espesso e irregular (alto contraste: âmbar grosso + núcleo branco).
        main = _vbolt(self.col_x, jitter=self.WIDTH * 0.3, segs=14)
        ipts = [(int(px), int(py)) for px, py in main]
        pygame.draw.lines(surface, self.COLOR, False, ipts, 9)
        pygame.draw.lines(surface, self.BRIGHT, False, ipts, 5)
        pygame.draw.lines(surface, _NEON_WHITE, False, ipts, 2)
        # Ramificações secundárias (APENAS visuais, sem hitbox) — relâmpago real.
        for _ in range(vq.electric(5)):
            k = random.randint(1, len(main) - 2)
            bx, by = main[k]
            ang = random.uniform(-1.1, 1.1) + (math.pi * 0.5)  # para baixo/lados
            length = random.uniform(40.0, 130.0)
            ex, ey = bx + math.cos(ang) * length, by + math.sin(ang) * length
            pts = _jagged(bx, by, ex, ey, jitter=10.0, segs=4)
            pygame.draw.lines(surface, self.BRIGHT, False, [(int(px), int(py)) for px, py in pts], 2)
        # Faíscas no ponto de impacto (base).
        for _ in range(vq.particles(6)):
            ang = random.uniform(math.pi, 2.0 * math.pi)
            d = random.uniform(8.0, 50.0)
            surface.fill(self.BRIGHT, (int(self.col_x + math.cos(ang) * d),
                                       int(Config.SCREEN_HEIGHT + math.sin(ang) * d), 2, 2))

    def _draw_dissipate(self, surface: pygame.Surface) -> None:
        f = max(0.0, 1.0 - self.phase_t / self.DISSIPATE)
        self._blit_haze(surface, self.WIDTH * f)  # estreita ao apagar
        cc = (int(self.BRIGHT[0] * f), int(self.BRIGHT[1] * f), int(self.BRIGHT[2] * f))
        pygame.draw.line(surface, cc, (int(self.col_x), 0), (int(self.col_x), Config.SCREEN_HEIGHT), max(1, int(3 * f)))
        for m in self._motes:
            if random.random() < f:
                pygame.draw.circle(surface, cc, (int(self.col_x + m[0]), int(m[1])), 1)
