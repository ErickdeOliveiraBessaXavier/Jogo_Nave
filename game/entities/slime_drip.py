import pygame
import random
import math
from typing import Optional
from collections import deque
from dataclasses import dataclass
from ..core.config import config as Config


@dataclass
class SplatParticle:
    x: float
    y: float
    radius: float
    speed_x: float
    speed_y: float
    lifetime: float
    age: float = 0.0
    dead: bool = False


class SlimeDrip:
    """Gota de slime que cai do boss slime com física realista."""

    def __init__(self, x: float, y: float, effect_width: int, effect_height: int):
        # Propriedades físicas
        self.radius: float = random.uniform(Config.SLIME_DRIP_RADIUS_MIN, Config.SLIME_DRIP_RADIUS_MAX)
        self.initial_radius: float = self.radius  # 🆕 Armazenar tamanho original
        self.x: float = x
        self.y: float = y
        
        # Velocidades
        self.speed_x: float = random.uniform(*Config.SLIME_DRIP_SPEED_X)
        self.speed_y: float = random.uniform(*Config.SLIME_DRIP_SPEED_Y)
        
        # Movimento ondulado
        self.angle: float = 0.0
        self.angle_velocity: float = random.uniform(*Config.SLIME_DRIP_ANGLE_VELOCITY)
        self.wave_amplitude: float = random.uniform(*Config.SLIME_DRIP_WAVE_AMPLITUDE)
        
        # Gravidade e terminal velocity
        self.gravity: float = random.uniform(*Config.SLIME_DRIP_GRAVITY)
        self.terminal_velocity: float = Config.SLIME_DRIP_TERMINAL_VELOCITY  # 🆕
        
        # Propriedades do jogo
        self.damage: int = max(1, int(self.radius / 30) + 1)
        self.dead: bool = False
        self.effect_width: int = effect_width
        self.effect_height: int = effect_height
        
        # Visual
        self.color: tuple[int, int, int, int] = random.choice(Config.SLIME_DRIP_COLORS)
        
        # Trail (calda)
        radius_progress = (self.radius - Config.SLIME_DRIP_RADIUS_MIN) / (Config.SLIME_DRIP_RADIUS_MAX - Config.SLIME_DRIP_RADIUS_MIN)
        trail_length = int(Config.SLIME_DRIP_TRAIL_LENGTH_MIN + radius_progress * (Config.SLIME_DRIP_TRAIL_LENGTH_MAX - Config.SLIME_DRIP_TRAIL_LENGTH_MIN))
        self.trail_positions: deque[tuple[float, float]] = deque(maxlen=trail_length)
        # 🆕 Pré-popular a calda com um formato inicial para ser visível desde o começo.
        initial_stretch = self.initial_radius * 8.5  # O comprimento inicial da calda
        if trail_length > 0:
            for i in range(trail_length):
                # Interpolar os pontos para criar uma linha vertical acima da gota
                progress = i / (trail_length - 1) if trail_length > 1 else 1.0
                offset_y = -initial_stretch * (1 - progress)  # Esticar para cima
                self.trail_positions.append((x, y + offset_y))

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
        
        # 🆕 Aplicar gravidade com terminal velocity
        self.speed_y += self.gravity * dt
        self.speed_y = min(self.speed_y, self.terminal_velocity)  # Limitar velocidade máxima
        
        # Aplicar friction ao movimento lateral
        self.speed_x *= Config.SLIME_DRIP_FRICTION
        
        # Movimento ondulado (apenas quando visível)
        if self.y > self.radius:
            self.angle += self.angle_velocity * dt
        
        # ❌ REMOVIDO: Código de encolhimento (shrink_rate)
        
        # Movimento (framerate-independent)
        self.x += self.speed_x * math.cos(self.angle) * self.wave_amplitude * dt
        self.y += self.speed_y * dt
        
        # 🆕 Armazenar posições para trail (calda alongada)
        # Quanto mais rápido cai, mais espaçado fica o trail
        if self.radius >= Config.SLIME_DRIP_TRAIL_MIN_RADIUS:
            self.trail_positions.append((self.x, self.y))
        
        # Bounds check
        if (self.y > self.effect_height + 100 or
            self.x < -100 or 
            self.x > self.effect_width + 100):
            self.dead = True

    def draw(self, surface: pygame.Surface, surface_pool: list[pygame.Surface], 
         pool_index: int, player_x: Optional[float] = None, player_y: Optional[float] = None, 
         ground_y: Optional[float] = None) -> int:
        if self.dead:
            return pool_index
        
        # Desenhar sombra (mantido)
        if ground_y is not None:
            distance_to_ground = max(0, ground_y - self.y)
            if distance_to_ground < 500:
                shadow_scale = 1.0 - (distance_to_ground / 500)
                shadow_alpha = int(80 * shadow_scale)
                shadow_radius = int(self.radius * 0.6 * (1 + shadow_scale * 0.5))
                
                if shadow_alpha > 10:
                    shadow_color = (0, 0, 0, shadow_alpha)
                    shadow_pos = (int(self.x), int(ground_y))
                    shadow_rect = pygame.Rect(
                        shadow_pos[0] - shadow_radius,
                        shadow_pos[1] - shadow_radius // 2,
                        shadow_radius * 2,
                        shadow_radius
                    )
                    pygame.draw.ellipse(surface, shadow_color, shadow_rect)
        
        # Usar surface do pool
        temp_surface = surface_pool[pool_index]
        next_index = (pool_index + 1) % len(surface_pool)
        temp_surface.fill((0, 0, 0, 0))
        
        # Centralizar a base da gota na parte inferior da surface para dar espaço para a calda
        surface_w, surface_h = temp_surface.get_size()
        center_x = surface_w // 2
        # Deixar um pouco de espaço na parte inferior
        center_y = int(surface_h - self.initial_radius - 10)
        center = (center_x, center_y)

        # 🎨 NOVO: Desenhar calda como um polígono único (formato "Pin de Mapa")
        if len(self.trail_positions) > 2:
            left_points: list[tuple[int, int]] = []
            right_points: list[tuple[int, int]] = []
            
            # Calcular pontos da borda para cada segmento da calda
            for i, (trail_x, trail_y) in enumerate(self.trail_positions):
                if i % 2 != 0:  # Step skipping para reduzir cálculos
                    continue
                progress = ((i + 1) / len(self.trail_positions)) ** Config.SLIME_DRIP_TRAIL_CURVE_FACTOR
                size_factor = (Config.SLIME_DRIP_TRAIL_SIZE_FACTOR_MIN + 
                               progress * (Config.SLIME_DRIP_TRAIL_SIZE_FACTOR_MAX - 
                                           Config.SLIME_DRIP_TRAIL_SIZE_FACTOR_MIN))
                trail_radius = int(self.initial_radius * size_factor)

                # Posição relativa ao novo centro na surface temporária
                offset_x = int(trail_x - self.x)
                offset_y = int(trail_y - self.y)
                trail_pos = (center[0] + offset_x, center[1] + offset_y)
                
                if trail_radius > 1:
                    left_points.append((trail_pos[0] - trail_radius, trail_pos[1]))
                    right_points.append((trail_pos[0] + trail_radius, trail_pos[1]))

            # Construir o polígono que conecta as bordas
            if left_points and right_points:
                polygon_points = left_points + right_points[::-1]
                
                trail_color = (self.color[0], self.color[1], self.color[2], 180)
                pygame.draw.polygon(temp_surface, trail_color, polygon_points)

        # Desenhar corpo principal da gota (círculo) por cima para garantir base redonda
        radius_int = int(self.radius)
        pygame.draw.circle(temp_surface, self.color, center, radius_int)
        
        # Highlight próximo do jogador (mantido)
        if player_x is not None and player_y is not None:
            # Check rápido de bounding box para otimização
            if abs(self.x - player_x) > Config.SLIME_DRIP_HIGHLIGHT_DISTANCE + self.radius or \
               abs(self.y - player_y) > Config.SLIME_DRIP_HIGHLIGHT_DISTANCE + self.radius:
                pass  # Skip highlight se muito longe
            else:
                dx = self.x - player_x
                dy = self.y - player_y
                distance_squared = dx * dx + dy * dy
                if distance_squared < Config.SLIME_DRIP_HIGHLIGHT_DISTANCE ** 2:
                    pulse = (math.sin(pygame.time.get_ticks() * Config.SLIME_DRIP_HIGHLIGHT_PULSE_SPEED) + 1) / 2
                    highlight_alpha = int(180 + pulse * 75)
                    highlight_color = Config.SLIME_DRIP_HIGHLIGHT_COLOR[:3] + (highlight_alpha,)
                    
                    highlight_radius = int(self.radius * 0.4)
                    pygame.draw.circle(temp_surface, highlight_color, center, highlight_radius)
                    
                    danger_radius = int(self.radius * 1.3)
                    pygame.draw.circle(temp_surface, (255, 100, 100, 80), center, danger_radius, width=2)
        
        # Blit a surface inteira, centralizada na posição da gota
        draw_x = int(self.x - center_x)
        draw_y = int(self.y - center_y)
        surface.blit(temp_surface, (draw_x, draw_y))
        
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
        
        # ✨ NOVO: Pulsação quando pode causar dano
        draw_radius = self.radius
        draw_color = self.color
        if self.can_damage():
            pulse = math.sin(self.age * 6.0)  # 6 rad/s
            draw_radius = self.radius + pulse * 5
            pulse_alpha = int(self.color[3] * (0.8 + pulse * 0.2))
            draw_color = (self.color[0], self.color[1], self.color[2], pulse_alpha)
        
        # Desenhar círculo no centro da surface temporária
        surface_size = Config.SLIME_POOL_SURFACE_SIZE
        center = (surface_size // 2, surface_size // 2)
        pygame.draw.circle(temp_surface, draw_color, center, int(draw_radius))
        
        # Calcular área do círculo para blit otimizado
        radius_int = int(draw_radius)
        half_size = surface_size // 2
        area = (half_size - radius_int, half_size - radius_int, radius_int * 2, radius_int * 2)
        
        # Blit apenas a região necessária
        draw_x = int(self.x - draw_radius)
        draw_y = int(self.y - draw_radius)
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
        # Partículas de respingo (tipadas com dataclass para melhor verificação de tipos)
        self.splat_particles: list[SplatParticle] = []
        
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
            surf = pygame.Surface((Config.SLIME_DRIP_SURFACE_SIZE, Config.SLIME_DRIP_SURFACE_SIZE), pygame.SRCALPHA).convert_alpha()
            self._surface_pool.append(surf)
        
        # Pool de surfaces para poças (tamanho fixo para otimização)
        self._pool_surface_pool: list[pygame.Surface] = []
        self._pool_surface_pool_size: int = 10
        for _ in range(self._pool_surface_pool_size):
            surf = pygame.Surface((Config.SLIME_POOL_SURFACE_SIZE, Config.SLIME_POOL_SURFACE_SIZE), pygame.SRCALPHA).convert_alpha()
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
        alive_drips: list[SlimeDrip] = []
        for drip in self.drips:
            drip.update(dt)
            # Criar poça quando gota atinge o chão
            if not drip.dead and drip.y >= self.ground_y and drip.radius > Config.SLIME_DRIP_MIN_POOL_RADIUS:
                self._create_pool(drip.x, self.ground_y, drip.radius)
                self._create_splat_particles(drip.x, self.ground_y, drip.radius)  # ✨ NOVO: Efeito de respingo
                drip.dead = True

            if not drip.dead:
                alive_drips.append(drip)
        self.drips = alive_drips

        # Atualizar poças
        self.pools = [p for p in self.pools if (p.update(dt), not p.dead)[1]]

        # ✨ NOVO: Atualizar partículas de respingo
        alive_particles: list[SplatParticle] = []
        for particle in self.splat_particles:
            particle.age += dt
            if particle.age >= particle.lifetime:
                particle.dead = True
            else:
                particle.speed_y += Config.SLIME_SPLAT_PARTICLE_GRAVITY * dt
                particle.x += particle.speed_x * dt
                particle.y += particle.speed_y * dt
                alive_particles.append(particle)
        self.splat_particles = alive_particles

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

    def _create_splat_particles(self, x: float, y: float, drip_radius: float) -> None:
        """Cria partículas de respingo quando gota atinge o chão."""
        num_particles = random.randint(Config.SLIME_SPLAT_PARTICLE_COUNT_MIN, Config.SLIME_SPLAT_PARTICLE_COUNT_MAX)
        
        for _ in range(num_particles):
            # Mini-partícula com velocidade lateral
            mini_radius = random.uniform(Config.SLIME_SPLAT_PARTICLE_RADIUS_MIN, Config.SLIME_SPLAT_PARTICLE_RADIUS_MAX)
            mini_x = x + random.uniform(-20, 20)
            mini_y = y - 5
            
            # Velocidade: salta lateralmente e um pouco para cima
            speed_x = random.uniform(*Config.SLIME_SPLAT_PARTICLE_SPEED_X)
            speed_y = random.uniform(*Config.SLIME_SPLAT_PARTICLE_SPEED_Y)  # Para cima
            
            # Criar partícula leve (usando lista para performance)
            p = SplatParticle(
                mini_x, mini_y, mini_radius, speed_x, speed_y,
                Config.SLIME_SPLAT_PARTICLE_LIFETIME, 0.0, False
            )
            self.splat_particles.append(p)

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha gotas e poças (usando pool de surfaces)."""
        # ✨ NOVO: Desenhar partículas de respingo PRIMEIRO (camada mais baixa)
        for particle in self.splat_particles:
            if not particle.dead:
                alpha = int(Config.SLIME_SPLAT_PARTICLE_COLOR[3] * (1 - particle.age / particle.lifetime))
                color = Config.SLIME_SPLAT_PARTICLE_COLOR[:3] + (alpha,)
                pygame.draw.circle(surface, color, (int(particle.x), int(particle.y)), int(particle.radius))
        
        # Desenhar poças
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
                self.player_last_y,
                self.ground_y
            )

    def check_player_collision(self, player_rect: pygame.Rect) -> int:
        """Verifica colisões com gotas E poças. Retorna dano total."""
        total_damage = 0
        surviving_drips: list[SlimeDrip] = []

        # Dano de gotas (remover ao colidir)
        for drip in self.drips:
            if drip.collides_with_player(player_rect):
                total_damage += drip.damage
                drip.dead = True
            else:
                surviving_drips.append(drip)
        self.drips = surviving_drips

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
        self.splat_particles.clear()  # ✨ NOVO: Limpar partículas também
        self.spawn_timer = 0
        self.player_last_x = None
        self.player_last_y = None
        self.player_velocity_x = 0.0