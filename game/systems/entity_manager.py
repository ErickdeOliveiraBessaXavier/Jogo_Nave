import pygame
from ..entities.bullet import Bullet
from ..entities.meteor import Meteor
from ..entities.alien import Alien
from ..entities.boss import Boss
from ..entities.alien_bullet import AlienBullet
from ..entities.boss_laser import BossLaser
from ..entities.explosion import Explosion
from ..entities.powerup import PowerUp
from ..entities.floating_score import FloatingScore
from ..entities.guided_meteor import GuidedMeteor


class EntityManager:
    def __init__(self):
        self.bullets: list[Bullet] = []
        self.enemies: list[Meteor | Alien] = []
        self.alien_bullets: list[AlienBullet] = []
        self.boss_lasers: list[BossLaser] = []
        self.explosions: list[Explosion] = []
        self.powerups: list[PowerUp] = []
        self.floating_scores: list[FloatingScore] = []
        self.boss: Boss | None = None

    def update(self, dt: float, player_x: float, player_y: float | None = None):
        new_alien_bullets: list[AlienBullet] = []
        for b in self.bullets:
            b.update(dt)
        for ab in self.alien_bullets:
            ab.update(dt)
        for bl in self.boss_lasers:
            bl.update(dt)
        for e in self.explosions:
            e.update(dt)
        for p in self.powerups:
            p.update(dt)
        for fs in self.floating_scores:
            fs.update(dt)
        if self.boss:
            lasers_fired, spawned_meteors = self.boss.update(dt, player_x, player_y)
            if lasers_fired:
                self.boss_lasers.extend(lasers_fired)
            if spawned_meteors:
                self.enemies.extend(spawned_meteors)
        for enemy in self.enemies:
            # Se for um meteoro guiado, passar a posição do jogador
            if isinstance(enemy, GuidedMeteor):
                shot = enemy.update(dt, player_x, player_y)
            else:
                shot = enemy.update(dt)
            if isinstance(enemy, Alien) and shot:
                new_alien_bullets.extend(shot)
        self.alien_bullets.extend(new_alien_bullets)

    def draw(self, surface: pygame.Surface):
        from typing import Any

        entity_lists: list[list[Any]] = [
            self.enemies,
            self.bullets,
            self.alien_bullets,
            self.boss_lasers,
            self.explosions,
            self.powerups,
            self.floating_scores,
        ]
        if self.boss:
            entity_lists.append([self.boss])
        for entity_list in entity_lists:
            for entity in entity_list:
                entity.draw(surface)

    def cleanup(self):
        self.bullets = [b for b in self.bullets if not b.dead]
        self.alien_bullets = [ab for ab in self.alien_bullets if not ab.dead]
        self.boss_lasers = [bl for bl in self.boss_lasers if not bl.dead]
        self.enemies = [e for e in self.enemies if not e.dead]
        self.explosions = [e for e in self.explosions if not e.finished()]
        self.powerups = [p for p in self.powerups if not p.is_off_screen()]
        self.floating_scores = [
            fs for fs in self.floating_scores if not fs.is_dead()]

    def clear_all(self):
        self.bullets.clear()
        self.alien_bullets.clear()
        self.boss_lasers.clear()
        self.powerups.clear()
        self.floating_scores.clear()
        self.enemies.clear()
        self.explosions.clear()
        self.boss = None
