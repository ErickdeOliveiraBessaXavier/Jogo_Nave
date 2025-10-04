import pygame
import random
from typing import TypedDict, Optional, TYPE_CHECKING
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

    def update(self, dt: float):
        for s in self.stars:
            s["y"] += s["speed"] * dt
            if s["y"] > self.h:
                s["y"] = -s["size"]
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

    def background(self, surface: pygame.Surface, dt: float):
        surface.fill(colors.BLACK)
        self.starfield.update(dt)
        self.starfield.draw(surface)

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
        # tÃ­tulo e instruÃ§Ãµes resumidas
        right = [
            "CONTROLES:",
            "A/D ou Setas - Mover",
            "ESPACO - Atirar",
            "P - Pausar | ESC - Sair",
            "",
            "METEOROS:",
            "Pequenos: rapidos (menos pontos)",
            "Grandes: lentos (mais pontos)",
            "",
            "POWER-UPS:",
            "[+] Vida extra",
            "[S] Escudo temporario",
            "[2X] Tiro duplo",
            "[V] Velocidade aumentada",
            "[*] Pontos bonus",
        ]
        x, y = Config.SCREEN_WIDTH - 400, 20
        for i, line in enumerate(right):
            color = colors.WHITE
            if line in ("CONTROLES:", "METEOROS:", "POWER-UPS:"):
                if line == "CONTROLES:":
                    color = colors.GREEN
                elif line == "METEOROS:":
                    color = colors.YELLOW
                elif line == "POWER-UPS:":
                    color = colors.CYAN
            if not line:
                continue
            txt = self.font_small.render(line, True, color)
            surface.blit(txt, (x, y + i * 18))

        # contador
        ct = self.font_large.render(f"{int(remaining) + 1}", True, colors.RED)
        crect = ct.get_rect(
            center=(Config.SCREEN_WIDTH // 2, Config.SCREEN_HEIGHT - 100)
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
