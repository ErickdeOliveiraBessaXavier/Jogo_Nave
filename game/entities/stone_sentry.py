import math
import random
from typing import List, Tuple

import pygame

from ..core import colors
from ..core.config import config as Config
from ..entities.alien_bullet import AlienBullet


class StoneSentry:
    """
    Inimigo Sentinela de Pedra - Tema de Montanha.
    Flutua até uma posição e dispara projéteis contra o jogador.
    """

    # Cores de pedra (baseadas no Stone Golem Boss)
    STONE_COLORS = [
        (90, 70, 50),    # Terra Média
        (130, 110, 80),  # Barro / Argila
        (170, 150, 120), # Pedra Seca
        (100, 100, 100), # Cinza Pedra
    ]
    
    EXPLOSION_COLORS = [(130, 110, 80), (100, 100, 100), (255, 60, 60)]

    def __init__(self):
        # Dimensões
        self.w = 40
        self.h = 40
        
        # Posição inicial (entra pelo topo)
        self.x = random.randint(50, Config.SCREEN_WIDTH - 50 - self.w)
        self.y = -self.h
        
        # Alvo de repouso (parte superior da tela)
        self.target_y = random.randint(50, 200)
        self.speed_y = 150.0
        
        # Estado
        self.dead = False
        self.health = 30 # Mais resistente que um alien comum
        self.active = True
        
        # Timers de tiro
        self.shoot_timer = random.uniform(2.0, 4.0)
        
        # Visual
        self.rotation = 0.0
        self.rotation_speed = random.uniform(-30, 30)
        self.points = self._generate_stone_shape()
        self.color = random.choice(self.STONE_COLORS)
        self.eye_color = colors.RED
        self.pulse_timer = 0.0

    def _generate_stone_shape(self) -> List[Tuple[float, float]]:
        """Gera um formato de pedra irregular (octaedro imperfeito)."""
        pts = []
        num_points = 8
        size = self.w // 2
        for i in range(num_points):
            ang = (2 * math.pi * i) / num_points
            # Irregularidade
            r = size * random.uniform(0.8, 1.2)
            pts.append((r * math.cos(ang), r * math.sin(ang)))
        return pts

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def update(self, dt: float, player_pos: Tuple[float, float] | None = None) -> List[AlienBullet] | None:
        # Movimento de entrada
        if self.y < self.target_y:
            self.y += self.speed_y * dt
        else:
            # Flutuação suave senoidal
            self.pulse_timer += dt
            self.y = self.target_y + math.sin(self.pulse_timer * 2) * 10
            
        # Rotação lenta
        self.rotation += self.rotation_speed * dt
        
        # Atirar
        self.shoot_timer -= dt
        bullets = None
        if self.shoot_timer <= 0 and not self.dead:
            bullets = self._shoot(player_pos)
            self.shoot_timer = random.uniform(2.5, 4.5)
            
        return bullets

    def _shoot(self, player_pos: Tuple[float, float] | None) -> List[AlienBullet]:
        """Dispara um projétil na direção do jogador ou para baixo."""
        bx = self.x + self.w / 2
        by = self.y + self.h / 2
        
        bullet = AlienBullet(bx, by)
        
        if player_pos:
            # Mirar no jogador
            dx = player_pos[0] - bx
            dy = player_pos[1] - by
            dist = math.sqrt(dx*dx + dy*dy)
            if dist > 0:
                bullet.vx = (dx / dist) * 300.0
                bullet.vy = (dy / dist) * 300.0
        else:
            bullet.vy = 350.0
            
        return [bullet]

    def draw(self, screen: pygame.Surface):
        # Calcular pontos rotacionados
        rad = math.radians(self.rotation)
        cr = math.cos(rad)
        sr = math.sin(rad)
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        
        rotated_pts = [
            (cx + px * cr - py * sr, cy + px * sr + py * cr)
            for px, py in self.points
        ]
        
        # Desenhar corpo de pedra
        pygame.draw.polygon(screen, self.color, rotated_pts)
        pygame.draw.polygon(screen, colors.BLACK, rotated_pts, 2)
        
        # Desenhar "olho" brilhante no centro
        eye_pulse = (math.sin(self.pulse_timer * 5) + 1) / 2 # 0 a 1
        current_eye_color = (
            int(self.eye_color[0] * (0.5 + 0.5 * eye_pulse)),
            int(self.eye_color[1] * (0.5 + 0.5 * eye_pulse)),
            int(self.eye_color[2] * (0.5 + 0.5 * eye_pulse))
        )
        pygame.draw.circle(screen, current_eye_color, (int(cx), int(cy)), 6)
        pygame.draw.circle(screen, colors.WHITE, (int(cx), int(cy)), 2)

    def get_points_value(self) -> int:
        return 250

    def take_damage(self, amount: int):
        """Aplica dano à sentinela."""
        self.health -= amount
        if self.health <= 0:
            self.dead = True
