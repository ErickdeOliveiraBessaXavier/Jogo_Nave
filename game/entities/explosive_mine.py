import pygame
import random
from ..core.config import Config
from ..core import colors

class ExplosiveMine:
    def __init__(self, x: float | None = None, y: float | None = None):
        self.radius = 20  # Visual radius of the mine
        self.explosion_radius = self.radius * 8  # Explosion radius is 4 times the visual radius
        if x is None:
            self.x = random.randint(self.radius, Config.SCREEN_WIDTH - self.radius)
        else:
            self.x = x
        if y is None:
            self.y = -self.radius
        else:
            self.y = y
        self.health = 5
        self.max_health = 5
        self.speed = 50
        self.dead = False
        # Armazenar cores como tuplas explícitas
        self.color: tuple[int, int, int] = colors.RED
        self.outline_color: tuple[int, int, int] = colors.ORANGE

        self.shake_timer = 0.0
        self.shake_intensity = 0
        self.flash_timer = 0.0
        self.flash_interval = 0.1
        self.pre_explosion_timer = 0.0
        self.is_exploding = False

        # Pulsing animation
        self.animation_timer = 0.0
        self.pulse_scale = 1.0

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x) - self.radius, int(self.y) - self.radius, self.radius * 2, self.radius * 2)

    def take_damage(self, amount: int):
        if self.dead or self.is_exploding:
            return
        self.health -= amount
        if self.health <= 0:
            self.is_exploding = True
            self.pre_explosion_timer = 3.0
        else:
            self.shake_timer = 0.2
            self.shake_intensity = (self.max_health - self.health) * 2

    def update(self, dt: float):
        if self.is_exploding:
            self.pre_explosion_timer -= dt
            self.flash_timer += dt
            if self.flash_timer >= self.flash_interval:
                # Alternar cores diretamente com tuplas
                if self.color == colors.RED:
                    self.color = colors.YELLOW
                else:
                    self.color = colors.RED
                self.flash_timer = 0.0
            if self.pre_explosion_timer <= 0:
                self.dead = True
            
            # Reset pulsing animation when exploding
            self.pulse_scale = 1.0
            return

        self.y += self.speed * dt

        if self.shake_timer > 0:
            self.shake_timer -= dt

        # Pulsing animation
        self.animation_timer += dt * 3  # velocidade da pulsação
        self.pulse_scale = 1.0 + 0.2 * abs(
            pygame.math.Vector2(1, 0).rotate(self.animation_timer * 57.3).x
        )

    def is_off_screen(self) -> bool:
        return self.y > Config.SCREEN_HEIGHT + self.radius

    def draw(self, surface: pygame.Surface):
        x, y = self.x, self.y
        if self.shake_timer > 0:
            x += random.randint(-self.shake_intensity, self.shake_intensity)
            y += random.randint(-self.shake_intensity, self.shake_intensity)

        pulsing_radius = self.radius * self.pulse_scale
        pygame.draw.circle(surface, self.outline_color, (int(x), int(y)), int(pulsing_radius))
        pygame.draw.circle(surface, self.color, (int(x), int(y)), int(pulsing_radius) - 4)

        if self.is_exploding:
            # Draw explosion radius indicator
            progress = 1 - (self.pre_explosion_timer / 3.0)
            start_alpha = 0.2 * 255
            end_alpha = 0.7 * 255
            alpha = start_alpha + (end_alpha - start_alpha) * progress

            indicator_surface = pygame.Surface((self.explosion_radius * 2, self.explosion_radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(indicator_surface, (255, 255, 255, int(alpha)), (self.explosion_radius, self.explosion_radius), self.explosion_radius)
            surface.blit(indicator_surface, (self.x - self.explosion_radius, self.y - self.explosion_radius))

    def get_points_value(self) -> int:
        return 250