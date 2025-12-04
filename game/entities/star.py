"""Star (Estrela) - Moeda coletável para desbloquear slots de upgrades."""

import pygame
import math
import random


class Star:
    """
    Estrela coletável que serve como moeda para desbloquear slots.
    
    Visual similar ao starfield mas maior e mais chamativo.
    """

    def __init__(self, x: float, y: float):
        """
        Inicializa uma estrela.
        
        Args:
            x: Posição x inicial
            y: Posição y inicial
        """
        self.x = x
        self.y = y
        self.base_size = random.uniform(15, 25)
        self.size = self.base_size
        self.dead = False
        
        # Movimento
        self.vy = random.uniform(20, 40)  # Velocidade para baixo
        self.vx = random.uniform(-10, 10)  # Pequena variação horizontal
        
        # Animação de pulsação
        self.animation_timer = 0.0
        self.pulse_speed = random.uniform(3, 5)
        
        # Rotação
        self.rotation = random.uniform(0, 360)
        self.rotation_speed = random.uniform(-180, 180)  # graus por segundo
        
        # Brilho/glow
        self.glow_radius = self.base_size * 2
        self.glow_intensity = random.uniform(0.6, 1.0)
        
        # Cor amarela/dourada
        self.base_color = (255, 255, 100)
        self.glow_color = (255, 255, 150, 150)  # com alpha
        
    def update(self, dt: float, screen_width: int = 1600, screen_height: int = 900) -> None:
        """
        Atualiza posição e animação da estrela.
        
        Args:
            dt: Delta time
            screen_width: Largura da tela
            screen_height: Altura da tela
        """
        # Movimento
        self.x += self.vx * dt
        self.y += self.vy * dt
        
        # Rotação
        self.rotation += self.rotation_speed * dt
        self.rotation %= 360
        
        # Animação de pulsação
        self.animation_timer += dt * self.pulse_speed
        pulse = 1.0 + 0.3 * math.sin(self.animation_timer * math.pi * 2)
        self.size = self.base_size * pulse
        self.glow_radius = self.base_size * 2 * pulse
        
        # Remove se sair da tela
        margin = 100
        if (
            self.x < -margin
            or self.x > screen_width + margin
            or self.y > screen_height + margin
        ):
            self.dead = True
    
    def draw(self, surface: pygame.Surface) -> None:
        """
        Desenha a estrela com efeito de brilho.
        
        Args:
            surface: Superfície do Pygame para desenhar
        """
        if self.dead:
            return
        
        # Desenhar glow (círculo semi-transparente)
        glow_surf = pygame.Surface((int(self.glow_radius * 2), int(self.glow_radius * 2)), pygame.SRCALPHA)
        pygame.draw.circle(
            glow_surf,
            self.glow_color,
            (int(self.glow_radius), int(self.glow_radius)),
            int(self.glow_radius)
        )
        surface.blit(
            glow_surf,
            (int(self.x - self.glow_radius), int(self.y - self.glow_radius)),
            special_flags=pygame.BLEND_ALPHA_SDL2
        )
        
        # Desenhar estrela (estrela de 5 pontas)
        points: list[tuple[float, float]] = []
        num_points = 5
        outer_radius = self.size
        inner_radius = self.size * 0.4
        
        for i in range(num_points * 2):
            angle = math.radians(self.rotation + (i * 360 / (num_points * 2)))
            radius = outer_radius if i % 2 == 0 else inner_radius
            px = self.x + radius * math.cos(angle)
            py = self.y + radius * math.sin(angle)
            points.append((px, py))
        
        # Desenhar estrela preenchida
        pygame.draw.polygon(surface, self.base_color, points)
        
        # Desenhar borda branca para destaque
        pygame.draw.polygon(surface, (255, 255, 255), points, 2)
        
        # Desenhar ponto central brilhante
        pygame.draw.circle(surface, (255, 255, 255), (int(self.x), int(self.y)), max(3, int(self.size * 0.2)))
    
    def get_rect(self) -> pygame.Rect:
        """
        Retorna o retângulo de colisão da estrela.
        
        Returns:
            pygame.Rect: Retângulo de colisão
        """
        return pygame.Rect(
            self.x - self.size,
            self.y - self.size,
            self.size * 2,
            self.size * 2
        )
