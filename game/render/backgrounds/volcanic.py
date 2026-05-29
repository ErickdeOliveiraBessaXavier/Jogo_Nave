import math
import random
from typing import Any, Dict, List, Tuple

import pygame

from .base import Background


class VolcanicBackground(Background):
    """Background vulcânico em caverna com parallax, estalactites, estalagmites irregulares, colunas e lava."""

    # Constantes da Lava e Brasas
    NUM_LAVA_POOLS = 3
    NUM_EMBERS = 60
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
        """Camadas de parallax: fundo mais claro/lento → frente escura/rápida.

        4 camadas (antes 6): em ordem painter as traseiras ficavam quase
        totalmente cobertas pelas frontais — overdraw puro. 4 dão o mesmo
        gradiente com ~1/3 menos draw calls e fill rate.
        """
        layer_configs: List[Dict[str, Any]] = [
            {"speed": 12.0, "color": (50, 18, 9), "num_objects": 10, "base_thickness": 40},
            {"speed": 35.0, "color": (35, 12, 5), "num_objects": 8, "base_thickness": 70},
            {"speed": 80.0, "color": (22, 9, 2), "num_objects": 5, "base_thickness": 110},
            {"speed": 180.0, "color": (8, 3, 0), "num_objects": 3, "base_thickness": 150},
        ]

        for config in layer_configs:
            objects: List[Dict[str, Any]] = []
            spacing = self.width / config["num_objects"]

            for i in range(config["num_objects"]):
                start_x = i * spacing + random.uniform(-40, 40)
                objects.append(self._generate_cave_object(start_x, config["speed"]))

            # Terreno irregular para teto e chão
            terrain_res = 50  # Distância entre pontos do terreno
            num_points = int(self.width / terrain_res) + 4
            base = config["base_thickness"]
            ceiling_terrain = [random.uniform(0.6, 1.4) * base for _ in range(num_points)]
            floor_terrain = [random.uniform(0.6, 1.4) * base for _ in range(num_points)]

            # Buffers de pontos reutilizados no draw (evita realocar a lista por
            # frame — §7). Os 2 pontos finais (cantos de fechamento) são fixos.
            ceiling_buf: List[Tuple[float, float]] = [(0.0, 0.0)] * (num_points + 2)
            ceiling_buf[num_points] = (self.width + 100, -100)
            ceiling_buf[num_points + 1] = (-100, -100)
            floor_buf: List[Tuple[float, float]] = [(0.0, 0.0)] * (num_points + 2)
            floor_buf[num_points] = (self.width + 100, self.height + 100)
            floor_buf[num_points + 1] = (-100, self.height + 100)

            self.layers.append({
                "speed": config["speed"],
                "color": config["color"],
                "base_thickness": base,
                "objects": objects,
                "ceiling_terrain": ceiling_terrain,
                "floor_terrain": floor_terrain,
                "ceiling_buf": ceiling_buf,
                "floor_buf": floor_buf,
                "num_points": num_points,
                "terrain_x": 0.0,
                "terrain_res": terrain_res,
            })

    def _generate_cave_object(self, start_x: float, speed: float = 0.0) -> Dict[str, Any]:
        """Gera polígonos irregulares para simular rochas realistas. 
        O tamanho escala significativamente com a velocidade (camada)."""
        obj_type = random.choices(["stalactite", "stalagmite", "column"], weights=[4, 4, 2])[0]
        
        # Escalar tamanho baseado na camada (speed maior = mais perto = maior)
        # Aumentado para evitar o efeito "achatado"
        scale = 1.0 + (speed / 150.0) 
        width = int(random.randint(70, 200) * scale)
        # Altura mais agressiva para ocupar o espaço vertical
        height = int(random.randint(150, self.height - 100) * (0.4 + scale * 0.6))
        
        # Gerar pontos irregulares
        points_offsets: List[Tuple[float, float]] = []
        segments = random.randint(4, 8)
        
        if obj_type == "stalactite":
            points_offsets.append((0, 0))
            for j in range(1, segments):
                px = (width / segments) * j
                # Ponta principal e secundárias
                py = height * random.uniform(0.7, 1.1) if j == segments // 2 else height * random.uniform(0.1, 0.7)
                points_offsets.append((px, py))
            points_offsets.append((width, 0))

        elif obj_type == "stalagmite":
            points_offsets.append((0, self.height))
            for j in range(1, segments):
                px = (width / segments) * j
                py_offset = height * random.uniform(0.7, 1.1) if j == segments // 2 else height * random.uniform(0.1, 0.7)
                points_offsets.append((px, self.height - py_offset))
            points_offsets.append((width, self.height))

        elif obj_type == "column":
            # Colunas mais orgânicas e "grossas"
            mid_w_left = width * random.uniform(0.2, 0.5)
            mid_w_right = width * random.uniform(0.5, 0.8)
            points_offsets = [
                (0, 0), 
                (mid_w_left, self.height * 0.3),
                (mid_w_left * 0.8, self.height * 0.7),
                (0, self.height),
                (width, self.height), 
                (mid_w_right * 1.2, self.height * 0.7),
                (mid_w_right, self.height * 0.3),
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
        """Brasas flutuantes subindo pela tela inteira (efeito clássico)."""
        for _ in range(self.NUM_EMBERS):
            self.embers.append({
                "x": random.randint(0, self.width),
                "y": random.randint(0, self.height),
                "speed": random.uniform(20, 80),
                "size": random.randint(2, 5),
                "brightness": random.uniform(0.5, 1.0),
            })

    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        """Atualiza físicas de scroll, lava e partículas."""
        self.wave_offset += dt * self.WAVE_SPEED * speed_mult

        # Scroll do Parallax
        for layer in self.layers:
            scroll_speed = layer["speed"] * dt * speed_mult
            
            # Scroll do terreno. `while` (não `if`): no warp do "entering" o
            # scroll de um frame pode passar de vários `terrain_res`; com `if` o
            # terrain_x afundava sem voltar ao intervalo e o terreno dessincronizava
            # (a camada mais rápida "não acompanhava"). O while alcança todos os
            # passos pendentes no mesmo frame.
            layer["terrain_x"] -= scroll_speed
            base = layer["base_thickness"]
            while layer["terrain_x"] <= -layer["terrain_res"]:
                layer["terrain_x"] += layer["terrain_res"]
                layer["ceiling_terrain"].pop(0)
                layer["ceiling_terrain"].append(random.uniform(0.6, 1.4) * base)
                layer["floor_terrain"].pop(0)
                layer["floor_terrain"].append(random.uniform(0.6, 1.4) * base)

            objects = layer["objects"]
            # Borda direita do objeto mais distante
            rightmost = max(o["x"] + o["width"] for o in objects) if objects else self.width
            
            for obj in objects:
                obj["x"] -= scroll_speed

                if obj["x"] + obj["width"] < -100:
                    new_x = max(rightmost + random.randint(20, 150), self.width)
                    new_obj = self._generate_cave_object(new_x, layer["speed"])
                    obj["x"] = new_x
                    obj["points_offsets"] = new_obj["points_offsets"]
                    obj["width"] = new_obj["width"]
                    obj["type"] = new_obj["type"]
                    rightmost = new_x + new_obj["width"]

        # Brasas: sobem pela tela inteira e reaparecem embaixo (como antes).
        for ember in self.embers:
            ember["y"] -= ember["speed"] * dt * speed_mult
            if ember["y"] < -10:
                ember["y"] = self.height + 10
                ember["x"] = random.randint(0, self.width)

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha o ambiente: rocha (parallax) ao fundo, lava no piso à frente."""
        # Fundo base bem escuro
        surface.fill((10, 5, 2))

        # 1. Camadas de parallax (teto, chão e formações de rocha)
        for layer in self.layers:
            self._draw_layer_elements(surface, layer)

        # 2. Lava no piso, desenhada À FRENTE da rocha (senão o terreno do chão
        #    das camadas frontais, que desce até a base da tela, cobria a lava).
        #    A camada escura do parallax encosta no limite inferior; a lava fica
        #    direto contra ela, sem faixa de "chão" intermediária.
        for pool in self.lava_pools:
            points = self._calculate_lava_wave(pool)
            if len(points) >= 3:
                pygame.draw.polygon(surface, (210, 60, 10), points)
                pygame.draw.polygon(surface, (255, 120, 0), points, 2)

        # 3. Brasas por cima de tudo (cor alaranjada do efeito clássico)
        for ember in self.embers:
            brightness = int(255 * ember["brightness"])
            color = (brightness, brightness // 3, 0)
            pygame.draw.circle(
                surface, color, (int(ember["x"]), int(ember["y"])), ember["size"]
            )

    def _draw_layer_elements(self, surface: pygame.Surface, layer: Dict[str, Any]) -> None:
        """Desenha os elementos de uma camada (teto, chão e formações)."""
        draw_poly = pygame.draw.polygon  # bind local — chamado várias vezes (§7)
        color = layer["color"]
        tx = layer["terrain_x"]
        tres = layer["terrain_res"]
        n = layer["num_points"]
        h = self.height

        # Teto e chão: escreve nos buffers persistentes in-place (sem realocar
        # a lista nem recriar os pontos de fechamento).
        ceil_buf = layer["ceiling_buf"]
        floor_buf = layer["floor_buf"]
        ceil_t = layer["ceiling_terrain"]
        floor_t = layer["floor_terrain"]
        for i in range(n):
            x = tx + i * tres
            ceil_buf[i] = (x, ceil_t[i])
            floor_buf[i] = (x, h - floor_t[i])
        draw_poly(surface, color, ceil_buf)
        draw_poly(surface, color, floor_buf)

        # Formações (estalactites, estalagmites, colunas)
        for obj in layer["objects"]:
            x_offset = obj["x"]
            world_points = [(px + x_offset, py) for px, py in obj["points_offsets"]]
            draw_poly(surface, color, world_points)

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