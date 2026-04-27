from __future__ import annotations

import math
import random
from enum import Enum, auto
from typing import Final

import pygame

from ..core.config import config as Config


class _PropellerState(Enum):
    ENTERING = auto()
    PATROLLING = auto()
    WIND_UP = auto()
    BLOWING = auto()
    COOLDOWN = auto()


class MountainPropeller:
    """
    Inimigo de suporte das Cordilheiras.
    Fica na borda direita, movendo-se verticalmente.
    Cria uma corrente de vento que empurra o jogador para a esquerda e o torna lento.
    """

    # Equilíbrio e Timing
    WIND_DURATION: Final = 3.5
    WIND_UP_TIME: Final = 1.2
    COOLDOWN_TIME: Final = 3.0
    
    # Física do Vento
    PUSH_FORCE: Final = 220.0  # Pixels/seg para a esquerda
    SLOW_SPEED_MULT: Final = 0.45  # Velocidade do jogador = 45% do normal
    
    BODY_W: Final = 42
    BODY_H: Final = 56
    EDGE_MARGIN: Final = 60

    def __init__(self, y: float | None = None):
        self.x = Config.SCREEN_WIDTH + self.BODY_W
        self.target_x = Config.SCREEN_WIDTH - self.EDGE_MARGIN
        self.y = y if y is not None else random.randint(100, Config.SCREEN_HEIGHT - 100)
        
        self.health = 6
        self.max_health = 6
        self.dead = False
        self.causes_damage = False  # O vento é o perigo, não o corpo (evita mortes injustas na borda)

        self.state = _PropellerState.ENTERING
        self.timer = 0.0
        
        self.move_speed = 140.0
        self.move_dir = random.choice([-1, 1])
        
        # Animação da Hélice
        self.prop_angle = 0.0
        self.prop_speed = 0.0  # Graus por segundo
        
        # Partículas de Vento (Riscos/Streaks)
        self.wind_streaks: list[dict] = []
        self._init_streaks()

    def _init_streaks(self):
        """Inicializa riscos de vento que cruzam a tela."""
        for _ in range(30):
            self.wind_streaks.append({
                "x": random.uniform(0, Config.SCREEN_WIDTH),
                "y_offset": random.uniform(-35, 35),
                "speed": random.uniform(900, 1400),
                "len": random.uniform(40, 100),
                "alpha": random.randint(40, 100)
            })

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(
            int(self.x - self.BODY_W // 2),
            int(self.y - self.BODY_H // 2),
            self.BODY_W,
            self.BODY_H
        )

    def is_blowing(self) -> bool:
        return self.state == _PropellerState.BLOWING

    def get_wind_rect(self) -> pygame.Rect:
        """Retorna o retângulo da corrente de vento (da hélice até a borda esquerda)."""
        if not self.is_blowing():
            return pygame.Rect(0, 0, 0, 0)
        # O vento sopra da frente da hélice (x-20) até o fim da tela à esquerda
        return pygame.Rect(0, int(self.y - 45), int(self.x - 10), 90)

    def take_damage(self, amount: int):
        self.health -= amount
        if self.health <= 0:
            self.dead = True

    def get_points_value(self) -> int:
        return 250

    def update(self, dt: float):
        self.timer += dt
        
        # FSM de Estados
        if self.state == _PropellerState.ENTERING:
            self.x -= 180 * dt
            if self.x <= self.target_x:
                self.x = self.target_x
                self.state = _PropellerState.PATROLLING
                self.timer = 0.0
                
        elif self.state == _PropellerState.PATROLLING:
            self._update_movement(dt)
            self.prop_speed = 250.0
            if self.timer > 1.8:
                self.state = _PropellerState.WIND_UP
                self.timer = 0.0
                
        elif self.state == _PropellerState.WIND_UP:
            # Desacelera movimento vertical ao carregar
            self._update_movement(dt * 0.4)
            # Acelera hélice
            progress = self.timer / self.WIND_UP_TIME
            self.prop_speed = 250.0 + (1800.0 * (progress ** 2))
            if self.timer >= self.WIND_UP_TIME:
                self.state = _PropellerState.BLOWING
                self.timer = 0.0
                
        elif self.state == _PropellerState.BLOWING:
            self.prop_speed = 2200.0
            self._update_streaks(dt)
            # Fica parado enquanto sopra para manter o foco do perigo
            if self.timer >= self.WIND_DURATION:
                self.state = _PropellerState.COOLDOWN
                self.timer = 0.0
                
        elif self.state == _PropellerState.COOLDOWN:
            self._update_movement(dt)
            progress = self.timer / 1.0
            self.prop_speed = max(250.0, 2200.0 * (1.0 - progress))
            if self.timer >= self.COOLDOWN_TIME:
                self.state = _PropellerState.PATROLLING
                self.timer = 0.0

        self.prop_angle += self.prop_speed * dt

    def _update_movement(self, dt: float):
        self.y += self.move_speed * self.move_dir * dt
        # Bounce nas bordas verticais
        if self.y < 100:
            self.y = 100
            self.move_dir = 1
        elif self.y > Config.SCREEN_HEIGHT - 100:
            self.y = Config.SCREEN_HEIGHT - 100
            self.move_dir = -1

    def _update_streaks(self, dt: float):
        for s in self.wind_streaks:
            s["x"] -= s["speed"] * dt
            if s["x"] + s["len"] < 0:
                s["x"] = self.x - 20
                s["y_offset"] = random.uniform(-40, 40)

    def draw(self, surface: pygame.Surface):
        # 1. Efeito Visual do Vento (Blur + Riscos)
        if self.is_blowing():
            self._draw_wind_effect(surface)
            
        # 2. Corpo do Inimigo (Estilo Industrial/Pedra)
        self._draw_body(surface)
        
        # 3. Hélice
        self._draw_propeller(surface)

    def _draw_wind_effect(self, surface: pygame.Surface):
        w_rect = self.get_wind_rect()
        # Camada de Blur (Várias faixas semi-transparentes)
        # Criamos uma surface temporária para o blend
        wind_surf = pygame.Surface((w_rect.width, w_rect.height), pygame.SRCALPHA)
        
        # Centro mais denso, bordas mais suaves
        for i in range(5):
            alpha = 12 - (i * 2)
            h = w_rect.height - (i * 15)
            y = (w_rect.height - h) // 2
            if h > 0:
                pygame.draw.rect(wind_surf, (220, 240, 255, alpha), (0, y, w_rect.width, h))
        
        surface.blit(wind_surf, (w_rect.x, w_rect.y))
        
        # Desenhar os Riscos (Streaks)
        for s in self.wind_streaks:
            if 0 < s["x"] < self.x:
                start = (s["x"], self.y + s["y_offset"])
                end = (s["x"] + s["len"], self.y + s["y_offset"])
                pygame.draw.line(surface, (255, 255, 255, s["alpha"]), start, end, 1)

    def _draw_body(self, surface: pygame.Surface):
        r = self.rect
        # Base principal
        pygame.draw.rect(surface, (70, 70, 85), r, border_radius=6)
        pygame.draw.rect(surface, (40, 40, 50), r, width=2, border_radius=6)
        
        # Detalhes de ventilação/grelha
        for i in range(3):
            gy = r.top + 10 + (i * 14)
            pygame.draw.line(surface, (30, 30, 40), (r.left + 8, gy), (r.right - 8, gy), 3)
            
        # Luz indicadora de estado
        light_color = (100, 255, 100) # Idle
        if self.state == _PropellerState.WIND_UP:
            light_color = (255, 150, 0) if (pygame.time.get_ticks() // 100) % 2 else (50, 30, 0)
        elif self.state == _PropellerState.BLOWING:
            light_color = (0, 200, 255)
            
        pygame.draw.circle(surface, light_color, (int(self.x), int(r.bottom - 12)), 4)

    def _draw_propeller(self, surface: pygame.Surface):
        # A hélice fica na frente (lado esquerdo do inimigo)
        px, py = self.x - 15, self.y
        num_blades = 3
        blade_length = 32
        
        for i in range(num_blades):
            angle_rad = math.radians(self.prop_angle + (i * 360 / num_blades))
            
            # Cálculo dos pontos da lâmina (triângulo alongado)
            end_x = px + math.cos(angle_rad) * blade_length
            end_y = py + math.sin(angle_rad) * blade_length
            
            # Lâmina
            pygame.draw.line(surface, (160, 160, 175), (px, py), (end_x, end_y), 5)
            # Ponta da lâmina com cor diferente
            pygame.draw.circle(surface, (200, 200, 210), (int(end_x), int(end_y)), 3)

        # Eixo central
        pygame.draw.circle(surface, (50, 50, 60), (int(px), int(py)), 8)
        pygame.draw.circle(surface, (100, 100, 110), (int(px), int(py)), 4)
