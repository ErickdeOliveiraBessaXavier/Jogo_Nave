"""Gera a capa do jogo: nome centralizado sobre um fundo starfield.

Reutiliza o StarField real do jogo (mesma estetica do gameplay) e a fonte
pixelada PressStart2P. Saida: cover_pixel_patrol.png na raiz do projeto.

Uso:
    python scripts/generate_cover.py
"""

import math
import os
import random
import sys
from pathlib import Path

# Headless: nao precisa de janela real.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402

from game.render.backgrounds.starfield import CelestialManager, StarField  # noqa: E402

# --- Configuracao da capa ---
WIDTH, HEIGHT = 1280, 1024          # proporcao ~5:4 (boa para a capa do itch.io)
TITLE = "PIXEL PATROL"
SUBTITLE = "SHOOT - SURVIVE - PATROL"
OUTPUT = ROOT / "cover_pixel_patrol.png"
FONT_PATH = ROOT / "game" / "assets" / "fonts" / "PressStart2P-Regular.ttf"


def vertical_gradient(w: int, h: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> pygame.Surface:
    """Gradiente vertical suave para o fundo do espaco."""
    surf = pygame.Surface((w, h))
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        pygame.draw.line(surf, (r, g, b), (0, y), (w, y))
    return surf


def radial_glow(radius: int, color: tuple[int, int, int], max_alpha: int) -> pygame.Surface:
    """Brilho radial (nebula/halo) com alpha caindo do centro para a borda."""
    size = radius * 2
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    for r in range(radius, 0, -1):
        t = r / radius
        alpha = int(max_alpha * (1 - t) ** 2)
        pygame.draw.circle(surf, (*color, alpha), (radius, radius), r)
    return surf


def render_title(font: pygame.font.Font, text: str) -> pygame.Surface:
    """Renderiza o titulo com contorno escuro + glow ciano (estilo neon)."""
    main_color = (235, 245, 255)
    glow_color = (40, 200, 255)
    outline_color = (10, 20, 40)

    base = font.render(text, True, main_color)
    tw, th = base.get_size()
    pad = 24
    surf = pygame.Surface((tw + pad * 2, th + pad * 2), pygame.SRCALPHA)
    cx, cy = pad, pad

    # Glow: varias copias borradas (offsets em circulo)
    for radius in (10, 7, 4):
        glow = font.render(text, True, glow_color)
        glow.set_alpha(60)
        for ang in range(0, 360, 45):
            dx = int(math.cos(math.radians(ang)) * radius)
            dy = int(math.sin(math.radians(ang)) * radius)
            surf.blit(glow, (cx + dx, cy + dy))

    # Contorno nitido (8 direcoes)
    outline = font.render(text, True, outline_color)
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, -2), (-2, 2), (2, 2)):
        surf.blit(outline, (cx + dx, cy + dy))

    # Texto principal
    surf.blit(base, (cx, cy))
    return surf


def main() -> None:
    random.seed(7)  # composicao reproduzivel
    pygame.init()
    pygame.font.init()
    pygame.display.set_mode((1, 1))  # contexto de video p/ convert_alpha

    canvas = vertical_gradient(WIDTH, HEIGHT, (6, 8, 22), (16, 10, 30))

    # Nebulas de fundo (brilhos suaves)
    for color, (fx, fy), rad, alpha in (
        ((30, 60, 140), (0.25, 0.30), 520, 70),
        ((120, 40, 110), (0.78, 0.68), 460, 60),
        ((20, 90, 90), (0.60, 0.20), 360, 45),
    ):
        glow = radial_glow(rad, color, alpha)
        canvas.blit(glow, (int(WIDTH * fx) - rad, int(HEIGHT * fy) - rad))

    # Starfield real do jogo + corpos celestes (planetas)
    starfield = StarField(WIDTH, HEIGHT, n=420)
    celestial = CelestialManager(WIDTH, HEIGHT, n=4)
    # Avanca alguns frames para variar fase/pulsacao das estrelas
    for _ in range(30):
        starfield.update(0.05)
        celestial.update(0.05, allow_spawning=False)
    celestial.draw(canvas)
    starfield.draw(canvas)

    # Titulo centralizado
    title_font = pygame.font.Font(str(FONT_PATH), 84)
    title = render_title(title_font, TITLE)
    tx = (WIDTH - title.get_width()) // 2
    ty = int(HEIGHT * 0.42) - title.get_height() // 2
    canvas.blit(title, (tx, ty))

    # Subtitulo
    sub_font = pygame.font.Font(str(FONT_PATH), 22)
    sub = sub_font.render(SUBTITLE, True, (150, 180, 210))
    sx = (WIDTH - sub.get_width()) // 2
    sy = ty + title.get_height() + 18
    canvas.blit(sub, (sx, sy))

    pygame.image.save(canvas, str(OUTPUT))
    print(f"Capa gerada: {OUTPUT}  ({WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
