"""
Backgrounds Dinâmicos para Mundos

Implementa backgrounds temáticos para cada mundo:
- Montanhas: Parallax com picos rochosos
- Cidade: Prédios cyberpunk com janelas piscantes
- Vulcânico: Lava ondulante com brasas flutuantes
- Starfield: Mantém sistema original
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
import pygame
import random
import math
import logging

logger = logging.getLogger(__name__)


class Background(ABC):
    """Classe base para backgrounds de mundos."""
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
    
    @abstractmethod
    def update(self, dt: float, speed_mult: float = 1.0):
        """Atualiza animação do background."""
        pass
    
    @abstractmethod
    def draw(self, surface: pygame.Surface):
        """Desenha o background."""
        pass
    
    @abstractmethod
    def reset(self):
        """Reseta para estado inicial."""
        pass


class MountainsBackground(Background):
    """Background de montanhas com parallax."""
    
    def __init__(self, width: int, height: int):
        super().__init__(width, height)
        self.layers: List[dict] = []
        self._create_layers()
    
    def _create_layers(self) -> None:
        """Cria 3 camadas de montanhas com parallax."""
        # Camada distante (céu/nuvens - mais clara, mais lenta)
        self.layers.append({
            'y_base': self.height * 0.4,
            'speed': 15,
            'color': (120, 100, 80),
            'peaks': self._generate_peaks(4, 80, 180),
            'offset': 0.0,
        })
        
        # Camada média
        self.layers.append({
            'y_base': self.height * 0.6,
            'speed': 35,
            'color': (90, 70, 50),
            'peaks': self._generate_peaks(6, 100, 220),
            'offset': 0.0,
        })
        
        # Camada próxima (mais escura, mais rápida)
        self.layers.append({
            'y_base': self.height * 0.75,
            'speed': 55,
            'color': (60, 45, 35),
            'peaks': self._generate_peaks(8, 120, 280),
            'offset': 0.0,
        })
    
    def _generate_peaks(self, count: int, min_height: int, max_height: int) -> List[int]:
        """Gera alturas de picos de montanha."""
        return [random.randint(min_height, max_height) for _ in range(count)]
    
    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        """Atualiza scroll parallax."""
        for layer in self.layers:
            layer['offset'] += layer['speed'] * dt * speed_mult
            # Wrap around quando completar um ciclo
            if layer['offset'] >= self.width:
                layer['offset'] -= self.width
    
    def draw(self, surface: pygame.Surface) -> None:
        """Desenha camadas de montanhas."""
        for layer in self.layers:
            points: List[Tuple[int, int]] = []
            segment_width = self.width / len(layer['peaks'])
            
            # Desenhar duas vezes para criar loop sem emendas
            for loop_offset in [0, self.width]:
                for i, peak_height in enumerate(layer['peaks']):
                    x = i * segment_width + loop_offset - layer['offset']
                    y = layer['y_base'] - peak_height
                    points.append((int(x), int(y)))
            
            # Fechar polígono embaixo
            points.append((self.width * 2, self.height))
            points.append((-self.width, self.height))
            
            # Desenhar apenas pontos visíveis
            if len(points) >= 3:
                pygame.draw.polygon(surface, layer['color'], points)
    
    def reset(self) -> None:
        """Reseta camadas para estado inicial."""
        self.layers.clear()
        self._create_layers()


class CityBackground(Background):
    """Background de cidade cyberpunk."""
    
    def __init__(self, width: int, height: int):
        super().__init__(width, height)
        self.buildings: List[dict] = []
        self.blink_timer: float = 0.0
        self._create_buildings()
    
    def _create_buildings(self) -> None:
        """Gera prédios proceduralmente."""
        x = -200  # Começar fora da tela
        while x < self.width + 400:
            width = random.randint(60, 180)
            height = random.randint(250, 550)
            neon_color = random.choice([
                (0, 255, 255),    # Cyan
                (255, 0, 255),    # Magenta
                (255, 255, 0),    # Amarelo
                (0, 255, 150),    # Verde neon
            ])
            
            self.buildings.append({
                'x': x,
                'width': width,
                'height': height,
                'neon_color': neon_color,
                'window_pattern': random.randint(0, 3),  # Padrão de janelas
            })
            
            x += width + random.randint(10, 40)
    
    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        """Scroll horizontal."""
        scroll_speed = 25 * speed_mult
        self.blink_timer += dt
        
        for building in self.buildings:
            building['x'] += scroll_speed * dt
            
            # Wrap around
            if building['x'] > self.width + 200:
                building['x'] -= (self.width + 800)
    
    def draw(self, surface: pygame.Surface) -> None:
        """Desenha cidade cyberpunk."""
        for bldg in self.buildings:
            x = int(bldg['x'])
            y = self.height - bldg['height']
            
            # Silhueta do prédio (escuro)
            pygame.draw.rect(
                surface,
                (15, 15, 30),
                (x, y, bldg['width'], bldg['height'])
            )
            
            # Borda neon
            pygame.draw.rect(
                surface,
                bldg['neon_color'],
                (x, y, bldg['width'], bldg['height']),
                2
            )
            
            # Janelas iluminadas
            window_w = 12
            window_h = 20
            spacing = 25
            
            for wy in range(y + 30, y + bldg['height'] - 30, spacing + window_h):
                for wx in range(x + 15, x + bldg['width'] - 15, spacing):
                    # Padrão de piscar baseado em tempo + posição
                    blink_offset = (wx + wy) % 100
                    should_be_lit = (int(self.blink_timer * 100) + blink_offset) % 200 < 150
                    
                    if should_be_lit:
                        color = (255, 255, 200)  # Branco quente
                    else:
                        color = (40, 40, 60)  # Apagado
                    
                    pygame.draw.rect(surface, color, (wx, wy, window_w, window_h))
    
    def reset(self) -> None:
        """Reseta cidade para estado inicial."""
        self.buildings.clear()
        self.blink_timer = 0.0
        self._create_buildings()


class VolcanicBackground(Background):
    """Background vulcânico com lava."""
    
    def __init__(self, width: int, height: int):
        super().__init__(width, height)
        self.lava_pools: List[dict] = []
        self.embers: List[dict] = []
        self.wave_offset: float = 0.0
        self._create_lava()
        self._create_embers()
    
    def _create_lava(self) -> None:
        """Cria pools de lava no chão."""
        for _ in range(3):
            self.lava_pools.append({
                'y': self.height - random.randint(50, 150),
                'amplitude': random.randint(5, 15),
                'frequency': random.uniform(0.5, 1.5),
                'phase': random.uniform(0, 6.28),
            })
    
    def _create_embers(self) -> None:
        """Cria partículas de brasa."""
        for _ in range(40):
            self.embers.append({
                'x': random.randint(0, self.width),
                'y': random.randint(0, self.height),
                'speed': random.uniform(20, 80),
                'size': random.randint(2, 5),
                'brightness': random.uniform(0.5, 1.0),
            })
    
    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        """Atualiza animação de lava e brasas."""
        self.wave_offset += dt * 2
        
        # Atualizar brasas (sobem)
        for ember in self.embers:
            ember['y'] -= ember['speed'] * dt * speed_mult
            
            # Resetar se sair da tela
            if ember['y'] < -10:
                ember['y'] = self.height + 10
                ember['x'] = random.randint(0, self.width)
    
    def draw(self, surface: pygame.Surface) -> None:
        """Desenha cenário vulcânico."""
        # Lava no chão (ondulante)
        for pool in self.lava_pools:
            points: List[Tuple[int, int]] = []
            for x in range(0, self.width, 20):
                wave = math.sin(
                    (x * pool['frequency'] / 100) + 
                    (self.wave_offset * pool['frequency']) + 
                    pool['phase']
                )
                y = pool['y'] + wave * pool['amplitude']
                points.append((x, int(y)))
            
            points.append((self.width, self.height))
            points.append((0, self.height))
            
            # Gradiente de lava (simulado com polígono)
            if len(points) >= 3:
                pygame.draw.polygon(surface, (200, 50, 0), points)
                pygame.draw.polygon(surface, (255, 100, 0), points, 3)
        
        # Brasas flutuantes
        for ember in self.embers:
            brightness = int(255 * ember['brightness'])
            color = (brightness, brightness // 3, 0)
            pygame.draw.circle(
                surface,
                color,
                (int(ember['x']), int(ember['y'])),
                ember['size']
            )
    
    def reset(self) -> None:
        """Reseta vulcão para estado inicial."""
        self.lava_pools.clear()
        self.embers.clear()
        self.wave_offset = 0.0
        self._create_lava()
        self._create_embers()
