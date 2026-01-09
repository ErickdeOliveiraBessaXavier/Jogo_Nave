import pygame
from ..core.config import config as Config
from ..core import colors


class AlienBullet:
    def __init__(self, x: float, y: float):
        self.x, self.y = x, y
        self.speed = Config.ALIEN_BULLET_SPEED
        self.dead = False
        
        # Cores para piscar
        self.color_1 = colors.ALIEN_BULLET_GREEN_1
        self.color_2 = colors.ALIEN_BULLET_GREEN_2
        self.current_color = self.color_1
        
        # Animação de tamanho (pulsação)
        self.min_radius = Config.ALIEN_BULLET_MIN_RADIUS
        self.max_radius = Config.ALIEN_BULLET_MAX_RADIUS
        self.current_radius = self.min_radius
        self.pulse_timer = 0.0
        self.pulse_speed = Config.ALIEN_BULLET_PULSE_SPEED

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(
            int(self.x) - self.current_radius,
            int(self.y) - self.current_radius,
            self.current_radius * 2,
            self.current_radius * 2
        )

    def update(self, dt: float):
        self.y += self.speed * dt
        if self.y > Config.SCREEN_HEIGHT:
            self.dead = True

        # Atualizar pulsação de tamanho e cor
        self.pulse_timer += dt
        
        # Ciclo de pulsação (aumenta e diminui)
        import math
        cycle = self.pulse_timer * self.pulse_speed
        progress = (math.sin(cycle) + 1) / 2  # Valor entre 0 e 1
        
        # Calcular raio com pulsação
        self.current_radius = self.min_radius + (self.max_radius - self.min_radius) * progress
        
        # Alternar cor a cada Config.ALIEN_BULLET_COLOR_CHANGE_INTERVAL (mais frenético)
        change_interval = Config.ALIEN_BULLET_COLOR_CHANGE_INTERVAL
        if (self.pulse_timer % (change_interval * 2)) < change_interval:
            self.current_color = self.color_1
        else:
            self.current_color = self.color_2

    def draw(self, surface: pygame.Surface):
        # Desenhar círculo preenchido
        pygame.draw.circle(
            surface,
            self.current_color,
            (int(self.x), int(self.y)),
            int(self.current_radius)
        )
        # Desenhar borda branca
        pygame.draw.circle(
            surface,
            colors.WHITE,
            (int(self.x), int(self.y)),
            int(self.current_radius),
            width=1
        )
