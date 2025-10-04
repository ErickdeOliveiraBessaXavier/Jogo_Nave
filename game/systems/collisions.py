import pygame
from ..entities.ship import Ship
from ..entities.meteor import Meteor
from ..entities.alien import Alien
from ..entities.bullet import Bullet
from ..entities.alien_bullet import AlienBullet
from ..entities.boss_laser import BossLaser
from ..entities.explosion import Explosion
from ..entities.powerup import PowerUp
from ..entities.boss import Boss
from ..entities.floating_score import FloatingScore


class Collisions:
    def bullets_vs_enemies(
        self,
        bullets: list[Bullet],
        enemies: list[Meteor | Alien],
        explosions: list[Explosion],
    ):
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        for b in bullets[:]:
            for enemy in enemies[:]:
                if b.rect.colliderect(enemy.rect):
                    if b in bullets:
                        bullets.remove(b)
                    if enemy in enemies:
                        enemies.remove(enemy)

                    cx, cy = (enemy.x + enemy.w / 2, enemy.y + enemy.h / 2)
                    explosions.append(Explosion(cx, cy, size=enemy.w // 2))

                    pts = enemy.get_points_value()
                    score_gain += pts
                    destroyed_count += 1
                    score_events.append((cx, cy, pts))

                    if isinstance(
                            enemy, Meteor) and hasattr(
                            enemy, "spawn_fragments"):
                        fragments = enemy.spawn_fragments()
                        if fragments:
                            enemies.extend(fragments)
                    break
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
                bullets.remove(b)
                boss.take_damage(b.damage)
                explosions.append(Explosion(b.x, b.y, size=15))
                
                # Não dar pontos por acertar o boss, apenas ao derrotá-lo
                if boss.dead:
                    # Dar pontuação fixa de 10.000 ao derrotar o boss
                    from ..core.config import Config
                    floating_scores.append(FloatingScore(
                        boss.x + boss.w / 2, 
                        boss.y + boss.h / 2, 
                        Config.BOSS_DEFEAT_SCORE
                    ))
                    score_gain += Config.BOSS_DEFEAT_SCORE
                    explosions.append(
                        Explosion(
                            boss.x + boss.w / 2,
                            boss.y + boss.h / 2,
                            size=100))
        return score_gain

    def ship_vs_boss(
            self,
            ship: Ship,
            boss: Boss,
            explosions: list[Explosion]) -> bool:
        if ship.invuln > 0:
            return False
        if ship.rect.colliderect(pygame.Rect(boss.x, boss.y, boss.w, boss.h)):
            explosions.append(
                Explosion(ship.x + ship.w / 2, ship.y + ship.h / 2, size=30)
            )
            return True
        return False

    def ship_vs_enemies(self,
                        ship: Ship,
                        enemies: list[Meteor | Alien],
                        explosions: list[Explosion]) -> bool:
        if ship.invuln > 0:
            return False
        for enemy in enemies[:]:
            if ship.rect.colliderect(enemy.rect):
                enemies.remove(enemy)
                explosions.append(
                    Explosion(
                        ship.x + ship.w / 2,
                        ship.y + ship.h / 2,
                        size=30))
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
