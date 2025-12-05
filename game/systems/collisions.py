import pygame
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .entity_manager import EntityManager
from ..entities.ship import Ship
from ..entities.meteor import Meteor
from ..entities.alien import Alien
from ..entities.bullet import Bullet
from ..entities.alien_bullet import AlienBullet
from ..entities.boss_laser import BossLaser
from ..entities.player_laser import PlayerLaser
from ..entities.eye_laser import EyeLaser
from ..entities.spike_boss_laser import SpikeBossLaser
from ..entities.mine_explosion import MineExplosion
from ..entities.powerup import PowerUp
from ..entities.boss import Boss
from ..entities.boss_square import BossSquare
from ..entities.floating_score import FloatingScore
from ..core.sound import sound_manager
from ..entities.mini_ship_bullet import MiniShipBullet
from ..entities.eye_enemy import EyeEnemy
from ..entities.spike import Spike
from ..entities.spike_boss import SpikeBoss
from ..entities.star import Star
from ..core.config import Config
from ..core.spatial_grid import SpatialGrid
from ..entities.explosive_effect import ExplosiveEffect
from ..entities.air_strike_bomb import AirStrikeBomb


from ..entities.explosive_mine import ExplosiveMine


class Collisions:

    def check_mine_explosions(
        self,
        enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy],
        mine_explosions: list[MineExplosion],
        ship: Ship,
        entity_manager: "EntityManager",  # <-- ADICIONAR
    ) -> tuple[int, int, list[tuple[float, float, int]], bool]:
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []
        ship_hit = False

        for enemy in enemies[:]:
            if isinstance(enemy, ExplosiveMine) and enemy.dead:
                cx, cy = (enemy.x, enemy.y)
                explosion_radius = enemy.explosion_radius
                mine_explosions.append(MineExplosion(cx, cy, size=explosion_radius))
                if self.handle_mine_explosion(
                    cx, cy, explosion_radius, enemies, ship, entity_manager
                ):
                    ship_hit = True
                sound_manager.play_explosion_boss()  # Som de explosão grande
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
        entity_manager: "EntityManager",  # <-- ADICIONAR
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
                    enemy.dead = True
                    # Nova forma
                    entity_manager.spawn_explosion(
                        enemy_cx, enemy_cy, size=enemy.w // 2
                    )

        # Check player collision
        if ship.invuln <= 0:
            ship_cx = ship.x + ship.w / 2
            ship_cy = ship.y + ship.h / 2
            ship_r = ship.w / 2

            dist_sq = (ship_cx - explosion_x) ** 2 + (ship_cy - explosion_y) ** 2
            if dist_sq < (explosion_radius + ship_r) ** 2:
                # Nova forma
                entity_manager.spawn_explosion(
                    ship.x + ship.w / 2, ship.y + ship.h / 2, size=30
                )
                ship_hit = True
        return ship_hit

    def explosive_effects_vs_enemies(
        self,
        explosive_effects: list[ExplosiveEffect],
        enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy],
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Verifica colisão contínua entre efeitos explosivos ativos e inimigos.
        
        Isso permite que fragmentos de meteoros e novos inimigos que entrem
        na área de explosão sofram dano enquanto o efeito estiver ativo.
        """
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []
        
        for effect in explosive_effects:
            if not effect.damage_active:
                continue
            
            damage_radius = effect.current_damage_radius
            if damage_radius <= 0:
                continue
            
            for enemy in enemies[:]:
                if enemy.dead:
                    continue
                
                # Verificar se já foi atingido por este efeito
                enemy_id = id(enemy)
                if enemy_id in effect.hit_enemies:
                    continue
                
                # Calcular distância
                if isinstance(enemy, ExplosiveMine):
                    enemy_cx, enemy_cy = enemy.x, enemy.y
                    enemy_r = enemy.radius
                else:
                    enemy_cx = enemy.x + enemy.w / 2
                    enemy_cy = enemy.y + enemy.h / 2
                    enemy_r = enemy.w / 2
                
                dist_sq = (enemy_cx - effect.x) ** 2 + (enemy_cy - effect.y) ** 2
                
                # Verificar colisão
                if dist_sq < (damage_radius + enemy_r) ** 2:
                    # Marcar como atingido
                    effect.hit_enemies.add(enemy_id)
                    
                    if isinstance(enemy, ExplosiveMine):
                        enemy.take_damage(2)
                    else:
                        if isinstance(enemy, EyeEnemy):
                            enemy.destroy()
                        enemy.dead = True
                        
                        # Spawn explosion visual
                        entity_manager.spawn_explosion(enemy_cx, enemy_cy, size=int(enemy.w // 2))
                        
                        # Score
                        pts = enemy.get_points_value()
                        score_gain += pts
                        destroyed_count += 1
                        score_events.append((enemy_cx, enemy_cy, pts))
                        
                        # Fragmentar meteoros
                        if isinstance(enemy, Meteor) and hasattr(enemy, "spawn_fragments"):
                            fragments = enemy.spawn_fragments()
                            if fragments:
                                enemies.extend(fragments)
        
        return score_gain, destroyed_count, score_events

    def air_strike_bombs_vs_enemies(
        self,
        air_strike_bombs: list[AirStrikeBomb],
        enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy],
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Verifica colisão entre explosões de bombas e inimigos.
        
        Bombas que explodiram causam dano em área a todos os inimigos
        dentro do raio de explosão.
        """
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []
        
        for bomb in air_strike_bombs:
            if not bomb.exploding or not bomb.damage_active:
                continue
            
            damage_radius = bomb.explosion_radius
            if damage_radius <= 0:
                continue
            
            for enemy in enemies[:]:
                if enemy.dead:
                    continue
                
                # Verificar se já foi atingido por esta bomba
                enemy_id = id(enemy)
                if enemy_id in bomb.hit_enemies:
                    continue
                
                # Calcular distância
                if isinstance(enemy, ExplosiveMine):
                    enemy_cx, enemy_cy = enemy.x, enemy.y
                    enemy_r = enemy.radius
                else:
                    enemy_cx = enemy.x + enemy.w / 2
                    enemy_cy = enemy.y + enemy.h / 2
                    enemy_r = enemy.w / 2
                
                dist_sq = (enemy_cx - bomb.x) ** 2 + (enemy_cy - bomb.target_y) ** 2
                
                # Verificar colisão
                if dist_sq < (damage_radius + enemy_r) ** 2:
                    # Marcar como atingido
                    bomb.hit_enemies.add(enemy_id)
                    
                    if isinstance(enemy, ExplosiveMine):
                        enemy.take_damage(5)  # Dano alto para minas
                    else:
                        if isinstance(enemy, EyeEnemy):
                            enemy.destroy()
                        enemy.dead = True
                        
                        # Spawn explosion visual
                        entity_manager.spawn_explosion(enemy_cx, enemy_cy, size=int(enemy.w // 2))
                        
                        # Score
                        pts = enemy.get_points_value()
                        score_gain += pts
                        destroyed_count += 1
                        score_events.append((enemy_cx, enemy_cy, pts))
                        
                        # Fragmentar meteoros
                        if isinstance(enemy, Meteor) and hasattr(enemy, "spawn_fragments"):
                            fragments = enemy.spawn_fragments()
                            if fragments:
                                enemies.extend(fragments)
        
        return score_gain, destroyed_count, score_events

    def mini_ship_bullets_vs_enemies(
        self,
        mini_ship_bullets: list[MiniShipBullet],
        enemy_grid: SpatialGrid[Meteor | Alien | ExplosiveMine | EyeEnemy],
        enemies: list[
            Meteor | Alien | ExplosiveMine | EyeEnemy
        ],  # Para adicionar fragments
        entity_manager: "EntityManager",  # <-- ADICIONAR
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        # Usar grid existente

        for b in mini_ship_bullets[:]:
            # Query potential collisions using spatial grid (expand by 10 pixels for safety)
            query_x = b.rect.x - 10
            query_y = b.rect.y - 10
            query_w = b.rect.width + 20
            query_h = b.rect.height + 20
            potential_enemies = enemy_grid.query(query_x, query_y, query_w, query_h)
            for enemy in potential_enemies:
                if b.rect.colliderect(enemy.rect):
                    b.dead = True

                    if isinstance(enemy, ExplosiveMine):
                        enemy.take_damage(1)
                    else:
                        if isinstance(enemy, EyeEnemy):
                            enemy.destroy()
                        enemy.dead = True

                        cx, cy = (enemy.rect.centerx, enemy.rect.centery)
                        # Nova forma
                        entity_manager.spawn_explosion(
                            cx, cy, size=enemy.rect.width // 2
                        )

                        if isinstance(enemy, Meteor):
                            sound_manager.play_explosion_asteroid()
                        else:
                            sound_manager.play_explosion_alien()

                        pts = enemy.get_points_value()
                        score_gain += pts
                        destroyed_count += 1
                        score_events.append((cx, cy, pts))

                        if isinstance(enemy, Meteor) and hasattr(
                            enemy, "spawn_fragments"
                        ):
                            fragments = enemy.spawn_fragments()
                            if fragments:
                                enemies.extend(fragments)
                    break  # Bullet is gone, check next bullet
        return score_gain, destroyed_count, score_events

    def bullets_vs_enemies(
        self,
        bullets: list[Bullet],
        mine_explosions: list[MineExplosion],
        ship: Ship,
        enemy_grid: SpatialGrid[Meteor | Alien | ExplosiveMine | EyeEnemy],
        enemies: list[
            Meteor | Alien | ExplosiveMine | EyeEnemy
        ],  # Para adicionar fragments
        entity_manager: "EntityManager",  # <-- NOVO
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        # Usar grid existente em vez de criar nova

        for b in bullets[:]:
            # Query potential collisions using spatial grid (expand by 10 pixels for safety)
            query_x = b.rect.x - 10
            query_y = b.rect.y - 10
            query_w = b.rect.width + 20
            query_h = b.rect.height + 20
            potential_enemies = enemy_grid.query(query_x, query_y, query_w, query_h)
            for enemy in potential_enemies:
                if b.rect.colliderect(enemy.rect):
                    if isinstance(enemy, ExplosiveMine):
                        enemy.take_damage(1)
                    else:
                        if isinstance(enemy, EyeEnemy):
                            enemy.destroy()
                        enemy.dead = True

                        cx, cy = (enemy.x + enemy.w / 2, enemy.y + enemy.h / 2)
                        # Nova forma: usar pool
                        entity_manager.spawn_explosion(cx, cy, size=enemy.w // 2)

                        # Tocar som de explosão baseado no tipo de inimigo
                        if isinstance(enemy, Meteor):
                            sound_manager.play_explosion_asteroid()
                        else:  # Se não é Meteor, é Alien
                            sound_manager.play_explosion_alien()

                        pts = enemy.get_points_value()
                        score_gain += pts
                        destroyed_count += 1
                        score_events.append((cx, cy, pts))

                        if isinstance(enemy, Meteor) and hasattr(
                            enemy, "spawn_fragments"
                        ):
                            fragments = enemy.spawn_fragments()
                            if fragments:
                                enemies.extend(fragments)
                    
                    # Se é um tiro explosivo, causar dano em área
                    if b.explosive:
                        explosion_cx = b.x + b.w / 2
                        explosion_cy = b.y + b.h / 2
                        explosion_radius = 60  # Raio da explosão
                        
                        # Criar efeito visual do círculo de área (branco semi-transparente)
                        entity_manager.spawn_explosive_effect(explosion_cx, explosion_cy, radius=explosion_radius)
                        
                        # Criar explosão visual de partículas
                        entity_manager.spawn_explosion(explosion_cx, explosion_cy, size=explosion_radius // 2)
                        
                        # Tocar som de explosão
                        sound_manager.play_explosion_asteroid()
                        
                        # Dano em área para inimigos próximos
                        area_query = enemy_grid.query(
                            explosion_cx - explosion_radius,
                            explosion_cy - explosion_radius,
                            explosion_radius * 2,
                            explosion_radius * 2
                        )
                        for nearby_enemy in area_query:
                            if nearby_enemy.dead:
                                continue
                            # Verificar distância real
                            enemy_cx = nearby_enemy.x + getattr(nearby_enemy, 'w', 0) / 2
                            enemy_cy = nearby_enemy.y + getattr(nearby_enemy, 'h', 0) / 2
                            dist_sq = (enemy_cx - explosion_cx) ** 2 + (enemy_cy - explosion_cy) ** 2
                            if dist_sq < explosion_radius ** 2:
                                if isinstance(nearby_enemy, ExplosiveMine):
                                    nearby_enemy.take_damage(2)  # Dano extra
                                elif not nearby_enemy.dead:
                                    if isinstance(nearby_enemy, EyeEnemy):
                                        nearby_enemy.destroy()
                                    nearby_enemy.dead = True
                                    ncx, ncy = (nearby_enemy.x + nearby_enemy.w / 2, nearby_enemy.y + nearby_enemy.h / 2)
                                    entity_manager.spawn_explosion(ncx, ncy, size=nearby_enemy.w // 2)
                                    pts = nearby_enemy.get_points_value()
                                    score_gain += pts
                                    destroyed_count += 1
                                    score_events.append((ncx, ncy, pts))
                                    
                                    if isinstance(nearby_enemy, Meteor) and hasattr(nearby_enemy, "spawn_fragments"):
                                        fragments = nearby_enemy.spawn_fragments()
                                        if fragments:
                                            enemies.extend(fragments)
                    
                    if not b.piercing:
                        b.dead = True
                        break  # Bullet is gone, check next bullet
        return score_gain, destroyed_count, score_events

    def bullets_vs_boss(
        self,
        bullets: list[Bullet],
        boss: Boss,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        score_gain = 0
        for b in bullets[:]:
            if b.rect.colliderect(pygame.Rect(boss.x, boss.y, boss.w, boss.h)):
                if not b.piercing:
                    b.dead = True
                boss.take_damage(b.damage)
                # Tocar som de dano no boss
                sound_manager.play_boss_damage()
                entity_manager.spawn_explosion(b.x, b.y, size=15)

                # Não dar pontos por acertar o boss, apenas ao derrotá-lo
                if boss.dead:
                    # Dar pontuação fixa de 10.000 ao derrotar o boss
                    from ..core.config import config as Config

                    floating_scores.append(
                        FloatingScore(
                            boss.x + boss.w / 2,
                            boss.y + boss.h / 2,
                            Config.BOSS_DEFEAT_SCORE,
                        )
                    )
                    score_gain += Config.BOSS_DEFEAT_SCORE
                    entity_manager.spawn_explosion(
                        boss.x + boss.w / 2, boss.y + boss.h / 2, size=100
                    )
        return score_gain

    def ship_vs_boss(
        self, ship: Ship, boss: Boss, entity_manager: "EntityManager"
    ) -> bool:
        if ship.invuln > 0:
            return False
        if ship.rect.colliderect(pygame.Rect(boss.x, boss.y, boss.w, boss.h)):
            entity_manager.spawn_explosion(
                ship.x + ship.w / 2, ship.y + ship.h / 2, size=30
            )
            return True
        return False

    def ship_vs_enemies(
        self,
        ship: Ship,
        enemy_grid: SpatialGrid[Meteor | Alien | ExplosiveMine | EyeEnemy],
        entity_manager: "EntityManager",
    ) -> bool:
        if ship.invuln > 0:
            return False

        # Usar grid existente

        # Query potential collisions with ship's rect (expand by 10 pixels)
        query_x = ship.rect.x - 10
        query_y = ship.rect.y - 10
        query_w = ship.rect.width + 20
        query_h = ship.rect.height + 20
        potential_enemies = enemy_grid.query(query_x, query_y, query_w, query_h)
        for enemy in potential_enemies:
            if enemy and ship.rect.colliderect(enemy.rect):
                if isinstance(enemy, ExplosiveMine):
                    enemy.dead = True  # Explode immediately
                else:
                    if isinstance(enemy, EyeEnemy):
                        enemy.destroy()
                    enemy.dead = True
                entity_manager.spawn_explosion(
                    ship.x + ship.w / 2, ship.y + ship.h / 2, size=30
                )
                # Tocar som de colisão apropriado baseado no tipo de inimigo
                if isinstance(enemy, Meteor):
                    sound_manager.play_explosion_asteroid()
                elif isinstance(enemy, Alien):
                    sound_manager.play_explosion_alien()
                else:
                    # ExplosiveMine, EyeEnemy e outros
                    sound_manager.play_explosion_alien()
                return True
        return False

    def alien_bullets_vs_ship(
        self, ship: Ship, alien_bullets: list[AlienBullet]
    ) -> bool:
        if ship.invuln > 0:
            return False
        for bullet in alien_bullets[:]:
            if ship.rect.colliderect(bullet.rect):
                bullet.dead = True
                return True
        return False

    def eye_laser_vs_ship(self, ship: Ship, eye_lasers: list[EyeLaser]) -> bool:
        if ship.invuln > 0:
            return False
        for laser in eye_lasers:
            if laser.w > 0 and ship.rect.clipline(laser.get_collision_line()):
                return True
        return False

    def laser_vs_ship(self, ship: Ship, lasers: list[BossLaser]) -> bool:
        if ship.invuln > 0:
            return False
        for laser in lasers:
            if laser.w > 0 and ship.rect.clipline(laser.get_collision_line()):
                return True
        return False

    def spike_boss_laser_vs_ship(
        self, ship: Ship, lasers: list[SpikeBossLaser]
    ) -> bool:
        """Colisão entre laser gigante do SpikeBoss e nave."""
        if ship.invuln > 0:
            return False
        for laser in lasers:
            if laser.w > 0 and ship.rect.colliderect(laser.get_collision_rect()):
                return True
        return False

    def mini_ship_bullets_vs_boss(
        self,
        mini_ship_bullets: list[MiniShipBullet],
        boss: Boss,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão de balas das mini ships com Boss normal."""
        score_gain = 0
        for b in mini_ship_bullets[:]:
            if b.rect.colliderect(pygame.Rect(boss.x, boss.y, boss.w, boss.h)):
                b.dead = True
                boss.take_damage(b.damage)
                sound_manager.play_boss_damage()
                entity_manager.spawn_explosion(b.x, b.y, size=15)

                if boss.dead:
                    from ..core.config import config as Config

                    floating_scores.append(
                        FloatingScore(
                            boss.x + boss.w / 2,
                            boss.y + boss.h / 2,
                            Config.BOSS_DEFEAT_SCORE,
                        )
                    )
                    score_gain += Config.BOSS_DEFEAT_SCORE
                    entity_manager.spawn_explosion(
                        boss.x + boss.w / 2, boss.y + boss.h / 2, size=100
                    )
        return score_gain

    def mini_ship_bullets_vs_spike_boss(
        self,
        mini_ship_bullets: list[MiniShipBullet],
        boss: SpikeBoss,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão de balas das mini ships com SpikeBoss."""
        score_gain = 0
        for b in mini_ship_bullets[:]:
            if b.rect.colliderect(pygame.Rect(boss.x, boss.y, boss.w, boss.h)):
                b.dead = True
                boss.take_damage(b.damage)
                sound_manager.play_boss_damage()
                entity_manager.spawn_explosion(b.x, b.y, size=15)

                if boss.dead:
                    from ..core.config import config as Config

                    floating_scores.append(
                        FloatingScore(
                            boss.x + boss.w / 2,
                            boss.y + boss.h / 2,
                            Config.BOSS_DEFEAT_SCORE,
                        )
                    )
                    score_gain += Config.BOSS_DEFEAT_SCORE
                    entity_manager.spawn_explosion(
                        boss.x + boss.w / 2, boss.y + boss.h / 2, size=100
                    )
        return score_gain

    def mini_ship_bullets_vs_spikes(
        self,
        mini_ship_bullets: list[MiniShipBullet],
        spikes: list[Spike],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão de balas das mini ships com Spikes."""
        score_gain = 0

        # Build spatial grid for spikes
        grid = SpatialGrid[Spike]()
        for spike in spikes:
            grid.insert_from_rect(spike)

        for b in mini_ship_bullets[:]:
            # Query potential spikes (expand by 10 pixels)
            query_x = b.rect.x - 10
            query_y = b.rect.y - 10
            query_w = b.rect.width + 20
            query_h = b.rect.height + 20
            potential_spikes = grid.query(query_x, query_y, query_w, query_h)
            for spike in potential_spikes:
                # Só colide se o spike estiver voando
                if spike.state == "flying" and b.rect.colliderect(spike.rect):
                    b.dead = True
                    spike.dead = True
                    entity_manager.spawn_explosion(
                        spike.center_x, spike.center_y, size=15
                    )
                    sound_manager.play_explosion_alien()
                    score_gain += Config.SPIKE_POINTS
                    break
        return score_gain

    def ship_vs_powerups(
        self,
        ship: Ship,
        powerups: list[PowerUp],
    ) -> list[str]:
        collected_kinds: list[str] = []
        for p in powerups[:]:
            if ship.rect.colliderect(p.rect):
                p.dead = True
                kind = getattr(p, "kind", "shield")
                collected_kinds.append(kind)
        return collected_kinds

    def ship_vs_stars(
        self,
        ship: Ship,
        stars: list[Star],
    ) -> int:
        """Verifica colisão entre nave e estrelas. Retorna quantidade coletada."""
        collected = 0
        for star in stars[:]:
            if ship.rect.colliderect(star.get_rect()):
                star.dead = True
                collected += 1
        return collected

    def ship_vs_spikes(
        self, ship: Ship, spikes: list[Spike], entity_manager: "EntityManager"
    ) -> bool:
        """Verifica colisão entre nave e espinhos."""
        if ship.invuln > 0:
            return False
        for spike in spikes[:]:
            if ship.rect.colliderect(spike.rect):
                # Destruir o espinho ao acertar a nave
                spike.dead = True
                # Criar explosão no local do spike
                entity_manager.spawn_explosion(spike.center_x, spike.center_y, size=15)
                return True
        return False

    def bullets_vs_spikes(
        self,
        bullets: list[Bullet],
        spikes: list[Spike],
        entity_manager: "EntityManager",
    ) -> int:
        """Verifica colisão entre balas e espinhos. Retorna pontos ganhos."""
        score_gain = 0

        # Build spatial grid for spikes
        grid = SpatialGrid[Spike]()
        for spike in spikes:
            grid.insert_from_rect(spike)

        for b in bullets[:]:
            # Query potential spikes (expand by 10 pixels)
            query_x = b.rect.x - 10
            query_y = b.rect.y - 10
            query_w = b.rect.width + 20
            query_h = b.rect.height + 20
            potential_spikes = grid.query(query_x, query_y, query_w, query_h)
            for spike in potential_spikes:
                if b.rect.colliderect(spike.rect):
                    # Remover bala
                    if not b.piercing:
                        b.dead = True

                    # Destruir espinho
                    spike.dead = True

                    # Explosão pequena no centro do spike
                    entity_manager.spawn_explosion(
                        spike.center_x, spike.center_y, size=15
                    )

                    # Som
                    sound_manager.play_explosion_asteroid()

                    # Pontos
                    score_gain += spike.get_points_value()
                    break  # Próxima bala
        return score_gain

    def bullets_vs_spike_boss(
        self,
        bullets: list[Bullet],
        boss: SpikeBoss,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão de balas com SpikeBoss."""
        score_gain = 0
        for b in bullets[:]:
            if b.rect.colliderect(pygame.Rect(boss.x, boss.y, boss.w, boss.h)):
                if not b.piercing:
                    b.dead = True
                boss.take_damage(b.damage)
                sound_manager.play_boss_damage()
                entity_manager.spawn_explosion(b.x, b.y, size=15)

                # Pontos ao derrotar
                if boss.dead:
                    from ..core.config import config as Config

                    floating_scores.append(
                        FloatingScore(
                            boss.x + boss.w / 2,
                            boss.y + boss.h / 2,
                            Config.BOSS_DEFEAT_SCORE,
                        )
                    )
                    score_gain += Config.BOSS_DEFEAT_SCORE
                    entity_manager.spawn_explosion(
                        boss.x + boss.w / 2, boss.y + boss.h / 2, size=100
                    )
        return score_gain

    def ship_vs_spike_boss(
        self, ship: Ship, boss: SpikeBoss, entity_manager: "EntityManager"
    ) -> bool:
        """Colisão entre nave e SpikeBoss."""
        if ship.invuln > 0:
            return False

        # Colisão com o corpo do boss
        if ship.rect.colliderect(pygame.Rect(boss.x, boss.y, boss.w, boss.h)):
            entity_manager.spawn_explosion(
                ship.x + ship.w / 2, ship.y + ship.h / 2, size=30
            )
            return True

        # Colisão com onda de proximidade
        proximity_data = boss.get_proximity_attack_data()
        if proximity_data:
            _, boss_center_x, boss_center_y, wave_radius = proximity_data
            # Calcular distância do centro da nave ao centro do boss
            ship_center_x = ship.x + ship.w / 2
            ship_center_y = ship.y + ship.h / 2
            dx = ship_center_x - boss_center_x
            dy = ship_center_y - boss_center_y
            distance = math.sqrt(dx * dx + dy * dy)

            # Se a nave está dentro da onda
            if distance <= wave_radius:
                entity_manager.spawn_explosion(
                    ship.x + ship.w / 2, ship.y + ship.h / 2, size=20
                )
                return True

        return False

    def bullets_vs_boss_squares(
        self,
        bullets: list[Bullet],
        boss_squares: list[BossSquare],
        entity_manager: "EntityManager",
    ) -> int:
        """
        Colisão entre balas do jogador e quadrados do boss.
        Os quadrados NÃO são destruídos, apenas geram explosão visual.
        Retorna número de acertos para feedback visual/sonoro.
        """
        hit_count = 0

        for bullet in bullets[:]:
            if bullet.dead:
                continue

            bullet_rect = bullet.rect

            for square in boss_squares:
                if square.dead:
                    continue

                square_rect = square.get_rect()
                if bullet_rect.colliderect(square_rect):
                    # Criar explosão no ponto de impacto
                    entity_manager.spawn_explosion(bullet.x, bullet.y, size=20)

                    # Destruir apenas a bala
                    bullet.dead = True
                    hit_count += 1

                    # Som de impacto (mesmo som de dano ao boss)
                    sound_manager.play_boss_damage()
                    break

        return hit_count

    def ship_vs_boss_squares(self, ship: Ship, boss_squares: list[BossSquare]) -> bool:
        """
        Colisão entre nave e quadrados do boss (indestrutíveis).
        Os quadrados não são destruídos ao colidir.
        """
        if ship.invuln > 0:
            return False

        ship_rect = ship.rect

        for square in boss_squares:
            if ship_rect.colliderect(square.get_rect()):
                return True

        return False

    def player_lasers_vs_enemies(
        self,
        player_lasers: list[PlayerLaser],
        enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy],
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Colisão dos lasers do jogador com inimigos (atravessa múltiplos alvos)."""
        score_gain: int = 0
        destroyed_count: int = 0
        score_events: list[tuple[float, float, int]] = []

        for laser in player_lasers:
            if laser.w <= 0:  # Laser ainda não expandiu ou já retraiu
                continue

            line = laser.get_collision_line()

            for enemy in enemies[:]:
                if enemy.dead:
                    continue

                # Verificar se já atingiu este inimigo
                enemy_id = id(enemy)
                if enemy_id in laser.hit_enemies:
                    continue

                enemy_rect = enemy.rect
                if enemy_rect.clipline(line):
                    # Marcar inimigo como já atingido por este laser
                    laser.hit_enemies.add(enemy_id)

                    # Aplicar dano de acordo com o tipo de inimigo
                    if isinstance(enemy, Meteor):
                        enemy.dead = True  # Meteoros morrem instantaneamente
                    elif isinstance(enemy, ExplosiveMine):
                        enemy.take_damage(laser.damage)
                    else:
                        # Alien ou EyeEnemy
                        if isinstance(enemy, EyeEnemy):
                            enemy.destroy()
                        enemy.dead = True
                    
                    # Som apropriado baseado no tipo
                    if isinstance(enemy, Meteor):
                        sound_manager.play_explosion_asteroid()
                    else:
                        sound_manager.play_explosion_alien()

                    # Spawnar pequena explosão no ponto de impacto
                    cx: float = enemy.x + getattr(enemy, 'w', 0) / 2
                    cy: float = enemy.y + getattr(enemy, 'h', 0) / 2
                    entity_manager.spawn_explosion(cx, cy, size=20)

                    # Se morreu, adicionar pontos
                    if enemy.dead:
                        pts: int = enemy.get_points_value()
                        score_gain += pts
                        destroyed_count += 1
                        score_events.append((cx, cy, pts))
                        floating_scores.append(FloatingScore(cx, cy, pts))

        return score_gain, destroyed_count, score_events

    def player_lasers_vs_boss(
        self,
        player_lasers: list[PlayerLaser],
        boss: Boss | SpikeBoss,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão dos lasers do jogador com o boss."""
        score_gain: int = 0

        for laser in player_lasers:
            if laser.w <= 0:
                continue

            line = laser.get_collision_line()
            boss_rect = pygame.Rect(boss.x, boss.y, boss.w, boss.h)

            if boss_rect.clipline(line):
                # Verificar se já atingiu o boss
                boss_id = id(boss)
                if boss_id in laser.hit_enemies:
                    continue

                laser.hit_enemies.add(boss_id)
                boss.take_damage(laser.damage)
                sound_manager.play_boss_damage()

                # Explosão no ponto de impacto
                cx: float = boss.x + boss.w / 2
                cy: float = boss.y + boss.h / 2
                entity_manager.spawn_explosion(cx, cy, size=30)

                if boss.dead:
                    # Boss sempre dá pontos fixos ao morrer
                    from ..core.config import config as Config
                    pts: int = Config.BOSS_DEFEAT_SCORE
                    score_gain += pts
                    floating_scores.append(FloatingScore(cx, cy, pts))

        return score_gain
