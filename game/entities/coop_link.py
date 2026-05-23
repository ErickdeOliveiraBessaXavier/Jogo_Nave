import math
import random
from typing import Any, Tuple, List

import pygame

class CoopLink:
    """
    Feixe de energia que conecta dois jogadores.
    Design aprimorado com distorção de ruído, pulsação e arcos de alta voltagem.
    """
    
    def __init__(self, ship1: Any, ship2: Any, duration: float):
        self.ship1 = ship1
        self.ship2 = ship2
        self.timer = duration
        self.dead = False
        self.damage = 300  # Dano por segundo (Aumentado para ser mais recompensador no coop)
        self.base_width = 8.0
        
        self.pulse_timer = 0.0
        self.noise_timer = 0.0
        self._noise_offsets: List[float] = [random.uniform(0, 100) for _ in range(10)]

    def update(self, dt: float):
        self.timer -= dt
        self.pulse_timer += dt * 15
        self.noise_timer += dt * 25
        
        if self.timer <= 0 or getattr(self.ship1, "dead", False) or getattr(self.ship2, "dead", False):
            self.dead = True
        
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
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dist = math.hypot(dx, dy)
        if dist < 10: return
        
        # 1. Glow Externo (Aura Pulsante)
        pulse = math.sin(self.pulse_timer) * 0.3 + 0.7
        glow_width = int(self.base_width * 2.5 * pulse)
        
        # Desenhar aura sutil (Ciano Escuro)
        pygame.draw.line(surface, (0, 100, 200), p1, p2, glow_width + 4)
        
        # 2. Arcos de Alta Voltagem (Distorção irregular)
        self._draw_electricity(surface, p1, p2, dx, dy, dist)
        
        # 3. Núcleo de Plasma (Ciano Brilhante)
        core_w = max(2, int(self.base_width * 0.6 * pulse))
        pygame.draw.line(surface, (0, 255, 255), p1, p2, core_w)
        
        # 4. Centro Estabilizado (Branco Puro)
        pygame.draw.line(surface, (255, 255, 255), p1, p2, max(1, core_w // 3))
        
        # 5. Partículas de energia nas naves (Nódulos de conexão)
        for ship in [self.ship1, self.ship2]:
            cx, cy = ship.x + ship.w/2, ship.y + ship.h/2
            r = int(10 * pulse)
            pygame.draw.circle(surface, (255, 255, 255), (int(cx), int(cy)), r, 1)

    def _draw_electricity(self, surface: pygame.Surface, p1: tuple[float, float], p2: tuple[float, float], dx: float, dy: float, dist: float):
        # Gera uma linha quebrada que oscila rapidamente
        segments = 8
        pts = [p1]
        
        # Vetor perpendicular para o offset
        px, py = -dy/dist, dx/dist
        
        for i in range(1, segments):
            f = i / segments
            lx = p1[0] + dx * f
            ly = p1[1] + dy * f
            
            # Ruído baseado no tempo para um efeito de "fio vivo"
            noise = math.sin(self.noise_timer + i * 0.8) * 12
            pts.append((lx + px * noise, ly + py * noise))
            
        pts.append(p2)
        pygame.draw.lines(surface, (200, 255, 255), False, pts, 2)
