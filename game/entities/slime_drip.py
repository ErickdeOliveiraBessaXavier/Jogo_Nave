import pygame
import random
import math
from typing import Optional, List, ClassVar, TypedDict


class TrailParticle(TypedDict):
    x: float
    y: float
    radius: float
    initial_radius: float
    alpha: float
    initial_alpha: float
    lifetime: float
    max_lifetime: float

from dataclasses import dataclass
from ..core.config import config as Config


def easeOutQuad(t: float) -> float:
    """Easing function for smooth fade out."""
    return 1 - (1 - t) * (1 - t)


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


class SlimeSpriteCache:
    """Cache otimizado para sprites escalados do slime drip."""
    
    # Source sprites loaded once
    _sprite_sources: ClassVar[List[pygame.Surface]] = []
    # Cache of scaled sprites: key = (sprite_index, radius, alpha)
    _scaled_sprites: ClassVar[dict[tuple[int, int, int], pygame.Surface]] = {}
    
    @classmethod
    def initialize_sources(cls) -> bool:
        """Load source sprites once. Returns True if successful."""
        if cls._sprite_sources:
            return True  # Already loaded
        
        try:
            for path in Config.SLIME_DRIP_TRAIL_SPRITE_PATHS:
                surf: pygame.Surface = pygame.image.load(path).convert_alpha()
                cls._sprite_sources.append(surf)
            return True
        except Exception:
            cls._sprite_sources.clear()
            return False
    
    @classmethod
    def get_sprite(cls, sprite_index: int, radius: int, alpha: int) -> Optional[pygame.Surface]:
        """Get cached scaled sprite, quantizing alpha to optimize cache size."""
        if not cls._sprite_sources:
            return None

        # Quantize alpha into buckets to reduce the number of cached surfaces.
        alpha_bucket = (alpha // 25) * 25
        key = (sprite_index, radius, alpha_bucket)

        # Look for the bucketed sprite in the cache.
        if key not in cls._scaled_sprites:
            # Prune cache if it gets too large.
            # This assumes Python 3.7+ where dicts maintain insertion order.
            if len(cls._scaled_sprites) > 100:
                items = list(cls._scaled_sprites.items())
                cls._scaled_sprites = dict(items[50:]) # Keep the 50 most recent

            try:
                # Create the sprite using the bucketed alpha.
                src = cls._sprite_sources[sprite_index % len(cls._sprite_sources)]
                scaled_surface = pygame.transform.smoothscale(src, (radius * 2, radius * 2)).convert_alpha()
                scaled_surface.set_alpha(alpha_bucket)
                cls._scaled_sprites[key] = scaled_surface
            except Exception:
                return None # Failed to create sprite

        cached_sprite = cls._scaled_sprites.get(key)
        if not cached_sprite:
            return None

        # If the requested alpha is the same as the bucket, return the cached sprite directly.
        if alpha == alpha_bucket:
            return cached_sprite

        # Otherwise, create a copy and apply the precise alpha value.
        final_sprite = cached_sprite.copy()
        final_sprite.set_alpha(alpha)
        
        return final_sprite
    
    @classmethod
    def clear(cls) -> None:
        """Limpa o cache de sprites e fontes."""
        cls._sprite_sources.clear()
        cls._scaled_sprites.clear()


class SlimeDrip:
    """Gota de slime que cai do boss slime com física realista."""

    def __init__(self, x: float, y: float, effect_width: int, effect_height: int):
        # Propriedades físicas
        self.radius: float = random.uniform(Config.SLIME_DRIP_RADIUS_MIN, Config.SLIME_DRIP_RADIUS_MAX)
        self.initial_radius: float = self.radius
        self.x: float = x
        self.y: float = y
        self.start_y: float = y
        self.curve: float = random.uniform(-1.0, 1.0) * random.uniform(0.5, 1.0)
        
        # Velocidades
        self.speed_x: float = random.uniform(*Config.SLIME_DRIP_SPEED_X)
        self.speed_y: float = random.uniform(*Config.SLIME_DRIP_SPEED_Y)
        
        # Gravidade e terminal velocity
        self.gravity: float = random.uniform(*Config.SLIME_DRIP_GRAVITY)
        self.terminal_velocity: float = Config.SLIME_DRIP_TERMINAL_VELOCITY
        
        # Propriedades do jogo
        self.damage: int = Config.SLIME_DRIP_DAMAGE + max(0, int(self.radius / 30))
        self.dead: bool = False
        self.effect_width: int = effect_width
        self.effect_height: int = effect_height
        
        # Visual
        self.sprite_index: int = random.randint(0, 2)
        self.color: tuple[int, int, int, int] = Config.SLIME_DRIP_COLORS[self.sprite_index]
        
        # NEW: Lightweight particle trail
        self.trail_particles: List[TrailParticle] = []
        self.trail_spawn_timer: float = 0.0
        self.trail_spawn_interval: float = Config.SLIME_DRIP_TRAIL_SPAWN_INTERVAL

        # Load main sprite for the drip's head
        self.main_sprite: Optional[pygame.Surface] = None
        if Config.SLIME_DRIP_USE_SPRITES:
            try:
                if not SlimeSpriteCache.initialize_sources():
                    raise Exception("Failed to load sprite sources")
                
                main_radius = int(self.radius)
                main_alpha = 255  # Make main drip head fully opaque
                self.main_sprite = SlimeSpriteCache.get_sprite(self.sprite_index, main_radius, main_alpha)
            except Exception:
                self.main_sprite = None

    @classmethod
    def clear_sprite_cache(cls) -> None:
        """Clear sprite cache between levels to free memory."""
        SlimeSpriteCache.clear()

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
        
        # Aplicar gravidade com terminal velocity
        self.speed_y += self.gravity * dt
        self.speed_y = min(self.speed_y, self.terminal_velocity)
        
        # Aplicar friction ao movimento lateral
        self.speed_x *= Config.SLIME_DRIP_FRICTION
        
        # Movimento (framerate-independent)
        self.x += self.speed_x * dt
        self.y += self.speed_y * dt

        # Curvatura lateral leve: aumenta com o progresso da queda
        fall_progress = max(0.0, min(1.0, (self.y - self.start_y) / max(1.0, self.effect_height)))
        self.x += self.curve * Config.SLIME_DRIP_CURVE_STRENGTH * fall_progress * dt
        
        # --- Update particle trail ---
        # Update existing particles
        for p in self.trail_particles[:]:
            p['lifetime'] -= dt
            if p['lifetime'] <= 0:
                self.trail_particles.remove(p)
            else:
                # Fade out and shrink
                life_pct = p['lifetime'] / p['max_lifetime']
                p['alpha'] = p['initial_alpha'] * life_pct
                p['radius'] = p['initial_radius'] * life_pct

        # Spawn new particles
        self.trail_spawn_timer += dt
        if self.trail_spawn_timer >= self.trail_spawn_interval:
            self.trail_spawn_timer = 0
            max_lifetime = Config.SLIME_DRIP_TRAIL_LIFETIME
            radius = self.radius * Config.SLIME_DRIP_TRAIL_RADIUS_FACTOR
            self.trail_particles.append({
                'x': self.x,
                'y': self.y,
                'radius': radius,
                'initial_radius': radius,
                'alpha': self.color[3],
                'initial_alpha': self.color[3],
                'lifetime': max_lifetime,
                'max_lifetime': max_lifetime
            })

        # Bounds check
        if (self.y > self.effect_height + 100 or
            self.x < -100 or 
            self.x > self.effect_width + 100):
            self.dead = True

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
        
        # Splash particles integrated into pool
        self.splash_particles: list[SplatParticle] = []
        self._create_splash_particles()
    
    def _create_splash_particles(self) -> None:
        """Create splash particles when pool is formed."""
        num_particles = random.randint(Config.SLIME_SPLAT_PARTICLE_COUNT_MIN, Config.SLIME_SPLAT_PARTICLE_COUNT_MAX)
        
        for _ in range(num_particles):
            # Mini-particle with lateral velocity
            mini_radius = random.uniform(Config.SLIME_SPLAT_PARTICLE_RADIUS_MIN, Config.SLIME_SPLAT_PARTICLE_RADIUS_MAX)
            mini_x = self.x + random.uniform(-20, 20)
            mini_y = self.y - 5
            
            # Velocity: jumps laterally and slightly upward
            speed_x = random.uniform(*Config.SLIME_SPLAT_PARTICLE_SPEED_X)
            speed_y = random.uniform(*Config.SLIME_SPLAT_PARTICLE_SPEED_Y)  # Upward
            
            # Create light particle (using list for performance)
            p = SplatParticle(
                mini_x, mini_y, mini_radius, speed_x, speed_y,
                Config.SLIME_SPLAT_PARTICLE_LIFETIME, 0.0, False
            )
            self.splash_particles.append(p)
    
    def update(self, dt: float) -> None:
        """Atualiza poça (expande e evapora) e partículas."""
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
        
        # Update splash particles with easing
        alive_particles: list[SplatParticle] = []
        for particle in self.splash_particles:
            particle.age += dt
            if particle.age >= particle.lifetime:
                particle.dead = True
            else:
                # Apply gravity
                particle.speed_y += Config.SLIME_SPLAT_PARTICLE_GRAVITY * dt
                particle.x += particle.speed_x * dt
                particle.y += particle.speed_y * dt
                alive_particles.append(particle)
        self.splash_particles = alive_particles
        
        # Morrer quando tempo acabar
        if self.age >= self.lifetime:
            self.dead = True
    
    def draw(self, surface: pygame.Surface, surface_pool: list[pygame.Surface], pool_index: int, fps: float = 60.0) -> int:
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
        
        # Optimization: Limit particles if FPS drops
        if len(self.splash_particles) > 10 and fps < 58:
            self.splash_particles = self.splash_particles[:10]

        # Draw splash particles with easing
        for particle in self.splash_particles:
            if not particle.dead:
                # Use easing for more realistic fade
                life_progress = particle.age / particle.lifetime
                eased_progress = easeOutQuad(life_progress)
                alpha = int(Config.SLIME_SPLAT_PARTICLE_COLOR[3] * (1 - eased_progress))
                color = Config.SLIME_SPLAT_PARTICLE_COLOR[:3] + (alpha,)
                pygame.draw.circle(surface, color, (int(particle.x), int(particle.y)), int(particle.radius))
        
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
        
        # Spatial grid for collision optimization
        self.grid_cell_size: int = 100
        self.spatial_grid: dict[tuple[int, int], list[SlimeDrip]] = {}  # Added type annotation
        
        # Spawn settings (escalam com dificuldade)
        self.max_drips: int = int(Config.SLIME_DRIP_MAX_ACTIVE * difficulty_multiplier)
        self.spawn_timer: float = 0.0
        self.spawn_interval: float = Config.SLIME_DRIP_SPAWN_INTERVAL / difficulty_multiplier
        
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
        self.ground_y: Optional[float] = float(effect_height - Config.SLIME_DRIP_GROUND_OFFSET)

    def _get_grid_cell(self, x: float, y: float) -> tuple[int, int]:
        """Get grid cell coordinates for a position."""
        return (int(x // self.grid_cell_size), int(y // self.grid_cell_size))

    def _add_drip_to_grid(self, drip: SlimeDrip) -> None:
        """Add a drip to the spatial grid."""
        cell = self._get_grid_cell(drip.x, drip.y)
        self.spatial_grid.setdefault(cell, []).append(drip)

    def _remove_drip_from_grid(self, drip: SlimeDrip) -> None:
        """Remove a drip from the spatial grid."""
        cell = self._get_grid_cell(drip.x, drip.y)
        if cell in self.spatial_grid:
            self.spatial_grid[cell] = [d for d in self.spatial_grid[cell] if d is not drip]
            if not self.spatial_grid[cell]:
                del self.spatial_grid[cell]

    def _update_drip_grid_position(self, drip: SlimeDrip, old_x: float, old_y: float) -> None:
        """Update drip's position in spatial grid if it moved to a different cell."""
        old_cell = self._get_grid_cell(old_x, old_y)
        new_cell = self._get_grid_cell(drip.x, drip.y)

        if old_cell == new_cell:
            return  # ✅ Early exit - não precisa fazer nada

        # Usar remoção direta ao invés de list comprehension
        if old_cell in self.spatial_grid:
            try:
                self.spatial_grid[old_cell].remove(drip)
                if not self.spatial_grid[old_cell]:
                    del self.spatial_grid[old_cell]
            except ValueError:
                pass  # Drip não estava na lista

        # Adicionar à nova célula
        self.spatial_grid.setdefault(new_cell, []).append(drip)

    def _get_nearby_drips(self, x: float, y: float) -> list[SlimeDrip]:
        """Get drips in the same cell and adjacent cells."""
        center_cell = self._get_grid_cell(x, y)
        nearby_drips: list[SlimeDrip] = []
        
        # Check 3x3 grid around center cell
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                cell = (center_cell[0] + dx, center_cell[1] + dy)
                if cell in self.spatial_grid:
                    nearby_drips.extend(self.spatial_grid[cell])
        
        return nearby_drips

    def update(self, dt: float, boss_x: float, boss_y: float,
               boss_width: int, player_x: float, player_y: float) -> None:
        """Atualiza todas as gotas e poças.

        ✅ CORRIGIDO: player_x e player_y agora obrigatórios para feedback visual
        """
        # Atualizar gotas existentes
        alive_drips: list[SlimeDrip] = []
        for drip in self.drips:
            old_x, old_y = drip.x, drip.y
            drip.update(dt)
            # Update spatial grid position
            self._update_drip_grid_position(drip, old_x, old_y)
            
            # Criar poça quando gota atinge o chão
            if not drip.dead and self.ground_y is not None and drip.y >= self.ground_y and drip.radius > Config.SLIME_DRIP_MIN_POOL_RADIUS:
                self._create_pool(drip.x, self.ground_y, drip.radius)
                drip.dead = True
                # Remove from grid when it becomes a pool
                self._remove_drip_from_grid(drip)

            if not drip.dead:
                alive_drips.append(drip)
        self.drips = alive_drips

        # Atualizar poças
        self.pools = [p for p in self.pools if (p.update(dt), not p.dead)[1]]

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
        # Add to spatial grid
        self._add_drip_to_grid(drip)

    def _create_pool(self, x: float, y: float, drip_radius: float) -> None:
        """Cria uma poça no chão."""
        # Limitar número de poças
        if len(self.pools) >= Config.SLIME_POOL_MAX_ACTIVE:
            self.pools.pop(0)  # Remover mais antiga
        
        pool = SlimePool(x, y, drip_radius)
        self.pools.append(pool)

    def draw(self, surface: pygame.Surface, fps: float = 60.0) -> None:
        """Desenha gotas e poças, incluindo o novo rastro de partículas."""
        # 1. Desenhar poças
        for pool in self.pools:
            self._pool_surface_pool_index = pool.draw(
                surface,
                self._pool_surface_pool,
                self._pool_surface_pool_index,
                fps=fps
            )
        
        # 2. Desenhar gotas com o novo rastro de partículas
        for drip in self.drips:
            if drip.dead:
                continue
            
            # Desenhar sombra diretamente na surface principal
            if self.ground_y is not None:
                distance_to_ground = max(0, self.ground_y - drip.y)
                if distance_to_ground < 500:
                    shadow_scale = 1.0 - (distance_to_ground / 500)
                    shadow_alpha = int(80 * shadow_scale)
                    shadow_radius = int(drip.radius * 0.6 * (1 + shadow_scale * 0.5))
                    
                    if shadow_alpha > 10:
                        shadow_color = (0, 0, 0, shadow_alpha)
                        shadow_pos = (int(drip.x), int(self.ground_y))
                        shadow_rect = pygame.Rect(
                            shadow_pos[0] - shadow_radius,
                            shadow_pos[1] - shadow_radius // 2,
                            shadow_radius * 2,
                            shadow_radius
                        )
                        pygame.draw.ellipse(surface, shadow_color, shadow_rect)
            
            # Desenhar o rastro de partículas (atrás da cabeça)
            for particle in drip.trail_particles:
                p_color = (*drip.color[:3], int(particle['alpha']))
                pygame.draw.circle(surface, p_color, (int(particle['x']), int(particle['y'])), int(particle['radius']))

            # Desenhar a cabeça da gota
            if drip.main_sprite:
                # O ponto de âncora é o centro da gota
                draw_x = int(drip.x - drip.main_sprite.get_width() / 2)
                draw_y = int(drip.y - drip.main_sprite.get_height() / 2)
                surface.blit(drip.main_sprite, (draw_x, draw_y))
            else:
                # Fallback se não houver sprite
                pygame.draw.circle(surface, drip.color, (int(drip.x), int(drip.y)), int(drip.radius))

            # Adicionar highlight dinâmico se perto do jogador
            if self.player_last_x is not None and self.player_last_y is not None:
                dx, dy = drip.x - self.player_last_x, drip.y - self.player_last_y
                if (dx*dx + dy*dy) < Config.SLIME_DRIP_HIGHLIGHT_DISTANCE ** 2:
                    pulse = (math.sin(pygame.time.get_ticks() * Config.SLIME_DRIP_HIGHLIGHT_PULSE_SPEED) + 1) / 2
                    highlight_alpha = int(180 + pulse * 75)
                    highlight_color = (*Config.SLIME_DRIP_HIGHLIGHT_COLOR[:3], highlight_alpha)
                    
                    pygame.draw.circle(surface, highlight_color, (int(drip.x), int(drip.y)), int(drip.radius * 0.4))
                    pygame.draw.circle(surface, (255, 100, 100, 80), (int(drip.x), int(drip.y)), int(drip.radius * 1.3), width=2)

    def check_player_collision(self, player_rect: pygame.Rect) -> int:
        """Verifica colisões com gotas E poças usando spatial grid. Retorna dano total."""
        total_damage = 0
        
        # Get player center for grid lookup
        player_center_x = player_rect.centerx
        player_center_y = player_rect.centery
        
        # Only check drips in nearby grid cells for performance.
        nearby_drips = self._get_nearby_drips(player_center_x, player_center_y)
        
        # Dano de gotas (remover ao colidir).
        for drip in nearby_drips:
            if not drip.dead and drip.collides_with_player(player_rect):
                total_damage += drip.damage
                drip.dead = True
                self._remove_drip_from_grid(drip)
        
        # A segunda verificação de colisão foi removida conforme otimização,
        # confiando que a grid espacial é suficiente.

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
        self.spatial_grid.clear()  # Clear spatial grid
        self.spawn_timer = 0
        self.player_last_x = None
        self.player_last_y = None
        self.player_velocity_x = 0.0