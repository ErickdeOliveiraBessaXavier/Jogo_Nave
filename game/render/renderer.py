import pygame
import random
from typing import TypedDict, Optional, TYPE_CHECKING
from pathlib import Path
from ..core import colors
from ..core.config import Config
from ..core.assets import get_font

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
    def __init__(self, w: int, h: int, n: int = 2): # Changed n from 3 to 2
        self.w, self.h = w, h
        self.celestial_bodies: list[CelestialBody] = []
        self.image_files = self._load_image_files()
        for _ in range(n):
            self.celestial_bodies.append(self._create_celestial_body())

    def _load_image_files(self) -> list[Path]:
        image_dir = Path(__file__).resolve().parents[1] / "assets" / "images"
        return list(image_dir.glob("*.png"))

    def _create_celestial_body(self, y_position: Optional[float] = None) -> CelestialBody:
        image_path = random.choice(self.image_files)
        original_image = pygame.image.load(image_path).convert_alpha()

        scale = random.uniform(0.1, 0.6) # Reduced max scale from 1.0 to 0.6
        width = int(original_image.get_width() * scale)
        height = int(original_image.get_height() * scale)
        image = pygame.transform.scale(original_image, (width, height))

        # Opacity based on size
        alpha = int(50 + (scale - 0.1) * (255 - 50) / (0.6 - 0.1)) # Adjusted denominator for new max scale
        image.set_alpha(alpha)

        # Logic to ensure bodies don't spawn too close horizontally
        new_x = 0
        max_attempts = 10 # Prevent infinite loops
        for _ in range(max_attempts):
            new_x = random.uniform(0, self.w - width)
            overlap = False
            for existing_body in self.celestial_bodies:
                # Check for horizontal overlap, considering a minimum gap
                min_gap = 50 # Minimum horizontal gap between bodies
                if (new_x < existing_body["x"] + existing_body["image"].get_width() + min_gap and
                    new_x + width + min_gap > existing_body["x"]):
                    overlap = True
                    break
            if not overlap:
                break
        # If after max_attempts, still overlaps, just use the last generated new_x (it's rare with n=2)


        return {
            "image": image,
            "x": new_x,
            "y": y_position if y_position is not None else random.uniform(0, self.h),
            "speed": random.uniform(50, 150) * scale + 20,
            "scale": scale,
        }

    def update(self, dt: float, speed_multiplier: float = 1.0):
        for body in self.celestial_bodies:
            body["y"] += body["speed"] * dt * speed_multiplier
            if body["y"] > self.h:
                index = self.celestial_bodies.index(body)
                # Ensure objects start further above the screen to prevent "pop" effect
                self.celestial_bodies[index] = self._create_celestial_body(y_position=random.uniform(-self.h * 1.5, -self.h * 0.5))

    def draw(self, surface: pygame.Surface):
        for body in self.celestial_bodies:
            surface.blit(body["image"], (round(body["x"]), round(body["y"])))


class StarField:
    def __init__(self, w: int, h: int, n: int = 60):
        self.w, self.h = w, h
        self.stars: list[Star] = []
        for _ in range(n):
            self.stars.append(
                {
                    "x": random.randint(0, w),
                    "y": random.randint(0, h),
                    "speed": random.uniform(30, 150),  # px/s
                    "size": random.choice([1, 1, 2, 3]),
                    "brightness": random.randint(120, 255),
                }
            )

    def update(self, dt: float, speed_multiplier: float = 1.0):
        for s in self.stars:
            s["y"] += s["speed"] * dt * speed_multiplier
            if s["y"] > self.h:
                # Reposicionar estrela no topo (acima da tela)
                s["y"] = -s["size"]  # Começa logo acima da tela
                s["x"] = random.randint(0, self.w)

    def draw(self, surface: pygame.Surface):
        for s in self.stars:
            c = (s["brightness"], s["brightness"], s["brightness"])
            pygame.draw.circle(surface, c, (int(s["x"]), int(s["y"])), s["size"])


class Renderer:
    def __init__(self):
        self.font_small = get_font(12)
        self.font_medium = get_font(24)
        self.font_large = get_font(32)
        self.starfield = StarField(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
        self.celestial_manager = CelestialManager(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT, n=2)

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

            invuln_s = getattr(ship, "invuln", 0) / 1000.0
            ds_s = getattr(ship, "double_shot_timer", 0)
            sp_s = getattr(ship, "speed_boost_timer", 0)

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
        invuln = getattr(ship, "invuln", 0)
        if invuln > 0:
            cx = int(ship.x + ship.w / 2)
            cy = int(ship.y + ship.h / 2)
            radius = max(ship.w, ship.h) // 2 + 6

            halo = pygame.Surface((radius * 2 + 6, radius * 2 + 6), pygame.SRCALPHA)
            pygame.draw.circle(
                halo, (0, 120, 255, 120), (radius + 3, radius + 3), radius, width=3
            )
            surface.blit(halo, (cx - radius - 3, cy - radius - 3))
