import pygame
import math
import random
from typing import Any, TypedDict

from ..core.sound import sound_manager
from ..core.config import config
from ..core.colors import BLACK_HOLE_PARTICLE_COLORS


class Particle(TypedDict):
    """Estrutura de uma partícula do disco de acreção."""

    x: float
    y: float
    size: int
    angle: float
    orbit_radius: float
    base_speed: float
    opacity: float
    color: tuple[int, int, int]


class BlackHole:
    """Buraco negro que sobe pela tela, crescendo e atraindo inimigos."""

    def __init__(self, x: float, y: float, duration: float):
        self.x = x
        self.y = y
        self.duration = duration  # Não usado, mas mantido para compatibilidade
        self.lifetime = 0.0
        self.dead = False

        # Tocar som do buraco negro
        sound_manager.play_black_hole()

        # Movimento
        self.speed_y = (
            config.BLACK_HOLE_SPEED_Y
        )  # Velocidade para cima (pixels/segundo)

        # Raios do buraco negro (começam pequenos)
        self.core_radius = (
            config.BLACK_HOLE_INITIAL_CORE_RADIUS
        )  # Núcleo central (começa pequeno)
        self.event_horizon = (
            self.core_radius * 2
        )  # Raio de destruição (proporcional ao núcleo)
        self.pull_radius = config.BLACK_HOLE_INITIAL_PULL_RADIUS  # Raio de atração

        # Raios finais (crescimento)
        self.max_core_radius = config.BLACK_HOLE_MAX_CORE_RADIUS
        self.max_event_horizon = config.BLACK_HOLE_MAX_CORE_RADIUS * 2
        self.max_pull_radius = config.BLACK_HOLE_MAX_PULL_RADIUS

        # Taxa de crescimento (por segundo)
        self.growth_rate = (
            config.BLACK_HOLE_GROWTH_RATE
        )  # Cresce 15 pixels de raio por segundo

        # Partículas do disco de acreção
        self.particles: list[Particle] = []
        self._create_particles()

        # Animação
        self.animation_timer = 0.0

    def _create_particles(self):
        """Cria partículas para o disco de acreção."""
        for _ in range(config.BLACK_HOLE_PARTICLE_COUNT):  # Usar configuração otimizada
            angle = random.uniform(0, math.pi * 2)
            distance = random.uniform(self.pull_radius * 0.5, self.pull_radius * 1.0)
            particle: Particle = {
                "x": self.x + math.cos(angle) * distance,
                "y": self.y + math.sin(angle) * distance,
                "size": random.randint(2, 4),
                "angle": angle,
                "orbit_radius": distance,
                "base_speed": random.uniform(0.2, 0.5),
                "opacity": random.uniform(0.3, 1.0),
                "color": random.choice(
                    BLACK_HOLE_PARTICLE_COLORS
                ),  # Usar constante de cores
            }
            self.particles.append(particle)

    def update(self, dt: float):
        """Atualiza o buraco negro.

        Args:
            dt: Delta time
        """
        self.lifetime += dt
        self.animation_timer += dt

        # Mover para cima
        self.y += self.speed_y * dt

        # Crescer gradualmente até atingir tamanho máximo
        if self.core_radius < self.max_core_radius:
            self.core_radius = min(
                self.max_core_radius, self.core_radius + self.growth_rate * dt
            )
            self.event_horizon = self.core_radius * 2
            self.pull_radius = min(
                self.max_pull_radius, self.pull_radius + self.growth_rate * 5 * dt
            )

        # Morrer se sair da tela (parte de cima)
        if self.y < -self.pull_radius:
            self.dead = True
            return

        # Atualizar todas as partículas do disco
        for particle in self.particles:
            dx = self.x - particle["x"]
            dy = self.y - particle["y"]
            distance_squared = (
                dx * dx + dy * dy
            )  # Usar distância ao quadrado (evita sqrt)
            distance = math.sqrt(
                distance_squared
            )  # Manter para cálculos que precisam do valor real

            # Aceleração em direção ao centro
            distance_factor = max(0.3, distance / (self.pull_radius * 0.5))
            acceleration_factor = 1 / distance_factor

            # Velocidade angular
            angular_speed = (1 / max(1, distance)) * 20 * acceleration_factor
            particle["angle"] += angular_speed * particle["base_speed"]

            # Espiral em direção ao centro
            spiral_speed = particle["base_speed"] * 0.1 * acceleration_factor
            particle["orbit_radius"] -= spiral_speed

            # Nova posição orbital
            particle["x"] = (
                self.x + math.cos(particle["angle"]) * particle["orbit_radius"]
            )
            particle["y"] = (
                self.y + math.sin(particle["angle"]) * particle["orbit_radius"]
            )

            # Fade próximo ao buraco negro (usar comparação ao quadrado para evitar sqrt)
            fade_distance_squared = (self.pull_radius * 0.3) ** 2
            if distance_squared < fade_distance_squared:
                fade_distance = self.pull_radius * 0.3
                particle["opacity"] = max(0.2, distance / fade_distance)

            # Resetar se ficar muito próximo
            if particle["orbit_radius"] < self.core_radius + 20:
                angle = random.uniform(0, math.pi * 2)
                distance = random.uniform(
                    self.pull_radius * 0.5, self.pull_radius * 1.0
                )
                particle["x"] = self.x + math.cos(angle) * distance
                particle["y"] = self.y + math.sin(angle) * distance
                particle["orbit_radius"] = distance
                particle["angle"] = angle
                particle["opacity"] = random.uniform(0.3, 1.0)

    def is_enemy_in_range(self, enemy: Any) -> bool:
        """Verifica rapidamente se um inimigo está dentro do raio de atração.

        Returns:
            True se o inimigo está dentro do pull_radius
        """
        enemy_x = getattr(enemy, "x", 0) + getattr(enemy, "w", 0) / 2
        enemy_y = getattr(enemy, "y", 0) + getattr(enemy, "h", 0) / 2

        dx = self.x - enemy_x
        dy = self.y - enemy_y
        distance_squared = dx * dx + dy * dy

        # Usar distância ao quadrado para evitar sqrt
        return distance_squared < (self.pull_radius * self.pull_radius)

    def process_all_enemies(
        self, enemies: list[Any], dt: float, spawn_explosion_callback: Any = None
    ) -> None:
        """Processa todos os inimigos de uma vez, aplicando gravidade e destruindo quando necessário.

        Args:
            enemies: Lista de todos os inimigos
            dt: Delta time
            spawn_explosion_callback: Callback para spawnar explosões quando inimigos são destruídos
        """
        pull_radius_squared = self.pull_radius * self.pull_radius
        event_horizon_squared = self.event_horizon * self.event_horizon

        for enemy in enemies:
            if getattr(enemy, "dead", False):
                continue

            # Verificar se é um boss - bosses são imunes ao buraco negro
            enemy_class_name = enemy.__class__.__name__
            if enemy_class_name in ("Boss", "SlimeBoss", "SpikeBoss"):
                continue

            # Calcular distância ao buraco negro
            enemy_x = getattr(enemy, "x", 0) + getattr(enemy, "w", 0) / 2
            enemy_y = getattr(enemy, "y", 0) + getattr(enemy, "h", 0) / 2

            dx = self.x - enemy_x
            dy = self.y - enemy_y
            distance_squared = dx * dx + dy * dy

            # Verificar se está fora do raio de atração (usando distância ao quadrado)
            if distance_squared >= pull_radius_squared:
                continue

            # Verificar se deve destruir (usando distância ao quadrado)
            if distance_squared < event_horizon_squared:
                enemy.dead = True
                if spawn_explosion_callback:
                    spawn_explosion_callback(enemy_x, enemy_y, size=30)
                continue

            # Aplicar força gravitacional
            distance = math.sqrt(distance_squared)  # Só calcular sqrt quando necessário

            # Força aumenta exponencialmente perto do centro
            pull_strength = 1.0 - (distance / self.pull_radius)
            pull_strength = pull_strength**2  # Exponencial

            # Velocidade de atração (pixels/segundo)
            pull_speed = config.BLACK_HOLE_PULL_SPEED * pull_strength

            # Normalizar vetor de direção e aplicar movimento
            if distance > 0:
                dx /= distance
                dy /= distance
                enemy.x += dx * pull_speed * dt
                enemy.y += dy * pull_speed * dt

    def draw(self, surface: pygame.Surface):
        """Desenha o buraco negro.

        Args:
            surface: Superfície para desenhar
        """
        # Desenhar todas as partículas do disco de acreção
        # OPT: Usar pygame.draw.circle direto ao invés de criar Surface (muito mais rápido)
        for particle in self.particles:
            color_with_alpha = particle["color"] + (int(particle["opacity"] * 255),)
            pygame.draw.circle(
                surface,
                color_with_alpha,
                (int(particle["x"]), int(particle["y"])),
                particle["size"],
            )

        # Desenhar núcleo do buraco negro (preto absoluto)
        pygame.draw.circle(
            surface, (0, 0, 0), (int(self.x), int(self.y)), int(self.core_radius)
        )

        # Borda sutil do horizonte de eventos
        pygame.draw.circle(
            surface, (50, 50, 50), (int(self.x), int(self.y)), int(self.core_radius), 1
        )

    @property
    def rect(self) -> pygame.Rect:
        """Retorna um retângulo para verificações básicas."""
        return pygame.Rect(
            int(self.x - self.pull_radius),
            int(self.y - self.pull_radius),
            self.pull_radius * 2,
            self.pull_radius * 2,
        )
