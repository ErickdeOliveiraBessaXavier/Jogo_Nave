import math
import random
from typing import TYPE_CHECKING, List, Tuple

import pygame

from ..core.config import config as Config
from .explosive_mine import ExplosiveMine

if TYPE_CHECKING:
    from ..systems.hit_result import HitResult


class MountainGeode(ExplosiveMine):
    """Inimigo exclusivo de Cordilheiras que substitui minas explosivas."""

    # Cache de shapes: (r, color_key) -> Surface  (0=normal, 1=flash)
    _shape_cache: dict[tuple[int, int], pygame.Surface] = {}

    def __init__(self, x: float | None = None, y: float | None = None):
        self.radius = 26
        self.explosion_radius = self.radius * 6

        if x is None:
            self.x = random.randint(self.radius, Config.SCREEN_WIDTH - self.radius)
        else:
            self.x = x
        self.y = -self.radius if y is None else y

        self.health = 50
        self.max_health = 50
        self.speed = 42
        self.dead = False

        self.shake_timer = 0.0
        self.shake_intensity = 0
        self.flash_timer = 0.0
        self.flash_interval = 0.11
        self.pre_explosion_timer = 0.0
        self.is_exploding = False

        self.animation_timer = random.uniform(0.0, 8.0)
        self.pulse_scale = 1.0
        self.sway_phase = random.uniform(0.0, math.tau)
        self.sway_freq = random.uniform(1.0, 1.4)
        self.sway_amplitude = random.uniform(10.0, 18.0)

        self.stop_y = random.uniform(
            Config.SCREEN_HEIGHT * 0.25, Config.SCREEN_HEIGHT * 0.60
        )
        self.stopped = False
        self.spawns_ice_zone: bool = True

        # Surface pré-alocada para o indicador de explosão
        self._indicator_surface = pygame.Surface(
            (self.explosion_radius * 2, self.explosion_radius * 2), pygame.SRCALPHA
        )

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
            self.pre_explosion_timer = 2.2
            self.shake_timer = 2.2
            self.shake_intensity = 9
        else:
            self.shake_timer = 0.18
            self.shake_intensity = (self.max_health - self.health) * 2

    def update(self, dt: float):
        if self.is_exploding:
            self.pre_explosion_timer -= dt
            self.flash_timer += dt
            if self.flash_timer >= self.flash_interval:
                self.flash_timer = 0.0

            self.pulse_scale = 1.0
            if self.shake_timer > 0:
                self.shake_timer -= dt
            return

        self.animation_timer += dt
        self.pulse_scale = 1.0 + 0.16 * abs(math.sin(self.animation_timer * 4.0))

        if self.shake_timer > 0:
            self.shake_timer -= dt

        if self.stopped:
            return

        self.y += self.speed * dt

        sway = math.sin(self.sway_phase + self.animation_timer * self.sway_freq)
        self.x += sway * self.sway_amplitude * dt
        self.x = max(self.radius, min(Config.SCREEN_WIDTH - self.radius, self.x))

        if self.y >= self.stop_y:
            self.y = self.stop_y
            self.stopped = True

    def is_off_screen(self) -> bool:
        return self.y > Config.SCREEN_HEIGHT + self.radius

    def draw(self, surface: pygame.Surface):
        cx, cy = self.x, self.y
        if self.shake_timer > 0:
            cx += random.randint(-self.shake_intensity, self.shake_intensity)
            cy += random.randint(-self.shake_intensity, self.shake_intensity)

        scale = self.pulse_scale if not self.is_exploding else 1.0
        r = max(8, int(self.radius * scale))
        color_key = 1 if (self.is_exploding and int(self.flash_timer * 20) % 2 == 0) else 0
        shape_cache_key = (r, color_key)

        draw_surface = self.__class__._shape_cache.get(shape_cache_key)
        if draw_surface is None:
            if len(self.__class__._shape_cache) > 64:
                self.__class__._shape_cache.clear()

            draw_surface = pygame.Surface((r * 3, r * 3), pygame.SRCALPHA)
            center = (r * 3 // 2, r * 3 // 2)

            if color_key == 1:
                geode_color = (255, 240, 180, 230)
                glow_color = (255, 210, 130, 140)
            else:
                geode_color = (132, 186, 216, 220)
                glow_color = (96, 142, 188, 90)

            points: List[Tuple[int, int]] = []
            for i in range(8):
                angle = (math.tau * i / 8.0) - math.pi / 2
                spike = 1.0 + (0.15 if i % 2 == 0 else -0.08)
                px = int(center[0] + math.cos(angle) * r * spike)
                py = int(center[1] + math.sin(angle) * r * spike)
                points.append((px, py))

            pygame.draw.polygon(draw_surface, glow_color, points)
            pygame.draw.polygon(draw_surface, geode_color, points, width=2)
            core_radius = max(4, int(r * 0.35))
            pygame.draw.circle(draw_surface, (220, 245, 255, 180), center, core_radius)
            self.__class__._shape_cache[shape_cache_key] = draw_surface

        center = (r * 3 // 2, r * 3 // 2)
        surface.blit(draw_surface, (int(cx - center[0]), int(cy - center[1])))

        if self.is_exploding:
            progress = 1 - (self.pre_explosion_timer / 2.2)
            progress = max(0.0, min(1.0, progress))
            start_alpha = int(0.22 * 255)
            end_alpha = int(0.75 * 255)
            alpha = int(start_alpha + (end_alpha - start_alpha) * progress)

            self._indicator_surface.fill((0, 0, 0, 0))
            pygame.draw.circle(
                self._indicator_surface,
                (180, 235, 255, alpha),
                (self.explosion_radius, self.explosion_radius),
                self.explosion_radius,
                width=2,
            )
            surface.blit(
                self._indicator_surface,
                (self.x - self.explosion_radius, self.y - self.explosion_radius),
            )

    def get_points_value(self) -> int:
        return 280

    def collision_circle(self) -> tuple[float, float, float]:
        return self.x, self.y, float(self.radius)

    def on_hit(self, damage: int, hit_x: float, hit_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.take_damage(damage)

        # Retorna HitResult com som de impacto mineral/boss
        # Se estiver prestes a explodir, pode retornar som de dano maior
        sound = (
            hit_sounds.BOSS_DAMAGE if self.health > 0 else hit_sounds.EXPLOSION_ASTEROID
        )
        return HitResult(
            killed=False,  # O timer de explosão controla a morte real
            sound=sound,
            explosion_size=7 if self.health > 0 else 0,
        )

    def on_ship_contact(self, contact_x: float, contact_y: float) -> "HitResult":
        from ..systems import hit_sounds
        from ..systems.hit_result import HitResult

        self.dead = True  # Explode imediatamente no contato
        return HitResult(killed=True, sound=hit_sounds.EXPLOSION_ASTEROID)

    def should_remove(self) -> bool:
        return self.dead
