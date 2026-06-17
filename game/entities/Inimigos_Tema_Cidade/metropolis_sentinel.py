"""Sentinela Orbital do Metropolis Overlord (Fase 1 / interlúdio, tema CITY).

Quatro esferas de energia que percorrem o PERÍMETRO da tela. São os **geradores do
escudo** do Overlord: enquanto pelo menos uma vive, o contorno neon do boss
permanece energizado e o corpo é invulnerável. Destruir as quatro derruba o escudo
(descarga visual) e abre a fase seguinte — ver `MetropolisOverlordBoss`.

Cada sentinela tem um papel (cor própria) com projétil custom e telegrafo próprios:
  "neon"    → rajadas retas (telegrafo: linha de mira reta).
  "missile" → mísseis seguidores (telegrafo: anel + chevrons girando).
  "laser"   → feixes verticais (telegrafo: coluna-alvo destacada).
  "emp"     → pulsos EMP em anel (telegrafo: anel de área crescendo).

Ataques por FSM legível (REPOUSO → PREPARAÇÃO → DISPARO → RECUPERAÇÃO), com
materialização ao nascer e destruição impactante (fragmentação/dissipação). A
patrulha (Top → Right → Bottom → Left) é por comprimento de arco (velocidade
uniforme). `draw` puro (§3): mutação só no `update`; o boss lê `s.dead`.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List

import pygame

from ...core.config import config as Config
from ...core.visual_quality import visual_quality as vq
from ..enemy_hit_mixin import EnemyHitMixin
from .metropolis_projectiles import (
    EMPPulse,
    MicroMissile,
    NeonBurstShot,
    VerticalLaser,
)

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult

_NEON_WHITE = (255, 255, 255)

# Inset do trajeto em relação à borda real da tela. ~RADIUS para a esfera ficar
# ENCOSTADA na borda (ancorada ao perímetro) e ainda 100% visível/alcançável.
_EDGE_INSET = 28.0

# Estados da FSM de combate (legibilidade).
_S_IDLE = "idle"
_S_AIM = "aim"
_S_FIRE = "fire"
_S_RECOVER = "recover"


def _jagged(x1: float, y1: float, x2: float, y2: float, jitter: float, segs: int = 4):
    """Polilinha em ziguezague entre dois pontos (raio elétrico). Para `draw` (§3)."""
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


class MetropolisSentinel(EnemyHitMixin):
    """Esfera de energia que patrulha o perímetro da tela e ataca (geradora do escudo)."""

    is_boss: bool = False
    RADIUS = 22.0
    HEALTH = 100
    POINTS = 250
    BASE_SPEED = 0.12  # t por segundo (uma volta a cada ~8s) — patrulha inalterada

    BIRTH_TIME: float = 0.6
    DEATH_BURST: float = 0.5
    FIRE_TIME: float = 0.14
    RECOVER_TIME: float = 0.5

    # Cadência por papel: REPOUSO (entre ataques) e PREPARAÇÃO (telegrafo). REPOUSO/
    # RECUPERAÇÃO escalam c/ aggr; o TELEGRAFO é fixo (sempre legível).
    _ROLE_IDLE = {"neon": 0.7, "missile": 1.1, "laser": 1.4, "emp": 1.6}
    _ROLE_AIM = {"neon": 0.6, "missile": 0.8, "laser": 0.85, "emp": 1.0}

    # Paleta por papel (dark, mid, bright) — identidade de cor mantida, render rico.
    _ROLE_PALETTE = {
        "neon":    ((90, 20, 70),   (255, 70, 200),  (255, 175, 235)),
        "missile": ((90, 55, 10),   (255, 190, 80),  (255, 225, 170)),
        "laser":   ((20, 70, 95),   (90, 200, 255),  (190, 240, 255)),
        "emp":     ((70, 45, 110),  (180, 120, 255), (225, 205, 255)),
    }

    _explosion_size_killed = 0  # explosão é própria (energética), não a genérica
    _explosion_size_hit = 0

    def __init__(
        self,
        role: str,
        start_t: float = 0.0,
        aggressiveness_multiplier: float = 1.0,
        activation_delay: float = 0.0,
    ) -> None:
        self.role = role
        self._t = start_t % 1.0
        self._aggr = max(0.5, aggressiveness_multiplier)
        self.health = self.HEALTH
        self.dead = False
        self.hit_timer = 0.0
        self.anim_time = 0.0

        self._dark, self._mid, self._bright = self._ROLE_PALETTE.get(
            role, self._ROLE_PALETTE["laser"]
        )

        # Rotação própria (visual) do anel/filamentos.
        self._spin = random.uniform(0.0, 2.0 * math.pi)
        self._spin_speed = random.choice((-1.0, 1.0)) * random.uniform(1.4, 2.4)

        # Nascimento e morte.
        self._birth = True
        self._birth_t = self.BIRTH_TIME
        self._dying = False
        self._death_t = 0.0
        self._frags: List[list] = []

        # FSM de combate: começa em REPOUSO; `activation_delay` adia o 1º ataque
        # (escalona as 4 sentinelas). `_charge` (0→1) é o progresso do telegrafo.
        self._state = _S_IDLE
        self._state_t = self._idle_dur() + max(0.0, activation_delay)
        self._charge = 0.0
        self._aim_dur = self._ROLE_AIM.get(role, 0.8)
        self._flash = 0.0
        self.x, self.y = self._calculate_pos(self._t)
        self._aim_x, self._aim_y = self.x, self.y  # alvo travado no início da preparação

        self._rect = pygame.Rect(0, 0, int(self.RADIUS * 2), int(self.RADIUS * 2))
        self._sync_rect()

    # ── Geometria / colisão ────────────────────────────────────────────────
    def _calculate_pos(self, t: float) -> tuple[float, float]:
        """(x, y) ao longo do PERÍMETRO da arena, parametrizado por comprimento de arco
        (velocidade uniforme; topo → direita → base → esquerda em loop)."""
        w, h = Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT
        left, right = _EDGE_INSET, w - _EDGE_INSET
        top, bottom = _EDGE_INSET, h - _EDGE_INSET
        seg_w = right - left
        seg_h = bottom - top
        perim = 2.0 * (seg_w + seg_h)
        d = (t % 1.0) * perim

        if d <= seg_w:  # topo: TL → TR
            return left + d, top
        d -= seg_w
        if d <= seg_h:  # direita: TR → BR
            return right, top + d
        d -= seg_h
        if d <= seg_w:  # base: BR → BL
            return right - d, bottom
        d -= seg_w
        return left, bottom - d  # esquerda: BL → TL

    def _sync_rect(self) -> None:
        self._rect.center = (int(self.x), int(self.y))

    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    @property
    def causes_damage(self) -> bool:
        return not self._birth and not self._dying and not self.dead

    def collision_circle(self) -> tuple[float, float, float]:
        if self._birth or self._dying or self.dead:
            return -1000.0, -1000.0, 0.0
        return self.x, self.y, self.RADIUS

    def take_damage(self, amount: int) -> None:
        if self._birth or self._dying or self.dead:
            return
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self._start_death()

    def _start_death(self) -> None:
        if not self._dying:
            self._dying = True
            self._death_t = self.DEATH_BURST
            self._spawn_death_fragments()

    def _spawn_death_fragments(self) -> None:
        self._frags = []
        for _ in range(vq.particles(9)):
            ang = random.uniform(0.0, 2.0 * math.pi)
            spd = random.uniform(90.0, 300.0)
            self._frags.append([
                self.x, self.y,                            # 0,1 pos
                math.cos(ang) * spd, math.sin(ang) * spd,  # 2,3 vel
                random.uniform(2.5, 6.0),                  # 4 tamanho
                random.random() < 0.4,                     # 5 hot
            ])

    def get_points_value(self) -> int:
        return self.POINTS

    def on_hit(self, damage: int, _hx: float, _hy: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult

        if self._birth or self._dying or self.dead:
            return HitResult()
        self.take_damage(damage)
        if self._dying:  # morreu neste hit
            return HitResult(killed=True, points=self.POINTS, sound=hit_sounds.EXPLOSION_ALIEN)
        return HitResult(sound=hit_sounds.BOSS_DAMAGE)

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ...systems import hit_sounds
        from ...systems.hit_result import HitResult
        return HitResult(sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool:
        return self.dead

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        if dt <= 0.0:
            return
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)
        if self._flash > 0.0:
            self._flash = max(0.0, self._flash - dt)
        self._spin += self._spin_speed * dt

        if self._dying:
            self._death_t -= dt
            for f in self._frags:
                f[0] += f[2] * dt
                f[1] += f[3] * dt
                f[2] *= 0.95
                f[3] *= 0.95
            if self._death_t <= 0.0:
                self.dead = True
            return

        # Patrulha o perímetro (velocidade inalterada), inclusive nascendo.
        self._t = (self._t + self.BASE_SPEED * dt) % 1.0
        self.x, self.y = self._calculate_pos(self._t)
        self._sync_rect()

        if self._birth:
            self._birth_t -= dt
            if self._birth_t <= 0.0:
                self._birth = False
            return

        self._update_combat(dt, ctx)

    def _idle_dur(self) -> float:
        return self._ROLE_IDLE.get(self.role, 1.1) / self._aggr

    def _update_combat(self, dt: float, ctx: "EnemyUpdateContext") -> None:
        """FSM REPOUSO → PREPARAÇÃO(telegrafo) → DISPARO → RECUPERAÇÃO. Alvo TRAVADO
        no início da preparação (telegrafo honesto)."""
        st = self._state
        self._state_t -= dt

        if st == _S_IDLE:
            self._charge = 0.0
            if self._state_t <= 0.0:
                self._aim_x, self._aim_y = ctx.player_x, ctx.player_y
                self._aim_dur = self._ROLE_AIM.get(self.role, 0.8)
                self._state, self._state_t = _S_AIM, self._aim_dur
        elif st == _S_AIM:
            self._charge = max(0.0, min(1.0, 1.0 - self._state_t / self._aim_dur))
            if self._state_t <= 0.0:
                self._flash = 0.22
                self._charge = 1.0
                self._state, self._state_t = _S_FIRE, self.FIRE_TIME
                ctx.new_enemies.extend(self._fire())
        elif st == _S_FIRE:
            if self._state_t <= 0.0:
                self._charge = 0.0
                self._state, self._state_t = _S_RECOVER, self.RECOVER_TIME / self._aggr
        else:  # RECUPERAÇÃO
            if self._state_t <= 0.0:
                self._state, self._state_t = _S_IDLE, self._idle_dur()

    def _fire(self) -> List[object]:
        ax, ay = self._aim_x, self._aim_y
        if self.role == "neon":
            return [NeonBurstShot(self.x, self.y, ax, ay)]
        if self.role == "missile":
            return [MicroMissile(self.x, self.y, ax, ay)]
        if self.role == "laser":
            col = max(40.0, min(Config.SCREEN_WIDTH - 40.0, ax))
            return [VerticalLaser(col)]
        if self.role == "emp":
            return [EMPPulse(self.x, self.y)]
        return []

    # ── Render (§3) ───────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        if self._dying:
            self._draw_death(surface)
            return
        if self._birth:
            self._draw_birth(surface)
            return
        self._draw_active(surface)

    def _draw_active(self, surface: pygame.Surface) -> None:
        st = self._state
        hit = self.hit_timer > 0.0

        if st == _S_AIM:
            energy, vib = 0.85 + 0.45 * self._charge, 1.0 + 2.0 * self._charge
        elif st == _S_FIRE:
            energy, vib = 1.6, 0.0
        elif st == _S_RECOVER:
            energy, vib = 0.55, 0.0
        else:
            energy, vib = 0.75, 0.0

        # Telegrafo por cor (atrás de tudo) na preparação.
        if st == _S_AIM:
            self._draw_telegraph(surface)

        cx = self.x + (random.uniform(-vib, vib) if vib else 0.0)
        cy = self.y + (random.uniform(-vib, vib) if vib else 0.0)
        x, y = int(cx), int(cy)
        pulse = 0.5 + 0.5 * math.sin(self.anim_time * 5.0)
        rr = self.RADIUS * (1.0 + 0.05 * math.sin(self.anim_time * 4.0))

        # Halo respirando (intensidade pelo estado).
        halo_r = int(rr + 8 + 4 * pulse)
        halo_a = max(30, min(140, int(60 * energy + 30 * pulse)))
        halo = pygame.Surface((halo_r * 2, halo_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(halo, (*self._mid, halo_a), (halo_r, halo_r), halo_r)
        surface.blit(halo, (x - halo_r, y - halo_r))

        # Anel tecnológico externo (hexágono girando + nós).
        hexpts = self._ngon(cx, cy, 6, rr + 5, self._spin * 0.5)
        pygame.draw.polygon(surface, self._dark, [(int(hx), int(hy)) for hx, hy in hexpts], 1)
        for hx, hy in hexpts:
            pygame.draw.circle(surface, self._bright, (int(hx), int(hy)), 2)

        # Esfera de energia em camadas (dark → mid → bright → núcleo branco-quente).
        body = _NEON_WHITE if hit else self._mid
        pygame.draw.circle(surface, self._dark, (x, y), int(rr))
        pygame.draw.circle(surface, body, (x, y), int(rr * 0.78))
        pygame.draw.circle(surface, self._bright, (x, y), int(rr * 0.46))
        core_r = int(rr * (0.24 + 0.06 * pulse) + 1)
        pygame.draw.circle(surface, _NEON_WHITE, (x, y), core_r)
        pygame.draw.circle(surface, self._bright, (x, y), int(rr), 2)

        # Filamentos internos girando (vivacidade; crepitar — §3).
        for k in range(3):
            a = self._spin + k * (2.0 * math.pi / 3.0)
            ex = x + math.cos(a) * rr * 0.85
            ey = y + math.sin(a) * rr * 0.85
            if random.random() < (0.7 if st == _S_AIM else 0.45):
                bolt = _jagged(x, y, ex, ey, jitter=3.0, segs=3)
                pygame.draw.lines(surface, self._bright, False, [(int(bx), int(by)) for bx, by in bolt], 1)

        # Satélites orbitando (movimento secundário).
        for i in range(3):
            sa = self.anim_time * 1.6 + i * (2.0 * math.pi / 3.0)
            srx = int(cx + math.cos(sa) * (rr + 9))
            sry = int(cy + math.sin(sa) * (rr + 9))
            pygame.draw.circle(surface, self._bright, (srx, sry), 2 if st == _S_AIM else 1)

        # Anel de carga apertando (preparação) → clarão (disparo).
        if st == _S_AIM:
            ring_r = int(rr + 14 - 10 * self._charge)
            ca = 0.4 + 0.6 * self._charge
            col = (int(self._bright[0] * ca), int(self._bright[1] * ca), int(self._bright[2] * ca))
            pygame.draw.circle(surface, col, (x, y), max(1, ring_r), 2)
        elif st == _S_FIRE:
            fr = int(rr + 6 + 22 * (self._flash / self.FIRE_TIME))
            pygame.draw.circle(surface, _NEON_WHITE, (x, y), max(1, fr), 2)

        self._draw_health_bar(surface, x, y)

    def _draw_health_bar(self, surface: pygame.Surface, cx: int, cy: int) -> None:
        bw = int(self.RADIUS * 2)
        by = max(2, min(Config.SCREEN_HEIGHT - 7, cy - int(self.RADIUS) - 10))
        bx = cx - bw // 2
        pygame.draw.rect(surface, (30, 30, 30), (bx, by, bw, 5))
        frac = max(0.0, self.health / self.HEALTH)
        pygame.draw.rect(surface, self._mid, (bx, by, int(bw * frac), 5))

    def _draw_telegraph(self, surface: pygame.Surface) -> None:
        """Sinal claro do ataque (alvo TRAVADO), distinto por papel/cor."""
        tp = self._charge
        cx, cy = self.x, self.y
        ax, ay = self._aim_x, self._aim_y
        a = 0.3 + 0.6 * tp
        col = (int(self._bright[0] * a), int(self._bright[1] * a), int(self._bright[2] * a))

        if self.role == "neon":          # linha de mira reta
            ang = math.atan2(ay - cy, ax - cx)
            ex, ey = cx + math.cos(ang) * 1100.0, cy + math.sin(ang) * 1100.0
            pygame.draw.line(surface, col, (int(cx), int(cy)), (int(ex), int(ey)), 1 if tp < 0.7 else 2)
            if tp > 0.55 and int(self.anim_time * 20) % 2 == 0:
                pygame.draw.circle(surface, self._bright, (int(ax), int(ay)), 7, 1)
        elif self.role == "missile":     # anel + chevrons girando (rastreia)
            rr = int(self.RADIUS + 12 + 6 * tp)
            pygame.draw.circle(surface, col, (int(cx), int(cy)), rr, 1)
            for k in range(3):
                ca2 = self.anim_time * 3.0 + k * (2.0 * math.pi / 3.0)
                pygame.draw.circle(
                    surface, self._bright,
                    (int(cx + math.cos(ca2) * rr), int(cy + math.sin(ca2) * rr)), 3,
                )
        elif self.role == "laser":       # coluna-alvo destacada (onde o feixe cai)
            colx = int(max(40.0, min(Config.SCREEN_WIDTH - 40.0, ax)))
            if int(self.anim_time * 18) % 2 == 0 or tp > 0.7:
                pygame.draw.line(surface, col, (colx, 0), (colx, Config.SCREEN_HEIGHT), 1 if tp < 0.7 else 2)
        else:                            # emp: anel de área crescendo ao redor
            zr = int(self.RADIUS + 8 + 70 * tp)
            pygame.draw.circle(surface, col, (int(cx), int(cy)), zr, 2)

    @staticmethod
    def _ngon(cx: float, cy: float, n: int, radius: float, angle: float):
        step = 2.0 * math.pi / n
        return [
            (cx + math.cos(angle + i * step) * radius, cy + math.sin(angle + i * step) * radius)
            for i in range(n)
        ]

    def _draw_birth(self, surface: pygame.Surface) -> None:
        """Materialização energética: partículas convergindo → arcos condensando →
        ESTABILIZAÇÃO (anel contraindo + ignição). `draw` puro (§3)."""
        x, y = int(self.x), int(self.y)
        p = 1.0 - max(0.0, self._birth_t) / self.BIRTH_TIME  # 0 → 1
        cos, sin = math.cos, math.sin

        gather = self.RADIUS * (3.0 - 2.0 * p)
        for k in range(vq.particles(10)):
            ang = self._spin * 0.5 + k * (2.0 * math.pi / 10.0) + random.uniform(-0.3, 0.3)
            d = gather * random.uniform(0.5, 1.2)
            base = self._bright if random.random() < 0.4 else self._mid
            ga = (0.4 + 0.6 * (1.0 - p)) * random.uniform(0.6, 1.0)
            gc = (int(base[0] * ga), int(base[1] * ga), int(base[2] * ga))
            surface.fill(gc, (int(x + cos(ang) * d), int(y + sin(ang) * d), 2, 2))

        if p > 0.15:
            for _ in range(vq.electric(2 + int(p * 4))):
                ang = random.uniform(0.0, 2.0 * math.pi)
                d = gather * random.uniform(0.6, 1.05)
                axx, ayy = x + cos(ang) * d, y + sin(ang) * d
                lc = self._bright if random.random() < 0.6 else (220, 245, 255)
                pts = _jagged(axx, ayy, x, y, jitter=4.0 + 5.0 * (1.0 - p), segs=4)
                pygame.draw.lines(surface, lc, False, [(int(px), int(py)) for px, py in pts], 1)

        # Esfera fechando (cresce + ganha brilho).
        rr = int(self.RADIUS * (0.3 + 0.7 * p))
        if rr > 0:
            pygame.draw.circle(surface, (int(self._mid[0] * p), int(self._mid[1] * p), int(self._mid[2] * p)), (x, y), rr)
            pygame.draw.circle(surface, (int(self._bright[0] * p), int(self._bright[1] * p), int(self._bright[2] * p)), (x, y), max(1, int(rr * 0.5)))

        # Estabilização (0.8→1.0): anel contraindo + flicker assentando.
        if p > 0.8:
            snap = (p - 0.8) / 0.2
            sr = int(self.RADIUS * (1.8 - 0.8 * snap))
            sa = 1.0 - snap
            sc = (int(225 * sa + 30), int(245 * sa + 10), 255)
            pygame.draw.circle(surface, sc, (x, y), max(1, sr), 2)
            if snap < 0.6 and random.random() < 0.4:
                pygame.draw.circle(surface, _NEON_WHITE, (x, y), int(self.RADIUS * 0.6), 1)

    def _draw_death(self, surface: pygame.Surface) -> None:
        """Destruição impactante: implosão → ESTOURO (onda de choque + fragmentos +
        descarga + estática) → afterglow residual. `draw` puro (§3)."""
        t = 1.0 - max(0.0, self._death_t) / self.DEATH_BURST  # 0 → 1
        x, y = int(self.x), int(self.y)
        cos, sin = math.cos, math.sin

        if t < 0.2:  # IMPLOSÃO: esfera suga p/ dentro + carrega o estouro.
            it = t / 0.2
            pygame.draw.circle(surface, self._bright, (x, y), max(1, int(self.RADIUS * (1.0 - 0.6 * it))), 2)
            pygame.draw.circle(surface, _NEON_WHITE, (x, y), max(1, int(self.RADIUS * 0.3 * (1.0 - it))))
            return

        bt = (t - 0.2) / 0.8
        ba = 1.0 - bt

        # Onda de choque.
        r = int(self.RADIUS * (0.6 + 3.2 * bt))
        if r > 0 and ba > 0.0:
            ring = (int(self._bright[0] * ba), int(self._bright[1] * ba), int(self._bright[2] * ba))
            pygame.draw.circle(surface, ring, (x, y), r, max(1, int(3 * ba)))

        # Fragmentos de energia projetados (fragmentação).
        for f in self._frags:
            base = _NEON_WHITE if f[5] else self._mid
            fc = (int(base[0] * ba), int(base[1] * ba), int(base[2] * ba))
            pygame.draw.circle(surface, fc, (int(f[0]), int(f[1])), max(1, int(f[4] * (0.5 + 0.5 * ba))))

        # Descarga elétrica para fora.
        for _ in range(vq.electric(1 + int(ba * 5))):
            ang = random.uniform(0.0, 2.0 * math.pi)
            reach = self.RADIUS * (1.2 + 2.4 * bt)
            ex, ey = x + cos(ang) * reach, y + sin(ang) * reach
            lc = (230, 248, 255) if random.random() < 0.5 else self._bright
            pts = _jagged(x, y, ex, ey, jitter=6.0 * ba + 2.0, segs=4)
            pygame.draw.lines(surface, lc, False, [(int(px), int(py)) for px, py in pts], 1)

        # Estática espalhando.
        for _ in range(vq.particles(int(8 * ba) + 1)):
            ang = random.uniform(0.0, 2.0 * math.pi)
            d = r * random.uniform(0.4, 1.05)
            base = _NEON_WHITE if random.random() < 0.45 else self._mid
            sc = (int(base[0] * ba), int(base[1] * ba), int(base[2] * ba))
            surface.fill(sc, (int(x + cos(ang) * d), int(y + sin(ang) * d), 2, 2))

        # Afterglow residual.
        if bt > 0.55:
            ga = 1.0 - (bt - 0.55) / 0.45
            gr = int(self.RADIUS * 1.6 * ga)
            if gr > 0:
                glow = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
                pygame.draw.circle(glow, (*self._mid, int(120 * ga)), (gr, gr), gr)
                surface.blit(glow, (x - gr, y - gr))
