"""Visual do tiro TELEGUIADO: o '+' pixelizado que gira.

Paleta, cache de frames e desenho do modificador — nada de física. A perseguição
(alvo, curva, velocidade) continua na `Bullet`, que é onde ela pertence: as
constantes de VELOCIDADE do teleguiado ficaram lá de propósito, e só os frames
vieram para cá.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Tuple

import pygame

from ....core import colors
from ....core.player_tint import player_shot_color
from ....core.upgrades_config import giant_visual_scale

if TYPE_CHECKING:
    from ..bullet import Bullet


# Cache estático de frames pré-rotacionados do tiro teleguiado.
# 24 frames = 15° por frame; suficiente para 360°/s a 60fps.
# Cada frame é uma surface pequena (~20x20). Total ~10 KB de memória.
# Chave: (player_index, explosive, scale_key) — `scale_key` distingue o tiro
# normal do Giant Shot (combinação teleguiado + tiro aumentado), quantizado
# em 1 casa para não estourar o cache com floats quase iguais.
_HOMING_NUM_FRAMES: int = 24
_HOMING_FRAMES: Dict[Tuple[int, bool, float], List[pygame.Surface]] = {}


def _build_homing_base_surface(
    with_explosive_ring: bool, player_index: int
) -> pygame.Surface:
    """Constrói a sprite base do '+' (sem rotação). Tamanho 20x20 garante
    que cabe rotacionado em qualquer ângulo sem cortes."""
    size = 6
    surf_size = 20
    center = surf_size // 2
    surf = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)

    color_bright = player_shot_color(colors.GREEN, player_index)
    color_dim = player_shot_color((0, 200, 0), player_index)

    # Braços do '+'
    for i in range(-size, size + 1):
        color = color_bright if abs(i) < 2 else color_dim
        surf.set_at((center + i, center), color)
        surf.set_at((center, center + i), color)

    # Centro super brilhante (radius 2 cobre o miolo)
    pygame.draw.circle(
        surf, player_shot_color((150, 255, 150), player_index), (center, center), 2
    )

    # Aro do combo homing+explosive
    if with_explosive_ring:
        pygame.draw.circle(
            surf, player_shot_color((255, 80, 0), player_index), (center, center), 9, 1
        )

    return surf


def _get_homing_frames(
    player_index: int, explosive: bool, scale: float = 1.0
) -> List[pygame.Surface]:
    """Frames rotacionados do teleguiado, memoizados por (jogador, explosivo, escala).

    Renderizados sob demanda no primeiro draw — não no import — para garantir
    que o display já esteja inicializado quando o convert_alpha rodar.

    `scale` (> 1.0 quando o Giant Shot está ativo) engorda a sprite para casar
    com o hitbox aumentado, tornando visível a combinação teleguiado + tiro
    grande. A escala é aplicada na surface base ANTES da rotação, para as bordas
    rotacionadas saírem mais suaves.
    """
    scale_key = round(scale, 1)
    key = (player_index, explosive, scale_key)
    frames = _HOMING_FRAMES.get(key)
    if frames is not None:
        return frames

    base = _build_homing_base_surface(explosive, player_index)
    if scale_key != 1.0:
        bw, bh = base.get_size()
        base = pygame.transform.scale(
            base, (max(1, round(bw * scale_key)), max(1, round(bh * scale_key)))
        )
    step = 360.0 / _HOMING_NUM_FRAMES
    frames = []
    for i in range(_HOMING_NUM_FRAMES):
        frame = pygame.transform.rotate(base, -i * step)
        try:
            frame = frame.convert_alpha()
        except pygame.error:
            pass
        frames.append(frame)
    _HOMING_FRAMES[key] = frames
    return frames



def draw(bullet: "Bullet", surface: pygame.Surface) -> None:
    """Desenha o tiro teleguiado como um '+' pixelizado que gira.
    Usa frames pré-rotacionados — 1 blit em vez de 26 draw.circle."""
    frames = _get_homing_frames(
        bullet.player_index,
        bullet.explosive,
        giant_visual_scale(bullet.size_multiplier),
    )
    idx = int(bullet.rotation_angle * _HOMING_NUM_FRAMES / 360.0) % _HOMING_NUM_FRAMES
    frame = frames[idx]
    fw, fh = frame.get_size()
    center_x = bullet.x + bullet.w / 2
    center_y = bullet.y + bullet.h / 2
    surface.blit(frame, (int(center_x - fw / 2), int(center_y - fh / 2)))
