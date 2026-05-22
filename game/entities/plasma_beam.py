import pygame
from typing import Any

class PlasmaBeam:
    def __init__(self, ship: Any, duration: float):
        self.ship = ship
        self.timer = duration
        self.dead = False
        self.length = 800
        self.width = 12
        self.damage = 600 # Dano massivo por segundo

    def update(self, dt: float):
        self.timer -= dt
        if self.timer <= 0 or getattr(self.ship, "dead", False):
            self.dead = True

    def get_line(self) -> tuple[tuple[float, float], tuple[float, float]]:
        # Pega a direção que a nave está virada
        vx, vy = self.ship.get_facing_vector()
        cx = self.ship.x + self.ship.w / 2
        cy = self.ship.y + self.ship.h / 2
        
        start_pos = (cx + vx * 30, cy + vy * 30)
        end_pos = (cx + vx * self.length, cy + vy * self.length)
        return start_pos, end_pos

    def draw(self, surface: pygame.Surface):
        if self.dead: return
        
        p1, p2 = self.get_line()
        
        # Pulsação visual
        import time
        pulse = (pygame.time.get_ticks() % 100) / 100.0
        current_width = self.width + int(pulse * 6)
        
        # Brilho externo (Roxo/Azul)
        temp_surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        pygame.draw.line(temp_surf, (150, 0, 255, 160), p1, p2, current_width + 8)
        surface.blit(temp_surf, (0, 0))
        
        # Núcleo brilhante (Branco/Ciano)
        pygame.draw.line(surface, (200, 255, 255), p1, p2, current_width // 2)
        pygame.draw.line(surface, (255, 255, 255), p1, p2, 2)
