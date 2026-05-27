from __future__ import annotations

import sys
from pathlib import Path

import pygame

# Adiciona o diretório raiz ao path para permitir importações do pacote 'game'
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game.entities.satellite_pixel_map import PIXEL_MAP, C


def export_png(out_path: Path, scale: int) -> None:
    rows = len(PIXEL_MAP)
    cols = len(PIXEL_MAP[0])
    # Cria uma superfície com canal alpha (transparência)
    surface = pygame.Surface((cols * scale, rows * scale), pygame.SRCALPHA)

    for r, row in enumerate(PIXEL_MAP):
        for c, key in enumerate(row):
            if key is None:
                continue
            color = C.get(key)
            if color is None:
                continue
            # Desenha o pixel escalonado
            pygame.draw.rect(surface, color, (c * scale, r * scale, scale, scale))

    pygame.image.save(surface, str(out_path))
    print(f"PNG salvo em: {out_path}")


def main() -> None:
    # Escala de cada "pixel" do mapa
    scale = 20  # Ajuste conforme necessário
    out_dir = Path("Output")
    out_dir.mkdir(parents=True, exist_ok=True)

    png_path = out_dir / "satellite_pixel_map.png"
    export_png(png_path, scale)


if __name__ == "__main__":
    main()
