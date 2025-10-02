import random
import pygame
from ..core.config import Config
from ..core.assets import get_font


class PowerUp:
    TYPES = ["life", "shield", "double_shot", "speed", "score", "rainbow"]

    def __init__(self):
        self.kind = random.choice(PowerUp.TYPES)
        self.w, self.h = Config.POWERUP_SIZE, Config.POWERUP_SIZE
        self.x = random.randint(0, Config.SCREEN_WIDTH - self.w)
        self.y = -self.h
        self.speed = Config.POWERUP_SPEED
        self.rect = pygame.Rect(self.x, self.y, self.w, self.h)

        # Animação/pulsação
        self.animation_timer = 0.0
        self.pulse_scale = 1.0

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
            "life": (255, 50, 50),  # vermelho mais suave
            "shield": (50, 50, 255),  # azul mais suave
            "double_shot": (50, 255, 50),  # verde mais suave
            "speed": (255, 255, 50),  # amarelo mais suave
            "score": (255, 50, 255),  # magenta mais suave
        }

        text_map = {
            "life": "[+]",
            "shield": "[S]",
            "double_shot": "[2X]",
            "speed": "[V]",
            "score": "[*]",
            "rainbow": "[ALL]",
        }

        # Desenha o fundo do power-up com pulsação
        pulse_size = int(min(self.w, self.h) * self.pulse_scale)
        pulse_rect = pygame.Rect(
            self.rect.centerx - pulse_size // 2,
            self.rect.centery - pulse_size // 2,
            pulse_size,
            pulse_size,
        )

        # Sombra
        shadow_rect = pulse_rect.copy()
        shadow_rect.x += 2
        shadow_rect.y += 2
        pygame.draw.ellipse(surface, (0, 0, 0, 128), shadow_rect)

        # Efeito especial para o power-up rainbow
        if self.kind == "rainbow":
            self._draw_rainbow_effect(surface, pulse_rect)
        else:
            # Fundo principal
            pygame.draw.ellipse(surface, color_map[self.kind], pulse_rect)

            # Borda brilhante
            pygame.draw.ellipse(surface, (255, 255, 255), pulse_rect, 2)

        # Desenha o texto
        self._draw_text(surface, text_map[self.kind])

    def _draw_text(self, surface: pygame.Surface, text: str):
        """Desenha texto simples para cada tipo de power-up"""
        # Usa o sistema de assets para carregar a fonte
        font = get_font(10)  # Tamanho um pouco menor para melhor alinhamento

        # Renderiza o texto
        text_surface = font.render(text, True, (255, 255, 255))

        # Centraliza o texto no power-up usando o centro do círculo pulsante
        circle_center_x = self.rect.centerx
        circle_center_y = self.rect.centery

        text_rect = text_surface.get_rect()
        text_rect.centerx = circle_center_x + 1  # Move 1 pixel para direita
        text_rect.centery = circle_center_y

        # Desenha o texto
        surface.blit(text_surface, text_rect)

    def _draw_rainbow_effect(
            self,
            surface: pygame.Surface,
            pulse_rect: pygame.Rect):
        """Desenha efeito arco-íris especial para o power-up rainbow"""
        import math

        # Cria múltiplas camadas de círculos com cores diferentes
        colors = [
            (255, 0, 0),  # vermelho
            (255, 127, 0),  # laranja
            (255, 255, 0),  # amarelo
            (0, 255, 0),  # verde
            (0, 0, 255),  # azul
            (75, 0, 130),  # índigo
            (148, 0, 211),  # violeta
        ]

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
                intensity = 0.7 + 0.3 * \
                    math.sin(self.animation_timer + i * 0.5)
                adjusted_color = tuple(int(c * intensity) for c in color)

                pygame.draw.ellipse(surface, adjusted_color, layer_rect)

        # Borda brilhante externa
        pygame.draw.ellipse(surface, (255, 255, 255), pulse_rect, 3)

    def is_off_screen(self) -> bool:
        """Verifica se o power-up saiu da tela"""
        return self.y > Config.SCREEN_HEIGHT
