import pygame
import math
import random
from ..core.config import Config
from ..core import colors


class Spike:
    """
    Triângulo grudado na lateral da tela que ocasionalmente se solta
    e voa em direção à nave como um míssil teleguiado impreciso.
    """

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
        self.state = 'attached'
        self.dead = False
        self.damage = Config.SPIKE_DAMAGE
        
        # Sistema de entrada com zoom-in
        self.spawn_delay = random.uniform(
            Config.SPIKE_SPAWN_DELAY_MIN,
            Config.SPIKE_SPAWN_DELAY_MAX
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
            -Config.SPIKE_SPEED_VARIATION,
            Config.SPIKE_SPEED_VARIATION
        )
        self.max_speed = Config.SPIKE_MAX_SPEED + random.uniform(
            -Config.SPIKE_MAX_SPEED_VARIATION,
            Config.SPIKE_MAX_SPEED_VARIATION
        )
        
        # Tempo até começar a tremer (randomizado)
        self.time_until_attack = random.uniform(
            Config.SPIKE_MIN_ATTACH_TIME,
            Config.SPIKE_MAX_ATTACH_TIME
        )
        
        # Animação de rotação
        self.rotation = 0.0
        # Rotação rápida quando voando (única para cada spike)
        self.flying_rotation_speed = random.uniform(
            Config.SPIKE_ROTATION_SPEED_MIN,
            Config.SPIKE_ROTATION_SPEED_MAX
        ) * random.choice([-1, 1])  # Aleatoriamente horário ou anti-horário
        
        # Cache de posições do centro
        self._cached_center_x = self.center_x
        self._cached_center_y = self.center_y

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.size, self.size)
    
    @property
    def center_x(self) -> float:
        return self.x + self.size / 2
    
    @property
    def center_y(self) -> float:
        return self.y + self.size / 2
    
    def _update_cached_center(self):
        """Atualiza o cache das posições do centro."""
        self._cached_center_x = self.center_x
        self._cached_center_y = self.center_y
    
    def _calculate_distance(self, x1: float, y1: float, x2: float, y2: float) -> float:
        """Calcula a distância euclidiana entre dois pontos."""
        dx = x2 - x1
        dy = y2 - y1
        return math.sqrt(dx * dx + dy * dy)
    
    def _get_triangle_base_angle(self) -> float:
        """Retorna o ângulo base do triângulo dependendo do estado."""
        if self.state == 'flying':
            # Quando voando, usa a rotação dinâmica
            return self.rotation
        else:
            # Quando grudado/tremendo, aponta para dentro da tela
            if self.from_left:
                return 0.0  # Apontando para direita
            else:
                return math.pi  # Apontando para esquerda
    
    def _get_triangle_points(self, center_x: float, center_y: float, scaled_size: float) -> list[tuple[float, float]]:
        """
        Gera os pontos do triângulo com base na rotação e escala.
        
        Args:
            center_x: Posição X do centro
            center_y: Posição Y do centro
            scaled_size: Raio do triângulo (metade do tamanho)
            
        Returns:
            Lista de 3 pontos (x, y) formando o triângulo
        """
        angle = self._get_triangle_base_angle()
        points: list[tuple[float, float]] = []
        
        for i in range(3):
            point_angle = angle + (i * 2 * math.pi / 3) + math.pi / 2
            px = center_x + math.cos(point_angle) * scaled_size
            py = center_y + math.sin(point_angle) * scaled_size
            points.append((px, py))
        
        return points

    def update(self, dt: float, player_x: float = 0, player_y: float = 0, attacking_count: int = 0):
        """
        Atualiza o estado do triângulo.
        
        Args:
            dt: Delta time
            player_x: Posição X da nave (para míssil teleguiado)
            player_y: Posição Y da nave (para míssil teleguiado)
            attacking_count: Quantos triângulos estão atualmente atacando
        """
        if self.dead:
            return

        # Sistema de spawn com zoom-in
        if self.is_spawning:
            if self.spawn_delay > 0:
                # Esperando o delay antes de começar a aparecer
                self.spawn_delay -= dt
                return  # Não fazer nada enquanto espera
            else:
                # Animação de zoom-in
                self.spawn_animation_timer += dt
                progress = min(self.spawn_animation_timer / Config.SPIKE_SPAWN_ANIMATION_DURATION, 1.0)
                # Easing out (começa rápido, termina suave)
                self.spawn_scale = 1 - (1 - progress) ** 3
                
                if progress >= 1.0:
                    # Animação completa
                    self.is_spawning = False
                    self.spawn_scale = 1.0
                return  # Não fazer outras atualizações durante spawn

        # Rotação apenas quando voando (modo de perseguição)
        if self.state == 'flying':
            # Rotação rápida e única quando voando
            self.rotation += self.flying_rotation_speed * dt

        if self.state == 'respawning':
            # Esperando para reaparecer
            self.respawn_timer -= dt
            if self.respawn_timer <= 0:
                self._respawn()
        
        elif self.state == 'attached':
            # Contagem regressiva para começar a tremer
            self.time_until_attack -= dt
            # Só permite começar a tremer se não exceder o limite de ataques simultâneos
            if self.time_until_attack <= 0 and attacking_count < Config.SPIKE_MAX_ATTACKING:
                self._start_trembling()
        
        elif self.state == 'trembling':
            # Tremor antes de soltar
            self.tremble_timer += dt
            
            # Tremor cada vez mais intenso
            progress = min(self.tremble_timer / Config.SPIKE_TREMBLE_DURATION, 1.0)
            self.tremble_intensity = int(progress * Config.SPIKE_MAX_TREMBLE)
            
            # Aplicar tremor
            self.tremble_offset_x = random.randint(-self.tremble_intensity, self.tremble_intensity)
            self.tremble_offset_y = random.randint(-self.tremble_intensity, self.tremble_intensity)
            
            # Soltar após duração do tremor
            if self.tremble_timer >= Config.SPIKE_TREMBLE_DURATION:
                self._launch(player_x, player_y)
        
        elif self.state == 'flying':
            # Míssil teleguiado com imprecisão
            target_x = player_x + self.target_offset_x
            target_y = player_y + self.target_offset_y
            
            # Atualiza cache do centro
            self._update_cached_center()
            
            # Calcular direção até o alvo
            dx = target_x - self._cached_center_x
            dy = target_y - self._cached_center_y
            distance = self._calculate_distance(self._cached_center_x, self._cached_center_y, target_x, target_y)
            
            if distance > 1:
                # Normalizar direção
                dx /= distance
                dy /= distance
                
                # Acelerar na direção do alvo
                self.vx += dx * self.acceleration * dt
                self.vy += dy * self.acceleration * dt
                
                # Limitar velocidade máxima
                current_speed = math.sqrt(self.vx * self.vx + self.vy * self.vy)
                if current_speed > self.max_speed:
                    factor = self.max_speed / current_speed
                    self.vx *= factor
                    self.vy *= factor
            
            # Atualizar posição
            self.x += self.vx * dt
            self.y += self.vy * dt
            
            # NÃO rotacionar na direção do movimento - deixar o giro contínuo acontecer
            # A rotação já está sendo atualizada no início do update()
            
            # Marcar para respawn se saiu da tela
            if (self.x < -self.size or self.x > Config.SCREEN_WIDTH + self.size or
                self.y < -self.size or self.y > Config.SCREEN_HEIGHT + self.size):
                self._start_respawn()

    def _start_trembling(self):
        """Inicia o estado de tremor antes de soltar."""
        self.state = 'trembling'
        self.tremble_timer = 0.0

    def _launch(self, player_x: float, player_y: float):
        """
        Solta o triângulo e inicia voo teleguiado.
        
        Args:
            player_x: Posição X da nave
            player_y: Posição Y da nave
        """
        self.state = 'flying'
        
        # Adicionar imprecisão na mira
        self.target_offset_x = random.uniform(
            -Config.SPIKE_AIM_IMPRECISION,
            Config.SPIKE_AIM_IMPRECISION
        )
        self.target_offset_y = random.uniform(
            -Config.SPIKE_AIM_IMPRECISION,
            Config.SPIKE_AIM_IMPRECISION
        )
        
        # Velocidade inicial (usa a velocidade única deste spike)
        dx = (player_x + self.target_offset_x) - self.center_x
        dy = (player_y + self.target_offset_y) - self.center_y
        distance = math.sqrt(dx * dx + dy * dy)
        
        if distance > 0:
            self.vx = (dx / distance) * self.initial_speed
            self.vy = (dy / distance) * self.initial_speed
    
    def _start_respawn(self):
        """Inicia o processo de respawn após sair da tela."""
        self.state = 'respawning'
        self.respawn_timer = Config.SPIKE_RESPAWN_TIME
    
    def _respawn(self):
        """Reaparece na posição original na parede."""
        self.x = self.original_x
        self.y = self.original_y
        self.state = 'attached'
        
        # Reset de estados
        self.vx = 0.0
        self.vy = 0.0
        self.tremble_timer = 0.0
        self.tremble_offset_x = 0
        self.tremble_offset_y = 0
        self.tremble_intensity = 0
        
        # Reiniciar animação de spawn
        self.is_spawning = True
        self.spawn_delay = random.uniform(
            Config.SPIKE_SPAWN_DELAY_MIN,
            Config.SPIKE_SPAWN_DELAY_MAX
        )
        self.spawn_animation_timer = 0.0
        self.spawn_scale = 0.0
        
        # Novo tempo aleatório antes de atacar novamente
        self.time_until_attack = random.uniform(
            Config.SPIKE_MIN_ATTACH_TIME,
            Config.SPIKE_MAX_ATTACH_TIME
        )

    def draw(self, surface: pygame.Surface):
        """Desenha o triângulo."""
        if self.dead or self.state == 'respawning':
            return
        
        # Se ainda está spawnando e não chegou a hora, não desenhar
        if self.is_spawning and self.spawn_delay > 0:
            return

        # Posição de desenho (com tremor se aplicável)
        draw_x = self.x + (self.tremble_offset_x if self.state == 'trembling' else 0)
        draw_y = self.y + (self.tremble_offset_y if self.state == 'trembling' else 0)

        # Cor baseada no estado
        if self.state == 'attached':
            color = colors.DARK_RED
        elif self.state == 'trembling':
            # Piscar entre vermelho e branco
            flash = int(self.tremble_timer * 10) % 2 == 0
            color = colors.WHITE if flash else colors.RED
        else:  # flying
            color = colors.RED

        # Criar triângulo com escala aplicada (para efeito zoom-in)
        center_x = draw_x + self.size / 2
        center_y = draw_y + self.size / 2
        
        # Aplicar escala de spawn
        current_scale = self.spawn_scale if self.is_spawning else 1.0
        scaled_size = self.size * current_scale / 2
        
        # Gerar pontos do triângulo usando helper method
        points = self._get_triangle_points(center_x, center_y, scaled_size)

        # Desenhar triângulo
        pygame.draw.polygon(surface, color, points)
        
        # Borda brilhante
        border_color = colors.YELLOW if self.state == 'trembling' else colors.WHITE
        pygame.draw.polygon(surface, border_color, points, width=2)
        
        # Indicador visual quando grudado (pequeno pulso no centro)
        if self.state == 'attached':
            pulse = abs(math.sin(self.time_until_attack * 2))
            pulse_color = (int(100 + 155 * pulse), 0, 0)
            pygame.draw.circle(
                surface,
                pulse_color,
                (int(center_x), int(center_y)),
                3
            )

    def get_points_value(self) -> int:
        """Pontos ganhos ao destruir o triângulo."""
        return Config.SPIKE_POINTS

