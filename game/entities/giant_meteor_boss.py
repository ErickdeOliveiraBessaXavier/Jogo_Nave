import math
import random
from typing import TYPE_CHECKING, TypedDict

import pygame

from ..core import colors
from ..core.config import config
from ..core.sound import sound_manager

if TYPE_CHECKING:
    from ..systems.entity_manager import EntityManager
    from ..systems.hit_result import HitResult, MeteorSpec

# ---------------------------------------------------------------------------
# Geração de forma base
# ---------------------------------------------------------------------------
_SHAPE_EDGE_SEGS: int = 20
_SHAPE_EDGE_JITTER: float = 8.0

# ---------------------------------------------------------------------------
# Geração e sistema de rachaduras
# ---------------------------------------------------------------------------
_CRACK_COUNT_MIN: int = 25
_CRACK_COUNT_MAX: int = 30
_CRACK_RNG_SEED: int = 42
_CRACK_POSITION_JITTER: float = 18.0
_CRACK_WIDTH_MIN: float = 45.0
_CRACK_WIDTH_MAX: float = 75.0
_CRACK_PATH_SEGS: int = 6
_CRACK_HP_THRESHOLD: float = 0.90
_CRACK_STAGES: int = 12
_CRACK_MIN_DIST_RATIO: float = 0.08
_CRACK_WIDTH_SCALE_BASE: float = 0.35
_CRACK_WIDTH_SCALE_RANGE: float = 0.55
_CRACK_DEPTH_MIN_BASE: float = 0.20
_CRACK_DEPTH_MIN_SCALE: float = 0.60
_CRACK_DEPTH_MAX_BASE: float = 0.35
_CRACK_DEPTH_MAX_SCALE: float = 0.65

# ---------------------------------------------------------------------------
# Animação
# ---------------------------------------------------------------------------
_TRANSITION_DURATION: float = 0.3
_SHAKE_DURATION: float = 0.5
_SHAKE_BASE_INTENSITY: float = 8.0
_SHAKE_INTENSITY_PER_STAGE: float = 0.7

# ---------------------------------------------------------------------------
# Spawn de meteoros normais (estado falling)
# ---------------------------------------------------------------------------
_SPAWN_INTERVAL_BASE: float = 2.0
_SPAWN_INTERVAL_SCALE: float = 1.5
_SPAWN_CAP_PER_TICK: int = 4
_SPAWN_CAP_SCALE: float = 1.2
_SPAWN_METEOR_LIMIT: int = 30
_NORMAL_METEOR_X_MARGIN: float = 100.0
_NORMAL_METEOR_Y_JITTER: float = 10.0
_NORMAL_METEOR_VX_RANGE: float = 40.0
_NORMAL_METEOR_VY_MIN: float = 180.0
_NORMAL_METEOR_VY_MAX: float = 320.0

# ---------------------------------------------------------------------------
# Fragmentos ao receber dano
# ---------------------------------------------------------------------------
_DMGFRAG_CRACK_BIAS: float = 0.7
_DMGFRAG_POS_JITTER: float = 15.0
_DMGFRAG_SPEED_MIN: float = 150.0
_DMGFRAG_SPEED_MAX: float = 300.0
_DMGFRAG_SPEED_SPREAD: tuple[float, float] = (0.7, 1.3)
_DMGFRAG_SIDE_VX_MIN: float = 80.0
_DMGFRAG_SIDE_VX_MAX: float = 180.0
_DMGFRAG_VY_BIAS_MIN: float = 100.0
_DMGFRAG_VY_BIAS_MAX: float = 200.0
_DMGFRAG_GENERIC_VX_RANGE: float = 120.0
_DMGFRAG_GENERIC_VX_SIDE_MIN: float = 100.0
_DMGFRAG_GENERIC_VX_SIDE_MAX: float = 300.0
_DMGFRAG_GENERIC_VY_MIN: float = 100.0
_DMGFRAG_GENERIC_VY_MAX: float = 200.0

# ---------------------------------------------------------------------------
# Fragmentos de morte
# ---------------------------------------------------------------------------
_DEATHFRAG_SPEED_MIN: float = 200.0
_DEATHFRAG_SPEED_MAX: float = 450.0
_DEATHFRAG_SIDE_VX_MIN: float = 50.0
_DEATHFRAG_SIDE_VX_MAX: float = 150.0
_DEATHFRAG_VY_BIAS: float = 50.0
_DEATHFRAG_SIZE_BONUS_MIN: int = 10
_DEATHFRAG_SIZE_BONUS_MAX: int = 25

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
_SURFACE_PADDING: int = 20
_COLOR_BODY: tuple[int, int, int] = (180, 90, 45)


class CrackPosition(TypedDict):
    edge_idx: int
    start_x: float
    start_y: float
    dir_x: float
    dir_y: float
    perp_x: float
    perp_y: float
    base_width: float


class GiantMeteorBoss:
    """Boss simples: um meteoro gigante caindo lentamente."""

    def __init__(self, _x: float, _y: float) -> None:
        self.w = int(config.SCREEN_WIDTH * 1.3)
        self.h = config.GIANT_METEOR_BOSS_HEIGHT
        self.x = -int(config.SCREEN_WIDTH * 0.15)
        self.y = -self.h - 100
        self.target_y = -self.h * 0.7

        self.health = config.GIANT_METEOR_BOSS_HEALTH
        self.max_health = self.health
        self.dead = False

        self.entry_speed = config.GIANT_METEOR_BOSS_ENTRY_SPEED
        self.speed = config.GIANT_METEOR_BOSS_FALL_SPEED

        self.state = "entering"
        self.meteor_spawn_timer = 0.0
        self.meteor_spawn_interval = _SPAWN_INTERVAL_BASE
        self._last_damage_stage = -1
        self._transition_timer = 0.0
        self._old_shape: list[tuple[float, float]] | None = None
        self._target_shape: list[tuple[float, float]] | None = None
        self._shake_timer = 0.0
        self._shake_intensity = _SHAKE_BASE_INTENSITY

        self.is_side_scroll: bool = False  # setado pelo EntityManager ao spawnar

        self._base_shape = self._generate_base_shape()
        self._current_shape = list(self._base_shape)
        self._all_crack_positions = self._generate_all_crack_positions()
        self._crack_birth_stage: dict[int, int] = {}

        self._surface: pygame.Surface | None = None
        self._surface_dirty = True

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x + self.w / 2, self.y + self.h / 2, max(self.w, self.h) / 2

    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult, MeteorSpec

        self.take_damage(damage)
        fragments: tuple[MeteorSpec, ...] = ()
        if self.dead:
            return HitResult(
                killed=True,
                points=config.BOSS_DEFEAT_SCORE,
                explosion_size=120,
                sound=hit_sounds.EXPLOSION_BOSS,
                fragments=self._build_death_fragment_specs(),
            )
        if self.state == "falling" and random.random() < config.GIANT_METEOR_HIT_FRAGMENT_CHANCE:
            fragments = self._build_damage_fragment_specs()
        return HitResult(explosion_size=18, sound=hit_sounds.BOSS_DAMAGE, fragments=fragments)

    def should_remove(self) -> bool:
        return self.dead

    def take_damage(self, damage: int) -> None:
        if self.dead:
            return
        self.health -= damage
        if self.health <= 0:
            self.dead, self.state = True, "dying"

    def update(self, dt: float, entity_manager: "EntityManager") -> None:
        if self.dead:
            return

        hp_pct = self.health / self.max_health
        stage = min(_CRACK_STAGES - 1, int((1.0 - hp_pct) * _CRACK_STAGES))

        if stage != self._last_damage_stage:
            self._old_shape = list(self._current_shape)
            self._target_shape = self._apply_damage_cracks(hp_pct)
            self._transition_timer = 0.0
            self._shake_timer = _SHAKE_DURATION
            self._shake_intensity = _SHAKE_BASE_INTENSITY + stage * _SHAKE_INTENSITY_PER_STAGE
            self._last_damage_stage = stage
            self._surface_dirty = True
            if hasattr(sound_manager, "play_meteor_boss_crack"):
                sound_manager.play_meteor_boss_crack()

        if self._target_shape:
            self._transition_timer += dt
            t = min(1.0, self._transition_timer / _TRANSITION_DURATION)
            self._current_shape = self._interpolate_shapes(
                self._old_shape or self._base_shape,
                self._target_shape,
                1 - (1 - t) ** 2,
            )
            self._surface_dirty = True
            if t >= 1.0:
                self._current_shape = list(self._target_shape)
                self._old_shape = self._target_shape = None

        if self._shake_timer > 0:
            self._shake_timer = max(0.0, self._shake_timer - dt)

        if self.state == "entering":
            self.y += self.entry_speed * dt
            if self.y >= self.target_y:
                self.y, self.state = self.target_y, "falling"
        elif self.state == "falling":
            self.y += self.speed * dt
            self.meteor_spawn_interval = _SPAWN_INTERVAL_BASE - _SPAWN_INTERVAL_SCALE * (1 - hp_pct)
            self.meteor_spawn_timer += dt
            if self.meteor_spawn_timer >= self.meteor_spawn_interval:
                self.meteor_spawn_timer = 0.0
                active = entity_manager.meteor_pool.get_active_count()
                cap = min(_SPAWN_CAP_PER_TICK, 1 + int(stage * _SPAWN_CAP_SCALE))
                count = max(0, min(cap, _SPAWN_METEOR_LIMIT - active))
                for _ in range(count):
                    self._spawn_normal_meteor(entity_manager)

    def draw(self, surface: pygame.Surface) -> None:
        if self._surface_dirty or self._surface is None:
            surf_w = max(1, self.w + _SURFACE_PADDING)
            surf_h = max(1, self.h + _SURFACE_PADDING)
            self._surface = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA).convert_alpha()
            if len(self._current_shape) >= 3:
                pygame.draw.polygon(self._surface, _COLOR_BODY, self._current_shape)
                pygame.draw.polygon(self._surface, colors.RED, self._current_shape, 3)
            self._surface_dirty = False

        sx, sy = 0.0, 0.0
        if self._shake_timer > 0:
            intns = self._shake_intensity * (self._shake_timer / _SHAKE_DURATION)
            sx, sy = random.uniform(-intns, intns), random.uniform(-intns, intns)
        surface.blit(self._surface, (int(self.x + sx), int(self.y + sy)))

    # ------------------------------------------------------------------
    # Shape generation
    # ------------------------------------------------------------------

    def _generate_base_shape(self) -> list[tuple[float, float]]:
        j = _SHAPE_EDGE_JITTER
        s = _SHAPE_EDGE_SEGS
        pts: list[tuple[float, float]] = []
        for i in range(s + 1):
            pts.append((i * self.w / s, random.uniform(-j, j)))
        for i in range(1, s + 1):
            pts.append((self.w + random.uniform(-j, j), i * self.h / s))
        for i in range(s, -1, -1):
            pts.append((i * self.w / s, self.h + random.uniform(-j, j)))
        for i in range(s - 1, 0, -1):
            pts.append((random.uniform(-j, j), i * self.h / s))
        return pts

    def _generate_all_crack_positions(self) -> list[CrackPosition]:
        rng = random.Random(_CRACK_RNG_SEED)
        cracks: list[CrackPosition] = []
        cx, cy = self.w * 0.5, self.h * 0.5
        for _ in range(rng.randint(_CRACK_COUNT_MIN, _CRACK_COUNT_MAX)):
            idx = rng.randint(0, len(self._base_shape) - 1)
            bx, by = self._base_shape[idx]
            jitter = _CRACK_POSITION_JITTER
            sx = bx + rng.uniform(-jitter, jitter)
            sy = by + rng.uniform(-jitter, jitter)
            dx, dy = cx - sx, cy - sy
            dist = math.hypot(dx, dy)
            if dist == 0:
                continue
            ux, uy = dx / dist, dy / dist
            cracks.append({
                "edge_idx": idx,
                "start_x": sx,
                "start_y": sy,
                "dir_x": ux,
                "dir_y": uy,
                "perp_x": -uy,
                "perp_y": ux,
                "base_width": rng.uniform(_CRACK_WIDTH_MIN, _CRACK_WIDTH_MAX),
            })
        return cracks

    def _apply_damage_cracks(self, hp_pct: float) -> list[tuple[float, float]]:
        if hp_pct > _CRACK_HP_THRESHOLD:
            return list(self._base_shape)

        stage = min(_CRACK_STAGES - 1, int((1.0 - hp_pct) * _CRACK_STAGES))
        total = len(self._all_crack_positions)
        num_active = max(2, int(total * stage / _CRACK_STAGES))
        min_dist = self.w * _CRACK_MIN_DIST_RATIO

        to_act = num_active - len(self._crack_birth_stage)
        c_idx, attempts = len(self._crack_birth_stage), 0
        while to_act > 0 and c_idx < total and attempts < total * 2:
            if c_idx not in self._crack_birth_stage:
                pos = self._all_crack_positions[c_idx]
                too_close = any(
                    math.hypot(
                        pos["start_x"] - self._all_crack_positions[a]["start_x"],
                        pos["start_y"] - self._all_crack_positions[a]["start_y"],
                    ) < min_dist
                    for a in self._crack_birth_stage
                )
                if not too_close:
                    self._crack_birth_stage[c_idx] = stage
                    to_act -= 1
            c_idx += 1
            attempts += 1

        max_d = min(self.w, self.h) * 0.5
        age_norm = _CRACK_STAGES - 1
        crks: list[tuple[int, list[tuple[float, float]]]] = []
        for i in range(min(num_active, total)):
            birth = self._crack_birth_stage.get(i, stage)
            age = stage - birth
            t = age / age_norm
            rng = random.Random(i * 1000 + birth * 100)
            width = self._all_crack_positions[i]["base_width"] * (
                _CRACK_WIDTH_SCALE_BASE + t * _CRACK_WIDTH_SCALE_RANGE
            )
            depth = rng.uniform(
                _CRACK_DEPTH_MIN_BASE + t * _CRACK_DEPTH_MIN_SCALE,
                _CRACK_DEPTH_MAX_BASE + t * _CRACK_DEPTH_MAX_SCALE,
            ) * max_d
            crks.append((
                self._all_crack_positions[i]["edge_idx"],
                self._generate_crack_path(self._all_crack_positions[i], width, depth, rng),
            ))

        crks.sort(key=lambda x: x[0], reverse=True)
        res: list[tuple[float, float]] = list(self._base_shape)
        for idx, pts in crks:
            res[idx : idx + 1] = pts
        return res

    def _generate_crack_path(
        self, data: CrackPosition, w: float, d: float, rng: random.Random
    ) -> list[tuple[float, float]]:
        s = _CRACK_PATH_SEGS
        line: list[tuple[float, float]] = []
        for i in range(s + 1):
            p = i / s
            off = (
                w * 0.4 * 0.3 * rng.choice([-1, 1]) * (0.5 + 0.5 * (1 - abs(2 * p - 1)))
                + w * 0.4 * 0.5 * rng.uniform(-1, 1)
            )
            line.append((
                data["start_x"] + data["dir_x"] * d * p + data["perp_x"] * off,
                data["start_y"] + data["dir_y"] * d * p + data["perp_y"] * off,
            ))

        pts: list[tuple[float, float]] = []
        for i in range(s + 1):
            hw = w * (1 - (i / s) ** 1.5) * 0.5
            pts.append((line[i][0] + data["perp_x"] * hw, line[i][1] + data["perp_y"] * hw))
        for i in range(s - 1, -1, -1):
            hw = w * (1 - (i / s) ** 1.5) * 0.5
            pts.append((line[i][0] - data["perp_x"] * hw, line[i][1] - data["perp_y"] * hw))
        return pts

    def _interpolate_shapes(
        self, s1: list[tuple[float, float]], s2: list[tuple[float, float]], t: float
    ) -> list[tuple[float, float]]:
        if len(s1) != len(s2):
            return s2 if t > 0.5 else s1
        return [
            (s1[i][0] + (s2[i][0] - s1[i][0]) * t, s1[i][1] + (s2[i][1] - s1[i][1]) * t)
            for i in range(len(s1))
        ]

    # ------------------------------------------------------------------
    # Fragment specs
    # ------------------------------------------------------------------

    def _spawn_normal_meteor(self, em: "EntityManager") -> None:
        em.spawn_meteor(
            size=random.randint(config.GIANT_METEOR_FRAGMENT_MIN_SIZE, config.GIANT_METEOR_FRAGMENT_MAX_SIZE),
            x=random.uniform(0, config.SCREEN_WIDTH - _NORMAL_METEOR_X_MARGIN),
            y=random.uniform(-_NORMAL_METEOR_Y_JITTER, _NORMAL_METEOR_Y_JITTER),
            vx=random.uniform(-_NORMAL_METEOR_VX_RANGE, _NORMAL_METEOR_VX_RANGE),
            vy=random.uniform(_NORMAL_METEOR_VY_MIN, _NORMAL_METEOR_VY_MAX),
        )

    def _build_damage_fragment_specs(self) -> "tuple[MeteorSpec, ...]":
        from ..systems.hit_result import MeteorSpec

        mn = config.GIANT_METEOR_FRAGMENT_MIN_SIZE
        mx = config.GIANT_METEOR_FRAGMENT_MAX_SIZE
        age_norm = _CRACK_STAGES - 1
        specs: list[MeteorSpec] = []

        for _ in range(random.randint(*config.GIANT_METEOR_HIT_FRAGMENT_COUNT)):
            if self._crack_birth_stage and random.random() < _DMGFRAG_CRACK_BIAS:
                idx = random.choice(list(self._crack_birth_stage.keys()))
                cd = self._all_crack_positions[idx]
                jitter = _DMGFRAG_POS_JITTER
                x = self.x + cd["start_x"] + random.uniform(-jitter, jitter)
                y = self.y + cd["start_y"] + random.uniform(-jitter, jitter)
                spd = random.uniform(_DMGFRAG_SPEED_MIN, _DMGFRAG_SPEED_MAX)
                spread = random.uniform(*_DMGFRAG_SPEED_SPREAD)
                vx = -cd["dir_x"] * spd * spread
                vy = -cd["dir_y"] * spd * spread
                if self.is_side_scroll:
                    vx -= random.uniform(_DMGFRAG_SIDE_VX_MIN, _DMGFRAG_SIDE_VX_MAX)
                vy += self.speed + random.uniform(_DMGFRAG_VY_BIAS_MIN, _DMGFRAG_VY_BIAS_MAX)
                age = max(0, self._last_damage_stage - self._crack_birth_stage[idx])
                size = random.randint(
                    mn + age * 2,
                    min(mx, mn + int((mx - mn) * (age / age_norm) + 5)),
                )
            else:
                x = self.x + random.uniform(0, self.w)
                y = self.y + random.uniform(0, self.h)
                vx = (
                    random.uniform(-_DMGFRAG_GENERIC_VX_SIDE_MAX, -_DMGFRAG_GENERIC_VX_SIDE_MIN)
                    if self.is_side_scroll
                    else random.uniform(-_DMGFRAG_GENERIC_VX_RANGE, _DMGFRAG_GENERIC_VX_RANGE)
                )
                vy = random.uniform(_DMGFRAG_GENERIC_VY_MIN, _DMGFRAG_GENERIC_VY_MAX)
                size = random.randint(mn, mx)
            specs.append(MeteorSpec(size, x, y, vx, vy))

        return tuple(specs)

    def _build_death_fragment_specs(self) -> "tuple[MeteorSpec, ...]":
        from ..systems.hit_result import MeteorSpec

        mn = config.GIANT_METEOR_FRAGMENT_MIN_SIZE
        mx = config.GIANT_METEOR_FRAGMENT_MAX_SIZE
        specs: list[MeteorSpec] = []

        for _ in range(random.randint(*config.GIANT_METEOR_DEATH_FRAGMENT_COUNT)):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(_DEATHFRAG_SPEED_MIN, _DEATHFRAG_SPEED_MAX)
            size = random.randint(mn + _DEATHFRAG_SIZE_BONUS_MIN, mx + _DEATHFRAG_SIZE_BONUS_MAX)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            if self.is_side_scroll:
                vx -= random.uniform(_DEATHFRAG_SIDE_VX_MIN, _DEATHFRAG_SIDE_VX_MAX)
            vy += _DEATHFRAG_VY_BIAS
            specs.append(MeteorSpec(
                size,
                self.x + random.uniform(0, self.w),
                self.y + random.uniform(0, self.h),
                vx,
                vy,
            ))

        return tuple(specs)
