import random
from typing import TYPE_CHECKING, Any, Dict, Optional

import pygame

from ..core.spatial_grid import SpatialGrid
from ..core.upgrades_config import EMP_LINGER_DURATION
from ..entities.air_strike_bomb import AirStrikeBomb
from ..entities.alien import Alien
from ..entities.alien_bullet import AlienBullet
from ..entities.black_hole import BlackHole
from ..entities.boss import Boss
from ..entities.boss_laser import BossLaser
from ..entities.boss_square import BossSquare
from ..entities.bot_elemental import ElementalRobot, EnergyOrb
from ..entities.bullet import Bullet
from ..entities.bullet_pool import BulletPool
from ..entities.cannon_mine import CannonMine
from ..entities.cannon_tower import CannonTower
from ..entities.emp_wave import EMPWave
from ..entities.explosion import Explosion, ExplosionType  # ← ADICIONAR
from ..entities.explosion_pool import ExplosionPool
from ..entities.explosive_effect import ExplosiveEffect
from ..entities.explosive_mine import ExplosiveMine
from ..entities.eye_enemy import EyeEnemy
from ..entities.eye_laser import EyeLaser
from ..entities.floating_score import FloatingScore
from ..entities.formation import Formation
from ..entities.giant_meteor_boss import GiantMeteorBoss
from ..entities.guided_meteor import GuidedMeteor
from ..entities.meteor import Meteor
from ..entities.meteor_pool import MeteorPool
from ..entities.mine_explosion import MineExplosion
from ..entities.mini_ship import MiniShip
from ..entities.mini_ship_bullet import MiniShipBullet
from ..entities.player_laser import PlayerLaser
from ..entities.powerup import PowerUp
from ..entities.mountain_mage import MountainMage, MountainStalagmite
from ..entities.rock_glider import RockGlider
from ..entities.rock_glider_pool import RockGliderPool
from ..entities.slime_boss import SlimeBoss
from ..entities.slime_drip import SlimeDrip
from ..entities.spike import Spike
from ..entities.spike_boss import SpikeBoss
from ..entities.spike_boss_laser import SpikeBossLaser
from ..entities.square_minion_boss import SquareMinionBoss
from ..entities.star import Star
from ..entities.stone_golem_boss import (
    Boulder,
    EntryDebris,
    OrbitalRock,
    RockShard,
    StoneGolemBoss,
)
from ..entities.stone_sentry import StoneSentry

if TYPE_CHECKING:
    from ..entities.ship import Ship


class EntityManager:
    def __init__(
        self, sound_manager: Optional[Any] = None, is_side_scroll: bool = False
    ):
        self.sound_manager = sound_manager
        self.is_side_scroll = is_side_scroll  # NOVO: Modo de jogo
        self.bullets: list[Bullet] = []
        self.emp_waves: list[EMPWave] = []  # Ondas visuais do EMP
        self.energy_orbs: list[
            EnergyOrb
        ] = []  # Projéteis do ElementalRobot (mini-boss)
        self.explosive_effects: list[
            ExplosiveEffect
        ] = []  # Efeitos visuais de explosão de área
        self.enemies: list[
            Meteor
            | Alien
            | ExplosiveMine
            | EyeEnemy
            | SquareMinionBoss
            | ElementalRobot
            | StoneSentry
            | MountainMage
            | MountainStalagmite
        ] = []
        self.alien_bullets: list[AlienBullet] = []
        self.boss_lasers: list[BossLaser | SpikeBossLaser] = []
        self.player_lasers: list[PlayerLaser] = []  # Lasers do jogador
        self.boss_squares: list[BossSquare] = []  # Quadrados lançados pelo boss
        self.slime_drips: list["SlimeDrip"] = []  # Gotas de slime do SlimeBoss
        self.eye_lasers: list[EyeLaser] = []
        self.mine_explosions: list[MineExplosion] = []
        self.powerups: list[PowerUp] = []
        self.stars: list[Star] = []  # Estrelas coletáveis
        self.floating_scores: list[FloatingScore] = []
        self.boss: (
            Boss | SpikeBoss | SlimeBoss | GiantMeteorBoss | StoneGolemBoss | None
        ) = None
        self.mini_ships: list[MiniShip] = []
        self.mini_ship_bullets: list[MiniShipBullet] = []
        self.formations: list[Formation] = []  # Nova lista para formações
        self.spikes: list[Spike] = []  # Lista para espinhos do SpikeBoss
        self.boulders: list[Boulder] = []  # Pedregulhos do StoneGolemBoss
        self.rock_shards: list[RockShard] = []  # Fragmentos de pedra do StoneGolemBoss
        self.orbital_rocks: list[OrbitalRock] = []  # Pedras orbitais do StoneGolemBoss
        self._grid_needs_rebuild = True
        self._cached_formation_enemies: list[Any] = []
        self._cached_all_enemies: list[Any] = []
        self.air_strike_bombs: list[AirStrikeBomb] = []  # Bombas do bombardeio aéreo
        self.cannon_towers: list[CannonTower] = []  # Torres de canhão
        self.cannon_mines: list[CannonMine] = []  # Minas das torres
        self.black_holes: list[BlackHole] = []  # Buracos negros
        self.meteor_pool = MeteorPool(
            initial_size=100, is_side_scroll=is_side_scroll
        )  # Pool de meteoros
        self.rock_glider_pool = RockGliderPool(
            initial_size=24, is_side_scroll=is_side_scroll
        )  # Pool de rock gliders
        self.bullet_pool = BulletPool(initial_size=50)  # Pool de balas
        self.enemy_spatial_grid: SpatialGrid[
            Meteor
            | Alien
            | ExplosiveMine
            | EyeEnemy
            | SquareMinionBoss
            | ElementalRobot
            | StoneSentry
            | MountainMage
            | MountainStalagmite
            | Boulder
            | RockShard
            | OrbitalRock
            | EntryDebris
        ] = SpatialGrid()  # Grid espacial para inimigos
        self.spike_spatial_grid: SpatialGrid[Spike] = (
            SpatialGrid()
        )  # OPT: Grid para spikes
        self.explosion_pool = ExplosionPool(initial_size=50)  # Pool de explosões

    @property
    def eye_enemy_count(self) -> int:
        return sum(1 for e in self.enemies if isinstance(e, EyeEnemy))

    def spawn_explosion(
        self,
        x: float,
        y: float,
        size: int = 30,
        explosion_type: list[tuple[int, int, int]] | None = None,
    ) -> Explosion:
        """
        Spawna uma explosão usando o pool.

        Args:
            x, y: Posição da explosão
            size: Tamanho da explosão
            explosion_type: Tipo de explosão (ExplosionType.ALIEN, ExplosionType.SLIME, None para padrão)

        Returns:
            Explosão criada ou reutilizada do pool
        """
        return self.explosion_pool.get(x, y, size, explosion_type)

    def trigger_slime_boss_death(self, boss: SlimeBoss) -> None:
        """Spawn a dramatic multi-explosion sequence for the Slime Boss death."""

        cx = boss.x + boss.w / 2
        cy = boss.y + boss.h / 2

        # Central blast
        self.spawn_explosion(
            cx, cy, size=140, explosion_type=ExplosionType.SLIME
        )  # ← ATUALIZAR

        # Large clustered blasts across the body
        for _ in range(12):
            ex = random.uniform(boss.x + boss.w * 0.1, boss.x + boss.w * 0.9)
            ey = random.uniform(boss.y + boss.h * 0.15, boss.y + boss.h * 0.85)
            size = random.randint(70, 120)
            self.spawn_explosion(
                ex, ey, size=size, explosion_type=ExplosionType.SLIME
            )  # ← ATUALIZAR

        # Smaller follow-up blasts for lingering effect
        for _ in range(8):
            ex = random.uniform(boss.x, boss.x + boss.w)
            ey = random.uniform(boss.y, boss.y + boss.h)
            size = random.randint(40, 70)
            self.spawn_explosion(
                ex, ey, size=size, explosion_type=ExplosionType.SLIME
            )  # ← ATUALIZAR

    def spawn_emp_wave(self, center_x: float, center_y: float) -> None:
        """Spawna uma onda visual de EMP."""
        self.emp_waves.append(EMPWave(center_x, center_y))

    def spawn_explosive_effect(self, x: float, y: float, radius: float = 60.0) -> None:
        """Spawna um efeito visual de explosão de área (círculo branco semi-transparente)."""
        self.explosive_effects.append(ExplosiveEffect(x, y, radius=radius))

    def spawn_air_strike(self, target_x: float, target_y: float) -> None:
        """Spawna uma bomba para o bombardeio aéreo."""
        # Validar que o alvo está dentro da tela
        screen = pygame.display.get_surface()
        screen_width = screen.get_width() if screen else 1600
        screen_height = screen.get_height() if screen else 900

        clamped_target_x = max(40, min(screen_width - 40, target_x))
        clamped_target_y = max(60, min(screen_height - 40, target_y))

        # Criar a bomba diretamente
        self.spawn_air_strike_bomb(clamped_target_x, clamped_target_y)

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

    def spawn_black_hole(self, x: float, y: float, duration: float) -> None:
        """Spawna um buraco negro."""
        black_hole = BlackHole(
            x,
            y,
            duration,
            is_side_scroll=self.is_side_scroll,
        )
        self.black_holes.append(black_hole)

    def spawn_cannon_tower(self, x: float, y: float) -> None:
        """Spawna uma torre de canhão."""
        tower = CannonTower(x, y)  # Criar sem callback primeiro

        # Definir callback agora que temos a torre
        def on_fire_mine(target_x: float, target_y: float) -> None:
            self._spawn_cannon_mine(
                x + 30, y, target_x, target_y, tower
            )  # Centro da torre

        tower.on_fire_mine = on_fire_mine  # Atribuir callback
        self.cannon_towers.append(tower)

    def _spawn_cannon_mine(
        self,
        launch_x: float,
        launch_y: float,
        target_x: float,
        target_y: float,
        tower: CannonTower,
    ) -> None:
        """Spawna uma mina de canhão."""
        # Callback para som de explosão
        on_explode = None
        if self.sound_manager:
            on_explode = self.sound_manager.play_explosion_asteroid

        mine = CannonMine(target_x, target_y, launch_x, launch_y, on_explode=on_explode)
        self.cannon_mines.append(mine)
        tower.register_mine(mine)  # Registrar mina na torre

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
            x,
            y,
            target_x,
            target_y,
            damage=damage,
            ship=ship,
            ball_index=ball_index,
            target_entity=target_entity,
        )
        self.player_lasers.append(laser)
        return laser

    def rebuild_all_grids(self):
        """OPT #1: Reconstrói todas as grids espaciais (inimigos + spikes)."""
        if not self._grid_needs_rebuild:
            return

        # Grid de inimigos normais + formações
        self.enemy_spatial_grid.clear()

        # Inserir inimigos normais
        for enemy in self.enemies:
            self.enemy_spatial_grid.insert_from_rect(enemy)

        # Inserir minas do StoneGolemBoss (agora destrutíveis)
        for mine in self.boulders:
            if not mine.dead:
                self.enemy_spatial_grid.insert_from_rect(mine)

        # Inserir fragmentos de pedra do StoneGolemBoss
        for shard in self.rock_shards:
            if not shard.dead:
                self.enemy_spatial_grid.insert_from_rect(shard)

        # Inserir pedras orbitais APENAS quando podem causar dano (fase fired)
        for orbital_rock in self.orbital_rocks:
            if not orbital_rock.dead and getattr(orbital_rock, "causes_damage", False):
                self.enemy_spatial_grid.insert_from_rect(orbital_rock)

        # Inserir detritos de entrada do StoneGolemBoss
        if isinstance(self.boss, StoneGolemBoss):
            for debris in self.boss.entry_debris:
                if not debris.dead:
                    self.enemy_spatial_grid.insert_from_rect(debris)

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

        self._grid_needs_rebuild = False

    def _check_alien_collisions(self):
        """Verifica colisões entre aliens e inverte suas direções."""
        # Coletar apenas aliens vivos e não controlados por formação
        aliens = [
            e
            for e in self.enemies
            if isinstance(e, Alien) and not e.dead and not e.formation_controlled
        ]

        # Verificar colisões entre pares de aliens
        for i in range(len(aliens)):
            for j in range(i + 1, len(aliens)):
                alien1 = aliens[i]
                alien2 = aliens[j]

                # Verificar se os retângulos colidem
                if alien1.rect.colliderect(alien2.rect):
                    # Inverter direções horizontais de ambos
                    alien1.speed_x *= -1
                    alien2.speed_x *= -1

                    # Separar aliens ligeiramente para evitar colisão contínua
                    overlap_x = (alien1.w + alien2.w) / 2 - abs(alien1.x - alien2.x)
                    if overlap_x > 0:
                        if alien1.x < alien2.x:
                            alien1.x -= overlap_x / 2
                            alien2.x += overlap_x / 2
                        else:
                            alien1.x += overlap_x / 2
                            alien2.x -= overlap_x / 2

    def update(
        self,
        dt: float,
        player_x: float,
        player_y: float,
        freeze_enemies: bool = False,
        screen_width: int = 1600,
        screen_height: int = 900,
    ):
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
                    setattr(entity, "emp_linger_timer", float(EMP_LINGER_DURATION))
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
            # SlimeBoss só tem ataque de drip interno, não spawna entidades externas
            elif isinstance(self.boss, SlimeBoss):
                self.boss.update(enemy_dt, player_x, player_y, self)
            # GiantMeteorBoss apenas atualiza posição (queda lenta)
            elif isinstance(self.boss, GiantMeteorBoss):
                self.boss.update(enemy_dt, self)
            # StoneGolemBoss retorna (List[Boulder], List[RockShard], List[OrbitalRock])
            elif isinstance(self.boss, StoneGolemBoss):
                new_boulders, new_shards, orbital_rocks = self.boss.update(
                    enemy_dt, player_x, player_y, self
                )
                if new_boulders:
                    self.boulders.extend(new_boulders)
                if new_shards:
                    self.rock_shards.extend(new_shards)
                # Sincroniza a lista de pedras orbitais (gerenciada pelo boss)
                self.orbital_rocks = orbital_rocks
            # Boss normal retorna (List[BossLaser], List[BossSquare])
            else:  # isinstance(self.boss, Boss)
                lasers_fired, spawned_squares = self.boss.update(
                    enemy_dt, player_x, player_y
                )
                if lasers_fired:
                    self.boss_lasers.extend(lasers_fired)
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
                enemy.update(scaled_dt, self.is_side_scroll, player_x, player_y)
            elif isinstance(enemy, SquareMinionBoss):
                enemy.update(scaled_dt, screen_width, screen_height)
            elif isinstance(enemy, ElementalRobot):
                # Mini-boss: update recebe dt real + enemy_dt (EMP) + posição do jogador
                new_orbs = enemy.update(dt, scaled_dt, player_x, player_y)
                if new_orbs:
                    self.energy_orbs.extend(new_orbs)
            elif isinstance(enemy, StoneSentry):
                shot = enemy.update(scaled_dt, (player_x, player_y), self.enemies)
                if shot:
                    new_alien_bullets.extend(shot)
            elif isinstance(enemy, MountainMage):
                new_stalagmites = enemy.update(scaled_dt, (player_x, player_y))
                if new_stalagmites:
                    self.enemies.extend(new_stalagmites)
            else:
                enemy.update(scaled_dt)

        # Atualizar Energy Orbs (projéteis do ElementalRobot)
        for orb in self.energy_orbs:
            orb.update(dt)

        # Verificar colisões entre aliens
        self._check_alien_collisions()

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

        # Atualizar minas do StoneGolemBoss (GolemMine.update retorna shards da explosão)
        for mine in self.boulders:
            explosion_shards = mine.update(dt)
            if explosion_shards:
                self.rock_shards.extend(explosion_shards)

        # Atualizar rock shards do StoneGolemBoss
        for shard in self.rock_shards:
            shard.update(dt)

        # Atualizar pedras orbitais do StoneGolemBoss (o boss já faz o update
        # interno; aqui apenas garantimos que a lista local está sincronizada)
        # Nada a fazer: self.orbital_rocks é referência à lista interna do boss

        # Atualizar bombas de bombardeio aéreo
        for bomb in self.air_strike_bombs[:]:
            bomb.update(enemy_dt)
            if bomb.dead:
                self.air_strike_bombs.remove(bomb)

        # Atualizar torres de canhão
        for tower in self.cannon_towers[:]:
            tower.update(enemy_dt)
            if tower.dead:
                self.cannon_towers.remove(tower)

        # Atualizar minas das torres
        for mine in self.cannon_mines[:]:
            mine.update(enemy_dt)
            if mine.dead:
                self.cannon_mines.remove(mine)

        # Atualizar buracos negros
        for black_hole in self.black_holes[:]:
            black_hole.update(dt)
            if black_hole.dead:
                self.black_holes.remove(black_hole)

        # Aplicar gravidade dos black holes
        # Cada black hole processa todos os inimigos de uma vez (mais eficiente)
        for black_hole in self.black_holes:
            black_hole.process_all_enemies(
                self._cached_all_enemies,
                enemy_dt,
                spawn_explosion_callback=self.spawn_explosion,
            )

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
            self.cannon_towers,  # Include cannon towers
            self.cannon_mines,  # Include cannon mines
        ]

        # Update all entities in a generic way, handling specific types
        for entity_list in entity_groups:
            for entity in entity_list:
                if isinstance(entity, (EyeEnemy, GuidedMeteor, ElementalRobot)):
                    if isinstance(entity, GuidedMeteor):
                        entity.update(dt, self.is_side_scroll, player_x, player_y)
                    elif isinstance(entity, ElementalRobot):
                        # ElementalRobot no Game Over: usamos dt para ambos os tempos
                        entity.update(dt, dt, player_x, player_y)
                    else:  # EyeEnemy
                        entity.update(dt, player_x, player_y)
                elif isinstance(entity, MiniShip):
                    # MiniShip.update expects enemy_list and bullet_list,
                    # but during game over slow-mo, they might not need complex interactions
                    entity.update(dt, [], [])
                elif isinstance(entity, Meteor):
                    # Meteor.update precisa saber o modo de jogo
                    entity.update(dt, self.is_side_scroll)
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
            elif isinstance(self.boss, SlimeBoss):
                self.boss.update(dt, player_x, player_y)
            elif isinstance(self.boss, GiantMeteorBoss):
                self.boss.update(dt, self)
            elif isinstance(self.boss, StoneGolemBoss):
                new_boulders, new_shards, orbital_rocks = self.boss.update(
                    dt, player_x, player_y, self
                )
                if new_boulders:
                    self.boulders.extend(new_boulders)
                if new_shards:
                    self.rock_shards.extend(new_shards)
                self.orbital_rocks = orbital_rocks
            else:  # General Boss type
                lasers_fired, spawned_squares = self.boss.update(dt, player_x, player_y)
                if lasers_fired:
                    self.boss_lasers.extend(lasers_fired)
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
        fps: float = 60.0,
    ):
        """Desenha todas as entidades com a profundidade correta."""
        screen_rect = surface.get_rect()

        def is_visible(entity: Any) -> bool:
            rect = getattr(entity, "rect", None)
            if rect is not None:
                return rect.colliderect(screen_rect)

            x = getattr(entity, "x", None)
            y = getattr(entity, "y", None)
            w = getattr(entity, "w", None)
            h = getattr(entity, "h", None)
            if x is None or y is None or w is None or h is None:
                return True

            return pygame.Rect(int(x), int(y), int(w), int(h)).colliderect(screen_rect)

        # 1. Primeiro desenhamos os inimigos (base/fundo)
        if enemy_visible:
            # Meteoros do pool (fluxo contínuo)
            self.meteor_pool.draw(surface)

            # Inimigos comuns e mini-bosses (como o ElementalRobot)
            for enemy in self.enemies:
                # Estalagmites com fragmentos ativos sempre devem ser desenhadas
                if isinstance(enemy, MountainStalagmite) and getattr(enemy, "_fragments", None):
                    enemy.draw(surface)
                    continue
                if not is_visible(enemy):
                    continue
                if isinstance(enemy, EyeEnemy):
                    enemy.draw(surface, player_x, player_y)
                else:
                    enemy.draw(surface)

            # Formações de inimigos
            for formation in self.formations:
                if not is_visible(formation):
                    continue
                formation.draw(surface)

        # 2. Desenhar o Boss (logo acima dos inimigos comuns)
        if self.boss:
            if isinstance(self.boss, SlimeBoss):
                self.boss.draw(surface, fps)
            else:
                self.boss.draw(surface)

        # 3. Desenhar perigos ambientais e lasers de área
        for laser in self.boss_lasers:
            laser.draw(surface)
        for black_hole in self.black_holes:
            black_hole.draw(surface)
        for wave in self.emp_waves:
            wave.draw(surface)

        # 4. Desenhar projéteis e efeitos de impacto (devem ficar SOBRE os inimigos)
        entity_lists: list[list[Any]] = [
            self.bullets,
            self.alien_bullets,
            self.energy_orbs,
            self.player_lasers,
            self.mini_ship_bullets,
            self.eye_lasers,
            self.boss_squares,
            self.powerups,
            self.stars,
            self.floating_scores,
            self.mini_ships,
            self.spikes,
            self.mine_explosions,
            self.air_strike_bombs,
            self.cannon_mines,
            self.cannon_towers,
            self.boulders,
            self.rock_shards,
        ]

        for entity_list in entity_lists:
            for entity in entity_list:
                if not is_visible(entity):
                    continue
                entity.draw(surface)

        # 5. Efeitos visuais de explosão (no topo de tudo)
        self.explosion_pool.draw_all(surface)
        for effect in self.explosive_effects:
            effect.draw(surface)

    def spawn_elemental_robot(
        self,
        x: float | None = None,
        y: float | None = None,
        difficulty_multiplier: float = 1.0,
        start_visible: bool = False,
    ) -> ElementalRobot:
        """
        Spawna um ElementalRobot (mini-boss) na posição indicada.

        Args:
            x: Posição horizontal (padrão: centro da tela)
            y: Posição vertical de parada (padrão: 15% da altura)
            difficulty_multiplier: Não afeta o HP (fixo em 25 hits), reservado
                                   para uso futuro (ex: velocidade de disparo).

        Returns:
            ElementalRobot criado e adicionado à lista de inimigos.
        """
        screen = pygame.display.get_surface()
        sw = screen.get_width() if screen else 1600
        sh = screen.get_height() if screen else 900

        spawn_x = x if x is not None else sw / 2 - 72  # centralizado na tela
        spawn_y = y if y is not None else sh * 0.15  # 15% do topo

        robot = ElementalRobot(
            spawn_x,
            spawn_y,
            difficulty_multiplier=difficulty_multiplier,
            start_visible=start_visible,
        )
        self.enemies.append(robot)
        return robot

    def spawn_meteor(
        self,
        size: int | None = None,
        x: float | None = None,
        y: float | None = None,
        vx: float | None = None,
        vy: float | None = None,
        behind: bool = False,
    ) -> Meteor:
        """
        Spawna um meteoro usando o pool.

        Args:
            size, x, y, vx, vy: Parâmetros de configuração do meteoro
            behind: Se True, insere no início da lista (atrás de outros inimigos)

        Returns:
            Meteoro criado ou reutilizado do pool
        """
        meteor = self.meteor_pool.get(size=size, x=x, y=y, vx=vx, vy=vy)
        if behind:
            self.enemies.insert(0, meteor)
        else:
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
            is_side_scroll=self.is_side_scroll,
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

    def _is_enemy_off_screen(self, enemy: Any) -> bool:
        """
        Verifica se um inimigo está fora da tela.

        Em top-down: sai pela parte inferior (y > screen_height)
        Em side-scroll: sai pela parte esquerda (x < -width)
        """
        # Obter largura do inimigo de forma segura
        enemy_width = getattr(enemy, "w", None)
        if enemy_width is None:
            # Tentar rect.width se .w não existir
            rect = getattr(enemy, "rect", None)
            if rect is not None:
                enemy_width = getattr(rect, "width", 50)  # Default 50 se não encontrar
            else:
                enemy_width = 50  # Fallback para largura padrão

        # Obter altura do inimigo de forma segura
        enemy_height = getattr(enemy, "h", None)
        if enemy_height is None:
            rect = getattr(enemy, "rect", None)
            if rect is not None:
                enemy_height = getattr(rect, "height", 50)
            else:
                enemy_height = 50

        if self.is_side_scroll:
            # Side-scroll: inimigos saem pela esquerda, por cima ou por baixo
            screen = pygame.display.get_surface()
            screen_height = screen.get_height() if screen else 900
            return (
                enemy.x < -enemy_width
                or enemy.y < -enemy_height
                or enemy.y > screen_height
            )
        else:
            # Top-down: inimigos saem pela parte inferior (ou pela lateral/superior)
            screen = pygame.display.get_surface()
            screen_height = screen.get_height() if screen else 900
            screen_width = screen.get_width() if screen else 1600

            return (
                enemy.y > screen_height
                or enemy.x < -enemy_width
                or enemy.x > screen_width
            )

    def cleanup(self):
        # Liberar bullets dead ao pool
        for b in self.bullets:
            if b.dead:
                self.bullet_pool.release(b)
        self.bullets = [b for b in self.bullets if not b.dead]

        # Marcar inimigos fora da tela como mortos ANTES de liberar ao pool
        for e in self.enemies:
            if not e.dead and self._is_enemy_off_screen(e):
                e.dead = True

        # Liberar meteoros dead ao pool
        for e in self.enemies:
            if isinstance(e, Meteor) and e.dead:
                self.meteor_pool.release(e)
            elif isinstance(e, RockGlider) and e.dead:
                self.rock_glider_pool.release(e)

        self.alien_bullets = [ab for ab in self.alien_bullets if not ab.dead]
        self.energy_orbs = [orb for orb in self.energy_orbs if not orb.dead]
        self.boss_lasers = [bl for bl in self.boss_lasers if not bl.dead]
        self.player_lasers = [pl for pl in self.player_lasers if not pl.dead]
        self.boss_squares = [bs for bs in self.boss_squares if not bs.dead]
        self.slime_drips = [sd for sd in self.slime_drips if not sd.dead]
        self.eye_lasers = [el for el in self.eye_lasers if not el.dead]
        self.mini_ship_bullets = [vb for vb in self.mini_ship_bullets if not vb.dead]
        self.enemies = [
            e
            for e in self.enemies
            if not (
                e.dead
                and not (
                    isinstance(e, MountainStalagmite)
                    and getattr(e, "_fragments", None)
                )
            )
            and not (isinstance(e, ExplosiveMine) and e.is_off_screen())
        ]
        self.mine_explosions = [me for me in self.mine_explosions if not me.finished()]
        self.powerups = [p for p in self.powerups if not p.dead]
        self.stars = [s for s in self.stars if not s.dead]  # Limpar estrelas coletadas
        self.floating_scores = [fs for fs in self.floating_scores if not fs.is_dead()]
        self.formations = [
            f for f in self.formations if not f.dead
        ]  # Limpar formações mortas
        self.spikes = [s for s in self.spikes if not s.dead]  # Limpar spikes mortos
        self.air_strike_bombs = [b for b in self.air_strike_bombs if not b.dead]
        self.cannon_towers = [
            t for t in self.cannon_towers if not t.dead
        ]  # Limpar torres mortas
        self.cannon_mines = [
            m for m in self.cannon_mines if not m.dead
        ]  # Limpar minas mortas
        self.boulders = [
            b for b in self.boulders if not b.dead
        ]  # Limpar boulders mortos
        self.rock_shards = [
            s for s in self.rock_shards if not s.dead
        ]  # Limpar shards mortos
        # orbital_rocks é gerenciada pelo boss — apenas filtra as mortas da cópia local
        self.orbital_rocks = [r for r in self.orbital_rocks if not r.dead]
        self._grid_needs_rebuild = True

    def clear_all(self):
        self.bullets.clear()
        self.alien_bullets.clear()
        self.energy_orbs.clear()  # Limpar orbs do ElementalRobot
        self.boss_lasers.clear()
        self.boss_squares.clear()
        self.slime_drips.clear()
        self.eye_lasers.clear()
        self.powerups.clear()
        self.stars.clear()  # Limpar estrelas
        self.floating_scores.clear()
        self.enemies.clear()
        self.mine_explosions.clear()
        self.explosive_effects.clear()  # Limpar efeitos de explosão de área
        self.air_strike_bombs.clear()  # Limpar bombas de bombardeio
        self.cannon_towers.clear()  # Limpar torres de canhão
        self.cannon_mines.clear()  # Limpar minas das torres
        self.boss = None
        self.mini_ships.clear()
        self.mini_ship_bullets.clear()
        self.formations.clear()
        self.spikes.clear()
        self.meteor_pool.clear_active()  # Limpar meteoros ativos do pool
        self.rock_glider_pool.clear_active()  # Limpar rock gliders ativos do pool
        self.bullet_pool.clear_active()  # Limpar balas ativas do pool
        self.explosion_pool.clear_active()  # Limpar explosões ativas do pool

    def clear_for_level_transition(self):
        """Limpa entidades para transição de fase, mas preserva balas do jogador e torres de upgrades."""
        # Balas do jogador são mantidas, mas limpamos as inativas do pool
        for bullet in self.bullets[:]:
            if bullet.dead:
                self.bullet_pool.release(bullet)
        self.bullets = [b for b in self.bullets if not b.dead]

        self.alien_bullets.clear()
        self.energy_orbs.clear()  # Limpar orbs do ElementalRobot na transição
        self.boss_squares.clear()
        self.eye_lasers.clear()
        self.floating_scores.clear()
        self.enemies.clear()
        self.mine_explosions.clear()
        self.boss = None
        self.formations.clear()
        self.meteor_pool.clear_active()  # Limpar meteoros ativos do pool
        self.rock_glider_pool.clear_active()  # Limpar rock gliders ativos do pool
        # NÃO limpar bullet_pool aqui para manter balas do jogador
        self.explosion_pool.clear_active()  # Limpar explosões ativas do pool
        self.spikes.clear()
        self.air_strike_bombs.clear()  # Limpar bombas de bombardeio

        # PRESERVAR torres e minas de upgrades ativos:
        # Torres de canhão são mantidas pois fazem parte do sistema de upgrades
        # Minas ativas das torres também são preservadas para continuidade
        # self.cannon_towers.clear()  # REMOVIDO - preservar torres de upgrade
        # self.cannon_mines.clear()   # REMOVIDO - preservar minas ativas

        # Apenas limpar minas mortas e torres mortas (cleanup normal)
        self.cannon_towers = [tower for tower in self.cannon_towers if not tower.dead]
        self.cannon_mines = [mine for mine in self.cannon_mines if not mine.dead]

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas de performance para debug."""
        return {
            "bullets": len(self.bullets),
            "enemies": len(self.enemies),
            "formations": len(self.formations),
            "explosions_active": self.explosion_pool.get_stats()["active"],
            "grid_stats": self.enemy_spatial_grid.get_statistics(),
        }
