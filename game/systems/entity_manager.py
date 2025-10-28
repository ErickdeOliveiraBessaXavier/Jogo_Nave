import pygame
from ..entities.bullet import Bullet
from ..entities.meteor import Meteor
from ..entities.alien import Alien
from ..entities.boss import Boss
from ..entities.alien_bullet import AlienBullet
from ..entities.boss_laser import BossLaser
from ..entities.explosion import Explosion
from ..entities.mine_explosion import MineExplosion
from ..entities.powerup import PowerUp
from ..entities.floating_score import FloatingScore
from ..entities.guided_meteor import GuidedMeteor
from ..entities.explosive_mine import ExplosiveMine
from ..entities.mini_ship import MiniShip
from ..entities.mini_ship_bullet import MiniShipBullet
from ..entities.eye_enemy import EyeEnemy
from ..entities.eye_laser import EyeLaser


class EntityManager:
    def __init__(self):
        self.bullets: list[Bullet] = []
        self.enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy] = []
        self.alien_bullets: list[AlienBullet] = []
        self.boss_lasers: list[BossLaser] = []
        self.eye_lasers: list[EyeLaser] = []
        self.explosions: list[Explosion] = []
        self.mine_explosions: list[MineExplosion] = []
        self.powerups: list[PowerUp] = []
        self.floating_scores: list[FloatingScore] = []
        self.boss: Boss | None = None
        self.mini_ships: list[MiniShip] = []
        self.mini_ship_bullets: list[MiniShipBullet] = []

    def update(self, dt: float, player_x: float, player_y: float):
        new_alien_bullets: list[AlienBullet] = []
        new_eye_lasers: list[EyeLaser] = []
        for b in self.bullets:
            b.update(dt)
        for ab in self.alien_bullets:
            ab.update(dt)
        for vb in self.mini_ship_bullets:
            vb.update(dt)
        for bl in self.boss_lasers:
            bl.update(dt)
        for el in self.eye_lasers:
            el.update(dt)
        for e in self.explosions:
            e.update(dt)
        for me in self.mine_explosions:
            me.update(dt)
        for p in self.powerups:
            p.update(dt)
        for fs in self.floating_scores:
            fs.update(dt)
        for ms in self.mini_ships:
            ms.update(dt, self.enemies, self.mini_ship_bullets)
        if self.boss:
            lasers_fired, spawned_meteors = self.boss.update(dt, player_x, player_y)
            if lasers_fired:
                self.boss_lasers.extend(lasers_fired)
            if spawned_meteors:
                self.enemies.extend(spawned_meteors)
        for enemy in self.enemies:
            if isinstance(enemy, Alien):
                shot = enemy.update(dt)
                if shot:
                    new_alien_bullets.extend(shot)
            elif isinstance(enemy, EyeEnemy):
                shot = enemy.update(dt, player_x, player_y)
                if shot:
                    new_eye_lasers.extend(shot)
            elif isinstance(enemy, GuidedMeteor):
                enemy.update(dt, player_x, player_y)
            else:
                enemy.update(dt)

        self.alien_bullets.extend(new_alien_bullets)
        self.eye_lasers.extend(new_eye_lasers)
    
    def draw(self, surface: pygame.Surface, player_x: float, player_y: float):
        """Desenha todas as entidades. EyeEnemy precisa da posição do jogador."""
        from typing import Any

        # Entidades que não precisam da posição do jogador
        entity_lists: list[list[Any]] = [
            self.bullets,
            self.alien_bullets,
            self.boss_lasers,
            self.eye_lasers,
            self.explosions,
            self.mine_explosions,
            self.powerups,
            self.floating_scores,
            self.mini_ship_bullets,
            self.mini_ships,
        ]
        
        if self.boss:
            entity_lists.append([self.boss])
        
        for entity_list in entity_lists:
            for entity in entity_list:
                entity.draw(surface)
        
        # Desenhar inimigos (EyeEnemy precisa da posição do jogador)
        for enemy in self.enemies:
            if isinstance(enemy, EyeEnemy):
                enemy.draw(surface, player_x, player_y)
            else:
                enemy.draw(surface)

    def cleanup(self):
        self.bullets = [b for b in self.bullets if not b.dead]
        self.alien_bullets = [ab for ab in self.alien_bullets if not ab.dead]
        self.boss_lasers = [bl for bl in self.boss_lasers if not bl.dead]
        self.eye_lasers = [el for el in self.eye_lasers if not el.dead]
        self.mini_ship_bullets = [vb for vb in self.mini_ship_bullets if not vb.dead]
        self.enemies = [
            e
            for e in self.enemies
            if not e.dead and not (isinstance(e, ExplosiveMine) and e.is_off_screen())
        ]
        self.explosions = [e for e in self.explosions if not e.finished()]
        self.mine_explosions = [me for me in self.mine_explosions if not me.finished()]
        self.powerups = [p for p in self.powerups if not p.is_off_screen()]
        self.floating_scores = [fs for fs in self.floating_scores if not fs.is_dead()]

    def clear_all(self):
        self.bullets.clear()
        self.alien_bullets.clear()
        self.boss_lasers.clear()
        self.eye_lasers.clear()
        self.powerups.clear()
        self.floating_scores.clear()
        self.enemies.clear()
        self.explosions.clear()
        self.mine_explosions.clear()
        self.boss = None
        self.mini_ships.clear()
        self.mini_ship_bullets.clear()

    def clear_for_level_transition(self):
        """Limpa entidades para transição de fase, mas preserva balas do jogador."""
        # Preservar balas do jogador durante transições
        # self.bullets.clear()  # NÃO limpar balas do jogador
        self.alien_bullets.clear()
        self.boss_lasers.clear()
        self.eye_lasers.clear()
        self.powerups.clear()
        self.floating_scores.clear()
        self.enemies.clear()
        self.explosions.clear()
        self.mine_explosions.clear()
        self.boss = None
        self.mini_ships.clear()
        self.mini_ship_bullets.clear()