import pygame
import math
import random
from typing import Any

from ..core.config import config
from ..core.sound import sound_manager

class PlasmaBeam:
    """
    Lança de Plasma Hiper-Estabilizada:
    Um feixe que cresce em comprimento e largura, penetra tudo e 
    causa uma explosão massiva no final.
    """
    def __init__(self, ship: Any, duration: float):
        self.ship = ship
        self.duration = duration
        self.timer = duration
        self.lifetime = 0.0
        self.dead = False
        
        # Atributos dinâmicos
        self.max_length = 1200
        self.current_length = 100.0
        self.max_width = 40
        self.current_width = 4.0
        
        # Dano base por segundo (aplicado via tick no EntityManager)
        self.damage = 150.0 # Dano alto para compensar a natureza direcional
        
        # Efeitos visuais
        self.pulse_timer = 0.0
        self.particles = []
        
        # Som
        sound_manager.play_boss_laser_fire() # Reutiliza som de laser contínuo

    def update(self, dt: float):
        self.lifetime += dt
        self.timer -= dt
        self.pulse_timer += dt * 10
        
        if self.timer <= 0 or getattr(self.ship, "dead", False):
            self.dead = True
            # Se morreu por tempo, dispara explosão final no EntityManager
            return

        # Crescimento progressivo
        growth_factor = self.lifetime / self.duration
        self.current_length = min(self.max_length, 100 + self.max_length * growth_factor)
        self.current_width = min(self.max_width, 4 + self.max_width * (growth_factor ** 2))

    def get_line(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Retorna os pontos inicial e final do feixe para colisão."""
        vx, vy = 0, -1
        if hasattr(self.ship, "get_facing_vector"):
            vx, vy = self.ship.get_facing_vector()
        
        p1 = (self.ship.x + self.ship.w / 2, self.ship.y + self.ship.h / 2)
        p2 = (p1[0] + vx * self.current_length, p1[1] + vy * self.current_length)
        return p1, p2

    def draw(self, surface: pygame.Surface):
        p1, p2 = self.get_line()
        
        # Pulsação visual
        pulse = math.sin(self.pulse_timer) * 5
        draw_width = max(2, int(self.current_width + pulse))
        
        # 1. Glow Externo (Azul Profundo/Roxo)
        for i in range(3, 0, -1):
            alpha = 50 + (i * 30)
            color = (50, 0, 255, alpha)
            glow_width = draw_width + (i * 8)
            
            # Criar surface temporária para alpha se necessário, mas para linhas síncronas 
            # costumamos desenhar direto com larguras variadas
            pygame.draw.line(surface, color[:3], p1, p2, glow_width)

        # 2. Feixe Principal (Ciano Brilhante)
        pygame.draw.line(surface, (0, 200, 255), p1, p2, draw_width)
        
        # 3. Núcleo (Branco)
        pygame.draw.line(surface, (255, 255, 255), p1, p2, max(1, draw_width // 3))
        
        # 4. Partículas de energia na ponta e na base
        self._draw_energy_sparks(surface, p1, p2)

    def _draw_energy_sparks(self, surface: pygame.Surface, p1, p2):
        # Faíscas na ponta da lança
        for _ in range(3):
            angle = random.uniform(0, math.pi * 2)
            dist = random.uniform(0, self.current_width)
            offset_x = math.cos(angle) * dist
            offset_y = math.sin(angle) * dist
            size = random.randint(2, 5)
            pygame.draw.circle(surface, (200, 255, 255), (int(p2[0] + offset_x), int(p2[1] + offset_y)), size)

    def trigger_final_explosion(self, entity_manager: Any):
        """Chamado pelo EntityManager quando o feixe expira."""
        p1, p2 = self.get_line()
        # Explosão massiva na ponta da lança
        if hasattr(entity_manager, "spawn_explosion"):
            entity_manager.spawn_explosion(p2[0], p2[1], size=180) # Aumentado
            # Dano em área na explosão final
            for e in entity_manager._cached_all_enemies:
                if not getattr(e, "dead", False):
                    dx = e.x + getattr(e, "w", 0)/2 - p2[0]
                    dy = e.y + getattr(e, "h", 0)/2 - p2[1]
                    if (dx*dx + dy*dy) < 180*180:
                        if hasattr(e, "take_damage"): e.take_damage(400)
                        elif hasattr(e, "lives"): 
                             current = getattr(e, "lives")
                             setattr(e, "lives", current - 400)
