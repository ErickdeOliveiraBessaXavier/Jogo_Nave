from __future__ import annotations

import math
import random
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Dict, Final, List, Tuple

import pygame

from ..core.config import config as Config
from .mountain_mage import MountainStalactite, MountainStalagmite

if TYPE_CHECKING:
    from ..systems.hit_result import HitResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TELEPORT_FADE_SPEED: Final = 6.0
_LERP_BODY: Final = 10.0
_LERP_HAT: Final = 5.0
_LERP_EYE: Final = 8.0
_LERP_ARM: Final = 7.0

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ArchmageState(Enum):
    APPEARING = auto()
    IDLE = auto()
    PHASE1_TWIN_ORBS = auto()
    PHASE1_EXPANSION = auto()
    PHASE2_MAZE = auto()
    PHASE2_MAZE_ABSORB = auto()  # orb absorption intro
    PHASE2_SIPHON = auto()
    PHASE3_SINGULARITY = auto()
    PHASE3_RESONANCE = auto()
    TELEPORT = auto()
    SLIDE = auto()  # glide to new position without fading
    DEFEATED = auto()


class OrbType(Enum):
    CYAN = auto()
    PURPLE = auto()
    ORANGE = auto()
    WHITE = auto()


# ---------------------------------------------------------------------------
# ResonanceWave
# ---------------------------------------------------------------------------


class ResonanceWave:
    """Expanding circular shockwave."""

    def __init__(self, x: float, y: float, color: tuple[int, int, int]) -> None:
        self.x = x
        self.y = y
        self.radius = 10.0
        self.max_radius = 450.0
        self.speed = 280.0
        self.color = color
        self.dead = False
        self.causes_damage = True

    @property
    def rect(self) -> pygame.Rect:
        r = int(self.radius)
        return pygame.Rect(int(self.x) - r, int(self.y) - r, r * 2, r * 2)

    def update(self, dt: float) -> None:
        self.radius += self.speed * dt
        if self.radius >= self.max_radius:
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        alpha = max(0, int(255 * (1.0 - self.radius / self.max_radius)))
        diam = int(self.radius * 2) + 10
        s = pygame.Surface((diam, diam), pygame.SRCALPHA)
        cx = cy = diam // 2
        pygame.draw.circle(s, (*self.color, alpha // 2), (cx, cy), int(self.radius), 4)
        surface.blit(s, (int(self.x) - cx, int(self.y) - cy))

    def on_ship_contact(self, cx: float, cy: float) -> "HitResult":
        from ..systems.hit_result import HitResult

        return HitResult(killed=False)

    def should_remove(self) -> bool:
        return self.dead


# ---------------------------------------------------------------------------
# Pixel maps
# ---------------------------------------------------------------------------

HAT_MAP: Final[List[str]] = [
    ".........H........",
    "........HH........",
    ".......H*H........",
    "......H**H........",
    ".....HH**H........",
    "....H***HH........",
    "...HH****H........",
    "..HHHHHHHHHHHHHH..",
    ".HOOOOOOOOOOOOOOH.",
    "H****************H",
]

BODY_MAP: Final[List[str]] = [
    "....GGGGGGGG....",
    "...GBBBBBBBBG...",
    "..GBBMMMMMMBBG..",
    "..BBMEEEEEEMBB..",
    "..BBMEEEEEEMBB..",
    "..BBOOOOOOOOBB.",
    "..BBBB....BBBB..",
    ".BBBB......BBBB.",
]

ARM_MAP: Final[List[str]] = [
    "..GG..",
    ".GBBG.",
    ".BBBB.",
    "..MM..",
    ".MOOM.",
    ".MDDM.",
    "..DD..",
]

# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------

_PALETTES: Final[Dict[str, Dict[str, tuple[int, int, int]]]] = {
    "normal": {
        "robe": (60, 45, 110),
        "metal": (100, 105, 115),
        "visor": (10, 10, 20),
        "core": (30, 25, 45),
        "hat": (45, 30, 85),
        "hat_hl": (80, 60, 150),
        "joint": (30, 30, 35),
        "gold": (212, 175, 55),
        "gola": (80, 70, 140),
    },
    "phase3": {
        "robe": (40, 10, 60),
        "metal": (60, 65, 80),
        "visor": (20, 0, 0),
        "core": (25, 5, 30),
        "hat": (30, 5, 50),
        "hat_hl": (100, 20, 50),
        "joint": (20, 10, 15),
        "gold": (180, 130, 40),
        "gola": (60, 20, 80),
    },
    "flash": {
        k: (255, 255, 255)
        for k in (
            "robe",
            "metal",
            "visor",
            "core",
            "hat",
            "hat_hl",
            "joint",
            "gold",
            "gola",
        )
    },
}

_CHAR_TO_KEY: Final[Dict[str, str]] = {
    "H": "hat",
    "*": "hat_hl",
    "M": "metal",
    "V": "visor",
    "E": "core",
    "D": "joint",
    "O": "gold",
    "G": "gola",
}


# ---------------------------------------------------------------------------
# CloudArchmageBoss
# ---------------------------------------------------------------------------


class CloudArchmageBoss:
    MAX_HEALTH: Final[int] = 1200
    WIDTH: Final[int] = 80
    HEIGHT: Final[int] = 110

    PHASE2_THRESHOLD: Final[float] = 0.5  # fase 2 começa na metade do HP
    PHASE3_THRESHOLD: Final[float] = 0.3
    ORBIT_RADIUS: Final[float] = 130.0
    ORB_SIZE: Final[int] = 18

    SHIELD_MAX_HP: Final[int] = 80
    SHIELD_RADIUS: Final[float] = 95.0
    _SCALE: Final[int] = 4
    _SHIELD_SPAWN_DUR: Final[float] = 0.55

    # Teleport states are split into two sub-phases to avoid same-frame ghost.
    _TELEPORT_HALF: Final[float] = 0.6

    def __init__(self, x: float | None = None, y: float | None = None) -> None:
        sw = Config.SCREEN_WIDTH
        self.w, self.h = self.WIDTH, self.HEIGHT
        self.x: float = x if x is not None else sw / 2 - self.w / 2
        self.y: float = y if y is not None else -self.h - 50.0

        # Lerp targets — zero-initialised here; snapped after sprites are baked below
        self._hat_x = self._hat_y = 0.0
        self._body_x = self._body_y = 0.0
        self._l_arm_x = self._l_arm_y = 0.0
        self._r_arm_x = self._r_arm_y = 0.0
        self._eye_l_x = self._eye_l_y = 0.0
        self._eye_r_x = self._eye_r_y = 0.0

        self.max_health: int = self.MAX_HEALTH
        self.health: int = self.MAX_HEALTH
        self.dead: bool = False
        self.active: bool = False

        self._state: ArchmageState = ArchmageState.APPEARING
        self._state_timer: float = 2.5
        self._hit_flash: float = 0.0
        self._pulse_timer: float = 0.0
        self._orb_angle: float = 0.0
        # Mantle animation timer — decoupled from _pulse_timer so siphon
        # vibration doesn't bleed into the rest of the body animation.
        self._mantle_timer: float = 0.0
        self._mantle_speed: float = 1.0  # multiplier; 1=idle, ramps during siphon

        self._drift_timer: float = 0.0
        # 1.0 = fully visible, 0.0 = invisible
        self._teleport_visual: float = 1.0
        # Guard: prevents the reposition from firing more than once per teleport
        self._teleport_repositioned: bool = False
        # Safety: how long we've waited for orbs to return during teleport
        self._teleport_wait_timer: float = 0.0

        # Slide teleport vars
        self._slide_target_x: float = 0.0
        self._slide_target_y: float = 0.0
        self._slide_timer: float = 0.0
        self._slide_duration: float = 0.7  # seconds to reach target

        # Shield (PHASE2_MAZE rampage) ----------------------------------------
        self._shield_hp: int = 0  # 0 = no shield active
        self._shield_max_hp: int = self.SHIELD_MAX_HP
        self._shield_timer: float = 0.0  # pulsation timer
        self._shield_active: bool = False
        # Orb absorption animation: tracks orbs converging toward boss center
        self._absorb_timer: float = 0.0  # counts up during absorption phase
        self._absorb_duration: float = 1.2  # seconds for orbs to fly in

        # Shield spawn animation
        self._shield_spawn_t: float = 0.0  # 0→1 during spawn, 1=fully formed
        self._shield_spawning: bool = False
        self._shield_spawn_dur: float = self._SHIELD_SPAWN_DUR
        # Spawn burst rings: list of {r, alpha} emitted at spawn moment
        self._shield_rings: list[dict[str, float]] = []
        # Per-orb absorbed flag to fire burst FX exactly once per orb
        # dict[orb_index] = True when burst already fired
        self._orb_absorbed_fired: dict[int, bool] = {}
        # Orb burst particles: list of {x,y,vx,vy,life,max_life,color}
        self._orb_bursts: list[dict[str, Any]] = []
        # Particles emitted when shield shatters
        self._shield_break_particles: list[dict[str, Any]] = []
        # Trail particles for Orange orb and other effects
        self._trail_particles: list[dict[str, Any]] = []

        # ── Passive orb effect caches (updated every frame; read by collisions) ──
        # Purple: gravitational acceleration vector applied to player (px/s²)
        self._purple_gravity: tuple[float, float] = (0.0, 0.0)
        # Cyan: (x, y, radius) of the repulsion aura while attacking, or None
        self._cyan_attack_zone: tuple[float, float, float] | None = None
        # White: True when at least one White orb is orbiting (slows bullets)
        self._white_slow_active: bool = False

        _orb_defs: list[tuple[OrbType, tuple[int, int, int]]] = [
            (OrbType.CYAN, (0, 255, 255)),
            (OrbType.PURPLE, (180, 50, 255)),
            (OrbType.ORANGE, (255, 140, 0)),
            (OrbType.WHITE, (220, 240, 255)),
        ]
        self._orbs: list[dict[str, Any]] = [
            {
                "type": orb_type,
                "color": color,
                "x": 0.0,
                "y": 0.0,
                "target_x": 0.0,
                "target_y": 0.0,
                "base_angle": i * (math.tau / len(_orb_defs)),
                "mode": "ORBIT",
                "timer": 0.0,
            }
            for i, (orb_type, color) in enumerate(_orb_defs)
        ]

        self._target_pos: tuple[float, float] = (sw / 2.0, 160.0)
        self._active_telegraphs: list[dict[str, Any]] = []

        # Pre-bake all sprites once; never recreate inside draw().
        self._sprites: Dict[str, Dict[str, pygame.Surface]] = {
            "hat": {},
            "body": {},
            "arm": {},
        }
        # Teleport scale cache: {(part, state_key, scale_0_to_100): Surface}
        # Keyed on integer percent to bound cache size to ~300 entries total.
        self._teleport_cache: Dict[tuple[str, str, int], pygame.Surface] = {}
        self._render_all_parts()
        # Sprites now exist — snap lerp targets to initial position
        self._sync_lerp_to_position()

    # ------------------------------------------------------------------
    # Sprite baking
    # ------------------------------------------------------------------

    def _render_all_parts(self) -> None:
        for state_name, pal in _PALETTES.items():
            self._sprites["hat"][state_name] = self._bake_surface(HAT_MAP, pal)
            self._sprites["body"][state_name] = self._bake_surface(BODY_MAP, pal)
            self._sprites["arm"][state_name] = self._bake_surface(ARM_MAP, pal)

    def _bake_surface(
        self, pixelmap: List[str], pal: Dict[str, tuple[int, int, int]]
    ) -> pygame.Surface:
        cols = len(pixelmap[0])
        rows = len(pixelmap)
        surf = pygame.Surface((cols * self._SCALE, rows * self._SCALE), pygame.SRCALPHA)
        for r_idx, row in enumerate(pixelmap):
            for c_idx, char in enumerate(row):
                if char == ".":
                    continue
                key = _CHAR_TO_KEY.get(char, "robe")
                pygame.draw.rect(
                    surf,
                    pal[key],
                    (
                        c_idx * self._SCALE,
                        r_idx * self._SCALE,
                        self._SCALE,
                        self._SCALE,
                    ),
                )
        return surf.convert_alpha()

    def _get_scaled_sprite(
        self, part: str, state_key: str, visual: float
    ) -> pygame.Surface:
        """Returns a cached scaled sprite for the teleport effect."""
        pct = max(1, min(100, int(visual * 100)))
        cache_key = (part, state_key, pct)
        if cache_key not in self._teleport_cache:
            base = self._sprites[part][state_key]
            w = max(1, int(base.get_width() * visual))
            h = max(1, int(base.get_height() * visual))
            self._teleport_cache[cache_key] = pygame.transform.scale(
                base, (w, h)
            ).convert_alpha()
        return self._teleport_cache[cache_key]

    # ------------------------------------------------------------------
    # Lerp helpers
    # ------------------------------------------------------------------

    def _sync_lerp_to_position(self) -> None:
        """Hard-snap all lerp targets to current self.x/y. Call after a teleport reposition."""
        bx = self.x + self.w / 2

        hat_surf_w = (
            self._sprites["hat"]["normal"].get_width()
            if self._sprites.get("hat")
            else 0
        )
        body_surf_w = (
            self._sprites["body"]["normal"].get_width()
            if self._sprites.get("body")
            else 0
        )
        arm_surf_w = (
            self._sprites["arm"]["normal"].get_width()
            if self._sprites.get("arm")
            else 0
        )

        by = self.y + 20.0

        self._body_x = bx - body_surf_w / 2
        self._body_y = by
        self._hat_x = bx - hat_surf_w / 2
        self._hat_y = by - 60.0
        self._eye_l_x = bx - 18.0
        self._eye_l_y = (self._hat_y + self._body_y + 20.0) / 2
        self._eye_r_x = bx + 10.0
        self._eye_r_y = self._eye_l_y
        self._l_arm_x = bx - 55.0
        self._l_arm_y = by + 20.0
        self._r_arm_x = bx + 55.0 - arm_surf_w
        self._r_arm_y = by + 20.0

    def _update_lerp_physics(self, dt: float) -> None:
        bx = self.x + self.w / 2
        by = self.y + 20.0
        pt = self._pulse_timer

        body_w = self._sprites["body"]["normal"].get_width()
        hat_w = self._sprites["hat"]["normal"].get_width()
        arm_w = self._sprites["arm"]["normal"].get_width()

        # Body
        txb = bx - body_w / 2
        tyb = by + math.sin(pt * 4.0) * 4.0
        self._body_x += (txb - self._body_x) * _LERP_BODY * dt
        self._body_y += (tyb - self._body_y) * _LERP_BODY * dt

        # Hat (looser float)
        txh = bx - hat_w / 2
        tyh = by - 60.0 + math.sin(pt * 3.0) * 10.0
        self._hat_x += (txh - self._hat_x) * _LERP_HAT * dt
        self._hat_y += (tyh - self._hat_y) * _LERP_HAT * dt

        # Eyes
        ey = (self._hat_y + self._body_y + 20.0) / 2
        self._eye_l_x += (bx - 18.0 - self._eye_l_x) * _LERP_EYE * dt
        self._eye_l_y += (ey - self._eye_l_y) * _LERP_EYE * dt
        self._eye_r_x += (bx + 10.0 - self._eye_r_x) * _LERP_EYE * dt
        self._eye_r_y += (ey - self._eye_r_y) * _LERP_EYE * dt

        # Arms
        self._l_arm_x += (bx - 55.0 - self._l_arm_x) * _LERP_ARM * dt
        self._l_arm_y += (
            (by + 20.0 + math.cos(pt * 3.0) * 10.0 - self._l_arm_y) * _LERP_ARM * dt
        )
        self._r_arm_x += (bx + 55.0 - arm_w - self._r_arm_x) * _LERP_ARM * dt
        self._r_arm_y += (
            (by + 20.0 + math.sin(pt * 3.0) * 10.0 - self._r_arm_y) * _LERP_ARM * dt
        )

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self, dt: float, player_pos: Tuple[float, float] | None = None
    ) -> List[Any]:
        if self.dead:
            return []

        self._pulse_timer += dt
        self._hit_flash = max(0.0, self._hit_flash - dt)
        self._mantle_timer += dt * self._mantle_speed
        self._shield_timer += dt

        # Shield spawn animation tick
        if self._shield_spawning:
            self._shield_spawn_t = min(
                1.0, self._shield_spawn_t + dt / self._shield_spawn_dur
            )
            if self._shield_spawn_t >= 1.0:
                self._shield_spawning = False
                self._shield_active = True

        # Spawn burst rings expand outward and fade
        for ring in self._shield_rings[:]:
            ring["r"] += 220.0 * dt
            ring["alpha"] -= 280.0 * dt
            if ring["alpha"] <= 0:
                self._shield_rings.remove(ring)

        # Orb burst particles
        for p in self._orb_bursts[:]:
            p["life"] -= dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["vy"] += 60.0 * dt
            if p["life"] <= 0:
                self._orb_bursts.remove(p)

        # Shield break particles
        for p in self._shield_break_particles[:]:
            p["life"] -= dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["vx"] *= max(0.0, 1.0 - 3.5 * dt)
            p["vy"] *= max(0.0, 1.0 - 3.5 * dt)
            if p["life"] <= 0:
                self._shield_break_particles.remove(p)

        # Trail particles (Orange orb and others)
        for p in self._trail_particles[:]:
            p["life"] -= dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            if p["life"] <= 0:
                self._trail_particles.remove(p)

        if self._state != ArchmageState.PHASE2_SIPHON:
            self._mantle_speed = max(1.0, self._mantle_speed - dt * 4.0)
        hp_ratio = self.health / self.max_health

        # Constant mystic drift (not during cinematic states)
        if self._state not in (
            ArchmageState.APPEARING,
            ArchmageState.TELEPORT,
            ArchmageState.SLIDE,
            ArchmageState.DEFEATED,
        ):
            self._drift_timer += dt
            self.x += math.sin(self._drift_timer * 1.5) * 40.0 * dt
            self.y += math.cos(self._drift_timer * 1.2) * 25.0 * dt

        # Fade-in recovery outside teleport
        if self._state != ArchmageState.TELEPORT:
            self._teleport_visual = min(
                1.0, self._teleport_visual + _TELEPORT_FADE_SPEED * dt
            )

        # Orbital speed scales with damage taken
        self._orb_angle += dt * 1.2 * (1.0 + (1.0 - hp_ratio) * 1.5)

        spawned: List[Any] = []

        match self._state:
            case ArchmageState.APPEARING:
                self._update_appearing(dt)
            case ArchmageState.IDLE:
                self._update_idle(dt, hp_ratio)
            case ArchmageState.TELEPORT:
                self._update_teleport(dt)
            case ArchmageState.PHASE1_TWIN_ORBS:
                self._update_twin_orbs(dt, player_pos)
            case ArchmageState.PHASE1_EXPANSION:
                self._update_expansion(dt, player_pos)
            case ArchmageState.PHASE2_MAZE_ABSORB:
                self._update_maze_absorb(dt)
            case ArchmageState.PHASE2_MAZE:
                spawned = self._update_maze(dt, player_pos)
            case ArchmageState.PHASE2_SIPHON:
                self._update_siphon(dt, player_pos)
            case ArchmageState.SLIDE:
                self._update_slide(dt)
            case ArchmageState.PHASE3_SINGULARITY | ArchmageState.PHASE3_RESONANCE:
                pass  # TODO: implement phase 3 handlers
            case ArchmageState.DEFEATED:
                pass

        self._update_orbs_positions(dt)
        self._update_lerp_physics(dt)
        return spawned

    @property
    def rect(self) -> pygame.Rect:
        """Empty during teleport (both fade-out and before reposition).
        Expands to cover shield when active."""
        if self._state == ArchmageState.TELEPORT and not self._teleport_repositioned:
            return pygame.Rect(0, 0, 0, 0)
        if self._teleport_visual < 0.45:
            return pygame.Rect(0, 0, 0, 0)
        if self._shield_active or self._shield_spawning:
            r = int(
                self.SHIELD_RADIUS
                * (self._shield_spawn_t if self._shield_spawning else 1.0)
            )
            cx, cy = int(self.x + self.w / 2), int(self.y + self.h / 2)
            return pygame.Rect(cx - r, cy - r, r * 2, r * 2)
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def collision_circle(self) -> tuple[float, float, float]:
        if self._state == ArchmageState.TELEPORT and not self._teleport_repositioned:
            return 0.0, 0.0, 0.0
        if self._teleport_visual < 0.45:
            return 0.0, 0.0, 0.0
        cx, cy = self.x + self.w / 2, self.y + self.h / 2
        if self._shield_active or self._shield_spawning:
            r = self.SHIELD_RADIUS * (
                self._shield_spawn_t if self._shield_spawning else 1.0
            )
            return cx, cy, r
        return cx, cy, max(self.w, self.h) / 2

    @property
    def is_siphoning(self) -> bool:
        return self._state == ArchmageState.PHASE2_SIPHON and self._state_timer > 0.5

    # ------------------------------------------------------------------
    # Orb positioning
    # ------------------------------------------------------------------

    def _update_orbs_positions(self, dt: float) -> None:
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2

        # Orbit Buffs (Phase 1)
        hp_ratio = self.health / self.max_health
        is_phase1 = hp_ratio > self.PHASE2_THRESHOLD

        orbit_speed_mult = 1.0

        # Reset per-frame effect caches before accumulating
        self._purple_gravity = (0.0, 0.0)
        self._white_slow_active = False

        if is_phase1:
            for orb in self._orbs:
                if orb["mode"] != "ORBIT":
                    continue
                if orb["type"] == OrbType.ORANGE:
                    orbit_speed_mult += 0.4
                elif orb["type"] == OrbType.WHITE:
                    self._white_slow_active = True
                    # Erratic secondary drift when White is orbiting
                    self.x += math.sin(self._drift_timer * 4.0) * 10.0 * dt
                elif orb["type"] == OrbType.PURPLE:
                    # Mark gravity as active; the pull direction is computed
                    # lazily in get_gravity_pull() using the live player position.
                    self._purple_gravity = (55.0, 0.0)  # (magnitude sentinel, unused_y)

        # Update orbital angle
        self._orb_angle += dt * 1.2 * (1.0 + (1.0 - hp_ratio) * 1.5) * orbit_speed_mult

        for orb in self._orbs:
            if orb["mode"] == "ABSORBED":
                continue  # managed by _update_maze_absorb / draw_shield
            angle = self._orb_angle + orb["base_angle"]
            if orb["mode"] == "ORBIT":
                orb["x"] = cx + math.cos(angle) * self.ORBIT_RADIUS
                orb["y"] = cy + math.sin(angle) * (self.ORBIT_RADIUS * 0.5)
            elif orb["mode"] == "RETURN":
                tx = cx + math.cos(angle) * self.ORBIT_RADIUS
                ty = cy + math.sin(angle) * (self.ORBIT_RADIUS * 0.5)
                orb["x"] += (tx - orb["x"]) * 5.0 * dt
                orb["y"] += (ty - orb["y"]) * 5.0 * dt
                if math.hypot(tx - orb["x"], ty - orb["y"]) < 5.0:
                    orb["mode"] = "ORBIT"

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    def _update_appearing(self, dt: float) -> None:
        self._state_timer -= dt
        tx, ty = self._target_pos
        self.x += (tx - self.x - self.w / 2) * 2.0 * dt
        self.y += (ty - self.y) * 2.5 * dt
        if self._state_timer <= 0.0:
            self._state = ArchmageState.IDLE
            self.active = True

    def _update_idle(self, dt: float, hp_ratio: float) -> None:
        self._state_timer -= dt
        if self._state_timer > 0.0:
            return

        if hp_ratio > self.PHASE2_THRESHOLD:
            self._state = random.choice(
                (ArchmageState.PHASE1_TWIN_ORBS, ArchmageState.PHASE1_EXPANSION)
            )
        elif hp_ratio > self.PHASE3_THRESHOLD:
            self._state = random.choice(
                (ArchmageState.PHASE2_MAZE_ABSORB, ArchmageState.PHASE2_SIPHON)
            )
        else:
            self._state = random.choice(
                (ArchmageState.PHASE1_TWIN_ORBS, ArchmageState.PHASE2_MAZE_ABSORB)
            )

        timings = {
            ArchmageState.PHASE2_MAZE_ABSORB: 5.0,
            ArchmageState.PHASE2_SIPHON: 4.0,
        }
        self._state_timer = timings.get(self._state, 2.5)

    def _update_maze_absorb(self, dt: float) -> None:
        """
        Intro do ataque PHASE2_MAZE:
          - Esferas não-cyan voam para o centro com burst de partículas ao chegar.
          - Esfera cyan contrai para órbita menor.
          - Manto treme progressivamente.
          - Ao concluir, inicia animação de spawn do escudo (SHIELD_SPAWNING).
        """
        self._absorb_timer += dt
        progress = min(1.0, self._absorb_timer / self._absorb_duration)
        self._mantle_speed = 1.0 + progress * 7.0

        cx = self.x + self.w / 2
        cy = self.y + self.h / 2

        for idx, orb in enumerate(self._orbs):
            if orb["type"] == OrbType.CYAN:
                target_r = self.SHIELD_RADIUS * 0.55
                angle = self._orb_angle + orb["base_angle"]
                tx = cx + math.cos(angle) * target_r
                ty = cy + math.sin(angle) * (target_r * 0.5)
                orb["x"] += (tx - orb["x"]) * 6.0 * dt
                orb["y"] += (ty - orb["y"]) * 6.0 * dt
            else:
                orb["mode"] = "ABSORBED"
                # Accelerating lerp toward boss center
                speed = 3.0 + progress * 12.0
                orb["x"] += (cx - orb["x"]) * speed * dt
                orb["y"] += (cy - orb["y"]) * speed * dt

                # Fire burst exactly once when orb reaches the boss center
                dist = math.hypot(cx - orb["x"], cy - orb["y"])
                if dist < 14.0 and not self._orb_absorbed_fired.get(idx, False):
                    self._orb_absorbed_fired[idx] = True
                    self._emit_orb_burst(orb["x"], orb["y"], orb["color"])

        if progress >= 1.0:
            # Shield HP scales with current boss HP so it stays relevant at all phases
            self._shield_max_hp = max(30, int(self.health * 0.15))
            self._shield_hp = self._shield_max_hp
            self._shield_spawning = True
            self._shield_spawn_t = 0.0
            self._shield_rings.clear()
            # Emit initial expansion rings
            for _ in range(3):
                self._shield_rings.append({"r": 8.0, "alpha": 200.0})
            self._absorb_timer = 0.0
            self._mantle_speed = 1.0
            self._orb_absorbed_fired = {}
            self._state = ArchmageState.PHASE2_MAZE
            self._state_timer = 5.0

    def _emit_shield_break(self) -> None:
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        r = self.SHIELD_RADIUS
        rot = self._shield_timer * 0.6
        for k in range(6):
            angle = rot + k * math.tau / 6
            px = cx + math.cos(angle) * r
            py = cy + math.sin(angle) * r
            for _ in range(10):
                a = random.uniform(0, math.tau)
                speed = random.uniform(120.0, 380.0)
                life = random.uniform(0.3, 0.75)
                self._shield_break_particles.append(
                    {
                        "x": px,
                        "y": py,
                        "vx": math.cos(a) * speed,
                        "vy": math.sin(a) * speed,
                        "life": life,
                        "max_life": life,
                        "color": (0, 200, 255),
                    }
                )

    def _emit_orb_burst(self, x: float, y: float, color: tuple[int, int, int]) -> None:
        """Spawns burst particles when an orb is absorbed into the boss."""
        for _ in range(14):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(60.0, 220.0)
            life = random.uniform(0.25, 0.55)
            self._orb_bursts.append(
                {
                    "x": x,
                    "y": y,
                    "vx": math.cos(angle) * speed,
                    "vy": math.sin(angle) * speed,
                    "life": life,
                    "max_life": life,
                    "color": color,
                }
            )

    def _update_maze(
        self, dt: float, player_pos: Tuple[float, float] | None
    ) -> List[Any]:
        self._state_timer -= dt
        spawned: List[Any] = []

        interval = 0.75
        last_tick = (self._state_timer + dt) // interval
        current_tick = self._state_timer // interval

        if last_tick != current_tick and self._state_timer > 1.2:
            tx = random.randint(100, Config.SCREEN_WIDTH - 100)
            if player_pos:
                tx = player_pos[0] + random.choice((-160, 0, 160))
                tx = max(60.0, min(float(Config.SCREEN_WIDTH - 60), tx))
            self._active_telegraphs.append(
                {
                    "x": tx,
                    "is_stalactite": random.random() < 0.5,
                    "timer": 0.9,
                    "charge": 0.0,
                    "target_y": player_pos[1]
                    if player_pos
                    else Config.SCREEN_HEIGHT / 2,
                }
            )

        for t in self._active_telegraphs[:]:
            t["timer"] -= dt
            t["charge"] = 1.0 - (t["timer"] / 0.9)
            if t["timer"] <= 0.0:
                if t["is_stalactite"]:
                    spawned.append(MountainStalactite(t["x"], -10.0, t["target_y"]))
                else:
                    spawned.append(
                        MountainStalagmite(
                            t["x"], float(Config.SCREEN_HEIGHT) + 10.0, t["target_y"]
                        )
                    )
                self._active_telegraphs.remove(t)

        if self._state_timer <= 0.0 and not self._active_telegraphs:
            self._begin_teleport()

        return spawned

    def _update_siphon(self, dt: float, player_pos: Tuple[float, float] | None) -> None:
        self._state_timer -= dt
        if self._state_timer > 0.5:
            self._mantle_speed = min(6.0, self._mantle_speed + dt * 8.0)
        if self._state_timer <= 0.0:
            self._begin_teleport()

    def _begin_teleport(self) -> None:
        # Tear down shield and restore absorbed orbs (e.g. teleporting mid-PHASE2_MAZE)
        if self._shield_active or self._shield_spawning:
            self._shield_active = False
            self._shield_hp = 0
            self._restore_orbs()

        for orb in self._orbs:
            if orb.get("mode") in ("ATTACK", "RETURN"):
                orb["mode"] = "RETURN"
                orb["timer"] = 0.0

        # White orb (Illusion) biases movement toward the faster, visible SLIDE —
        # harder for the player to predict where the boss will end up.
        hp_ratio = self.health / self.max_health
        white_orbiting = hp_ratio > self.PHASE2_THRESHOLD and any(
            o["type"] == OrbType.WHITE and o["mode"] == "ORBIT" for o in self._orbs
        )
        slide_chance = 0.65 if white_orbiting else 0.4

        if random.random() < slide_chance:
            # 40 % chance: glide visibly to new position
            self._slide_target_x = float(random.randint(100, Config.SCREEN_WIDTH - 100))
            self._slide_target_y = float(random.randint(50, 200))
            self._slide_timer = 0.0
            self._state = ArchmageState.SLIDE
        else:
            # 60 % chance: classic fade-out / fade-in teleport
            self._state = ArchmageState.TELEPORT
            self._state_timer = 1.2
            self._teleport_repositioned = False
            self._teleport_wait_timer = 0.0

    def _update_slide(self, dt: float) -> None:
        """Glides boss smoothly to a new position without fading out."""
        self._slide_timer += dt
        t = min(1.0, self._slide_timer / self._slide_duration)
        # Ease-in-out cubic for a snappy but smooth feel
        eased = t * t * (3.0 - 2.0 * t)

        # Drive x/y toward target; lerp physics lets the body trail naturally
        speed = 8.0 + eased * 14.0  # accelerates as it gets closer to target
        self.x += (self._slide_target_x - self.x) * speed * dt
        self.y += (self._slide_target_y - self.y) * speed * dt

        # Collision is live the whole time (boss is visible)
        # but we mark repositioned=True immediately so rect uses new position
        self._teleport_repositioned = True

        if t >= 1.0:
            # Snap to exact target to avoid floating point drift
            self.x = self._slide_target_x
            self.y = self._slide_target_y
            self._state = ArchmageState.IDLE
            self._state_timer = 0.6 + random.uniform(0.0, 0.3)

    def _update_teleport(self, dt: float) -> None:
        # Decrement timer, but we may pause it while waiting for orbs to
        # return to orbit (to avoid repositioning while they still pursue
        # stale targets).
        self._state_timer -= dt

        if self._state_timer > self._TELEPORT_HALF:
            # Phase A: fade out
            self._teleport_visual = max(
                0.0, self._teleport_visual - _TELEPORT_FADE_SPEED * dt
            )
        else:
            # Phase B: wait for orbs to finish returning before repositioning.
            if not self._teleport_repositioned:
                # If any orb is not yet back in orbit, keep the boss invisible
                # and pause the teleport timer until they are.
                if any(orb.get("mode") != "ORBIT" for orb in self._orbs):
                    self._teleport_visual = 0.0
                    # Undo the timer decrement to pause the countdown.
                    self._state_timer += dt
                    # Track how long we've been waiting; if too long, force
                    # the reposition to avoid permanent stalls.
                    self._teleport_wait_timer += dt
                    if self._teleport_wait_timer > 3.0:
                        # give up waiting and allow reposition
                        pass
                    else:
                        return

                # All orbs are in orbit — safe to reposition now.
                self.x = float(random.randint(100, Config.SCREEN_WIDTH - 100))
                self.y = float(random.randint(50, 200))
                # Snap lerp state to new position BEFORE lerp runs this frame
                self._sync_lerp_to_position()
                self._teleport_repositioned = True

            # Fade back in
            self._teleport_visual = min(
                1.0, self._teleport_visual + _TELEPORT_FADE_SPEED * dt
            )

        # Only leave TELEPORT state once we've completed the countdown and
        # also performed the reposition (if required).
        if self._state_timer <= 0.0 and self._teleport_repositioned:
            self._state = ArchmageState.IDLE
            self._state_timer = 0.8 + random.uniform(0.0, 0.4)

    def _update_twin_orbs(
        self, dt: float, player_pos: Tuple[float, float] | None
    ) -> None:
        if not player_pos:
            return
        self._state_timer -= dt

        # Reset cyan repulsion zone — rebuilt below if cyan is attacking
        self._cyan_attack_zone = None

        attacking = [o for o in self._orbs if o["mode"] == "ATTACK"]
        if not attacking and self._state_timer > 1.0:
            for o in random.sample(self._orbs, 2):
                o["mode"] = "ATTACK"
                o["timer"] = 0.0
                o["target_x"], o["target_y"] = player_pos
                # Purple orb starts by computing a flanking target: a point
                # directly behind the player relative to the boss so it can
                # pull the player toward the boss center.
                if o["type"] == OrbType.PURPLE:
                    bx = self.x + self.w / 2
                    by = self.y + self.h / 2
                    # Direction from boss → player
                    dx = player_pos[0] - bx
                    dy = player_pos[1] - by
                    d = math.hypot(dx, dy) or 1.0
                    # Flank target: 80 px behind the player (away from the boss)
                    o["target_x"] = player_pos[0] + (dx / d) * 80.0
                    o["target_y"] = player_pos[1] + (dy / d) * 80.0

        for o in attacking:
            o["timer"] += dt

            # ── Per-type attack FX ──────────────────────────────────────────
            if o["type"] == OrbType.ORANGE:
                # Leaves a heat trail that can damage the player
                if random.random() < 0.4:
                    self._trail_particles.append(
                        {
                            "x": o["x"],
                            "y": o["y"],
                            "vx": random.uniform(-20, 20),
                            "vy": random.uniform(-20, 20),
                            "life": 1.8,
                            "max_life": 1.8,
                            "color": (255, 100, 0),
                            "radius": 7,  # hitbox radius for collision check
                            "damages": True,  # flag consumed by collisions system
                        }
                    )

            elif o["type"] == OrbType.CYAN:
                # Cyan attack: maintain a repulsion aura around itself.
                # We only keep the last (most relevant) attacking cyan.
                _CYAN_REPULSE_R = 55.0
                self._cyan_attack_zone = (o["x"], o["y"], _CYAN_REPULSE_R)

            # ── Movement ────────────────────────────────────────────────────
            dx = o["target_x"] - o["x"]
            dy = o["target_y"] - o["y"]
            dist = math.hypot(dx, dy)

            if dist > 10.0 and o["timer"] < 2.5:
                speed = 300.0

                if o["type"] == OrbType.WHITE:
                    # Erratic jitter — unpredictable micro-teleports
                    speed *= 1.3
                    if random.random() < 0.15:
                        o["x"] += random.uniform(-15, 15)
                        o["y"] += random.uniform(-15, 15)

                elif o["type"] == OrbType.PURPLE:
                    # After reaching the flank position, re-target toward boss
                    # center so it drags the player inward if they collide.
                    bx = self.x + self.w / 2
                    by = self.y + self.h / 2
                    if dist < 30.0:
                        o["target_x"] = bx
                        o["target_y"] = by

                vx, vy = (dx / dist) * speed, (dy / dist) * speed
                wave = math.sin(o["timer"] * 10.0) * 150.0
                o["x"] += (vx + (-vy / speed) * wave) * dt
                o["y"] += (vy + (vx / speed) * wave) * dt
            else:
                o["mode"] = "RETURN"

        if self._state_timer <= 0.0:
            self._begin_teleport()

    def _update_expansion(
        self, dt: float, player_pos: Tuple[float, float] | None
    ) -> None:
        self._state_timer -= dt
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        target_r = 240.0 if self._state_timer > 1.0 else self.ORBIT_RADIUS

        for orb in self._orbs:
            angle = self._orb_angle + orb["base_angle"]
            current_r = math.hypot(orb["x"] - cx, orb["y"] - cy)
            new_r = current_r + (target_r - current_r) * 3.0 * dt
            orb["x"] = cx + math.cos(angle) * new_r
            orb["y"] = cy + math.sin(angle) * (new_r * 0.5)

        if self._state_timer <= 0.0:
            self._begin_teleport()

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead and self._state != ArchmageState.DEFEATED:
            return
        if self._teleport_visual <= 0.02:
            return

        hp_ratio = self.health / self.max_health
        state_key = (
            "flash"
            if self._hit_flash > 0.0
            else ("normal" if hp_ratio > 0.3 else "phase3")
        )

        self._draw_trail_particles(surface)
        self._draw_orbs(surface)
        self._draw_orb_bursts(surface)
        self._draw_shield_break_particles(surface)
        if self._shield_active or self._shield_spawning:
            self._draw_shield(surface)

        if self._state != ArchmageState.DEFEATED:
            self._draw_flowing_mantle(surface, state_key)

        fading = self._teleport_visual < 1.0

        # Draw order (back → front): arms → body → eyes → hat
        parts: list[tuple[str, float, float]] = [
            ("arm", self._l_arm_x, self._l_arm_y),
            ("arm", self._r_arm_x, self._r_arm_y),
            ("body", self._body_x, self._body_y),
        ]

        for part, px, py in parts:
            if fading:
                s = self._get_scaled_sprite(part, state_key, self._teleport_visual)
                base = self._sprites[part][state_key]
                offset_x = (base.get_width() - s.get_width()) // 2
                offset_y = (base.get_height() - s.get_height()) // 2
                surface.blit(s, (int(px) + offset_x, int(py) + offset_y))
            else:
                surface.blit(self._sprites[part][state_key], (int(px), int(py)))

        # Eyes drawn before hat so the hat renders on top
        if self._hit_flash <= 0.0 and self._teleport_visual > 0.5:
            eye_color = (255, 230, 0)
            pygame.draw.rect(
                surface, eye_color, (int(self._eye_l_x), int(self._eye_l_y), 8, 8)
            )
            pygame.draw.rect(
                surface, eye_color, (int(self._eye_r_x), int(self._eye_r_y), 8, 8)
            )

        # Hat is topmost element
        hat_px, hat_py = self._hat_x, self._hat_y
        if fading:
            s = self._get_scaled_sprite("hat", state_key, self._teleport_visual)
            base = self._sprites["hat"][state_key]
            offset_x = (base.get_width() - s.get_width()) // 2
            offset_y = (base.get_height() - s.get_height()) // 2
            surface.blit(s, (int(hat_px) + offset_x, int(hat_py) + offset_y))
        else:
            surface.blit(self._sprites["hat"][state_key], (int(hat_px), int(hat_py)))

        self._draw_health_bar(surface)

        for t in self._active_telegraphs:
            self._draw_telegraph_marker(surface, t)

    def _draw_shield(self, surface: pygame.Surface) -> None:
        """Hexagonal shield with spawn animation (scale-in + burst rings) and HP opacity."""
        cx = int(self.x + self.w / 2)
        cy = int(self.y + self.h / 2)
        hp_pct = max(0.0, self._shield_hp / self._shield_max_hp)

        # Determine current radius and opacity based on spawn progress
        if self._shield_spawning:
            # Ease-out cubic for satisfying pop-in feel
            t = self._shield_spawn_t
            eased = 1.0 - (1.0 - t) ** 3
            r = self.SHIELD_RADIUS * eased
            opacity_scale = eased
        else:
            r = self.SHIELD_RADIUS
            opacity_scale = 1.0

        pulse = 0.7 + 0.3 * math.sin(self._shield_timer * 5.0)
        rim_alpha = max(0, min(255, int((140 + 80 * hp_pct * pulse) * opacity_scale)))

        # Burst rings (emitted at spawn moment, radiate outward)
        for ring in self._shield_rings:
            ring_alpha = max(0, min(255, int(ring["alpha"])))
            if ring_alpha <= 0:
                continue
            ring_r = int(ring["r"])
            if ring_r <= 0:
                continue
            ring_surf = pygame.Surface(
                (ring_r * 2 + 4, ring_r * 2 + 4), pygame.SRCALPHA
            )
            rc = ring_r + 2
            pygame.draw.circle(
                ring_surf, (0, 210, 255, ring_alpha), (rc, rc), ring_r, 2
            )
            surface.blit(ring_surf, (cx - rc, cy - rc))

        if r < 2:
            return

        # Hexagon outline only (rotates, scales in during spawn)
        rot_offset = self._shield_timer * 0.6
        hex_pts = [
            (
                cx + int(r * math.cos(rot_offset + k * math.tau / 6)),
                cy + int(r * math.sin(rot_offset + k * math.tau / 6)),
            )
            for k in range(6)
        ]
        pygame.draw.polygon(surface, (0, 200, 255, rim_alpha), hex_pts, 3)

        # HP bar — only when fully spawned
        if not self._shield_spawning:
            bar_w = int(self.SHIELD_RADIUS * 1.6)
            bar_h = 4
            bx = cx - bar_w // 2
            by = cy + int(self.SHIELD_RADIUS) + 8
            pygame.draw.rect(surface, (0, 40, 60), (bx, by, bar_w, bar_h))
            pygame.draw.rect(
                surface, (0, 220, 255), (bx, by, int(bar_w * hp_pct), bar_h)
            )
            pygame.draw.rect(surface, (0, 160, 200), (bx, by, bar_w, bar_h), 1)

    def _draw_orb_bursts(self, surface: pygame.Surface) -> None:
        """Draws particle bursts emitted when orbs are absorbed."""
        for p in self._orb_bursts:
            ratio = max(0.0, p["life"] / p["max_life"])
            alpha = int(220 * ratio)
            radius = max(1, int(3 + 4 * ratio))
            s = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(
                s, (*p["color"], alpha), (radius + 1, radius + 1), radius
            )
            surface.blit(s, (int(p["x"]) - radius - 1, int(p["y"]) - radius - 1))

    def _draw_trail_particles(self, surface: pygame.Surface) -> None:
        """Draws heat-trail particles left by the Orange orb (and any future trail sources)."""
        for p in self._trail_particles:
            ratio = max(0.0, p["life"] / p["max_life"])
            alpha = int(200 * ratio)
            # Shrink radius as the particle ages so it looks like it cools/fades
            base_r = p.get("radius", 5)
            radius = max(1, int(base_r * (0.4 + 0.6 * ratio)))
            s = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
            # Orange trail: hot core (bright) fades to dim ember
            r_c, g_c, b_c = p["color"]
            core_color = (
                min(255, r_c),
                min(255, int(g_c * ratio + 40 * (1 - ratio))),
                b_c,
                alpha,
            )
            pygame.draw.circle(s, core_color, (radius + 1, radius + 1), radius)
            surface.blit(s, (int(p["x"]) - radius - 1, int(p["y"]) - radius - 1))

    def _draw_shield_break_particles(self, surface: pygame.Surface) -> None:
        for p in self._shield_break_particles:
            ratio = max(0.0, p["life"] / p["max_life"])
            alpha = int(240 * ratio)
            radius = max(1, int(2 + 5 * ratio))
            s = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(
                s, (*p["color"], alpha), (radius + 1, radius + 1), radius
            )
            surface.blit(s, (int(p["x"]) - radius - 1, int(p["y"]) - radius - 1))

    def _draw_health_bar(self, surface: pygame.Surface) -> None:
        if self.health <= 0 or self._state == ArchmageState.APPEARING:
            return
        hp_ratio = max(0.0, self.health / self.max_health)
        bar_w, bar_h = 240, 8
        bx = self._hat_x + self._sprites["hat"]["normal"].get_width() / 2 - bar_w / 2
        by = self._hat_y - 30.0
        pygame.draw.rect(surface, (20, 20, 35), (int(bx), int(by), bar_w, bar_h))
        color = (0, 255, 200) if hp_ratio > 0.3 else (255, 50, 50)
        pygame.draw.rect(
            surface, color, (int(bx), int(by), int(bar_w * hp_ratio), bar_h)
        )
        pygame.draw.rect(surface, (120, 120, 180), (int(bx), int(by), bar_w, bar_h), 1)

    def _draw_telegraph_marker(
        self, surface: pygame.Surface, t: dict[str, Any]
    ) -> None:
        mr = int(14 + t["charge"] * 18)
        diam = mr * 4
        ms = pygame.Surface((diam, diam), pygame.SRCALPHA)
        mc = diam // 2
        alpha = int(100 + t["charge"] * 120)
        color = (
            (255, 235, 140, alpha) if not t["is_stalactite"] else (160, 220, 255, alpha)
        )
        pygame.draw.circle(ms, color, (mc, mc), mr, width=2)
        pygame.draw.line(ms, color, (mc, 0), (mc, diam), width=1)
        pygame.draw.line(ms, color, (0, mc), (diam, mc), width=1)
        draw_y = Config.SCREEN_HEIGHT - mr * 2 if not t["is_stalactite"] else mr * 2
        surface.blit(ms, (int(t["x"]) - mc, draw_y - mc))

    def _draw_flowing_mantle(self, surface: pygame.Surface, state_key: str) -> None:
        color = (80, 60, 150) if state_key == "normal" else (100, 20, 50)
        if state_key == "flash":
            color = (255, 255, 255)
        base_y = self._body_y + len(BODY_MAP) * self._SCALE - 5
        # Per-flap freq/phase/amp gives each triangle independent motion — idle animation.
        _FLAP_FREQ = (1.00, 1.30, 0.90, 1.15)
        _FLAP_PHASE = (0.00, 1.10, 2.30, 3.70)
        _FLAP_AMP = (10.0, 14.0, 11.0, 13.0)
        for i in range(4):
            offset_x = i * 12 + 6
            wave = (
                math.sin(self._mantle_timer * 4.0 * _FLAP_FREQ[i] + _FLAP_PHASE[i])
                * _FLAP_AMP[i]
            )
            pts = [
                (self._body_x + offset_x, base_y),
                (self._body_x + offset_x + 10, base_y),
                (self._body_x + offset_x + 5 + wave, base_y + 35),
            ]
            pygame.draw.polygon(surface, color, pts)

    def _draw_orbs(self, surface: pygame.Surface) -> None:
        sz = self.ORB_SIZE
        for i, orb in enumerate(self._orbs):
            if orb["mode"] == "ABSORBED":
                continue
            ox, oy = int(orb["x"]), int(orb["y"])
            glow_diam = sz * 2 + 16
            glow = pygame.Surface((glow_diam, glow_diam), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*orb["color"], 40), (sz + 8, sz + 8), sz + 8)
            surface.blit(glow, (ox - sz - 8, oy - sz - 8))
            pygame.draw.circle(surface, orb["color"], (ox, oy), sz)

            # Rotating rune — pre-bake the base, rotate is still per-frame but small
            rune = pygame.Surface((12, 12), pygame.SRCALPHA)
            pygame.draw.rect(rune, (255, 255, 255, 200), (0, 0, 12, 12), 2)
            rotated = pygame.transform.rotate(rune, self._orb_angle * 100.0 + i * 45.0)
            surface.blit(
                rotated, (ox - rotated.get_width() // 2, oy - rotated.get_height() // 2)
            )

    # ------------------------------------------------------------------
    # Combat interface
    # ------------------------------------------------------------------

    def _restore_orbs(self) -> None:
        """Reativa as esferas absorvidas quando o escudo é destruído."""
        self._shield_spawning = False
        self._shield_spawn_t = 0.0
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        for orb in self._orbs:
            if orb["mode"] == "ABSORBED":
                angle = self._orb_angle + orb["base_angle"]
                orb["x"] = cx + math.cos(angle) * self.ORBIT_RADIUS
                orb["y"] = cy + math.sin(angle) * (self.ORBIT_RADIUS * 0.5)
                orb["mode"] = "ORBIT"

    def take_damage(
        self, amount: int = 1, hit_x: float | None = None, hit_y: float | None = None
    ) -> None:
        if self.dead or not self.active:
            return

        # Phase 1 Protection: Cyan orb can intercept hits if nearby
        if self.health / self.max_health > self.PHASE2_THRESHOLD:
            if hit_x is not None and hit_y is not None:
                for orb in self._orbs:
                    if orb["type"] == OrbType.CYAN and orb["mode"] != "ABSORBED":
                        dist = math.hypot(orb["x"] - hit_x, orb["y"] - hit_y)
                        if dist < self.ORB_SIZE + 20:
                            # Cyan orb intercepts! Flash it instead
                            self._hit_flash = 0.08
                            # We could give the orb "HP" but for now let's just make it a shield
                            return

        # Shield absorbs damage while active OR while spawning
        if (self._shield_active or self._shield_spawning) and self._shield_hp > 0:
            self._shield_hp -= amount
            self._hit_flash = 0.08
            if self._shield_hp <= 0:
                self._shield_hp = 0
                self._shield_active = False
                self._emit_shield_break()
                self._restore_orbs()
            return
        self.health -= amount
        self._hit_flash = 0.15
        if self.health <= 0:
            self.dead = True
            self._state = ArchmageState.DEFEATED

    # ------------------------------------------------------------------
    # Passive orb-effect API  (consumed by collisions / player systems)
    # ------------------------------------------------------------------

    def get_gravity_pull(self, player_x: float, player_y: float) -> tuple[float, float]:
        """Return the gravitational acceleration (ax, ay) in px/s² that the
        Purple orb exerts on the player this frame.

        Returns (0, 0) when the effect is inactive.  The caller must multiply
        by dt before adding to player velocity::

            ax, ay = boss.get_gravity_pull(px, py)
            vel_x += ax * dt
            vel_y += ay * dt
        """
        magnitude = self._purple_gravity[0]  # sentinel stored by _update_orbs_positions
        if magnitude == 0.0:
            return (0.0, 0.0)
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        dx = cx - player_x
        dy = cy - player_y
        dist = math.hypot(dx, dy) or 1.0
        # Inverse-square-root falloff: strong up close, gentle at distance
        pull = min(magnitude, magnitude * (150.0 / dist) ** 0.6)
        return (dx / dist * pull, dy / dist * pull)

    def get_cyan_repulsion_zone(self) -> tuple[float, float, float] | None:
        """Return (x, y, radius) of the Cyan orb's projectile-repulsion aura
        while it is attacking, or ``None`` when inactive.

        Any bullet whose centre falls inside this circle should be deflected or
        destroyed by the collision system.
        """
        return self._cyan_attack_zone

    def get_orange_trail_hazards(self) -> list[tuple[float, float, float]]:
        """Return a list of (x, y, radius) circles representing active Orange
        heat-trail particles that can damage the player on contact.

        Only particles flagged ``damages=True`` are included.
        """
        return [
            (p["x"], p["y"], float(p.get("radius", 5)))
            for p in self._trail_particles
            if p.get("damages")
        ]

    def get_white_slow_zone(self) -> tuple[float, float, float] | None:
        """Return (x, y, radius) of the White orb's bullet-slowing field while
        it is orbiting (Phase 1), or ``None`` when inactive.

        Bullets passing through this zone should have their speed halved.
        """
        if not self._white_slow_active:
            return None
        for orb in self._orbs:
            if orb["type"] == OrbType.WHITE and orb["mode"] == "ORBIT":
                return (orb["x"], orb["y"], 50.0)
        return None

    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.take_damage(damage, hit_x, hit_y)
        if self.dead:
            return HitResult(
                killed=True,
                points=5000,
                explosion_size=100,
                sound=hit_sounds.EXPLOSION_ALIEN,
            )
        return HitResult(explosion_size=20, sound=hit_sounds.BOSS_DAMAGE)

    def should_remove(self) -> bool:
        return self.dead
