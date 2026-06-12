from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from .ship import Ship


_REPULSION_GLOW_CACHE: dict[int, pygame.Surface] = {}


def _get_repulsion_glow(glow_r: int) -> pygame.Surface:
    cached = _REPULSION_GLOW_CACHE.get(glow_r)
    if cached is not None:
        return cached
    surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
    pygame.draw.circle(surf, (200, 255, 255, 40), (glow_r, glow_r), glow_r)
    try:
        surf = surf.convert_alpha()
    except pygame.error:
        pass
    _REPULSION_GLOW_CACHE[glow_r] = surf
    return surf


_CHAIN_SPARK_COLORS: tuple[tuple[int, int, int], ...] = (
    (100, 200, 255),
    (200, 255, 255),
    (255, 255, 255),
)


class ShipRenderer:
    """Renderiza a `Ship` e seus efeitos visuais.

    Lê estado da `Ship` sem mutá-lo. Mantido como classe (não função pura)
    para que helpers privados como `_draw_charge_indicator` permaneçam coesos
    junto ao renderer e o estado de iteração possa ser cacheado no futuro.
    """

    def __init__(self, ship: "Ship") -> None:
        self.ship = ship

    def draw(self, surface: pygame.Surface) -> None:
        ship = self.ship
        if not ship.visible:
            return

        # Rastro do dash: desenhado antes do blink de invuln para garantir visibilidade
        # mesmo quando a nave em si está piscando durante os i-frames.
        for p in ship.dash_trail_particles:
            pygame.draw.circle(
                surface, p["color"], (int(p["x"]), int(p["y"])), int(p["size"])
            )

        # Indicador de carga do Caçador: anel de progresso ao redor da nave.
        if ship.charge_shot_active:
            self._draw_charge_indicator(surface)

        if ship.invuln > 0 and int(ship.invuln / 100) % 2 == 0:
            return

        # Desenhar partículas de thruster (atrás da nave)
        for p in ship.thruster_particles:
            pygame.draw.circle(surface, p["color"], (p["x"], p["y"]), p["size"])

        # Desenhar escudo (se ativo)
        if ship.has_shield:
            # Efeito pulsante
            pulse = abs((ship.draw_time * 4) % 2 - 1)

            sprite_w, sprite_h = ship.ship_image_size
            center_x = int(ship.x + sprite_w / 2)
            center_y = int(ship.y + sprite_h / 2)
            base_radius = max(sprite_w, sprite_h) / 2 + 8

            radius = int(base_radius + pulse * 4)

            shield_color = (100, 150, 255)
            for i in range(3):
                pygame.draw.circle(
                    surface, shield_color, (center_x, center_y), radius - i, 2
                )

        # Repulsion Shield (Vento)
        if ship.has_repulsion_shield:
            sprite_w, sprite_h = ship.ship_image_size
            cx = int(ship.x + sprite_w / 2)
            cy = int(ship.y + sprite_h / 2)

            pulse = abs((ship.draw_time * 6) % 2 - 1)
            glow_r = 30 + int(pulse * 10)

            # Surface cacheada (módulo) — sem alocação por frame.
            glow_surf = _get_repulsion_glow(glow_r)
            surface.blit(glow_surf, (cx - glow_r, cy - glow_r))

        # Chain Shot (Efeito Estático/Elétrico)
        if ship.has_chain_shot:
            sprite_w, sprite_h = ship.cached_sprite_size
            cx, cy = int(ship.x + sprite_w / 2), int(ship.y + sprite_h / 2)
            radius = max(sprite_w, sprite_h) // 2 + 5

            if random.random() < 0.8:
                cos = math.cos
                sin = math.sin
                uniform = random.uniform
                choice = random.choice
                draw_lines = pygame.draw.lines
                colors_pool = _CHAIN_SPARK_COLORS
                tau = math.tau

                num_arcs = random.randint(2, 4)
                for _ in range(num_arcs):
                    angle1 = uniform(0, tau)
                    angle2 = angle1 + uniform(0.2, 0.8)
                    mid_angle = (angle1 + angle2) * 0.5
                    mid_radius = radius + uniform(2, 8)

                    p1 = (cx + cos(angle1) * radius, cy + sin(angle1) * radius)
                    p_mid = (
                        cx + cos(mid_angle) * mid_radius,
                        cy + sin(mid_angle) * mid_radius,
                    )
                    p2 = (cx + cos(angle2) * radius, cy + sin(angle2) * radius)

                    draw_lines(surface, choice(colors_pool), False, [p1, p_mid, p2], 1)

        # Rastros de Vento Constante (Omnidirecional)
        if ship.repulsion_wind_streaks:
            cos = math.cos
            sin = math.sin
            draw_line = pygame.draw.line
            for s in ship.repulsion_wind_streaks:
                angle = s["angle"]
                dist = s["dist"]
                length = s["len"]
                ca = cos(angle)
                sa = sin(angle)
                base_x = s["cx"]
                base_y = s["cy"]
                start_x = base_x + ca * dist
                start_y = base_y + sa * dist
                end_x = base_x + ca * (dist + length)
                end_y = base_y + sa * (dist + length)
                draw_line(
                    surface,
                    (255, 255, 255, int(s["alpha"])),
                    (start_x, start_y),
                    (end_x, end_y),
                    1,
                )

        # Calcular tremor
        shake_x, shake_y = 0, 0
        if ship.is_entering:
            shake_x = random.randint(-2, 2)
            shake_y = random.randint(-2, 2)

        # Desenhar a nave (usar imagem rotacionada se houver rotação)
        if ship.ship_image is not None:
            image_to_draw = (
                ship.ship_image_rotated
                if (ship.rotation_angle != 0.0 and ship.ship_image_rotated is not None)
                else ship.ship_image
            )
            surface.blit(image_to_draw, (ship.x + shake_x, ship.y + shake_y))

        # Debuff elétrico (campo da Torreta Orbital): arcos crepitando enquanto
        # "carregada"; gaiola de raios intensa enquanto a descarga paralisa.
        if ship.is_electrified or ship.is_stunned:
            self._draw_electric_debuff(surface)

        # Desenhar bolas elétricas orbitais
        if ship.orbital_lasers_active:
            self._draw_orbital_lasers(surface)

        # Desenhar partículas de entrada (acima da nave)
        for p in ship.entry_particles:
            pygame.draw.circle(surface, p["color"], (p["x"], p["y"]), p["size"])

    def _draw_electric_debuff(self, surface: pygame.Surface) -> None:
        """Feedback visual do debuff elétrico, distinto entre os dois estados.

        - "carregada" (`is_electrified`): poucos arcos finos crepitando ao redor
          — sinal de que a nave está infectada e pode descarregar a qualquer
          momento;
        - "paralisada" (`is_stunned`): gaiola densa de raios brancos travando a
          nave, com núcleo pulsante — leitura inequívoca de movimento bloqueado.
        """
        ship = self.ship
        sprite_w, sprite_h = ship.cached_sprite_size
        cx = int(ship.x + sprite_w / 2)
        cy = int(ship.y + sprite_h / 2)
        base_r = max(sprite_w, sprite_h) // 2 + 4

        cos = math.cos
        sin = math.sin
        uniform = random.uniform
        tau = math.tau
        draw_lines = pygame.draw.lines

        stunned = ship.is_stunned
        if stunned:
            # Gaiola intensa: anel pulsante + muitos arcos brancos curtos.
            pulse = abs((ship.draw_time * 12) % 2 - 1)
            ring_r = base_r + int(pulse * 4)
            pygame.draw.circle(surface, (180, 230, 255), (cx, cy), ring_r, 1)
            num_arcs = 7
            arc_colors = ((220, 245, 255), (255, 255, 255))
            spread = (0.25, 0.7)
            reach = (4, 11)
        else:
            # Crepitação leve: poucos arcos ciano finos.
            if random.random() > 0.7:
                return
            num_arcs = 3
            arc_colors = ((110, 200, 255), (200, 240, 255))
            spread = (0.2, 0.6)
            reach = (2, 7)

        for _ in range(num_arcs):
            a0 = uniform(0, tau)
            a1 = a0 + uniform(*spread)
            mid_a = (a0 + a1) * 0.5
            mid_r = base_r + uniform(*reach)
            p0 = (cx + cos(a0) * base_r, cy + sin(a0) * base_r)
            pm_pt = (cx + cos(mid_a) * mid_r, cy + sin(mid_a) * mid_r)
            p1 = (cx + cos(a1) * base_r, cy + sin(a1) * base_r)
            color = arc_colors[random.randint(0, len(arc_colors) - 1)]
            draw_lines(surface, color, False, [p0, pm_pt, p1], 1)

    def _draw_charge_indicator(self, surface: pygame.Surface) -> None:
        """Anel de progresso da carga ao redor da nave (Caçador)."""
        ship = self.ship
        progress = ship.charge_shot_progress
        if progress <= 0:
            return

        cx = int(ship.x + ship.w / 2)
        cy = int(ship.y + ship.h / 2)
        radius = max(ship.w, ship.h) // 2 + 10

        r = int(60 + 60 * progress)
        g = int(180 + 60 * progress)
        b = 255
        color = (r, g, b)

        segments = 36
        active_segments = max(1, int(segments * progress))
        for i in range(active_segments):
            angle = -math.pi / 2 + (i / segments) * math.tau
            px = cx + int(math.cos(angle) * radius)
            py = cy + int(math.sin(angle) * radius)
            pygame.draw.circle(surface, color, (px, py), 2)

        if progress >= 1.0:
            pulse = int(2 + 2 * abs(math.sin(ship.draw_time * 8)))
            pygame.draw.circle(surface, (255, 255, 255), (cx, cy), radius + 2, pulse)

    def _draw_orbital_lasers(self, surface: pygame.Surface) -> None:
        ship = self.ship
        current_time = ship.draw_time

        sprite_w, sprite_h = ship.ship_image_size

        for i in range(ship.num_orbital_balls):
            charges = ship.orbital_laser_charges[i]
            fade = ship.orbital_ball_fade[i]
            entry = ship.orbital_ball_entry[i]
            shake = ship.orbital_ball_shake[i]

            if charges <= 0 and fade <= 0.0:
                continue

            angle = ship.orbital_angle + (i * 2 * math.pi / ship.num_orbital_balls)

            if entry > 0.0:
                entry_progress = 1.0 - (entry / 0.9)
                entry_progress = 1.0 - (1.0 - entry_progress) ** 3
                current_radius = ship.orbital_radius * entry_progress
            else:
                current_radius = ship.orbital_radius

            shake_x, shake_y = 0, 0
            if shake > 0.0:
                shake_intensity = int(5 * (shake / 0.8))
                if shake_intensity > 0:
                    shake_x = random.randint(-shake_intensity, shake_intensity)
                    shake_y = random.randint(-shake_intensity, shake_intensity)

            ball_x = int(
                ship.x + sprite_w / 2 + math.cos(angle) * current_radius + shake_x
            )
            ball_y = int(
                ship.y + sprite_h / 2 + math.sin(angle) * current_radius + shake_y
            )

            # Em fade (última carga usada): piscar vermelho e diminuir.
            if charges <= 0 and fade > 0.0:
                blink = int(current_time * 10) % 2 == 0
                if blink:
                    fade_alpha = fade / 1.5
                    ball_radius = int(3 + fade_alpha * 3)
                    pygame.draw.circle(
                        surface,
                        (255, 100, 100),
                        (ball_x, ball_y),
                        ball_radius + 2,
                        1,
                    )
                    pygame.draw.circle(
                        surface, (255, 150, 150), (ball_x, ball_y), ball_radius
                    )
                continue

            # Última carga - piscar amarelo/vermelho como aviso
            if charges == 1:
                blink = int(current_time * 6) % 2 == 0
                pulse = abs((current_time * 8 + i) % 2 - 1)
                ball_radius = int(4 + pulse * 2)
                if blink:
                    pygame.draw.circle(
                        surface,
                        (255, 180, 50),
                        (ball_x, ball_y),
                        ball_radius + 3,
                        1,
                    )
                    pygame.draw.circle(
                        surface,
                        (255, 200, 100),
                        (ball_x, ball_y),
                        ball_radius + 2,
                        1,
                    )
                    pygame.draw.circle(
                        surface, (255, 220, 150), (ball_x, ball_y), ball_radius
                    )
                else:
                    pygame.draw.circle(
                        surface,
                        (255, 100, 50),
                        (ball_x, ball_y),
                        ball_radius + 2,
                        1,
                    )
                    pygame.draw.circle(
                        surface, (255, 150, 100), (ball_x, ball_y), ball_radius
                    )

            # Cargas normais (2 ou 3)
            else:
                is_ready_to_fire = (
                    ship.orbital_current_ball == i
                    and ship.orbital_global_cooldown < 1.0
                )

                if entry > 0.0:
                    entry_alpha = 1.0 - (entry / 0.9)
                    pulse = abs((current_time * 8 + i) % 2 - 1)
                    ball_radius = int(2 + entry_alpha * 4 + pulse * 1)
                    alpha_color = int(255 * entry_alpha)
                    pygame.draw.circle(
                        surface,
                        (100, 200, alpha_color),
                        (ball_x, ball_y),
                        ball_radius + 2,
                        1,
                    )
                    pygame.draw.circle(
                        surface,
                        (150, 255, alpha_color),
                        (ball_x, ball_y),
                        ball_radius,
                    )
                elif is_ready_to_fire:
                    pulse = abs((current_time * 12 + i) % 2 - 1)
                    ball_radius = int(4 + pulse * 3)
                    pygame.draw.circle(
                        surface,
                        (150, 255, 255),
                        (ball_x, ball_y),
                        ball_radius + 4,
                        1,
                    )
                    pygame.draw.circle(
                        surface,
                        (200, 240, 255),
                        (ball_x, ball_y),
                        ball_radius + 3,
                        1,
                    )
                    pygame.draw.circle(
                        surface,
                        (255, 255, 255),
                        (ball_x, ball_y),
                        ball_radius + 1,
                    )
                else:
                    pulse = abs((current_time * 6 + i) % 2 - 1)
                    ball_radius = int(4 + pulse * 2)
                    pygame.draw.circle(
                        surface,
                        (100, 200, 255),
                        (ball_x, ball_y),
                        ball_radius + 3,
                        1,
                    )
                    pygame.draw.circle(
                        surface,
                        (150, 255, 255),
                        (ball_x, ball_y),
                        ball_radius + 2,
                        1,
                    )
                    pygame.draw.circle(
                        surface,
                        (200, 240, 255),
                        (ball_x, ball_y),
                        ball_radius,
                    )
