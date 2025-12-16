import pygame
import random
from typing import Optional

from ..core.config import config as Config


class SlimeDrip:
    """Gota de slime que cai do boss slime com física realista."""

    def __init__(self, x: float, y: float, effect_width: int, effect_height: int):
        # Propriedades físicas baseadas no código JavaScript
        self.radius = random.uniform(
            Config.SLIME_DRIP_RADIUS_MIN, 
            Config.SLIME_DRIP_RADIUS_MAX
        )
        self.x = x
        self.y = y
        # Valores agora são pixels/segundo (framerate-independent)
        self.speed_x = random.uniform(*Config.SLIME_DRIP_SPEED_X)
        self.speed_y = random.uniform(*Config.SLIME_DRIP_SPEED_Y)
        self.angle = 0
        self.angle_velocity = random.uniform(*Config.SLIME_DRIP_ANGLE_VELOCITY)
        self.range = random.uniform(*Config.SLIME_DRIP_RANGE)

        self.gravity = random.uniform(*Config.SLIME_DRIP_GRAVITY)

        # Propriedades do jogo
        self.damage = Config.SLIME_DRIP_DAMAGE
        self.dead = False
        self.effect_width = effect_width
        self.effect_height = effect_height

        # Cores do slime com transparência
        self.color = random.choice(Config.SLIME_DRIP_COLORS)

        # Controle de tamanho mínimo (mais permissivo para gotas pequenas)
        self.min_radius = Config.SLIME_DRIP_MIN_RADIUS

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
        """Atualiza a física da gota."""
        if self.dead:
            return

        # Movimento lateral com limite nas bordas
        if self.x < self.radius or self.x > self.effect_width - self.radius:
            self.speed_x *= -1

        # Aplicar gravidade quando estiver visível
        if self.y > self.radius:
            self.speed_y += self.gravity * dt  # Gravidade acelera a velocidade vertical
            self.angle += self.angle_velocity * dt  # Agora usa dt diretamente

        # Diminuir tamanho quando estiver caindo (taxa proporcional ao tamanho)
        if self.y > self.radius * 2:
            # Gotas maiores diminuem mais rápido, gotas menores diminuem mais devagar
            shrink_rate = (Config.SLIME_DRIP_SHRINK_RATE_BASE + 
                          (self.radius / 80.0) * Config.SLIME_DRIP_SHRINK_RATE_MULTIPLIER)
            self.radius -= shrink_rate * dt  # Agora usa dt diretamente

        # Movimento horizontal e vertical (framerate-independent)
        self.x += self.speed_x * dt
        self.y += self.speed_y * dt  # Agora usa dt diretamente

        # Reset quando sair da tela ou ficar muito pequena
        if self.y > self.effect_height + 100 or self.radius < self.min_radius:
            self.dead = True

    def draw(self, surface: pygame.Surface, surface_pool: list[pygame.Surface],
             pool_index: int) -> int:
        """Desenha a gota usando uma surface do pool.

        Args:
            surface: Surface principal onde desenhar
            surface_pool: Pool de surfaces para reutilizar
            pool_index: Índice atual no pool

        Returns:
            Próximo índice do pool (circular)
        """
        if self.dead:
            return pool_index

        # Pegar surface do pool (circular)
        temp_surface = surface_pool[pool_index]
        next_index = (pool_index + 1) % len(surface_pool)

        # Limpar surface (importante!)
        temp_surface.fill((0, 0, 0, 0))

        # Desenhar círculo
        radius_int = int(self.radius)
        center = (radius_int, radius_int)
        pygame.draw.circle(temp_surface, self.color, center, radius_int)

        # Blit apenas a região necessária
        draw_x = int(self.x - self.radius)
        draw_y = int(self.y - self.radius)
        surface.blit(temp_surface, (draw_x, draw_y),
                     area=(0, 0, radius_int * 2, radius_int * 2))

        return next_index

    def collides_with_player(self, player_rect: pygame.Rect) -> bool:
        """Verifica colisão circular com o jogador (otimizado)."""
        if self.dead:
            return False

        # FASE 1: AABB check rápido (elimina 80%+ dos casos)
        # Criar rect expandido da gota
        drip_left = self.x - self.radius
        drip_right = self.x + self.radius
        drip_top = self.y - self.radius
        drip_bottom = self.y + self.radius

        # Check de sobreposição retangular
        if (drip_right < player_rect.left or
            drip_left > player_rect.right or
            drip_bottom < player_rect.top or
            drip_top > player_rect.bottom):
            return False  # Nem perto - early exit

        # FASE 2: Colisão circular precisa (só se passou AABB)
        dx = self.x - player_rect.centerx
        dy = self.y - player_rect.centery
        distance_squared = dx * dx + dy * dy  # SEM sqrt!

        player_radius = min(player_rect.width, player_rect.height) / 2
        threshold_squared = (self.radius + player_radius) ** 2

        return distance_squared < threshold_squared


class SlimeDrippingEffect:
    """Sistema que gerencia múltiplas gotas de slime."""

    def __init__(self, effect_width: int, effect_height: int):
        self.effect_width = effect_width
        self.effect_height = effect_height
        self.drips: list[SlimeDrip] = []
        self.pools: list[SlimePool] = []
        
        self.max_drips = Config.SLIME_DRIP_MAX_ACTIVE
        self.spawn_timer = 0
        self.spawn_interval = Config.SLIME_DRIP_SPAWN_INTERVAL
        
        self.player_last_x: Optional[float] = None
        self.player_velocity_x: float = 0.0
        self.prediction_time = Config.SLIME_DRIP_PREDICTION_TIME
        self.ground_y = effect_height - 50

        # Cache de surfaces para reutilização (evita criar surfaces toda vez)
        self._surface_pool: list[pygame.Surface] = []
        self._surface_pool_size = 20  # Pool fixo
        self._surface_pool_index = 0

        # Pré-criar surfaces no pool (tamanho máximo possível: raio 85 * 2 = 170)
        for _ in range(self._surface_pool_size):
            surf = pygame.Surface((170, 170), pygame.SRCALPHA)
            self._surface_pool.append(surf)

    def update(self, dt: float, boss_x: float, boss_y: float, boss_width: int, player_x: Optional[float] = None) -> None:
        """Atualiza todas as gotas, poças e spawna novas."""
        # Atualizar gotas existentes e criar poças quando chegam ao chão
        for drip in self.drips[:]:
            drip.update(dt)

            # Criar poça se atingir o chão
            if not drip.dead and drip.y >= self.ground_y and drip.radius > 15:
                self._create_pool(drip.x, self.ground_y, drip.radius)
                drip.dead = True  # Gota vira poça
            elif drip.dead:
                self.drips.remove(drip)

        # Atualizar poças existentes
        for pool in self.pools[:]:
            pool.update(dt)
            if pool.dead:
                self.pools.remove(pool)

        # Spawn de novas gotas
        self.spawn_timer += dt
        if self.spawn_timer >= self.spawn_interval and len(self.drips) < self.max_drips:
            self.spawn_timer = 0
            self._spawn_drip(boss_x, boss_y, boss_width, player_x)

    def _create_pool(self, x: float, y: float, drip_radius: float) -> None:
        """Cria uma poça no chão."""
        # Evitar muitas poças (máximo definido)
        if len(self.pools) >= Config.SLIME_POOL_MAX_ACTIVE:
            # Remover poça mais antiga
            self.pools.pop(0)

        pool = SlimePool(x, y, drip_radius)
        self.pools.append(pool)

    def _spawn_drip(self, boss_x: float, boss_y: float, boss_width: int,
                    player_x: Optional[float] = None) -> None:
        """Spawna gota com previsão de movimento do jogador."""
        if player_x is not None:
            # Calcular velocidade do jogador
            if self.player_last_x is not None:
                # Velocidade = diferença de posição (suavizada)
                instant_velocity = player_x - self.player_last_x
                # Suavização exponencial (evitar jitter)
                self.player_velocity_x = (self.player_velocity_x * 0.7 +
                                          instant_velocity * 0.3)

            self.player_last_x = player_x

            # Prever posição futura do jogador
            predicted_x = player_x + (self.player_velocity_x * self.prediction_time)

            # Limitar à largura do boss
            boss_center = boss_x + boss_width / 2
            max_offset = boss_width * 0.4

            if abs(predicted_x - boss_center) > max_offset:
                # Jogador muito longe - usar posição atual
                target_x = player_x
            else:
                # Usar previsão com margem de erro
                error_margin = random.uniform(-50, 50)
                target_x = predicted_x + error_margin

            # 80% de chance de spawn direcionado
            if random.random() < Config.SLIME_DRIP_SPAWN_CHANCE_DIRECTED:
                # Interpolar entre boss_center e target_x
                bias = random.uniform(0.6, 0.9)  # 60-90% em direção ao alvo
                x = boss_center + (target_x - boss_center) * bias
            else:
                # 20% spawn aleatório (manter imprevisível)
                x = boss_x + random.uniform(0, boss_width)
        else:
            # Sem jogador - spawn aleatório
            x = boss_x + random.uniform(0, boss_width)

        # Posição Y ligeiramente acima do boss
        y = boss_y - 10

        drip = SlimeDrip(x, y, self.effect_width, self.effect_height)
        self.drips.append(drip)

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha todas as gotas e poças usando pool de surfaces."""
        # Desenhar poças primeiro (atrás das gotas)
        for pool in self.pools:
            pool.draw(surface)

        # Desenhar gotas
        for drip in self.drips:
            self._surface_pool_index = drip.draw(
                surface,
                self._surface_pool,
                self._surface_pool_index
            )

    def check_player_collision(self, player_rect: pygame.Rect) -> int:
        """Verifica colisões com o jogador e retorna o dano total."""
        total_damage = 0

        # Verificar colisões com gotas
        for drip in self.drips[:]:
            if drip.collides_with_player(player_rect):
                total_damage += drip.damage
                drip.dead = True  # Gota some ao acertar

        # Verificar colisões com poças
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


class SlimePool:
    """Poça de slime no chão que causa dano."""

    def __init__(self, x: float, y: float, initial_radius: float):
        self.x = x
        self.y = y
        self.radius = initial_radius
        self.max_radius = initial_radius * Config.SLIME_POOL_RADIUS_MULTIPLIER
        self.lifetime = Config.SLIME_POOL_LIFETIME
        self.age = 0.0
        self.damage = Config.SLIME_POOL_DAMAGE
        self.damage_cooldown = Config.SLIME_POOL_DAMAGE_COOLDOWN
        self.last_damage_time = 0.0
        self.dead = False

        # Visual
        self.color = Config.SLIME_POOL_COLOR

    def update(self, dt: float) -> None:
        """Atualiza poça (expande e evapora)."""
        if self.dead:
            return

        self.age += dt
        self.last_damage_time += dt

        # Expandir nos primeiros 0.5s
        if self.age < Config.SLIME_POOL_EXPANSION_TIME:
            growth = (self.max_radius - self.radius) * (dt / Config.SLIME_POOL_EXPANSION_TIME)
            self.radius += growth

        # Evaporar nos últimos 1.5s
        elif self.age > self.lifetime - Config.SLIME_POOL_FADE_TIME:
            time_left = self.lifetime - self.age
            alpha = int(Config.SLIME_POOL_COLOR[3] * (time_left / Config.SLIME_POOL_FADE_TIME))
            self.color = (Config.SLIME_POOL_COLOR[0], Config.SLIME_POOL_COLOR[1], 
                         Config.SLIME_POOL_COLOR[2], max(0, alpha))

        # Morrer quando tempo acabar
        if self.age >= self.lifetime:
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha poça com transparência."""
        if self.dead or self.color[3] == 0:
            return

        # Surface temporária para transparência
        pool_surf = pygame.Surface((int(self.radius * 2), int(self.radius * 2)),
                                   pygame.SRCALPHA)
        pygame.draw.circle(pool_surf, self.color,
                          (int(self.radius), int(self.radius)),
                          int(self.radius))

        surface.blit(pool_surf, (int(self.x - self.radius),
                                 int(self.y - self.radius)))

    def can_damage(self) -> bool:
        """Verifica se pode causar dano (cooldown)."""
        return self.last_damage_time >= self.damage_cooldown

    def reset_damage_cooldown(self) -> None:
        """Reseta cooldown de dano."""
        self.last_damage_time = 0.0

    def collides_with_player(self, player_rect: pygame.Rect) -> bool:
        """Verifica se jogador está pisando na poça."""
        if self.dead:
            return False

        # Distância do centro da poça ao centro do jogador
        dx = self.x - player_rect.centerx
        dy = self.y - player_rect.centery
        distance_squared = dx * dx + dy * dy

        player_radius = min(player_rect.width, player_rect.height) / 2
        return distance_squared < (self.radius + player_radius) ** 2