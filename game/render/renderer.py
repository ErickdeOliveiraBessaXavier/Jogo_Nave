import pygame
import random
from typing import TypedDict, Optional, TYPE_CHECKING
from pathlib import Path
from ..core import colors
from ..core.config import Config
from ..core.assets import get_font, get_image # Added get_image
from ..core.render_config import RenderConfig 

if TYPE_CHECKING:
    from ..entities.ship import Ship


class Star(TypedDict):
    x: int
    y: float
    speed: float
    size: int
    brightness: int


class CelestialBody(TypedDict):
    image: pygame.Surface
    x: float
    y: float
    speed: float
    scale: float


class CelestialManager:
    def __init__(self, w: int, h: int, n: int = RenderConfig.CELESTIAL_NUM_BODIES):
        self.w, self.h = w, h
        self.celestial_bodies: list[CelestialBody] = []
        self.image_files = self._load_image_files()
        # Initialize the pool with 'n' celestial bodies
        for _ in range(n):
            self.celestial_bodies.append(self._create_and_initialize_celestial_body())

    def _load_image_files(self) -> list[Path]:
        image_dir = Path(__file__).resolve().parents[1] / "assets" / "images"
        return list(image_dir.glob("*.png"))

    def _generate_scaled_image(self, image_path: Path, scale: float) -> pygame.Surface:
        """Loads, scales, and sets alpha for a celestial body image."""
        original_image = get_image(image_path)

        width = int(original_image.get_width() * scale)
        height = int(original_image.get_height() * scale)
        image = pygame.transform.scale(original_image, (width, height))

        # Opacity based on size
        alpha = int(RenderConfig.CELESTIAL_ALPHA_MIN + (scale - RenderConfig.CELESTIAL_SCALE_MIN) * (RenderConfig.CELESTIAL_ALPHA_MAX - RenderConfig.CELESTIAL_ALPHA_MIN) / (RenderConfig.CELESTIAL_SCALE_MAX - RenderConfig.CELESTIAL_SCALE_MIN))
        image.set_alpha(alpha)
        return image

    def _get_random_x_position(self, width: int, current_body: Optional[CelestialBody] = None) -> float:
        """Generates a random x-position ensuring no overlap with existing bodies."""
        new_x = 0
        max_attempts = 10
        for _ in range(max_attempts):
            test_x = random.uniform(0, self.w - width)
            overlap = False
            for existing_body in self.celestial_bodies:
                if existing_body is current_body: # Don't check overlap with itself
                    continue
                min_gap = RenderConfig.CELESTIAL_MIN_GAP
                if (test_x < existing_body["x"] + existing_body["image"].get_width() + min_gap and
                    test_x + width + min_gap > existing_body["x"]):
                    overlap = True
                    break
            if not overlap:
                new_x = test_x
                break
        return new_x

    def _create_and_initialize_celestial_body(self, y_position: Optional[float] = None) -> CelestialBody:
        """Creates a new celestial body and initializes its properties."""
        image_path = random.choice(self.image_files)
        
        scale = random.uniform(RenderConfig.CELESTIAL_SCALE_MIN, RenderConfig.CELESTIAL_SCALE_MAX)
        image = self._generate_scaled_image(image_path, scale)

        x = self._get_random_x_position(image.get_width())

        body: CelestialBody = {
            "image": image,
            "x": x,
            "y": y_position if y_position is not None else random.uniform(0, self.h),
            "speed": random.uniform(RenderConfig.CELESTIAL_SPEED_BASE_MIN, RenderConfig.CELESTIAL_SPEED_BASE_MAX) * scale + RenderConfig.CELESTIAL_SPEED_OFFSET,
            "scale": scale,
        }
        return body

    def _reset_celestial_body(self, body: CelestialBody, y_position: Optional[float] = None):
        """Resets the properties of an existing celestial body."""
        image_path = random.choice(self.image_files)
        
        scale = random.uniform(RenderConfig.CELESTIAL_SCALE_MIN, RenderConfig.CELESTIAL_SCALE_MAX)
        image = self._generate_scaled_image(image_path, scale)

        body["image"] = image
        body["x"] = self._get_random_x_position(image.get_width(), current_body=body) # Pass current_body for overlap check
        body["y"] = y_position if y_position is not None else random.uniform(0, self.h)
        body["speed"] = random.uniform(RenderConfig.CELESTIAL_SPEED_BASE_MIN, RenderConfig.CELESTIAL_SPEED_BASE_MAX) * scale + RenderConfig.CELESTIAL_SPEED_OFFSET
        body["scale"] = scale

    def update(self, dt: float, speed_multiplier: float = 1.0):
        for body in self.celestial_bodies:
            body["y"] += body["speed"] * dt * speed_multiplier
            if body["y"] > self.h:
                # Reset the existing body instead of creating a new one
                self._reset_celestial_body(body, y_position=random.uniform(self.h * RenderConfig.CELESTIAL_RESET_Y_MIN_MULTIPLIER, self.h * RenderConfig.CELESTIAL_RESET_Y_MAX_MULTIPLIER))

    def draw(self, surface: pygame.Surface):
        for body in self.celestial_bodies:
            surface.blit(body["image"], (round(body["x"]), round(body["y"])))


class StarField:
    def __init__(self, w: int, h: int, n: int = RenderConfig.STARFIELD_NUM_STARS):
        self.w, self.h = w, h
        self.stars: list[Star] = []
        # Initialize the pool with 'n' stars
        for _ in range(n):
            self.stars.append(self._create_and_initialize_star())

    def _create_and_initialize_star(self) -> Star:
        """Creates and initializes a new star."""
        return Star({
            "x": random.randint(0, self.w),
            "y": random.randint(0, self.h),
            "speed": random.uniform(RenderConfig.STARFIELD_SPEED_MIN, RenderConfig.STARFIELD_SPEED_MAX),
            "size": random.choice([1, 1, 2, 3]),
            "brightness": random.randint(RenderConfig.STARFIELD_BRIGHTNESS_MIN, RenderConfig.STARFIELD_BRIGHTNESS_MAX),
        })

    def _reset_star(self, star: Star):
        """Resets the properties of an existing star."""
        star["x"] = random.randint(0, self.w)
        star["y"] = -star["size"]  # Start above the screen
        star["speed"] = random.uniform(RenderConfig.STARFIELD_SPEED_MIN, RenderConfig.STARFIELD_SPEED_MAX)
        star["size"] = random.choice([1, 1, 2, 3])
        star["brightness"] = random.randint(RenderConfig.STARFIELD_BRIGHTNESS_MIN, RenderConfig.STARFIELD_BRIGHTNESS_MAX)

    def update(self, dt: float, speed_multiplier: float = 1.0):
        for s in self.stars:
            s["y"] += s["speed"] * dt * speed_multiplier
            if s["y"] > self.h:
                # Reset the existing star instead of creating a new one
                self._reset_star(s)

    def draw(self, surface: pygame.Surface):
        for s in self.stars:
            c = (s["brightness"], s["brightness"], s["brightness"])
            center_x, center_y = int(s["x"]), int(s["y"])
            half_size = s["size"]
            
            # Draw a diamond-shaped star
            points = [
                (center_x, center_y - half_size),  # Top
                (center_x + half_size, center_y),  # Right
                (center_x, center_y + half_size),  # Bottom
                (center_x - half_size, center_y),  # Left
            ]
            pygame.draw.polygon(surface, c, points)



class Renderer:
    def __init__(self):
        self.font_small = get_font(12)
        self.font_medium = get_font(24)
        self.font_large = get_font(32)
        self.starfield = StarField(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
        self.celestial_manager = CelestialManager(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT, n=RenderConfig.CELESTIAL_NUM_BODIES)

    def background(
        self, surface: pygame.Surface, dt: float, speed_multiplier: float = 1.0
    ):
        surface.fill(colors.BLACK)
        self.starfield.update(dt, speed_multiplier)
        self.celestial_manager.update(dt, speed_multiplier)
        self.starfield.draw(surface)
        self.celestial_manager.draw(surface)

    def hud(
        self,
        surface: pygame.Surface,
        score: int,
        lives: int,
        enemies_destroyed: int,
        ship: Optional["Ship"] = None,
        level_number: int = 1,
    ):
        s = self.font_medium.render(f"Pontos: {score}", True, colors.WHITE)
        l = self.font_medium.render(f"Vidas: {lives}", True, colors.WHITE)
        lvl = self.font_medium.render(f"Fase: {level_number}", True, colors.WHITE)
        e = self.font_small.render(f"Inimigos: {enemies_destroyed}", True, colors.WHITE)

        surface.blit(s, (10, 10))
        surface.blit(l, (Config.SCREEN_WIDTH - l.get_width() - 10, 10))
        surface.blit(lvl, (10, 44))
        surface.blit(e, (10, 78))

        # --- efeitos ativos (se ship for informado) ---
        if ship is not None:
            y = 110

            def line(txt: str, color: tuple[int, int, int] = colors.GREEN):
                nonlocal y
                t = self.font_small.render(txt, True, color)
                surface.blit(t, (10, y))
                y += 18

            invuln_s = ship.get_invulnerable_time()
            ds_s = ship.get_double_shot_time()
            sp_s = ship.get_speed_boost_time()

            if invuln_s > 0:
                line(f"[S] Escudo: {invuln_s:.1f}s", colors.BLUE)
            if ds_s > 0:
                line(f"[2X] Tiro Duplo: {ds_s:.1f}s", colors.GREEN)
            if sp_s > 0:
                line(f"[V] Velocidade: {sp_s:.1f}s", colors.YELLOW)

    def overlay(self, surface: pygame.Surface, title: str, subtitle: str = ""):
        overlay = pygame.Surface(
            (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))
        t = self.font_large.render(title, True, colors.YELLOW)
        rect = t.get_rect(
            center=(Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 2 - 40)
        )
        surface.blit(t, rect)
        if subtitle:
            s = self.font_medium.render(subtitle, True, colors.WHITE)
            rect = s.get_rect(
                center=(Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 2 + 20)
            )
            surface.blit(s, rect)

    def preparation(self, surface: pygame.Surface, remaining: float):
        # Usar fonte do warning (60pt)
        warning_font = get_font(Config.WARNING_FONT_SIZE)

        # contador
        ct = warning_font.render(f"{int(remaining) + 1}", True, colors.RED)
        crect = ct.get_rect(
            center=(Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT // 2)
        )
        surface.blit(ct, crect)

    def effects_on_ship(self, surface: pygame.Surface, ship: "Ship"):
        """Desenha efeitos visuais na nave (ex.: halo de escudo)."""
        if ship.is_invulnerable:
            cx = int(ship.x + ship.w / 2)
            cy = int(ship.y + ship.h / 2)
            radius = max(ship.w, ship.h) // 2 + 6

            halo = pygame.Surface((radius * 2 + 6, radius * 2 + 6), pygame.SRCALPHA)
            pygame.draw.circle(
                halo, (0, 120, 255, 120), (radius + 3, radius + 3), radius, width=3
            )
            surface.blit(halo, (cx - radius - 3, cy - radius - 3))

