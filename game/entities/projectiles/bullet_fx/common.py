"""Peças de desenho compartilhadas entre os efeitos de tiro."""

from __future__ import annotations

import math

import pygame


def breathing_rect(rect: pygame.Rect) -> pygame.Rect:
    """Rect visual do Giant Shot pulsando ±12% em torno do centro.

    Retorna uma CÓPIA inflada (``rect.inflate`` não muta o original), então o
    hitbox em ``self._rect`` fica intacto — é só respiração cosmética. Ritmo
    lento, alinhado ao halo âmbar do gigante. A amplitude é generosa (±12%)
    porque, arredondada em pixels, uma dose menor sumiria nos tiros pequenos.
    """
    factor = 0.12 * math.sin(pygame.time.get_ticks() * 0.005)
    return rect.inflate(round(rect.width * factor), round(rect.height * factor))
