import pygame
import random
from typing import List

from ..core.config import config as Config


class SlimeDrip:
    """Gota de slime com círculo colorido e física variável."""

    def __init__(self, x: float = 0, y: float = 0, effect_width: int = 800, effect_height: int = 600):
        # Estado do pool
        self.active: bool = False
        self.dead: bool = True

        # Posição e tamanho
        self.x: float = x
        self.y: float = y
        self.effect_width: int = effect_width
        self.effect_height: int = effect_height

        # Tamanho variável (0.5x a 1.5x do tamanho original)
        self.scale: float = random.uniform(0.5, 1.5)
        self.radius: float = Config.SLIME_DRIP_RADIUS_MAX * self.scale
        self.damage: int = max(1, int(self.scale * 2))  # Dano baseado no tamanho

        # Física simples - gotas maiores caem mais devagar
        base_speed = random.uniform(100.0, 300.0)
        # Reduz velocidade baseado no tamanho (gotas maiores = mais lentas)
        speed_multiplier = 1.0 - (self.scale - 0.5) * 0.4  # 0.6x a 1.0x velocidade
        self.speed_x: float = random.uniform(-20.0, 20.0) * speed_multiplier
        self.speed_y: float = base_speed * speed_multiplier
        self.gravity: float = 200.0 * speed_multiplier  # Gravidade também reduzida

        # Cor baseada nas cores originais do config
        self.color = random.choice(Config.SLIME_DRIP_COLORS)

    def reset(self, x: float, y: float, effect_width: int = 800, effect_height: int = 600) -> None:
        """Reseta a gota para reutilização no pool."""
        self.active = True
        self.dead = False

        # Posição
        self.x = x
        self.y = y
        self.effect_width = effect_width
        self.effect_height = effect_height

        # Tamanho variável (0.5x a 1.5x do tamanho original)
        self.scale = random.uniform(0.5, 1.5)
        self.radius = Config.SLIME_DRIP_RADIUS_MAX * self.scale
        self.damage = max(1, int(self.scale * 2))  # Dano baseado no tamanho

        # Física - gotas maiores caem mais devagar
        base_speed = random.uniform(100.0, 300.0)
        speed_multiplier = 1.0 - (self.scale - 0.5) * 0.4  # 0.6x a 1.0x velocidade
        self.speed_x = random.uniform(-20.0, 20.0) * speed_multiplier
        self.speed_y = base_speed * speed_multiplier
        self.gravity = 200.0 * speed_multiplier

        # Cor baseada nas cores originais do config
        self.color = random.choice(Config.SLIME_DRIP_COLORS)

    def update(self, dt: float) -> None:
        """Atualiza a física da gota e animação."""
        if not self.active or self.dead:
            return

        # Aplicar gravidade
        self.speed_y += self.gravity * dt

        # Movimento
        self.x += self.speed_x * dt
        self.y += self.speed_y * dt

        # Morrer se sair da tela
        if self.y > self.effect_height + 100 or self.x < -100 or self.x > self.effect_width + 100:
            self.dead = True
            self.active = False

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha a gota como um círculo colorido."""
        if not self.active or self.dead:
            return

        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), int(self.radius))

    def collides_with_player(self, player_rect: pygame.Rect) -> bool:
        """Verifica colisão circular com o jogador."""
        if not self.active or self.dead:
            return False

        # Distância ao centro do jogador
        dx = self.x - player_rect.centerx
        dy = self.y - player_rect.centery
        distance_squared = dx * dx + dy * dy

        # Raio total (jogador + gota)
        total_radius = player_rect.width // 2 + self.radius

        return distance_squared <= total_radius * total_radius


class SlimeDripPool:
    """
    Pool Pattern para gotas de slime: gerencia uma coleção reutilizável de gotas,
    evitando criar e destruir objetos repetidamente.
    """

    def __init__(self, initial_size: int = 20):
        """
        Inicializa o pool com gotas inativas.

        Args:
            initial_size: Quantidade inicial de gotas no pool
        """
        self.pool: List[SlimeDrip] = []
        self.active: List[SlimeDrip] = []

        # Pré-cria gotas inativas
        for _ in range(initial_size):
            drip = SlimeDrip()
            drip.active = False
            drip.dead = True
            self.pool.append(drip)

    def get(self, x: float, y: float, effect_width: int = 800, effect_height: int = 600) -> SlimeDrip:
        """
        Obtém uma gota do pool, reutilizando uma inativa ou criando nova.

        Args:
            x, y: Posição inicial da gota
            effect_width, effect_height: Dimensões da área de efeito

        Returns:
            Gota ativa e configurada
        """
        # Procura uma gota inativa no pool
        for drip in self.pool:
            if not drip.active:
                drip.reset(x, y, effect_width, effect_height)
                self.active.append(drip)
                return drip

        # Se não houver disponível, cria nova
        drip = SlimeDrip(x, y, effect_width, effect_height)
        self.pool.append(drip)
        self.active.append(drip)
        return drip

    def release(self, drip: SlimeDrip) -> None:
        """
        Libera uma gota de volta ao pool, marcando como inativa.

        Args:
            drip: Gota a ser desativada
        """
        if drip in self.active:
            drip.active = False
            drip.dead = True
            self.active.remove(drip)

    def update(self, dt: float) -> None:
        """
        Atualiza todas as gotas ativas e libera as que morreram.

        Args:
            dt: Delta time em segundos
        """
        for drip in self.active[:]:  # Copia a lista para iterar com segurança
            drip.update(dt)
            if drip.dead:
                self.release(drip)

    def draw(self, surface: pygame.Surface) -> None:
        """
        Desenha todas as gotas ativas.

        Args:
            surface: Superfície do pygame onde desenhar
        """
        for drip in self.active:
            drip.draw(surface)

    def check_collisions(self, player_rect: pygame.Rect) -> int:
        """
        Verifica colisões com o jogador e retorna dano total.
        Gotas que colidem são automaticamente liberadas.

        Args:
            player_rect: Retângulo do jogador

        Returns:
            Dano total causado pelas colisões
        """
        total_damage = 0
        for drip in self.active[:]:  # Copia para iterar com segurança
            if drip.collides_with_player(player_rect):
                drip.dead = True  # Gota morre ao colidir
                drip.active = False
                total_damage += drip.damage
                self.active.remove(drip)
        return total_damage

    def clear_active(self) -> None:
        """Remove todas as gotas ativas, devolvendo-as ao pool."""
        for drip in self.active[:]:
            self.release(drip)

    def get_active_count(self) -> int:
        """Retorna a quantidade de gotas atualmente ativas."""
        return len(self.active)

    def get_pool_size(self) -> int:
        """Retorna o tamanho total do pool (ativas + inativas)."""
        return len(self.pool)


class SlimeDrippingEffect:
    """Efeito simples de gotas de slime caindo - wrapper para o pool."""

    def __init__(self, effect_width: int, effect_height: int, difficulty_multiplier: float = 1.0):
        self.effect_width: int = effect_width
        self.effect_height: int = effect_height

        # Pool de gotas
        self.drip_pool = SlimeDripPool(initial_size=Config.SLIME_DRIP_MAX_ACTIVE * 2)

        # Spawn settings
        self.spawn_timer: float = 0.0
        self.spawn_interval: float = Config.SLIME_DRIP_SPAWN_INTERVAL / difficulty_multiplier
        self.max_drips: int = Config.SLIME_DRIP_MAX_ACTIVE

    def update(self, dt: float, boss_x: float, boss_y: float,
               boss_width: int, player_x: float, player_y: float) -> None:
        """Atualiza todas as gotas e spawna novas."""

        # Atualizar pool
        self.drip_pool.update(dt)

        # Spawn de novas gotas
        self.spawn_timer += dt
        if (self.spawn_timer >= self.spawn_interval and
            self.drip_pool.get_active_count() < self.max_drips):
            self.spawn_timer = 0
            self._spawn_drip(boss_x, boss_y, boss_width)

    def _spawn_drip(self, boss_x: float, boss_y: float, boss_width: int) -> None:
        """Spawna uma gota aleatoriamente acima do boss."""
        x = boss_x + random.uniform(0, boss_width)
        y = boss_y - 50  # 50 pixels acima do boss
        self.drip_pool.get(x, y, self.effect_width, self.effect_height)

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha todas as gotas."""
        self.drip_pool.draw(surface)

    def check_collisions(self, player_rect: pygame.Rect) -> int:
        """Verifica colisões com o jogador e retorna dano total."""
        return self.drip_pool.check_collisions(player_rect)
