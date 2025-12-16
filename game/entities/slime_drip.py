import pygame
import random
import math
from typing import Optional


class SlimeDrip:
    """Gota de slime que cai do boss slime com física realista."""

    def __init__(self, x: float, y: float, effect_width: int, effect_height: int):
        # Propriedades físicas baseadas no código JavaScript
        self.radius = random.uniform(25, 85)  # Raio inicial (25-85 pixels) - um pouco maior
        self.x = x
        self.y = y
        self.speed_x = random.uniform(-0.2, 0.2)  # Movimento lateral suave
        self.speed_y = random.uniform(0.2, 0.5)  # Velocidade de queda
        self.angle = 0
        self.angle_velocity = random.uniform(-0.05, 0.05)  # Rotação
        self.range = random.uniform(5, 15)  # Amplitude do movimento ondulado
        self.gravity = random.uniform(0.003, 0.008)  # Gravidade
        self.vertical_velocity = 0  # Velocidade vertical acumulada

        # Propriedades do jogo
        self.damage = 1  # Dano causado ao jogador
        self.dead = False
        self.effect_width = effect_width
        self.effect_height = effect_height

        # Cores do slime com transparência
        slime_colors = [
            (241, 187, 242, 180),  # #F1BBF2 com alpha 180
            (96, 29, 115, 200),    # #601D73 com alpha 200
            (68, 18, 89, 220)      # #441259 com alpha 220
        ]
        self.color = random.choice(slime_colors)

        # Controle de tamanho mínimo (mais permissivo para gotas pequenas)
        self.min_radius = 4

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
            self.vertical_velocity += self.gravity
            self.speed_y += self.vertical_velocity * dt
            self.angle += self.angle_velocity

        # Diminuir tamanho quando estiver caindo (taxa proporcional ao tamanho)
        if self.y > self.radius * 2:
            # Gotas maiores diminuem mais rápido, gotas menores diminuem mais devagar
            shrink_rate = 0.05 + (self.radius / 80.0) * 0.08  # 0.05-0.13 baseado no tamanho (mais lento)
            self.radius -= shrink_rate * dt * 60

        # Movimento ondulado
        self.x += self.speed_x * math.cos(self.angle) * self.range * dt * 60
        self.y += self.speed_y * dt * 60

        # Reset quando sair da tela ou ficar muito pequena
        if self.y > self.effect_height + 100 or self.radius < self.min_radius:
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha a gota com cores do slime e transparência."""
        if self.dead:
            return

        # Criar superfície temporária para transparência
        temp_surface = pygame.Surface((int(self.radius * 2), int(self.radius * 2)), pygame.SRCALPHA)
        pygame.draw.circle(
            temp_surface,
            self.color,  # Cor com alpha
            (int(self.radius), int(self.radius)),
            int(self.radius)
        )

        # Desenhar na superfície principal
        surface.blit(temp_surface, (int(self.x - self.radius), int(self.y - self.radius)))

    def collides_with_player(self, player_rect: pygame.Rect) -> bool:
        """Verifica colisão circular com o jogador."""
        if self.dead:
            return False

        # Distância entre centros
        dx = self.x - player_rect.centerx
        dy = self.y - player_rect.centery
        distance = math.sqrt(dx*dx + dy*dy)

        # Colisão se a distância for menor que raio da gota + raio do jogador
        player_radius = min(player_rect.width, player_rect.height) / 2
        return distance < (self.radius + player_radius)


class SlimeDrippingEffect:
    """Sistema que gerencia múltiplas gotas de slime."""

    def __init__(self, effect_width: int, effect_height: int):
        self.effect_width = effect_width
        self.effect_height = effect_height
        self.drips: list[SlimeDrip] = []
        self.max_drips = 15  # Máximo de gotas simultâneas
        self.spawn_timer = 0
        self.spawn_interval = 0.3  # Segundos entre spawns

    def update(self, dt: float, boss_x: float, boss_y: float, boss_width: int, player_x: Optional[float] = None) -> None:
        """Atualiza todas as gotas e spawna novas."""
        # Atualizar gotas existentes
        for drip in self.drips[:]:
            drip.update(dt)
            if drip.dead:
                self.drips.remove(drip)

        # Spawn de novas gotas
        self.spawn_timer += dt
        if self.spawn_timer >= self.spawn_interval and len(self.drips) < self.max_drips:
            self.spawn_timer = 0
            self._spawn_drip(boss_x, boss_y, boss_width, player_x)

    def _spawn_drip(self, boss_x: float, boss_y: float, boss_width: int, player_x: Optional[float] = None) -> None:
        """Spawna uma nova gota com maior probabilidade próxima ao jogador."""
        if player_x is not None:
            # Sistema de spawn direcionado ao jogador
            boss_center = boss_x + boss_width / 2
            distance_to_player = abs(boss_center - player_x)

            # Chance maior de spawn próximo ao jogador
            if random.random() < 0.7:  # 70% de chance de spawn direcionado
                # Spawn mais próximo ao jogador
                offset_range = min(distance_to_player * 0.8, boss_width * 0.6)
                if player_x < boss_center:
                    # Jogador à esquerda
                    x = boss_center - random.uniform(0, offset_range)
                else:
                    # Jogador à direita
                    x = boss_center + random.uniform(0, offset_range)
            else:
                # Spawn aleatório normal
                x = boss_x + random.uniform(0, boss_width)
        else:
            # Spawn aleatório se não há jogador
            x = boss_x + random.uniform(0, boss_width)

        # Posição Y ligeiramente acima do boss
        y = boss_y - 10

        drip = SlimeDrip(x, y, self.effect_width, self.effect_height)
        self.drips.append(drip)

    def draw(self, surface: pygame.Surface) -> None:
        """Desenha todas as gotas."""
        for drip in self.drips:
            drip.draw(surface)

    def check_player_collision(self, player_rect: pygame.Rect) -> int:
        """Verifica colisões com o jogador e retorna o dano total."""
        total_damage = 0
        for drip in self.drips[:]:
            if drip.collides_with_player(player_rect):
                total_damage += drip.damage
                drip.dead = True  # Gota some ao acertar
        return total_damage

    def reset(self) -> None:
        """Remove todas as gotas."""
        self.drips.clear()
        self.spawn_timer = 0