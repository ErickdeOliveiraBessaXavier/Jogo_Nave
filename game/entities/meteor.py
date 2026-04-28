from __future__ import annotations

import math
import random
from typing import Callable, List, Tuple

import pygame

from ..core import colors
from ..core.config import config as Config

# Type alias for the meteor factory function
MeteorFactory = Callable[[int, float, float, float, float], "Meteor"]

# Cache global de shapes para reutilização
_SHAPE_CACHE: dict[int, List[Tuple[float, float]]] = {}


def _get_or_create_shape(size: int) -> List[Tuple[float, float]]:
    """Retorna shape cacheado ou cria novo com irregularidade balanceada."""
    if size not in _SHAPE_CACHE:
        pts: List[Tuple[float, float]] = []
        num_points = max(8, int(size / 3))

        radii: List[float] = []
        for i in range(num_points):
            radii.append(random.uniform(0.7, 1.3))

        smoothed_radii: List[float] = []
        for i in range(num_points):
            prev_r: float = radii[(i - 1) % num_points]
            curr_r: float = radii[i]
            next_r: float = radii[(i + 1) % num_points]
            smooth_r: float = prev_r * 0.1 + curr_r * 0.8 + next_r * 0.1
            smoothed_radii.append(smooth_r)

        for i in range(num_points):
            ang: float = (2 * math.pi * i) / num_points
            r: float = size * smoothed_radii[i]
            pts.append((r * math.cos(ang), r * math.sin(ang)))

        _SHAPE_CACHE[size] = pts
    return _SHAPE_CACHE[size]


class Meteor:
    def __init__(
        self,
        size: int | None = None,
        x: float | None = None,
        y: float | None = None,
        vx: float | None = None,
        vy: float | None = None,
    ):
        # Initialize attributes with type hints
        self.size: int
        self.w: int
        self.h: int
        self.x: float
        self.y: float
        self.vx: float
        self.vy: float
        self.rotation: float
        self.rotation_speed: float
        self._base_points: List[Tuple[float, float]]
        self.color_intensity: float
        self.dead: bool
        self.active: bool
        self.health: int

        # Configure all attributes
        self.size = (
            size
            if size is not None
            else random.randint(Config.MIN_METEOR_SIZE, Config.MAX_METEOR_SIZE)
        )
        self.w = self.h = self.size * 2

        self._configure_position(x, y)
        self._configure_velocity(vx, vy)
        self._configure_rotation()
        self._configure_appearance()
        self._configure_health()

    def _configure_position(self, x: float | None, y: float | None) -> None:
        """Configure meteor position."""
        if x is None:
            self.x = random.randint(0, Config.SCREEN_WIDTH - self.w)
        else:
            self.x = x
        self.y = -self.h if y is None else y

    def _configure_velocity(self, vx: float | None, vy: float | None) -> None:
        """Configure meteor velocity based on size."""
        ratio = (self.size - Config.MIN_METEOR_SIZE) / (
            Config.MAX_METEOR_SIZE - Config.MIN_METEOR_SIZE + 1e-6
        )
        base_vy = (
            Config.FAST_METEOR_SPEED
            - (Config.FAST_METEOR_SPEED - Config.SLOW_METEOR_SPEED) * ratio
        )

        if vy is None:
            self.vy = base_vy
        else:
            self.vy = vy

        if vx is None:
            if random.random() < Config.DIAGONAL_CHANCE:
                self.vx = random.uniform(-120.0, 120.0) * (
                    self.vy / max(Config.FAST_METEOR_SPEED, 1e-6)
                )
            else:
                self.vx = 0.0
        else:
            self.vx = vx

    def _configure_rotation(self) -> None:
        """Configure meteor rotation."""
        ratio = (self.size - Config.MIN_METEOR_SIZE) / (
            Config.MAX_METEOR_SIZE - Config.MIN_METEOR_SIZE + 1e-6
        )
        self.rotation = 0.0
        self.rotation_speed = random.uniform(-180, 180) * (1.0 - ratio * 0.5)

    def _configure_appearance(self) -> None:
        """Configure meteor shape and color."""
        ratio = (self.size - Config.MIN_METEOR_SIZE) / (
            Config.MAX_METEOR_SIZE - Config.MIN_METEOR_SIZE + 1e-6
        )
        self._base_points = _get_or_create_shape(self.size)
        self.color_intensity = 1.0 - ratio * 0.3
        self.dead = False
        self.active = True

    def _configure_health(self) -> None:
        """Configure meteor health based on size."""
        self.health = int(10 + (self.size / Config.MAX_METEOR_SIZE) * 40)
        # is_side_scroll é setado pelo MeteorPool/spawner; default seguro.
        if not hasattr(self, "is_side_scroll"):
            self.is_side_scroll = False

    def reset(
        self,
        size: int | None = None,
        x: float | None = None,
        y: float | None = None,
        vx: float | None = None,
        vy: float | None = None,
    ):
        """Reconfigura o meteoro para reutilização no pool."""
        self.size = (
            size
            if size is not None
            else random.randint(Config.MIN_METEOR_SIZE, Config.MAX_METEOR_SIZE)
        )
        self.w = self.h = self.size * 2

        self._configure_position(x, y)
        self._configure_velocity(vx, vy)
        self._configure_rotation()
        self._configure_appearance()
        self._configure_health()

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float, is_side_scroll: bool = False):
        """Update meteor position and rotation."""
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.rotation += self.rotation_speed * dt

        if is_side_scroll:
            if self.x < -self.w or self.y > Config.SCREEN_HEIGHT or self.y < -self.h:
                self.dead = True
        else:
            if (
                (self.y > Config.SCREEN_HEIGHT)
                or (self.x < -self.w)
                or (self.x > Config.SCREEN_WIDTH + self.w)
            ):
                self.dead = True

    def _rotated_points(self) -> List[Tuple[int, int]]:
        """Retorna pontos rotacionados."""
        rad = math.radians(self.rotation)
        cr = math.cos(rad)
        sr = math.sin(rad)
        cx = self.x + self.w * 0.5
        cy = self.y + self.h * 0.5

        return [
            (round(cx + px * cr - py * sr), round(cy + px * sr + py * cr))
            for px, py in self._base_points
        ]

    def draw(self, screen: pygame.Surface):
        """Draw meteor on screen."""
        points = self._rotated_points()
        intensity = max(0.0, min(1.0, self.color_intensity))

        if self.size <= Config.MIN_METEOR_SIZE + 8:
            body_color = (
                max(0, min(255, int(255 * intensity))),
                max(0, min(255, int(200 * intensity))),
                max(0, min(255, int(100 * intensity))),
            )
            border_color = colors.YELLOW
            core_color = colors.LIGHT_ORANGE
        else:
            body_color = (
                max(0, min(255, int(200 * intensity))),
                max(0, min(255, int(100 * intensity))),
                max(0, min(255, int(50 * intensity))),
            )
            border_color = colors.RED
            core_color = colors.DARK_RED

        pygame.draw.polygon(screen, body_color, points)
        pygame.draw.polygon(screen, border_color, points, 2)
        center = (int(self.x + self.w // 2), int(self.y + self.h // 2))
        pygame.draw.circle(screen, core_color, center, max(2, self.size // 4))

    def get_points_value(self) -> int:
        """Calculate points value based on meteor size."""
        size_factor = Config.MAX_METEOR_SIZE - self.size
        size_bonus = int(size_factor * Config.SIZE_BONUS_MULTIPLIER)
        return Config.BASE_POINTS + size_bonus

    def can_split(self) -> bool:
        """Check if meteor is large enough to fragment."""
        return self.size >= Config.FRAGMENT_SPLIT_THRESHOLD

    def spawn_fragments(
        self,
        is_side_scroll: bool = False,
        meteor_factory: MeteorFactory | None = None,
    ) -> List[Meteor]:
        """
        Split meteor into smaller fragments when destroyed.

        In top-down mode: fragments inherit gravity (fall downward)
        In side-scroll mode: fragments disperse naturally in all directions

        Args:
            is_side_scroll: Game mode determines fragment physics
            meteor_factory: Optional factory function for creating fragments

        Returns:
            List of fragment Meteor objects (empty if cannot split)
        """
        if not self.can_split():
            return []

        # Use provided factory or default constructor
        factory = meteor_factory or self._create_meteor

        cx = self.x + self.w / 2
        cy = self.y + self.h / 2

        count = random.randint(*Config.FRAGMENT_COUNT_RANGE)
        target_size = max(Config.MIN_METEOR_SIZE, int(self.size * 0.55))
        fragments: List[Meteor] = []

        # Pre-calculate physics constants
        parent_speed = math.sqrt(self.vx * self.vx + self.vy * self.vy)
        base_speed = max(200.0, parent_speed * 0.8)

        base_angle_rad = math.radians(random.uniform(0, 360))
        half_spread_rad = math.radians(Config.FRAGMENT_SPREAD / 2)
        size_offset_x = self.size * 0.5
        size_offset_y = self.size * 0.3

        for _ in range(count):
            # Fragment size variation (±20%)
            s = max(Config.MIN_METEOR_SIZE, int(target_size * random.uniform(0.8, 1.2)))

            # Angle with spread
            angle_offset = random.uniform(-half_spread_rad, half_spread_rad)
            ang = base_angle_rad + angle_offset

            # Pre-calculate trigonometry once
            cos_ang = math.cos(ang)
            sin_ang = math.sin(ang)

            # Velocity with variation
            speed = base_speed * random.uniform(0.8, 1.3)
            vx = cos_ang * speed + self.vx * 0.3

            # Y velocity depends on game mode
            if is_side_scroll:
                # Side-scroll: natural dispersal
                vy = sin_ang * speed + self.vy * 0.2
            else:
                # Top-down: gravity pulls downward
                vy = abs(sin_ang * speed) + self.vy * 0.2 + 50.0

            # Fragment position
            fx = cx + cos_ang * size_offset_x - s
            fy = cy + sin_ang * size_offset_y - s

            fragments.append(factory(s, fx, fy, vx, vy))

        return fragments

    @staticmethod
    def _create_meteor(size: int, x: float, y: float, vx: float, vy: float) -> Meteor:
        """Default factory for creating fragment meteors."""
        return Meteor(size=size, x=x, y=y, vx=vx, vy=vy)

    def _build_fragment_specs(self, is_side_scroll: bool):
        """Constrói tuplas leves (size, x, y, vx, vy) para serem materializadas
        pelo EntityManager via meteor_pool.get(*spec). Mantém o pool isolado
        da entidade.
        """
        from ..systems.hit_result import MeteorSpec

        if not self.can_split():
            return ()

        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        count = random.randint(*Config.FRAGMENT_COUNT_RANGE)
        target_size = max(Config.MIN_METEOR_SIZE, int(self.size * 0.55))

        parent_speed = math.sqrt(self.vx * self.vx + self.vy * self.vy)
        base_speed = max(200.0, parent_speed * 0.8)

        base_angle_rad = math.radians(random.uniform(0, 360))
        half_spread_rad = math.radians(Config.FRAGMENT_SPREAD / 2)
        size_offset_x = self.size * 0.5
        size_offset_y = self.size * 0.3

        specs: list[MeteorSpec] = []
        for _ in range(count):
            s = max(Config.MIN_METEOR_SIZE, int(target_size * random.uniform(0.8, 1.2)))
            ang = base_angle_rad + random.uniform(-half_spread_rad, half_spread_rad)
            cos_ang = math.cos(ang)
            sin_ang = math.sin(ang)
            speed = base_speed * random.uniform(0.8, 1.3)
            vx = cos_ang * speed + self.vx * 0.3
            if is_side_scroll:
                vy = sin_ang * speed + self.vy * 0.2
            else:
                vy = abs(sin_ang * speed) + self.vy * 0.2 + 50.0
            fx = cx + cos_ang * size_offset_x - s
            fy = cy + sin_ang * size_offset_y - s
            specs.append(MeteorSpec(s, fx, fy, vx, vy))

        return tuple(specs)

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x + self.w / 2, self.y + self.h / 2, max(12, self.size)

    def on_hit(self, damage: int, hit_x: float, hit_y: float):
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        is_side_scroll = getattr(self, "is_side_scroll", False)
        fragments = self._build_fragment_specs(is_side_scroll)
        return HitResult(
            killed=True,
            points=self.get_points_value(),
            explosion_size=max(12, int(self.w // 2)),
            sound=hit_sounds.EXPLOSION_ASTEROID,
            fragments=fragments,
        )

    def on_ship_contact(self, contact_x: float, contact_y: float):
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ASTEROID)

    def should_remove(self) -> bool:
        return self.dead

    def on_remove(self, entity_manager: "EntityManager") -> None:
        """Callback chamado pelo EntityManager antes de remover a entidade."""
        if hasattr(entity_manager, "meteor_pool"):
            entity_manager.meteor_pool.release(self)
