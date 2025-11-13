"""Boss Square Projectile - Indestructible projectile launched by the boss."""

import pygame
import math


class BossSquare:
    """
    Indestructible square projectile launched by the boss in frenzy mode.
    
    Features:
    - Flies towards player with slight inaccuracy
    - Pulsating animation like power-ups
    - Cannot be destroyed by bullets
    - Causes damage on collision with player
    """
    
    def __init__(self, x: float, y: float, vx: float, vy: float, size: float):
        """
        Initialize a boss square projectile.
        
        Args:
            x: Starting x position
            y: Starting y position
            vx: X velocity
            vy: Y velocity
            size: Base size of the square
        """
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.base_size = size
        self.size = size
        self.dead = False
        
        # Animation
        self.animation_timer = 0.0
        self.rotation = 0.0  # Rotação contínua
        
        # Growth effect - aumenta conforme se move
        self.growth_timer = 0.0
        self.max_growth_scale = 2.5  # Crescimento máximo (2.5x do tamanho inicial)
        self.growth_duration = 2.0  # Tempo para atingir tamanho máximo (segundos)
        
    def update(self, dt: float, screen_width: int = 1600, screen_height: int = 900) -> None:
        """
        Update position and animation.
        
        Args:
            dt: Delta time
            screen_width: Current screen width (for boundary check)
            screen_height: Current screen height (for boundary check)
        """
        # Move
        self.x += self.vx * dt
        self.y += self.vy * dt
        
        # Rotação contínua
        self.rotation += dt * 360  # Gira 360 graus por segundo
        
        # Efeito de crescimento progressivo
        self.growth_timer += dt
        growth_progress = min(self.growth_timer / self.growth_duration, 1.0)
        # Curva de crescimento suave (ease-out)
        growth_scale = 1.0 + (self.max_growth_scale - 1.0) * (1.0 - (1.0 - growth_progress) ** 2)
        
        # Pulsation animation (same as power-ups)
        self.animation_timer += dt * 5
        pulse_scale = 1.0 + 0.2 * abs(
            pygame.math.Vector2(1, 0).rotate(self.animation_timer * 57.3).x
        )
        
        # Combina crescimento com pulsação
        self.size = self.base_size * growth_scale * pulse_scale
        
        # Remove if off-screen (margem muito grande para garantir que saia completamente)
        # Considerando tamanho do quadrado + pulsação + rotação + crescimento
        margin = 300  # Aumentado devido ao crescimento
        if (self.x < -margin or self.x > screen_width + margin or
            self.y < -margin or self.y > screen_height + margin):
            self.dead = True
    
    def draw(self, surface: pygame.Surface) -> None:
        """Draw the square projectile with rotation."""
        if self.dead:
            return
        
        # Calcular cor com intensidade alternada
        intensity = int(128 + 127 * abs(
            pygame.math.Vector2(1, 0).rotate(self.animation_timer * 57.3).x
        ))
        color = (255, intensity, intensity)
        border_color = (255, 255, 255)
        
        # Desenhar quadrado rotacionado
        center_x = self.x
        center_y = self.y
        angle_rad = math.radians(self.rotation)
        
        # Calcular os 4 cantos do quadrado rotacionado
        half_size = self.size / 2
        corners = [
            (-half_size, -half_size),
            (half_size, -half_size),
            (half_size, half_size),
            (-half_size, half_size)
        ]
        
        # Rotacionar cada canto
        rotated_corners: list[tuple[float, float]] = []
        for cx, cy in corners:
            # Aplicar rotação
            rx = cx * math.cos(angle_rad) - cy * math.sin(angle_rad)
            ry = cx * math.sin(angle_rad) + cy * math.cos(angle_rad)
            rotated_corners.append((center_x + rx, center_y + ry))
        
        # Desenhar polígono preenchido
        pygame.draw.polygon(surface, color, rotated_corners)
        
        # Desenhar borda
        pygame.draw.polygon(surface, border_color, rotated_corners, 2)
    
    def get_rect(self) -> pygame.Rect:
        """Get collision rectangle."""
        half_size = self.size / 2
        return pygame.Rect(
            self.x - half_size,
            self.y - half_size,
            self.size,
            self.size
        )
