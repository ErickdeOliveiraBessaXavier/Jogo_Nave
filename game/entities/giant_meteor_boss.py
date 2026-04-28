import math
import random
from typing import TYPE_CHECKING, TypedDict

import pygame

from ..core import colors
from ..core.config import config
from ..core.sound import sound_manager

if TYPE_CHECKING:
    from ..systems.entity_manager import EntityManager
    from ..systems.hit_result import MeteorSpec
    from ..systems.hit_result import HitResult


class CrackPosition(TypedDict):
    """Dados de uma posição de rachadura."""

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

    def __init__(self, _x: float, _y: float):
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
        self.meteor_spawn_interval = 2.0
        self._last_damage_stage = -1
        self._transition_timer = 0.0
        self._transition_duration = 0.3
        self._old_shape: list[tuple[float, float]] | None = None
        self._target_shape: list[tuple[float, float]] | None = None
        self._shake_timer = 0.0
        self._shake_duration = 0.5
        self._shake_intensity = 8.0

        self.is_side_scroll: bool = False  # setado pelo EntityManager ao spawnar

        self._base_shape = self._generate_base_shape()
        self._current_shape = list(self._base_shape)
        self._all_crack_positions = self._generate_all_crack_positions()
        self._crack_birth_stage: dict[int, int] = {}

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
            fragments = self._build_death_fragment_specs()
            return HitResult(killed=True, points=config.BOSS_DEFEAT_SCORE, explosion_size=120, sound=hit_sounds.EXPLOSION_BOSS, fragments=fragments)
        if self.state == "falling" and random.random() < config.GIANT_METEOR_HIT_FRAGMENT_CHANCE:
            fragments = self._build_damage_fragment_specs()
        return HitResult(explosion_size=18, sound=hit_sounds.BOSS_DAMAGE, fragments=fragments)

    def should_remove(self) -> bool:
        return self.dead

    def _interpolate_shapes(self, s1: list[tuple[float, float]], s2: list[tuple[float, float]], t: float) -> list[tuple[float, float]]:
        if len(s1) != len(s2): return s2 if t > 0.5 else s1
        return [(s1[i][0] + (s2[i][0]-s1[i][0])*t, s1[i][1] + (s2[i][1]-s1[i][1])*t) for i in range(len(s1))]

    def _generate_base_shape(self) -> list[tuple[float, float]]:
        pts: list[tuple[float, float]] = []
        segs = 20
        for i in range(segs + 1): pts.append((i * self.w / segs, random.uniform(-8, 8)))
        for i in range(1, segs + 1): pts.append((self.w + random.uniform(-8, 8), i * self.h / segs))
        for i in range(segs, -1, -1): pts.append((i * self.w / segs, self.h + random.uniform(-8, 8)))
        for i in range(segs - 1, 0, -1): pts.append((random.uniform(-8, 8), i * self.h / segs))
        return pts

    def _generate_all_crack_positions(self) -> list[CrackPosition]:
        rng = random.Random(42)
        cracks: list[CrackPosition] = []
        cx, cy = self.w * 0.5, self.h * 0.5
        for _ in range(rng.randint(25, 30)):
            idx = rng.randint(0, len(self._base_shape) - 1)
            bx, by = self._base_shape[idx]
            sx, sy = bx + rng.uniform(-18, 18), by + rng.uniform(-18, 18)
            dx, dy = cx - sx, cy - sy
            dist = (dx*dx + dy*dy)**0.5
            if dist == 0: continue
            ux, uy = dx/dist, dy/dist
            cracks.append({"edge_idx": idx, "start_x": sx, "start_y": sy, "dir_x": ux, "dir_y": uy, "perp_x": -uy, "perp_y": ux, "base_width": rng.uniform(45, 75)})
        return cracks

    def _apply_damage_cracks(self, hp_pct: float) -> list[tuple[float, float]]:
        if hp_pct > 0.90: return list(self._base_shape)
        stage = min(11, int((1.0 - hp_pct) * 12))
        total = len(self._all_crack_positions)
        num_active = [max(2, int(total * s / 12)) for s in range(12)][stage]
        min_dist = self.w * 0.08
        to_act = num_active - len(self._crack_birth_stage)
        c_idx, att = len(self._crack_birth_stage), 0
        while to_act > 0 and c_idx < total and att < total * 2:
            if c_idx not in self._crack_birth_stage:
                pos = self._all_crack_positions[c_idx]
                too_close = any(((pos["start_x"]-self._all_crack_positions[a]["start_x"])**2 + (pos["start_y"]-self._all_crack_positions[a]["start_y"])**2)**0.5 < min_dist for a in self._crack_birth_stage)
                if not too_close:
                    self._crack_birth_stage[c_idx] = stage
                    to_act -= 1
            c_idx += 1
            att += 1
        crks: list[tuple[int, list[tuple[float, float]]]] = []
        max_d = min(self.w, self.h) * 0.5
        for i in range(min(num_active, total)):
            birth = self._crack_birth_stage.get(i, stage)
            age = stage - birth
            rng = random.Random(i * 1000 + birth * 100)
            width = self._all_crack_positions[i]["base_width"] * (0.35 + (age/11.0)*0.55)
            depth = rng.uniform(0.20 + (age/11.0)*0.60, 0.35 + (age/11.0)*0.65) * max_d
            crks.append((self._all_crack_positions[i]["edge_idx"], self._generate_crack_path(self._all_crack_positions[i], width, depth, rng)))
        crks.sort(key=lambda x: x[0], reverse=True)
        res: list[tuple[float, float]] = list(self._base_shape)
        for idx, pts in crks: res[idx:idx+1] = pts
        return res

    def _generate_crack_path(self, data: CrackPosition, w: float, d: float, rng: random.Random) -> list[tuple[float, float]]:
        line: list[tuple[float, float]] = []
        segs = 10
        for i in range(segs + 1):
            p = i / segs
            off = w*0.4 * 0.3 * rng.choice([-1, 1]) * (0.5 + 0.5*(1-abs(2*p-1))) + w*0.4*0.5*rng.uniform(-1, 1)
            line.append((data["start_x"] + data["dir_x"]*d*p + data["perp_x"]*off, data["start_y"] + data["dir_y"]*d*p + data["perp_y"]*off))
        pts: list[tuple[float, float]] = []
        for i in range(segs + 1):
            hw = w * (1 - (i/segs)**1.5) * 0.5
            pts.append((line[i][0] + data["perp_x"]*hw, line[i][1] + data["perp_y"]*hw))
        for i in range(segs - 1, -1, -1):
            hw = w * (1 - (i/segs)**1.5) * 0.5
            pts.append((line[i][0] - data["perp_x"]*hw, line[i][1] - data["perp_y"]*hw))
        return pts

    def take_damage(self, damage: int) -> None:
        if self.dead: return
        self.health -= damage
        if self.health <= 0:
            self.dead, self.state = True, "dying"

    def update(self, dt: float, entity_manager: "EntityManager") -> None:
        if self.dead: return
        hp_pct = self.health / self.max_health
        stage = min(11, int((1.0 - hp_pct) * 12))
        if stage != self._last_damage_stage:
            self._old_shape, self._target_shape = list(self._current_shape), self._apply_damage_cracks(hp_pct)
            self._transition_timer, self._shake_timer, self._shake_intensity = 0.0, self._shake_duration, 8.0 + stage*0.7
            self._last_damage_stage = stage
            if hasattr(sound_manager, "play_meteor_boss_crack"): sound_manager.play_meteor_boss_crack()
        if self._target_shape:
            self._transition_timer += dt
            t = min(1.0, self._transition_timer / self._transition_duration)
            self._current_shape = self._interpolate_shapes(self._old_shape or self._base_shape, self._target_shape, 1 - (1-t)**2)
            if t >= 1.0: self._current_shape, self._old_shape, self._target_shape = list(self._target_shape), None, None
        if self._shake_timer > 0: self._shake_timer = max(0.0, self._shake_timer - dt)
        if self.state == "entering":
            self.y += self.entry_speed * dt
            if self.y >= self.target_y: self.y, self.state = self.target_y, "falling"
        elif self.state == "falling":
            self.y += self.speed * dt
            self.meteor_spawn_interval = 2.0 - 1.5*(1-hp_pct)
            self.meteor_spawn_timer += dt
            if self.meteor_spawn_timer >= self.meteor_spawn_interval:
                self.meteor_spawn_timer = 0.0
                for _ in range(1 + int(stage * 1.2)): self._spawn_normal_meteor(entity_manager)

    def _spawn_normal_meteor(self, em: "EntityManager") -> None:
        x = random.uniform(0, config.SCREEN_WIDTH - 100)
        y = random.uniform(-10, 10)  # borda superior, sobrevive ao off-screen check em ambos os modos
        vx = random.uniform(-40, 40)
        vy = random.uniform(180, 320)
        em.spawn_meteor(size=random.randint(config.GIANT_METEOR_FRAGMENT_MIN_SIZE, config.GIANT_METEOR_FRAGMENT_MAX_SIZE), x=x, y=y, vx=vx, vy=vy)

    def _build_damage_fragment_specs(self) -> "tuple[MeteorSpec, ...]":
        from ..systems.hit_result import MeteorSpec
        specs: list[MeteorSpec] = []
        for _ in range(random.randint(*config.GIANT_METEOR_HIT_FRAGMENT_COUNT)):
            if self._crack_birth_stage and random.random() < 0.7:
                idx = random.choice(list(self._crack_birth_stage.keys()))
                cd = self._all_crack_positions[idx]
                x = self.x + cd["start_x"] + random.uniform(-15, 15)
                y = self.y + cd["start_y"] + random.uniform(-15, 15)
                spd = random.uniform(150, 300)
                vx = -cd["dir_x"] * spd * random.uniform(0.7, 1.3)
                vy = -cd["dir_y"] * spd * random.uniform(0.7, 1.3)
                if self.is_side_scroll:
                    vx -= random.uniform(80, 180)  # bias para a esquerda (direção do scroll)
                vy += self.speed + random.uniform(100, 200)  # bias para baixo sempre
                age = max(0, self._last_damage_stage - self._crack_birth_stage[idx])
                mn, mx = config.GIANT_METEOR_FRAGMENT_MIN_SIZE, config.GIANT_METEOR_FRAGMENT_MAX_SIZE
                size = random.randint(mn + age*2, min(mx, mn + int((mx-mn)*(age/11.0)+5)))
            else:
                x = self.x + random.uniform(0, self.w)
                y = self.y + random.uniform(0, self.h)
                if self.is_side_scroll:
                    vx = random.uniform(-300, -100)
                else:
                    vx = random.uniform(-120, 120)
                vy = random.uniform(100, 200)
                size = random.randint(config.GIANT_METEOR_FRAGMENT_MIN_SIZE, config.GIANT_METEOR_FRAGMENT_MAX_SIZE)
            specs.append(MeteorSpec(size, x, y, vx, vy))
        return tuple(specs)

    def _build_death_fragment_specs(self) -> "tuple[MeteorSpec, ...]":
        from ..systems.hit_result import MeteorSpec
        specs: list[MeteorSpec] = []
        for _ in range(random.randint(*config.GIANT_METEOR_DEATH_FRAGMENT_COUNT)):
            angle, speed = random.uniform(0, 2 * math.pi), random.uniform(200, 450)
            size = random.randint(config.GIANT_METEOR_FRAGMENT_MIN_SIZE + 10, config.GIANT_METEOR_FRAGMENT_MAX_SIZE + 25)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            if self.is_side_scroll:
                vx -= random.uniform(50, 150)  # bias para a esquerda
            vy += 50  # bias para baixo sempre
            specs.append(MeteorSpec(size, self.x + random.uniform(0, self.w), self.y + random.uniform(0, self.h), vx, vy))
        return tuple(specs)

    def draw(self, surface: pygame.Surface) -> None:
        sx, sy = 0.0, 0.0
        if self._shake_timer > 0:
            intns = self._shake_intensity * (self._shake_timer / self._shake_duration)
            sx, sy = random.uniform(-intns, intns), random.uniform(-intns, intns)
        pts = [(self.x + px + sx, self.y + py + sy) for px, py in self._current_shape]
        if len(pts) >= 3:
            pygame.draw.polygon(surface, (180, 90, 45), pts)
            pygame.draw.polygon(surface, colors.RED, pts, 3)
