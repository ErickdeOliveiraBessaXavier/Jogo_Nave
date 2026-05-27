"""aiming.py — rotação suave de sprite na direção da mira.

Lógica única compartilhada pelas escoltas autônomas (`Wingman`, `MiniShip`)
que giram o sprite para apontar ao alvo. Centraliza a convenção de ângulo do
projeto e a interpolação suave, evitando que cada entidade reimplemente (e
divirja) o mesmo `atan2`/wrap-around.

Convenção (pygame): 0° aponta à direita e os ângulos crescem no sentido
anti-horário. Como `dy` cresce para baixo na tela, a conversão usa `-atan2`.
Os sprites do projeto apontam para cima por padrão, então o desenho subtrai
90° (`ANGLE_UP`).

Funções puras: não mutam entidades nem alocam estado.
"""

from __future__ import annotations

import math

import pygame

# Orientações de referência em graus (mesma convenção de `angle_to`).
ANGLE_RIGHT = 0.0
ANGLE_UP = 90.0

# Velocidade padrão de giro do sprite (quão rápido `current` alcança `target`).
DEFAULT_TURN_RATE = 10.0


def angle_to(dx: float, dy: float) -> float:
    """Ângulo (graus) da direção de tela (dx, dy) na convenção do pygame."""
    return math.degrees(-math.atan2(dy, dx))


def approach_angle(current: float, target: float, dt: float,
                   rate: float = DEFAULT_TURN_RATE) -> float:
    """Interpola `current` rumo a `target` pelo caminho angular mais curto."""
    diff = (target - current + 180.0) % 360.0 - 180.0
    return current + diff * rate * dt


def rotate_sprite_up(sprite: pygame.Surface, angle: float) -> pygame.Surface:
    """Rotaciona um sprite que aponta para cima para apontar a `angle` (graus)."""
    return pygame.transform.rotate(sprite, angle - ANGLE_UP)
