from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Final

import pygame

from ..core.assets import get_font
from ..core.config import config as Config
from .fire_zone import FireZone
from .mountain_mage import MountainStalactite, MountainStalagmite

if TYPE_CHECKING:
    from ..systems.hit_result import HitResult


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TELEPORT_FADE_SPEED: Final = 6.0
_LERP_BODY: Final = 10.0
_LERP_HAT: Final = 5.0
_LERP_EYE: Final = 8.0
_LERP_ARM: Final = 7.0

# Power timings
_ABSORPTION_DURATION: Final = 1.2
_POWER_DURATION_MIN: Final = 8.0
_POWER_DURATION_MAX: Final = 12.0
_ABSORPTION_COOLDOWN: Final = 3.0
_PHASE3_COMBO_DURATION: Final = 10.0
_OVERLOAD_DURATION: Final = 12.0
_OVERLOAD_COOLDOWN: Final = 35.0
_VULNERABLE_DURATION: Final = 5.0
_CYAN_REPULSE_RADIUS: Final = 120.0
_CYAN_SHIELD_COLOR: Final[tuple[int, int, int]] = (
    0,
    220,
    255,
)  # canonical cyan used for shield tint & particles
_PHASE2_STALAGMITE_INTERVAL: Final = 1.4
_PHASE3_FIREZONE_INTERVAL: Final = 2.0
_PHASE3_STALAGMITE_INTERVAL: Final = 1.2
_PHASE3_COMBO_COOLDOWN: Final = 1.0
_FIREZONE_WARNING_DURATION: Final = 0.9
_FIREZONE_RADIUS_SCALE: Final = 2.0
_MAX_FIRE_ZONES: Final = 5

# Wander movement
_WANDER_SPEED: Final = 105.0
_WANDER_INTERVAL_MIN: Final = 2.0
_WANDER_INTERVAL_MAX: Final = 4.5

# Particle emission
_SHIELD_BREAK_PARTICLE_COUNT: Final = 10
_ORB_BURST_PARTICLE_COUNT: Final = 14
_SHIELD_RING_COUNT: Final = 3
_SHIELD_RING_EXPAND_SPEED: Final = 220.0
_SHIELD_RING_FADE_SPEED: Final = 280.0

# Flap animation (module level — not reallocated each draw call)
_FLAP_FREQ: Final[tuple[float, ...]] = (1.00, 1.30, 0.90, 1.15)
_FLAP_PHASE: Final[tuple[float, ...]] = (0.00, 1.10, 2.30, 3.70)
_FLAP_AMP: Final[tuple[float, ...]] = (10.0, 14.0, 11.0, 13.0)
_FLAP_COUNT: Final = 4
_FLAP_OFFSET_X_STEP: Final = 12
_FLAP_OFFSET_X_BASE: Final = 6
_FLAP_BASE_HEIGHT: Final = 35

# Teleport wait safety threshold
_TELEPORT_MAX_WAIT: Final = 3.0

# Intro sequence
_INTRO_ORB_SPAWN_INTERVAL: Final = 1.5
_INTRO_DIM_MAX: Final = 170
_INTRO_DIM_FADE_IN: Final = 1.8
_INTRO_DIM_FADE_OUT: Final = 0.45
_INTRO_BOSS_FADE_IN: Final = 0.6
_INTRO_ORB_BIRTH_DURATION: Final = 0.75

# Eye geometry offsets (relative to boss center)
_EYE_L_OFFSET_X: Final = -18.0
_EYE_R_OFFSET_X: Final = 10.0
_EYE_SIZE: Final = 8


class ArchmageState(Enum):
    APPEARING = auto()
    INTRO = auto()
    IDLE = auto()
    ABSORBING_ORB = auto()
    USING_POWER = auto()
    COOLDOWN = auto()
    PHASE2_DEFENSE = auto()
    PHASE2_VULNERABLE = auto()
    PHASE3_COMBOS = auto()
    PHASE3_OVERLOAD = auto()
    PHASE3_VULNERABLE = auto()
    TELEPORT = auto()
    SLIDE = auto()
    DEFEATED = auto()


class OrbType(Enum):
    CYAN = auto()  # Shield
    PURPLE = auto()  # Stalagmites
    ORANGE = auto()  # FireZones
    WHITE = auto()  # Dodge


class OrbMode(Enum):
    """Explicit enum replaces the fragile string literals 'ORBIT', 'ATTACK', etc."""

    ORBIT = auto()
    ATTACK = auto()
    RETURN = auto()
    ABSORBED = auto()


# ---------------------------------------------------------------------------
# Data classes — replace plain dicts for structured game objects
# ---------------------------------------------------------------------------

Color = tuple[int, int, int]


@dataclass
class Orb:
    """Represents one of the four orbiting companion spheres."""

    type: OrbType
    color: Color
    x: float = 0.0
    y: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    base_angle: float = 0.0
    mode: OrbMode = OrbMode.ORBIT
    timer: float = 0.0


@dataclass
class Particle:
    """Generic physics particle (used for orb bursts, shield break, trail)."""

    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: Color
    # Optional fields used by specific particle types
    radius: int = 5
    damages: bool = False
    apply_gravity: bool = False
    apply_drag: bool = False


@dataclass
class ShieldRing:
    r: float
    alpha: float


@dataclass
class Telegraph:
    x: float
    is_stalactite: bool
    timer: float
    charge: float
    target_y: float


@dataclass
class FireZoneWarning:
    x: float
    y: float
    timer: float
    charge: float
    radius: int
    duration: float


# ---------------------------------------------------------------------------
# Pixel maps
# ---------------------------------------------------------------------------

HAT_MAP: Final[list[str]] = [
    ".........H........",
    "........H*H.......",
    ".......H**H.......",
    "......H***H.......",
    ".....HH****H......",
    "....H******HH.....",
    "...HH********H....",
    "..HHHHHHHHHHHHHH..",
    ".HOOOOOOOOOOOOOOH.",
    "H****************H",
]

BODY_MAP: Final[list[str]] = [
    "....GGGGGGGG....",
    "...GBBBBBBBBG...",
    "..GBBMMMMMMBBG..",
    "..BBMEEEEEEMBB..",
    "..BBMEEEEEEMBB..",
    "..BBOOOOOOOOBB.",
    "..BBBB....BBBB..",
    ".BBBB......BBBB.",
]

ARM_MAP: Final[list[str]] = [
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

_PALETTES: Final[dict[str, dict[str, Color]]] = {
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

_CHAR_TO_KEY: Final[dict[str, str]] = {
    "H": "hat",
    "*": "hat_hl",
    "M": "metal",
    "V": "visor",
    "E": "core",
    "D": "joint",
    "O": "gold",
    "G": "gola",
    "B": "robe",
}


# ---------------------------------------------------------------------------
# ResonanceWave
# ---------------------------------------------------------------------------


class ResonanceWave:
    """Expanding circular shockwave emitted during Phase 3 Resonance."""

    _MAX_RADIUS: Final = 450.0
    _SPEED: Final = 280.0

    def __init__(self, x: float, y: float, color: Color) -> None:
        self.x = x
        self.y = y
        self.radius: float = 10.0
        self.color = color
        self.dead = False
        self.causes_damage = True
        # Reuse a single Surface; resize only when the diameter changes.
        self._cached_diam: int = 0
        self._surf: pygame.Surface | None = None

    @property
    def rect(self) -> pygame.Rect:
        r = int(self.radius)
        return pygame.Rect(int(self.x) - r, int(self.y) - r, r * 2, r * 2)

    def update(self, dt: float) -> None:
        self.radius += self._SPEED * dt
        if self.radius >= self._MAX_RADIUS:
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        alpha = max(0, int(255 * (1.0 - self.radius / self._MAX_RADIUS)))
        diam = int(self.radius * 2) + 10
        # Only reallocate the surface when the diameter changes bucket (every 2 px)
        if self._surf is None or diam != self._cached_diam:
            self._surf = pygame.Surface((diam, diam), pygame.SRCALPHA)
            self._cached_diam = diam
        else:
            self._surf.fill((0, 0, 0, 0))
        cx = cy = diam // 2
        pygame.draw.circle(
            self._surf, (*self.color, alpha // 2), (cx, cy), int(self.radius), 4
        )
        surface.blit(self._surf, (int(self.x) - cx, int(self.y) - cy))

    def on_ship_contact(self, _cx: float, _cy: float) -> "HitResult":
        from ..systems.hit_result import HitResult

        return HitResult(killed=False)

    def should_remove(self) -> bool:
        return self.dead


# ---------------------------------------------------------------------------
# CloudArchmageBoss
# ---------------------------------------------------------------------------


class CloudArchmageBoss:
    MAX_HEALTH: Final[int] = 1200
    WIDTH: Final[int] = 80
    HEIGHT: Final[int] = 110

    PHASE2_THRESHOLD: Final[float] = 0.5
    PHASE3_THRESHOLD: Final[float] = 0.3
    ORBIT_RADIUS: Final[float] = 130.0
    ORB_SIZE: Final[int] = 18

    SHIELD_MAX_HP: Final[int] = 80
    SHIELD_RADIUS: Final[float] = 95.0
    _SCALE: Final[int] = 4
    _SHIELD_SPAWN_DUR: Final[float] = 0.55
    _TELEPORT_HALF: Final[float] = 0.6

    def __init__(self, x: float | None = None, y: float | None = None) -> None:
        sw = Config.SCREEN_WIDTH
        self.w, self.h = self.WIDTH, self.HEIGHT
        self.x: float = x if x is not None else sw / 2 - self.w / 2
        self.y: float = y if y is not None else -self.h - 50.0

        # Lerp targets — zero-initialised; snapped after sprites are baked
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

        self._state: ArchmageState = ArchmageState.INTRO
        self._state_timer: float = 2.5
        self._hit_flash: float = 0.0
        self._pulse_timer: float = 0.0
        self._orb_angle: float = 0.0
        self._mantle_timer: float = 0.0
        self._mantle_speed: float = 1.0
        self._intro_spawn_timer: float = 0.0
        self._intro_orbs_spawned: int = 0
        self._intro_orb_births: list[Particle] = []
        self._intro_dim_alpha: float = 0.0
        self._intro_reveal_timer: float = 0.0
        self._intro_boss_alpha: float = 0.0
        self._miss_timer: float = 0.0
        self._miss_x: float = 0.0
        self._miss_y: float = 0.0
        self._miss_dy: float = -0.5
        self._white_dodge_was_miss: bool = False

        self._gradient_timer: float = 0.0
        self._displayed_tint: tuple[float, float, float] | None = None
        # Cache: {(r, g, b, alpha_int): Surface} — reused across frames
        # Cache: (qr, qg, qb, w, h) -> overlay já mascarado pela alpha do sprite
        self._tint_cache: dict[tuple[int, int, int, int, int], pygame.Surface] = {}

        self._drift_timer: float = 0.0
        self._wander_target_x: float = sw / 2.0
        self._wander_target_y: float = 160.0
        self._wander_timer: float = 0.0
        self._teleport_visual: float = 1.0
        self._teleport_repositioned: bool = False
        self._teleport_wait_timer: float = 0.0
        self._resume_state: ArchmageState = ArchmageState.IDLE

        self._slide_target_x: float = 0.0
        self._slide_target_y: float = 0.0
        self._slide_start_x: float = 0.0
        self._slide_start_y: float = 0.0
        self._slide_timer: float = 0.0
        self._slide_duration: float = 0.42
        self._slide_is_forced: bool = False
        self._hit_count: int = 0

        # Shield state
        self._shield_hp: int = 0
        self._shield_max_hp: int = self.SHIELD_MAX_HP
        self._shield_timer: float = 0.0
        self._shield_active: bool = False
        self._absorb_timer: float = 0.0
        self._absorb_duration: float = _ABSORPTION_DURATION
        self._shield_spawn_t: float = 0.0
        self._shield_spawning: bool = False
        self._shield_spawn_dur: float = self._SHIELD_SPAWN_DUR
        self._shield_rings: list[ShieldRing] = []
        self._orb_absorbed_fired: dict[int, bool] = {}
        self._cyan_attack_zone: tuple[float, float, float] | None = None

        # Refactored Power State
        self._absorbed_orbs: list[Orb] = []
        self._active_orb_index: int | None = None
        self._active_power: Orb | None = None
        self._power_timer: float = 0.0
        self._cooldown_timer: float = 0.0
        self._overload_timer: float = 0.0
        self._overload_cooldown: float = 0.0
        self._vulnerable_timer: float = 0.0
        self._stalagmite_spawn_timer: float = 0.0
        self._fire_zone_spawn_timer: float = 0.0
        self._phase3_combo_powers: tuple[OrbType, ...] | None = None
        self._spawned_fire_zones: list[FireZone] = []

        # Particle lists — now typed as list[Particle]
        self._orb_bursts: list[Particle] = []
        self._shield_break_particles: list[Particle] = []
        self._trail_particles: list[Particle] = []

        # Passive orb effect caches
        self._white_dodge_active: bool = False

        _orb_defs: list[tuple[OrbType, Color]] = [
            (OrbType.CYAN, _CYAN_SHIELD_COLOR),
            (OrbType.PURPLE, (180, 50, 255)),
            (OrbType.ORANGE, (255, 140, 0)),
            (OrbType.WHITE, (220, 240, 255)),
        ]
        self._orbs: list[Orb] = [
            Orb(
                type=orb_type,
                color=color,
                base_angle=i * (math.tau / len(_orb_defs)),
            )
            for i, (orb_type, color) in enumerate(_orb_defs)
        ]
        for orb in self._orbs:
            orb.mode = OrbMode.ABSORBED
            orb.x = self.x + self.w / 2
            orb.y = self.y + self.h / 2

        self._target_pos: tuple[float, float] = (sw / 2.0, 160.0)
        self._active_telegraphs: list[Telegraph] = []
        self._firezone_warnings: list[FireZoneWarning] = []

        # Pre-bake all sprites once; never recreate inside draw()
        self._sprites: dict[str, dict[str, pygame.Surface]] = {
            "hat": {},
            "body": {},
            "arm": {},
        }
        # Teleport scale cache: {(part, state_key, scale_pct): Surface}
        self._teleport_cache: dict[tuple[str, str, int], pygame.Surface] = {}
        self._render_all_parts()
        self._sync_lerp_to_position()
        self._start_intro_sequence()

    # ------------------------------------------------------------------
    # Sprite baking
    # ------------------------------------------------------------------

    def _render_all_parts(self) -> None:
        for state_name, pal in _PALETTES.items():
            self._sprites["hat"][state_name] = self._bake_surface(HAT_MAP, pal)
            self._sprites["body"][state_name] = self._bake_surface(BODY_MAP, pal)
            self._sprites["arm"][state_name] = self._bake_surface(ARM_MAP, pal)

    def _bake_surface(
        self, pixelmap: list[str], pal: dict[str, Color]
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
        if pygame.display.get_init():
            return surf.convert_alpha()
        return surf

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
            scaled = pygame.transform.scale(base, (w, h))
            if pygame.display.get_init():
                scaled = scaled.convert_alpha()
            self._teleport_cache[cache_key] = scaled
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
        self._eye_l_x = bx + _EYE_L_OFFSET_X
        self._eye_l_y = (self._hat_y + self._body_y + 20.0) / 2
        self._eye_r_x = bx + _EYE_R_OFFSET_X
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
        self._eye_l_x += (bx + _EYE_L_OFFSET_X - self._eye_l_x) * _LERP_EYE * dt
        self._eye_l_y += (ey - self._eye_l_y) * _LERP_EYE * dt
        self._eye_r_x += (bx + _EYE_R_OFFSET_X - self._eye_r_x) * _LERP_EYE * dt
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
        self, dt: float, player_pos: tuple[float, float] | None = None
    ) -> list[Any]:
        if self.dead:
            return []

        self._pulse_timer += dt
        self._gradient_timer += dt
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

        self._update_shield_rings(dt)
        self._update_particles(dt)
        self._update_miss_indicator(dt)

        if self._state not in (
            ArchmageState.PHASE2_DEFENSE,
            ArchmageState.PHASE2_VULNERABLE,
            ArchmageState.PHASE3_OVERLOAD,
            ArchmageState.PHASE3_VULNERABLE,
            ArchmageState.INTRO,
        ):
            self._mantle_speed = max(1.0, self._mantle_speed - dt * 4.0)
        hp_ratio = self.health / self.max_health

        # Constant mystic drift (not during cinematic states)
        _CINEMATIC_STATES = (
            ArchmageState.INTRO,
            ArchmageState.APPEARING,
            ArchmageState.TELEPORT,
            ArchmageState.SLIDE,
            ArchmageState.DEFEATED,
        )
        if self._state not in _CINEMATIC_STATES:
            self._drift_timer += dt
            self._wander_timer -= dt
            cx = self.x + self.w / 2
            cy = self.y + self.h / 2
            dist_to_wander = math.hypot(
                self._wander_target_x - cx, self._wander_target_y - cy
            )
            if self._wander_timer <= 0.0 or dist_to_wander < 40.0:
                self._wander_target_x = random.uniform(
                    120.0, Config.SCREEN_WIDTH - 120.0
                )
                self._wander_target_y = random.uniform(
                    60.0, Config.SCREEN_HEIGHT * 0.55
                )
                self._wander_timer = random.uniform(
                    _WANDER_INTERVAL_MIN, _WANDER_INTERVAL_MAX
                )
            if dist_to_wander > 10.0:
                wander_spd = _WANDER_SPEED * (1.0 + (1.0 - hp_ratio) * 0.8)
                nx = (self._wander_target_x - cx) / dist_to_wander
                ny = (self._wander_target_y - cy) / dist_to_wander
                self.x += nx * wander_spd * dt
                self.y += ny * wander_spd * dt
            self.x += math.sin(self._drift_timer * 2.3) * 12.0 * dt
            self.y += math.cos(self._drift_timer * 1.7) * 8.0 * dt
            self.x = _clamp(self.x, 50.0, Config.SCREEN_WIDTH - self.w - 50.0)
            self.y = _clamp(self.y, 30.0, Config.SCREEN_HEIGHT * 0.6 - self.h)

        # Fade-in recovery outside teleport
        if self._state not in (ArchmageState.TELEPORT, ArchmageState.INTRO):
            self._teleport_visual = min(
                1.0, self._teleport_visual + _TELEPORT_FADE_SPEED * dt
            )

        # Orbital speed scales with damage taken (handled in _update_orbs_positions)

        spawned: list[Any] = []
        self._update_phase2_telegraphs(dt, spawned)
        self._update_firezone_warnings(dt, spawned)

        match self._state:
            case ArchmageState.INTRO:
                self._update_intro(dt)
            case ArchmageState.APPEARING:
                self._update_appearing(dt)
            case ArchmageState.IDLE:
                self._update_idle(dt, hp_ratio)
            case ArchmageState.ABSORBING_ORB:
                self._update_absorbing_orb(dt)
            case ArchmageState.USING_POWER:
                spawned.extend(self._update_using_power(dt, player_pos))
            case ArchmageState.COOLDOWN:
                self._update_cooldown(dt)
            case ArchmageState.PHASE2_DEFENSE:
                spawned.extend(self._update_phase2_defense(dt, player_pos))
            case ArchmageState.PHASE2_VULNERABLE:
                self._update_phase2_vulnerable(dt)
            case ArchmageState.PHASE3_COMBOS:
                spawned.extend(self._update_phase3_combos(dt, player_pos))
            case ArchmageState.PHASE3_OVERLOAD:
                spawned.extend(self._update_phase3_overload(dt, player_pos))
            case ArchmageState.PHASE3_VULNERABLE:
                self._update_phase3_vulnerable(dt)
            case ArchmageState.TELEPORT:
                self._update_teleport(dt)
            case ArchmageState.SLIDE:
                self._update_slide(dt)
            case ArchmageState.DEFEATED:
                pass

        if self._state != ArchmageState.INTRO:
            self._update_orbs_positions(dt)
        self._update_lerp_physics(dt)
        self._update_displayed_tint(dt)
        return spawned

    def _update_shield_rings(self, dt: float) -> None:
        """Expand and fade shield rings; prune dead ones via list comprehension (O(n), no .remove)."""
        for ring in self._shield_rings:
            ring.r += _SHIELD_RING_EXPAND_SPEED * dt
            ring.alpha -= _SHIELD_RING_FADE_SPEED * dt
        self._shield_rings = [r for r in self._shield_rings if r.alpha > 0]

    def _update_particles(self, dt: float) -> None:
        """Advance all particle lists; prune dead entries in a single pass."""
        # Orb burst particles (gravity enabled)
        for p in self._orb_bursts:
            p.life -= dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += 60.0 * dt
        self._orb_bursts = [p for p in self._orb_bursts if p.life > 0]

        # Shield break particles (drag enabled)
        drag = max(0.0, 1.0 - 3.5 * dt)
        for p in self._shield_break_particles:
            p.life -= dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vx *= drag
            p.vy *= drag
        self._shield_break_particles = [
            p for p in self._shield_break_particles if p.life > 0
        ]

        # Trail particles (plain physics)
        for p in self._trail_particles:
            p.life -= dt
            p.x += p.vx * dt
            p.y += p.vy * dt
        self._trail_particles = [p for p in self._trail_particles if p.life > 0]

        for p in self._intro_orb_births:
            p.life -= dt
            p.x += p.vx * dt
            p.y += p.vy * dt
        self._intro_orb_births = [p for p in self._intro_orb_births if p.life > 0]

    def _start_intro_sequence(self) -> None:
        self._state = ArchmageState.INTRO
        self.active = False
        self._state_timer = 0.0
        self._intro_spawn_timer = 0.0
        self._intro_orbs_spawned = 0
        self._intro_dim_alpha = 0.0
        self._intro_reveal_timer = 0.0
        self._intro_boss_alpha = 0.0
        self._teleport_visual = 0.0
        self._hit_flash = 0.0
        self._white_dodge_active = False

    def _spawn_intro_orb_birth(self, orb: Orb) -> None:
        for _ in range(18):
            angle = random.uniform(0.0, math.tau)
            speed = random.uniform(70.0, 180.0)
            life = random.uniform(0.35, _INTRO_ORB_BIRTH_DURATION)
            self._intro_orb_births.append(
                Particle(
                    x=orb.x,
                    y=orb.y,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed - 50.0,
                    life=life,
                    max_life=life,
                    color=orb.color,
                    radius=4,
                )
            )

    def _update_intro(self, dt: float) -> None:
        self._intro_spawn_timer += dt
        self._intro_dim_alpha = min(
            _INTRO_DIM_MAX,
            self._intro_dim_alpha + (_INTRO_DIM_MAX / _INTRO_DIM_FADE_IN) * dt,
        )

        if self._intro_orbs_spawned < len(self._orbs):
            if self._intro_spawn_timer >= _INTRO_ORB_SPAWN_INTERVAL:
                self._intro_spawn_timer -= _INTRO_ORB_SPAWN_INTERVAL
                orb = self._orbs[self._intro_orbs_spawned]
                self._intro_orbs_spawned += 1
                orb.mode = OrbMode.ORBIT
                orb.timer = 0.0
                cx_orb = self.x + self.w / 2
                cy_orb = self.y + self.h / 2
                orb.x = cx_orb + math.cos(orb.base_angle) * self.ORBIT_RADIUS
                orb.y = cy_orb + math.sin(orb.base_angle) * (self.ORBIT_RADIUS * 0.5)
                self._spawn_intro_orb_birth(orb)

        for orb in self._orbs:
            if orb.mode == OrbMode.ORBIT:
                orb.timer += dt

        if self._intro_orbs_spawned >= len(self._orbs):
            if not self._intro_orb_births:
                self._intro_reveal_timer += dt
                self._intro_boss_alpha = min(
                    1.0, self._intro_boss_alpha + dt / _INTRO_BOSS_FADE_IN
                )
                self._teleport_visual = self._intro_boss_alpha
                self._intro_dim_alpha = max(
                    0.0,
                    self._intro_dim_alpha - (_INTRO_DIM_MAX / _INTRO_DIM_FADE_OUT) * dt,
                )
                if self._intro_dim_alpha <= 0.0:
                    self._state = ArchmageState.IDLE
                    self.active = True
                    self._state_timer = 0.6
                    self._teleport_visual = 1.0

    def get_intro_dim_alpha(self) -> int:
        if self._state == ArchmageState.INTRO:
            return max(0, min(_INTRO_DIM_MAX, int(self._intro_dim_alpha)))
        return 0

    @property
    def is_intro_active(self) -> bool:
        return self._state == ArchmageState.INTRO

    def _update_miss_indicator(self, dt: float) -> None:
        self._miss_timer = max(0.0, self._miss_timer - dt * 60.0)
        self._miss_y += self._miss_dy

    def _trigger_miss_indicator(self, hit_x: float | None, hit_y: float | None) -> None:
        self._miss_timer = 60.0
        center_x = self.x + self.w / 2
        center_y = self.y + self.h / 2
        self._miss_x = hit_x if hit_x is not None else center_x
        self._miss_y = (hit_y if hit_y is not None else center_y) - 56.0

    @property
    def rect(self) -> pygame.Rect:
        """Empty during teleport fade-out; expands to cover shield when active."""
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
        return self._state == ArchmageState.PHASE2_DEFENSE and self._shield_active

    # ------------------------------------------------------------------
    # Orb positioning
    # ------------------------------------------------------------------

    def _update_orbs_positions(self, dt: float) -> None:
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        hp_ratio = self.health / self.max_health

        orbit_speed_mult = 1.0 + (1.0 - hp_ratio) * 1.5
        # Increased base angular velocity for more dynamic orbits
        self._orb_angle += dt * 2.4 * orbit_speed_mult

        for orb in self._orbs:
            if orb.mode == OrbMode.ABSORBED:
                orb.x += (cx - orb.x) * 10.0 * dt
                orb.y += (cy - orb.y) * 10.0 * dt
                continue

            angle = self._orb_angle + orb.base_angle
            if orb.mode == OrbMode.ORBIT:
                orb.x = cx + math.cos(angle) * self.ORBIT_RADIUS
                orb.y = cy + math.sin(angle) * (self.ORBIT_RADIUS * 0.5)
            elif orb.mode == OrbMode.ATTACK:
                tx = orb.target_x or cx
                ty = orb.target_y or cy
                orb.x += (tx - orb.x) * 10.0 * dt
                orb.y += (ty - orb.y) * 10.0 * dt
                if math.hypot(tx - orb.x, ty - orb.y) < 6.0:
                    self._emit_orb_burst(orb.x, orb.y, orb.color)
                    orb.mode = OrbMode.ABSORBED
            elif orb.mode == OrbMode.RETURN:
                tx = cx + math.cos(angle) * self.ORBIT_RADIUS
                ty = cy + math.sin(angle) * (self.ORBIT_RADIUS * 0.5)
                orb.x += (tx - orb.x) * 5.0 * dt
                orb.y += (ty - orb.y) * 5.0 * dt
                if math.hypot(tx - orb.x, ty - orb.y) < 5.0:
                    orb.mode = OrbMode.ORBIT

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
            self._begin_phase1_cycle()
        elif hp_ratio > self.PHASE3_THRESHOLD:
            self._begin_phase2_defense()
        else:
            self._begin_phase3_combos()

    def _start_orb_absorption(self, orb_index: int) -> None:
        orb = self._orbs[orb_index]
        self._active_orb_index = orb_index
        self._active_power = orb
        self._absorbed_orbs = [orb]
        self._power_timer = 0.0
        self._cooldown_timer = 0.0
        self._state = ArchmageState.ABSORBING_ORB
        self._state_timer = _ABSORPTION_DURATION
        orb.mode = OrbMode.ATTACK
        orb.target_x = self.x + self.w / 2
        orb.target_y = self.y + self.h / 2
        self._white_dodge_active = False

    def _begin_phase1_cycle(self) -> None:
        active_orbs = [
            index for index, orb in enumerate(self._orbs) if orb.mode == OrbMode.ORBIT
        ]
        if active_orbs:
            self._start_orb_absorption(random.choice(active_orbs))
        else:
            # Orbs still returning — retry after a short delay instead of freezing in IDLE
            self._state = ArchmageState.IDLE
            self._state_timer = 0.4

    def _begin_phase2_defense(self) -> None:
        self._phase3_combo_powers = None
        self._state = ArchmageState.PHASE2_DEFENSE
        self._state_timer = random.uniform(2.4, 3.6)
        self._shield_max_hp = self.SHIELD_MAX_HP + int(self.health * 0.5)
        self._shield_hp = self._shield_max_hp
        self._shield_active = False
        self._shield_spawning = True
        self._shield_spawn_t = 0.0
        self._shield_rings = [
            ShieldRing(r=8.0, alpha=200.0) for _ in range(_SHIELD_RING_COUNT)
        ]
        self._vulnerable_timer = 0.0
        self._stalagmite_spawn_timer = 0.0
        self._active_telegraphs.clear()
        self._white_dodge_active = False
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        for orb in self._orbs:
            if orb.mode == OrbMode.ORBIT:
                orb.mode = OrbMode.ATTACK
                orb.target_x = cx
                orb.target_y = cy

    def _begin_phase3_combos(self) -> None:
        self._phase3_combo_powers = None
        self._state = ArchmageState.PHASE3_COMBOS
        self._state_timer = 0.0
        self._overload_timer = 0.0
        if self._overload_cooldown <= 0.0:
            self._overload_cooldown = _OVERLOAD_COOLDOWN
        self._fire_zone_spawn_timer = 0.0
        self._stalagmite_spawn_timer = 0.0
        self._white_dodge_active = False

    def _choose_phase3_combo(self) -> tuple[OrbType, ...]:
        return random.choice(
            (
                (OrbType.PURPLE, OrbType.ORANGE),  # Roxo + Laranja
                (OrbType.ORANGE, OrbType.WHITE),  # Laranja + Branco
                (OrbType.CYAN, OrbType.ORANGE),  # Azul + Laranja
                (OrbType.CYAN, OrbType.PURPLE),  # Azul + Roxo
                (OrbType.CYAN, OrbType.WHITE),  # Azul + Branco
                (OrbType.PURPLE, OrbType.WHITE),  # Roxo + Branco
                # Triplos para intensidade máxima
                (OrbType.PURPLE, OrbType.ORANGE, OrbType.WHITE),
                (OrbType.CYAN, OrbType.ORANGE, OrbType.PURPLE),
                (OrbType.CYAN, OrbType.WHITE, OrbType.ORANGE),
            )
        )

    def _activate_combo_effects(self, powers: tuple[OrbType, ...]) -> None:
        self._restore_orbs()
        self._phase3_combo_powers = powers
        self._white_dodge_active = OrbType.WHITE in powers

        if OrbType.CYAN in powers:
            # Em combos da fase 3, o escudo é um pouco mais fraco que na defesa pura da fase 2
            self._shield_max_hp = self.SHIELD_MAX_HP + int(self.health * 0.4)
            self._shield_hp = self._shield_max_hp
            self._shield_active = False
            self._shield_spawning = True
            self._shield_spawn_t = 0.0
            self._shield_rings = [
                ShieldRing(r=8.0, alpha=200.0) for _ in range(_SHIELD_RING_COUNT)
            ]

        self._fire_zone_spawn_timer = 0.0
        self._stalagmite_spawn_timer = 0.0
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        for orb in self._orbs:
            if orb.type in powers and orb.mode == OrbMode.ORBIT:
                orb.mode = OrbMode.ATTACK
                orb.target_x = cx
                orb.target_y = cy

    def _finish_phase1_power(self) -> None:
        if self._active_orb_index is None:
            return

        orb = self._orbs[self._active_orb_index]
        if orb.type == OrbType.CYAN:
            self._shield_active = False
            self._shield_spawning = False
            self._shield_hp = 0
        # If orb was fully absorbed, snap it back to an orbital position
        # so the RETURN lerp has a sensible starting point
        if orb.mode == OrbMode.ABSORBED:
            angle = self._orb_angle + orb.base_angle
            cx = self.x + self.w / 2
            cy = self.y + self.h / 2
            orb.x = cx + math.cos(angle) * self.ORBIT_RADIUS
            orb.y = cy + math.sin(angle) * (self.ORBIT_RADIUS * 0.5)
        orb.mode = OrbMode.RETURN
        orb.timer = 0.0
        self._active_orb_index = None
        self._active_power = None
        self._white_dodge_active = False
        self._state = ArchmageState.COOLDOWN
        self._cooldown_timer = _ABSORPTION_COOLDOWN

    def _emit_shield_break(self) -> None:
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        r = self.SHIELD_RADIUS
        rot = self._shield_timer * 0.6
        for k in range(6):
            angle = rot + k * math.tau / 6
            px = cx + math.cos(angle) * r
            py = cy + math.sin(angle) * r
            for _ in range(_SHIELD_BREAK_PARTICLE_COUNT):
                a = random.uniform(0, math.tau)
                speed = random.uniform(120.0, 380.0)
                life = random.uniform(0.3, 0.75)
                self._shield_break_particles.append(
                    Particle(
                        x=px,
                        y=py,
                        vx=math.cos(a) * speed,
                        vy=math.sin(a) * speed,
                        life=life,
                        max_life=life,
                        color=_CYAN_SHIELD_COLOR,
                    )
                )

    def _emit_orb_burst(self, x: float, y: float, color: Color) -> None:
        """Spawns burst particles when an orb is absorbed into the boss."""
        for _ in range(_ORB_BURST_PARTICLE_COUNT):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(60.0, 220.0)
            life = random.uniform(0.25, 0.55)
            self._orb_bursts.append(
                Particle(
                    x=x,
                    y=y,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed,
                    life=life,
                    max_life=life,
                    color=color,
                )
            )

    def _update_absorbing_orb(self, dt: float) -> None:
        self._state_timer -= dt
        if self._state_timer <= 0.0:
            self._state = ArchmageState.USING_POWER
            self._power_timer = random.uniform(_POWER_DURATION_MIN, _POWER_DURATION_MAX)
            self._state_timer = self._power_timer
            if (
                self._active_power is not None
                and self._active_power.type == OrbType.CYAN
            ):
                self._shield_max_hp = self.SHIELD_MAX_HP + int(self.health * 0.5)
                self._shield_hp = self._shield_max_hp
                self._shield_active = False
                self._shield_spawning = True
                self._shield_spawn_t = 0.0
                self._shield_timer = 0.0

    def _update_using_power(
        self, dt: float, player_pos: tuple[float, float] | None
    ) -> list[Any]:
        spawned: list[Any] = []
        self._power_timer -= dt
        self._state_timer = self._power_timer

        if self._active_power is None:
            self._finish_phase1_power()
            return spawned

        power_type = self._active_power.type
        boss_cx = self.x + self.w / 2
        boss_cy = self.y + self.h / 2
        target_x, target_y = player_pos if player_pos else (boss_cx, boss_cy)

        if power_type == OrbType.WHITE:
            self._white_dodge_active = True
        elif power_type == OrbType.CYAN:
            self._white_dodge_active = False
            # Shield spawn/active state is managed entirely by the update loop
            # (lines that tick _shield_spawn_t and flip _shield_active). No action needed here.
        elif power_type == OrbType.PURPLE:
            self._stalagmite_spawn_timer += dt
            while self._stalagmite_spawn_timer >= _PHASE2_STALAGMITE_INTERVAL:
                self._stalagmite_spawn_timer -= _PHASE2_STALAGMITE_INTERVAL
                x_pos = float(
                    _clamp(
                        target_x + random.randint(-120, 120),
                        60.0,
                        Config.SCREEN_WIDTH - 60.0,
                    )
                )
                y_pos = float(_clamp(target_y, 80.0, Config.SCREEN_HEIGHT - 120.0))
                self._active_telegraphs.append(
                    Telegraph(
                        x=x_pos,
                        is_stalactite=random.random() < 0.5,
                        timer=Config.MOUNTAIN_MAGE_WARNING_DURATION,
                        charge=0.0,
                        target_y=y_pos,
                    )
                )
        elif power_type == OrbType.ORANGE:
            if not self._spawned_fire_zones and not self._firezone_warnings:
                for _ in range(3):
                    self._queue_random_firezone_warning(
                        radius=int(64 * _FIREZONE_RADIUS_SCALE),
                        duration=random.uniform(5.0, 8.0),
                    )

        self._spawned_fire_zones = [
            zone for zone in self._spawned_fire_zones if not zone.should_remove()
        ]

        if self._power_timer <= 0.0:
            self._finish_phase1_power()

        return spawned

    def _update_cooldown(self, dt: float) -> None:
        self._cooldown_timer = max(0.0, self._cooldown_timer - dt)
        if self._cooldown_timer > 0.0:
            return
        self._begin_teleport()

    def _update_phase2_defense(
        self, dt: float, player_pos: tuple[float, float] | None
    ) -> list[Any]:
        spawned: list[Any] = []
        self._stalagmite_spawn_timer += dt
        self._state_timer -= dt
        self._shield_timer += dt
        self._white_dodge_active = False

        if self.health / self.max_health <= self.PHASE3_THRESHOLD:
            self._active_telegraphs.clear()
            self._begin_phase3_combos()
            return spawned

        if self._state_timer <= 0.0:
            # O teletransporte agora só acontece em estados de repouso (Vulnerable),
            # não permitindo fuga enquanto o escudo estiver ativo.
            pass

        while self._stalagmite_spawn_timer >= _PHASE2_STALAGMITE_INTERVAL:
            self._stalagmite_spawn_timer -= _PHASE2_STALAGMITE_INTERVAL
            player_x, player_y = (
                player_pos
                if player_pos is not None
                else (self.x + self.w / 2, self.y + self.h / 2)
            )
            x_pos = float(_clamp(player_x, 60.0, Config.SCREEN_WIDTH - 60.0))
            target_y = float(_clamp(player_y, 80.0, Config.SCREEN_HEIGHT - 120.0))
            self._active_telegraphs.append(
                Telegraph(
                    x=x_pos,
                    is_stalactite=random.random() < 0.5,
                    timer=Config.MOUNTAIN_MAGE_WARNING_DURATION,
                    charge=0.0,
                    target_y=target_y,
                )
            )

        return spawned

    def _update_phase2_telegraphs(self, dt: float, spawned: list[Any]) -> None:
        if not self._active_telegraphs:
            return

        warning_duration = max(0.1, float(Config.MOUNTAIN_MAGE_WARNING_DURATION))
        remaining_telegraphs: list[Telegraph] = []

        for telegraph in self._active_telegraphs:
            telegraph.timer -= dt
            telegraph.charge = min(
                1.0, 1.0 - max(0.0, telegraph.timer) / warning_duration
            )

            if telegraph.timer > 0.0:
                remaining_telegraphs.append(telegraph)
                continue

            if telegraph.is_stalactite:
                spawned.append(
                    MountainStalactite(telegraph.x, -10.0, float(telegraph.target_y))
                )
            else:
                spawned.append(
                    MountainStalagmite(
                        telegraph.x,
                        float(Config.SCREEN_HEIGHT) + 10.0,
                        float(telegraph.target_y),
                    )
                )

        self._active_telegraphs = remaining_telegraphs

    def _queue_random_firezone_warning(self, radius: int, duration: float) -> None:
        active = sum(1 for z in self._spawned_fire_zones if not z.should_remove())
        if active + len(self._firezone_warnings) >= _MAX_FIRE_ZONES:
            return
        margin = max(90.0, float(radius) + 24.0)
        x = random.uniform(margin, Config.SCREEN_WIDTH - margin)
        y = random.uniform(margin, Config.SCREEN_HEIGHT - margin)
        self._firezone_warnings.append(
            FireZoneWarning(
                x=x,
                y=y,
                timer=_FIREZONE_WARNING_DURATION,
                charge=0.0,
                radius=radius,
                duration=duration,
            )
        )

    def _update_firezone_warnings(self, dt: float, spawned: list[Any]) -> None:
        if not self._firezone_warnings:
            return

        warning_duration = max(0.1, _FIREZONE_WARNING_DURATION)
        remaining: list[FireZoneWarning] = []

        for warning in self._firezone_warnings:
            warning.timer -= dt
            warning.charge = min(1.0, 1.0 - max(0.0, warning.timer) / warning_duration)

            if warning.timer > 0.0:
                remaining.append(warning)
                continue

            zone = FireZone(
                warning.x,
                warning.y,
                radius=warning.radius,
                duration=warning.duration,
            )
            self._spawned_fire_zones.append(zone)
            spawned.append(zone)

        self._firezone_warnings = remaining

    def _update_phase2_vulnerable(self, dt: float) -> None:
        self._vulnerable_timer = max(0.0, self._vulnerable_timer - dt)
        if self._vulnerable_timer > 0.0:
            return

        if self.health / self.max_health <= self.PHASE3_THRESHOLD:
            self._begin_phase3_combos()
        else:
            self._begin_teleport()

    def _begin_teleport(self) -> None:
        _ATTACKING_STATES = (
            ArchmageState.ABSORBING_ORB,
            ArchmageState.USING_POWER,
            ArchmageState.PHASE2_DEFENSE,
            ArchmageState.PHASE3_COMBOS,
            ArchmageState.PHASE3_OVERLOAD,
        )
        if self._state in _ATTACKING_STATES:
            return

        # Determinamos o estado de retorno baseado no estado ATUAL (antes do teleport)
        if self._state in (
            ArchmageState.PHASE2_DEFENSE,
            ArchmageState.PHASE2_VULNERABLE,
        ):
            self._resume_state = ArchmageState.PHASE2_DEFENSE
        elif self._state in (
            ArchmageState.PHASE3_COMBOS,
            ArchmageState.PHASE3_OVERLOAD,
            ArchmageState.PHASE3_VULNERABLE,
        ):
            self._resume_state = ArchmageState.PHASE3_COMBOS
        else:
            self._resume_state = ArchmageState.IDLE

        if self._resume_state == ArchmageState.IDLE:
            # Phase 1 / cooldown teleport: fully reset active power and shield
            self._shield_active = False
            self._shield_spawning = False
            self._shield_hp = 0
            self._active_orb_index = None
            self._active_power = None
            self._white_dodge_active = False
            self._active_telegraphs.clear()
            self._firezone_warnings.clear()
        # No Phase 2/3 teleport, we preserve shield and attack states entirely

        self._restore_orbs()

        for orb in self._orbs:
            if orb.mode in (OrbMode.ATTACK, OrbMode.RETURN):
                orb.mode = OrbMode.RETURN
                orb.timer = 0.0

        hp_ratio = self.health / self.max_health
        white_orbiting = hp_ratio > self.PHASE2_THRESHOLD and any(
            o.type == OrbType.WHITE and o.mode == OrbMode.ORBIT for o in self._orbs
        )
        slide_chance = 0.65 if white_orbiting else 0.4

        if random.random() < slide_chance:
            self._slide_start_x = self.x
            self._slide_start_y = self.y
            self._slide_target_x = float(random.randint(100, Config.SCREEN_WIDTH - 100))
            self._slide_target_y = float(random.randint(50, 200))
            self._slide_timer = 0.0
            self._state = ArchmageState.SLIDE
        else:
            self._state = ArchmageState.TELEPORT
            self._state_timer = 1.2
            self._teleport_repositioned = False
            self._teleport_wait_timer = 0.0

    def _update_phase3_combos(
        self, dt: float, player_pos: tuple[float, float] | None
    ) -> list[Any]:
        spawned: list[Any] = []

        if self._phase3_combo_powers is None:
            self._activate_combo_effects(self._choose_phase3_combo())
            self._state_timer = random.uniform(_POWER_DURATION_MIN, _POWER_DURATION_MAX)

        self._state_timer -= dt
        self._overload_cooldown = max(0.0, self._overload_cooldown - dt)
        self._white_dodge_active = (
            self._phase3_combo_powers is not None
            and OrbType.WHITE in self._phase3_combo_powers
        )

        target_x, target_y = (
            player_pos if player_pos else (self.x + self.w / 2, self.y + self.h / 2)
        )

        if self._phase3_combo_powers and OrbType.ORANGE in self._phase3_combo_powers:
            self._fire_zone_spawn_timer += dt
            while self._fire_zone_spawn_timer >= _PHASE3_FIREZONE_INTERVAL:
                self._fire_zone_spawn_timer -= _PHASE3_FIREZONE_INTERVAL
                for _ in range(3):
                    self._queue_random_firezone_warning(
                        radius=int(60 * _FIREZONE_RADIUS_SCALE),
                        duration=random.uniform(5.0, 8.0),
                    )

        if self._phase3_combo_powers and OrbType.PURPLE in self._phase3_combo_powers:
            self._stalagmite_spawn_timer += dt
            while self._stalagmite_spawn_timer >= _PHASE3_STALAGMITE_INTERVAL:
                self._stalagmite_spawn_timer -= _PHASE3_STALAGMITE_INTERVAL
                if random.random() < 0.5:
                    spawned.append(
                        MountainStalactite(float(target_x), -10.0, float(target_y))
                    )
                else:
                    spawned.append(
                        MountainStalagmite(
                            float(target_x),
                            float(Config.SCREEN_HEIGHT) + 10.0,
                            float(target_y),
                        )
                    )

        self._spawned_fire_zones = [
            zone for zone in self._spawned_fire_zones if not zone.should_remove()
        ]

        if self._state_timer <= 0.0:
            self._phase3_combo_powers = None
            self._white_dodge_active = False
            if self._overload_cooldown <= 0.0:
                self._begin_phase3_overload()
            else:
                self._state = ArchmageState.COOLDOWN
                self._cooldown_timer = _PHASE3_COMBO_COOLDOWN

        return spawned

    def _begin_phase3_overload(self) -> None:
        self._restore_orbs()
        self._phase3_combo_powers = None
        self._state = ArchmageState.PHASE3_OVERLOAD
        self._state_timer = _OVERLOAD_DURATION
        self._overload_timer = 0.0
        self._white_dodge_active = True
        self._fire_zone_spawn_timer = 0.0
        self._stalagmite_spawn_timer = 0.0
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        for orb in self._orbs:
            if orb.mode == OrbMode.ORBIT:
                orb.mode = OrbMode.ATTACK
                orb.target_x = cx
                orb.target_y = cy

    def _update_phase3_overload(
        self, dt: float, player_pos: tuple[float, float] | None
    ) -> list[Any]:
        spawned: list[Any] = []
        self._state_timer -= dt
        self._overload_timer += dt
        self._overload_cooldown = max(0.0, self._overload_cooldown - dt)
        self._white_dodge_active = True

        target_x, target_y = (
            player_pos if player_pos else (self.x + self.w / 2, self.y + self.h / 2)
        )

        self._fire_zone_spawn_timer += dt
        self._stalagmite_spawn_timer += dt

        while self._fire_zone_spawn_timer >= 1.0:
            self._fire_zone_spawn_timer -= 1.0
            for _ in range(3):
                self._queue_random_firezone_warning(
                    radius=int(68 * _FIREZONE_RADIUS_SCALE),
                    duration=random.uniform(5.0, 8.0),
                )

        while self._stalagmite_spawn_timer >= 0.9:
            self._stalagmite_spawn_timer -= 0.9
            if random.random() < 0.5:
                spawned.append(
                    MountainStalactite(float(target_x), -10.0, float(target_y))
                )
            else:
                spawned.append(
                    MountainStalagmite(
                        float(target_x),
                        float(Config.SCREEN_HEIGHT) + 10.0,
                        float(target_y),
                    )
                )

        self._spawned_fire_zones = [
            zone for zone in self._spawned_fire_zones if not zone.should_remove()
        ]

        if self._state_timer <= 0.0:
            self._begin_phase3_vulnerable()

        return spawned

    def _begin_phase3_vulnerable(self) -> None:
        self._restore_orbs()
        self._state = ArchmageState.PHASE3_VULNERABLE
        self._state_timer = _VULNERABLE_DURATION
        self._white_dodge_active = False
        self._phase3_combo_powers = None

    def _update_phase3_vulnerable(self, dt: float) -> None:
        self._state_timer -= dt
        if self._state_timer > 0.0:
            return

        self._overload_cooldown = _OVERLOAD_COOLDOWN
        self._begin_teleport()

    def _trigger_forced_slide(self) -> None:
        if self._state in (
            ArchmageState.INTRO,
            ArchmageState.APPEARING,
            ArchmageState.DEFEATED,
            ArchmageState.SLIDE,
            ArchmageState.ABSORBING_ORB,
            ArchmageState.USING_POWER,
            ArchmageState.PHASE2_DEFENSE,
            ArchmageState.PHASE3_COMBOS,
            ArchmageState.PHASE3_OVERLOAD,
        ):
            return
        self._restore_orbs()
        self._active_orb_index = None
        self._active_power = None
        self._white_dodge_active = False
        self._active_telegraphs.clear()
        self._firezone_warnings.clear()
        self._slide_start_x = self.x
        self._slide_start_y = self.y
        tx, ty = self.x, self.y
        for _ in range(20):
            tx = random.uniform(80.0, Config.SCREEN_WIDTH - 80.0 - self.w)
            ty = random.uniform(40.0, Config.SCREEN_HEIGHT * 0.55 - self.h)
            if math.hypot(tx - self.x, ty - self.y) >= 320.0:
                break
        self._slide_target_x = tx
        self._slide_target_y = ty
        self._slide_timer = 0.0
        self._slide_duration = 0.65
        self._slide_is_forced = True
        self._state = ArchmageState.SLIDE

    def _update_slide(self, dt: float) -> None:
        """Glides boss smoothly to a new position without fading out."""
        self._slide_timer += dt
        t = min(1.0, self._slide_timer / self._slide_duration)
        eased = 1.0 - (1.0 - t) ** 3  # Ease-out cubic: arranca rápido, freia no fim

        self.x = (
            self._slide_start_x + (self._slide_target_x - self._slide_start_x) * eased
        )
        self.y = (
            self._slide_start_y + (self._slide_target_y - self._slide_start_y) * eased
        )
        self._teleport_repositioned = True

        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        for _ in range(3):
            angle = random.uniform(0.0, math.tau)
            spd = random.uniform(20.0, 55.0)
            life = random.uniform(0.15, 0.30)
            self._trail_particles.append(
                Particle(
                    x=cx + random.uniform(-12.0, 12.0),
                    y=cy + random.uniform(-12.0, 12.0),
                    vx=math.cos(angle) * spd,
                    vy=math.sin(angle) * spd,
                    life=life,
                    max_life=life,
                    color=(140, 190, 255),
                    radius=5,
                )
            )

        if t >= 1.0:
            self.x = self._slide_target_x
            self.y = self._slide_target_y
            if self._slide_is_forced:
                self._slide_duration = 0.42
                self._slide_is_forced = False
            if self._resume_state == ArchmageState.PHASE2_DEFENSE:
                self._begin_phase2_defense()
            elif self._resume_state == ArchmageState.PHASE3_COMBOS:
                self._begin_phase3_combos()
            else:
                self._state = ArchmageState.IDLE
                self._state_timer = 0.6 + random.uniform(0.0, 0.3)
            self._resume_state = ArchmageState.IDLE

    def _update_teleport(self, dt: float) -> None:
        self._state_timer -= dt

        if self._state_timer > self._TELEPORT_HALF:
            # Phase A: fade out
            self._teleport_visual = max(
                0.0, self._teleport_visual - _TELEPORT_FADE_SPEED * dt
            )
        else:
            # Phase B: wait for orbs, then reposition and fade in
            if not self._teleport_repositioned:
                orbs_returning = any(orb.mode != OrbMode.ORBIT for orb in self._orbs)
                if orbs_returning:
                    self._teleport_visual = 0.0
                    self._state_timer += dt  # pause countdown
                    self._teleport_wait_timer += dt
                    if self._teleport_wait_timer <= _TELEPORT_MAX_WAIT:
                        return

                self.x = float(random.randint(100, Config.SCREEN_WIDTH - 100))
                self.y = float(random.randint(50, 200))
                self._sync_lerp_to_position()
                self._teleport_repositioned = True

            self._teleport_visual = min(
                1.0, self._teleport_visual + _TELEPORT_FADE_SPEED * dt
            )

        if self._state_timer <= 0.0 and self._teleport_repositioned:
            if self._resume_state == ArchmageState.PHASE2_DEFENSE:
                self._begin_phase2_defense()
            elif self._resume_state == ArchmageState.PHASE3_COMBOS:
                self._begin_phase3_combos()
            else:
                self._state = ArchmageState.IDLE
                self._state_timer = 0.8 + random.uniform(0.0, 0.4)
            self._resume_state = ArchmageState.IDLE

    # ------------------------------------------------------------------
    # Gradient tint helpers
    # ------------------------------------------------------------------

    _GRADIENT_CYCLE: Final = 2.0
    _GRADIENT_ALPHA: Final = 110  # 0-255; tune for intensity
    _TINT_LERP_SPEED: Final = 10.0

    def _update_displayed_tint(self, dt: float) -> None:
        target = self._get_gradient_color()
        if target is None:
            self._displayed_tint = None
            return
        if self._displayed_tint is None:
            self._displayed_tint = (float(target[0]), float(target[1]), float(target[2]))
            return
        k = min(1.0, self._TINT_LERP_SPEED * dt)
        r, g, b = self._displayed_tint
        self._displayed_tint = (
            r + (float(target[0]) - r) * k,
            g + (float(target[1]) - g) * k,
            b + (float(target[2]) - b) * k,
        )

    def _get_gradient_color(self) -> Color | None:
        colors: list[Color] = []

        if self._state in (ArchmageState.ABSORBING_ORB, ArchmageState.USING_POWER):
            if self._active_power is not None:
                colors = [self._active_power.color]
        elif self._state in (
            ArchmageState.PHASE2_DEFENSE,
            ArchmageState.PHASE2_VULNERABLE,
        ):
            colors = [_CYAN_SHIELD_COLOR]
        elif self._state in (
            ArchmageState.PHASE3_COMBOS,
            ArchmageState.PHASE3_VULNERABLE,
        ):
            if self._phase3_combo_powers:
                colors = [
                    orb.color
                    for orb in self._orbs
                    if orb.type in self._phase3_combo_powers
                ]
        elif self._state == ArchmageState.PHASE3_OVERLOAD:
            colors = [orb.color for orb in self._orbs]

        if not colors:
            return None
        if len(colors) == 1:
            return colors[0]

        steps = 64
        t_raw = (self._gradient_timer % self._GRADIENT_CYCLE) / self._GRADIENT_CYCLE
        t = int(t_raw * steps) / steps
        n = len(colors)
        segment = t * n
        idx = int(segment) % n
        local_t = segment - int(segment)
        c0 = colors[idx]
        c1 = colors[(idx + 1) % n]
        return (
            int(c0[0] + (c1[0] - c0[0]) * local_t),
            int(c0[1] + (c1[1] - c0[1]) * local_t),
            int(c0[2] + (c1[2] - c0[2]) * local_t),
        )

    def _blit_tinted(
        self,
        dest: pygame.Surface,
        surf: pygame.Surface,
        pos: tuple[int, int],
        tint: Color,
    ) -> None:
        """Blits surf onto dest at pos com tint aplicado apenas a pixels opacos.

        O overlay é mascarado pelo alpha do sprite (MULT) antes do ADD —
        pixels transparentes ficam alpha=0 e não recebem cor da orb.
        O cache usa tint quantizado (steps de 8) para limitar crescimento.
        """
        w, h = surf.get_width(), surf.get_height()
        qr, qg, qb = tint[0] >> 3 << 3, tint[1] >> 3 << 3, tint[2] >> 3 << 3
        key = (qr, qg, qb, w, h)
        masked = self._tint_cache.get(key)
        if masked is None:
            masked = pygame.Surface((w, h), pygame.SRCALPHA)
            masked.fill((qr, qg, qb, self._GRADIENT_ALPHA))
            masked.blit(surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            if pygame.display.get_init():
                masked = masked.convert_alpha()
            self._tint_cache[key] = masked

        temp = surf.copy()
        temp.blit(masked, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        dest.blit(temp, pos)

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    _INTRO_ORB_FADE_DUR: Final = 0.45

    def _draw_intro(self, surface: pygame.Surface) -> None:
        """Desenha apenas partículas de nascimento e orbs durante a sequência de intro."""
        self._draw_particle_list(
            surface, self._intro_orb_births, base_alpha=220, size_base=3, size_range=4
        )
        self._draw_intro_orbs(surface)

    def _draw_intro_orbs(self, surface: pygame.Surface) -> None:
        sz = self.ORB_SIZE
        for orb in self._orbs:
            if orb.mode != OrbMode.ORBIT:
                continue
            alpha = int(255 * min(1.0, orb.timer / self._INTRO_ORB_FADE_DUR))
            if alpha <= 0:
                continue
            ox, oy = int(orb.x), int(orb.y)
            glow_diam = sz * 2 + 16
            glow = pygame.Surface((glow_diam, glow_diam), pygame.SRCALPHA)
            pygame.draw.circle(
                glow, (*orb.color, int(40 * alpha / 255)), (sz + 8, sz + 8), sz + 8
            )
            surface.blit(glow, (ox - sz - 8, oy - sz - 8))
            orb_surf = pygame.Surface((sz * 2, sz * 2), pygame.SRCALPHA)
            pygame.draw.circle(orb_surf, (*orb.color, alpha), (sz, sz), sz)
            surface.blit(orb_surf, (ox - sz, oy - sz))

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead and self._state != ArchmageState.DEFEATED:
            return

        if self._state == ArchmageState.INTRO:
            self._draw_intro(surface)
            return

        if self._teleport_visual <= 0.02:
            return

        state_key = (
            "flash"
            if self._hit_flash > 0.0
            else (
                "phase3"
                if self._state
                in (
                    ArchmageState.PHASE3_COMBOS,
                    ArchmageState.PHASE3_OVERLOAD,
                    ArchmageState.PHASE3_VULNERABLE,
                )
                or (
                    self._active_power is not None
                    and self._active_power.type in (OrbType.ORANGE, OrbType.PURPLE)
                )
                else "normal"
            )
        )

        self._draw_trail_particles(surface)
        self._draw_orbs(surface)
        self._draw_orb_bursts(surface)
        self._draw_shield_break_particles(surface)
        if self._shield_active or self._shield_spawning:
            self._draw_shield(surface)

        gradient_tint = (
            (int(self._displayed_tint[0]), int(self._displayed_tint[1]), int(self._displayed_tint[2]))
            if self._displayed_tint is not None
            else None
        )

        if self._state != ArchmageState.DEFEATED:
            self._draw_flowing_mantle(surface, state_key, gradient_tint)

        fading = self._teleport_visual < 1.0

        parts: list[tuple[str, float, float]] = [
            ("arm", self._l_arm_x, self._l_arm_y),
            ("arm", self._r_arm_x, self._r_arm_y),
            ("body", self._body_x, self._body_y),
        ]
        for part, px, py in parts:
            self._draw_fading_part(
                surface, part, state_key, px, py, fading, gradient_tint
            )

        if self._hit_flash <= 0.0 and self._teleport_visual > 0.5:
            eye_color = (255, 230, 0)
            pygame.draw.rect(
                surface,
                eye_color,
                (int(self._eye_l_x), int(self._eye_l_y), _EYE_SIZE, _EYE_SIZE),
            )
            pygame.draw.rect(
                surface,
                eye_color,
                (int(self._eye_r_x), int(self._eye_r_y), _EYE_SIZE, _EYE_SIZE),
            )

        self._draw_fading_part(
            surface, "hat", state_key, self._hat_x, self._hat_y, fading, gradient_tint
        )
        self._draw_health_bar(surface)
        self._draw_miss_indicator(surface)

        for t in self._active_telegraphs:
            self._draw_telegraph_marker(surface, t)
        for warning in self._firezone_warnings:
            self._draw_firezone_warning(surface, warning)

    def _draw_fading_part(
        self,
        surface: pygame.Surface,
        part: str,
        state_key: str,
        px: float,
        py: float,
        fading: bool,
        gradient_tint: Color | None = None,
    ) -> None:
        """Draw a sprite part, applying teleport scale-shrink if fading."""
        if fading:
            s = self._get_scaled_sprite(part, state_key, self._teleport_visual)
            base = self._sprites[part][state_key]
            offset_x = (base.get_width() - s.get_width()) // 2
            offset_y = (base.get_height() - s.get_height()) // 2
            pos = (int(px) + offset_x, int(py) + offset_y)
            if gradient_tint:
                self._blit_tinted(surface, s, pos, gradient_tint)
            else:
                surface.blit(s, pos)
        else:
            base = self._sprites[part][state_key]
            pos = (int(px), int(py))
            if gradient_tint:
                self._blit_tinted(surface, base, pos, gradient_tint)
            else:
                surface.blit(base, pos)

    def _draw_particle_list(
        self,
        surface: pygame.Surface,
        particles: list[Particle],
        base_alpha: int = 220,
        size_base: int = 3,
        size_range: int = 4,
    ) -> None:
        """Generic particle renderer. Draws each particle as a fading circle."""
        for p in particles:
            ratio = max(0.0, p.life / p.max_life)
            alpha = int(base_alpha * ratio)
            radius = max(1, int(size_base + size_range * ratio))
            s = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*p.color, alpha), (radius + 1, radius + 1), radius)
            surface.blit(s, (int(p.x) - radius - 1, int(p.y) - radius - 1))

    def _draw_shield(self, surface: pygame.Surface) -> None:
        """Hexagonal shield with spawn animation (scale-in + burst rings) and HP opacity."""
        cx = int(self.x + self.w / 2)
        cy = int(self._body_y + (len(BODY_MAP) * self._SCALE) / 2)
        hp_pct = max(0.0, self._shield_hp / self._shield_max_hp)

        if self._shield_spawning:
            t = self._shield_spawn_t
            eased = 1.0 - (1.0 - t) ** 3  # Ease-out cubic
            r = self.SHIELD_RADIUS * eased
            opacity_scale = eased
        else:
            r = self.SHIELD_RADIUS
            opacity_scale = 1.0

        pulse = 0.7 + 0.3 * math.sin(self._shield_timer * 5.0)
        rim_alpha = max(0, min(255, int((140 + 80 * hp_pct * pulse) * opacity_scale)))

        for ring in self._shield_rings:
            ring_alpha = max(0, min(255, int(ring.alpha)))
            if ring_alpha <= 0:
                continue
            ring_r = int(ring.r)
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

        rot_offset = self._shield_timer * 0.6
        hex_pts = [
            (
                cx + int(r * math.cos(rot_offset + k * math.tau / 6)),
                cy + int(r * math.sin(rot_offset + k * math.tau / 6)),
            )
            for k in range(6)
        ]
        pygame.draw.polygon(surface, (0, 200, 255, rim_alpha), hex_pts, 3)

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
        self._draw_particle_list(
            surface, self._orb_bursts, base_alpha=220, size_base=3, size_range=4
        )

    def _draw_shield_break_particles(self, surface: pygame.Surface) -> None:
        self._draw_particle_list(
            surface,
            self._shield_break_particles,
            base_alpha=240,
            size_base=2,
            size_range=5,
        )

    def _draw_trail_particles(self, surface: pygame.Surface) -> None:
        """Draws heat-trail particles left by the Orange orb (and any future trail sources)."""
        for p in self._trail_particles:
            ratio = max(0.0, p.life / p.max_life)
            alpha = int(200 * ratio)
            base_r = p.radius
            radius = max(1, int(base_r * (0.4 + 0.6 * ratio)))
            s = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
            r_c, g_c, b_c = p.color
            core_color = (
                min(255, r_c),
                min(255, int(g_c * ratio + 40 * (1 - ratio))),
                b_c,
                alpha,
            )
            pygame.draw.circle(s, core_color, (radius + 1, radius + 1), radius)
            surface.blit(s, (int(p.x) - radius - 1, int(p.y) - radius - 1))

    def _draw_miss_indicator(self, surface: pygame.Surface) -> None:
        if self._miss_timer <= 0.0:
            return

        alpha = int(255 * (self._miss_timer / 60.0))
        font = get_font(28)
        miss_surface = font.render("MISS", True, (255, 70, 70))
        miss_surface.set_alpha(alpha)

        x = int(self._miss_x)
        y = int(self._miss_y)
        miss_rect = miss_surface.get_rect(center=(x, y))
        surface.blit(miss_surface, miss_rect)

    def _draw_health_bar(self, surface: pygame.Surface) -> None:
        if self.health <= 0 or self._state in (
            ArchmageState.APPEARING,
            ArchmageState.INTRO,
        ):
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

    def _draw_telegraph_marker(self, surface: pygame.Surface, t: Telegraph) -> None:
        mr = int(14 + t.charge * 18)
        diam = mr * 4
        ms = pygame.Surface((diam, diam), pygame.SRCALPHA)
        mc = diam // 2
        alpha = int(100 + t.charge * 120)
        color = (
            (255, 235, 140, alpha) if not t.is_stalactite else (160, 220, 255, alpha)
        )
        pygame.draw.circle(ms, color, (mc, mc), mr, width=2)
        pygame.draw.line(ms, color, (mc, 0), (mc, diam), width=1)
        pygame.draw.line(ms, color, (0, mc), (diam, mc), width=1)
        draw_y = Config.SCREEN_HEIGHT - mr * 2 if not t.is_stalactite else mr * 2
        surface.blit(ms, (int(t.x) - mc, draw_y - mc))

    def _draw_firezone_warning(
        self, surface: pygame.Surface, warning: FireZoneWarning
    ) -> None:
        radius = max(20, int(warning.radius))
        pulse = 0.78 + 0.22 * math.sin(
            self._pulse_timer * 16.0 + warning.charge * math.pi
        )
        alpha_outer = int((70 + warning.charge * 120) * pulse)
        alpha_inner = int(45 + warning.charge * 110)

        diam = radius * 2 + 16
        marker = pygame.Surface((diam, diam), pygame.SRCALPHA)
        center = diam // 2
        ring_color = (255, 120, 40, max(0, min(255, alpha_outer)))
        fill_color = (255, 80, 20, max(0, min(255, alpha_inner)))

        pygame.draw.circle(marker, fill_color, (center, center), radius)
        pygame.draw.circle(marker, ring_color, (center, center), radius, width=4)
        surface.blit(marker, (int(warning.x) - center, int(warning.y) - center))

    def _draw_flowing_mantle(
        self,
        surface: pygame.Surface,
        state_key: str,
        gradient_tint: Color | None = None,
    ) -> None:
        if gradient_tint:
            r, g, b = gradient_tint
            # Blend gradient tint with a dark base so mantle stays readable
            color: Color = (r // 2, g // 2, b // 2)
        elif state_key == "flash":
            color = (255, 255, 255)
        elif state_key == "normal":
            color = (80, 60, 150)
        else:
            color = (100, 20, 50)

        base_y = self._body_y + len(BODY_MAP) * self._SCALE - 5
        for i in range(_FLAP_COUNT):
            offset_x = i * _FLAP_OFFSET_X_STEP + _FLAP_OFFSET_X_BASE
            wave = (
                math.sin(self._mantle_timer * 4.0 * _FLAP_FREQ[i] + _FLAP_PHASE[i])
                * _FLAP_AMP[i]
            )
            pts = [
                (self._body_x + offset_x, base_y),
                (self._body_x + offset_x + 10, base_y),
                (self._body_x + offset_x + 5 + wave, base_y + _FLAP_BASE_HEIGHT),
            ]
            pygame.draw.polygon(surface, color, pts)

    def _draw_orbs(self, surface: pygame.Surface) -> None:
        sz = self.ORB_SIZE
        for i, orb in enumerate(self._orbs):
            if orb.mode == OrbMode.ABSORBED:
                continue
            ox, oy = int(orb.x), int(orb.y)
            glow_diam = sz * 2 + 16
            glow = pygame.Surface((glow_diam, glow_diam), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*orb.color, 40), (sz + 8, sz + 8), sz + 8)
            surface.blit(glow, (ox - sz - 8, oy - sz - 8))
            pygame.draw.circle(surface, orb.color, (ox, oy), sz)

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
        self._shield_spawning = False
        self._shield_spawn_t = 0.0
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        for orb in self._orbs:
            if orb.mode == OrbMode.ABSORBED:
                angle = self._orb_angle + orb.base_angle
                orb.x = cx + math.cos(angle) * self.ORBIT_RADIUS
                orb.y = cy + math.sin(angle) * (self.ORBIT_RADIUS * 0.5)
                orb.mode = OrbMode.ORBIT
            elif orb.mode == OrbMode.ATTACK:
                orb.mode = OrbMode.RETURN
                orb.timer = 0.0

    def take_damage(
        self, amount: int = 1, hit_x: float | None = None, hit_y: float | None = None
    ) -> None:
        if self.dead or not self.active:
            return

        # White Power: 50% chance to dodge
        if self._white_dodge_active and random.random() < 0.5:
            # Mostra um flash rápido branco para indicar esquiva
            self._white_dodge_was_miss = True
            self._trigger_miss_indicator(hit_x, hit_y)
            return

        self._white_dodge_was_miss = False

        # Phase 1 Protection: Cyan orb intercepts hits if nearby
        if self.health / self.max_health > self.PHASE2_THRESHOLD:
            if hit_x is not None and hit_y is not None:
                for orb in self._orbs:
                    if orb.type == OrbType.CYAN and orb.mode != OrbMode.ABSORBED:
                        dist = math.hypot(orb.x - hit_x, orb.y - hit_y)
                        if dist < self.ORB_SIZE + 20:
                            self._hit_flash = 0.08
                            return

        # Shield absorbs damage while active or spawning
        if (self._shield_active or self._shield_spawning) and self._shield_hp > 0:
            self._shield_hp -= amount
            self._hit_flash = 0.08
            if self._shield_hp <= 0:
                self._shield_hp = 0
                self._shield_active = False
                self._shield_spawning = False
                self._emit_shield_break()
                # Snap the cyan orb back to orbit before restoring all orbs
                if self._active_orb_index is not None:
                    cyan_orb = self._orbs[self._active_orb_index]
                    angle = self._orb_angle + cyan_orb.base_angle
                    cx = self.x + self.w / 2
                    cy = self.y + self.h / 2
                    cyan_orb.x = cx + math.cos(angle) * self.ORBIT_RADIUS
                    cyan_orb.y = cy + math.sin(angle) * (self.ORBIT_RADIUS * 0.5)
                    cyan_orb.mode = OrbMode.RETURN
                self._active_orb_index = None
                self._active_power = None
                self._white_dodge_active = False
                self._restore_orbs()
                # In phase 1, go back to cooldown → idle rather than jumping to phase 2
                if self.health / self.max_health > self.PHASE2_THRESHOLD:
                    self._state = ArchmageState.COOLDOWN
                    self._cooldown_timer = _ABSORPTION_COOLDOWN
                elif self.health / self.max_health > self.PHASE3_THRESHOLD:
                    self._vulnerable_timer = _VULNERABLE_DURATION
                    self._state = ArchmageState.PHASE2_VULNERABLE
                else:
                    self._begin_phase3_vulnerable()
            return

        self.health -= amount
        self._hit_flash = 0.15
        if self.health <= 0:
            self.dead = True
            self._state = ArchmageState.DEFEATED
            return
        self._hit_count += 1
        if self._hit_count % 30 == 0:
            self._trigger_forced_slide()

    # ------------------------------------------------------------------
    # Passive orb-effect API (consumed by systems)
    # ------------------------------------------------------------------

    def get_orange_trail_hazards(self) -> list[tuple[float, float, float]]:
        """Retorna lista de círculos (x, y, radius) das zonas de fogo ativas."""
        return [
            (zone.x, zone.y, float(zone.radius))
            for zone in self._spawned_fire_zones
            if not zone.should_remove()
        ]

    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult, NO_HIT

        if self._white_dodge_was_miss:
            self._white_dodge_was_miss = False
            return NO_HIT

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
