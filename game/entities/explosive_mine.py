from typing import TYPE_CHECKING
import random

import pygame

from ..core import colors
from ..core.assets import get_image
from ..core.config import config as Config
from ..core.sprite_loader import sprite_loader

if TYPE_CHECKING:
    from ..systems.hit_result import HitResult


class ExplosiveMine:
    # Cache de sprites
    _normal_sprite: pygame.Surface | None = None
    _explosion_sprite: pygame.Surface | None = None
    is_explosive_mine: bool = True

    @classmethod
    def load_sprites(cls) -> None:
        """Carrega os sprites da mina explosiva."""
        if cls._normal_sprite is None:
            cls._normal_sprite = get_image(
                "game/assets/images/mines/minas_explosivas.png"
            )
        if cls._explosion_sprite is None:
            cls._explosion_sprite = get_image(
                "game/assets/images/mines/minas_explosivas_sprite_explosão.png"
            )

    def __init__(self, x: float | None = None, y: float | None = None):
        self.load_sprites()
        self.radius: int
        self.explosion_radius: int
        self.x: float
        self.y: float
        self.health: int
        self.max_health: int
        self.speed: int
        self.dead: bool
        # Armazenar cores como tuplas explícitas
        self.color: tuple[int, int, int]
        self.outline_color: tuple[int, int, int]

        self.shake_timer: float
        self.shake_intensity: int
        self.rotation_angle: float
        self.rotation_speed: float
        self.flash_timer: float
        self.flash_interval: float
        self.pre_explosion_timer: float
        self.is_exploding: bool

        # Pulsing animation
        self.animation_timer: float
        self.pulse_scale: float

        # Load sprites from cache
        self.normal_sprite: pygame.Surface
        self.explosion_sprite: pygame.Surface

        # Sprite dimensions
        self.sprite_width: int
        self.sprite_height: int

        # Scale factor to fit the visual radius
        self.scale: float

        self.radius = 30  # Visual radius of the mine
        self.explosion_radius = (
            self.radius * 8
        )  # Explosion radius is 4 times the visual radius
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
        self.rotation_angle = 0.0
        self.rotation_speed = random.uniform(25, 35) * random.choice([-1, 1])
        self.flash_timer = 0.0
        self.flash_interval = 0.1
        self.pre_explosion_timer = 0.0
        self.is_exploding = False

        # Pulsing animation
        self.animation_timer = 0.0
        self.pulse_scale = 1.0

        # Load sprites from cache
        normal_temp = self.__class__._normal_sprite
        explosion_temp = self.__class__._explosion_sprite

        assert normal_temp is not None, "Normal sprite for explosive mine not loaded"
        assert (
            explosion_temp is not None
        ), "Explosion sprite for explosive mine not loaded"

        self.normal_sprite = normal_temp
        self.explosion_sprite = explosion_temp

        # Sprite dimensions
        self.sprite_width = self.normal_sprite.get_width()
        self.sprite_height = self.normal_sprite.get_height()

        # Scale factor to fit the visual radius
        target_size = self.radius * 2  # 40 pixels diameter
        self.scale = target_size / self.sprite_width

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(
            int(self.x - self.radius),
            int(self.y - self.radius),
            self.radius * 2,
            self.radius * 2,
        )

    def take_damage(self, amount: int):
        if self.dead or self.is_exploding:
            return
        self.health -= amount
        if self.health <= 0:
            self.is_exploding = True
            self.pre_explosion_timer = 3.0
            self.shake_timer = 3.0
            self.shake_intensity = 10
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

            # IMPORTANTE: NÃO marcar dead aqui!
            # O check_mine_explosions vai verificar pre_explosion_timer <= 0
            # e criar a MineExplosion visual + marcar dead DEPOIS

            # Reset pulsing animation when exploding
            self.pulse_scale = 1.0

            if self.shake_timer > 0:
                self.shake_timer -= dt
            return

        self.y += self.speed * dt

        # Pulsing animation
        self.animation_timer += dt * 3  # velocidade da pulsação
        self.pulse_scale = 1.0 + 0.2 * abs(
            pygame.math.Vector2(1, 0).rotate(self.animation_timer * 57.3).x
        )

        # Rotation animation
        self.rotation_angle += dt * self.rotation_speed

        if self.shake_timer > 0:
            self.shake_timer -= dt

    def is_off_screen(self) -> bool:
        return self.y > Config.SCREEN_HEIGHT + self.radius

    def draw(self, surface: pygame.Surface):
        x, y = self.x, self.y
        if self.shake_timer > 0:
            x += random.randint(-self.shake_intensity, self.shake_intensity)
            y += random.randint(-self.shake_intensity, self.shake_intensity)

        # Choose sprite based on state
        if self.is_exploding:
            current_sprite = self.explosion_sprite
        else:
            current_sprite = self.normal_sprite

        # Apply pulsing effect to scale
        scale = self.pulse_scale if not self.is_exploding else 1.0

        # Get the scaled sprite
        if scale != 1.0:
            scaled_width = int(self.sprite_width * self.scale * scale)
            scaled_height = int(self.sprite_height * self.scale * scale)
            final_sprite = pygame.transform.scale(
                current_sprite, (scaled_width, scaled_height)
            )
        else:
            final_sprite = pygame.transform.scale(
                current_sprite,
                (
                    int(self.sprite_width * self.scale),
                    int(self.sprite_height * self.scale),
                ),
            )

        # Apply rotation if not exploding
        if not self.is_exploding:
            final_sprite = pygame.transform.rotate(final_sprite, self.rotation_angle)

        # Center the final sprite
        draw_x = int(x - final_sprite.get_width() / 2)
        draw_y = int(y - final_sprite.get_height() / 2)
        surface.blit(final_sprite, (draw_x, draw_y))

        if self.is_exploding:
            # Draw explosion radius indicator
            progress = 1 - (self.pre_explosion_timer / 3.0)
            start_alpha = 0.2 * 255
            end_alpha = 0.7 * 255
            alpha = start_alpha + (end_alpha - start_alpha) * progress

            indicator_surface = pygame.Surface(
                (self.explosion_radius * 2, self.explosion_radius * 2), pygame.SRCALPHA
            )
            pygame.draw.circle(
                indicator_surface,
                (255, 255, 255, int(alpha)),
                (self.explosion_radius, self.explosion_radius),
                self.explosion_radius,
            )
            surface.blit(
                indicator_surface,
                (self.x - self.explosion_radius, self.y - self.explosion_radius),
            )

    def get_points_value(self) -> int:
        return 250

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x, self.y, float(self.radius)

    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> "HitResult":
        from ..systems.hit_result import NO_HIT

        self.take_damage(damage)
        # Quem mata é o timer interno, não o tiro. Sem feedback aqui.
        return NO_HIT

    def on_ship_contact(self, contact_x: float, contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True  # explode imediatamente no contato
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ALIEN)

    def should_remove(self) -> bool:
        return self.dead


# REGISTRAR no sistema de pré-carregamento
sprite_loader.register("ExplosiveMine", ExplosiveMine.load_sprites)
