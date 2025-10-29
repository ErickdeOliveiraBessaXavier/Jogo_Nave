import pygame
from ..entities.ship import Ship
from ..entities.meteor import Meteor
from ..entities.alien import Alien
from ..entities.bullet import Bullet
from ..entities.alien_bullet import AlienBullet
from ..entities.boss_laser import BossLaser
from ..entities.eye_laser import EyeLaser
from ..entities.explosion import Explosion
from ..entities.mine_explosion import MineExplosion
from ..entities.powerup import PowerUp
from ..entities.boss import Boss
from ..entities.floating_score import FloatingScore
from ..core.sound import sound_manager
from ..entities.mini_ship_bullet import MiniShipBullet
from ..entities.eye_enemy import EyeEnemy


from ..entities.explosive_mine import ExplosiveMine


class Collisions:

    def check_mine_explosions(
        self,
        enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy],
        mine_explosions: list[MineExplosion],
        explosions: list[Explosion],
        ship: Ship,
    ) -> tuple[int, int, list[tuple[float, float, int]], bool]:
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []
        ship_hit = False

        for enemy in enemies[:]:
            if isinstance(enemy, ExplosiveMine) and enemy.dead:
                if enemy in enemies:
                    enemies.remove(enemy)
                cx, cy = (enemy.x, enemy.y)
                explosion_radius = enemy.explosion_radius
                mine_explosions.append(MineExplosion(cx, cy, size=explosion_radius))
                if self.handle_mine_explosion(cx, cy, explosion_radius, enemies, ship, explosions):
                    ship_hit = True
                sound_manager.play_explosion_boss() # Som de explosão grande
                pts = enemy.get_points_value()
                score_gain += pts
                destroyed_count += 1
                score_events.append((cx, cy, pts))
        return score_gain, destroyed_count, score_events, ship_hit

    def handle_mine_explosion(
        self,
        explosion_x: float,
        explosion_y: float,
        explosion_radius: int,
        enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy],
        ship: Ship,
        explosions: list[Explosion],
    ) -> bool:
        ship_hit = False
        for enemy in enemies[:]:
            if isinstance(enemy, ExplosiveMine):
                enemy_cx, enemy_cy = enemy.x, enemy.y
                enemy_r = enemy.radius
            else:
                enemy_cx, enemy_cy = enemy.x + enemy.w / 2, enemy.y + enemy.h / 2
                enemy_r = enemy.w / 2

            dist_sq = (enemy_cx - explosion_x) ** 2 + (enemy_cy - explosion_y) ** 2
            if dist_sq < (explosion_radius + enemy_r) ** 2:
                if isinstance(enemy, ExplosiveMine):
                    enemy.take_damage(enemy.health)  # Trigger chain reaction
                else:
                    if enemy in enemies:
                        enemies.remove(enemy)
                    explosions.append(Explosion(enemy_cx, enemy_cy, size=enemy.w // 2))

        # Check player collision
        if ship.invuln <= 0:
            ship_cx = ship.x + ship.w / 2
            ship_cy = ship.y + ship.h / 2
            ship_r = ship.w / 2

            dist_sq = (ship_cx - explosion_x) ** 2 + (ship_cy - explosion_y) ** 2
            if dist_sq < (explosion_radius + ship_r) ** 2:
                explosions.append(
                    Explosion(ship.x + ship.w / 2, ship.y + ship.h / 2, size=30)
                )
                ship_hit = True
        return ship_hit

    def mini_ship_bullets_vs_enemies(
        self,
        mini_ship_bullets: list[MiniShipBullet],
        enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy],
        explosions: list[Explosion],
    ):
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        for b in mini_ship_bullets[:]:
            for enemy in enemies[:]:
                if b.rect.colliderect(enemy.rect):
                    if b in mini_ship_bullets:
                        mini_ship_bullets.remove(b)

                    if isinstance(enemy, ExplosiveMine):
                        enemy.take_damage(1)
                    else:
                        if isinstance(enemy, EyeEnemy):
                            enemy.destroy()
                        if enemy in enemies:
                            enemies.remove(enemy)

                        cx, cy = (enemy.x + enemy.w / 2, enemy.y + enemy.h / 2)
                        explosions.append(Explosion(cx, cy, size=enemy.w // 2))
                        
                        if isinstance(enemy, Meteor):
                            sound_manager.play_explosion_asteroid()
                        else:
                            sound_manager.play_explosion_alien()

                        pts = enemy.get_points_value()
                        score_gain += pts
                        destroyed_count += 1
                        score_events.append((cx, cy, pts))

                        if isinstance(enemy, Meteor) and hasattr(enemy, "spawn_fragments"):
                            fragments = enemy.spawn_fragments()
                            if fragments:
                                enemies.extend(fragments)
                    break # Bullet is gone, check next bullet
        return score_gain, destroyed_count, score_events

    def bullets_vs_enemies(
        self,
        bullets: list[Bullet],
        enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy],
        explosions: list[Explosion],
        mine_explosions: list[MineExplosion],
        ship: Ship,
    ):
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        for b in bullets[:]:
            for enemy in enemies[:]:
                if b.rect.colliderect(enemy.rect):
                    if isinstance(enemy, ExplosiveMine):
                        enemy.take_damage(1)
                    else:
                        if isinstance(enemy, EyeEnemy):
                            enemy.destroy()
                        if enemy in enemies:
                            enemies.remove(enemy)

                        cx, cy = (enemy.x + enemy.w / 2, enemy.y + enemy.h / 2)
                        explosions.append(Explosion(cx, cy, size=enemy.w // 2))
                        
                        # Tocar som de explosão baseado no tipo de inimigo
                        if isinstance(enemy, Meteor):
                            sound_manager.play_explosion_asteroid()
                        else:  # Se não é Meteor, é Alien
                            sound_manager.play_explosion_alien()

                        pts = enemy.get_points_value()
                        score_gain += pts
                        destroyed_count += 1
                        score_events.append((cx, cy, pts))

                        if isinstance(enemy, Meteor) and hasattr(enemy, "spawn_fragments"):
                            fragments = enemy.spawn_fragments()
                            if fragments:
                                enemies.extend(fragments)
                    if not b.piercing:
                        break # Bullet is gone, check next bullet
        return score_gain, destroyed_count, score_events

    def bullets_vs_boss(
        self,
        bullets: list[Bullet],
        boss: Boss,
        explosions: list[Explosion],
        floating_scores: list[FloatingScore],
    ) -> int:
        score_gain = 0
        for b in bullets[:]:
            if b.rect.colliderect(pygame.Rect(boss.x, boss.y, boss.w, boss.h)):
                if not b.piercing:
                    bullets.remove(b)
                boss.take_damage(b.damage)
                # Tocar som de dano no boss
                sound_manager.play_boss_damage()
                explosions.append(Explosion(b.x, b.y, size=15))

                # Não dar pontos por acertar o boss, apenas ao derrotá-lo
                if boss.dead:
                    # Dar pontuação fixa de 10.000 ao derrotar o boss
                    from ..core.config import Config

                    floating_scores.append(
                        FloatingScore(
                            boss.x + boss.w / 2,
                            boss.y + boss.h / 2,
                            Config.BOSS_DEFEAT_SCORE,
                        )
                    )
                    score_gain += Config.BOSS_DEFEAT_SCORE
                    explosions.append(
                        Explosion(boss.x + boss.w / 2, boss.y + boss.h / 2, size=100)
                    )
        return score_gain

    def ship_vs_boss(self, ship: Ship, boss: Boss, explosions: list[Explosion]) -> bool:
        if ship.invuln > 0:
            return False
        if ship.rect.colliderect(pygame.Rect(boss.x, boss.y, boss.w, boss.h)):
            explosions.append(
                Explosion(ship.x + ship.w / 2, ship.y + ship.h / 2, size=30)
            )
            return True
        return False

    def ship_vs_enemies(
        self, ship: Ship, enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy], explosions: list[Explosion]
    ) -> bool:
        if ship.invuln > 0:
            return False
        for enemy in enemies[:]:
            if ship.rect.colliderect(enemy.rect):
                if isinstance(enemy, ExplosiveMine):
                    enemy.dead = True  # Explode immediately
                else:
                    if isinstance(enemy, EyeEnemy):
                        enemy.destroy()
                    if enemy in enemies:
                        enemies.remove(enemy)
                explosions.append(
                    Explosion(ship.x + ship.w / 2, ship.y + ship.h / 2, size=30)
                )
                return True
        return False

    def alien_bullets_vs_ship(
        self, ship: Ship, alien_bullets: list[AlienBullet]
    ) -> bool:
        if ship.invuln > 0:
            return False
        for bullet in alien_bullets[:]:
            if ship.rect.colliderect(bullet.rect):
                alien_bullets.remove(bullet)
                return True
        return False

    def eye_laser_vs_ship(self, ship: Ship, eye_lasers: list[EyeLaser]) -> bool:
        if ship.invuln > 0:
            return False
        for laser in eye_lasers:
            if ship.rect.clipline(laser.get_collision_line()):
                return True
        return False

    def laser_vs_ship(self, ship: Ship, lasers: list[BossLaser]) -> bool:
        if ship.invuln > 0:
            return False
        for laser in lasers:
            if laser.w > 0 and ship.rect.clipline(laser.get_collision_line()):
                return True
        return False

    def ship_vs_powerups(
        self,
        ship: Ship,
        powerups: list[PowerUp],
    ) -> list[str]:
        collected_kinds: list[str] = []
        for p in powerups[:]:
            if ship.rect.colliderect(p.rect):
                powerups.remove(p)
                kind = getattr(p, "kind", "shield")
                collected_kinds.append(kind)
        return collected_kinds

