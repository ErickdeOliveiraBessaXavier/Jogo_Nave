import math
import random
from typing import Any, Dict, List, Tuple

import pygame

from .base import Background


class VolcanicBackground(Background):
    """Background vulcânico em caverna com parallax, estalactites, estalagmites irregulares, colunas e lava."""

    # Constantes da Lava e Brasas
    NUM_LAVA_POOLS = 3
    NUM_EMBERS = 40
    WAVE_SPEED = 2.0
    LAVA_RESOLUTION = 20

    def __init__(self, width: int, height: int):
        super().__init__(width, height)
        self.lava_pools: List[Dict[str, Any]] = []
        self.embers: List[Dict[str, Any]] = []
        self.wave_offset: float = 0.0

        # Camadas de Parallax
        self.layers: List[Dict[str, Any]] = []

        self._create_layers()
        self._create_lava()
        self._create_embers()

    def _create_layers(self) -> None:
        """Cria as camadas com base na referência: fundos claros/lentos, frentes escuras/rápidas."""
        # Paleta de cores inspirada na imagem (do fundo claro para a frente escura)
        layer_configs: List[Dict[str, Any]] = [
            # Camada de Fundo (Luz da caverna)
            {"speed": 10.0, "color": (198, 176, 137), "num_objects": 12, "base_thickness": 15},
            # Camada Intermediária
            {"speed": 25.0, "color": (142, 114, 88), "num_objects": 9, "base_thickness": 35},
            # Camada Frontal (Silhueta escura)
            {"speed": 55.0, "color": (75, 50, 45), "num_objects": 6, "base_thickness": 60},
        ]

        for config in layer_configs:
            objects: List[Dict[str, Any]] = []
            spacing = self.width / config["num_objects"]
            
            for i in range(config["num_objects"]):
                start_x = i * spacing + random.uniform(-40, 40)
                objects.append(self._generate_cave_object(start_x))

            self.layers.append({
                "speed": config["speed"],
                "color": config["color"],
                "base_thickness": config["base_thickness"],
                "objects": objects
            })

    def _generate_cave_object(self, start_x: float) -> Dict[str, Any]:
        """Gera polígonos irregulares para simular rochas realistas da imagem."""
        obj_type = random.choices(["stalactite", "stalagmite", "column"], weights=[4, 4, 2])[0]
        width = random.randint(60, 180)
        height = random.randint(100, self.height - 150)
        
        # Gerar pontos irregulares para quebrar a forma geométrica perfeita
        points_offsets: List[Tuple[float, float]] = []
        segments = random.randint(3, 6) # Quantidade de "pontas" ou irregularidades
        
        if obj_type == "stalactite":
            points_offsets.append((0, 0))
            for j in range(1, segments):
                px = (width / segments) * j
                # Cria a ponta principal no meio, e menores dos lados
                py = height * random.uniform(0.6, 1.0) if j == segments // 2 else height * random.uniform(0.1, 0.5)
                points_offsets.append((px, py))
            points_offsets.append((width, 0))

        elif obj_type == "stalagmite":
            points_offsets.append((0, self.height))
            for j in range(1, segments):
                px = (width / segments) * j
                py_offset = height * random.uniform(0.6, 1.0) if j == segments // 2 else height * random.uniform(0.1, 0.5)
                points_offsets.append((px, self.height - py_offset))
            points_offsets.append((width, self.height))

        elif obj_type == "column":
            # Colunas com bordas irregulares simulando junção
            points_offsets = [
                (0, 0), 
                (width * random.uniform(0.2, 0.4), self.height * 0.5), 
                (0, self.height),
                (width, self.height), 
                (width * random.uniform(0.6, 0.8), self.height * 0.5), 
                (width, 0)
            ]

        return {
            "type": obj_type,
            "x": start_x,
            "width": width,
            "points_offsets": points_offsets
        }

    def _create_lava(self) -> None:
        """Cria pools de lava na parte inferior."""
        for _ in range(self.NUM_LAVA_POOLS):
            self.lava_pools.append({
                "y": self.height - random.randint(20, 60),
                "amplitude": random.randint(5, 12),
                "frequency": random.uniform(0.5, 1.2),
                "phase": random.uniform(0, 6.28),
            })

    def _create_embers(self) -> None:
        """Brasas subindo."""
        for _ in range(self.NUM_EMBERS):
            self.embers.append({
                "x": random.randint(0, self.width),
                "y": random.randint(self.height - 100, self.height),
                "speed": random.uniform(15, 60),
                "size": random.randint(2, 4),
                "brightness": random.uniform(0.5, 1.0),
            })

    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        """Atualiza físicas de scroll, lava e partículas."""
        self.wave_offset += dt * self.WAVE_SPEED * speed_mult

        # Scroll do Parallax
        for layer in self.layers:
            scroll_speed = layer["speed"] * dt * speed_mult
            objects = layer["objects"]
            # Borda direita do objeto mais distante — calculada uma vez por
            # camada (O(n)); atualizada a cada wrap dentro do loop.
            rightmost = max(o["x"] + o["width"] for o in objects)
            
            for obj in layer["objects"]:
                obj["x"] -= scroll_speed

                if obj["x"] + obj["width"] < -50:
                    # Reaparece à direita do mais distante, medindo pela borda
                    # direita (x + width) — larguras variadas não se sobrepõem.
                    new_x = max(rightmost + random.randint(20, 100), self.width)
                    new_obj = self._generate_cave_object(new_x)
                    obj["x"] = new_x
                    obj["points_offsets"] = new_obj["points_offsets"]
                    obj["width"] = new_obj["width"]
                    obj["type"] = new_obj["type"]
                    # Avança a borda p/ o próximo wrap no mesmo frame não colidir.
                    rightmost = new_x + new_obj["width"]

        # Brasas
        for ember in self.embers:
            ember["y"] -= ember["speed"] * dt * speed_mult
            ember["x"] += math.sin(ember["y"] / 15) * 0.8  # Movimento orgânico

            if ember["y"] < self.height - 200: # Somem antes de chegar no topo
                ember["y"] = self.height + 10
                ember["x"] = random.randint(0, self.width)

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha com base na referência visual: fundo claro, camadas contínuas."""
        # Fundo base bem claro e amarelado (simulando a luz distante da caverna)
        surface.fill((235, 222, 170))

        # 1. Desenhar as camadas de rocha
        for layer in self.layers:
            color = layer["color"]
            
            # Base sólida no teto e no chão para que as rochas não flutuem (como na imagem)
            pygame.draw.rect(surface, color, (0, 0, self.width, layer["base_thickness"]))
            pygame.draw.rect(surface, color, (0, self.height - layer["base_thickness"] + 20, self.width, layer["base_thickness"]))

            # Desenhar as formações irregulares
            for obj in layer["objects"]:
                x_offset = obj["x"]
                
                # Traduz as coordenadas relativas da rocha para a posição 'x' atual no mundo
                world_points = [(px + x_offset, py) for px, py in obj["points_offsets"]]
                pygame.draw.polygon(surface, color, world_points)

        # 2. Desenhar a lava (apenas na parte mais inferior)
        for pool in self.lava_pools:
            points = self._calculate_lava_wave(pool)
            if len(points) >= 3:
                pygame.draw.polygon(surface, (210, 60, 10), points)
                pygame.draw.polygon(surface, (255, 120, 0), points, 2)

        # 3. Desenhar brasas com leve brilho
        for ember in self.embers:
            brightness = int(255 * ember["brightness"])
            color = (255, brightness, 0)
            pygame.draw.circle(
                surface, color, (int(ember["x"]), int(ember["y"])), ember["size"]
            )

    def _calculate_lava_wave(self, pool: Dict[str, Any]) -> List[Tuple[int, int]]:
        points: List[Tuple[int, int]] = []

        for x in range(0, self.width + self.LAVA_RESOLUTION, self.LAVA_RESOLUTION):
            if x > self.width: x = self.width 
            
            wave = math.sin(
                (x * pool["frequency"] / 100)
                + (self.wave_offset * pool["frequency"])
                + pool["phase"]
            )
            y = pool["y"] + wave * pool["amplitude"]
            points.append((x, int(y)))

        points.append((self.width, self.height))
        points.append((0, self.height))

        return points

    def reset(self) -> None:
        self.lava_pools.clear()
        self.embers.clear()
        self.layers.clear()
        self.wave_offset = 0.0
        
        self._create_layers()
        self._create_lava()
        self._create_embers()