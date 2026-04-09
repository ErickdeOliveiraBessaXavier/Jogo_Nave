"""
Stone Golem Boss — Mundo 1: Cordilheira Celestial (Montanhas)

Boss do nível 10. Padrão Arc (como Boss original):
- Classe independente, sem herança
- Spawna entidades EXTERNAS (Boulder e RockShard)
- Retorna entidades para o EntityManager adicionar
- Visual pixel-art com pygame.draw (sem sprites), inspirado no arquivo HTML de referência
- EMP slowdown automático via enemy_dt

Sistema de dano ao jogador:
- O jogo usa VIDAS, não barra de HP
- GolemMine: contato direto ou explosão (shards) remove 1 vida
- RockShard e OrbitalRock (fase 'fired') também causam dano por rect collision
- A detecção é feita via rect collision em playing.py/_check_ship_damage()
- Todas as entidades expõem .rect, .dead e .causes_damage

FSM de estados (inspirada no arquivo HTML de referência):
  ENTERING    → entra pela parte superior da tela
  SCAN        → idle, olho fechado, move verticalmente (2 s)
  OPENING     → olho abre com easing (1.5 s) → CHARGE
  CHARGE      → núcleo pulsa, partículas de carga (1.5 s) → FIRE
  FIRE        → Planta 3 GolemMines na posição do jogador → CLOSING
  EARTH_SHAKE → tremor + jitter (0.8 s) → EARTH_PULL
  EARTH_PULL  → pedras sobem da borda inferior até a órbita → EARTH_ORBIT
  EARTH_ORBIT → pedras orbitam o boss (~1.2 s) → EARTH_FIRE
  EARTH_FIRE  → pedras arremessadas uma a uma no jogador → SCAN
  SWEEP_CHARGE→ olho abre para sweep (1.2 s) → SWEEP_FIRE
  SWEEP_FIRE  → cone de shards varrendo → CLOSING
  ORB_SPAWN   → olho abre roxo (0.8 s) → ORB_HOLD
  ORB_HOLD    → rajadas de Rosa dos Ventos (4 ondas) → CLOSING
  CLOSING     → olho fecha com easing → SCAN
"""

import logging
import math
import random
from typing import List, Optional, Tuple

import pygame

from ..core.config import config as Config
from ..entities.stone_golem_pixel_map import EYE_COL_END as _EYE_COL_END
from ..entities.stone_golem_pixel_map import EYE_COL_START as _EYE_COL_START
from ..entities.stone_golem_pixel_map import EYE_ROW as _EYE_ROW
from ..entities.stone_golem_pixel_map import EYE_ROW_ABOVE as _EYE_ROW_ABOVE
from ..entities.stone_golem_pixel_map import EYE_ROW_BELOW as _EYE_ROW_BELOW
from ..entities.stone_golem_pixel_map import \
    ORBITAL_ROCK_COLORS as _ORBITAL_ROCK_COLORS
from ..entities.stone_golem_pixel_map import PIXEL_COLS as _PIXEL_COLS
from ..entities.stone_golem_pixel_map import PIXEL_MAP as _PIXEL_MAP
from ..entities.stone_golem_pixel_map import PIXEL_ROWS as _PIXEL_ROWS
from ..entities.stone_golem_pixel_map import C as _C

logger = logging.getLogger(__name__)


# ============================================================================
# HELPERS MATEMATICOS
# ============================================================================


def _ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


# ============================================================================
# ENTIDADES PROJETADAS PELO GOLEM
# ============================================================================


class GolemMine:
    """
    Mina de energia vermelha plantada pelo boss na posição do jogador.
    """

    FUSE_TIME = 5.0  # segundos até explodir
    LAND_SPEED = 900.0  # px/s durante a queda
    RADIUS = 12
    EXPL_SHARDS = 16  # fragmentos na explosão

    _COLOR_BODY = (200, 40, 40)
    _COLOR_RING = (255, 100, 100)
    _COLOR_PULSE = (255, 200, 200)

    def __init__(self, x: float, y: float, target_x: float, target_y: float):
        self.x = float(x)
        self.y = float(y)
        self.target_x = float(target_x)
        self.target_y = float(target_y)
        self.dead = False
        self.causes_damage = True

        self._phase = "landing"
        self._fuse_timer = 0.0
        self._pulse_t = 0.0

        self.rect = pygame.Rect(
            int(self.x - self.RADIUS),
            int(self.y - self.RADIUS),
            self.RADIUS * 2,
            self.RADIUS * 2,
        )

        r = self.RADIUS
        max_glow_r = int(r * 2.2)
        self._glow_surf = pygame.Surface(
            (max_glow_r * 2, max_glow_r * 2), pygame.SRCALPHA
        )
        self._arc_surf = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)

    def update(self, dt: float) -> list["RockShard"]:
        self._pulse_t += dt
        spawned: list[RockShard] = []

        if self._phase == "landing":
            dx = self.target_x - self.x
            dy = self.target_y - self.y
            dist = math.hypot(dx, dy)
            if dist < self.LAND_SPEED * dt:
                self.x, self.y = self.target_x, self.target_y
                self._phase = "armed"
            else:
                nx, ny = dx / dist, dy / dist
                self.x += nx * self.LAND_SPEED * dt
                self.y += ny * self.LAND_SPEED * dt

        elif self._phase == "armed":
            self._fuse_timer += dt
            if self._fuse_timer >= self.FUSE_TIME:
                self._phase = "exploded"
                for i in range(self.EXPL_SHARDS):
                    angle_deg = (360.0 / self.EXPL_SHARDS) * i + random.uniform(-5, 5)
                    spawned.append(
                        RockShard(
                            self.x,
                            self.y,
                            angle_deg,
                            speed_mult=1.4,
                            color=(255, 100, 60),
                        )
                    )
                self.dead = True

        self.rect.x = int(self.x - self.RADIUS)
        self.rect.y = int(self.y - self.RADIUS)
        return spawned

    def draw(self, surface: pygame.Surface) -> None:
        if self._phase == "exploded":
            return

        cx, cy = int(self.x), int(self.y)
        r = self.RADIUS
        fuse_ratio = (
            self._fuse_timer / self.FUSE_TIME if self._phase == "armed" else 0.0
        )
        blink_freq = 4.0 + fuse_ratio * 14.0
        blink_on = math.sin(self._pulse_t * blink_freq * math.pi * 2) > 0

        pulse = abs(math.sin(self._pulse_t * blink_freq * math.pi))
        glow_r = int(r * 1.6 + pulse * r * 0.6)
        glow_alpha = int(60 + pulse * 80)

        self._glow_surf.fill((0, 0, 0, 0))
        pygame.draw.circle(
            self._glow_surf, (*self._COLOR_RING, glow_alpha), (glow_r, glow_r), glow_r
        )
        surface.blit(self._glow_surf, (cx - glow_r, cy - glow_r))

        S = max(2, r // 3)
        body_color = self._COLOR_PULSE if blink_on else self._COLOR_BODY
        pygame.draw.rect(surface, body_color, (cx - S, cy - S * 3, S * 2, S * 6))
        pygame.draw.rect(surface, body_color, (cx - S * 3, cy - S, S * 6, S * 2))
        pygame.draw.rect(surface, body_color, (cx - S * 2, cy - S * 2, S * 4, S * 4))

        if self._phase == "armed":
            remaining = 1.0 - fuse_ratio
            arc_end = int(remaining * 360)
            if arc_end > 2:
                self._arc_surf.fill((0, 0, 0, 0))
                arc_col = (
                    int(255 * fuse_ratio + 60 * remaining),
                    int(200 * remaining),
                    40,
                    200,
                )
                pygame.draw.arc(
                    self._arc_surf,
                    arc_col,
                    (4, 4, r * 4 - 8, r * 4 - 8),
                    math.radians(90),
                    math.radians(90 + arc_end),
                    max(1, S),
                )
                surface.blit(self._arc_surf, (cx - r * 2, cy - r * 2))


Boulder = GolemMine


class RockShard:
    """
    Fragmento de pedra disparado pelo boss.
    """

    def __init__(
        self,
        x: float,
        y: float,
        angle_deg: float,
        speed_mult: float = 1.0,
        color: Optional[Tuple[int, int, int]] = None,
    ):
        self.x = x
        self.y = y
        self.size = random.randint(10, 16)
        self.dead = False
        self.color = color if color is not None else (217, 66, 255)

        speed = getattr(Config, "GOLEM_SHARD_SPEED", 420) * speed_mult
        rad = math.radians(angle_deg)
        self.vx = math.cos(rad) * speed
        self.vy = math.sin(rad) * speed

        self._angle = angle_deg
        self._spin = random.uniform(-220, 220)

        self.rect = pygame.Rect(
            int(self.x - self.size),
            int(self.y - self.size),
            self.size * 2,
            self.size * 2,
        )

        s = self.size // 2
        self._glow_surf = pygame.Surface((s * 4, s * 4), pygame.SRCALPHA)
        self._glow_surf.fill((*self.color, 60))

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self._angle += self._spin * dt
        self.rect.x = int(self.x - self.size)
        self.rect.y = int(self.y - self.size)

        screen_h = getattr(Config, "SCREEN_HEIGHT", 800)
        screen_w = getattr(Config, "SCREEN_WIDTH", 480)
        if (
            self.y > screen_h + 40
            or self.y < -40
            or self.x < -40
            or self.x > screen_w + 40
        ):
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = int(self.x), int(self.y)
        s = self.size // 2
        c = self.color
        core = (255, 255, 255)
        surface.blit(self._glow_surf, (cx - s * 2, cy - s * 2))
        pygame.draw.rect(surface, c, (cx - s, cy - s, s * 2, s * 2))
        pygame.draw.rect(surface, core, (cx - s // 2, cy - s // 2, s, s))


class OrbitalRock:
    """
    Pedra de terra usada no ataque Earth do Golem.
    """

    def __init__(
        self,
        screen_w: int,
        screen_h: int,
        orbit_cx: float,
        orbit_cy: float,
        target_rx: float,
        target_ry: float,
        orbit_angle_start: float,
        rock_size: int,
        color: Tuple[int, int, int],
        S: int,
    ):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.dead = False
        self.x = orbit_cx + (random.random() - 0.5) * screen_w * 0.8
        self.y = screen_h + 50 + random.random() * 150
        self.orbit_cx = orbit_cx
        self.orbit_cy = orbit_cy
        self.target_rx = target_rx
        self.target_ry = target_ry
        self.orbit_angle = orbit_angle_start
        self.orbit_speed = 0.03 + random.random() * 0.04
        self._S = S
        self._size = rock_size
        self.color = color
        self.bob_offset = random.uniform(0, math.pi * 2)
        self.spin = random.uniform(0, 360)
        self.spin_speed = random.uniform(200, 450) * random.choice([-1, 1])
        self.trail: list[list[float]] = []
        self.phase = "pulling"
        self.fire_delay = 0.0
        self._fire_vx = 0.0
        self._fire_vy = 0.0
        self._fire_perp_x = 0.0
        self._fire_perp_y = 0.0
        self._fire_perp_decay = 3.5
        self._fire_gravity = getattr(Config, "GOLEM_BOULDER_GRAVITY", 30)

        hit = S * self._size
        self.rect = pygame.Rect(int(self.x) - hit, int(self.y) - hit, hit * 2, hit * 2)

        canvas_size = (self._size + 2) * S * 2
        self._rock_surf = pygame.Surface((canvas_size, canvas_size), pygame.SRCALPHA)
        ox = canvas_size // 2 - (self._size * S) // 2
        oy = canvas_size // 2 - S
        if self._size == 2:
            pygame.draw.rect(self._rock_surf, self.color, (ox, oy, S * 2, S * 2))
        else:
            pygame.draw.rect(self._rock_surf, self.color, (ox, oy, S * 3, S * 2))
            pygame.draw.rect(self._rock_surf, self.color, (ox + S, oy - S, S, S))
            pygame.draw.rect(self._rock_surf, self.color, (ox - S, oy + S, S, S))
        self._dust_surf = pygame.Surface((S * 2, S * 2), pygame.SRCALPHA)

    def _orbit_target(self) -> Tuple[float, float]:
        bobbing_y = math.sin(self.orbit_angle * 2 + self.bob_offset) * 15
        return (
            self.orbit_cx + math.cos(self.orbit_angle) * self.target_rx,
            self.orbit_cy + math.sin(self.orbit_angle) * self.target_ry + bobbing_y,
        )

    def fire_at(self, target_x: float, target_y: float) -> None:
        self.phase = "fired"
        base_speed = getattr(Config, "GOLEM_BOULDER_SPEED", 340) * 1.15
        spread_x = target_x + random.uniform(-250, 250)
        spread_y = target_y + random.uniform(-100, 250)
        dx, dy = spread_x - self.x, spread_y - self.y
        dist = math.hypot(dx, dy) or 1.0
        self._fire_vx, self._fire_vy = dx / dist * base_speed, dy / dist * base_speed
        perp_strength = random.uniform(-400, 400)
        self._fire_perp_x, self._fire_perp_y = (
            -dy / dist * perp_strength,
            dx / dist * perp_strength,
        )
        self._fire_perp_decay = random.uniform(1.8, 3.5)

    def update(
        self,
        dt: float,
        orbit_cx: float,
        orbit_cy: float,
        player_x: float = 0.0,
        player_y: float = 0.0,
    ) -> None:
        self.orbit_cx, self.orbit_cy = orbit_cx, orbit_cy
        self.orbit_angle += self.orbit_speed * 60 * dt

        if self.phase == "pulling":
            tx, ty = self._orbit_target()
            self.x += (tx - self.x) * min(1.0, 3.0 * dt)
            self.y += (ty - self.y) * min(1.0, 3.0 * dt)
        elif self.phase == "orbiting":
            tx, ty = self._orbit_target()
            self.x += (tx - self.x) * min(1.0, 12.0 * dt)
            self.y += (ty - self.y) * min(1.0, 12.0 * dt)
            if self.fire_delay > 0:
                self.fire_delay -= dt
                if self.fire_delay <= 0:
                    self.fire_at(player_x, player_y)
        elif self.phase == "fired":
            decay = math.exp(-self._fire_perp_decay * dt)
            self._fire_perp_x *= decay
            self._fire_perp_y *= decay
            self._fire_vy += self._fire_gravity * dt
            self.x += (self._fire_vx + self._fire_perp_x) * dt
            self.y += (self._fire_vy + self._fire_perp_y) * dt
            self.spin += self.spin_speed * dt
            if random.random() < 0.4:
                self.trail.append([self.x, self.y, 255.0])
            if (
                self.y > self.screen_h + 80
                or self.x < -80
                or self.x > self.screen_w + 80
            ):
                self.dead = True

        for t in self.trail:
            t[2] -= 800 * dt
        self.trail = [t for t in self.trail if t[2] > 0]
        hit = self._S * self._size
        self.rect.x, self.rect.y = int(self.x) - hit, int(self.y) - hit

    def draw(self, surface: pygame.Surface) -> None:
        S, c = self._S, self.color
        for tx, ty, alpha in self.trail:
            self._dust_surf.fill((*c, int(alpha * 0.6)))
            surface.blit(self._dust_surf, (int(tx) - S, int(ty) - S))
        img = (
            pygame.transform.rotate(self._rock_surf, self.spin)
            if self.phase == "fired"
            else self._rock_surf
        )
        surface.blit(img, img.get_rect(center=(int(self.x), int(self.y))))

    @property
    def causes_damage(self) -> bool:
        return self.phase == "fired"

    @property
    def behind_boss(self) -> bool:
        return math.sin(self.orbit_angle) < 0 and self.phase != "fired"


# ============================================================================
# PARTICULA DE CARGA
# ============================================================================


class _ChargeParticle:
    def __init__(self, pupil_x: float, pupil_y: float, color: Tuple[int, int, int]):
        self.angle = random.uniform(0, math.pi * 2)
        self.dist = 120 + random.uniform(0, 40)
        self.start_dist = self.dist
        self.orbit_speed = 0.05 + random.uniform(0, 0.08)
        self.radial_speed = 80 + random.uniform(0, 80)
        self.color, self.size = color, random.randint(3, 6)
        self.px, self.py = pupil_x, pupil_y
        self.dead = False
        self._surf = pygame.Surface((self.size * 2, self.size * 2), pygame.SRCALPHA)

    def update(self, dt: float, pupil_x: float, pupil_y: float) -> None:
        self.dist -= self.radial_speed * dt
        speed_mul = 1.0 + (1.0 - _clamp(self.dist / self.start_dist, 0, 1)) * 2.0
        self.angle += self.orbit_speed * speed_mul * (dt * 60)
        if self.dist < 2:
            self.dead = True
            return
        self.px = pupil_x + math.cos(self.angle) * self.dist
        self.py = pupil_y + math.sin(self.angle) * self.dist

    def draw(self, surface: pygame.Surface) -> None:
        ratio = _clamp(self.dist / self.start_dist * 2, 0, 1)
        if ratio < 0.05:
            return
        self._surf.fill((0, 0, 0, 0))
        pygame.draw.circle(
            self._surf,
            (*self.color, int(ratio * 220)),
            (self.size, self.size),
            self.size,
        )
        surface.blit(self._surf, (int(self.px) - self.size, int(self.py) - self.size))


class StoneGolemBoss:
    """
    Boss do Mundo 1 — Cordilheira Celestial.
    """

    SCALE = 12

    def __init__(
        self,
        x: float,
        y: float,
        health: Optional[int] = None,
        difficulty_multiplier: float = 1.0,
    ):
        S = self.SCALE
        self._screen_w, self._screen_h = getattr(Config, "SCREEN_WIDTH", 480), getattr(
            Config, "SCREEN_HEIGHT", 800
        )
        self.w, self.h = _PIXEL_COLS * S, _PIXEL_ROWS * S
        margin_x = 70
        self.x, self.y = self._screen_w - self.w - margin_x, -self.h
        self.target_y, self.difficulty_multiplier = y, difficulty_multiplier
        base_health = getattr(Config, "GOLEM_HEALTH", 2500)
        self.max_health = int(base_health * difficulty_multiplier)
        self.health = health if health is not None else self.max_health
        self.dead, self.hit_score = False, 60
        self.direction, self.entry_speed = 1, getattr(Config, "GOLEM_ENTRY_SPEED", 160)
        self.fsm_state, self.fsm_ticks, self._prev_fsm_state = (
            "ENTERING",
            0.0,
            "ENTERING",
        )
        self.eye_growth, self._scan_step, self._current_float_y = 0.0, 0, 0.0
        self.stomp_shake, self.stomp_shake_timer = 0.0, 0.0
        self._jitter_x, self._jitter_y = 0.0, 0.0
        self._sweep_angle, self._sweep_total = math.pi / 2, math.radians(30)
        self._shards_fired_at: set[int] = set()
        self._sweep_locked_angle, self._sweep_lock_done = math.pi / 2, False
        self._orbital_rocks: List[OrbitalRock] = []
        self._mines: List[GolemMine] = []
        self._fire_shots_count, self._fire_shot_timer, self._cycles_since_fire = (
            0,
            0.0,
            0,
        )
        self._orb_shots_done, self._orb_rotation = 0, 0.0
        self._charge_particles: List[_ChargeParticle] = []
        self._time, self.rect = 0.0, pygame.Rect(
            int(self.x), int(self.y), self.w, self.h
        )
        self.emp_linger_timer = 0.0
        self._body_surf_top, self._body_surf_bottom = None, None
        self._pre_bake_body()
        self._thruster_surfs = [
            pygame.Surface((S * 10 + 2, S * 4 + 2), pygame.SRCALPHA) for _ in range(5)
        ]
        self._cone_surf = pygame.Surface(
            (self._screen_w, self._screen_h), pygame.SRCALPHA
        )
        self._beam_surf = pygame.Surface(
            (self._screen_w, self._screen_h), pygame.SRCALPHA
        )
        self._halo_surf = pygame.Surface(
            (self._screen_w, self._screen_h), pygame.SRCALPHA
        )

    def _pre_bake_body(self) -> None:
        S = self.SCALE
        self._body_surf_top = pygame.Surface(
            (self.w, _EYE_ROW_ABOVE * S), pygame.SRCALPHA
        )
        for r in range(_EYE_ROW_ABOVE):
            for c, k in enumerate(_PIXEL_MAP[r]):
                if k:
                    pygame.draw.rect(self._body_surf_top, _C[k], (c * S, r * S, S, S))
        bottom_start = _EYE_ROW_BELOW + 1
        self._body_surf_bottom = pygame.Surface(
            (self.w, (_PIXEL_ROWS - bottom_start) * S), pygame.SRCALPHA
        )
        for r in range(bottom_start, _PIXEL_ROWS):
            dr = r - bottom_start
            for c, k in enumerate(_PIXEL_MAP[r]):
                if k:
                    pygame.draw.rect(
                        self._body_surf_bottom, _C[k], (c * S, dr * S, S, S)
                    )

    def _shared_center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self._current_float_y

    def _pupil_pos(self) -> Tuple[float, float]:
        S = self.SCALE
        px = (
            self.x + _EYE_COL_START * S + self._jitter_x + S * 2.5 + self._scan_step * S
        )
        return px, self._shared_center()[1] + self._jitter_y

    def _change_fsm(self, new_state: str) -> None:
        self._prev_fsm_state, self.fsm_state, self.fsm_ticks = (
            self.fsm_state,
            new_state,
            0.0,
        )
        if new_state == "CHARGE":
            self._charge_particles.clear()
        if new_state == "FIRE":
            self._fire_shots_count, self._fire_shot_timer, self._cycles_since_fire = (
                0,
                0.0,
                0,
            )
        if new_state == "ORB_SPAWN":
            self._orb_rotation, self._orb_shots_done = 0.0, 0
        if new_state == "SWEEP_CHARGE":
            self._sweep_locked_angle, self._sweep_lock_done = math.pi / 2, False
        if new_state == "SWEEP_FIRE":
            self._sweep_angle, self._shards_fired_at = (
                self._sweep_locked_angle - self._sweep_total / 2,
                set(),
            )
        if new_state == "EARTH_PULL":
            self._orbital_rocks.clear()
            cx, cy, S = *self._shared_center(), self.SCALE
            for _ in range(15):
                rx, ry = (
                    self.w * 0.45 + random.random() * self.w * 0.2,
                    self.w * 0.12 + random.random() * self.w * 0.1,
                )
                self._orbital_rocks.append(
                    OrbitalRock(
                        self._screen_w,
                        self._screen_h,
                        cx,
                        cy,
                        rx,
                        ry,
                        random.random() * math.pi * 2,
                        2 if random.random() > 0.5 else 3,
                        random.choice(_ORBITAL_ROCK_COLORS),
                        S,
                    )
                )
        if new_state == "EARTH_ORBIT":
            for r in self._orbital_rocks:
                r.phase = "orbiting"
        if new_state == "EARTH_FIRE":
            for r in self._orbital_rocks:
                if r.phase == "orbiting":
                    r.fire_delay = random.uniform(0.1, 1.2)

    def update(
        self, dt: float, player_x: float, player_y: float
    ) -> Tuple[List["GolemMine"], List[RockShard], List[OrbitalRock]]:
        new_mines, new_shards = [], []
        self._time += dt
        self.fsm_ticks += dt
        _anchored = {
            "CHARGE",
            "FIRE",
            "EARTH_SHAKE",
            "EARTH_PULL",
            "EARTH_ORBIT",
            "EARTH_FIRE",
            "ORB_SPAWN",
            "ORB_HOLD",
            "ORB_FIRE",
            "SWEEP_CHARGE",
            "SWEEP_FIRE",
        }
        target_float = (
            0.0
            if self.fsm_state in _anchored
            else round(math.sin(self._time * 2.5) * 12)
        )
        self._current_float_y += (target_float - self._current_float_y) * min(
            1.0, 6.0 * dt
        )
        self._scan_step = (
            round(math.cos(self._time * 3))
            if self.fsm_state in {"SCAN", "OPENING", "ORB_SPAWN"}
            else 0
        )
        S = self.SCALE
        if self.fsm_state in ("EARTH_SHAKE", "EARTH_PULL", "SWEEP_FIRE"):
            self._jitter_x, self._jitter_y = (
                random.uniform(-0.5, 0.5) * S,
                random.uniform(-0.5, 0.5) * S,
            )
        else:
            self._jitter_x, self._jitter_y = 0.0, 0.0
        self.stomp_shake = self._jitter_y
        self._run_fsm(dt, player_x, player_y, new_mines, new_shards)
        px, py = self._pupil_pos()
        for p in self._charge_particles:
            p.update(dt, px, py)
        self._charge_particles = [p for p in self._charge_particles if not p.dead]
        self._mines = [m for m in self._mines if not m.dead]
        cx, cy = self._shared_center()
        for r in self._orbital_rocks:
            r.update(dt, cx, cy, player_x, player_y)
        self._orbital_rocks = [r for r in self._orbital_rocks if not r.dead]
        self.rect.x, self.rect.y = int(self.x), int(self.y)
        return new_mines, new_shards, self._orbital_rocks

    def _run_fsm(
        self,
        dt: float,
        player_x: float,
        player_y: float,
        new_mines: List["GolemMine"],
        new_shards: List[RockShard],
    ) -> None:
        t, state, spd = self.fsm_ticks, self.fsm_state, self.difficulty_multiplier
        if state == "ENTERING":
            self.y += self.entry_speed * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self._change_fsm("SCAN")
        elif state == "SCAN":
            self._move_vertical(dt)
            self.eye_growth = 0.0
            if t > (2.0 / spd):
                r = random.random()
                if self._cycles_since_fire >= 2 or r < 0.4:
                    self._change_fsm("OPENING")
                elif r < 0.6:
                    self._change_fsm("EARTH_SHAKE")
                elif r < 0.8:
                    self._change_fsm("ORB_SPAWN")
                else:
                    self._change_fsm("SWEEP_CHARGE")
        elif state == "OPENING":
            self._move_vertical(dt)
            self.eye_growth = _ease_out_cubic(_clamp(t / (1.5 / spd), 0, 1))
            if t > (2.5 / spd):
                self._change_fsm("CHARGE")
        elif state == "CHARGE":
            self._move_vertical(dt)
            px, py = self._pupil_pos()
            if len(self._charge_particles) < 150:
                for _ in range(3):
                    self._charge_particles.append(
                        _ChargeParticle(
                            px, py, random.choice([(255, 77, 77), (255, 153, 153)])
                        )
                    )
            if t > (1.5 / spd):
                self._change_fsm("FIRE")
        elif state == "FIRE":
            self._fire_shot_timer -= dt
            if self._fire_shot_timer <= 0 and self._fire_shots_count < 3:
                px, py = self._pupil_pos()
                mine = GolemMine(
                    px,
                    py,
                    player_x + random.uniform(-40, 40),
                    player_y + random.uniform(-40, 40),
                )
                new_mines.append(mine)
                self._mines.append(mine)
                self._fire_shots_count += 1
                self._fire_shot_timer = 0.6 / spd
            if self._fire_shots_count >= 3 and self._fire_shot_timer <= -0.3:
                self._change_fsm("CLOSING")
        elif state == "EARTH_SHAKE":
            self._move_vertical(dt)
            if t > (0.8 / spd):
                self._change_fsm("EARTH_PULL")
        elif state == "EARTH_PULL":
            self._move_vertical(dt)
            if t > (1.33 / spd):
                self._change_fsm("EARTH_ORBIT")
        elif state == "EARTH_ORBIT":
            self._move_vertical(dt)
            if t > (1.5 / spd):
                self._change_fsm("EARTH_FIRE")
        elif state == "EARTH_FIRE":
            self._move_vertical(dt)
            if (
                not self._orbital_rocks
                or all(r.phase == "fired" and r.dead for r in self._orbital_rocks)
                or t > (5.0 / spd)
            ):
                self._cycles_since_fire += 1
                self._change_fsm("SCAN")
        elif state == "ORB_SPAWN":
            self.eye_growth = _ease_out_cubic(_clamp(t / (0.8 / spd), 0, 1))
            if t > (0.8 / spd):
                self._change_fsm("ORB_HOLD")
        elif state == "ORB_HOLD":
            px, py = self._pupil_pos()
            wave_interval, max_waves = 0.75 / spd, 4
            if self._orb_shots_done < max_waves and t >= (
                self._orb_shots_done * wave_interval
            ):
                offset = 22.5 if (self._orb_shots_done % 2 == 1) else 0.0
                for i in range(8):
                    new_shards.append(
                        RockShard(
                            px,
                            py,
                            (i * 45.0) + offset,
                            speed_mult=2.0,
                            color=_C["EYE_IRIS_ORB"],
                        )
                    )
                self._orb_shots_done += 1
            if self._orb_shots_done >= max_waves and t > (
                max_waves * wave_interval + 0.5
            ):
                self._change_fsm("CLOSING")
        elif state == "SWEEP_CHARGE":
            self._move_vertical(dt)
            self.eye_growth = _ease_out_cubic(_clamp(t / (1.2 / spd), 0, 1))
            charge_duration = 1.8 / spd
            if t / charge_duration < 0.7:
                px, py = self._pupil_pos()
                self._sweep_locked_angle = math.atan2(player_y - py, player_x - px) % (
                    2 * math.pi
                )
            elif not self._sweep_lock_done:
                self._sweep_lock_done = True
            if t > charge_duration:
                self._change_fsm("SWEEP_FIRE")
        elif state == "SWEEP_FIRE":
            px, py = self._pupil_pos()
            fire_duration, delay = 0.9 / spd, 0.2 / spd
            self._sweep_angle = (
                self._sweep_locked_angle
                - self._sweep_total / 2
                + _clamp(t / fire_duration, 0, 1) * self._sweep_total
            )
            if t > delay:
                shoot_angle = (
                    self._sweep_locked_angle
                    - self._sweep_total / 2
                    + _clamp((t - delay) / fire_duration, 0, 1) * self._sweep_total
                )
                bucket = int(math.degrees(shoot_angle) / 4)
                if bucket not in self._shards_fired_at:
                    self._shards_fired_at.add(bucket)
                    new_shards.append(
                        RockShard(
                            px,
                            py,
                            math.degrees(shoot_angle),
                            speed_mult=1.3,
                            color=_C["SWEEP_BEAM"],
                        )
                    )
            if t > fire_duration + delay + 0.3:
                self._change_fsm("CLOSING")
        elif state == "CLOSING":
            self._move_vertical(dt)
            self.eye_growth = 1.0 - _ease_out_cubic(_clamp(t / (0.6 / spd), 0, 1))
            if self.eye_growth <= 0.01:
                self.eye_growth = 0.0
                self._cycles_since_fire = (
                    0 if self._prev_fsm_state == "FIRE" else self._cycles_since_fire + 1
                )
                self._change_fsm("SCAN")

    def _move_vertical(self, dt: float) -> None:
        speed = getattr(Config, "GOLEM_SPEED", 75)
        self.y += self.direction * speed * dt
        if self.y <= 40 or self.y >= self._screen_h // 2:
            self.direction *= -1

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        if self.health <= 0:
            self.health, self.dead = 0, True

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return
        S, ox, oy = (
            self.SCALE,
            int(self.x + self._jitter_x),
            int(self.y + self._current_float_y + self._jitter_y),
        )
        for r in self._orbital_rocks:
            if r.behind_boss:
                r.draw(surface)
        if self._body_surf_top:
            surface.blit(self._body_surf_top, (ox, oy))
        if self._body_surf_bottom:
            surface.blit(self._body_surf_bottom, (ox, oy + (_EYE_ROW_BELOW + 1) * S))
        eye_off = int(self.eye_growth * S)
        for r_idx in (_EYE_ROW_ABOVE, _EYE_ROW, _EYE_ROW_BELOW):
            for c_idx, k in enumerate(_PIXEL_MAP[r_idx]):
                if k is None or (
                    r_idx == _EYE_ROW and _EYE_COL_START <= c_idx <= _EYE_COL_END
                ):
                    continue
                px_d, py_d = ox + c_idx * S, oy + r_idx * S
                if _EYE_COL_START <= c_idx <= _EYE_COL_END:
                    if r_idx == _EYE_ROW_ABOVE:
                        py_d -= eye_off
                    elif r_idx == _EYE_ROW_BELOW:
                        py_d += eye_off
                pygame.draw.rect(surface, _C[k], (px_d, py_d, S, S))
        self._draw_eye(surface, ox, oy, S, eye_off)
        self._draw_thruster(surface, ox, oy, S)
        for p in self._charge_particles:
            p.draw(surface)
        if self.fsm_state in ("SWEEP_CHARGE", "SWEEP_FIRE"):
            self._draw_sweep_cone(surface)
        if self.fsm_state == "SWEEP_FIRE":
            self._draw_sweep_beam(surface)
        if self.fsm_state in ("CHARGE", "SWEEP_CHARGE"):
            self._draw_charge_core(surface)
        for r in self._orbital_rocks:
            if not r.behind_boss:
                r.draw(surface)
        self._draw_health_bar(surface, ox, oy)

    def _draw_eye(
        self, surface: pygame.Surface, ox: int, oy: int, S: int, eye_offset: int
    ) -> None:
        state = self.fsm_state
        if state in {"OPENING", "CHARGE", "FIRE"}:
            bg, iris = _C["EYE_BG_LASER"], _C["EYE_IRIS_LASER"]
        elif state in {"EARTH_SHAKE", "EARTH_PULL", "EARTH_ORBIT", "EARTH_FIRE"}:
            bg, iris = _C["EYE_BG_EARTH"], _C["EYE_IRIS_EARTH"]
        elif state in {"ORB_SPAWN", "ORB_HOLD", "ORB_FIRE"}:
            bg, iris = _C["EYE_BG_ORB"], _C["EYE_IRIS_ORB"]
        elif state in {"SWEEP_CHARGE", "SWEEP_FIRE"}:
            bg, iris = _C["EYE_BG_SWEEP"], _C["EYE_IRIS_SWEEP"]
        else:
            bg, iris = _C["EYE_BG_DEFAULT"], _C["EYE_IRIS_DEFAULT"]
        vx, ey, vh = ox + _EYE_COL_START * S, oy + _EYE_ROW * S, S + eye_offset * 2
        vy = ey - eye_offset
        pygame.draw.rect(surface, bg, (vx, vy, S * 5, vh))
        pygame.draw.rect(surface, iris, (vx + S + self._scan_step * S, vy, S * 3, vh))
        pygame.draw.rect(
            surface, _C["PUPIL"], (vx + S * 2 + self._scan_step * S, vy + 1, S, S)
        )

    def _draw_thruster(self, surface: pygame.Surface, ox: int, oy: int, S: int) -> None:
        cx, sy, t = ox + self.w // 2, oy + self.h, self._time
        pygame.draw.rect(surface, (255, 255, 255), (cx - S, sy, S * 2, S))
        for i in range(5):
            ph = ((t * 2.0) + (i / 5)) % 1.0
            w, h = int(S * 10 * (1 - ph)), max(S, int(S * 4 * (1 - ph)))
            y, al = sy + int(ph * S * 14) + S, max(0, int(255 * (1 - ph**2)))
            if w < S:
                continue
            col = (
                (255, 255, 255)
                if ph < 0.15
                else ((157, 212, 240) if ph < 0.5 else (91, 159, 200))
            )
            self._thruster_surfs[i].fill((0, 0, 0, 0))
            pygame.draw.rect(self._thruster_surfs[i], (*col, al), (0, 0, w, h), S)
            surface.blit(self._thruster_surfs[i], (cx - w // 2, y - h // 2))

    def _draw_sweep_cone(self, surface: pygame.Surface) -> None:
        px, py = self._pupil_pos()
        cone_len, half = (
            max(self._screen_w, self._screen_h) * 2.5,
            self._sweep_total / 2,
        )
        al = (
            int(38 + math.sin(self._time * 20) * 12)
            if self.fsm_state == "SWEEP_CHARGE"
            else 40
        )
        ang = self._sweep_locked_angle if self._sweep_lock_done else self._sweep_angle
        self._cone_surf.fill((0, 0, 0, 0))
        pts = [
            (int(px), int(py)),
            (
                int(px + math.cos(ang - half) * cone_len),
                int(py + math.sin(ang - half) * cone_len),
            ),
            (
                int(px + math.cos(ang + half) * cone_len),
                int(py + math.sin(ang + half) * cone_len),
            ),
        ]
        pygame.draw.polygon(self._cone_surf, (*_C["SWEEP_BEAM"], al), pts)
        surface.blit(self._cone_surf, (0, 0))

    def get_sweep_beam(self) -> Optional[Tuple[float, float, float, float]]:
        if self.fsm_state != "SWEEP_FIRE":
            return None
        px, py = self._pupil_pos()
        bl = max(self._screen_w, self._screen_h) * 2.5
        return (
            px,
            py,
            px + math.cos(self._sweep_angle) * bl,
            py + math.sin(self._sweep_angle) * bl,
        )

    def _draw_sweep_beam(self, surface: pygame.Surface) -> None:
        px, py, ex, ey = self.get_sweep_beam() or (0, 0, 0, 0)
        if px == 0:
            return
        self._halo_surf.fill((0, 0, 0, 0))
        pygame.draw.line(
            self._halo_surf,
            (*_C["SWEEP_BEAM"], 77),
            (int(px), int(py)),
            (int(ex), int(ey)),
            self.SCALE * 3,
        )
        surface.blit(self._halo_surf, (0, 0))
        pygame.draw.line(
            surface,
            (255, 255, 255),
            (int(px), int(py)),
            (int(ex), int(ey)),
            max(1, self.SCALE),
        )

    def _draw_charge_core(self, surface: pygame.Surface) -> None:
        px, py, S, t = *self._pupil_pos(), self.SCALE, self.fsm_ticks
        col = (
            _C["EYE_IRIS_LASER"] if self.fsm_state == "CHARGE" else _C["EYE_IRIS_SWEEP"]
        )
        rot = self._time * (10 if self.fsm_state == "CHARGE" else 20)
        idx = 2 if t > 1.0 else (1 if t > 0.6 else 0)
        if idx == 0:
            pygame.draw.rect(surface, col, (int(px) - S // 2, int(py) - S // 2, S, S))
        elif idx == 1:
            pygame.draw.rect(
                surface, col, (int(px) - S // 2, int(py) - S * 2, S, S * 4)
            )
            pygame.draw.rect(
                surface, col, (int(px) - S * 2, int(py) - S // 2, S * 4, S)
            )
            pygame.draw.rect(
                surface, _C["PUPIL"], (int(px) - S // 2, int(py) - S // 2, S, S)
            )
        else:
            pygame.draw.rect(
                surface, col, (int(px) - S // 2, int(py) - S * 3, S, S * 6)
            )
            pygame.draw.rect(
                surface, col, (int(px) - S * 3, int(py) - S // 2, S * 6, S)
            )
            pygame.draw.rect(
                surface, col, (int(px) - S * 2, int(py) - S * 2, S * 4, S * 4)
            )
            for i in range(4):
                a = math.radians(rot + i * 90)
                pygame.draw.rect(
                    surface,
                    _C["PUPIL"],
                    (
                        int(px + math.cos(a) * S * 2) - S // 2,
                        int(py + math.sin(a) * S * 2) - S // 2,
                        S,
                        S,
                    ),
                )

    def _draw_health_bar(self, surface: pygame.Surface, ox: int, oy: int) -> None:
        bw, bx, by, bh = self.w + 16, ox - 8, oy - 14, 7
        pygame.draw.rect(surface, (30, 30, 30), (bx, by, bw, bh), border_radius=3)
        hp = max(0.0, self.health / self.max_health)
        pygame.draw.rect(
            surface,
            (int(220 * (1 - hp) + 60 * hp), int(200 * hp), 40),
            (bx, by, int(bw * hp), bh),
            border_radius=3,
        )
        pygame.draw.rect(surface, (180, 180, 180), (bx, by, bw, bh), 1, border_radius=3)
