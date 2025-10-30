import pygame
import random
from ..core.config import Config
from ..core import colors
from .alien_bullet import AlienBullet


class Alien:
    def __init__(self):
        self.w, self.h = 35, 25
        self.x = random.randint(0, Config.SCREEN_WIDTH - self.w)
        self.y = -self.h
        self.speed_x = random.choice([-100, 100])
        self.speed_y = 60
        self.dead = False
        self.shoot_timer = random.uniform(1.5, 3.0)
        
        # Atributos para controle por formação
        self.formation_controlled = False
        self.formation_index = 0
        self.formation_angle = 0.0

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float) -> list[AlienBullet] | None:
        # Se controlado por formação, não move automaticamente
        if self.formation_controlled:
            # Apenas atualiza timer de tiro (o disparo é gerenciado pela Formation)
            self.shoot_timer -= dt
            # Marcar como morto se sair muito da tela (segurança)
            if self.y > Config.SCREEN_HEIGHT + 100 or self.y < -100:
                self.dead = True
            return None
        
        # Movimento normal (quando não está em formação)
        self.x += self.speed_x * dt
        self.y += self.speed_y * dt

        # Inverter direção nas bordas
        if self.x <= 0 or self.x + self.w >= Config.SCREEN_WIDTH:
            self.speed_x *= -1

        # Marcar como morto se sair da tela
        if self.y > Config.SCREEN_HEIGHT:
            self.dead = True

        # Atirar
        self.shoot_timer -= dt
        if self.shoot_timer <= 0:
            self.shoot_timer = random.uniform(2.0, 4.0)
            return [AlienBullet(self.x + self.w / 2, self.y + self.h)]
        return None

    def draw(self, surface: pygame.Surface):
        # Corpo principal
        body_rect = pygame.Rect(self.x, self.y + 5, self.w, self.h - 10)
        pygame.draw.rect(surface, colors.GREEN, body_rect, border_radius=5)

        # Cockpit
        cockpit_rect = pygame.Rect(self.x + 10, self.y, self.w - 20, 10)
        pygame.draw.ellipse(surface, colors.MAGENTA, cockpit_rect)
        pygame.draw.ellipse(surface, colors.WHITE, cockpit_rect, 1)

    def get_points_value(self) -> int:
        return 150  # Pontos por destruir um alien
