import pygame
import random
from typing import Set


class AirStrikeBomb:
    """Bomba do bombardeio aéreo - estilo simplificado como MineExplosion."""

    def __init__(
        self,
        target_x: float,
        target_y: float,
        explosion_radius: float = 80.0,
        fall_speed: float = 800.0,
        damage: int = 100,
    ):
        self.target_x = target_x
        self.target_y = target_y
        self.explosion_radius = explosion_radius
        self.damage = damage
        self.fall_speed = fall_speed

        # Posição (começa acima da tela)
        self.x = target_x
        self.y = -50.0

        # Estados
        self.dead = False
        self.exploded = False
        self.state = "falling"  # "falling", "exploding", "done"

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
            self.y += self.fall_speed * dt
            self.rotation += 150 * dt

            if self.y >= self.target_y:
                self.y = self.target_y
                self.state = "exploding"
                self.exploded = True

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
        """Desenha meteoro com bom contraste."""

        # 1. Glow externo
        glow_size = 25
        glow = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
        pygame.draw.circle(
            glow, (255, 150, 50, 70), (glow_size // 2, glow_size // 2), glow_size // 2
        )
        surface.blit(
            glow,
            (int(self.x) - glow_size // 2, int(self.y) - glow_size // 2),
            special_flags=pygame.BLEND_RGBA_ADD,
        )

        # 2. Corpo do meteoro
        bomb = pygame.Surface((20, 30), pygame.SRCALPHA)
        pygame.draw.ellipse(bomb, (140, 140, 140), (4, 4, 12, 22))  # Corpo cinza claro
        pygame.draw.ellipse(bomb, (200, 200, 200), (5, 5, 6, 10))  # Highlight
        pygame.draw.polygon(
            bomb, (255, 180, 50), [(10, 4), (6, 10), (14, 10)]
        )  # Ponta laranja

        rotated = pygame.transform.rotate(bomb, -self.rotation)
        rect = rotated.get_rect(center=(int(self.x), int(self.y)))
        surface.blit(rotated, rect)

        # 3. Trail de fogo
        for i in range(3):
            y = self.y - 25 - i * 12
            if y > 0:
                alpha = 120 - i * 35
                size = 5 + i * 2
                s = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
                pygame.draw.circle(s, (255, 120, 50, alpha), (size, size), size)
                if size > 2:
                    pygame.draw.circle(
                        s, (255, 220, 100, alpha), (size, size), size // 2
                    )
                surface.blit(
                    s,
                    (int(self.x) - size, int(y) - size),
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
