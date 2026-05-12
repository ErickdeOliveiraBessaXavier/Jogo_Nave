import colorsys
import random
from typing import Tuple

import pygame

from ..core.assets import get_font
from ..core.colors import (POWERUP_COOLDOWN_HASTE, POWERUP_DAMAGE_BOOST,
                           POWERUP_DOUBLE_SHOT, POWERUP_LIFE,
                           POWERUP_MINI_SHIPS, POWERUP_PIERCING_SHOT,
                           POWERUP_RAINBOW, POWERUP_SCORE, POWERUP_SHIELD,
                           POWERUP_SPEED, POWERUP_TIME_STOP, RAINBOW_COLORS)
from ..core.config import PowerUpType
from ..core.config import config as Config


class PowerUp:
    def __init__(self, powerup_type: PowerUpType):
        self.type = powerup_type
        self.kind = powerup_type.value  # Mantém compatibilidade com código existente
        self.w, self.h = Config.POWERUP_SIZE, Config.POWERUP_SIZE
        self.x = random.randint(0, Config.SCREEN_WIDTH - self.w)
        self.y = -self.h
        self.speed = Config.POWERUP_SPEED
        self.rect = pygame.Rect(self.x, self.y, self.w, self.h)

        # Animação/pulsação
        self.animation_timer = 0.0
        self.pulse_scale = 1.0
        self.dead = False

    def update(self, dt: float):
        self.y += self.speed * dt
        self.rect.topleft = (int(self.x), int(self.y))

        # Animação de pulsação
        self.animation_timer += dt * 5  # velocidade da pulsação
        self.pulse_scale = 1.0 + 0.2 * abs(
            pygame.math.Vector2(1, 0).rotate(self.animation_timer * 57.3).x
        )

    def draw(self, surface: pygame.Surface):
        color_map = {
            "life": POWERUP_LIFE,
            "shield": POWERUP_SHIELD,
            "double_shot": POWERUP_DOUBLE_SHOT,
            "speed": POWERUP_SPEED,
            "score": POWERUP_SCORE,
            "piercing_shot": POWERUP_PIERCING_SHOT,
            "mini_ships": POWERUP_MINI_SHIPS,
            "rainbow": POWERUP_RAINBOW,
            "cooldown_haste": POWERUP_COOLDOWN_HASTE,
            "time_stop": POWERUP_TIME_STOP,
            "damage_boost": POWERUP_DAMAGE_BOOST,
        }

        text_map = {
            "life": "[+]",
            "shield": "[S]",
            "double_shot": "[2X]",
            "speed": "[V]",
            "score": "[x1.5]",
            "piercing_shot": "[P]",
            "mini_ships": "[M]",
            "rainbow": "[ALL]",
            "cooldown_haste": "[CD]",
            "time_stop": "[STOP]",
            "damage_boost": "[DMG]",
        }

        # Desenha o fundo do power-up com pulsação
        pulse_size = int(min(self.w, self.h) * self.pulse_scale)
        pulse_rect = pygame.Rect(
            self.rect.centerx - pulse_size // 2,
            self.rect.centery - pulse_size // 2,
            pulse_size,
            pulse_size,
        )

        # Criar superfície com alpha para blur/transparência
        blur_surface = pygame.Surface((pulse_size, pulse_size), pygame.SRCALPHA)

        # Fundo cinza com opacidade 0.8 e blur simulado (múltiplas camadas)
        for i in range(3):
            alpha = int(204 - i * 20)  # 204 = 0.8 * 255, decrescendo para simular blur
            size_offset = i * 2
            blur_rect = pygame.Rect(
                size_offset,
                size_offset,
                pulse_size - size_offset * 2,
                pulse_size - size_offset * 2,
            )
            pygame.draw.ellipse(blur_surface, (50, 50, 50, alpha), blur_rect)

        # Blit na surface principal
        surface.blit(blur_surface, (pulse_rect.x, pulse_rect.y))

        # Determinar cor da borda e texto
        if self.kind == "rainbow":
            # Rainbow animado - cicla através das cores do arco-íris
            hue = (self.animation_timer * 50) % 360
            # Converter HSV para RGB
            r, g, b = colorsys.hsv_to_rgb(hue / 360.0, 1.0, 1.0)
            border_color = (int(r * 255), int(g * 255), int(b * 255))
        else:
            border_color = color_map.get(self.kind, (255, 255, 255))

        # Borda colorida com espessura maior para destaque
        pygame.draw.ellipse(surface, border_color, pulse_rect, 3)

        # Borda interna mais fina e brilhante
        inner_rect = pulse_rect.inflate(-6, -6)
        pygame.draw.ellipse(surface, border_color, inner_rect, 1)

        # Desenha o texto - rainbow usa cor animada, outros usam branco
        text_color = border_color if self.kind == "rainbow" else (255, 255, 255)
        self._draw_text(surface, text_map.get(self.kind, "[?]"), text_color)

    def _draw_text(
        self,
        surface: pygame.Surface,
        text: str,
        color: Tuple[int, int, int] = (255, 255, 255),
    ):
        """Desenha texto simples para cada tipo de power-up"""
        try:
            # Usa o sistema de assets para carregar a fonte
            font = get_font(10)  # Tamanho um pouco menor para melhor alinhamento
        except pygame.error:
            # Fallback para fonte padrão se get_font falhar
            font = pygame.font.Font(None, 16)

        # Renderiza o texto com a cor fornecida
        text_surface = font.render(text, True, color)

        # Centraliza o texto no power-up usando o centro do círculo pulsante
        circle_center_x = self.rect.centerx
        circle_center_y = self.rect.centery

        text_rect = text_surface.get_rect()
        text_rect.centerx = circle_center_x + 1  # Move 1 pixel para direita
        text_rect.centery = circle_center_y

        # Desenha o texto
        surface.blit(text_surface, text_rect)

    def _draw_rainbow_effect(self, surface: pygame.Surface, pulse_rect: pygame.Rect):
        """Desenha efeito arco-íris especial para o power-up rainbow"""
        import math

        # Cria múltiplas camadas de círculos com cores diferentes
        colors = RAINBOW_COLORS

        # Desenha círculos concêntricos com cores do arco-íris
        for i, color in enumerate(colors):
            # Calcula o tamanho de cada círculo
            layer_size = pulse_rect.width - (i * 6)
            if layer_size > 0:
                layer_rect = pygame.Rect(
                    pulse_rect.centerx - layer_size // 2,
                    pulse_rect.centery - layer_size // 2,
                    layer_size,
                    layer_size,
                )

                # Varia a intensidade das cores com a animação
                intensity = 0.7 + 0.3 * math.sin(self.animation_timer + i * 0.5)
                adjusted_color = tuple(int(c * intensity) for c in color)

                pygame.draw.ellipse(surface, adjusted_color, layer_rect)

        # Borda brilhante externa
        pygame.draw.ellipse(surface, (255, 255, 255), pulse_rect, 3)

    def is_off_screen(self) -> bool:
        """Verifica se o power-up saiu da tela"""
        return self.y > Config.SCREEN_HEIGHT
