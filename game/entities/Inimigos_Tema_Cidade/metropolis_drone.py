"""Drone-triângulo energético do Metropolis Overlord (ataque da Fase 2).

Pequenos triângulos luminosos que o boss libera como "fragmentos" da própria
energia. Perseguição PROPOSITALMENTE BURRA (sem previsão, sem interceptação):
escolhem o jogador, aceleram na direção dele e fazem correções lentas e imprecisas
— podem ultrapassar a nave, sair da tela e não orbitam para sempre (vida curta +
a correção decai, então no fim voam reto). A cor vem do tema do núcleo ativo do
boss (cyan/magenta/amber), reforçando a identidade visual.

Vive em `em.enemies` (roteado por `result.spawned_enemies`): herda colisão/draw/
cleanup do contrato comum (`EnemyHitMixin`), zero plumbing nova. `draw` sem efeito
colateral (§3); mutação (movimento, rastro, faíscas, morte) só no update.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List, Tuple

import pygame

from ...core.config import config as Config
from ..enemy_hit_mixin import EnemyHitMixin
from . import metropolis_overlord_pixel_map as pmap

if TYPE_CHECKING:
    from ...systems.entity_context import EnemyUpdateContext
    from ...systems.hit_result import HitResult


def _off_screen(x: float, y: float, margin: float = 70.0) -> bool:
    return (
        x < -margin
        or x > Config.SCREEN_WIDTH + margin
        or y < -margin
        or y > Config.SCREEN_HEIGHT + margin
    )


class EnergyTriangleDrone(EnemyHitMixin):
    """Fragmento energético triangular com perseguição simples e instável."""

    is_boss: bool = False
    HEALTH: int = 6
    POINTS: int = 60
    SIZE: float = 13.0              # meia-altura do triângulo (raio de colisão ~igual)

    INITIAL_SPEED: float = 90.0
    ACCEL: float = 300.0
    MAX_SPEED: float = 370.0
    TURN_RATE: float = 1.4         # rad/s — correção LENTA e imprecisa
    CORRECT_WINDOW: float = 2.0    # s; depois disso para de corrigir (voa reto)
    LIFETIME: float = 5.5

    BIRTH_TIME: float = 0.34       # nascimento: portal/condensação → forma materializa
    SPIN_MIN: float = 2.4          # rad/s — rotação própria (só visual, não afeta rumo)
    SPIN_MAX: float = 3.8
    DEATH_BURST: float = 0.26      # duração da explosão energética simples

    _explosion_size_killed = 0     # explosão é própria (energética), não a genérica
    _explosion_size_hit = 0

    def __init__(
        self,
        x: float,
        y: float,
        target_x: float,
        target_y: float,
        theme: str,
        aggressiveness_multiplier: float = 1.0,
    ) -> None:
        self.x = float(x)
        self.y = float(y)
        self.theme = theme
        self._aggr = max(0.5, aggressiveness_multiplier)
        self.health = self.HEALTH
        self.dead = False
        self.hit_timer = 0.0
        self.anim_time = 0.0
        self._age = 0.0
        self.lifetime = self.LIFETIME

        # Cores do tema do núcleo (dark, mid, bright).
        self._dark, self._mid, self._bright = pmap.PLASMA_THEMES.get(theme, pmap.PLASMA_THEMES["cyan"])

        # Rumo inicial APROXIMADO ao jogador (com jitter — impulsivo, não preciso).
        self.heading = math.atan2(target_y - y, target_x - x) + random.uniform(-0.5, 0.5)
        self.speed = self.INITIAL_SPEED

        # Rotação própria contínua (só visual, NÃO altera o rumo): ângulo + velocidade
        # com sinal/intensidade aleatórios (instabilidade energética por drone).
        self._spin = random.uniform(0.0, 2.0 * math.pi)
        self._spin_speed = random.choice((-1.0, 1.0)) * random.uniform(self.SPIN_MIN, self.SPIN_MAX)

        # Nascimento: emerge por um portal/condensação antes de perseguir.
        self._birth = True
        self._birth_t = self.BIRTH_TIME

        self._trail: List[Tuple[float, float]] = []
        self._sparks: List[List[float]] = []  # [x, y, vx, vy, life, maxlife]
        self._spark_timer = 0.0

        self._dying = False
        self._death_t = 0.0

        self._rect = pygame.Rect(0, 0, int(self.SIZE * 2), int(self.SIZE * 2))
        self._sync_rect()

    # ── Geometria / colisão ────────────────────────────────────────────────
    def _sync_rect(self) -> None:
        self._rect.center = (int(self.x), int(self.y))

    @property
    def rect(self) -> pygame.Rect:
        return self._rect

    @property
    def causes_damage(self) -> bool:
        return not self._birth and not self._dying and not self.dead

    def collision_circle(self) -> tuple[float, float, float]:
        # Em nascimento/morte o drone não colide (está se formando/dissipando).
        if self._birth or self._dying or self.dead:
            return -1000.0, -1000.0, 0.0
        return self.x, self.y, self.SIZE * 0.85

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self._start_death()

    def get_points_value(self) -> int:
        return self.POINTS

    def _start_death(self) -> None:
        if not self._dying:
            self._dying = True
            self._death_t = self.DEATH_BURST

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

        self._start_death()
        return HitResult(sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead or (self._dying and self._death_t <= 0.0)

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        dt = ctx.sdt
        if dt <= 0.0:
            return
        self.anim_time += dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)
        self._update_sparks(dt)
        # Rotação própria contínua (visual), inclusive enquanto nasce/morre.
        self._spin += self._spin_speed * dt

        if self._dying:
            self._death_t -= dt
            return

        if self._birth:
            # Emerge pelo portal/condensação; ainda não se move nem persegue.
            self._birth_t -= dt
            if self._birth_t <= 0.0:
                self._birth = False
            return

        self._age += dt
        self.lifetime -= dt

        # Correção LENTA e imprecisa rumo ao jogador, decaindo até parar (impulsivo).
        if self._age < self.CORRECT_WINDOW:
            desired = math.atan2(ctx.player_y - self.y, ctx.player_x - self.x)
            diff = (desired - self.heading + math.pi) % (2 * math.pi) - math.pi
            fade = 1.0 - self._age / self.CORRECT_WINDOW
            lim = self.TURN_RATE * fade * dt
            self.heading += max(-lim, min(lim, diff))

        self.speed = min(self.MAX_SPEED, self.speed + self.ACCEL * dt)
        self.x += math.cos(self.heading) * self.speed * dt
        self.y += math.sin(self.heading) * self.speed * dt
        self._sync_rect()

        # Rastro energético curto.
        self._trail.append((self.x, self.y))
        if len(self._trail) > 8:
            del self._trail[0]

        # Faíscas pequenas durante o movimento.
        self._spark_timer -= dt
        if self._spark_timer <= 0.0:
            self._spark_timer = 0.04
            ang = self.heading + math.pi + random.uniform(-0.8, 0.8)
            sp = random.uniform(20.0, 70.0)
            self._sparks.append([
                self.x, self.y, math.cos(ang) * sp, math.sin(ang) * sp,
                random.uniform(0.2, 0.45), 0.45,
            ])

        if self.lifetime <= 0.0:
            self._start_death()   # expira na arena → explosão energética simples
        elif _off_screen(self.x, self.y):
            self.dead = True      # saiu da arena → some (invisível, sem efeito)

    def _update_sparks(self, dt: float) -> None:
        sparks = self._sparks
        w = 0
        for s in sparks:
            s[4] -= dt
            if s[4] > 0.0:
                s[0] += s[2] * dt
                s[1] += s[3] * dt
                sparks[w] = s
                w += 1
        del sparks[w:]

    # ── Render (§3) ───────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        if self._dying:
            self._draw_death(surface)
            return
        if self._birth:
            self._draw_birth(surface)
            return

        # Rastro: pontos do tema esmaecendo para trás.
        n = len(self._trail)
        for i, (tx, ty) in enumerate(self._trail):
            a = (i + 1) / max(1, n)
            r = max(1, int(self.SIZE * 0.5 * a))
            col = (int(self._mid[0] * a), int(self._mid[1] * a), int(self._mid[2] * a))
            pygame.draw.circle(surface, col, (int(tx), int(ty)), r)

        # Faíscas.
        for s in self._sparks:
            a = max(0.0, s[4] / s[5])
            col = (int(self._bright[0] * a), int(self._bright[1] * a), int(self._bright[2] * a))
            pygame.draw.circle(surface, col, (int(s[0]), int(s[1])), max(1, int(2 * a)))

        # Corpo: triângulo equilátero girando no próprio eixo (orientação = `_spin`,
        # independente do rumo de deslocamento).
        pts = self._tri_points(self.x, self.y, self._spin, self.SIZE)
        body = (255, 255, 255) if self.hit_timer > 0.0 else self._mid
        pygame.draw.polygon(surface, body, pts)
        pygame.draw.polygon(surface, self._bright, pts, 2)
        pygame.draw.circle(surface, self._bright, (int(self.x), int(self.y)), max(1, int(self.SIZE * 0.3)))

    def _draw_birth(self, surface: pygame.Surface) -> None:
        """Nascimento: anel de condensação contraindo + cacos convergindo + o
        triângulo se materializando (escala/brilho subindo). Render puro (§3)."""
        x, y = int(self.x), int(self.y)
        p = 1.0 - max(0.0, self._birth_t) / self.BIRTH_TIME  # 0 → 1

        # Anel de portal/condensação contraindo conforme a energia se concentra.
        ring_r = int(self.SIZE * (2.1 - 1.1 * p))
        ring_a = (1.0 - p) * 0.9
        rc = (int(self._bright[0] * ring_a), int(self._bright[1] * ring_a), int(self._bright[2] * ring_a))
        if ring_r > 0:
            pygame.draw.circle(surface, rc, (x, y), ring_r, 2)

        # Cacos de energia convergindo para o centro (condensação).
        gather = self.SIZE * 2.2 * (1.0 - p)
        for i in range(5):
            ang = self._spin + i * (2.0 * math.pi / 5.0)
            gx = int(x + math.cos(ang) * gather)
            gy = int(y + math.sin(ang) * gather)
            pygame.draw.circle(surface, rc, (gx, gy), max(1, int(2 * (1.0 - p) + 1)))

        # Triângulo materializando: escala e brilho sobem com o progresso.
        scale = 0.25 + 0.75 * p
        pts = self._tri_points(self.x, self.y, self._spin, self.SIZE * scale)
        body = (int(self._mid[0] * p), int(self._mid[1] * p), int(self._mid[2] * p))
        pygame.draw.polygon(surface, body, pts)
        ec = (int(self._bright[0] * p), int(self._bright[1] * p), int(self._bright[2] * p))
        pygame.draw.polygon(surface, ec, pts, 2)

    def _draw_death(self, surface: pygame.Surface) -> None:
        """Explosão energética simples: anel expandindo + flash do tema."""
        t = 1.0 - max(0.0, self._death_t) / self.DEATH_BURST
        r = int(self.SIZE * (0.8 + 2.6 * t))
        a = 1.0 - t
        col = (int(self._bright[0] * a), int(self._bright[1] * a), int(self._bright[2] * a))
        if r > 0:
            pygame.draw.circle(surface, col, (int(self.x), int(self.y)), r, max(1, int(3 * a)))
        core = (int(self._mid[0] * a), int(self._mid[1] * a), int(self._mid[2] * a))
        pygame.draw.circle(surface, core, (int(self.x), int(self.y)), max(1, int(self.SIZE * a)))

    @staticmethod
    def _tri_points(x: float, y: float, angle: float, radius: float):
        """Triângulo EQUILÁTERO (vértices 120° apart) inscrito no raio, orientação `angle`."""
        step = 2.0 * math.pi / 3.0
        return [
            (x + math.cos(angle) * radius, y + math.sin(angle) * radius),
            (x + math.cos(angle + step) * radius, y + math.sin(angle + step) * radius),
            (x + math.cos(angle + 2.0 * step) * radius, y + math.sin(angle + 2.0 * step) * radius),
        ]
