import pygame
import random
import math
from typing import Optional
from ..core.config import config as Config


class SlimeDrip:
    """Gota de slime que cai do boss slime com física realista."""

    def __init__(self, x: float, y: float, effect_width: int, effect_height: int):
        # Propriedades físicas com type hints explícitos
        self.radius: float = random.uniform(Config.SLIME_DRIP_RADIUS_MIN, Config.SLIME_DRIP_RADIUS_MAX)
        self.x: float = x
        self.y: float = y
        
        # Velocidades em pixels/segundo
        self.speed_x: float = random.uniform(*Config.SLIME_DRIP_SPEED_X)
        self.speed_y: float = random.uniform(*Config.SLIME_DRIP_SPEED_Y)
        
        # Movimento ondulado (amplitude do balanço lateral)
        self.angle: float = 0.0
        self.angle_velocity: float = random.uniform(*Config.SLIME_DRIP_ANGLE_VELOCITY)
        self.wave_amplitude: float = random.uniform(*Config.SLIME_DRIP_WAVE_AMPLITUDE)
        
        # Gravidade (aceleração aplicada diretamente a speed_y)
        self.gravity: float = random.uniform(*Config.SLIME_DRIP_GRAVITY)
        
        # Propriedades do jogo
        self.damage: int = max(1, int(self.radius / 30) + 1)  # Dano proporcional ao tamanho
        self.dead: bool = False
        self.effect_width: int = effect_width
        self.effect_height: int = effect_height
        
        # Visual
        self.color: tuple[int, int, int, int] = random.choice(Config.SLIME_DRIP_COLORS)
        self.min_radius: float = Config.SLIME_DRIP_MIN_RADIUS

    @property
    def rect(self) -> pygame.Rect:
        """Retângulo de colisão baseado no raio."""
        size = int(self.radius * 2)
        return pygame.Rect(
            int(self.x - self.radius),
            int(self.y - self.radius),
            size,
            size
        )

    def update(self, dt: float) -> None:
        """Atualiza a física da gota (framerate-independent)."""
        if self.dead:
            return
        
        # Movimento lateral com limite nas bordas
        if self.x < self.radius or self.x > self.effect_width - self.radius:
            self.speed_x *= -1
        
        # Aplicar gravidade sempre (física consistente)
        self.speed_y += self.gravity * dt
        
        # Aplicar friction ao movimento lateral para evitar oscilações infinitas
        self.speed_x *= (1 - Config.SLIME_DRIP_FRICTION * dt)
        
        # Movimento ondulado (apenas quando visível)
        if self.y > self.radius:
            self.angle += self.angle_velocity * dt
        
        # Diminuir tamanho quando estiver caindo
        if self.y > self.radius * 2:
            shrink_rate = (Config.SLIME_DRIP_SHRINK_RATE_BASE + 
                          (self.radius / 80.0) * Config.SLIME_DRIP_SHRINK_RATE_MULTIPLIER)
            self.radius -= shrink_rate * dt
        
        # Movimento (framerate-independent)
        self.x += self.speed_x * math.cos(self.angle) * self.wave_amplitude * dt
        self.y += self.speed_y * dt
        
        # ✅ CORRIGIDO: Bounds check completo (vertical E horizontal)
        if (self.y > self.effect_height + 100 or 
            self.radius < self.min_radius or
            self.x < -100 or 
            self.x > self.effect_width + 100):
            self.dead = True

    def draw(self, surface: pygame.Surface, surface_pool: list[pygame.Surface], 
             pool_index: int, player_x: Optional[float] = None, player_y: Optional[float] = None) -> int:
        """Desenha a gota usando pool de surfaces (otimizado).
        
        Args:
            surface: Surface principal onde desenhar
            surface_pool: Pool de surfaces para reutilizar
            pool_index: Índice atual no pool
            player_x, player_y: Posição do jogador para highlight
        
        Returns:
            Próximo índice do pool (circular)
        """
        if self.dead:
            return pool_index
        
        # ✅ CORRIGIDO: Usar surface do pool
        temp_surface = surface_pool[pool_index]
        next_index = (pool_index + 1) % len(surface_pool)
        
        # Limpar surface
        temp_surface.fill((0, 0, 0, 0))
        
        # Verificar se deve highlight (próximo do jogador)
        draw_color = self.color
        if player_x is not None and player_y is not None:
            dx = self.x - player_x
            dy = self.y - player_y
            distance_squared = dx * dx + dy * dy
            if distance_squared < Config.SLIME_DRIP_HIGHLIGHT_DISTANCE ** 2:
                draw_color = Config.SLIME_DRIP_HIGHLIGHT_COLOR
        
        # Desenhar círculo
        radius_int = int(self.radius)
        center = (radius_int, radius_int)
        pygame.draw.circle(temp_surface, draw_color, center, radius_int)
        
        # Blit apenas a região necessária
        draw_x = int(self.x - self.radius)
        draw_y = int(self.y - self.radius)
        surface.blit(temp_surface, (draw_x, draw_y), 
                     area=(0, 0, radius_int * 2, radius_int * 2))
        
        return next_index

    def collides_with_player(self, player_rect: pygame.Rect) -> bool:
        """Verifica colisão circular com o jogador (otimizado com AABB)."""
        if self.dead:
            return False
        
        # ✅ FASE 1: AABB check rápido (elimina 80%+ dos casos)
        if (self.x + self.radius < player_rect.left or 
            self.x - self.radius > player_rect.right or
            self.y + self.radius < player_rect.top or 
            self.y - self.radius > player_rect.bottom):
            return False  # Nem perto - early exit
        
        # ✅ FASE 2: Colisão circular precisa (sem sqrt!)
        dx = self.x - player_rect.centerx
        dy = self.y - player_rect.centery
        distance_squared = dx * dx + dy * dy
        
        player_radius = min(player_rect.width, player_rect.height) / 2
        threshold_squared = (self.radius + player_radius) ** 2
        
        return distance_squared < threshold_squared


class SlimePool:
    """Poça de slime no chão que causa dano contínuo."""
    
    def __init__(self, x: float, y: float, initial_radius: float):
        self.x: float = x
        self.y: float = y
        self.initial_radius: float = initial_radius  # ✅ CORRIGIDO: Armazenar como atributo
        self.radius: float = initial_radius
        self.max_radius: float = initial_radius * Config.SLIME_POOL_RADIUS_MULTIPLIER
        self.lifetime: float = Config.SLIME_POOL_LIFETIME
        self.age: float = 0.0
        self.damage: int = Config.SLIME_POOL_DAMAGE
        self.damage_cooldown: float = Config.SLIME_POOL_DAMAGE_COOLDOWN
        self.last_damage_time: float = 0.0
        self.dead: bool = False
        
        # Visual com alpha
        self.base_color: tuple[int, int, int, int] = Config.SLIME_POOL_COLOR
        self.color: tuple[int, int, int, int] = self.base_color
    
    def update(self, dt: float) -> None:
        """Atualiza poça (expande e evapora)."""
        if self.dead:
            return
        
        self.age += dt
        self.last_damage_time += dt
        
        # Expandir nos primeiros 0.5s
        if self.age < Config.SLIME_POOL_EXPANSION_TIME:
            progress = self.age / Config.SLIME_POOL_EXPANSION_TIME
            self.radius = self.initial_radius + (self.max_radius - self.initial_radius) * progress
        
        # Evaporar nos últimos 1.5s (fade out alpha)
        fade_start = self.lifetime - Config.SLIME_POOL_FADE_TIME
        if self.age > fade_start:
            time_left = self.lifetime - self.age
            alpha_progress = time_left / Config.SLIME_POOL_FADE_TIME
            alpha = int(self.base_color[3] * alpha_progress)
            self.color = (self.base_color[0], self.base_color[1], 
                         self.base_color[2], max(0, alpha))
        
        # Morrer quando tempo acabar
        if self.age >= self.lifetime:
            self.dead = True
    
    def draw(self, surface: pygame.Surface, surface_pool: list[pygame.Surface], pool_index: int) -> int:
        """Desenha poça com transparência usando pool de surfaces."""
        if self.dead or self.color[3] == 0:
            return pool_index
        
        temp_surface = surface_pool[pool_index]
        next_index = (pool_index + 1) % len(surface_pool)
        
        # Limpar surface
        temp_surface.fill((0, 0, 0, 0))
        
        # Desenhar círculo no centro da surface temporária
        surface_size = Config.SLIME_POOL_SURFACE_SIZE
        center = (surface_size // 2, surface_size // 2)
        pygame.draw.circle(temp_surface, self.color, center, int(self.radius))
        
        # Calcular área do círculo para blit otimizado
        radius_int = int(self.radius)
        half_size = surface_size // 2
        area = (half_size - radius_int, half_size - radius_int, radius_int * 2, radius_int * 2)
        
        # Blit apenas a região necessária
        draw_x = int(self.x - self.radius)
        draw_y = int(self.y - self.radius)
        surface.blit(temp_surface, (draw_x, draw_y), area=area)
        
        return next_index
    
    def can_damage(self) -> bool:
        """Verifica se pode causar dano (cooldown)."""
        return self.last_damage_time >= self.damage_cooldown
    
    def reset_damage_cooldown(self) -> None:
        """Reseta cooldown de dano."""
        self.last_damage_time = 0.0
    
    def collides_with_player(self, player_rect: pygame.Rect) -> bool:
        """Verifica se jogador está pisando na poça (AABB + circular)."""
        if self.dead:
            return False
        
        # AABB check rápido
        if (self.x + self.radius < player_rect.left or 
            self.x - self.radius > player_rect.right or
            self.y + self.radius < player_rect.top or 
            self.y - self.radius > player_rect.bottom):
            return False
        
        # Colisão circular (sem sqrt)
        dx = self.x - player_rect.centerx
        dy = self.y - player_rect.centery
        distance_squared = dx * dx + dy * dy
        
        player_radius = min(player_rect.width, player_rect.height) / 2
        return distance_squared < (self.radius + player_radius) ** 2


class SlimeDrippingEffect:
    """Sistema que gerencia múltiplas gotas de slime e poças no chão."""

    def __init__(self, effect_width: int, effect_height: int, difficulty_multiplier: float = 1.0):
        self.effect_width: int = effect_width
        self.effect_height: int = effect_height
        self.difficulty_multiplier: float = difficulty_multiplier
        
        # Gotas e poças
        self.drips: list[SlimeDrip] = []
        self.pools: list[SlimePool] = []
        
        # Spawn settings (escalam com dificuldade)
        self.max_drips: int = int(Config.SLIME_DRIP_MAX_ACTIVE * difficulty_multiplier)
        self.spawn_timer: float = 0.0
        self.spawn_interval: float = Config.SLIME_DRIP_SPAWN_INTERVAL / difficulty_multiplier
        
        # ✅ NOVO: Cache de surfaces para performance
        self._surface_pool: list[pygame.Surface] = []
        self._surface_pool_size: int = 20
        self._surface_pool_index: int = 0
        
        # Pré-criar surfaces no pool (tamanho máximo: raio 85 * 2 = 170)
        for _ in range(self._surface_pool_size):
            surf = pygame.Surface((Config.SLIME_DRIP_SURFACE_SIZE, Config.SLIME_DRIP_SURFACE_SIZE), pygame.SRCALPHA)
            self._surface_pool.append(surf)
        
        # Pool de surfaces para poças (tamanho fixo para otimização)
        self._pool_surface_pool: list[pygame.Surface] = []
        self._pool_surface_pool_size: int = 10
        for _ in range(self._pool_surface_pool_size):
            surf = pygame.Surface((Config.SLIME_POOL_SURFACE_SIZE, Config.SLIME_POOL_SURFACE_SIZE), pygame.SRCALPHA)
            self._pool_surface_pool.append(surf)
        self._pool_surface_pool_index: int = 0
        
        # Sistema de spawn inteligente
        self.player_last_x: Optional[float] = None
        self.player_last_y: Optional[float] = None  # Para feedback visual
        self.player_velocity_x: float = 0.0
        self.prediction_time: float = Config.SLIME_DRIP_PREDICTION_TIME
        
        # Linha do chão (onde gotas viram poças)
        self.ground_y: float = float(effect_height - Config.SLIME_DRIP_GROUND_OFFSET)

    def update(self, dt: float, boss_x: float, boss_y: float, 
               boss_width: int, player_x: float, player_y: float) -> None:
        """Atualiza todas as gotas e poças.
        
        ✅ CORRIGIDO: player_x e player_y agora obrigatórios para feedback visual
        """
        # Atualizar gotas existentes
        for drip in self.drips[:]:
            drip.update(dt)
            
            # Criar poça quando gota atinge o chão
            if not drip.dead and drip.y >= self.ground_y and drip.radius > Config.SLIME_DRIP_MIN_POOL_RADIUS:
                self._create_pool(drip.x, self.ground_y, drip.radius)
                drip.dead = True
            elif drip.dead:
                self.drips.remove(drip)
        
        # Atualizar poças
        for pool in self.pools[:]:
            pool.update(dt)
            if pool.dead:
                self.pools.remove(pool)
        
        # Spawn de novas gotas
        self.spawn_timer += dt
        if self.spawn_timer >= self.spawn_interval and len(self.drips) < self.max_drips:
            self.spawn_timer = 0
            self._spawn_drip(boss_x, boss_y, boss_width, player_x)
        
        # Armazenar posição do jogador para feedback visual
        self.player_last_x = player_x
        self.player_last_y = player_y

    def _is_position_occupied(self, x: float, y: float) -> bool:
        """Verifica se há gotas próximas à posição de spawn."""
        min_distance_squared = Config.SLIME_DRIP_MIN_SPAWN_DISTANCE ** 2
        for drip in self.drips:
            if not drip.dead:
                dx = drip.x - x
                dy = drip.y - y
                distance_squared = dx * dx + dy * dy
                if distance_squared < min_distance_squared:
                    return True
        return False

    def _spawn_drip(self, boss_x: float, boss_y: float, boss_width: int, 
                    player_x: float) -> None:
        """Spawna gota com previsão de movimento do jogador."""
        # Calcular velocidade do jogador
        if self.player_last_x is not None:
            instant_velocity = player_x - self.player_last_x
            # Suavização exponencial
            self.player_velocity_x = (self.player_velocity_x * 0.7 + 
                                      instant_velocity * 0.3)
        
        self.player_last_x = player_x
        
        # Prever posição futura
        predicted_x = player_x + (self.player_velocity_x * self.prediction_time)
        
        # Limitar à largura do boss
        boss_center = boss_x + boss_width / 2
        max_offset = boss_width * 0.4
        
        if abs(predicted_x - boss_center) > max_offset:
            target_x = player_x  # Muito longe - usar posição atual
        else:
            # Usar previsão com margem de erro
            error_margin = random.uniform(-50, 50)
            target_x = predicted_x + error_margin
        
        # 60% spawn direcionado, 40% aleatório (menos previsível)
        if random.random() < Config.SLIME_DRIP_SPAWN_CHANCE_DIRECTED:
            bias = random.uniform(0.6, 0.9)
            x = boss_center + (target_x - boss_center) * bias
        else:
            x = boss_x + random.uniform(0, boss_width)
        
        # Verificar se há gotas próximas (evitar spawn empilhado)
        if self._is_position_occupied(x, boss_y - Config.SLIME_DRIP_SPAWN_Y_OFFSET):
            return  # Não spawnar se posição ocupada
        
        y = boss_y - Config.SLIME_DRIP_SPAWN_Y_OFFSET
        drip = SlimeDrip(x, y, self.effect_width, self.effect_height)
        self.drips.append(drip)

    def _create_pool(self, x: float, y: float, drip_radius: float) -> None:
        """Cria uma poça no chão."""
        # Limitar número de poças
        if len(self.pools) >= Config.SLIME_POOL_MAX_ACTIVE:
            self.pools.pop(0)  # Remover mais antiga
        
        pool = SlimePool(x, y, drip_radius)
        self.pools.append(pool)

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha gotas e poças (usando pool de surfaces)."""
        # Desenhar poças PRIMEIRO (camada de fundo)
        for pool in self.pools:
            self._pool_surface_pool_index = pool.draw(
                surface,
                self._pool_surface_pool,
                self._pool_surface_pool_index
            )
        
        # ✅ CORRIGIDO: Desenhar gotas usando pool
        for drip in self.drips:
            self._surface_pool_index = drip.draw(
                surface,
                self._surface_pool,
                self._surface_pool_index,
                self.player_last_x,
                self.player_last_y
            )

    def check_player_collision(self, player_rect: pygame.Rect) -> int:
        """Verifica colisões com gotas E poças. Retorna dano total."""
        total_damage = 0
        
        # Dano de gotas (remover ao colidir)
        for drip in self.drips[:]:
            if drip.collides_with_player(player_rect):
                total_damage += drip.damage
                drip.dead = True
        
        # Dano de poças (dano contínuo com cooldown)
        for pool in self.pools:
            if pool.collides_with_player(player_rect) and pool.can_damage():
                total_damage += pool.damage
                pool.reset_damage_cooldown()
        
        return total_damage

    def reset(self) -> None:
        """Remove todas as gotas e poças."""
        self.drips.clear()
        self.pools.clear()
        self.spawn_timer = 0
        self.player_last_x = None
        self.player_velocity_x = 0.0