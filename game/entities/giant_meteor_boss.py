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
        # Tamanho grande, cobrindo largura inteira da tela
        self.w = Config.SCREEN_WIDTH
        self.h = Config.GIANT_METEOR_BOSS_HEIGHT
        self.x = 0  # Começa na posição 0 para cobrir toda a largura
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

        # Gerar forma irregular fixa (não muda a cada frame)
        self._base_shape = self._generate_base_shape()
        self._current_shape = self._base_shape.copy()

        # Posições fixas das rachaduras (geradas uma vez no início)
        self._crack_positions: list[CrackPosition] = self._generate_crack_positions()

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

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

    def _generate_crack_positions(self) -> list[CrackPosition]:
        """Gera posições fixas para as rachaduras que vão evoluir."""
        rng = random.Random(42)  # Seed fixa para consistência
        crack_positions: list[CrackPosition] = []

        # Definir 5-6 rachaduras que vão evoluir
        num_cracks = rng.randint(5, 6)

        # Centro do meteoro
        cx = self.w * 0.5
        cy = self.h * 0.5

        for _ in range(num_cracks):
            # Escolher um ponto na borda
            edge_point_idx = rng.randint(0, len(self._base_shape) - 1)
            start_x, start_y = self._base_shape[edge_point_idx]

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

            # Largura base da rachadura
            base_width = rng.uniform(30, 60)

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

    def _apply_damage_cracks(self, health_percent: float) -> list[tuple[float, float]]:
        """Aplica rachaduras à forma base baseado no nível de dano.

        As rachaduras crescem em profundidade conforme o dano aumenta.
        """
        if health_percent > 0.75:
            return self._base_shape.copy()  # Sem rachaduras ainda

        # Determinar profundidade baseado no dano
        if health_percent <= 0.25:
            depth_min, depth_max = 0.6, 0.75
            width_multiplier = 1.5
            num_small_cracks = 8  # Muitas rachaduras pequenas
        elif health_percent <= 0.50:
            depth_min, depth_max = 0.4, 0.5
            width_multiplier = 1.2
            num_small_cracks = 5  # Algumas rachaduras pequenas
        else:  # 0.50 < health <= 0.75
            depth_min, depth_max = 0.2, 0.3
            width_multiplier = 1.0
            num_small_cracks = 3  # Poucas rachaduras pequenas

        # Copiar forma base
        damaged_shape = self._base_shape.copy()

        # Lista para armazenar todas as rachaduras
        all_cracks: list[tuple[int, list[tuple[float, float]]]] = []

        # Usar seed baseada no estágio para profundidades consistentes
        stage = 4 - int(health_percent * 4)
        rng = random.Random(stage * 100)

        for crack_data in self._crack_positions:
            edge_point_idx = crack_data["edge_idx"]
            start_x = crack_data["start_x"]
            start_y = crack_data["start_y"]
            dir_x = crack_data["dir_x"]
            dir_y = crack_data["dir_y"]
            perp_x = crack_data["perp_x"]
            perp_y = crack_data["perp_y"]
            base_width = crack_data["base_width"] * width_multiplier

            # Profundidade da rachadura aumenta com o dano
            crack_depth = rng.uniform(depth_min, depth_max) * min(self.w, self.h) * 0.5

            # Criar pontos da rachadura simples
            crack_points = self._generate_single_crack(
                start_x,
                start_y,
                dir_x,
                dir_y,
                perp_x,
                perp_y,
                base_width,
                crack_depth,
                rng,
            )

            all_cracks.append((edge_point_idx, crack_points))

        # Agora adicionar rachaduras pequenas espalhadas
        for _ in range(num_small_cracks):
            # Escolher um ponto aleatório na borda
            edge_idx = rng.randint(0, len(self._base_shape) - 1)
            start_x, start_y = self._base_shape[edge_idx]

            # Direção para o centro
            cx = self.w * 0.5
            cy = self.h * 0.5
            to_center_x = cx - start_x
            to_center_y = cy - start_y
            center_dist = (to_center_x**2 + to_center_y**2) ** 0.5

            if center_dist == 0:
                continue

            dir_x = to_center_x / center_dist
            dir_y = to_center_y / center_dist

            # Vetor perpendicular
            perp_x = -dir_y
            perp_y = dir_x

            # Rachadura pequena: largura e profundidade menores
            small_width = rng.uniform(15, 35)
            small_depth = rng.uniform(0.08, 0.2) * min(self.w, self.h) * 0.5

            # Gerar rachadura simples pequena
            small_crack_points = self._generate_single_crack(
                start_x,
                start_y,
                dir_x,
                dir_y,
                perp_x,
                perp_y,
                small_width,
                small_depth,
                rng,
            )

            all_cracks.append((edge_idx, small_crack_points))

        # Ordenar rachaduras por índice (para inserir na ordem correta)
        all_cracks.sort(key=lambda x: x[0], reverse=True)

        # Inserir rachaduras na forma base
        for edge_idx, crack_points in all_cracks:
            # Remover o ponto original e inserir a rachadura
            insert_pos = edge_idx
            damaged_shape = (
                damaged_shape[:insert_pos]
                + crack_points
                + damaged_shape[insert_pos + 1 :]
            )

        return damaged_shape

    def _generate_single_crack(
        self,
        start_x: float,
        start_y: float,
        dir_x: float,
        dir_y: float,
        perp_x: float,
        perp_y: float,
        base_width: float,
        crack_depth: float,
        rng: random.Random,
    ) -> list[tuple[float, float]]:
        """Gera pontos para uma única ramificação de rachadura com efeito zigzag."""
        crack_points: list[tuple[float, float]] = []
        segments = 10

        # Primeiro, calcular a trajetória central com zigzag
        center_line: list[tuple[float, float]] = []
        change_points = [0.3, 0.6, 1.0]
        current_dir_x, current_dir_y = dir_x, dir_y

        for i in range(segments + 1):
            progress = i / segments

            # Verificar se atingiu um ponto de mudança
            for cp in change_points:
                if abs(progress - cp) < 0.01:  # Próximo o suficiente
                    # Adicionar offset perpendicular aleatório
                    offset_magnitude = rng.uniform(0.1, 0.3) * base_width
                    offset_sign = rng.choice([-1, 1])
                    offset_x = perp_x * offset_magnitude * offset_sign
                    offset_y = perp_y * offset_magnitude * offset_sign

                    # Nova direção com offset
                    current_dir_x = dir_x + offset_x / crack_depth
                    current_dir_y = dir_y + offset_y / crack_depth

                    # Normalizar
                    length = (current_dir_x**2 + current_dir_y**2) ** 0.5
                    current_dir_x /= length
                    current_dir_y /= length
                    break

            distance = crack_depth * progress
            center_x = start_x + current_dir_x * distance
            center_y = start_y + current_dir_y * distance
            center_line.append((center_x, center_y))

        # Agora gerar os pontos dos lados baseados na linha central
        for i in range(segments + 1):
            center_x, center_y = center_line[i]
            progress = i / segments
            current_width = base_width * (1 - progress**1.5)

            left_x = center_x + perp_x * current_width * 0.5
            left_y = center_y + perp_y * current_width * 0.5
            crack_points.append((left_x, left_y))

        # Lado direito (voltando)
        for i in range(segments, -1, -1):
            center_x, center_y = center_line[i]
            progress = i / segments
            current_width = base_width * (1 - progress**1.5)

            if i == 0:
                break

            right_x = center_x - perp_x * current_width * 0.5
            right_y = center_y - perp_y * current_width * 0.5
            crack_points.append((right_x, right_y))

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

        # Spawn de meteoros quando atingido (mais quando mais danificado)
        if entity_manager and self.state == "falling":
            health_percent = self.health / self.max_health
            # Chance de spawn aumenta com o dano (0.1 para saúde alta, 0.5 para saúde baixa)
            spawn_chance = 0.1 + (0.4 * (1 - health_percent))

            if random.random() < spawn_chance:
                # Spawn 1-3 meteoros baseado no dano
                num_meteors = random.randint(1, max(1, int(3 * (1 - health_percent))))
                for _ in range(num_meteors):
                    self._spawn_damage_meteor(entity_manager)

    def update(
        self,
        dt: float,
        player_x: float,
        player_y: float,
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
            # Intervalo varia de 2.0s (saúde cheia) para 0.5s (saúde baixa)
            self.meteor_spawn_interval = 2.0 - (1.5 * (1 - health_percent))

            # Spawn de meteoros normais durante a queda
            self.meteor_spawn_timer += dt
            if self.meteor_spawn_timer >= self.meteor_spawn_interval:
                self.meteor_spawn_timer = 0.0
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
        # Calcular estágio de deterioração baseado na vida restante
        health_percent = self.health / self.max_health

        # Determinar estágio atual baseado nos thresholds
        current_stage = 0
        if health_percent <= 0.25:
            current_stage = 3  # Muito danificado
        elif health_percent <= 0.50:
            current_stage = 2  # Danificado
        elif health_percent <= 0.75:
            current_stage = 1  # Levemente danificado
        # else: current_stage = 0 (intacto)

        # Só atualizar forma se o estágio mudou
        if current_stage != self._last_damage_stage:
            self._current_shape = self._apply_damage_cracks(health_percent)
            self._last_damage_stage = current_stage

        # Manter cor constante independente do dano
        body_color = (180, 90, 45)
        border_color = colors.RED

        # Ajustar pontos para a posição atual do meteoro
        adjusted_points = [(self.x + px, self.y + py) for px, py in self._current_shape]

        # Desenhar polígono irregular com rachaduras
        if len(adjusted_points) >= 3:
            pygame.draw.polygon(surface, body_color, adjusted_points)
            pygame.draw.polygon(surface, border_color, adjusted_points, 3)
