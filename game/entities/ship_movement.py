from __future__ import annotations

import math
import random
import time
from collections import deque
from typing import TYPE_CHECKING

import pygame

from ..core.config import config as Config
from .particle_types import ParticleDict, step_particle

if TYPE_CHECKING:
    from .ship import Ship


# Controle por mouse — sistema spring
# BASE_STIFFNESS: rigidez base do spring (px/s por px de distância).
#   Suba para resposta mais imediata em geral (range seguro: 6.0–12.0).
# MOUSE_DEAD_ZONE: raio de snap em pixels — elimina jitter próximo ao cursor.
#   Aumente se a nave "vibrar" parada (range seguro: 1.0–4.0).
MOUSE_BASE_STIFFNESS: float = 8.5
MOUSE_DEAD_ZONE: float = 2.0


class ShipMovement:
    """Lida com input → posição da `Ship`: dash, gamepad, mouse spring e teclado.

    O estado de movimento (x, y, dash_*, mouse_history) continua na `Ship` —
    esta classe centraliza as decisões de input/cinemática em um único lugar.
    """

    def __init__(self, ship: "Ship") -> None:
        self.ship = ship
        # Buffer de posições do cursor para reaction_delay (x, y, timestamp).
        # Deque: popleft O(1) para descartar entradas vencidas, evitando
        # rebuild da lista por frame.
        self._mouse_history: deque[tuple[float, float, float]] = deque()

    def try_dash(self, current_move_vec: pygame.math.Vector2) -> bool:
        """Ativa o dash do Fantasma se o cooldown permitir."""
        ship = self.ship
        if not ship.profile.has_dash:
            return False
        if ship.dash_cooldown_left > 0.0 or ship.is_dashing:
            return False
        # Paralisia elétrica trava o dash também.
        if ship.is_stunned:
            return False

        if current_move_vec.length_squared() > 0:
            direction = current_move_vec.normalize()
        else:
            # Sem input: dasha na direção em que a nave está apontando.
            vx, vy = ship.cardinal_vectors.get(ship.facing, (0.0, -1.0))
            direction = pygame.math.Vector2(vx, vy)

        ship.dash_dir = direction
        ship.dash_timer = ship.dash_duration
        ship.dash_cooldown_left = ship.profile.dash_cooldown
        # I-frames: invuln expressa em ms.
        ship.invuln = max(ship.invuln, int(ship.dash_duration * 1000))
        return True

    def update_dash(self, dt: float) -> None:
        """Avança dash, cooldown e partículas do rastro."""
        ship = self.ship
        if ship.dash_timer > 0.0:
            ship.dash_timer = max(0.0, ship.dash_timer - dt)
        if ship.dash_cooldown_left > 0.0:
            ship.dash_cooldown_left = max(0.0, ship.dash_cooldown_left - dt)
        self._update_dash_trail(dt)

    def _update_dash_trail(self, dt: float) -> None:
        ship = self.ship
        if ship.is_dashing:
            cx = ship.x + ship.w / 2
            cy = ship.y + ship.h / 2
            # Velocidade contrária à direção do dash (rastro fica para trás).
            back_x = -ship.dash_dir.x * random.uniform(60, 160)
            back_y = -ship.dash_dir.y * random.uniform(60, 160)
            for _ in range(3):
                ship.dash_trail_particles.append(
                    ParticleDict(
                        x=cx + random.uniform(-4, 4),
                        y=cy + random.uniform(-4, 4),
                        vx=back_x + random.uniform(-30, 30),
                        vy=back_y + random.uniform(-30, 30),
                        lifetime=random.uniform(0.18, 0.32),
                        size=random.uniform(3.0, 5.5),
                        color=(160, 220, 255),
                    )
                )

        if not ship.dash_trail_particles:
            return

        # Rastro do dash: encolhe rápido (dt*12) e tem drag (damping 0.92).
        ship.dash_trail_particles = [
            step_particle(p, dt, size_shrink_rate=12.0, velocity_damping=0.92)
            for p in ship.dash_trail_particles
            if p["lifetime"] - dt > 0 and p["size"] - dt * 12.0 > 0
        ]

    def move(
        self,
        held_actions: set[str],
        dt: float,
        is_side_scroll: bool = False,
        gamepad_vec: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        ship = self.ship

        # Fantasma em dash: força velocidade alta na direção travada e ignora input.
        # Dash tem prioridade sobre a paralisia (i-frames já em curso).
        if ship.is_dashing:
            dash_speed = ship.speed * ship.dash_speed_mult
            ship.x += ship.dash_dir.x * dash_speed * dt
            ship.y += ship.dash_dir.y * dash_speed * dt
            self._keep_in_bounds(is_side_scroll)
            return

        # Descarga elétrica: movimento completamente travado durante a paralisia.
        if ship.is_stunned:
            self._keep_in_bounds(is_side_scroll)
            return

        # Velocidade atual considerando boost, Nevasca (-70%) e Vento (slow).
        base_speed_multiplier = 1.0
        if ship.speed_boost_timer > 0:
            base_speed_multiplier = 1.5
        if ship.speed_modifier_timer > 0.0:
            base_speed_multiplier *= 0.3
        base_speed_multiplier *= ship.wind_slow_factor

        current_speed = ship.speed * base_speed_multiplier
        move_vec = pygame.math.Vector2(0, 0)

        gp_x, gp_y = gamepad_vec
        if gp_x != 0.0 or gp_y != 0.0:
            # Movimento proporcional à inclinação do stick. invert_controls_timer
            # (Toxina) espelha o vetor inteiro.
            if ship.invert_controls_timer > 0.0:
                gp_x, gp_y = -gp_x, -gp_y
            move_vec.x = gp_x
            move_vec.y = gp_y
            mag = move_vec.length()
            if mag > 1.0:
                move_vec /= mag
        elif ship.mouse_control:
            # Spring-follow: velocidade proporcional à distância ao cursor,
            # escalada por agility_mult do profile. Sem input lag.
            mouse_x, mouse_y = pygame.mouse.get_pos()

            if ship.invert_controls_timer > 0.0:
                screen_cx = getattr(Config, "SCREEN_WIDTH", 480) / 2
                screen_cy = getattr(Config, "SCREEN_HEIGHT", 800) / 2
                target_x = 2 * screen_cx - mouse_x
                target_y = 2 * screen_cy - mouse_y
            else:
                target_x = mouse_x
                target_y = mouse_y

            # Reaction delay: registrar posição atual e buscar posição atrasada.
            delay = ship.profile.reaction_delay
            if delay > 0.0:
                now = time.time()
                history = self._mouse_history
                history.append((target_x, target_y, now))
                # Descartar entradas vencidas — popleft O(1) por entrada.
                cutoff = now - (delay + 0.1)
                while history and history[0][2] < cutoff:
                    history.popleft()
                # Buscar a posição mais próxima de `delay` segundos atrás.
                for x, y, t in reversed(history):
                    if now - t >= delay:
                        target_x, target_y = x, y
                        break

            ship_center_x = ship.x + ship.w / 2
            ship_center_y = ship.y + ship.h / 2

            dx = target_x - ship_center_x
            dy = target_y - ship_center_y
            dist = math.sqrt(dx * dx + dy * dy)

            if dist >= MOUSE_DEAD_ZONE:
                # Sensitivity proporcional à distância, escalada por agility_mult.
                # velocidade = distância × sensitivity × agility × current_speed.
                sensitivity = MOUSE_BASE_STIFFNESS * 0.002 * ship.profile.agility_mult
                move_vec.x = dx * sensitivity
                move_vec.y = dy * sensitivity
        else:
            # Movimento por teclado. Toxina inverte mapeamento de teclas.
            left = "hold_right" if ship.invert_controls_timer > 0.0 else "hold_left"
            right = "hold_left" if ship.invert_controls_timer > 0.0 else "hold_right"
            up = "hold_down" if ship.invert_controls_timer > 0.0 else "hold_up"
            down = "hold_up" if ship.invert_controls_timer > 0.0 else "hold_down"

            if left in held_actions:
                move_vec.x -= 1
            if right in held_actions:
                move_vec.x += 1
            if up in held_actions:
                move_vec.y -= 1
            if down in held_actions:
                move_vec.y += 1

            if move_vec.length() > 0:
                move_vec.normalize_ip()

        ship.x += move_vec.x * current_speed * dt
        ship.y += move_vec.y * current_speed * dt

        self._keep_in_bounds(is_side_scroll)

    def _keep_in_bounds(self, _is_side_scroll: bool = False) -> None:
        ship = self.ship
        if ship.x < 0:
            ship.x = 0
        if ship.y < 0:
            ship.y = 0
        if ship.x + ship.w > Config.SCREEN_WIDTH:
            ship.x = Config.SCREEN_WIDTH - ship.w
        if ship.y + ship.h > Config.SCREEN_HEIGHT and not ship.is_entering:
            # Em top-down, permitir sair pela parte inferior durante entrada.
            ship.y = Config.SCREEN_HEIGHT - ship.h
