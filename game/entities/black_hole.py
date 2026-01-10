import pygame
import math
import random
from typing import Any, TypedDict

from ..core.sound import sound_manager


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
        self.speed_y = -50.0  # Velocidade para cima (pixels/segundo)

        # Raios do buraco negro (começam pequenos)
        self.core_radius = 10.0  # Núcleo central (começa pequeno)
        self.event_horizon = self.core_radius * 2  # Raio de destruição (proporcional ao núcleo)
        self.pull_radius = 250.0  # Raio de atração

        # Raios finais (crescimento)
        self.max_core_radius = 60.0
        self.max_event_horizon = 120.0
        self.max_pull_radius = 800.0
        
        # Taxa de crescimento (por segundo)
        self.growth_rate = 15.0  # Cresce 15 pixels de raio por segundo

        # Partículas do disco de acreção
        self.particles: list[Particle] = []
        self._create_particles()

        # Animação
        self.animation_timer = 0.0

    def _create_particles(self):
        """Cria partículas para o disco de acreção."""
        colors = [
            (255, 107, 53),   # laranja
            (247, 147, 30),   # laranja claro
            (255, 215, 0),    # dourado
            (255, 69, 0),     # vermelho alaranjado
            (255, 140, 0),    # laranja escuro
            (255, 170, 0),    # amarelo alaranjado
        ]

        for _ in range(150):
            angle = random.uniform(0, math.pi * 2)
            distance = random.uniform(self.pull_radius * 0.5, self.pull_radius * 1.0)
            particle: Particle = {
                'x': self.x + math.cos(angle) * distance,
                'y': self.y + math.sin(angle) * distance,
                'size': random.randint(2, 4),
                'angle': angle,
                'orbit_radius': distance,
                'base_speed': random.uniform(0.2, 0.5),
                'opacity': random.uniform(0.3, 1.0),
                'color': random.choice(colors)
            }
            self.particles.append(particle)

    def update(self, dt: float):
        """Atualiza o buraco negro."""
        self.lifetime += dt
        self.animation_timer += dt

        # Mover para cima
        self.y += self.speed_y * dt

        # Crescer gradualmente até atingir tamanho máximo
        if self.core_radius < self.max_core_radius:
            self.core_radius = min(self.max_core_radius, self.core_radius + self.growth_rate * dt)
            self.event_horizon = self.core_radius * 2
            self.pull_radius = min(self.max_pull_radius, self.pull_radius + self.growth_rate * 5 * dt)

        # Morrer se sair da tela (parte de cima)
        if self.y < -self.pull_radius:
            self.dead = True
            return

        # Atualizar partículas do disco
        for particle in self.particles:
            dx = self.x - particle['x']
            dy = self.y - particle['y']
            distance = math.sqrt(dx * dx + dy * dy)

            # Aceleração em direção ao centro
            distance_factor = max(0.3, distance / (self.pull_radius * 0.5))
            acceleration_factor = 1 / distance_factor

            # Velocidade angular
            angular_speed = (1 / max(1, distance)) * 20 * acceleration_factor
            particle['angle'] += angular_speed * particle['base_speed']

            # Espiral em direção ao centro
            spiral_speed = particle['base_speed'] * 0.1 * acceleration_factor
            particle['orbit_radius'] -= spiral_speed

            # Nova posição orbital
            particle['x'] = self.x + math.cos(particle['angle']) * particle['orbit_radius']
            particle['y'] = self.y + math.sin(particle['angle']) * particle['orbit_radius']

            # Fade próximo ao buraco negro
            fade_distance = self.pull_radius * 0.3
            if distance < fade_distance:
                particle['opacity'] = max(0.2, distance / fade_distance)

            # Resetar se ficar muito próximo
            if particle['orbit_radius'] < self.core_radius + 20:
                angle = random.uniform(0, math.pi * 2)
                distance = random.uniform(self.pull_radius * 0.5, self.pull_radius * 1.0)
                particle['x'] = self.x + math.cos(angle) * distance
                particle['y'] = self.y + math.sin(angle) * distance
                particle['orbit_radius'] = distance
                particle['angle'] = angle
                particle['opacity'] = random.uniform(0.3, 1.0)

    def apply_gravity_to_enemy(self, enemy: Any, dt: float) -> bool:
        """Aplica força gravitacional a um inimigo.
        
        Returns:
            True se o inimigo deve ser destruído (chegou ao horizonte de eventos)
        """
        # Calcular distância ao buraco negro
        enemy_x = getattr(enemy, 'x', 0) + getattr(enemy, 'w', 0) / 2
        enemy_y = getattr(enemy, 'y', 0) + getattr(enemy, 'h', 0) / 2

        dx = self.x - enemy_x
        dy = self.y - enemy_y
        distance = math.sqrt(dx * dx + dy * dy)

        # Verificar se deve destruir
        if distance < self.event_horizon:
            return True

        # Aplicar força gravitacional se dentro do raio de atração
        if distance < self.pull_radius:
            # Força aumenta exponencialmente perto do centro
            pull_strength = 1.0 - (distance / self.pull_radius)
            pull_strength = pull_strength ** 2  # Exponencial

            # Velocidade de atração (pixels/segundo)
            pull_speed = 300 * pull_strength

            # Normalizar vetor de direção
            if distance > 0:
                dx /= distance
                dy /= distance

            # Aplicar movimento
            enemy.x += dx * pull_speed * dt
            enemy.y += dy * pull_speed * dt

        return False

    def draw(self, surface: pygame.Surface):
        """Desenha o buraco negro."""
        # Desenhar partículas do disco de acreção primeiro
        for particle in self.particles:
            # Criar superfície com alpha para a partícula
            particle_surf = pygame.Surface((particle['size'], particle['size']), pygame.SRCALPHA)
            color = particle['color'] + (int(particle['opacity'] * 255),)
            particle_surf.fill(color)
            surface.blit(particle_surf, (int(particle['x']), int(particle['y'])))

        # Desenhar área de distorção (anel semi-transparente)
        distortion_size = int(self.core_radius * 4)
        distortion_surf = pygame.Surface((distortion_size, distortion_size), pygame.SRCALPHA)
        for i in range(3):
            radius = int(self.core_radius + 20 + i * 15)
            alpha = int(50 - i * 15)
            pygame.draw.circle(
                distortion_surf,
                (100, 50, 150, alpha),
                (distortion_size // 2, distortion_size // 2),
                radius,
                3
            )
        surface.blit(
            distortion_surf,
            (int(self.x - distortion_size // 2), int(self.y - distortion_size // 2))
        )

        # Desenhar núcleo do buraco negro (preto absoluto)
        pygame.draw.circle(
            surface,
            (0, 0, 0),
            (int(self.x), int(self.y)),
            int(self.core_radius)
        )

        # Garantir preto absoluto com segunda camada
        pygame.draw.circle(
            surface,
            (0, 0, 0),
            (int(self.x), int(self.y)),
            int(self.core_radius)
        )

        # Borda sutil do horizonte de eventos
        pygame.draw.circle(
            surface,
            (50, 50, 50),
            (int(self.x), int(self.y)),
            int(self.core_radius),
            1
        )

    @property
    def rect(self) -> pygame.Rect:
        """Retorna um retângulo para verificações básicas."""
        return pygame.Rect(
            int(self.x - self.pull_radius),
            int(self.y - self.pull_radius),
            self.pull_radius * 2,
            self.pull_radius * 2
        )
