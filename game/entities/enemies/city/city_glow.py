"""Glow radial aditivo compartilhado do bioma CITY.

Sprite de halo cacheado por (raio, cor bucketizada), reutilizado por todos os
inimigos do tema cidade (`CityDrone`, `FusedDrone`, ...). Vive em módulo próprio
para que nenhuma classe precise alcançar o privado de outra para desenhar o
mesmo glow (§1) — é uma utilidade pura (entra raio+cor, sai surface), sem estado
de domínio acoplado.
"""

from __future__ import annotations

import pygame

from .city_palette import RGB

# Cache (raio, cor bucketizada) → surface. Module-level: uma única tabela para
# todo o tema, esvaziada por inteiro ao atingir o limite (LRU não compensa aqui).
_glow_cache: dict[tuple[int, RGB], pygame.Surface] = {}
_GLOW_CACHE_LIMIT = 192


def get_glow(radius: int, color: RGB) -> pygame.Surface:
    """Sprite de glow radial aditivo, cacheado por (raio, cor bucketizada)."""
    # Bucketiza a cor em passos de 24 para limitar variações no cache.
    bucket = (color[0] // 24 * 24, color[1] // 24 * 24, color[2] // 24 * 24)
    key = (radius, bucket)
    cached = _glow_cache.get(key)
    if cached is not None:
        return cached

    diameter = max(2, radius * 2)
    glow = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
    # Algumas camadas concêntricas → halo suave (alpha decrescente).
    layers = 4
    for i in range(layers, 0, -1):
        r = max(1, int(radius * i / layers))
        alpha = int(120 * (i / layers) ** 2)
        pygame.draw.circle(glow, (*bucket, alpha), (radius, radius), r)

    if len(_glow_cache) >= _GLOW_CACHE_LIMIT:
        _glow_cache.clear()
    _glow_cache[key] = glow
    return glow
