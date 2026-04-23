from __future__ import annotations

from pathlib import Path
import sys

import pygame

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game.entities.mountain_serpent_pixel_map import C, PIXEL_MAP


def export_svg(out_path: Path, scale: int) -> None:
    rows = len(PIXEL_MAP)
    cols = len(PIXEL_MAP[0])
    width = cols * scale
    height = rows * scale

    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" shape-rendering="crispEdges">',
        f'<rect width="{width}" height="{height}" fill="transparent"/>',
    ]

    for r, row in enumerate(PIXEL_MAP):
        for c, key in enumerate(row):
            if key is None:
                continue
            color = C.get(key)
            if color is None:
                continue
            x = c * scale
            y = r * scale
            fill = f"rgb({color[0]},{color[1]},{color[2]})"
            lines.append(
                f'<rect x="{x}" y="{y}" width="{scale}" height="{scale}" fill="{fill}"/>'
            )

    lines.append("</svg>")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def export_png(out_path: Path, scale: int) -> None:
    rows = len(PIXEL_MAP)
    cols = len(PIXEL_MAP[0])
    surface = pygame.Surface((cols * scale, rows * scale), pygame.SRCALPHA)

    for r, row in enumerate(PIXEL_MAP):
        for c, key in enumerate(row):
            if key is None:
                continue
            color = C.get(key)
            if color is None:
                continue
            pygame.draw.rect(surface, color, (c * scale, r * scale, scale, scale))

    pygame.image.save(surface, str(out_path))


def main() -> None:
    scale = 18
    out_dir = Path("Output")
    out_dir.mkdir(parents=True, exist_ok=True)

    svg_path = out_dir / "mountain_serpent_pixel_map.svg"
    png_path = out_dir / "mountain_serpent_pixel_map.png"

    export_svg(svg_path, scale)
    export_png(png_path, scale)

    print(f"SVG salvo em: {svg_path}")
    print(f"PNG salvo em: {png_path}")


if __name__ == "__main__":
    main()
