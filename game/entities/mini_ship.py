import math

import pygame

from ..core.colors import LIGHT_BLUE
from ..core.config import config as Config
from .alien import Alien
from .explosive_mine import ExplosiveMine
from .eye_enemy import EyeEnemy
from .meteor import Meteor
from .mini_ship_bullet import MiniShipBullet
from .ship import Ship
from .stone_sentry import StoneSentry


class MiniShip:
    def __init__(self, player_ship: Ship, side: str, is_side_scroll: bool = False):
        self.player = player_ship
        self.side = side  # 'left' or 'right'
        self.is_side_scroll = is_side_scroll
        self.w = 20
        self.h = 20
        self.x = self.player.x
        self.y = self.player.y
        self.shoot_cooldown = 0.75
        self.shoot_timer = self.shoot_cooldown

        self.target_offset_x = 0
        self.target_offset_y = 0
        self.set_orientation(is_side_scroll)

    def set_orientation(self, is_side_scroll: bool) -> None:
        """Atualiza offsets de formação conforme o modo da fase."""
        self.is_side_scroll = is_side_scroll

        if self.is_side_scroll:
            # Em side-scroll, escolta em coluna (acima/abaixo) um pouco atrás da nave.
            self.target_offset_x = -34
            self.target_offset_y = -34 if self.side == "left" else 34
        else:
            # Em top-down, escolta lateral clássica.
            self.target_offset_x = -40 if self.side == "left" else 40
            self.target_offset_y = 10

    def update(
        self,
        dt: float,
        enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy | StoneSentry],
        bullets: list[MiniShipBullet],
    ):
        # Movement
        target_x = self.player.x + self.player.w / 2 + self.target_offset_x - self.w / 2
        target_y = self.player.y + self.player.h / 2 + self.target_offset_y - self.h / 2

        # Simple lerp for smooth following
        self.x += (target_x - self.x) * 7 * dt
        self.y += (target_y - self.y) * 7 * dt

        # Shooting
        self.shoot_timer -= dt
        if self.shoot_timer <= 0:
            nearest_enemy = self._find_nearest_enemy(enemies)
            if nearest_enemy:
                self.shoot(nearest_enemy, bullets)
                self.shoot_timer = self.shoot_cooldown

    def _find_nearest_enemy(
        self, enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy | StoneSentry]
    ) -> Meteor | Alien | ExplosiveMine | EyeEnemy | StoneSentry | None:
        nearest_enemy = None
        min_dist_sq = float("inf")

        for enemy in enemies:
            if isinstance(enemy, ExplosiveMine):
                enemy_cx, enemy_cy = enemy.x, enemy.y
            else:
                enemy_cx, enemy_cy = enemy.x + enemy.w / 2, enemy.y + enemy.h / 2

            dist_sq = (self.x - enemy_cx) ** 2 + (self.y - enemy_cy) ** 2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                nearest_enemy = enemy

        return nearest_enemy

    def shoot(
        self,
        target: Meteor | Alien | ExplosiveMine | EyeEnemy | StoneSentry,
        bullets: list[MiniShipBullet],
    ):
        if isinstance(target, ExplosiveMine):
            target_cx, target_cy = target.x, target.y
        else:
            target_cx, target_cy = target.x + target.w / 2, target.y + target.h / 2

        if self.is_side_scroll:
            origin_x = self.x + self.w
            origin_y = self.y + self.h / 2
        else:
            origin_x = self.x + self.w / 2
            origin_y = self.y

        angle = math.atan2(target_cy - origin_y, target_cx - origin_x)
        bullet_speed = Config.BULLET_SPEED * 1.2
        vx = math.cos(angle) * bullet_speed
        vy = math.sin(angle) * bullet_speed

        bullets.append(
            MiniShipBullet(
                origin_x,
                origin_y,
                vx,
                vy,
                piercing=self.player.piercing_shot_timer > 0,
            )
        )

    def draw(self, surface: pygame.Surface):
        should_blink = (
            self.player.mini_ships_timer < 3.0 and self.player.mini_ships_timer > 0
        )

        if should_blink and int(pygame.time.get_ticks() / 150) % 2 == 0:
            return

        if self.is_side_scroll:
            # Nave apontando para a direita.
            points: list[tuple[float, float]] = [
                (self.x + self.w, self.y + self.h / 2),
                (self.x, self.y),
                (self.x, self.y + self.h),
            ]
        else:
            points = [
                (self.x + self.w / 2, self.y),
                (self.x, self.y + self.h),
                (self.x + self.w, self.y + self.h),
            ]
        pygame.draw.polygon(surface, LIGHT_BLUE, points)
