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
from ..entities.square_minion_boss import SquareMinionBoss
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
    
    @staticmethod
    def get_collision_info(enemy: Meteor | Alien | ExplosiveMine | EyeEnemy | SquareMinionBoss) -> tuple[float, float, float]:
        """OPT #6: Helper para calcular center_x, center_y, radius de qualquer inimigo.
        
        Retorna (center_x, center_y, radius) consolidando lógica de type checking.
        """
        if isinstance(enemy, ExplosiveMine):
            return enemy.x, enemy.y, enemy.radius
        return enemy.x + enemy.w / 2, enemy.y + enemy.h / 2, enemy.w / 2

    def _destroy_enemy(
        self,
        enemy: Meteor | Alien | ExplosiveMine | EyeEnemy | SquareMinionBoss,
        enemies_list: list[Meteor | Alien | ExplosiveMine | EyeEnemy | SquareMinionBoss],
        entity_manager: "EntityManager",
        explosion_size: int | None = None,
    ) -> tuple[int, tuple[float, float, int]]:
        """Helper para destruição de inimigos com explosão, som e fragmentos.
        
        Centraliza lógica repetida em 8+ lugares.
        Retorna (pontos, (cx, cy, pontos)) para score_events.
        
        Args:
            explosion_size: Tamanho da explosão. Se None, usa w//2 ou radius.
        """
        # Calcular centro
        cx, cy, _ = self.get_collision_info(enemy)
        
        # Marcar como morto
        if isinstance(enemy, EyeEnemy):
            enemy.destroy()
        enemy.dead = True
        
        # Explosão visual - tamanho depende do tipo
        if explosion_size is None:
            if isinstance(enemy, ExplosiveMine):
                explosion_size = enemy.radius
            else:
                explosion_size = int(enemy.w // 2)
        entity_manager.spawn_explosion(cx, cy, size=explosion_size)
        
        # Som apropriado
        if isinstance(enemy, Meteor):
            sound_manager.play_explosion_asteroid()
        else:
            sound_manager.play_explosion_alien()
        
        # Pontos
        pts = enemy.get_points_value()
        
        # Fragmentos (apenas meteoros)
        if isinstance(enemy, Meteor) and hasattr(enemy, "spawn_fragments"):
            fragments = enemy.spawn_fragments()
            if fragments:
                enemies_list.extend(fragments)
        
        return pts, (cx, cy, pts)

    def _apply_area_damage(
        self,
        source_x: float,
        source_y: float,
        damage_radius: float,
        hit_tracking_set: set[int],
        enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy],
        entity_manager: "EntityManager",
        damage_to_mine: int = 2,
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Helper para aplicar dano em área a inimigos.
        
        Usado por: explosive effects, air strike bombs, explosive bullets.
        Retorna (score_gain, destroyed_count, score_events).
        """
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        for enemy in enemies[:]:
            if enemy.dead:
                continue

            enemy_id = id(enemy)
            if enemy_id in hit_tracking_set:
                continue

            # Calcular distância
            cx, cy, radius = self.get_collision_info(enemy)
            dist_sq = (cx - source_x) ** 2 + (cy - source_y) ** 2

            # Verificar colisão
            if dist_sq < (damage_radius + radius) ** 2:
                hit_tracking_set.add(enemy_id)

                if isinstance(enemy, ExplosiveMine):
                    enemy.take_damage(damage_to_mine)
                elif isinstance(enemy, SquareMinionBoss):
                    # SquareMinionBoss não pode ser destruído por tiros
                    pass  # Não faz nada - imune a tiros
                else:
                    pts, score_event = self._destroy_enemy(enemy, enemies, entity_manager)
                    score_gain += pts
                    destroyed_count += 1
                    score_events.append(score_event)

        return score_gain, destroyed_count, score_events

    def _apply_boss_damage(
        self,
        projectiles: list[Bullet] | list[MiniShipBullet],
        boss: Boss | SpikeBoss,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
        is_piercing_allowed: bool = False,
    ) -> int:
        """Helper para dano unificado ao boss (normal ou spike).
        
        Centraliza lógica de 4 métodos idênticos.
        Retorna score_gain.
        """
        score_gain = 0
        boss_rect = pygame.Rect(boss.x, boss.y, boss.w, boss.h)
        
        for proj in projectiles[:]:
            proj_rect = proj.rect
            if proj_rect.colliderect(boss_rect):
                # Destruir projétil se não for piercing
                if not (is_piercing_allowed and getattr(proj, 'piercing', False)):
                    proj.dead = True
                
                # Aplicar dano com multiplicador
                from ..core.config import config as Config
                damage = int(proj.damage * Config.BOSS_UPGRADE_DAMAGE_MULTIPLIER)
                boss.take_damage(damage)
                sound_manager.play_boss_damage()
                entity_manager.spawn_explosion(proj.x, proj.y, size=15)
                
                # Recompensa ao derrotar
                if boss.dead:
                    cx, cy = boss.x + boss.w / 2, boss.y + boss.h / 2
                    floating_scores.append(FloatingScore(cx, cy, Config.BOSS_DEFEAT_SCORE))
                    score_gain += Config.BOSS_DEFEAT_SCORE
                    entity_manager.spawn_explosion(cx, cy, size=100)
        
        return score_gain

    def check_mine_explosions(
        self,
        enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy],
        mine_explosions: list[MineExplosion],
        ship: Ship,
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]], bool]:
        """
        Processa explosões de minas.

        Fluxo:
        1) Quando uma mina está explodindo E seu timer acabou, cria MineExplosion visual.
        2) Processa explosões ativas usando raio máximo para causar dano.
        
        IMPORTANTE: Verificamos is_exploding + pre_explosion_timer <= 0 porque
        a mina só fica dead=True quando o timer acaba internamente.
        """
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []
        ship_hit = False

        # 1) Criar explosões para minas cujo timer de explosão acabou
        for enemy in enemies[:]:
            if isinstance(enemy, ExplosiveMine):
                # Verificar se está explodindo E timer acabou (mas ainda não marcada dead)
                # OU já está dead (timer acabou no update anterior)
                should_explode = (
                    (enemy.is_exploding and enemy.pre_explosion_timer <= 0 and not enemy.dead)
                    or enemy.dead
                )
                if should_explode:
                    cx, cy = (enemy.x, enemy.y)
                    explosion_radius = enemy.explosion_radius

                    mine_explosions.append(MineExplosion(cx, cy, size=explosion_radius))

                    # Checar nave e limpar formações
                    if self.handle_mine_explosion(
                        cx, cy, explosion_radius, enemies, ship, entity_manager
                    ):
                        ship_hit = True

                    sound_manager.play_explosion_boss()

                    # Marcar como dead DEPOIS de criar explosão
                    enemy.dead = True

                    pts = enemy.get_points_value()
                    score_gain += pts
                    destroyed_count += 1
                    score_events.append((cx, cy, pts))

        # 2) Processar explosões ativas: dano usa raio máximo (visual cresce gradualmente)
        for explosion in mine_explosions[:]:
            if explosion.finished():
                continue

            explosion_radius = explosion.max_radius

            explosion_x = explosion.x
            explosion_y = explosion.y

            for enemy in enemies[:]:
                if enemy.dead:
                    continue

                if isinstance(enemy, ExplosiveMine):
                    enemy_cx, enemy_cy = enemy.x, enemy.y
                    enemy_r = enemy.radius
                else:
                    enemy_cx = enemy.x + enemy.w / 2
                    enemy_cy = enemy.y + enemy.h / 2
                    enemy_r = enemy.w / 2

                dist_sq = (enemy_cx - explosion_x) ** 2 + (enemy_cy - explosion_y) ** 2

                if dist_sq < (explosion_radius + enemy_r) ** 2:
                    if isinstance(enemy, ExplosiveMine):
                        enemy.take_damage(enemy.health)
                    elif isinstance(enemy, SquareMinionBoss):
                        # SquareMinionBoss não pode ser destruído por explosões
                        pass  # Não faz nada - imune a explosões
                    else:
                        pts, score_event = self._destroy_enemy(enemy, enemies, entity_manager)
                        score_gain += pts
                        destroyed_count += 1
                        score_events.append(score_event)

        return score_gain, destroyed_count, score_events, ship_hit

    def handle_mine_explosion(
        self,
        explosion_x: float,
        explosion_y: float,
        explosion_radius: int,
        enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy],
        ship: Ship,
        entity_manager: "EntityManager",
    ) -> bool:
        """
        Checa colisão da explosão de mina com a nave e limpa formações.

        O dano aos inimigos é aplicado em check_mine_explosions
        enquanto a animação está ativa (raio crescendo).
        Retorna True se a nave foi atingida.
        """
        ship_hit = False

        # Remover inimigos mortos das formações (para marcar formação como dead)
        for formation in entity_manager.formations:
            formation.enemies = [e for e in formation.enemies if not e.dead]

        # Check player collision
        if ship.invuln <= 0:
            ship_cx = ship.x + ship.w / 2
            ship_cy = ship.y + ship.h / 2
            ship_r = ship.w / 2

            dist_sq = (ship_cx - explosion_x) ** 2 + (ship_cy - explosion_y) ** 2
            if dist_sq < (explosion_radius + ship_r) ** 2:
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

            # Usar helper consolidado
            gain, destroyed, events = self._apply_area_damage(
                effect.x,
                effect.y,
                damage_radius,
                effect.hit_enemies,
                enemies,
                entity_manager,
                damage_to_mine=2,
            )
            score_gain += gain
            destroyed_count += destroyed
            score_events.extend(events)

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

            # Usar helper consolidado
            gain, destroyed, events = self._apply_area_damage(
                bomb.x,
                bomb.target_y,
                damage_radius,
                bomb.hit_enemies,
                enemies,
                entity_manager,
                damage_to_mine=5,  # Dano alto para minas
            )
            score_gain += gain
            destroyed_count += destroyed
            score_events.extend(events)

        return score_gain, destroyed_count, score_events

    def mini_ship_bullets_vs_enemies(
        self,
        mini_ship_bullets: list[MiniShipBullet],
        enemy_grid: SpatialGrid[Meteor | Alien | ExplosiveMine | EyeEnemy | SquareMinionBoss],
        enemies: list[
            Meteor | Alien | ExplosiveMine | EyeEnemy | SquareMinionBoss
        ],  # Para adicionar fragments
        entity_manager: "EntityManager",  # <-- ADICIONAR
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        # Early return se lista vazia
        if not mini_ship_bullets:
            return 0, 0, []

        # Usar grid existente

        for b in mini_ship_bullets[:]:
            # OPT #2 & #3: Cache rect para evitar múltiplos acessos
            b_rect = b.rect
            # Query potential collisions using spatial grid (expand by 10 pixels for safety)
            query_x = b_rect.x - 10
            query_y = b_rect.y - 10
            query_w = b_rect.width + 20
            query_h = b_rect.height + 20
            potential_enemies = enemy_grid.query(query_x, query_y, query_w, query_h)
            
            # Early return se query vazia
            if not potential_enemies:
                continue

            for enemy in potential_enemies:
                # Handle both rect property and get_rect() method
                enemy_rect = enemy.rect if hasattr(enemy, 'rect') else enemy.get_rect()
                if b_rect.colliderect(enemy_rect):  # Usa cache
                    b.dead = True

                    if isinstance(enemy, ExplosiveMine):
                        enemy.take_damage(1)
                    elif isinstance(enemy, SquareMinionBoss):
                        # SquareMinionBoss não pode ser destruído por tiros, mas a bala sim
                        # Criar explosão visual no ponto de impacto
                        entity_manager.spawn_explosion(b.x, b.y, size=20)
                        # Som de impacto (mesmo som de dano ao boss)
                        sound_manager.play_boss_damage()
                        pass  # Não faz nada - imune a tiros
                    else:
                        # Usar helper consolidado
                        pts, score_event = self._destroy_enemy(enemy, enemies, entity_manager)
                        score_gain += pts
                        destroyed_count += 1
                        score_events.append(score_event)

                    break  # Bullet is gone, check next bullet
        return score_gain, destroyed_count, score_events

    def bullets_vs_enemies(
        self,
        bullets: list[Bullet],
        mine_explosions: list[MineExplosion],
        ship: Ship,
        enemy_grid: SpatialGrid[Meteor | Alien | ExplosiveMine | EyeEnemy | SquareMinionBoss],
        enemies: list[
            Meteor | Alien | ExplosiveMine | EyeEnemy | SquareMinionBoss
        ],  # Para adicionar fragments
        entity_manager: "EntityManager",  # <-- NOVO
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        # Early return se lista vazia
        if not bullets:
            return 0, 0, []

        for b in bullets[:]:
            # OPT #2 & #3: Cache rect para evitar múltiplos acessos
            b_rect = b.rect
            # Query potential collisions using spatial grid (expand by 10 pixels for safety)
            query_x = b_rect.x - 10
            query_y = b_rect.y - 10
            query_w = b_rect.width + 20
            query_h = b_rect.height + 20
            potential_enemies = enemy_grid.query(query_x, query_y, query_w, query_h)
            
            # Early return se query vazia
            if not potential_enemies:
                continue

            for enemy in potential_enemies:
                # Handle both rect property and get_rect() method
                enemy_rect = enemy.rect if hasattr(enemy, 'rect') else enemy.get_rect()
                if b_rect.colliderect(enemy_rect):  # Usa cache
                    b.dead = True  # Bala sempre é destruída ao colidir
                    
                    if isinstance(enemy, ExplosiveMine):
                        enemy.take_damage(1)
                    elif isinstance(enemy, SquareMinionBoss):
                        # SquareMinionBoss não pode ser destruído por tiros, mas a bala sim
                        # Criar explosão visual no ponto de impacto
                        entity_manager.spawn_explosion(b.x, b.y, size=20)
                        # Som de impacto (mesmo som de dano ao boss)
                        sound_manager.play_boss_damage()
                        pass  # Não faz nada - imune a tiros
                    else:
                        # Usar helper consolidado
                        pts, score_event = self._destroy_enemy(enemy, enemies, entity_manager)
                        score_gain += pts
                        destroyed_count += 1
                        score_events.append(score_event)

                    # Se é um tiro explosivo, causar dano em área
                    if b.explosive:
                        explosion_cx = b.x + b.w / 2
                        explosion_cy = b.y + b.h / 2
                        explosion_radius = 60  # Raio da explosão

                        # Criar efeito visual do círculo de área (branco semi-transparente)
                        entity_manager.spawn_explosive_effect(
                            explosion_cx, explosion_cy, radius=explosion_radius
                        )

                        # Criar explosão visual de partículas
                        entity_manager.spawn_explosion(
                            explosion_cx, explosion_cy, size=explosion_radius // 2
                        )

                        # Tocar som de explosão
                        sound_manager.play_explosion_asteroid()

                        # Dano em área para inimigos próximos
                        area_query = enemy_grid.query(
                            explosion_cx - explosion_radius,
                            explosion_cy - explosion_radius,
                            explosion_radius * 2,
                            explosion_radius * 2,
                        )
                        for nearby_enemy in area_query:
                            if nearby_enemy.dead:
                                continue
                            # Usar helper para calcular center
                            ncx, ncy, _ = self.get_collision_info(nearby_enemy)
                            dist_sq = (ncx - explosion_cx) ** 2 + (
                                ncy - explosion_cy
                            ) ** 2
                            if dist_sq < explosion_radius**2:
                                if isinstance(nearby_enemy, ExplosiveMine):
                                    nearby_enemy.take_damage(2)  # Dano extra
                                elif isinstance(nearby_enemy, SquareMinionBoss):
                                    # SquareMinionBoss não pode ser destruído por explosões de área
                                    pass  # Não faz nada - imune a explosões
                                elif not nearby_enemy.dead:
                                    pts, score_event = self._destroy_enemy(nearby_enemy, enemies, entity_manager)
                                    score_gain += pts
                                    destroyed_count += 1
                                    score_events.append(score_event)

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
        return self._apply_boss_damage(bullets, boss, floating_scores, entity_manager, is_piercing_allowed=True)

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
        enemy_grid: SpatialGrid[Meteor | Alien | ExplosiveMine | EyeEnemy | SquareMinionBoss],
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
            # Handle both rect property and get_rect() method
            enemy_rect = enemy.rect if hasattr(enemy, 'rect') else enemy.get_rect()
            if enemy and ship.rect.colliderect(enemy_rect):
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
                elif isinstance(enemy, (Alien, SquareMinionBoss)):
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
        return self._apply_boss_damage(mini_ship_bullets, boss, floating_scores, entity_manager, is_piercing_allowed=False)

    def mini_ship_bullets_vs_spike_boss(
        self,
        mini_ship_bullets: list[MiniShipBullet],
        boss: SpikeBoss,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão de balas das mini ships com SpikeBoss."""
        return self._apply_boss_damage(mini_ship_bullets, boss, floating_scores, entity_manager, is_piercing_allowed=False)

    def mini_ship_bullets_vs_spikes(
        self,
        mini_ship_bullets: list[MiniShipBullet],
        spike_grid: SpatialGrid[Spike],  # OPT #1: Recebe grid pronta
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão de balas das mini ships com Spikes."""
        score_gain = 0

        # OPT #2 & #3: Cache rect para evitar múltiplos acessos
        for b in mini_ship_bullets[:]:
            b_rect = b.rect  # Cache uma vez
            # Query potential spikes (expand by 10 pixels)
            query_x = b_rect.x - 10
            query_y = b_rect.y - 10
            query_w = b_rect.width + 20
            query_h = b_rect.height + 20
            potential_spikes = spike_grid.query(query_x, query_y, query_w, query_h)
            for spike in potential_spikes:
                # Só colide se o spike estiver voando
                if spike.state == "flying" and b_rect.colliderect(spike.rect):  # Usa cache
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
        spike_grid: SpatialGrid[Spike],  # OPT #1: Recebe grid pronta
        entity_manager: "EntityManager",
    ) -> int:
        """Verifica colisão entre balas e espinhos. Retorna pontos ganhos."""
        score_gain = 0

        # OPT #2 & #3: Cache rect para evitar múltiplos acessos
        for b in bullets[:]:
            b_rect = b.rect  # Cache uma vez
            # Query potential spikes (expand by 10 pixels)
            query_x = b_rect.x - 10
            query_y = b_rect.y - 10
            query_w = b_rect.width + 20
            query_h = b_rect.height + 20
            potential_spikes = spike_grid.query(query_x, query_y, query_w, query_h)
            for spike in potential_spikes:
                if b_rect.colliderect(spike.rect):  # Usa cache
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
        return self._apply_boss_damage(bullets, boss, floating_scores, entity_manager, is_piercing_allowed=True)

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

                # Handle both rect property and get_rect() method
                enemy_rect = enemy.rect if hasattr(enemy, 'rect') else enemy.get_rect()
                if enemy_rect.clipline(line):
                    # Marcar inimigo como já atingido por este laser
                    laser.hit_enemies.add(enemy_id)

                    # Aplicar dano de acordo com o tipo de inimigo
                    if isinstance(enemy, Meteor):
                        enemy.dead = True  # Meteoros morrem instantaneamente
                    elif isinstance(enemy, ExplosiveMine):
                        enemy.take_damage(laser.damage)
                        continue  # Não usar _destroy_enemy para minas
                    elif isinstance(enemy, SquareMinionBoss):
                        # SquareMinionBoss não pode ser destruído por lasers
                        pass  # Não faz nada - imune a lasers
                    
                    # Para inimigos normais, usar helper com explosion_size customizado
                    pts, score_event = self._destroy_enemy(enemy, enemies, entity_manager, explosion_size=20)
                    score_gain += pts
                    destroyed_count += 1
                    score_events.append(score_event)
                    floating_scores.append(FloatingScore(*score_event))

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
                # Apply damage modifier for laser upgrade against boss
                from ..core.config import config as Config
                damage = int(laser.damage * Config.BOSS_UPGRADE_DAMAGE_MULTIPLIER)
                boss.take_damage(damage)
                sound_manager.play_boss_damage()

                # Explosão no ponto de impacto
                cx: float = boss.x + boss.w / 2
                cy: float = boss.y + boss.h / 2
                entity_manager.spawn_explosion(cx, cy, size=30)

                if boss.dead:
                    # Boss sempre dá pontos fixos ao morrer
                    pts: int = Config.BOSS_DEFEAT_SCORE
                    score_gain += pts
                    floating_scores.append(FloatingScore(cx, cy, pts))
                    entity_manager.spawn_explosion(cx, cy, size=100)

        return score_gain
