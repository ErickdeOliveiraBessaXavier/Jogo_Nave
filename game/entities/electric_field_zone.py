"""Campo elétrico temporário deixado pelos orbes da Torreta Orbital.

Quando um `OrbitalEnergyOrb` sobrevive e chega à posição memorizada do jogador,
ele se converte neste campo. Ciclo de vida em três fases:

  expand    → crescimento gradual a partir do ponto de impacto (telegrama,
              ainda sem dano);
  active    → ~2.5s de dano contínuo a qualquer nave dentro da área, além de
              aplicar o debuff elétrico (paralisia — ver `Ship`);
  dissipate → animação de dissipação: a energia enfraquece, encolhe e perde
              intensidade antes de sumir (sem dano).

Dano à nave segue o molde da `FireZone`: a cena consome `ship_hits` retornado
por `Collisions.electric_fields_vs_ships`, com cadência por `DAMAGE_INTERVAL`
(`can_damage`/`register_hit` da `ZoneBase`). `draw()` só desenha (§3).
"""

import math
import random

import pygame

from .zone_base import ZoneBase, ZoneParticle

ELECTRIC_BLUE = (110, 190, 255)
ELECTRIC_PALE = (200, 240, 255)
ELECTRIC_WHITE = (255, 255, 255)
ELECTRIC_DEEP = (50, 110, 200)


class _SparkParticle(ZoneParticle):
    """Faísca elétrica: segmento serrilhado curto que pisca e some."""

    @property
    def current_size(self) -> float:
        return self.base_size * max(0.0, 1.0 - self.progress * 0.6)

    @property
    def alpha(self) -> int:
        fade_in = min(1.0, self.progress * 6.0)
        fade_out = max(0.0, 1.0 - self.progress)
        return int(255 * fade_in * fade_out)


class ElectricFieldZone(ZoneBase):
    DAMAGE_INTERVAL = 0.25  # 1 dano a cada 0.25s por nave (invuln limita na prática)

    EXPAND_DURATION = 0.45
    ACTIVE_DURATION = 2.5
    DISSIPATE_DURATION = 0.7

    _SPAWN_INTERVAL = 0.05
    _PARTICLE_LIFETIME_MIN = 0.18
    _PARTICLE_LIFETIME_MAX = 0.45

    def __init__(self, x: float, y: float, radius: int, duration: float | None = None):
        super().__init__(x, y, radius, duration or self.ACTIVE_DURATION)
        self.phase = "expand"
        self.phase_t = 0.0
        self._particles: list[_SparkParticle] = []
        self._surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        # Estática radial: raios distribuídos uniformemente pelo círculo inteiro
        # (base igualmente espaçada + giro lento + jitter), para que a descarga
        # do centro alcance qualquer região da zona — sem buracos angulares.
        self._bolt_count = 8
        self._bolt_phase = random.uniform(0.0, math.tau)

    # ── Fases ───────────────────────────────────────────────────────────────
    @property
    def damaging(self) -> bool:
        """Só a fase ativa causa dano/debuff — expand é telegrama, dissipate é eco."""
        return self.phase == "active"

    @property
    def intensity(self) -> float:
        """Energia normalizada [0..1] usada por raio efetivo e alpha do visual."""
        if self.phase == "expand":
            t = min(1.0, self.phase_t / self.EXPAND_DURATION)
            return 1.0 - (1.0 - t) ** 3  # ease-out: estoura rápido e assenta
        if self.phase == "active":
            return 1.0
        t = min(1.0, self.phase_t / self.DISSIPATE_DURATION)
        return max(0.0, (1.0 - t) ** 2)  # decai acelerando (perde força no fim)

    @property
    def effective_radius(self) -> float:
        if self.phase == "dissipate":
            # Encolhe junto com a perda de intensidade, sem colapsar de imediato.
            return self.radius * (0.35 + 0.65 * self.intensity)
        return self.radius * max(0.15, self.intensity)

    def in_zone(self, cx: float, cy: float, r: float = 0.0) -> bool:
        er = self.effective_radius
        return (cx - self.x) ** 2 + (cy - self.y) ** 2 < (er + r) ** 2

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x, self.y, float(self.effective_radius)

    def update(self, dt: float) -> None:
        if self.dead:
            return
        self.anim_timer += dt
        self.phase_t += dt

        if self.phase == "expand" and self.phase_t >= self.EXPAND_DURATION:
            self.phase = "active"
            self.phase_t = 0.0
        elif self.phase == "active":
            self.timer -= dt
            if self.timer <= 0.0:
                self.phase = "dissipate"
                self.phase_t = 0.0
        elif self.phase == "dissipate" and self.phase_t >= self.DISSIPATE_DURATION:
            self.dead = True
            return

        for eid in list(self.hit_cooldowns):
            self.hit_cooldowns[eid] -= dt
            if self.hit_cooldowns[eid] <= 0:
                del self.hit_cooldowns[eid]

        i = len(self._particles) - 1
        while i >= 0:
            p = self._particles[i]
            p.update(dt)
            if not p.alive:
                self._particles.pop(i)
            i -= 1

        # Dissipando, a geração de faíscas rareia junto com a intensidade.
        spawn_interval = self._SPAWN_INTERVAL / max(0.15, self.intensity)
        self._spawn_timer += dt
        while self._spawn_timer >= spawn_interval:
            self._spawn_timer -= spawn_interval
            self._spawn_particle()

    def _spawn_particle(self) -> None:
        angle = random.uniform(0.0, math.tau)
        dist = self.effective_radius * 0.92 * math.sqrt(random.random())
        self._particles.append(
            _SparkParticle(
                x=self.x + math.cos(angle) * dist,
                y=self.y + math.sin(angle) * dist,
                lifetime=random.uniform(
                    self._PARTICLE_LIFETIME_MIN, self._PARTICLE_LIFETIME_MAX
                ),
                base_size=random.uniform(self.radius * 0.06, self.radius * 0.16),
                rotation=random.uniform(0.0, math.tau),
                rot_speed=random.uniform(-8.0, 8.0),
            )
        )

    # ── Render ──────────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        intensity = self.intensity
        if intensity <= 0.01:
            return
        er = self.effective_radius
        r = self.radius  # tamanho da surface local (fixo)

        s = self._surface
        s.fill((0, 0, 0, 0))

        flicker = 0.82 + 0.18 * math.sin(self.anim_timer * 31.0)
        glow_a = int(38 * intensity * flicker)
        ring_a = int(170 * intensity * flicker)

        # Núcleo translúcido + anel externo serrilhado (contorno "elétrico").
        pygame.draw.circle(s, (*ELECTRIC_DEEP, glow_a), (r, r), int(er))
        ring_pts = self._noisy_ring_points(r, er, intensity)
        if len(ring_pts) >= 3:
            pygame.draw.polygon(s, (*ELECTRIC_BLUE, ring_a), ring_pts, 2)

        # Raios radiais do centro: ângulos igualmente espaçados girando devagar,
        # cobrindo o círculo inteiro de forma homogênea. O comprimento varia de
        # ~40% a 100% do raio para alcançar tanto o miolo quanto a borda — toda a
        # área lida como energizada, alimentada pelo centro.
        bolt_a = int(200 * intensity * flicker)
        n = self._bolt_count
        base = self._bolt_phase + self.anim_timer * 1.4
        step = math.tau / n
        for k in range(n):
            ang = base + k * step + random.uniform(-0.22, 0.22)
            length = er * random.uniform(0.4, 1.0)
            self._draw_bolt(s, r, r, ang, length, bolt_a)

        # Faíscas (segmentos curtos rotacionados).
        for p in self._particles:
            alpha = int(p.alpha * intensity)
            if alpha <= 0:
                continue
            size = p.current_size
            if size < 1.0:
                continue
            lx = p.x - (self.x - r)
            ly = p.y - (self.y - r)
            ca = math.cos(p.rotation) * size
            sa = math.sin(p.rotation) * size
            color = ELECTRIC_WHITE if random.random() < 0.3 else ELECTRIC_PALE
            pygame.draw.line(
                s, (*color, alpha), (lx - ca, ly - sa), (lx + ca, ly + sa), 2
            )

        # Estática: pixels soltos cintilando dentro do campo.
        static_count = int(10 * intensity)
        for _ in range(static_count):
            ang = random.uniform(0.0, math.tau)
            dist = er * math.sqrt(random.random())
            px = int(r + math.cos(ang) * dist)
            py = int(r + math.sin(ang) * dist)
            a = random.randint(60, 200)
            s.fill((*ELECTRIC_PALE, int(a * intensity)), (px, py, 2, 2))

        surface.blit(s, (int(self.x) - r, int(self.y) - r))

    def _noisy_ring_points(
        self, center: int, ring_radius: float, intensity: float
    ) -> list[tuple[float, float]]:
        """Anel com raio perturbado — leitura de instabilidade elétrica.

        `center` é o centro da surface local (r, r) — um valor serve aos dois eixos.
        """
        pts: list[tuple[float, float]] = []
        n = 26
        t = self.anim_timer
        for k in range(n):
            ang = math.tau * k / n
            wobble = math.sin(ang * 5.0 + t * 14.0) * 2.5 + random.uniform(-1.5, 1.5)
            rr = ring_radius + wobble * intensity
            pts.append((center + math.cos(ang) * rr, center + math.sin(ang) * rr))
        return pts

    @staticmethod
    def _draw_bolt(
        s: pygame.Surface,
        cx: int,
        cy: int,
        angle: float,
        length: float,
        alpha: int,
    ) -> None:
        """Raio serrilhado do centro para fora: 3 segmentos com desvio lateral."""
        steps = 3
        px, py = float(cx), float(cy)
        ca, sa = math.cos(angle), math.sin(angle)
        for i in range(1, steps + 1):
            t = i / steps
            off = random.uniform(-6.0, 6.0) if i < steps else 0.0
            nx = cx + ca * length * t - sa * off
            ny = cy + sa * length * t + ca * off
            color = ELECTRIC_WHITE if i == 1 else ELECTRIC_BLUE
            pygame.draw.line(s, (*color, alpha), (px, py), (nx, ny), 2)
            px, py = nx, ny

    def should_remove(self) -> bool:
        return self.dead
