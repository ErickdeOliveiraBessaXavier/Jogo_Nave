import pygame
import math
from ..core.config import Config
from ..core.colors import LIGHT_BLUE
from .ship import Ship
from .mini_ship_bullet import MiniShipBullet
from .meteor import Meteor
from .alien import Alien
from .explosive_mine import ExplosiveMine

class MiniShip:
    def __init__(self, player_ship: Ship, side: str):
        self.player = player_ship
        self.side = side  # 'left' or 'right'
        self.w = 20
        self.h = 20
        self.x = self.player.x
        self.y = self.player.y
        self.shoot_cooldown = 0.75
        self.shoot_timer = self.shoot_cooldown
        
        if self.side == 'left':
            self.target_offset_x = -40
        else: # right
            self.target_offset_x = 40
        self.target_offset_y = 10

    def update(self, dt: float, enemies: list[Meteor | Alien | ExplosiveMine], bullets: list[MiniShipBullet]):
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

    def _find_nearest_enemy(self, enemies: list[Meteor | Alien | ExplosiveMine]) -> Meteor | Alien | ExplosiveMine | None:
        nearest_enemy = None
        min_dist_sq = float('inf')

        for enemy in enemies:
            if isinstance(enemy, ExplosiveMine):
                enemy_cx, enemy_cy = enemy.x, enemy.y
            else:
                enemy_cx, enemy_cy = enemy.x + enemy.w / 2, enemy.y + enemy.h / 2
            
            dist_sq = (self.x - enemy_cx)**2 + (self.y - enemy_cy)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                nearest_enemy = enemy
        
        return nearest_enemy

    def shoot(self, target: Meteor | Alien | ExplosiveMine, bullets: list[MiniShipBullet]):
        if isinstance(target, ExplosiveMine):
            target_cx, target_cy = target.x, target.y
        else:
            target_cx, target_cy = target.x + target.w / 2, target.y + target.h / 2
        
        angle = math.atan2(target_cy - self.y, target_cx - self.x)
        bullet_speed = Config.BULLET_SPEED * 1.2
        vx = math.cos(angle) * bullet_speed
        vy = math.sin(angle) * bullet_speed
        
        bullets.append(MiniShipBullet(self.x + self.w/2, self.y, vx, vy))

    def draw(self, surface: pygame.Surface):
        should_blink = self.player.mini_ships_timer < 3.0 and self.player.mini_ships_timer > 0

        if should_blink and int(pygame.time.get_ticks() / 150) % 2 == 0:
            return
            
        points: list[tuple[float, float]] = [
            (self.x + self.w / 2, self.y),
            (self.x, self.y + self.h),
            (self.x + self.w, self.y + self.h),
        ]
        pygame.draw.polygon(surface, LIGHT_BLUE, points)
