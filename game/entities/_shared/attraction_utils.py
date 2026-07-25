from __future__ import annotations

import random
from typing import Any

import pygame


def update_magnetic_attraction(
    entity: Any,
    dt: float,
    attraction_pos: tuple[float, float] | None,
    attraction_mult: float,
) -> None:
    """Aplica o movimento de atração magnética compartilhado entre coletáveis."""
    base_speed_y = entity.speed

    if attraction_pos and attraction_mult > 1.0:
        attraction_range = 120.0 * attraction_mult
        target_x = float(attraction_pos[0])
        target_y = float(attraction_pos[1])

        dx = target_x - float(entity.rect.centerx)
        dy = target_y - float(entity.rect.centery)
        dist_sq = dx * dx + dy * dy

        if dist_sq < attraction_range**2:
            if not entity._is_being_attracted:
                entity._is_being_attracted = True
                entity.attraction_shake_timer = 0.4

            dist = dist_sq**0.5
            if dist > 0:
                force_factor = 3.0 + (5.0 * (1.0 - dist / attraction_range))
                attract_speed = entity.speed * force_factor * (attraction_mult * 0.8)

                entity.x += (dx / dist) * attract_speed * dt
                entity.y += (dy / dist) * attract_speed * dt
        else:
            entity._is_being_attracted = False
            entity.y += base_speed_y * dt
    else:
        entity._is_being_attracted = False
        entity.y += base_speed_y * dt

    entity.rect.topleft = (int(entity.x), int(entity.y))
    entity.attraction_shake_timer = max(0.0, entity.attraction_shake_timer - dt)


# Velocidade do puxão de encerramento de fase (px/s). Alta o bastante para varrer
# a tela em ~1-1.5s, mas LIMITADA (não escala com a distância como o magneto) para
# a leitura ser suave — nada de teleporte. Usada quando a fase fecha e nenhum
# coletável pode sobrar em tela.
CLOSING_PULL_SPEED: float = 950.0


def update_closing_pull(
    entity: Any,
    dt: float,
    target_pos: tuple[float, float],
    speed: float = CLOSING_PULL_SPEED,
) -> None:
    """Puxa um coletável direto ao jogador no encerramento de fase.

    Diferente do magneto (`update_magnetic_attraction`), ignora o range: atrai de
    qualquer distância e com velocidade constante, garantindo que power-ups/estrelas
    cheguem ao jogador (ou fiquem perto o bastante para serem coletados) antes do
    fim da fase, sem objetos congelados atravessando a transição.
    """
    entity._is_being_attracted = True
    if entity.attraction_shake_timer <= 0.0:
        entity.attraction_shake_timer = 0.4

    dx = float(target_pos[0]) - float(entity.rect.centerx)
    dy = float(target_pos[1]) - float(entity.rect.centery)
    dist = (dx * dx + dy * dy) ** 0.5
    if dist > 1.0:
        entity.x += (dx / dist) * speed * dt
        entity.y += (dy / dist) * speed * dt
    entity.rect.topleft = (int(entity.x), int(entity.y))
    entity.attraction_shake_timer = max(0.0, entity.attraction_shake_timer - dt)


def get_attraction_pulse_rect(entity: Any) -> tuple[int, int, pygame.Rect]:
    """Calcula a posição visual pulsante compartilhada entre coletáveis."""
    draw_x: int = int(entity.rect.x)
    draw_y: int = int(entity.rect.y)
    if entity.attraction_shake_timer > 0:
        intensity = int(8 * (entity.attraction_shake_timer / 0.4))
        draw_x += random.randint(-intensity, intensity)
        draw_y += random.randint(-intensity, intensity)

    pulse_size: int = int(min(entity.w, entity.h) * entity.pulse_scale)
    pulse_rect: pygame.Rect = pygame.Rect(
        draw_x + entity.w // 2 - pulse_size // 2,
        draw_y + entity.h // 2 - pulse_size // 2,
        pulse_size,
        pulse_size,
    )
    return draw_x, draw_y, pulse_rect
