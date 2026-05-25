import math
import random

import pygame

from ..core.config import config as Config


class Spike:
    """
    Mini nave suicida que fica adormecida nas laterais.
    Ao ser ativada, ela 'acorda' com raiva e avança contra o jogador.
    """

    # Design de pixel art procedural (grid 5x5)
    # 0 = Vazio, 1 = Casco, 2 = Detalhe/Asas, 3 = Olho, 4 = Propulsor
    SHIP_MAP = [
        [0, 0, 1, 0, 0],
        [0, 2, 1, 2, 0],
        [1, 3, 1, 3, 1],
        [1, 1, 1, 1, 1],
        [2, 0, 4, 0, 2],
    ]

    def __init__(self, y: float, from_left: bool = True):
        """
        Args:
            y: Posição vertical do triângulo
            from_left: Se True, triângulo na parede esquerda; se False, na direita
        """
        self.from_left = from_left
        self.size = Config.SPIKE_SIZE
        self.y = y
        self.original_y = y  # Guardar posição original para respawn

        # Posição na parede
        if from_left:
            self.x = 0  # Grudado na esquerda
            self.original_x = 0
        else:
            self.x = Config.SCREEN_WIDTH - self.size  # Grudado na direita
            self.original_x = Config.SCREEN_WIDTH - self.size

        # Estados: 'attached' (grudado), 'trembling' (tremendo), 'flying' (voando), 'respawning' (esperando respawn)
        self.state = "attached"
        self.dead = False
        self.damage = Config.SPIKE_DAMAGE

        # Sistema de entrada com zoom-in
        self.spawn_delay = random.uniform(
            Config.SPIKE_SPAWN_DELAY_MIN, Config.SPIKE_SPAWN_DELAY_MAX
        )
        self.spawn_animation_timer = 0.0
        self.is_spawning = True  # Começa no modo spawn
        self.spawn_scale = 0.0  # Escala atual (0 = invisível, 1 = tamanho normal)

        # Sistema de respawn
        self.respawn_timer = 0.0

        # Sistema de tremor
        self.tremble_timer = 0.0
        self.tremble_offset_x = 0
        self.tremble_offset_y = 0
        self.tremble_intensity = 0

        # Sistema de voo teleguiado
        self.vx = 0.0
        self.vy = 0.0
        self.target_offset_x = 0.0  # Imprecisão na mira
        self.target_offset_y = 0.0
        self.acceleration = Config.SPIKE_ACCELERATION

        # Velocidade única para cada spike (variação individual)
        self.initial_speed = Config.SPIKE_INITIAL_SPEED + random.uniform(
            -Config.SPIKE_SPEED_VARIATION, Config.SPIKE_SPEED_VARIATION
        )
        self.max_speed = Config.SPIKE_MAX_SPEED + random.uniform(
            -Config.SPIKE_MAX_SPEED_VARIATION, Config.SPIKE_MAX_SPEED_VARIATION
        )

        # Tempo até começar a tremer (randomizado)
        self.time_until_attack = random.uniform(
            Config.SPIKE_MIN_ATTACH_TIME, Config.SPIKE_MAX_ATTACH_TIME
        )

        # Animação de rotação (radianos)
        # Começa apontando para dentro da tela (90 deg ou -90 deg)
        self.rotation = math.radians(90 if from_left else -90)

        # Efeitos Visuais de Mini-Nave
        self.eye_glow = 0.0  # 0.0 (apagado) a 1.0 (brilhante)
        self.thruster_timer = 0.0
        self.breathing_pulse = 0.0

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.size, self.size)

    @property
    def center_x(self) -> float:
        return self.x + self.size / 2

    @property
    def center_y(self) -> float:
        return self.y + self.size / 2

    def _calculate_distance(self, x1: float, y1: float, x2: float, y2: float) -> float:
        """Calcula a distância euclidiana entre dois pontos."""
        dx = x2 - x1
        dy = y2 - y1
        return math.sqrt(dx * dx + dy * dy)

    def update(
        self,
        dt: float,
        player_x: float = 0,
        player_y: float = 0,
        attacking_count: int = 0,
    ):
        if self.dead:
            return

        # Animações Visuais
        self.breathing_pulse += dt * 2.0
        self.thruster_timer += dt * 15.0

        # Sistema de spawn com zoom-in
        if self.is_spawning:
            if self.spawn_delay > 0:
                self.spawn_delay -= dt
                return
            else:
                self.spawn_animation_timer += dt
                progress = min(self.spawn_animation_timer / Config.SPIKE_SPAWN_ANIMATION_DURATION, 1.0)
                self.spawn_scale = 1 - (1 - progress) ** 3
                if progress >= 1.0:
                    self.is_spawning = False
                    self.spawn_scale = 1.0
                return

        if self.state == "flying":
            # Apontar na direção da velocidade para parecer controlado
            if abs(self.vx) > 0.1 or abs(self.vy) > 0.1:
                # Nosso design de mini-nave tem o nariz no topo (0, -1)
                # math.atan2 retorna 0 para DIREITA. Logo, adicionamos pi/2
                target_rotation = math.atan2(self.vy, self.vx) + math.pi / 2
                
                # Lerp suave para a rotação lidando com wrap-around
                diff = (target_rotation - self.rotation + math.pi) % (2 * math.pi) - math.pi
                self.rotation += diff * dt * 10.0

            # Olhos ficam vermelhos e fixos quando voando
            self.eye_glow = 1.0
        elif self.state == "trembling":
            # Olhos piscam rápido quando acordando
            self.eye_glow = (math.sin(self.tremble_timer * 20.0) + 1.0) / 2.0
        else:
            # Pulsa suavemente quando dormindo
            self.eye_glow = (math.sin(self.breathing_pulse) + 1.0) / 4.0

        if self.state == "respawning":
            self.respawn_timer -= dt
            if self.respawn_timer <= 0:
                self._respawn()

        elif self.state == "attached":
            self.time_until_attack -= dt
            if self.time_until_attack <= 0 and attacking_count < Config.SPIKE_MAX_ATTACKING:
                self._start_trembling()

        elif self.state == "trembling":
            self.tremble_timer += dt
            progress = min(self.tremble_timer / Config.SPIKE_TREMBLE_DURATION, 1.0)
            self.tremble_intensity = int(progress * Config.SPIKE_MAX_TREMBLE)
            self.tremble_offset_x = random.randint(-self.tremble_intensity, self.tremble_intensity)
            self.tremble_offset_y = random.randint(-self.tremble_intensity, self.tremble_intensity)

            if self.tremble_timer >= Config.SPIKE_TREMBLE_DURATION:
                self._launch(player_x, player_y)

        elif self.state == "flying":
            target_x = player_x + self.target_offset_x
            target_y = player_y + self.target_offset_y

            dx = target_x - self.center_x
            dy = target_y - self.center_y
            distance = self._calculate_distance(self.center_x, self.center_y, target_x, target_y)

            if distance > 1:
                dx /= distance
                dy /= distance
                self.vx += dx * self.acceleration * dt
                self.vy += dy * self.acceleration * dt
                current_speed = math.sqrt(self.vx * self.vx + self.vy * self.vy)
                if current_speed > self.max_speed:
                    factor = self.max_speed / current_speed
                    self.vx *= factor
                    self.vy *= factor

            self.x += self.vx * dt
            self.y += self.vy * dt

            if (self.x < -self.size or self.x > Config.SCREEN_WIDTH + self.size or
                self.y < -self.size or self.y > Config.SCREEN_HEIGHT + self.size):
                self._start_respawn()

    def _start_trembling(self):
        self.state = "trembling"
        self.tremble_timer = 0.0

    def _launch(self, player_x: float, player_y: float):
        self.state = "flying"
        self.target_offset_x = random.uniform(-Config.SPIKE_AIM_IMPRECISION, Config.SPIKE_AIM_IMPRECISION)
        self.target_offset_y = random.uniform(-Config.SPIKE_AIM_IMPRECISION, Config.SPIKE_AIM_IMPRECISION)

        dx = (player_x + self.target_offset_x) - self.center_x
        dy = (player_y + self.target_offset_y) - self.center_y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance > 0:
            self.vx = (dx / distance) * self.initial_speed
            self.vy = (dy / distance) * self.initial_speed

    def _start_respawn(self):
        self.state = "respawning"
        self.respawn_timer = Config.SPIKE_RESPAWN_TIME

    def _respawn(self):
        self.x = self.original_x
        self.y = self.original_y
        self.state = "attached"
        self.vx = 0.0
        self.vy = 0.0
        self.tremble_timer = 0.0
        self.tremble_offset_x = 0
        self.tremble_offset_y = 0
        self.tremble_intensity = 0
        self.is_spawning = True
        self.spawn_delay = random.uniform(Config.SPIKE_SPAWN_DELAY_MIN, Config.SPIKE_SPAWN_DELAY_MAX)
        self.spawn_animation_timer = 0.0
        self.spawn_scale = 0.0
        self.time_until_attack = random.uniform(Config.SPIKE_MIN_ATTACH_TIME, Config.SPIKE_MAX_ATTACH_TIME)

    def draw(self, surface: pygame.Surface):
        if self.dead or self.state == "respawning":
            return

        if self.is_spawning and self.spawn_delay > 0:
            return

        # Posição e Rotação
        draw_x = self.x + (self.tremble_offset_x if self.state == "trembling" else 0)
        draw_y = self.y + (self.tremble_offset_y if self.state == "trembling" else 0)
        
        # Ângulo base dependendo do estado
        if self.state == "flying":
            angle = math.degrees(self.rotation)
        else:
            angle = 90 if self.from_left else -90 # Aponta para dentro

        # Escala
        current_scale = self.spawn_scale if self.is_spawning else 1.0
        scaled_size = int(self.size * current_scale)
        if scaled_size < 1:
            return

        # Superfície temporária para rotação da mini-nave
        ship_surf = pygame.Surface((self.size, self.size), pygame.SRCALPHA)
        p_size = self.size // 5 # Grid 5x5

        # Paleta de Cores baseada no humor
        if self.state == "flying":
            body_color = (200, 50, 50)
            wing_color = (150, 30, 30)
            eye_color = (255, 255, 100) # Olho amarelo de raiva
        elif self.state == "trembling":
            body_color = (150, 150, 150)
            wing_color = (100, 100, 100)
            eye_color = (255, 255, 255) if int(self.tremble_timer * 10) % 2 == 0 else (100, 0, 0)
        else: # attached/sleeping
            body_color = (80, 80, 100)
            wing_color = (60, 60, 80)
            # Olho azul/dim pulsa
            eye_val = int(50 + 150 * self.eye_glow)
            eye_color = (0, eye_val, eye_val)

        # Desenhar o mapa
        for r in range(5):
            for c in range(5):
                cell = self.SHIP_MAP[r][c]
                if cell == 0:
                    continue
                
                rect = pygame.Rect(c * p_size, r * p_size, p_size, p_size)
                if cell == 1: # Hull
                    pygame.draw.rect(ship_surf, body_color, rect)
                elif cell == 2: # Wings
                    pygame.draw.rect(ship_surf, wing_color, rect)
                elif cell == 3: # Eye
                    pygame.draw.rect(ship_surf, eye_color, rect)
                elif cell == 4 and self.state == "flying": # Thruster
                    # Chama animada
                    t_height = int(p_size * (0.8 + 0.5 * math.sin(self.thruster_timer)))
                    t_rect = pygame.Rect(c * p_size, r * p_size, p_size, t_height)
                    pygame.draw.rect(ship_surf, (255, 150, 0), t_rect)

        # Rotacionar e Blitar
        rotated_ship = pygame.transform.rotozoom(ship_surf, -angle, current_scale)
        rect = rotated_ship.get_rect(center=(int(draw_x + self.size/2), int(draw_y + self.size/2)))
        surface.blit(rotated_ship, rect)

    def get_points_value(self) -> int:
        """Pontos ganhos ao destruir o triângulo."""
        return Config.SPIKE_POINTS
