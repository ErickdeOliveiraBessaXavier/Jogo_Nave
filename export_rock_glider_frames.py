"""
Exporta frames animados do RockGlider para todas as combinações de tamanho e cor.

Uso:
    python export_rock_glider_frames.py

Saída:
    rock_glider_exports/
        size15_default/
            frame_00.png
            frame_01.png
            ...
            frame_15.png
        size15_blue/
            frame_00.png
            ...
        ...
        size22_purple/
            frame_00.png
            ...
"""

import os

import pygame

# ---------------------------------------------------------------------------
# Configurações de exportação
# ---------------------------------------------------------------------------
FRAME_COUNT = 16  # frames por variante
RING_SPEED = 2.3  # deve ser igual ao valor hardcoded no draw()
DT = 2.0 / (RING_SPEED * FRAME_COUNT)  # 2 ciclos completos de thruster
PAD = 10  # margem extra ao redor do sprite
OUTPUT_DIR = "rock_glider_exports"

SIZES = [12, 16, 20, 25, 30, 38, 45]  # range do jogo: 12–45 (normal spawn)

COLOR_VARIANTS: dict[str, dict[str, tuple[int, int, int]]] = {
    "default": {
        "body": (30, 30, 30),
        "eye": (255, 140, 0),
        "thruster_hot": (255, 220, 120),
        "thruster_mid": (255, 120, 70),
        "thruster_cool": (210, 60, 50),
        "rock": (101, 67, 33),
    },
    "blue": {
        "body": (18, 28, 72),
        "eye": (0, 210, 255),
        "thruster_hot": (180, 230, 255),
        "thruster_mid": (90, 155, 255),
        "thruster_cool": (45, 75, 210),
        "rock": (55, 80, 165),
    },
    "red": {
        "body": (72, 14, 14),
        "eye": (255, 230, 50),
        "thruster_hot": (255, 245, 180),
        "thruster_mid": (255, 155, 35),
        "thruster_cool": (205, 45, 45),
        "rock": (155, 48, 38),
    },
    "green": {
        "body": (14, 52, 18),
        "eye": (145, 255, 95),
        "thruster_hot": (195, 255, 170),
        "thruster_mid": (95, 205, 95),
        "thruster_cool": (35, 135, 55),
        "rock": (55, 105, 38),
    },
    "purple": {
        "body": (42, 14, 62),
        "eye": (225, 100, 255),
        "thruster_hot": (235, 185, 255),
        "thruster_mid": (172, 98, 245),
        "thruster_cool": (102, 38, 185),
        "rock": (102, 58, 145),
    },
}
# ---------------------------------------------------------------------------


def _apply_colors(glider, palette: dict[str, tuple[int, int, int]]) -> None:
    glider.color_body = palette["body"]
    glider.color_eye = palette["eye"]
    glider.color_thruster_hot = palette["thruster_hot"]
    glider.color_thruster_mid = palette["thruster_mid"]
    glider.color_thruster_cool = palette["thruster_cool"]
    glider._rock_color = palette["rock"]
    # Regenerar superfícies cacheadas com as novas cores
    glider._rebuild_draw_cache()


def _canvas_size(glider) -> tuple[int, int, int, int]:
    """Retorna (canvas_w, canvas_h, glider_x, glider_y) com padding."""
    rs = glider._rock_surface
    bs = glider._bot_surface
    rox, roy = glider._rock_surface_offset_x, glider._rock_surface_offset_y
    box, boy = glider._bot_surface_offset_x, glider._bot_surface_offset_y

    local_min_x = min(rox, box)
    local_min_y = min(roy, boy)
    local_max_x = max(rox + rs.get_width(), box + bs.get_width())
    local_max_y = max(
        roy + rs.get_height(), boy + bs.get_height() + 14
    )  # +14 thruster drop

    w = local_max_x - local_min_x + PAD * 2
    h = local_max_y - local_min_y + PAD * 2
    # Posição do glider dentro do canvas (origem local → canvas)
    gx = -local_min_x + PAD
    gy = -local_min_y + PAD
    return w, h, gx, gy


def export_variant(glider, size: int, name: str) -> None:
    cw, ch, gx, gy = _canvas_size(glider)

    folder = os.path.join(OUTPUT_DIR, f"size{size:02d}_{name}")
    os.makedirs(folder, exist_ok=True)

    for i in range(FRAME_COUNT):
        canvas = pygame.Surface((cw, ch), pygame.SRCALPHA)
        glider.x = float(gx)
        glider.y = float(gy)
        glider.draw(canvas)
        pygame.image.save(canvas, os.path.join(folder, f"rock_glider_{i:02d}.png"))
        glider.update(DT)
        glider.vx = 0.0

    print(f"  {folder}/  ({FRAME_COUNT} frames de {cw}x{ch})")


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1), pygame.NOFRAME)

    from game.entities.rock_glider import RockGlider

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(
        f"Exportando {len(SIZES)} tamanhos × {len(COLOR_VARIANTS)} cores "
        f"= {len(SIZES) * len(COLOR_VARIANTS)} sprite sheets\n"
    )

    for size in SIZES:
        for variant_name, palette in COLOR_VARIANTS.items():
            glider = RockGlider(size=size, x=0.0, y=0.0)
            glider.vx = 0.0
            glider.vy = 0.0
            _apply_colors(glider, palette)
            export_variant(glider, size, variant_name)

    print(f"\nPronto. Pastas em: {OUTPUT_DIR}/")
    pygame.quit()


if __name__ == "__main__":
    main()
