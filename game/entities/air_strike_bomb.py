import random
from typing import Callable, Optional, Set

import pygame

from ..core.upgrades_config import (
    AIR_STRIKE_BOMB_DAMAGE,
    AIR_STRIKE_BOMB_FALL_SPEED,
    AIR_STRIKE_BOMB_RADIUS,
)


class AirStrikeBomb:
    """Bomba do bombardeio aéreo - estilo simplificado como MineExplosion."""

    def __init__(
        self,
        target_x: float,
        target_y: float,
        explosion_radius: float = AIR_STRIKE_BOMB_RADIUS,
        fall_speed: float = AIR_STRIKE_BOMB_FALL_SPEED,
        damage: int = AIR_STRIKE_BOMB_DAMAGE,
        on_explode: Optional[Callable[[], None]] = None,
        on_fall: Optional[Callable[[], None]] = None,
    ):
        self.target_x = target_x
        self.target_y = target_y
        self.explosion_radius = explosion_radius
        self.damage = damage
        self.fall_speed = fall_speed
        self.on_explode = on_explode
        self.on_fall = on_fall

        # Posição inicial: sempre de cima, acima do alvo
        # Garante que a bomba caia sempre no mesmo local que o marcador
        screen = pygame.display.get_surface()
        screen_width = screen.get_width() if screen else 1600
        screen_height = screen.get_height() if screen else 900

        # Validar que o alvo está dentro da tela
        self.clamped_target_x = max(40, min(screen_width - 40, target_x))
        self.clamped_target_y = max(60, min(screen_height - 40, target_y))

        self.target_x = self.clamped_target_x
        self.target_y = self.clamped_target_y

        # A bomba sempre vem de cima, diretamente acima do alvo
        self.start_x = self.clamped_target_x
        self.start_y = -100  # 100 pixels acima da tela

        # Movimento vertical simples para baixo (mais realista e preciso)
        self.vx = 0.0
        self.vy = fall_speed

        # Posição atual (inicia na posição de spawn)
        self.x = self.start_x
        self.y = self.start_y

        # Estados
        self.dead = False
        self.exploded = False
        self.state = "falling"  # "falling", "exploding", "done"
        self._fall_sound_played = False  # Flag para tocar som de queda apenas uma vez

        # Animação
        self.explosion_timer = 0.0
        self.explosion_duration = 0.5
        self.rotation = random.uniform(0, 360)

        # Rastrear inimigos atingidos
        self.hit_enemies: Set[int] = set()

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x) - 6, int(self.y) - 12, 12, 24)

    @property
    def exploding(self) -> bool:
        return self.state == "exploding"

    @property
    def damage_active(self) -> bool:
        return (
            self.state == "exploding"
            and self.explosion_timer < self.explosion_duration * 0.8
        )

    @property
    def explosion_progress(self) -> float:
        if self.state != "exploding":
            return 0.0
        return min(1.0, self.explosion_timer / self.explosion_duration)

    @property
    def current_explosion_radius(self) -> float:
        if self.state != "exploding":
            return 0.0
        return self.explosion_radius * self.explosion_progress

    def update(self, dt: float) -> None:
        if self.state == "falling":
            # Movimento diagonal
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.rotation += 150 * dt

            # Tocar som de queda quando a bomba fica visível na tela
            if (
                not self._fall_sound_played
                and self.y > 0
                and self.x < pygame.display.get_surface().get_width()
                if pygame.display.get_surface()
                else 1600
            ):
                self._fall_sound_played = True
                if self.on_fall:
                    self.on_fall()

            # Verificar se chegou próximo ao alvo (margem de 5 pixels)
            if abs(self.x - self.target_x) < 5 and abs(self.y - self.target_y) < 5:
                self.x = self.target_x
                self.y = self.target_y
                self.state = "exploding"
                self.exploded = True
                # Tocar som de explosão
                if self.on_explode:
                    self.on_explode()

        elif self.state == "exploding":
            self.explosion_timer += dt
            if self.explosion_timer >= self.explosion_duration:
                self.state = "done"
                self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        if self.dead:
            return

        if self.state == "falling":
            self._draw_bomb(surface)
        elif self.state == "exploding":
            self._draw_explosion(surface)

    def _draw_bomb(self, surface: pygame.Surface) -> None:
        """Desenha meteoro estilo pixel art vibrante com cores personalizadas."""

        # Cores personalizadas
        COLOR_YELLOW: tuple[int, int, int] = (242, 186, 82)  # #F2BA52
        COLOR_ORANGE: tuple[int, int, int] = (242, 105, 56)  # #F26938
        COLOR_RED: tuple[int, int, int] = (191, 48, 48)  # #BF3030

        # Gradiente de cores do meteoro (de trás para frente)
        trail_colors: list[tuple[int, int, int, int]] = [
            (*COLOR_RED, 180),  # Vermelho escuro na ponta
            (*COLOR_RED, 220),  # Vermelho
            (*COLOR_ORANGE, 240),  # Laranja
            (*COLOR_ORANGE, 255),  # Laranja forte
            (*COLOR_YELLOW, 255),  # Amarelo
        ]

        # Desenhar trilha de fogo com gradiente
        trail_length = 50
        num_segments = 12

        for i in range(num_segments):
            progress = i / num_segments
            y_offset = -trail_length * progress
            y_pos = self.y + y_offset

            if y_pos > -10:
                # Interpolar cor baseado na posição
                color_index: int = min(
                    int(progress * len(trail_colors)), len(trail_colors) - 1
                )
                color: tuple[int, int, int, int] = trail_colors[color_index]

                # Tamanho diminui com a distância
                size = int(12 * (1 - progress * 0.7))
                if size > 1:
                    s = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
                    pygame.draw.circle(s, color, (size, size), size)
                    surface.blit(
                        s,
                        (int(self.x) - size, int(y_pos) - size),
                        special_flags=pygame.BLEND_RGBA_ADD,
                    )

        # Partículas dispersas na trilha (formato gota d'água)
        for i in range(8):
            offset_y = -20 - i * 8
            particle_y = self.y + offset_y
            particle_x = self.x  # Removido offset_x para manter em linha reta

            if particle_y > -5:
                # Cor aleatória entre as cores personalizadas
                color_choice: tuple[int, int, int, int] = random.choice(
                    [
                        (*COLOR_RED, 200),
                        (*COLOR_ORANGE, 200),
                        (*COLOR_YELLOW, 180),
                    ]
                )

                # Desenhar partícula em forma de gota d'água
                particle_size = random.randint(3, 5)
                s = pygame.Surface(
                    (particle_size * 2, particle_size * 3), pygame.SRCALPHA
                )

                # Círculo superior (cabeça da gota)
                pygame.draw.circle(
                    s, color_choice, (particle_size, particle_size), particle_size
                )
                # Triângulo inferior (cauda da gota)
                pygame.draw.polygon(
                    s,
                    color_choice,
                    [
                        (particle_size - particle_size // 2, particle_size),
                        (particle_size + particle_size // 2, particle_size),
                        (particle_size, particle_size * 2),
                    ],
                )

                surface.blit(
                    s,
                    (int(particle_x) - particle_size, int(particle_y) - particle_size),
                    special_flags=pygame.BLEND_RGBA_ADD,
                )

        # Núcleo do meteoro (cabeça) - formato gota d'água
        # Camada laranja (formato gota)
        orange_size = 12
        orange = pygame.Surface((orange_size * 2, orange_size * 3), pygame.SRCALPHA)
        # Círculo superior
        pygame.draw.circle(
            orange, (*COLOR_ORANGE, 255), (orange_size, orange_size), orange_size
        )
        # Cauda da gota
        pygame.draw.polygon(
            orange,
            (*COLOR_ORANGE, 255),
            [
                (orange_size - orange_size // 2, orange_size),
                (orange_size + orange_size // 2, orange_size),
                (orange_size, orange_size * 2),
            ],
        )
        surface.blit(
            orange,
            (int(self.x) - orange_size, int(self.y) - orange_size),
            special_flags=pygame.BLEND_RGBA_ADD,
        )

        # Camada amarela (formato gota)
        yellow_size = 8
        yellow = pygame.Surface((yellow_size * 2, yellow_size * 3), pygame.SRCALPHA)
        # Círculo superior
        pygame.draw.circle(
            yellow, (*COLOR_YELLOW, 255), (yellow_size, yellow_size), yellow_size
        )
        # Cauda da gota
        pygame.draw.polygon(
            yellow,
            (*COLOR_YELLOW, 255),
            [
                (yellow_size - yellow_size // 2, yellow_size),
                (yellow_size + yellow_size // 2, yellow_size),
                (yellow_size, yellow_size * 2),
            ],
        )
        surface.blit(
            yellow,
            (int(self.x) - yellow_size, int(self.y) - yellow_size),
            special_flags=pygame.BLEND_RGBA_ADD,
        )

        # Núcleo amarelo claro (centro)
        white_size = 4
        white = pygame.Surface((white_size * 2, white_size * 2), pygame.SRCALPHA)
        pygame.draw.circle(
            white, (255, 255, 200, 255), (white_size, white_size), white_size
        )
        surface.blit(
            white,
            (int(self.x) - white_size, int(self.y) - white_size),
            special_flags=pygame.BLEND_RGBA_ADD,
        )

    def _draw_explosion(self, surface: pygame.Surface) -> None:
        """Desenha explosão - estilo MineExplosion."""
        progress = self.explosion_progress
        radius = int(self.explosion_radius * progress)

        if radius <= 0:
            return

        alpha = int(255 * (1 - progress))
        size = int(self.explosion_radius * 2)

        # Desenha um círculo que expande (igual mine_explosion)
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        color = (255, int(255 * (1 - progress)), 0, alpha)
        pygame.draw.circle(s, color, (size // 2, size // 2), radius)
        surface.blit(s, (int(self.x) - size // 2, int(self.y) - size // 2))
