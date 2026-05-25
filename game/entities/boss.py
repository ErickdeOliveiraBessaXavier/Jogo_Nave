import logging
import math
import random
from typing import Any, List, Literal, Tuple

import pygame

from ..core import colors
from ..core.config import config as Config
from ..core.time import Timer
from .boss_cannon import BossCannon
from .boss_hit_mixin import BossHitMixin
from .boss_laser import BossLaser
from .boss_particles import BossParticleSystem
from .boss_pixel_map import (
    COLORS_FRENZY,
    COLORS_NORMAL,
    PIXEL_COLS,
    PIXEL_MAP,
)
from .boss_square import BossSquare
from .boss_state import BossState
from .draw_utils import rotated_square_corners

# Sound events emitted by Boss.update() — executed by EntityManager
BossSoundEvent = Literal[
    "play_charging",
    "stop_charging",
    "play_fire",
    "stop_fire",
]


class Boss(BossHitMixin):
    """
    Boss entity with face-oriented combat system and layered pixel art design.
    """

    BOSS_TYPE_NAME: str = "normal"

    # Attack constants
    FRENZY_LASER_ANGLES: List[float] = [-0.349, 0, 0.349]
    LASER_DISTANCE: int = 2000
    MAX_CHARGE_RADIUS: float = 15.0

    def __init__(
        self, x: float, y: float, health: int = Config.BOSS_HEALTH, hit_score: int = 50
    ):
        # Position and size - Adjusted for pixel map proportions
        self.w = 180  # 18 cols * 10 px
        self.h = 140  # 14 rows * 10 px
        self.pixel_size = self.w / PIXEL_COLS

        self.x = x
        self.y = -self.h
        self.target_y = y

        # Health and state
        self.health = health
        self.max_health = health
        self.hit_score = hit_score
        self.dead = False

        # Movement
        self.speed = Config.BOSS_NORMAL_SPEED
        self.direction = 1
        self.entry_speed = Config.BOSS_ENTRY_SPEED
        self.player_x: float = 0.0
        self.player_y: float | None = None

        # State machine
        self.state = BossState.ENTERING
        self.frenzy_mode = False
        self.frenzy_shake_timer = 0.0
        self._shake_offset_x: int = 0
        self._shake_offset_y: int = 0
        self.pending_frenzy = False
        self.square_attack_timer = Timer(random.uniform(2.0, 3.5))

        # Attack system
        self._init_attack_system()
        self.charge_progress = 0.0

        # Visual effects - Lerp and Layers
        self.current_palette = COLORS_NORMAL.copy()
        self.palette_lerp_speed = 5.0
        self.breathing_timer = 0.0

        self.particle_system = BossParticleSystem()
        self.fired_lasers: List[BossLaser] = []

        # Orientation system
        self.rotation_angle = 0.0
        self.facing_direction = pygame.Vector2(0, 1)
        self.face_center = pygame.Vector2(0, 0)
        self.cannon = BossCannon()
        # support multiple cannons: central + lateral (created on frenzy)
        self.cannons: List[BossCannon] = [self.cannon]

        # Laser delay
        self.laser_delay_timer = 0.0
        self.laser_delay_duration = Config.BOSS_LASER_DELAY
        self.pending_laser_data: dict[str, Any] | None = None

        # Floating squares
        self.floating_squares: List[BossSquare] = []
        self._init_floating_squares()
        self.squares_animation_timer = 0.0

        # Launch queue
        self.square_launch_queue: List[BossSquare] = []
        self.square_launch_timer = 0.0
        self.square_launch_delay = 0.15

        # Caching
        self._cached_layers: dict[str, pygame.Surface] = {}

    def _init_floating_squares(self) -> None:
        num_squares = 14
        boss_center_x = self.x + self.w / 2
        boss_center_y = self.y + self.h / 2

        for _ in range(num_squares):
            orbit_radius = random.uniform(80, 140)
            orbit_angle = random.uniform(0, 360)
            orbit_speed = random.choice(
                [
                    random.uniform(30, 60),
                    random.uniform(15, 30),
                    random.uniform(-60, -30),
                    random.uniform(-30, -15),
                ]
            )
            size = random.uniform(16, 28)

            angle_rad = math.radians(orbit_angle)
            initial_x = boss_center_x + math.cos(angle_rad) * orbit_radius
            initial_y = boss_center_y + math.sin(angle_rad) * orbit_radius

            square = BossSquare(
                x=initial_x,
                y=initial_y,
                vx=0,
                vy=0,
                size=size,
                is_orbital=True,
                orbit_radius=orbit_radius,
                orbit_angle=orbit_angle,
                orbit_speed=orbit_speed,
                speed_var=random.uniform(0.85, 1.18),
            )
            self.floating_squares.append(square)

    def _update_lerps(self, dt: float) -> None:
        """Update smooth color transitions."""
        target = COLORS_FRENZY if self.frenzy_mode else COLORS_NORMAL
        for key in self.current_palette:
            if key in target:
                curr = self.current_palette[key]
                targ = target[key]
                r = int(curr[0] + (targ[0] - curr[0]) * self.palette_lerp_speed * dt)
                g = int(curr[1] + (targ[1] - curr[1]) * self.palette_lerp_speed * dt)
                b = int(curr[2] + (targ[2] - curr[2]) * self.palette_lerp_speed * dt)
                # Clamp color values to valid RGB range (0-255)
                r = max(0, min(255, r))
                g = max(0, min(255, g))
                b = max(0, min(255, b))
                self.current_palette[key] = (r, g, b)

    def _update_orientation(self, player_x: float, player_y: float) -> None:
        """Update cannon orientation."""
        # Update central cannon position and aim; lateral cannons aim from their fixed positions
        if self.cannons and len(self.cannons) >= 1:
            # assume last is central if frenzy created
            central = self.cannons[-1]
            central.update_position(self.x, self.y, self.w, self.h)
            central.aim_at(player_x, player_y)
            # lateral cannons aim independently (they keep explicit positions)
            for c in self.cannons[:-1]:
                # if cannon has a relative offset, update its absolute position so it follows the boss
                rel = getattr(c, "_rel", None)
                if rel is not None:
                    relx, rely = rel
                    c.set_position(self.x + relx * self.w, self.y + rely * self.h)
                c.aim_at(player_x, player_y)
            # face_center remains the central barrel tip for legacy behaviors
            self.face_center.x, self.face_center.y = central.get_barrel_tip_position()
            self.facing_direction = central.get_direction()
        else:
            self.cannon.update_position(self.x, self.y, self.w, self.h)
            self.cannon.aim_at(player_x, player_y)
            self.face_center.x, self.face_center.y = (
                self.cannon.get_barrel_tip_position()
            )
            self.facing_direction = self.cannon.get_direction()

    def _init_attack_system(self) -> None:
        self.attack_timer = Timer(random.uniform(*Config.BOSS_CALM_ATTACK_INTERVAL))
        self.charge_duration = Config.BOSS_CHARGE_DURATION
        self.charge_timer = Timer(self.charge_duration)
        self.fire_duration = Config.BOSS_LASER_LIFETIME
        self.fire_timer = Timer(self.fire_duration)

    def _activate_frenzy_mode(self) -> None:
        self.frenzy_mode = True
        self.pending_frenzy = False
        self.speed = Config.BOSS_FRENZY_SPEED
        self.frenzy_shake_timer = Config.BOSS_FRENZY_SHAKE_DURATION
        self._cached_layers.clear()

        for square in self.floating_squares:
            square.set_frenzy_mode(True)

        self._update_frenzy_timings()

        # create side cannons positioned near the upper-left/right 'eye' areas
        if len(self.cannons) == 1:
            left = BossCannon()
            right = BossCannon()
            # relative positions inside boss box (rel_x, rel_y)
            left._rel = (0.25, 0.25)
            right._rel = (0.75, 0.25)
            # initialize positions
            left.set_position(
                self.x + left._rel[0] * self.w, self.y + left._rel[1] * self.h
            )
            right.set_position(
                self.x + right._rel[0] * self.w, self.y + right._rel[1] * self.h
            )
            # order: left, right, central (central used as face_center)
            self.cannons = [left, right, self.cannon]

        if self.state == BossState.ACTIVE:
            self.fired_lasers.clear()
            self._sound_events.append("stop_charging")
            self._sound_events.append("stop_fire")
            self.particle_system.clear_all()
            self._reset_attack_timer()

        self.fire_timer.duration = Config.BOSS_FRENZY_LASER_LIFETIME
        logging.info("💀 Boss entrou em modo FRENZY!")

    def _update_frenzy_timings(self) -> None:
        self.charge_duration = self._get_charge_duration()
        self.charge_timer.duration = self.charge_duration
        self.laser_delay_duration = self._get_laser_delay()

    def _get_charge_duration(self) -> float:
        return (
            Config.BOSS_FRENZY_CHARGE_DURATION
            if self.frenzy_mode
            else Config.BOSS_CHARGE_DURATION
        )

    def update(
        self, dt: float, player_x: float, player_y: float | None = None
    ) -> tuple[List[BossLaser], List[BossSquare], List[BossSoundEvent]]:
        self._sound_events: List[BossSoundEvent] = []
        self._update_lerps(dt)
        self.breathing_timer += dt
        self.frenzy_shake_timer = max(0.0, self.frenzy_shake_timer - dt)

        if self.frenzy_shake_timer > 0:
            self._shake_offset_x = random.randint(-3, 3)
            self._shake_offset_y = random.randint(-3, 3)
        else:
            self._shake_offset_x = 0
            self._shake_offset_y = 0

        self.player_x = player_x
        self.player_y = player_y

        center_x = self.x + self.w / 2
        center_y = self.y + self.h / 2

        self.squares_animation_timer += dt * 5
        pulse_scale = 1.0 + 0.2 * abs(math.cos(self.squares_animation_timer))

        for square in self.floating_squares:
            if square.state == "orbiting":
                square.orbit_angle = (
                    square.orbit_angle + square.orbit_speed * dt
                ) % 360
                angle_rad = math.radians(square.orbit_angle)
                target_x = center_x + math.cos(angle_rad) * square.orbit_radius
                target_y = center_y + math.sin(angle_rad) * square.orbit_radius
                lerp_speed = 7.0 * square.speed_var
                square.x += (target_x - square.x) * lerp_speed * dt
                square.y += (target_y - square.y) * lerp_speed * dt
                square.size = square.base_size * pulse_scale
                square.rotation = 0.0
            elif square.state in ("preparing", "launching"):
                square.prepare_timer += dt
                square.rotation += dt * 720
                prepare_pulse = 1.0 + 0.4 * abs(math.sin(square.prepare_timer * 10))
                square.size = square.base_size * prepare_pulse
                if square.state == "preparing" and square.prepare_timer >= 1.0:
                    square.state = "ready_to_launch"

        if player_y is not None:
            self._update_orientation(player_x, player_y)

        if self.frenzy_shake_timer <= 0:
            if self.pending_frenzy and self.state not in (
                BossState.AIMING,
                BossState.CHARGING,
                BossState.CONVERGING,
                BossState.FIRING,
            ):
                self._activate_frenzy_mode()

        spawned_squares: List[BossSquare] = []
        if self.frenzy_mode and self.frenzy_shake_timer <= 0 and player_y is not None:
            if self.square_launch_queue:
                self.square_launch_timer += dt
                if self.square_launch_timer >= self.square_launch_delay:
                    square = self.square_launch_queue.pop(0)
                    projectile = self._create_square_projectile(
                        square, player_x, player_y
                    )
                    projectile.palette = self.current_palette
                    spawned_squares.append(projectile)
                    square.state, square.prepare_timer, square.rotation = (
                        "orbiting",
                        0.0,
                        0.0,
                    )
                    self.square_launch_timer = 0.0

            ready_squares = [
                sq for sq in self.floating_squares if sq.state == "ready_to_launch"
            ]
            for square in ready_squares:
                square.state = "launching"
                self.square_launch_queue.append(square)

            if self.state == BossState.ACTIVE and not self.pending_laser_data:
                self.square_attack_timer.update(dt)
                if self.square_attack_timer.done():
                    preparing = [
                        sq for sq in self.floating_squares if sq.state != "orbiting"
                    ]
                    if not preparing:
                        orbiting = [
                            sq for sq in self.floating_squares if sq.state == "orbiting"
                        ]
                        if orbiting:
                            num = random.randint(3, min(6, len(orbiting)))
                            for sq in random.sample(orbiting, num):
                                sq.state, sq.prepare_timer = "preparing", 0.0
                    self.square_attack_timer.start(random.uniform(2.0, 3.5))

        lasers_fired: List[BossLaser] = []
        if self.state == BossState.ENTERING:
            self._update_entering_state(dt)
        elif self.state == BossState.ACTIVE:
            self._update_active_state(dt)
        elif self.state == BossState.AIMING:
            self._enter_charging()
        elif self.state == BossState.CHARGING:
            self._update_charging_state(dt)
        elif self.state == BossState.CONVERGING:
            lasers_fired = self._update_converging_state(dt)
        elif self.state == BossState.PREPARING_TO_FIRE:
            lasers_fired = self._update_preparing_to_fire_state(dt)
        elif self.state == BossState.FIRING:
            self._update_firing_state(dt)

        return (lasers_fired, spawned_squares, self._sound_events)

    def _update_entering_state(self, dt: float) -> None:
        self.y += self.entry_speed * dt
        if self.y >= self.target_y:
            self.y = self.target_y
            self.state = BossState.ACTIVE
            self.attack_timer.start()

    def _update_active_state(self, dt: float) -> None:
        self.x += self.speed * self.direction
        if self.x <= 0 or self.x + self.w >= Config.SCREEN_WIDTH:
            self.direction *= -1

        if self.frenzy_shake_timer <= 0:
            self.attack_timer.update(dt)
            if self.attack_timer.done():
                self.state = BossState.AIMING

    def _update_charging_state(self, dt: float) -> None:
        acc_dt = self._get_accelerated_dt(dt)
        self.charge_timer.update(dt)
        self.charge_progress = min(
            1.0, self.charge_progress + acc_dt / self.charge_duration
        )
        for c in self.cannons:
            c.set_charging(True, self.charge_progress)

        face_x, face_y = self.face_center.x, self.face_center.y
        self.particle_system.generate_charging_particles(face_x, face_y)
        self.particle_system.update_charging_particles(acc_dt, face_x, face_y)

        if self.charge_timer.done():
            self._sound_events.append("stop_charging")
            self.state = BossState.CONVERGING

    def _update_converging_state(self, dt: float) -> List[BossLaser]:
        self.particle_system.update_charging_particles(
            dt, self.face_center.x, self.face_center.y
        )
        for c in self.cannons:
            c.set_charging(True, 1.0)

        if not self.particle_system.charging_particles:
            self.particle_system.create_circle_disappear_particles(
                self.face_center.x,
                self.face_center.y,
                Config.BOSS_CHARGE_CIRCLE_MAX_RADIUS,
            )
            self.pending_laser_data = self._prepare_laser_data()
            self.state = BossState.PREPARING_TO_FIRE
            self.laser_delay_timer = self._get_laser_delay()
        return []

    def _prepare_laser_data(self) -> dict[str, Any]:
        return {
            "face_x": self.face_center.x,
            "face_y": self.face_center.y,
            "face_normal": self.facing_direction.copy(),
            "lifetime": Config.BOSS_FRENZY_LASER_LIFETIME
            if self.frenzy_mode
            else Config.BOSS_LASER_LIFETIME,
            "frenzy_mode": self.frenzy_mode,
        }

    def _update_preparing_to_fire_state(self, dt: float) -> List[BossLaser]:
        self.laser_delay_timer -= dt
        blink = (int(self.laser_delay_timer * 10) % 2) == 0
        for c in self.cannons:
            c.set_charging(True, 1.0 if blink else 0.7)
        self.particle_system.update_circle_disappear_particles(
            self._get_accelerated_dt(dt)
        )

        if self.laser_delay_timer <= 0 and self.pending_laser_data:
            new_lasers = self._create_lasers_from_data(self.pending_laser_data)
            self._sound_events.append("play_fire")
            self.fired_lasers.extend(new_lasers)
            self.fire_timer = Timer(self.pending_laser_data["lifetime"])
            self.fire_timer.start()
            self.state = BossState.FIRING
            self.pending_laser_data = None
            return new_lasers
        return []

    def _create_lasers_from_data(self, laser_data: dict[str, Any]) -> List[BossLaser]:
        return self._create_laser_pattern(
            laser_data["face_x"],
            laser_data["face_y"],
            laser_data["lifetime"],
            laser_data["frenzy_mode"],
            laser_data["face_normal"],
        )

    def _create_laser_pattern(
        self,
        face_x: float,
        face_y: float,
        lifetime: float,
        is_frenzy: bool,
        face_normal: pygame.Vector2,
    ) -> List[BossLaser]:
        if is_frenzy:
            # If we have multiple cannons (created on frenzy), spawn one laser per cannon
            if hasattr(self, "cannons") and len(self.cannons) >= 3:
                lasers: List[BossLaser] = []
                # offsets and sequence delays for left, right, center
                side_offset = (
                    self.w * 0.25
                )  # increase lateral separation for visible 'wall'
                seq_delays = [0.0, 0.15, 0.35]  # tighter sequential cadence
                for idx, c in enumerate(self.cannons):
                    tip_x, tip_y = c.get_barrel_tip_position()
                    # compute a target near the player's position with lateral offset for sides
                    target_x = self.player_x if self.player_x is not None else tip_x
                    target_y = self.player_y if self.player_y is not None else tip_y + 1
                    if idx == 0:  # left
                        target_x = target_x - side_offset
                    elif idx == 1:  # right
                        target_x = target_x + side_offset
                    # compute direction toward target
                    dx, dy = target_x - tip_x, target_y - tip_y
                    dist = math.hypot(dx, dy)
                    if dist > 0:
                        dx, dy = dx / dist, dy / dist
                    else:
                        dx, dy = face_normal.x, face_normal.y
                    lasers.append(
                        BossLaser(
                            tip_x,
                            tip_y,
                            tip_x + dx * self.LASER_DISTANCE,
                            tip_y + dy * self.LASER_DISTANCE,
                            lifetime=lifetime,
                            owner=c,
                            start_delay=seq_delays[min(idx, len(seq_delays) - 1)],
                        )
                    )
                return lasers
            # fallback: create fan from face center
            lasers: List[BossLaser] = []
            for i in [2, 0, 1]:
                ang = self.FRENZY_LASER_ANGLES[i]
                cos_a, sin_a = math.cos(ang), math.sin(ang)
                rot_dir = pygame.Vector2(
                    face_normal.x * cos_a - face_normal.y * sin_a,
                    face_normal.x * sin_a + face_normal.y * cos_a,
                )
                lasers.append(
                    BossLaser(
                        face_x,
                        face_y,
                        face_x + rot_dir.x * self.LASER_DISTANCE,
                        face_y + rot_dir.y * self.LASER_DISTANCE,
                        lifetime=lifetime,
                    )
                )
            return lasers
        return [
            BossLaser(
                face_x,
                face_y,
                face_x + face_normal.x * self.LASER_DISTANCE,
                face_y + face_normal.y * self.LASER_DISTANCE,
                lifetime=lifetime,
            )
        ]

    def _update_firing_state(self, dt: float) -> None:
        self.fire_timer.update(dt)
        for c in self.cannons:
            c.set_charging(False, 0.0)
        for laser in self.fired_lasers:
            laser.update(dt)
        self.fired_lasers = [L for L in self.fired_lasers if not L.dead]
        if not self.fired_lasers:
            self._sound_events.append("stop_fire")

        if self.fire_timer.done() and all(
            L.is_animation_finished() for L in self.fired_lasers
        ):
            self.state = BossState.ACTIVE
            self._reset_attack_timer()
            self.fired_lasers.clear()
            self._sound_events.append("stop_fire")

    def _reset_attack_timer(self) -> None:
        """Reset attack timer with random interval based on current mode."""
        self.attack_timer.duration = random.uniform(*Config.BOSS_CALM_ATTACK_INTERVAL)
        self.attack_timer.start()

    def _enter_charging(self) -> None:
        """Transition to CHARGING state and initialize charging phase."""
        self.state = BossState.CHARGING
        self.charge_progress = 0.0
        self.charge_timer.start()
        for c in self.cannons:
            c.set_charging(True, 0.0)

    def _create_square_projectile(
        self, square: BossSquare, px: float, py: float
    ) -> BossSquare:
        dx, dy = px - square.x, py - square.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 0:
            dx, dy = (
                dx / dist + random.uniform(-0.5, 0.5),
                dy / dist + random.uniform(-0.5, 0.5),
            )
            new_dist = math.sqrt(dx * dx + dy * dy)
            if new_dist > 0:
                dx, dy = dx / new_dist, dy / new_dist
        else:
            dx, dy = 0, 1
        return BossSquare(square.x, square.y, dx * 250, dy * 250, square.base_size)

    def _get_animation_speed_multiplier(self) -> float:
        return (
            Config.BOSS_FRENZY_ANIMATION_SPEED_MULTIPLIER
            if self.frenzy_mode
            else Config.BOSS_ANIMATION_SPEED_MULTIPLIER
        )

    def _get_accelerated_dt(self, dt: float) -> float:
        return dt * self._get_animation_speed_multiplier()

    def _get_laser_delay(self) -> float:
        return (
            Config.BOSS_FRENZY_LASER_DELAY
            if self.frenzy_mode
            else Config.BOSS_LASER_DELAY
        )

    def _render_layer(self, layer_cells: set[str]) -> pygame.Surface:
        surf = pygame.Surface((int(self.w), int(self.h)), pygame.SRCALPHA)
        p = self.pixel_size
        for r, row in enumerate(PIXEL_MAP):
            for c, cell in enumerate(row):
                if cell in layer_cells:
                    pygame.draw.rect(
                        surf, (255, 255, 255), (int(c * p), int(r * p), int(p), int(p))
                    )
        return surf

    def _get_layer_surfaces(self) -> dict[str, pygame.Surface]:
        if not self._cached_layers:
            self._cached_layers["shell"] = self._render_layer({"A", "C", "D", "E", "F"})
            self._cached_layers["core"] = self._render_layer({"G", "H"})
            self._cached_layers["cannon_base"] = self._render_layer({"I", "M"})
        return self._cached_layers

    def _draw_layer(
        self,
        surface: pygame.Surface,
        layer_name: str,
        dx: int,
        dy: int,
        off_x: float = 0,
        off_y: float = 0,
    ):
        layers = self._get_layer_surfaces()
        if layer_name not in layers:
            return
        lsurf = layers[layer_name].copy()
        palette = self.current_palette

        cells = {
            "shell": {"A", "C", "D", "E", "F"},
            "core": {"G", "H"},
            "cannon_base": {"I", "M"},
        }[layer_name]
        p = self.pixel_size
        for r, row in enumerate(PIXEL_MAP):
            for c, cell in enumerate(row):
                if cell in cells:
                    pygame.draw.rect(
                        lsurf,
                        palette.get(cell, (255, 0, 255)),
                        (int(c * p), int(r * p), int(p), int(p)),
                    )
        surface.blit(lsurf, (int(dx + off_x), int(dy + off_y)))

    def draw(self, surface: pygame.Surface) -> None:
        dx, dy = int(self.x + self._shake_offset_x), int(self.y + self._shake_offset_y)

        # 1. Squares Behind
        self._draw_floating_squares(
            surface, self._shake_offset_x, self._shake_offset_y, behind=True
        )

        # 2. Body Layers with breathing
        breathing = math.sin(self.breathing_timer * 2.5) * 2.0
        self._draw_layer(surface, "shell", dx, dy, 0, breathing)
        self._draw_layer(surface, "core", dx, dy, 0, breathing * 1.5)
        self._draw_layer(surface, "cannon_base", dx, dy)

        # 3. Squares Front
        self._draw_floating_squares(
            surface, self._shake_offset_x, self._shake_offset_y, behind=False
        )

        # 4. Interactive Elements
        # draw all cannons (central last so it renders on top)
        if len(self.cannons) > 1:
            for c in self.cannons:
                c.draw(surface, self._shake_offset_x, self._shake_offset_y)
        else:
            self.cannon.draw(surface, self._shake_offset_x, self._shake_offset_y)
        if self.state != BossState.ENTERING:
            self._draw_health_bar(surface)
        if self.state in (BossState.AIMING, BossState.CHARGING, BossState.CONVERGING):
            self._draw_aiming_line(surface)

        # 5. Effects
        if self.state in (
            BossState.CHARGING,
            BossState.CONVERGING,
            BossState.PREPARING_TO_FIRE,
        ):
            rad = (
                self.charge_progress * Config.BOSS_CHARGE_CIRCLE_MAX_RADIUS
                if self.state == BossState.CHARGING
                else Config.BOSS_CHARGE_CIRCLE_MAX_RADIUS
            )
            if rad > 0:
                pygame.draw.circle(
                    surface,
                    (255, 255, 100),
                    (
                        int(self.face_center.x + self._shake_offset_x),
                        int(self.face_center.y + self._shake_offset_y),
                    ),
                    int(rad),
                    4,
                )
                if rad > 8:
                    pygame.draw.circle(
                        surface,
                        (255, 255, 0),
                        (
                            int(self.face_center.x + self._shake_offset_x),
                            int(self.face_center.y + self._shake_offset_y),
                        ),
                        int(rad - 8),
                        2,
                    )
            self.particle_system.draw_particles(
                surface, self._shake_offset_x, self._shake_offset_y
            )

        if self.state == BossState.PREPARING_TO_FIRE:
            if (pygame.time.get_ticks() % 200) < 100:
                pygame.draw.circle(
                    surface,
                    (255, 255, 255),
                    (
                        int(self.face_center.x + self._shake_offset_x),
                        int(self.face_center.y + self._shake_offset_y),
                    ),
                    12,
                    3,
                )

        self.particle_system.draw_circle_disappear_particles(
            surface, self._shake_offset_x, self._shake_offset_y
        )

    def _draw_floating_squares(
        self, surface: pygame.Surface, off_x: float, off_y: float, behind: bool
    ) -> None:
        for i, sq in enumerate(self.floating_squares):
            if (i % 2 == 0) != behind:
                continue

            color, border = (255, 0, 0), (255, 100, 100)  # Fallback
            if sq.state in ("preparing", "launching"):
                p = 0.5 + 0.5 * abs(math.sin(sq.prepare_timer * 8))
                color, border = (255, int(200 * p), 0), (255, 255, 0)
            else:
                pal = self.current_palette
                # No frenzy usamos a cor do chassi ou similar
                color = pal.get("C", (200, 0, 0))
                intensity = 0.7 + (i / len(self.floating_squares)) * 0.3
                color = (
                    int(color[0] * intensity),
                    int(color[1] * intensity),
                    int(color[2] * intensity),
                )
                border = (
                    min(255, color[0] + 50),
                    min(255, color[1] + 50),
                    min(255, color[2] + 50),
                )

            if sq.rotation > 0:
                self._draw_rotated_square(surface, sq, color, border, off_x, off_y)
            else:
                r = pygame.Rect(
                    int(sq.x - sq.size / 2 + off_x),
                    int(sq.y - sq.size / 2 + off_y),
                    int(sq.size),
                    int(sq.size),
                )
                pygame.draw.rect(surface, color, r)
                pygame.draw.rect(surface, border, r, 2)

    def _draw_rotated_square(
        self,
        surface: pygame.Surface,
        sq: BossSquare,
        color: Tuple[int, int, int],
        border: Tuple[int, int, int],
        ox: float,
        oy: float,
    ) -> None:
        corners = rotated_square_corners(
            sq.x + ox, sq.y + oy, sq.size / 2, math.radians(sq.rotation)
        )
        pygame.draw.polygon(surface, color, corners)
        pygame.draw.polygon(surface, border, corners, 2)

    def _get_aiming_line_intensity(self) -> float:
        """Calcula a intensidade do traçado de mira baseado no estado.
        0.0 = mínimo, 1.0 = máximo (pronto para disparar).
        """
        if self.state == BossState.AIMING:
            return 0.3  # Fraco durante a mira inicial
        elif self.state == BossState.CHARGING:
            # Aumenta com o progresso de carga (0 -> 1)
            return 0.3 + self.charge_progress * 0.5  # 0.3 -> 0.8
        elif self.state == BossState.CONVERGING:
            return 1.0  # Máximo intensidade antes de preparar para disparar
        return 0.0

    def _draw_aiming_line(self, surface: pygame.Surface) -> None:
        total_cycle = Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH
        time_based_offset = int(pygame.time.get_ticks() * 0.1) % total_cycle
        intensity = self._get_aiming_line_intensity()
        if self.frenzy_mode and len(self.cannons) > 1:
            # Draw aiming lines for each cannon from its barrel tip
            for i, c in enumerate(self.cannons):
                tip_x, tip_y = c.get_barrel_tip_position()
                tip = pygame.Vector2(tip_x, tip_y)
                dirv = c.get_direction()
                # consider central cannon as primary for styling
                primary = i == len(self.cannons) - 1
                self._draw_dashed_line(
                    surface, tip, dirv, time_based_offset, primary, intensity
                )
        else:
            self._draw_dashed_line(
                surface,
                self.face_center,
                self.facing_direction,
                time_based_offset,
                True,
                intensity,
            )

    def _draw_dashed_line(
        self,
        surface: pygame.Surface,
        start: pygame.Vector2,
        direction: pygame.Vector2,
        offset: int,
        primary: bool,
        intensity: float = 0.5,
    ) -> None:
        # Aumentar cor conforme intensidade
        base_color = (
            colors.BOSS_AIM_LINE
            if primary
            else tuple(max(50, int(c * 0.6)) for c in colors.BOSS_AIM_LINE)
        )
        # Interpolar cor: base -> brilho vermelho conforme intensidade
        r = int(base_color[0] + (255 - base_color[0]) * intensity)
        g = int(base_color[1] + (50 - base_color[1]) * intensity)
        b = int(base_color[2] + (50 - base_color[2]) * intensity)
        color = (r, g, b)

        # Aumentar largura conforme intensidade
        base_width = 4 if primary else 2
        width = max(
            base_width, int(base_width + intensity * 6)
        )  # base_width -> base_width + 6

        curr_dist = offset - (Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH)
        while curr_dist < self.LASER_DISTANCE:
            if curr_dist + Config.BOSS_AIM_DASH_LENGTH > 0:
                s_dist, e_dist = (
                    max(0, curr_dist),
                    min(self.LASER_DISTANCE, curr_dist + Config.BOSS_AIM_DASH_LENGTH),
                )
                pygame.draw.line(
                    surface,
                    color,
                    start + direction * s_dist,
                    start + direction * e_dist,
                    width,
                )
            curr_dist += Config.BOSS_AIM_DASH_LENGTH + Config.BOSS_AIM_GAP_LENGTH

    def _draw_health_bar(self, surface: pygame.Surface) -> None:
        if self.health <= 0:
            return
        bmw, bh = min(200, self.w * 2), 10
        bx, by = self.x + (self.w - bmw) / 2, self.y - 20
        pygame.draw.rect(surface, (255, 0, 0), (bx, by, bmw, bh))
        pygame.draw.rect(
            surface,
            (0, 255, 0),
            (bx, by, int(bmw * (self.health / self.max_health)), bh),
        )

    def can_take_damage(self) -> bool:
        return self.state != BossState.ENTERING and not self.dead

    def get_rect(self) -> pygame.Rect:
        if not self.can_take_damage():
            return pygame.Rect(-1000, -1000, 0, 0)
        return pygame.Rect(int(self.x), int(self.y), int(self.w), int(self.h))

    @property
    def rect(self) -> pygame.Rect:
        return self.get_rect()

    def collision_circle(self) -> tuple[float, float, float]:
        if not self.can_take_damage():
            return -1000.0, -1000.0, 0.0
        return self.x + self.w / 2, self.y + self.h / 2, max(self.w, self.h) / 2

    def take_damage(self, amount: int) -> None:
        if not self.can_take_damage():
            return
        self.health -= amount
        if self.health <= 0:
            self.health, self.dead = 0, True
        if (
            not self.frenzy_mode
            and not self.pending_frenzy
            and self.health <= self.max_health * Config.BOSS_FRENZY_THRESHOLD
        ):
            if self.state not in (
                BossState.AIMING,
                BossState.CHARGING,
                BossState.CONVERGING,
                BossState.FIRING,
            ):
                self._activate_frenzy_mode()
            else:
                self.pending_frenzy = True

    def is_off_screen(self) -> bool:
        return self.y > Config.SCREEN_HEIGHT

    def get_explosion_duration(self) -> float:
        return Config.BOSS_EXPLOSION_DURATION
