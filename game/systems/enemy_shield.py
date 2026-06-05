"""Escudo temporário reutilizável para inimigos.

Mecânica desacoplada e sem herança (§9): qualquer inimigo passa a ter escudo
só ganhando os atributos públicos `shield_hp` / `shield_max` — nada muda no
`on_hit` de cada tipo. A absorção acontece no roteador único de dano
(`CollisionPhysics.apply_hit`, §8) e o desenho num passe central
(`EntityManager.draw`, §3, sem efeitos colaterais). Concebido para o
`SapperDrone`, mas aplicável a qualquer entidade com geometria (`rect` ou
`x/y/w/h`).

Opt-in: classes dict-based recebem o escudo automaticamente (setattr cria o
atributo). Classes com `__slots__` precisam declarar `"shield_hp"` e
`"shield_max"` nos slots — `grant_shield` ignora silenciosamente quem não
suporta, então nunca quebra.
"""

from __future__ import annotations

import math
from typing import Any, Tuple

import pygame

# Ciano elétrico (mesma família do ELECTRIC_BLUE do CITY): membrana de energia.
SHIELD_COLOR: Tuple[int, int, int] = (90, 200, 255)

_RING_WIDTH: int = 2
_RADIUS_MARGIN: int = 4      # px de folga além do corpo
_RADIUS_SCALE: float = 1.18  # bolha um pouco maior que a entidade
_BASE_FILL_ALPHA: int = 55   # alpha da membrana com escudo cheio
_BASE_RING_ALPHA: int = 150  # alpha do anel com escudo cheio

# Cache de bolhas por (raio, bucket de intensidade). Poucos raios (um por tipo
# de inimigo) e 16 buckets → cache pequeno, zero alocação no hot path (§7).
_BUBBLE_CACHE: dict[Tuple[int, int], pygame.Surface] = {}


def grant_shield(enemy: Any, amount: float) -> None:
    """Concede escudo ao inimigo, refrescando para o maior valor (não empilha
    indefinidamente entre pulsos). `shield_max` guarda o pico para o fade
    visual. No-op seguro em entidades com `__slots__` que não declaram os
    atributos."""
    if amount <= 0.0:
        return
    new_hp = max(getattr(enemy, "shield_hp", 0.0), float(amount))
    try:
        enemy.shield_hp = new_hp
        enemy.shield_max = new_hp
    except (AttributeError, TypeError):
        pass  # entidade com slots sem opt-in: ignora


def absorb(enemy: Any, damage: int) -> int:
    """Consome o escudo antes do HP. Retorna o dano restante (>=0) destinado ao
    HP. Sem escudo, devolve o dano intacto."""
    shield = getattr(enemy, "shield_hp", 0.0)
    if shield <= 0.0 or damage <= 0:
        return damage
    if shield >= damage:
        enemy.shield_hp = shield - damage
        return 0
    enemy.shield_hp = 0.0
    return damage - int(shield)


def _enemy_bounds(enemy: Any) -> Tuple[float, float, float]:
    """Centro + raio visual da entidade (envolve o corpo, não a hitbox)."""
    rect = getattr(enemy, "rect", None)
    if isinstance(rect, pygame.Rect):
        return float(rect.centerx), float(rect.centery), max(rect.w, rect.h) * 0.5
    x = float(getattr(enemy, "x", 0.0))
    y = float(getattr(enemy, "y", 0.0))
    w = float(getattr(enemy, "w", 0.0))
    h = float(getattr(enemy, "h", 0.0))
    return x + w * 0.5, y + h * 0.5, max(w, h) * 0.5


def _get_bubble(radius: int, intensity: float) -> pygame.Surface:
    bucket = max(1, min(16, int(intensity * 16)))
    key = (radius, bucket)
    surf = _BUBBLE_CACHE.get(key)
    if surf is None:
        t = bucket / 16.0
        fill_a = int(_BASE_FILL_ALPHA * t)
        ring_a = int(_BASE_RING_ALPHA * t)
        size = radius * 2 + 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (radius + 1, radius + 1)
        if fill_a > 0:
            pygame.draw.circle(surf, (*SHIELD_COLOR, fill_a), center, radius)
        pygame.draw.circle(surf, (*SHIELD_COLOR, ring_a), center, radius, _RING_WIDTH)
        _BUBBLE_CACHE[key] = surf
    return surf


def draw_shield(surface: pygame.Surface, enemy: Any, phase: float = 0.0) -> None:
    """Desenha a bolha de escudo escalada ao corpo do inimigo. `phase` (um
    acumulador update-driven, ex.: `enemy.pulse`) dá um shimmer sutil; ausente,
    o escudo fica estável. Só lê estado (§3)."""
    shield = getattr(enemy, "shield_hp", 0.0)
    if shield <= 0.0:
        return
    cx, cy, body_r = _enemy_bounds(enemy)
    radius = int(body_r * _RADIUS_SCALE) + _RADIUS_MARGIN
    if radius < 4:
        return
    shield_max = getattr(enemy, "shield_max", shield) or shield
    frac = max(0.25, min(1.0, shield / shield_max))
    shimmer = 0.85 + 0.15 * math.sin(phase * 3.0)
    bubble = _get_bubble(radius, frac * shimmer)
    surface.blit(bubble, (int(cx - radius - 1), int(cy - radius - 1)))
