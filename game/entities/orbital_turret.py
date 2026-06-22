"""Torreta Orbital — sentinela de **zoneamento** do bioma STARFIELD.

Um **olho de energia** central (núcleo de comando, uma inteligência observando o
jogador) orbitado por **três esferas elétricas instáveis**. As esferas carregam
energia **em sequência** e disparam **uma a uma**, num ritmo previsível que o
jogador aprende a ler. Cada disparo é um `OrbitalEnergyOrb` que **memoriza a
posição do jogador** no instante do tiro e viaja até lá.

Counterplay em camadas:
  - destruir os orbes com tiros antes que cheguem (são destrutíveis); ou
  - deixá-los chegar — cada orbe que sobrevive vira um `ElectricFieldZone`
    temporário que causa dano contínuo e aplica o debuff de paralisia. Ignorar
    os disparos faz a arena acumular zonas elétricas e restringe o movimento.

Visual: o núcleo é um pixel-map cacheado (olho); a pupila rastreia o jogador. As
três esferas são procedurais (orbitam por ângulo) com arcos, cintilação e
estática. Colisão pela **silhueta real** (olho + 3 esferas) via
`collision_circles()` (§8), não uma hitbox genérica.

Contratos (convenções do projeto): herda `EnemyHitMixin` (§9); update via
`update_in_context` (§5); `draw` sem efeitos colaterais (§3); orbes emitidos por
buffer do contexto (`new_orbital_orbs`).
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, List

import pygame

from ..core.sound import sound_manager
from ..core.visual_quality import visual_quality
from . import orbital_turret_pixel_map as pm
from .enemy_hit_mixin import EnemyHitMixin
from .orbital_energy_orb import OrbitalEnergyOrb

if TYPE_CHECKING:
    from ..systems.entity_context import EnemyUpdateContext
    from ..systems.hit_result import HitResult


def _lerp(a: pm.RGB, b: pm.RGB, t: float) -> pm.RGB:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


class OrbitalTurret(EnemyHitMixin):
    SIZE = 88
    EYE_CELL = 3  # 15×15 → 45px de olho central

    HEALTH = 70
    POINTS = 250

    NUM_SPHERES = 3
    ORBIT_RADIUS = 32.0
    SPHERE_RADIUS = 8.0
    ORBIT_SPEED = 0.9  # rad/s do giro das esferas

    CHARGE_TIME = 0.9       # carga de cada esfera (telegrama), dividido por aggr
    INTER_SHOT_DELAY = 0.45  # intervalo entre disparos da mesma salva
    REST_TIME = 1.8          # descanso após as três dispararem

    _explosion_size_killed: int = 34
    _explosion_size_hit: int = 10

    def __init__(
        self,
        x: float,
        y: float,
        aggressiveness_multiplier: float = 1.0,
        side_scroll: bool = False,
    ):
        self.w = self.SIZE
        self.h = self.SIZE
        self.x = float(x)
        self.y = float(y)
        self.side_scroll = side_scroll

        self.target_y = float(random.randint(60, 160))
        self.entry_speed = 130.0
        self._entry_done = False

        self.dead = False
        self.health = self.HEALTH
        self.active = True
        self.hit_timer = 0.0

        self._aggr = max(0.5, aggressiveness_multiplier)

        # Animação cosmética (acumuladores próprios, nunca time.time() — §3).
        self.anim_time = 0.0
        self.float_phase = random.uniform(0.0, math.tau)
        self.orbit_angle = random.uniform(0.0, math.tau)

        # Pupila do olho: deslocamento suavizado em direção ao jogador.
        self.pupil_dx = 0.0
        self.pupil_dy = 0.0

        # Estado da salva sequencial das esferas.
        self.phase = "rest"  # "charge" | "delay" | "rest"
        self.active_sphere = 0
        self._charge_t = 0.0
        self._delay_t = 0.0
        self._rest_t = random.uniform(0.6, 1.4)
        self.sphere_charge = [0.0] * self.NUM_SPHERES

    # ── Geometria ───────────────────────────────────────────────────────────
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def _center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def _sphere_pos(self, index: int) -> tuple[float, float]:
        cx, cy = self._center
        ang = self.orbit_angle + index * (math.tau / self.NUM_SPHERES)
        return cx + math.cos(ang) * self.ORBIT_RADIUS, cy + math.sin(ang) * self.ORBIT_RADIUS

    def collision_circle(self) -> tuple[float, float, float]:
        # Disco envolvente (broadphase) cobrindo olho + órbita das esferas.
        cx, cy = self._center
        return cx, cy, self.ORBIT_RADIUS + self.SPHERE_RADIUS

    def collision_circles(self) -> List[tuple[float, float, float]]:
        """Silhueta real (§8): núcleo-olho + as três esferas em suas posições."""
        cx, cy = self._center
        circles: List[tuple[float, float, float]] = [
            (cx, cy, self.EYE_CELL * 7.0)  # olho central (~21px de raio)
        ]
        for i in range(self.NUM_SPHERES):
            sx, sy = self._sphere_pos(i)
            # Esfera carregando incha um pouco — hitbox acompanha o visual.
            r = self.SPHERE_RADIUS * (1.0 + 0.35 * self.sphere_charge[i])
            circles.append((sx, sy, r))
        return circles

    def get_ship_contact_hitboxes(self) -> List[pygame.Rect]:
        """Rects para o pré-filtro AABB; a validação fina usa collision_circles."""
        rects: List[pygame.Rect] = []
        cx, cy = self._center
        er = int(self.EYE_CELL * 7.0)
        rects.append(pygame.Rect(int(cx - er), int(cy - er), er * 2, er * 2))
        sr = int(self.SPHERE_RADIUS + 2)
        for i in range(self.NUM_SPHERES):
            sx, sy = self._sphere_pos(i)
            rects.append(pygame.Rect(int(sx - sr), int(sy - sr), sr * 2, sr * 2))
        return rects

    # ── Update ──────────────────────────────────────────────────────────────
    def update_in_context(self, ctx: "EnemyUpdateContext") -> None:
        orbs = self.update(ctx.sdt, ctx.player_x, ctx.player_y)
        if orbs:
            ctx.new_orbital_orbs.extend(orbs)

    def update(
        self, dt: float, player_x: float, player_y: float
    ) -> List[OrbitalEnergyOrb]:
        if dt <= 0.0:
            return []

        self.anim_time += dt
        self.orbit_angle += self.ORBIT_SPEED * dt
        if self.hit_timer > 0.0:
            self.hit_timer = max(0.0, self.hit_timer - dt)

        if not self._entry_done:
            self.y += self.entry_speed * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self._entry_done = True
            return []

        # Flutuação vertical suave.
        self.y = self.target_y + math.sin(self.anim_time * 1.5 + self.float_phase) * 6.0

        # Pupila acompanha o jogador (suavizada).
        cx, cy = self._center
        tdx, tdy = player_x - cx, player_y - cy
        tdist = math.hypot(tdx, tdy) or 1.0
        max_off = self.EYE_CELL * 2.2
        goal_dx = (tdx / tdist) * max_off
        goal_dy = (tdy / tdist) * max_off
        self.pupil_dx += (goal_dx - self.pupil_dx) * min(1.0, 6.0 * dt)
        self.pupil_dy += (goal_dy - self.pupil_dy) * min(1.0, 6.0 * dt)

        return self._advance_volley(dt, player_x, player_y)

    def _advance_volley(
        self, dt: float, player_x: float, player_y: float
    ) -> List[OrbitalEnergyOrb]:
        """Carga sequencial das esferas; retorna orbe disparado (no máx. um/frame)."""
        orbs: List[OrbitalEnergyOrb] = []
        charge_time = self.CHARGE_TIME / self._aggr

        if self.phase == "charge":
            self._charge_t += dt
            self.sphere_charge[self.active_sphere] = min(
                1.0, self._charge_t / charge_time
            )
            if self._charge_t >= charge_time:
                orbs.append(self._fire_sphere(self.active_sphere, player_x, player_y))
                self.sphere_charge[self.active_sphere] = 0.0
                if self.active_sphere < self.NUM_SPHERES - 1:
                    self.phase = "delay"
                    self._delay_t = self.INTER_SHOT_DELAY / self._aggr
                else:
                    self.phase = "rest"
                    self._rest_t = self.REST_TIME / self._aggr

        elif self.phase == "delay":
            self._delay_t -= dt
            if self._delay_t <= 0.0:
                self.active_sphere += 1
                self._charge_t = 0.0
                self.phase = "charge"

        else:  # rest
            self._rest_t -= dt
            if self._rest_t <= 0.0:
                self.active_sphere = 0
                self._charge_t = 0.0
                self.phase = "charge"

        return orbs

    def _fire_sphere(
        self, index: int, player_x: float, player_y: float
    ) -> OrbitalEnergyOrb:
        sx, sy = self._sphere_pos(index)
        sound_manager.play_shot()
        return OrbitalEnergyOrb(
            sx,
            sy,
            player_x,
            player_y,
            aggressiveness_multiplier=self._aggr,
        )

    # ── Dano / morte ────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> None:
        self.health -= amount
        self.hit_timer = 0.1
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return self.POINTS

    def on_ship_contact(self, _contact_x: float, _contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead

    # ── Render ──────────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = self._center
        hit = self.hit_timer > 0.0

        # 1) Esferas ATRÁS do olho (as que estão na metade superior da órbita).
        spheres = [
            (i, *self._sphere_pos(i)) for i in range(self.NUM_SPHERES)
        ]
        for i, sx, sy in spheres:
            if sy < cy:
                self._draw_sphere(surface, i, sx, sy)

        # 2) Núcleo-olho.
        self._draw_eye(surface, cx, cy, hit)

        # 3) Esferas À FRENTE do olho.
        for i, sx, sy in spheres:
            if sy >= cy:
                self._draw_sphere(surface, i, sx, sy)

    def _draw_eye(self, surface: pygame.Surface, cx: float, cy: float, hit: bool) -> None:
        layers = pm.build_layers(self.EYE_CELL)
        size = pm.PIXEL_COLS * self.EYE_CELL
        bx = int(cx - size / 2)
        by = int(cy - size / 2)

        hull = layers["hull"]
        eye = layers["eye"]
        if hit:
            hull = hull.copy()
            hull.fill((150, 150, 160), special_flags=pygame.BLEND_RGB_ADD)
            eye = eye.copy()
            eye.fill((150, 150, 160), special_flags=pygame.BLEND_RGB_ADD)
        surface.blit(hull, (bx, by))
        surface.blit(eye, (bx, by))

        # Glow da íris pulsando — sobe quando há esfera carregando.
        pulse = 0.5 + 0.5 * math.sin(self.anim_time * 4.0)
        charge_glow = max(self.sphere_charge) if self._entry_done else 0.0
        core_t = min(1.0, pulse * 0.5 + charge_glow * 0.6)
        glow_col = pm.EYE_GLOW if not hit else (255, 255, 255)
        glow_r = int(self.EYE_CELL * 4 + self.EYE_CELL * 3 * core_t)
        glow = pm.get_glow(glow_r, glow_col)
        surface.blit(
            glow, (int(cx) - glow_r, int(cy) - glow_r), special_flags=pygame.BLEND_RGBA_ADD
        )

        # Pupila que rastreia o jogador.
        px = int(cx + self.pupil_dx)
        py = int(cy + self.pupil_dy)
        pupil_r = max(2, int(self.EYE_CELL * 1.6))
        pygame.draw.circle(surface, pm.PUPIL, (px, py), pupil_r)
        pygame.draw.circle(surface, pm.EYE_GLOW, (px, py), pupil_r, 1)
        # Brilho de "consciência".
        glint = pm.get_glow(self.EYE_CELL, pm.SPHERE_CORE)
        surface.blit(
            glint,
            (px - self.EYE_CELL, py - self.EYE_CELL - 1),
            special_flags=pygame.BLEND_RGBA_ADD,
        )

    def _draw_sphere(
        self, surface: pygame.Surface, index: int, sx: float, sy: float
    ) -> None:
        charge = self.sphere_charge[index]
        icx, icy = int(sx), int(sy)
        is_active = self.phase == "charge" and index == self.active_sphere

        # Instabilidade: cintilação base + tremor por estática.
        flick = 0.6 + 0.4 * math.sin(self.anim_time * 18.0 + index * 2.1)
        jitter = 1.0 + charge * 1.5
        jx = icx + random.uniform(-jitter, jitter)
        jy = icy + random.uniform(-jitter, jitter)

        radius = self.SPHERE_RADIUS * (1.0 + 0.35 * charge)

        # Halo (cresce com a carga).
        halo_r = int(radius + 3 + charge * 6)
        halo_col = _lerp(pm.SPHERE_DIM, pm.SPHERE_CORE, 0.3 + 0.5 * charge)
        glow = pm.get_glow(halo_r, halo_col)
        surface.blit(
            glow, (icx - halo_r, icy - halo_r), special_flags=pygame.BLEND_RGBA_ADD
        )

        # Corpo da esfera.
        body_t = 0.3 + 0.6 * flick + 0.3 * charge
        body_col = _lerp(pm.SPHERE_DIM, pm.SPHERE_MID, min(1.0, body_t))
        pygame.draw.circle(surface, body_col, (int(jx), int(jy)), int(radius))
        pygame.draw.circle(
            surface, pm.SPHERE_CORE, (int(jx), int(jy)), max(2, int(radius * 0.45))
        )

        # Arcos elétricos saltando — mais densos quando carregando.
        arc_chance = 0.85 if is_active else 0.5
        if random.random() < arc_chance:
            self._draw_sphere_arcs(surface, icx, icy, radius, charge)

        # Cintilações/estática: pixels soltos piscando no entorno (escala/qualidade).
        static_n = visual_quality.electric(int(2 + charge * 5))
        for _ in range(static_n):
            a = random.uniform(0.0, math.tau)
            d = radius * random.uniform(0.6, 1.6)
            px = int(icx + math.cos(a) * d)
            py = int(icy + math.sin(a) * d)
            col = pm.ARC_HOT if random.random() < 0.4 else pm.ARC_COLOR
            surface.fill(col, (px, py, 2, 2))

    @staticmethod
    def _draw_sphere_arcs(
        surface: pygame.Surface, cx: int, cy: int, radius: float, charge: float
    ) -> None:
        cos, sin = math.cos, math.sin
        num = visual_quality.electric(random.randint(1, 2 + int(charge * 2)))
        for _ in range(num):
            a0 = random.uniform(0.0, math.tau)
            length = radius + random.uniform(4, 9 + charge * 8)
            # Raio serrilhado de 2 segmentos saltando para fora.
            x0, y0 = cx + cos(a0) * radius, cy + sin(a0) * radius
            mid_a = a0 + random.uniform(-0.4, 0.4)
            xm = cx + cos(mid_a) * (length * 0.6) + random.uniform(-3, 3)
            ym = cy + sin(mid_a) * (length * 0.6) + random.uniform(-3, 3)
            x1 = cx + cos(a0) * length + random.uniform(-3, 3)
            y1 = cy + sin(a0) * length + random.uniform(-3, 3)
            col = pm.ARC_HOT if random.random() < 0.5 else pm.ARC_COLOR
            pygame.draw.lines(surface, col, False, [(x0, y0), (xm, ym), (x1, y1)], 1)
