import math
from typing import Any, Tuple, Set

import pygame

class CoopLink:
    """Feixe de energia que conecta dois jogadores e causa dano a inimigos que o atravessam."""
    
    def __init__(self, ship1: Any, ship2: Any, duration: float):
        self.ship1 = ship1
        self.ship2 = ship2
        self.timer = duration
        self.dead = False
        self.damage = 250  # Dano por segundo (aplicado via dt)
        self.w = 6.0
        
        # Para evitar causar dano múltiplo no mesmo inimigo no mesmo frame (se necessário)
        # Mas feixes contínuos geralmente aplicam dano por dt
        self.hit_enemies: Set[int] = set()

    def update(self, dt: float):
        self.timer -= dt
        if self.timer <= 0 or getattr(self.ship1, "dead", False) or getattr(self.ship2, "dead", False):
            self.dead = True
        
        # Verifica se as naves ainda são válidas (não estão explodindo/removidas)
        if not hasattr(self.ship1, "x") or not hasattr(self.ship2, "x"):
            self.dead = True

    def get_collision_line(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        p1 = (self.ship1.x + self.ship1.w / 2, self.ship1.y + self.ship1.h / 2)
        p2 = (self.ship2.x + self.ship2.w / 2, self.ship2.y + self.ship2.h / 2)
        return p1, p2

    def draw(self, surface: pygame.Surface):
        if self.dead:
            return
            
        p1, p2 = self.get_collision_line()
        
        # Efeito de pulsação
        pulse = math.sin(pygame.time.get_ticks() * 0.03) * 3
        width = int(self.w + pulse)
        
        # Brilho externo ciano/azul
        glow_color = (0, 255, 255, 130)
        # Pygame line não suporta alpha diretamente em surfaces sem SRCALPHA
        # Vamos desenhar o brilho
        temp_surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        pygame.draw.line(temp_surf, glow_color, p1, p2, width + 6)
        surface.blit(temp_surf, (0, 0))
        
        # Núcleo branco
        pygame.draw.line(surface, (255, 255, 255), p1, p2, max(1, width // 2))
        
        # Arcos elétricos aleatórios ao redor do feixe
        if width > 4:
            self._draw_arcs(surface, p1, p2)

    def _draw_arcs(self, surface: pygame.Surface, p1: Tuple[float, float], p2: Tuple[float, float]):
        import random
        num_arcs = 3
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dist = math.hypot(dx, dy)
        if dist < 10: return
        
        for _ in range(num_arcs):
            points = [p1]
            segments = 5
            for i in range(1, segments):
                f = i / segments
                # Ponto na linha
                lx = p1[0] + dx * f
                ly = p1[1] + dy * f
                # Desvio perpendicular
                offset = random.uniform(-15, 15)
                # Vetor perpendicular
                px, py = -dy/dist, dx/dist
                points.append((lx + px * offset, ly + py * offset))
            points.append(p2)
            pygame.draw.lines(surface, (200, 255, 255), False, points, 1)
