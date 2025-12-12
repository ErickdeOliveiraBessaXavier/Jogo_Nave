import pygame
from ..entities.bullet import Bullet
from ..entities.bullet_pool import BulletPool
from ..entities.meteor import Meteor
from ..entities.meteor_pool import MeteorPool
from ..entities.alien import Alien
from ..entities.boss import Boss
from ..entities.boss_square import BossSquare
from ..entities.alien_bullet import AlienBullet
from ..entities.boss_laser import BossLaser
from ..entities.spike_boss_laser import SpikeBossLaser
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
from ..entities.formation import Formation
from ..entities.spike import Spike
from ..entities.spike_boss import SpikeBoss
from ..entities.player_laser import PlayerLaser
from ..core.spatial_grid import SpatialGrid
from ..entities.explosion_pool import ExplosionPool
from ..entities.emp_wave import EMPWave
from ..entities.star import Star
from ..entities.explosive_effect import ExplosiveEffect
from ..entities.air_strike_marker import AirStrikeMarker
from ..entities.air_strike_bomb import AirStrikeBomb
from ..entities.square_minion_boss import SquareMinionBoss
from ..entities.square_minion_boss import SquareMinionBoss
from typing import Dict, Any, TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..entities.ship import Ship


class EntityManager:
    def __init__(self, sound_manager: Optional[Any] = None):
        self.sound_manager = sound_manager
        self.bullets: list[Bullet] = []
        self.emp_waves: list[EMPWave] = []  # Ondas visuais do EMP
        self.explosive_effects: list[ExplosiveEffect] = (
            []
        )  # Efeitos visuais de explosão de área
        self.enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy | SquareMinionBoss] = []
        self.alien_bullets: list[AlienBullet] = []
        self.boss_lasers: list[BossLaser | SpikeBossLaser] = []
        self.player_lasers: list[PlayerLaser] = []  # Lasers do jogador
        self.boss_squares: list[BossSquare] = []  # Quadrados lançados pelo boss
        self.eye_lasers: list[EyeLaser] = []
        self.mine_explosions: list[MineExplosion] = []
        self.powerups: list[PowerUp] = []
        self.stars: list[Star] = []  # Estrelas coletáveis
        self.floating_scores: list[FloatingScore] = []
        self.boss: Boss | SpikeBoss | None = None
        self.mini_ships: list[MiniShip] = []
        self.mini_ship_bullets: list[MiniShipBullet] = []
        self.formations: list[Formation] = []  # Nova lista para formações
        self.spikes: list[Spike] = []  # Lista para espinhos do SpikeBoss
        self.air_strike_markers: list[AirStrikeMarker] = []  # Marcadores de bombardeio
        self.air_strike_bombs: list[AirStrikeBomb] = []  # Bombas do bombardeio aéreo
        self.meteor_pool = MeteorPool(initial_size=100)  # Pool de meteoros
        self.bullet_pool = BulletPool(initial_size=50)  # Pool de balas
        self.enemy_spatial_grid: SpatialGrid[
            Meteor | Alien | ExplosiveMine | EyeEnemy | SquareMinionBoss
        ] = SpatialGrid()  # Grid espacial para inimigos
        self.spike_spatial_grid: SpatialGrid[Spike] = SpatialGrid()  # OPT: Grid para spikes
        self.explosion_pool = ExplosionPool(initial_size=50)  # Pool de explosões

    def spawn_explosion(self, x: float, y: float, size: int = 30) -> Explosion:
        """
        Spawna uma explosão usando o pool.

        Args:
            x, y: Posição da explosão
            size: Tamanho da explosão

        Returns:
            Explosão criada ou reutilizada do pool
        """
        return self.explosion_pool.get(x, y, size)

    def spawn_emp_wave(self, center_x: float, center_y: float) -> None:
        """Spawna uma onda visual de EMP."""
        self.emp_waves.append(EMPWave(center_x, center_y))

    def spawn_explosive_effect(self, x: float, y: float, radius: float = 60.0) -> None:
        """Spawna um efeito visual de explosão de área (círculo branco semi-transparente)."""
        self.explosive_effects.append(ExplosiveEffect(x, y, radius=radius))

    def spawn_air_strike(self, target_x: float, target_y: float) -> None:
        """Spawna um marcador e uma bomba para o bombardeio aéreo."""
        marker = AirStrikeMarker(target_x, target_y)
        self.air_strike_markers.append(marker)
        # A bomba será spawnada quando o marcador terminar

    def spawn_air_strike_bomb(self, target_x: float, target_y: float) -> None:
        """Spawna uma bomba de bombardeio aéreo."""
        # Callbacks para sons
        on_explode = None
        on_fall = None
        if self.sound_manager:
            on_explode = self.sound_manager.play_explosion_asteroid
            on_fall = self.sound_manager.play_meteor_rain
        bomb = AirStrikeBomb(target_x, target_y, on_explode=on_explode, on_fall=on_fall)
        self.air_strike_bombs.append(bomb)

    def spawn_player_laser(
        self,
        x: float,
        y: float,
        target_x: float,
        target_y: float,
        damage: int = 50,
        ship: Optional["Ship"] = None,
        ball_index: int = -1,
        target_entity: Optional[Any] = None,
    ) -> PlayerLaser:
        """Spawna um laser do jogador."""
        laser = PlayerLaser(
            x, y, target_x, target_y, damage=damage, ship=ship, ball_index=ball_index, target_entity=target_entity
        )
        self.player_lasers.append(laser)
        return laser

    def rebuild_all_grids(self):
        """OPT #1: Reconstrói todas as grids espaciais (inimigos + spikes)."""
        # Grid de inimigos normais + formações
        self.enemy_spatial_grid.clear()

        # Inserir inimigos normais
        for enemy in self.enemies:
            self.enemy_spatial_grid.insert_from_rect(enemy)

        # Inserir inimigos de formações (reutilizar cache se disponível)
        cached_formation_enemies = getattr(self, "_cached_formation_enemies", None)
        if cached_formation_enemies:
            for enemy in cached_formation_enemies:
                self.enemy_spatial_grid.insert_from_rect(enemy)
        else:
            # Fallback se cache não estiver disponível
            for formation in self.formations:
                for enemy in formation.get_enemies():
                    self.enemy_spatial_grid.insert_from_rect(enemy)

        # OPT #1: Grid de spikes (para evitar criar grid toda vez em collision checks)
        self.spike_spatial_grid.clear()
        for spike in self.spikes:
            self.spike_spatial_grid.insert_from_rect(spike)

    def update(self, dt: float, player_x: float, player_y: float, freeze_enemies: bool = False, screen_width: int = 1600, screen_height: int = 900):
        from typing import Any

        enemy_dt = 0.0 if freeze_enemies else dt

        new_alien_bullets: list[AlienBullet] = []
        new_eye_lasers: list[EyeLaser] = []

        # OPT #4: Cache formation enemies UMA VEZ para reutilizar em rebuild_enemy_grid()
        self._cached_formation_enemies: list[Any] = []

        # Cache de todos os inimigos (criar UMA VEZ)
        self._cached_all_enemies: list[Any] = list(self.enemies)
        for formation in self.formations:
            formation_enemies = formation.get_enemies()
            self._cached_formation_enemies.extend(formation_enemies)
            self._cached_all_enemies.extend(formation_enemies)
        if self.boss:
            self._cached_all_enemies.append(self.boss)

        # Atualizar ondas EMP (efeito visual)
        for wave in self.emp_waves[:]:
            wave.update(dt)
            if wave.dead:
                self.emp_waves.remove(wave)

        # Atualizar efeitos de explosão de área
        for effect in self.explosive_effects[:]:
            effect.update(dt)
            if effect.dead:
                self.explosive_effects.remove(effect)

        # OPT #5: Cache EMP settings to avoid repeated getattr() calls
        slow_active = getattr(self, "emp_active", False)
        slow_factor = getattr(self, "emp_slow_factor", 1.0) if slow_active else 1.0
        emp_waves = self.emp_waves  # Cache wave list reference

        def emp_mul_for(entity: Any) -> float:
            if not slow_active:
                # Ainda pode ter linger timer
                linger = getattr(entity, "emp_linger_timer", 0.0)
                if linger > 0.0:
                    return float(slow_factor)
                return 1.0

            # Obter posição da entidade (cache getattr result)
            rect = getattr(entity, "rect", None)
            if rect is not None:
                ex = rect.centerx
                ey = rect.centery
            else:
                ex = getattr(entity, "x", 0.0)
                ey = getattr(entity, "y", 0.0)

            # Verificar se está sendo afetada pela onda agora (use cached wave list)
            for wave in emp_waves:
                if wave.is_affecting_position(float(ex), float(ey), dt):
                    # Resetar/ativar timer de linger
                    try:
                        from ..core.upgrades_config import EMP_LINGER_DURATION

                        setattr(entity, "emp_linger_timer", float(EMP_LINGER_DURATION))
                    except Exception:
                        setattr(entity, "emp_linger_timer", 3.0)
                    return float(slow_factor)

            # Não está na onda, verificar linger
            linger = getattr(entity, "emp_linger_timer", 0.0)
            if linger > 0.0:
                return float(slow_factor)
            return 1.0

        # Atualizar timers de linger em todos
        def update_linger(entity: Any, dt: float) -> None:
            linger = getattr(entity, "emp_linger_timer", 0.0)
            if linger > 0.0:
                setattr(entity, "emp_linger_timer", max(0.0, linger - dt))

        # Atualizar formações
        for formation in self.formations[:]:
            update_linger(formation, dt)
            mul = emp_mul_for(formation)
            bullets_from_formation = formation.update(enemy_dt * mul)
            if bullets_from_formation:
                new_alien_bullets.extend(bullets_from_formation)

        # Update bullets do jogador (usar cache)
        for b in self.bullets:
            enemy_list = self._cached_all_enemies if b.homing else None
            b.update(dt, enemy_list)

        # Atualizar projéteis amigáveis (não congelam)
        for bullet in self.mini_ship_bullets:
            bullet.update(dt)
        for bullet in self.player_lasers:
            bullet.update(dt)

        # Atualizar projéteis inimigos (congelam)
        for bullet in self.alien_bullets:
            bullet.update(enemy_dt)
        for bullet in self.boss_lasers:
            bullet.update(enemy_dt)
        for bullet in self.eye_lasers:
            bullet.update(enemy_dt)
        # Update explosões do pool
        self.explosion_pool.update(dt)
        for me in self.mine_explosions:
            me.update(dt)
        for p in self.powerups:
            p.update(dt)
        for star in self.stars:
            star.update(dt)
        for fs in self.floating_scores:
            fs.update(dt)

        # Mini ships (usar cache)
        for ms in self.mini_ships:
            ms.update(dt, self._cached_all_enemies, self.mini_ship_bullets)

        # Atualizar spikes (precisam da posição do jogador para míssil teleguiado)
        # Contar quantos triângulos estão atualmente atacando (trembling ou flying)
        attacking_count = sum(
            1 for spike in self.spikes if spike.state in ("trembling", "flying")
        )
        for spike in self.spikes:
            update_linger(spike, dt)
            mul = emp_mul_for(spike)
            spike.update(enemy_dt * mul, player_x, player_y, attacking_count)

        if self.boss:
            # SpikeBoss retorna (List[Spike], List[SpikeBossLaser])
            if isinstance(self.boss, SpikeBoss):
                spawned_spikes, spike_boss_lasers = self.boss.update(
                    enemy_dt, player_x, player_y, self.spikes
                )
                if spawned_spikes:
                    self.spikes.extend(spawned_spikes)
                if spike_boss_lasers:
                    self.boss_lasers.extend(spike_boss_lasers)  # type: ignore
            # Boss normal retorna (List[BossLaser], List[Meteor], List[BossSquare])
            else:
                lasers_fired, spawned_meteors, spawned_squares = self.boss.update(
                    enemy_dt, player_x, player_y
                )
                if lasers_fired:
                    self.boss_lasers.extend(lasers_fired)
                if spawned_meteors:
                    for meteor in spawned_meteors:
                        self.enemies.append(meteor)
                if spawned_squares:
                    self.boss_squares.extend(spawned_squares)
                # Add orbital squares to boss_squares for collision detection
                for square in self.boss.floating_squares:
                    if square not in self.boss_squares:
                        self.boss_squares.append(square)
        for enemy in self.enemies:
            mul = emp_mul_for(enemy)
            scaled_dt = enemy_dt * mul
            if isinstance(enemy, Alien):
                shot = enemy.update(scaled_dt)
                if shot:
                    new_alien_bullets.extend(shot)
            elif isinstance(enemy, EyeEnemy):
                shot = enemy.update(scaled_dt, player_x, player_y)
                if shot:
                    new_eye_lasers.extend(shot)
            elif isinstance(enemy, GuidedMeteor):
                enemy.update(scaled_dt, player_x, player_y)
            elif isinstance(enemy, SquareMinionBoss):
                enemy.update(scaled_dt, screen_width, screen_height)
            else:
                enemy.update(scaled_dt)

        self.alien_bullets.extend(new_alien_bullets)
        self.eye_lasers.extend(new_eye_lasers)

        # Atualizar quadrados do boss (obtém dimensões dinâmicas da tela)
        screen = pygame.display.get_surface()
        screen_width = screen.get_width() if screen else 1600
        screen_height = screen.get_height() if screen else 900
        for square in self.boss_squares[:]:
            square.update(enemy_dt, screen_width, screen_height)
            if square.dead:
                self.boss_squares.remove(square)

        # Atualizar marcadores de bombardeio aéreo
        for marker in self.air_strike_markers[:]:
            marker.update(enemy_dt)
            if marker.dead:
                # Quando o marcador termina, spawnar a bomba
                self.spawn_air_strike_bomb(marker.target_x, marker.target_y)
                self.air_strike_markers.remove(marker)

        # Atualizar bombas de bombardeio aéreo
        for bomb in self.air_strike_bombs[:]:
            bomb.update(enemy_dt)
            if bomb.dead:
                self.air_strike_bombs.remove(bomb)

        # CRÍTICO: Cleanup ANTES de rebuild
        self.cleanup()
        self.rebuild_all_grids()  # OPT #1: Reconstrói todas as grids

    def update_for_game_over_slow_motion(
        self, dt: float, player_x: float, player_y: float
    ):
        """
        Updates entities specifically for the game over slow motion sequence.
        This method consolidates the update logic previously found in PlayingScene.
        """
        from typing import Any  # Used for type hinting lists of varied entities
        from ..entities.mini_ship import MiniShip
        from ..entities.eye_enemy import EyeEnemy
        from ..entities.guided_meteor import GuidedMeteor
        from ..entities.spike_boss import SpikeBoss

        # List of entity groups to update
        entity_groups: list[list[Any]] = [
            self.enemies,
            self.bullets,
            self.alien_bullets,
            self.boss_lasers,
            self.powerups,
            self.floating_scores,
            self.mini_ships,
            self.spikes,  # Include spikes in slow motion update
            self.boss_squares,  # Include boss squares
            self.eye_lasers,  # Include eye lasers
            self.mini_ship_bullets,  # Include mini ship bullets
        ]

        # Update all entities in a generic way, handling specific types
        for entity_list in entity_groups:
            for entity in entity_list:
                if isinstance(entity, (EyeEnemy, GuidedMeteor)):
                    entity.update(dt, player_x, player_y)
                elif isinstance(entity, MiniShip):
                    # MiniShip.update expects enemy_list and bullet_list,
                    # but during game over slow-mo, they might not need complex interactions
                    entity.update(dt, [], [])
                else:
                    entity.update(dt)

        # Update formations, if any
        for formation in self.formations:
            formation.update(dt)  # Formations update their internal enemies

        # Update explosões do pool (para mostrar explosão da nave no game over)
        self.explosion_pool.update(dt)

        # Handle boss update specifically if present
        if self.boss:
            if isinstance(self.boss, SpikeBoss):
                spawned_spikes, spike_boss_lasers = self.boss.update(
                    dt,
                    player_x,
                    player_y,
                    self.spikes,
                )
                if spawned_spikes:
                    self.spikes.extend(spawned_spikes)
                if spike_boss_lasers:
                    self.boss_lasers.extend(spike_boss_lasers)  # type: ignore
            else:  # General Boss type
                lasers_fired, spawned_meteors, spawned_squares = self.boss.update(
                    dt, player_x, player_y
                )
                if lasers_fired:
                    self.boss_lasers.extend(lasers_fired)
                if spawned_meteors:
                    self.enemies.extend(spawned_meteors)
                if spawned_squares:
                    self.boss_squares.extend(spawned_squares)

        # Ensure cleanup is called after updates during game over for consistency
        self.cleanup()

    def draw(
        self,
        surface: pygame.Surface,
        player_x: float,
        player_y: float,
        enemy_visible: bool = True,
    ):
        """Desenha todas as entidades. EyeEnemy precisa da posição do jogador."""
        from typing import Any

        # Entidades que não precisam da posição do jogador
        entity_lists: list[list[Any]] = [
            self.bullets,
            self.alien_bullets,
            self.boss_lasers,
            self.player_lasers,  # Lasers do jogador
            self.boss_squares,  # Quadrados do boss
            self.eye_lasers,
            self.mine_explosions,
            self.powerups,
            self.stars,  # Estrelas coletáveis
            self.floating_scores,
            self.mini_ship_bullets,
            self.mini_ships,
            self.spikes,  # Adicionar spikes
        ]

        if self.boss:
            entity_lists.append([self.boss])

        # Desenhar explosões do pool
        self.explosion_pool.draw_all(surface)

        # Desenhar ondas EMP (efeito visual)
        for wave in self.emp_waves:
            wave.draw(surface)

        # Desenhar efeitos de explosão de área (círculos brancos)
        for effect in self.explosive_effects:
            effect.draw(surface)

        # Desenhar marcadores de bombardeio aéreo
        for marker in self.air_strike_markers:
            marker.draw(surface)

        # Desenhar bombas de bombardeio aéreo
        for bomb in self.air_strike_bombs:
            bomb.draw(surface)

        for entity_list in entity_lists:
            for entity in entity_list:
                entity.draw(surface)

        # Desenhar inimigos (EyeEnemy precisa da posição do jogador)
        if enemy_visible:
            for enemy in self.enemies:
                if isinstance(enemy, EyeEnemy):
                    enemy.draw(surface, player_x, player_y)
                else:
                    enemy.draw(surface)

        # Desenhar formações (respeitar enemy_visible)
        if enemy_visible:
            for formation in self.formations:
                formation.draw(surface)

    def spawn_meteor(
        self,
        size: int | None = None,
        x: float | None = None,
        y: float | None = None,
        vx: float | None = None,
        vy: float | None = None,
    ) -> Meteor:
        """
        Spawna um meteoro usando o pool.

        Args:
            size, x, y, vx, vy: Parâmetros de configuração do meteoro

        Returns:
            Meteoro criado ou reutilizado do pool
        """
        meteor = self.meteor_pool.get(size=size, x=x, y=y, vx=vx, vy=vy)
        self.enemies.append(meteor)
        return meteor

    def spawn_bullet(
        self,
        x: float,
        y: float,
        damage: int = 10,
        piercing: bool = False,
        homing: bool = False,
        explosive: bool = False,
        low_ammo: bool = False,
    ) -> Bullet:
        """
        Spawna uma bala usando o pool.

        Args:
            x, y: Posição inicial da bala
            damage: Dano da bala
            piercing: Se a bala é perfurante
            homing: Se a bala é teleguiada
            explosive: Se a bala é explosiva
            low_ammo: Se restam poucas cargas (efeito de piscar)

        Returns:
            Bala criada ou reutilizada do pool
        """
        bullet = self.bullet_pool.get(
            x=x,
            y=y,
            damage=damage,
            piercing=piercing,
            homing=homing,
            explosive=explosive,
            low_ammo=low_ammo,
        )

        # Se é um tiro teleguiado, atribuir alvo inteligentemente
        if homing:
            target = self._assign_homing_target(bullet)
            if target:
                bullet.assign_target(target)

        self.bullets.append(bullet)
        return bullet

    def _assign_homing_target(self, bullet: Bullet) -> Any:
        """Atribui um alvo individual para o tiro teleguiado."""
        # Coletar todos os inimigos disponíveis
        all_enemies: list[Any] = list(self.enemies)

        for formation in self.formations:
            if not getattr(formation, "dead", True):
                all_enemies.extend(getattr(formation, "aliens", []))

        if self.boss and not getattr(self.boss, "dead", True):
            all_enemies.append(self.boss)

        # Filtrar inimigos mortos
        alive_enemies = [e for e in all_enemies if not getattr(e, "dead", True)]

        if not alive_enemies:
            return None

        # Contar quantos tiros teleguiados já estão mirando em cada inimigo
        target_counts: Dict[int, int] = {}
        for b in self.bullets:
            if getattr(b, "homing", False) and b.assigned_target_id is not None:
                target_counts[b.assigned_target_id] = (
                    target_counts.get(b.assigned_target_id, 0) + 1
                )

        # Encontrar o inimigo com menos tiros atribuídos
        best_target = None
        min_count: int = 999999
        min_distance: float = float("inf")

        for enemy in alive_enemies:
            enemy_id = id(enemy)
            count: int = target_counts.get(enemy_id, 0)

            # Calcular distância para critério de desempate
            enemy_x = enemy.x + getattr(enemy, "w", 0) / 2
            enemy_y = enemy.y + getattr(enemy, "h", 0) / 2
            dx = enemy_x - bullet.x
            dy = enemy_y - bullet.y
            distance = (dx * dx + dy * dy) ** 0.5

            # Preferir inimigos com menos tiros, em caso de empate escolher o mais próximo
            if count < min_count or (count == min_count and distance < min_distance):
                min_count = count
                min_distance = distance
                best_target = enemy

        return best_target

    def cleanup(self):
        # Liberar bullets dead ao pool
        for b in self.bullets:
            if b.dead:
                self.bullet_pool.release(b)
        self.bullets = [b for b in self.bullets if not b.dead]

        # Liberar meteoros dead ao pool
        for e in self.enemies:
            if isinstance(e, Meteor) and e.dead:
                self.meteor_pool.release(e)

        self.alien_bullets = [ab for ab in self.alien_bullets if not ab.dead]
        self.boss_lasers = [bl for bl in self.boss_lasers if not bl.dead]
        self.player_lasers = [pl for pl in self.player_lasers if not pl.dead]
        self.boss_squares = [bs for bs in self.boss_squares if not bs.dead]
        self.eye_lasers = [el for el in self.eye_lasers if not el.dead]
        self.mini_ship_bullets = [vb for vb in self.mini_ship_bullets if not vb.dead]
        self.enemies = [
            e
            for e in self.enemies
            if not e.dead and not (isinstance(e, ExplosiveMine) and e.is_off_screen())
        ]
        self.mine_explosions = [me for me in self.mine_explosions if not me.finished()]
        self.powerups = [p for p in self.powerups if not p.dead]
        self.stars = [s for s in self.stars if not s.dead]  # Limpar estrelas coletadas
        self.floating_scores = [fs for fs in self.floating_scores if not fs.is_dead()]
        self.formations = [
            f for f in self.formations if not f.dead
        ]  # Limpar formações mortas
        self.spikes = [s for s in self.spikes if not s.dead]  # Limpar spikes mortos
        self.air_strike_markers = [m for m in self.air_strike_markers if not m.dead]
        self.air_strike_bombs = [b for b in self.air_strike_bombs if not b.dead]

    def clear_all(self):
        self.bullets.clear()
        self.alien_bullets.clear()
        self.boss_lasers.clear()
        self.boss_squares.clear()
        self.eye_lasers.clear()
        self.powerups.clear()
        self.stars.clear()  # Limpar estrelas
        self.floating_scores.clear()
        self.enemies.clear()
        self.mine_explosions.clear()
        self.explosive_effects.clear()  # Limpar efeitos de explosão de área
        self.air_strike_markers.clear()  # Limpar marcadores de bombardeio
        self.air_strike_bombs.clear()  # Limpar bombas de bombardeio
        self.boss = None
        self.mini_ships.clear()
        self.mini_ship_bullets.clear()
        self.formations.clear()
        self.spikes.clear()
        self.meteor_pool.clear_active()  # Limpar meteoros ativos do pool
        self.bullet_pool.clear_active()  # Limpar balas ativas do pool
        self.explosion_pool.clear_active()  # Limpar explosões ativas do pool

    def clear_for_level_transition(self):
        """Limpa entidades para transição de fase, mas preserva balas do jogador."""
        # Balas do jogador são mantidas, mas limpamos as inativas do pool
        for bullet in self.bullets[:]:
            if bullet.dead:
                self.bullet_pool.release(bullet)
        self.bullets = [b for b in self.bullets if not b.dead]

        self.alien_bullets.clear()
        self.boss_lasers.clear()
        self.boss_squares.clear()
        self.eye_lasers.clear()
        self.floating_scores.clear()
        self.enemies.clear()
        self.mine_explosions.clear()
        self.boss = None
        self.formations.clear()
        self.meteor_pool.clear_active()  # Limpar meteoros ativos do pool
        # NÃO limpar bullet_pool aqui para manter balas do jogador
        self.explosion_pool.clear_active()  # Limpar explosões ativas do pool
        self.spikes.clear()
        self.air_strike_markers.clear()  # Limpar marcadores de bombardeio
        self.air_strike_bombs.clear()  # Limpar bombas de bombardeio

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas de performance para debug."""
        return {
            "bullets": len(self.bullets),
            "enemies": len(self.enemies),
            "formations": len(self.formations),
            "explosions_active": self.explosion_pool.get_stats()["active"],
            "grid_stats": self.enemy_spatial_grid.get_statistics(),
        }
