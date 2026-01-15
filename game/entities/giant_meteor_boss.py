import random
import pygame
from typing import TYPE_CHECKING, TypedDict

from ..core.config import config as Config
from ..core import colors

if TYPE_CHECKING:
    from ..systems.entity_manager import EntityManager


class CrackPosition(TypedDict):
    """Dados de uma posição de rachadura."""

    edge_idx: int
    start_x: float
    start_y: float
    dir_x: float
    dir_y: float
    perp_x: float
    perp_y: float
    base_width: float


class GiantMeteorBoss:
    """Boss simples: um meteoro gigante caindo lentamente.

    - Move apenas no eixo Y, entrando pela parte superior.
    - Recebe dano de balas; ao ser atingido, pode soltar pequenos fragmentos.
    - Ao morrer, dispara uma grande explosão (controlada pelas colisões).
    """

    def __init__(self, x: float, y: float):
        # Tamanho grande, com overflow proposital para efeito visual impactante
        self.w = int(Config.SCREEN_WIDTH * 1.3)  # 30% maior que a tela
        self.h = Config.GIANT_METEOR_BOSS_HEIGHT
        self.x = -int(Config.SCREEN_WIDTH * 0.15)  # Centralizar o overflow
        self.y = -self.h - 100  # Criado bem fora da tela (100px acima)
        # Ajustar target_y para mostrar apenas 30% do meteoro (70% fica escondido acima)
        self.target_y = -self.h * 0.7

        self.health = Config.GIANT_METEOR_BOSS_HEALTH
        self.max_health = self.health
        self.dead = False

        self.entry_speed = Config.GIANT_METEOR_BOSS_ENTRY_SPEED
        self.speed = Config.GIANT_METEOR_BOSS_FALL_SPEED

        # Estado
        self.state = "entering"  # entering -> falling -> dying

        # Timer para spawn de meteoros normais durante a luta
        self.meteor_spawn_timer = 0.0
        self.meteor_spawn_interval = 2.0  # Spawn a cada 2 segundos

        # Cache para evitar recálculos desnecessários da forma
        self._last_damage_stage = -1  # -1 significa não inicializado

        # Sistema de transição suave entre formas
        self._transition_timer = 0.0
        self._transition_duration = 0.3  # 0.3 segundos para transição
        self._old_shape: list[tuple[float, float]] | None = None
        self._target_shape: list[tuple[float, float]] | None = None

        # Sistema de tremor nas transições
        self._shake_timer = 0.0
        self._shake_duration = 0.5  # 0.5 segundos de tremor
        self._shake_intensity = 8.0  # Intensidade máxima do tremor

        # Gerar forma irregular fixa (não muda a cada frame)
        self._base_shape = self._generate_base_shape()
        self._current_shape = self._base_shape.copy()

        # Posições fixas de TODAS as rachaduras possíveis (geradas uma vez no início)
        # Cada rachadura tem uma "idade" que determina quando ela aparece
        self._all_crack_positions: list[CrackPosition] = self._generate_all_crack_positions()
        
        # Histórico de crescimento: {crack_index: stage_when_born}
        self._crack_birth_stage: dict[int, int] = {}

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def _interpolate_shapes(
        self, shape1: list[tuple[float, float]], shape2: list[tuple[float, float]], t: float
    ) -> list[tuple[float, float]]:
        """Interpola suavemente entre duas formas.
        
        Args:
            shape1: Forma inicial
            shape2: Forma final
            t: Fator de interpolação (0.0 = shape1, 1.0 = shape2)
            
        Returns:
            Forma interpolada
        """
        if len(shape1) != len(shape2):
            # Se as formas têm tamanhos diferentes, usar a mais recente
            return shape2 if t > 0.5 else shape1
            
        interpolated: list[tuple[float, float]] = []
        for i in range(len(shape1)):
            x1, y1 = shape1[i]
            x2, y2 = shape2[i]
            # Interpolação linear
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            interpolated.append((x, y))
        
        return interpolated

    def _generate_base_shape(self) -> list[tuple[float, float]]:
        """Gera a forma base irregular do meteoro."""
        points: list[tuple[float, float]] = []
        segments = 20

        # Borda superior
        for i in range(segments + 1):
            x = i * self.w / segments
            y = random.uniform(-8, 8)
            points.append((x, y))

        # Borda direita
        for i in range(1, segments + 1):
            x = self.w + random.uniform(-8, 8)
            y = i * self.h / segments
            points.append((x, y))

        # Borda inferior
        for i in range(segments, -1, -1):
            x = i * self.w / segments
            y = self.h + random.uniform(-8, 8)
            points.append((x, y))

        # Borda esquerda
        for i in range(segments - 1, 0, -1):
            x = random.uniform(-8, 8)
            y = i * self.h / segments
            points.append((x, y))

        return points

    def _generate_all_crack_positions(self) -> list[CrackPosition]:
        """Gera TODAS as posições de rachaduras possíveis que vão aparecer progressivamente."""
        rng = random.Random(42)  # Seed fixa para consistência
        crack_positions: list[CrackPosition] = []

        # Total de rachaduras ao longo de todos os estágios (25-30 rachaduras no total)
        num_total_cracks = rng.randint(25, 30)

        # Centro do meteoro
        cx = self.w * 0.5
        cy = self.h * 0.5

        for _ in range(num_total_cracks):
            # Escolher um ponto na borda
            edge_point_idx = rng.randint(0, len(self._base_shape) - 1)
            base_x, base_y = self._base_shape[edge_point_idx]

            # Adicionar variação aleatória à posição inicial (até 18px em cada direção)
            start_x = base_x + rng.uniform(-18, 18)
            start_y = base_y + rng.uniform(-18, 18)

            # Direção da rachadura (da borda para o centro)
            to_center_x = cx - start_x
            to_center_y = cy - start_y
            center_dist = (to_center_x**2 + to_center_y**2) ** 0.5

            if center_dist == 0:
                continue

            # Vetor unitário apontando para o centro
            dir_x = to_center_x / center_dist
            dir_y = to_center_y / center_dist

            # Vetor perpendicular (para criar a largura da rachadura)
            perp_x = -dir_y
            perp_y = dir_x

            # Largura base da rachadura (valores maiores para garantir visibilidade)
            base_width = rng.uniform(45, 75)

            crack_positions.append(
                {
                    "edge_idx": edge_point_idx,
                    "start_x": start_x,
                    "start_y": start_y,
                    "dir_x": dir_x,
                    "dir_y": dir_y,
                    "perp_x": perp_x,
                    "perp_y": perp_y,
                    "base_width": base_width,
                }
            )

        return crack_positions

    def _normalize_vector(self, x: float, y: float) -> tuple[float, float, bool]:
        """Normaliza um vetor e retorna (x, y, valid).
        
        Returns:
            Tupla com (x_normalizado, y_normalizado, é_válido)
        """
        length = (x*x + y*y) ** 0.5
        if length < 1e-6:  # Threshold mais robusto que == 0
            return 0.0, 0.0, False
        return x / length, y / length, True

    def _apply_damage_cracks(self, health_percent: float) -> list[tuple[float, float]]:
        """Aplica rachaduras à forma base baseado no nível de dano.
        
        Rachaduras "envelhecem" e crescem com o dano, novas rachaduras aparecem menores.
        """
        if health_percent > 0.90:
            return self._base_shape.copy()

        # Determinar estágio atual (0-11, para 12 estágios)
        current_stage = min(11, int((1.0 - health_percent) * 12))

        # Definir quantas rachaduras devem estar ativas em cada estágio (distribuição mais gradual)
        # Exemplo: começa com 2, cresce até todas
        total_cracks = len(self._all_crack_positions)
        cracks_per_stage = [
            max(2, int(total_cracks * s / 12)) for s in range(12)
        ]
        cracks_per_stage[-1] = total_cracks  # Último estágio: todas as rachaduras
        num_active_cracks = cracks_per_stage[current_stage]

        # Registrar nascimento de novas rachaduras neste estágio
        # Distância mínima ABSOLUTA entre rachaduras (nunca permitir sobreposição)
        min_crack_distance = self.w * 0.08  # 8% da largura - distância mínima garantida
        
        # Tentar ativar rachaduras até atingir o número desejado
        cracks_to_activate = num_active_cracks - len(self._crack_birth_stage)
        candidate_idx = len(self._crack_birth_stage)  # Começar do próximo índice disponível
        attempts = 0  # Evitar loop infinito
        
        while cracks_to_activate > 0 and candidate_idx < len(self._all_crack_positions) and attempts < len(self._all_crack_positions) * 2:
            if candidate_idx not in self._crack_birth_stage:
                # Verificar se esta rachadura está muito próxima de QUALQUER rachadura já existente
                new_crack_pos = self._all_crack_positions[candidate_idx]
                new_x, new_y = new_crack_pos["start_x"], new_crack_pos["start_y"]
                
                too_close = False
                for active_idx in self._crack_birth_stage.keys():
                    if active_idx >= len(self._all_crack_positions):
                        continue
                    active_crack_pos = self._all_crack_positions[active_idx]
                    active_x, active_y = active_crack_pos["start_x"], active_crack_pos["start_y"]
                    
                    # Calcular distância euclidiana
                    distance = ((new_x - active_x) ** 2 + (new_y - active_y) ** 2) ** 0.5
                    if distance < min_crack_distance:
                        too_close = True
                        break
                
                # Ativar rachadura se não estiver muito próxima de nenhuma existente
                if not too_close:
                    self._crack_birth_stage[candidate_idx] = current_stage
                    cracks_to_activate -= 1
            
            candidate_idx += 1
            attempts += 1
        
        # Coletar rachaduras ativas com seus tamanhos baseados na "idade"
        all_cracks: list[tuple[int, list[tuple[float, float]]]] = []
        
        max_dimension = min(self.w, self.h) * 0.5
        
        for crack_idx in range(num_active_cracks):
            if crack_idx >= len(self._all_crack_positions):
                break
                
            crack_data = self._all_crack_positions[crack_idx]
            birth_stage = self._crack_birth_stage.get(crack_idx, current_stage)
            
            # Calcular "idade" da rachadura (quantos estágios ela viveu)
            crack_age = current_stage - birth_stage
            
            # Tamanho base da rachadura cresce com a idade
            # Rachaduras novas: 35-45% do tamanho máximo (mais visíveis)
            # Rachaduras antigas: 70-90% do tamanho máximo
            size_factor = 0.35 + (crack_age / 11.0) * 0.55  # Cresce de 0.35 até 0.90

            # Profundidade aumenta mais agressivamente com a idade (rachaduras antigas são mais profundas)
            # Rachaduras novas: 20-35% do tamanho máximo
            # Rachaduras antigas: 80-100% do tamanho máximo
            depth_min = 0.20 + (crack_age / 11.0) * 0.60  # 0.20 até 0.80
            depth_max = 0.35 + (crack_age / 11.0) * 0.65  # 0.35 até 1.00
            
            # Usar seed específica para cada rachadura para consistência de tamanho
            crack_rng = random.Random(crack_idx * 1000 + birth_stage * 100)
            crack_depth = crack_rng.uniform(depth_min, depth_max) * max_dimension
            crack_width = crack_data["base_width"] * size_factor
            
            crack_points = self._generate_crack_path(
                crack_data,
                crack_width,
                crack_depth,
                crack_rng,
                segments=10
            )
            all_cracks.append((crack_data["edge_idx"], crack_points))
        
        # Ordenar e inserir rachaduras (de trás para frente para manter índices)
        all_cracks.sort(key=lambda x: x[0], reverse=True)
        
        # Construir forma danificada de uma vez
        damaged_shape = list(self._base_shape)  # Cópia explícita
        for edge_idx, crack_points in all_cracks:
            damaged_shape[edge_idx:edge_idx+1] = crack_points
        
        return damaged_shape

    def _generate_crack_path(
        self,
        crack_data: CrackPosition | dict[str, float],
        width: float,
        depth: float,
        rng: random.Random,
        segments: int = 10
    ) -> list[tuple[float, float]]:
        """Gera caminho de rachadura com desvios orgânicos usando Perlin-like noise.
        
        Versão melhorada com:
        - Desvios mais naturais e orgânicos
        - Menos cálculos redundantes
        - Código mais limpo e legível
        """
        start_x = crack_data["start_x"]
        start_y = crack_data["start_y"]
        dir_x = crack_data["dir_x"]
        dir_y = crack_data["dir_y"]
        perp_x = crack_data["perp_x"]
        perp_y = crack_data["perp_y"]
        
        # Gerar linha central com desvios orgânicos
        center_line: list[tuple[float, float]] = []
        
        # Parâmetros para desvio orgânico
        deviation_strength = width * 0.4
        frequency = rng.uniform(2.0, 4.0)  # Frequência da "onda"
        
        for i in range(segments + 1):
            progress = i / segments
            
            # Desvio lateral usando seno (simula Perlin noise simplificado)
            angle = progress * frequency * 3.14159
            sine_component = deviation_strength * 0.3 * rng.choice([-1, 1]) * (
                0.5 + 0.5 * (1 - abs(2 * progress - 1))  # Envelope para ser maior no meio
            ) * (0.5 + 0.5 * ((angle % 6.28318) / 6.28318))  # Componente senoidal simplificado
            
            random_component = deviation_strength * 0.5 * rng.uniform(-1, 1)
            
            lateral_offset = sine_component + random_component
            
            # Posição ao longo da direção principal
            distance = depth * progress
            
            # Adicionar desvio perpendicular
            center_x = start_x + dir_x * distance + perp_x * lateral_offset
            center_y = start_y + dir_y * distance + perp_y * lateral_offset
            
            center_line.append((center_x, center_y))
        
        # Construir pontos dos lados da rachadura
        crack_points: list[tuple[float, float]] = []
        
        # Lado esquerdo
        for i in range(segments + 1):
            cx, cy = center_line[i]
            progress = i / segments
            # Largura diminui quadraticamente para efeito natural
            current_width = width * (1 - progress ** 1.5)
            
            half_w = current_width * 0.5
            crack_points.append((cx + perp_x * half_w, cy + perp_y * half_w))
        
        # Lado direito (volta ao início, pula o último ponto para evitar duplicação)
        for i in range(segments - 1, -1, -1):
            cx, cy = center_line[i]
            progress = i / segments
            current_width = width * (1 - progress ** 1.5)
            
            half_w = current_width * 0.5
            crack_points.append((cx - perp_x * half_w, cy - perp_y * half_w))
        
        return crack_points

    def take_damage(
        self, damage: int, entity_manager: "EntityManager | None" = None
    ) -> None:
        if self.dead:
            return
        self.health -= damage
        if self.health <= 0:
            self.dead = True
            self.state = "dying"
            return

        # Spawn de meteoros quando atingido (quantidade escala fortemente com estágio de dano)
        if entity_manager and self.state == "falling":
            health_percent = self.health / self.max_health
            current_stage = min(11, int((1.0 - health_percent) * 12))
            # Chance de spawn aumenta com o dano (0.1 para saúde alta, 0.5 para saúde baixa)
            spawn_chance = 0.1 + (0.4 * (1 - health_percent))

            if random.random() < spawn_chance:
                # Spawn de meteoros escala com estágio: 1 no início, até 20 no último estágio
                num_meteors = random.randint(1 + current_stage, 1 + int(current_stage * 1.2))
                for _ in range(num_meteors):
                    self._spawn_damage_meteor(entity_manager)

    def update(
        self,
        dt: float,
        entity_manager: "EntityManager",
    ) -> None:
        """Atualiza movimento básico e spawna meteoros durante a luta.

        Mantém a simplicidade: entra até o target_y, depois cai lentamente.
        Durante a queda, spawna meteoros normais periodicamente.
        """
        if self.dead:
            return

        if self.state == "entering":
            self.y += self.entry_speed * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self.state = "falling"
        elif self.state == "falling":
            self.y += self.speed * dt

            # Ajustar intervalo de spawn baseado na saúde (quanto mais danificado, mais rápido)
            health_percent = self.health / self.max_health
            current_stage = min(11, int((1.0 - health_percent) * 12))
            # Intervalo varia de 2.0s (saúde cheia) para 0.5s (saúde baixa)
            self.meteor_spawn_interval = 2.0 - (1.5 * (1 - health_percent))

            # Spawn de vários meteoros normais durante a queda, quantidade escala com estágio
            self.meteor_spawn_timer += dt
            if self.meteor_spawn_timer >= self.meteor_spawn_interval:
                self.meteor_spawn_timer = 0.0
                num_meteors = 1 + int(current_stage * 1.2)  # 1 no início, até 17 no último estágio
                for _ in range(num_meteors):
                    self._spawn_normal_meteor(entity_manager)

    def _spawn_normal_meteor(self, entity_manager: "EntityManager") -> None:
        """Spawna um meteoro normal durante a luta do boss."""
        # Posição X aleatória na tela
        x = random.uniform(0, Config.SCREEN_WIDTH - 100)
        y = -100  # Começa acima da tela

        # Velocidade vertical normal (sem horizontal)
        vx = 0.0
        vy = random.uniform(150, 250)

        # Tamanho aleatório médio (entre 20 e 40)
        size = random.randint(20, 40)

        # Spawn o meteoro usando o entity_manager
        entity_manager.spawn_meteor(size=size, x=x, y=y, vx=vx, vy=vy)

    def _spawn_damage_meteor(self, entity_manager: "EntityManager") -> None:
        """Spawna um meteoro quando o boss é atingido."""
        # Posição próxima ao boss (leve variação)
        x = self.x + self.w * 0.5 + random.uniform(-50, 50)
        y = self.y + random.uniform(0, self.h * 0.8)

        # Velocidade diagonal (meteoro "saindo" do boss)
        speed = random.uniform(100, 200)
        vx = speed * random.choice([-1, 1]) * random.uniform(0.3, 1.0)
        vy = speed * random.uniform(0.5, 1.5)

        # Tamanho pequeno (fragmentos)
        size = random.randint(15, 30)

        # Spawn o meteoro usando o entity_manager
        entity_manager.spawn_meteor(size=size, x=x, y=y, vx=vx, vy=vy)

    def draw(self, surface: pygame.Surface) -> None:
        # Calcular estágio atual (0-11 para 12 estágios)
        health_percent = self.health / self.max_health
        current_stage = min(11, int((1.0 - health_percent) * 12))

        # Iniciar transição se o estágio mudou
        if current_stage != self._last_damage_stage:
            # Salvar forma atual como "antiga" (ou usar base_shape se for a primeira vez)
            self._old_shape = self._current_shape.copy() if self._current_shape else self._base_shape.copy()
            # Calcular nova forma como alvo
            self._target_shape = self._apply_damage_cracks(health_percent)
            # Reiniciar timer de transição
            self._transition_timer = 0.0
            # Ativar tremor na mudança de estágio
            self._shake_timer = self._shake_duration
            self._last_damage_stage = current_stage

        # Atualizar transição (assumindo que draw é chamado a cada frame)
        if (self._transition_timer < self._transition_duration and 
            self._old_shape is not None and self._target_shape is not None):
            self._transition_timer += 1.0 / 60.0  # Assumir 60 FPS
            t = min(1.0, self._transition_timer / self._transition_duration)
            # Aplicar easing suave (ease-out)
            t = 1 - (1 - t) ** 2
            self._current_shape = self._interpolate_shapes(
                self._old_shape, self._target_shape, t
            )
        elif self._target_shape is not None:
            # Transição completa
            self._current_shape = self._target_shape
            self._old_shape = None
            self._target_shape = None

        # Atualizar tremor
        shake_offset_x = 0.0
        shake_offset_y = 0.0
        if self._shake_timer > 0:
            self._shake_timer = max(0, self._shake_timer - 1.0 / 60.0)  # Assumir 60 FPS
            # Intensidade diminui com o tempo
            current_intensity = self._shake_intensity * (self._shake_timer / self._shake_duration)
            # Deslocamento aleatório
            shake_offset_x = random.uniform(-current_intensity, current_intensity)
            shake_offset_y = random.uniform(-current_intensity, current_intensity)

        # Manter cor constante independente do dano
        body_color = (180, 90, 45)
        border_color = colors.RED

        # Ajustar pontos para a posição atual do meteoro (incluindo tremor)
        adjusted_points = [(self.x + px + shake_offset_x, self.y + py + shake_offset_y) for px, py in self._current_shape]

        # Desenhar polígono irregular com rachaduras
        if len(adjusted_points) >= 3:
            pygame.draw.polygon(surface, body_color, adjusted_points)
            pygame.draw.polygon(surface, border_color, adjusted_points, 3)