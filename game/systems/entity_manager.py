import random
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

import pygame

from ..core.config import config as Config
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
from ..entities.cloud_archmage_boss import CloudArchmageBoss
from ..entities.emp_wave import EMPWave
from ..entities.explosion import Explosion, ExplosionType
from ..entities.explosion_pool import ExplosionPool
from ..entities.explosive_effect import ExplosiveEffect
from ..entities.explosive_mine import ExplosiveMine
from ..entities.eye_enemy import EyeEnemy
from ..entities.eye_laser import EyeLaser
from ..entities.fire_zone import FireZone
from ..entities.floating_score import FloatingScore
from ..entities.formation import Formation
from ..entities.giant_meteor_boss import GiantMeteorBoss
from ..entities.guided_meteor import GuidedMeteor
from ..entities.homing_bullet import HomingBullet
from ..entities.ice_poison_zone import IcePoisonZone
from ..entities.meteor import Meteor
from ..entities.meteor_pool import MeteorPool
from ..entities.mine_explosion import MineExplosion
from ..entities.mini_ship import MiniShip
from ..entities.mini_ship_bullet import MiniShipBullet
from ..entities.mountain_mage import (MountainMage, MountainStalactite,
                                      MountainStalagmite)
from ..entities.mountain_propeller import MountainPropeller
from ..entities.mountain_serpent_boss import (MountainSerpentBoss,
                                              SerpentBlock, SerpentRockBullet)
from ..entities.player_laser import PlayerLaser
from ..entities.powerup import PowerUp
from ..entities.rock_glider import RockGlider
from ..entities.rock_glider_pool import RockGliderPool
from ..entities.slime_boss import SlimeBoss
from ..entities.slime_drip import SlimeDrip
from ..entities.spike import Spike
from ..entities.spike_boss import SpikeBoss
from ..entities.spike_boss_laser import SpikeBossLaser
from ..entities.square_minion_boss import SquareMinionBoss
from ..entities.star import Star
from ..entities.stone_golem_boss import (AttackDebris, EmergeDebris, GolemMine,
                                         OrbitalDebris, StoneGolemBoss)
from ..entities.stone_sentry import StoneSentry
from .collision_protocols import Removable

if TYPE_CHECKING:
    from ..entities.ship import Ship


class EntityManager:
    """Gerencia todas as entidades do jogo, coordenando update, draw e cleanup."""

    def __init__(
        self, sound_manager: Optional[Any] = None, is_side_scroll: bool = False
    ) -> None:
        self.sound_manager = sound_manager
        self.is_side_scroll = is_side_scroll

        # Listas de projéteis e efeitos
        self.bullets: List[Bullet] = []
        self.homing_bullets: List[HomingBullet] = []
        self.emp_waves: List[EMPWave] = []
        self.energy_orbs: List[EnergyOrb] = []
        self.explosive_effects: List[ExplosiveEffect] = []
        self.alien_bullets: List[AlienBullet] = []
        self.serpent_bullets: List[SerpentRockBullet] = []
        self.boss_lasers: List[Union[BossLaser, SpikeBossLaser]] = []
        self.player_lasers: List[PlayerLaser] = []
        self.cacador_lasers: List[BossLaser] = []
        self.boss_squares: List[BossSquare] = []
        self.slime_drips: List[SlimeDrip] = []
        self.eye_lasers: List[EyeLaser] = []
        self.mine_explosions: List[MineExplosion] = []
        self.ice_poison_zones: List[IcePoisonZone] = []
        self.fire_zones: List[FireZone] = []
        self.mini_ship_bullets: List[MiniShipBullet] = []

        # Listas de entidades e coletáveis
        self.enemies: List[Any] = []
        self.powerups: List[PowerUp] = []
        self.stars: List[Star] = []
        self.floating_scores: List[FloatingScore] = []

        self.boss: Optional[
            Union[
                Boss,
                SpikeBoss,
                SlimeBoss,
                GiantMeteorBoss,
                StoneGolemBoss,
                MountainSerpentBoss,
                CloudArchmageBoss,
            ]
        ] = None

        self.mini_ships: List[MiniShip] = []
        self.formations: List[Formation] = []
        self.mountain_propellers: List[MountainPropeller] = []
        self.spikes: List[Spike] = []
        self.boulders: List[GolemMine] = []
        self.attack_debris: List[AttackDebris] = []
        self.orbital_debris: List[OrbitalDebris] = []
        self.air_strike_bombs: List[AirStrikeBomb] = []
        self.cannon_towers: List[CannonTower] = []
        self.cannon_mines: List[CannonMine] = []
        self.black_holes: List[BlackHole] = []

        # Pools de performance
        self.meteor_pool = MeteorPool(initial_size=100, is_side_scroll=is_side_scroll)
        self.rock_glider_pool = RockGliderPool(
            initial_size=24, is_side_scroll=is_side_scroll
        )
        self.bullet_pool = BulletPool(initial_size=50)
        self.explosion_pool = ExplosionPool(initial_size=50)

        # Grids espaciais
        self.enemy_spatial_grid: SpatialGrid[
            Union[
                Meteor,
                Alien,
                ExplosiveMine,
                EyeEnemy,
                SquareMinionBoss,
                ElementalRobot,
                StoneSentry,
                MountainMage,
                MountainStalagmite,
                MountainStalactite,
                MountainPropeller,
                SerpentBlock,
                GolemMine,
                AttackDebris,
                OrbitalDebris,
                EmergeDebris,
            ]
        ] = SpatialGrid()
        self.spike_spatial_grid: SpatialGrid[Spike] = SpatialGrid()

        # Estado interno
        self._grid_needs_rebuild = True
        self._cached_formation_enemies: List[Any] = []
        self._cached_all_enemies: List[Any] = []

    @property
    def eye_enemy_count(self) -> int:
        return sum(1 for e in self.enemies if isinstance(e, EyeEnemy))

    def spawn_explosion(
        self,
        x: float,
        y: float,
        size: int = 30,
        explosion_type: Optional[List[tuple[int, int, int]]] = None,
    ) -> Explosion:
        return self.explosion_pool.get(x, y, size, explosion_type)

    def absorb_fragments(self, fragments: tuple[Any, ...]) -> None:
        """Materializa fragments oriundos de HitResult.

        MeteorSpec → meteor_pool.get; entidades já alocadas → enemies.append.
        Mantém o pool isolado das entidades (estas só geram specs).
        """
        if not fragments:
            return
        from .hit_result import MeteorSpec

        for spec in fragments:
            if isinstance(spec, MeteorSpec):
                meteor = self.meteor_pool.get(
                    size=spec.size, x=spec.x, y=spec.y, vx=spec.vx, vy=spec.vy
                )
                self.enemies.append(meteor)
            else:
                self.enemies.append(spec)

    def trigger_death_sequence(self, target: Any) -> None:
        """Dispara cinemáticas de morte específicas (ex.: SlimeBoss)."""
        if isinstance(target, SlimeBoss):
            self.trigger_slime_boss_death(target)

    def trigger_slime_boss_death(self, boss: SlimeBoss) -> None:
        cx, cy = boss.x + boss.w / 2, boss.y + boss.h / 2
        self.spawn_explosion(cx, cy, size=140, explosion_type=ExplosionType.SLIME)
        for _ in range(12):
            ex = random.uniform(boss.x + boss.w * 0.1, boss.x + boss.w * 0.9)
            ey = random.uniform(boss.y + boss.h * 0.15, boss.y + boss.h * 0.85)
            self.spawn_explosion(
                ex, ey, size=random.randint(70, 120), explosion_type=ExplosionType.SLIME
            )
        for _ in range(8):
            ex = random.uniform(boss.x, boss.x + boss.w)
            ey = random.uniform(boss.y, boss.y + boss.h)
            self.spawn_explosion(
                ex, ey, size=random.randint(40, 70), explosion_type=ExplosionType.SLIME
            )

    def spawn_emp_wave(self, center_x: float, center_y: float) -> None:
        self.emp_waves.append(EMPWave(center_x, center_y))

    def spawn_explosive_effect(self, x: float, y: float, radius: float = 60.0) -> None:
        self.explosive_effects.append(ExplosiveEffect(x, y, radius=radius))

    def spawn_ice_poison_zone(
        self, x: float, y: float, radius: int, duration: float = 5.0
    ) -> None:
        self.ice_poison_zones.append(IcePoisonZone(x, y, radius, duration))

    def spawn_air_strike(self, target_x: float, target_y: float) -> None:
        screen = pygame.display.get_surface()
        sw, sh = screen.get_size() if screen else (1600, 900)
        tx = max(40, min(sw - 40, target_x))
        ty = max(60, min(sh - 40, target_y))
        self.spawn_air_strike_bomb(tx, ty)

    def spawn_air_strike_bomb(self, target_x: float, target_y: float) -> None:
        on_explode = (
            self.sound_manager.play_explosion_asteroid if self.sound_manager else None
        )
        on_fall = self.sound_manager.play_meteor_rain if self.sound_manager else None
        self.air_strike_bombs.append(
            AirStrikeBomb(target_x, target_y, on_explode=on_explode, on_fall=on_fall)
        )

    def spawn_black_hole(self, x: float, y: float, duration: float) -> None:
        self.black_holes.append(
            BlackHole(x, y, duration, is_side_scroll=self.is_side_scroll)
        )

    def spawn_cannon_tower(self, x: float, y: float) -> None:
        tower = CannonTower(x, y)

        def on_fire_mine(tx: float, ty: float) -> None:
            self._spawn_cannon_mine(x + 30, y, tx, ty, tower)

        tower.on_fire_mine = on_fire_mine
        self.cannon_towers.append(tower)

    def _spawn_cannon_mine(
        self, lx: float, ly: float, tx: float, ty: float, tower: CannonTower
    ) -> None:
        on_explode = (
            self.sound_manager.play_explosion_asteroid if self.sound_manager else None
        )
        mine = CannonMine(tx, ty, lx, ly, on_explode=on_explode)
        self.cannon_mines.append(mine)
        tower.register_mine(mine)

    def spawn_player_laser(
        self,
        x: float,
        y: float,
        tx: float,
        ty: float,
        damage: int = PlayerLaser.DAMAGE,
        ship: Optional["Ship"] = None,
        ball_index: int = -1,
        target_entity: Optional[Any] = None,
    ) -> PlayerLaser:
        laser = PlayerLaser(
            x,
            y,
            tx,
            ty,
            damage=damage,
            ship=ship,
            ball_index=ball_index,
            target_entity=target_entity,
        )
        self.player_lasers.append(laser)
        return laser

    def spawn_cacador_laser(
        self,
        x: float,
        y: float,
        direction: tuple[float, float],
        damage: int,
    ) -> BossLaser:
        # Mesmo comportamento visual/temporal do BossLaser, mas usado como poder do jogador.
        distance = float(max(Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT) * 2)
        dx, dy = direction
        laser = BossLaser(
            x=x,
            y=y,
            target_x=x + dx * distance,
            target_y=y + dy * distance,
            damage=damage,
        )
        self.cacador_lasers.append(laser)
        return laser

    def spawn_homing_bullet(
        self,
        x: float,
        y: float,
        damage: int,
        lifetime: float = 1.5,
        direction: tuple[float, float] | None = None,
    ) -> HomingBullet:
        """Spawna um tiro teleguiado consumível (Caçador)."""
        homing = HomingBullet(
            x=x,
            y=y,
            damage=damage,
            lifetime=lifetime,
            is_side_scroll=self.is_side_scroll,
            direction=direction,
        )
        self.homing_bullets.append(homing)
        return homing

    def rebuild_all_grids(self) -> None:
        if not self._grid_needs_rebuild:
            return

        self.enemy_spatial_grid.clear()
        for e in self.enemies:
            if not e.dead:
                self.enemy_spatial_grid.insert_from_rect(e)
        for prop in self.mountain_propellers:
            if not prop.dead:
                self.enemy_spatial_grid.insert_from_rect(prop)
        for m in self.boulders:
            if not m.dead:
                self.enemy_spatial_grid.insert_from_rect(m)
        for s in self.attack_debris:
            if not s.dead:
                self.enemy_spatial_grid.insert_from_rect(s)
        for r in self.orbital_debris:
            if not r.dead and getattr(r, "causes_damage", False):
                self.enemy_spatial_grid.insert_from_rect(r)

        if isinstance(self.boss, StoneGolemBoss):
            for d in self.boss.emerge_debris:
                if not d.dead:
                    self.enemy_spatial_grid.insert_from_rect(d)

        for e in self._cached_formation_enemies:
            self.enemy_spatial_grid.insert_from_rect(e)

        self.spike_spatial_grid.clear()
        for s in self.spikes:
            self.spike_spatial_grid.insert_from_rect(s)

        self._grid_needs_rebuild = False

    def _check_alien_collisions(self) -> None:
        aliens = [
            e
            for e in self.enemies
            if isinstance(e, Alien) and not e.dead and not e.formation_controlled
        ]
        processed: set[tuple[int, int]] = set()
        for a in aliens:
            r = a.rect
            for o in self.enemy_spatial_grid.query(
                r.x - 1, r.y - 1, r.width + 2, r.height + 2
            ):
                if (
                    o is a
                    or o.dead
                    or not isinstance(o, Alien)
                    or o.formation_controlled
                ):
                    continue
                aid, oid = id(a), id(o)
                if aid >= oid or (aid, oid) in processed:
                    continue
                if r.colliderect(o.rect):
                    processed.add((aid, oid))
                    a.speed_x *= -1
                    o.speed_x *= -1
                    ox = (a.w + o.w) / 2 - abs(a.x - o.x)
                    if ox > 0:
                        if a.x < o.x:
                            a.x -= ox / 2
                            o.x += ox / 2
                        else:
                            a.x += ox / 2
                            o.x -= ox / 2

    def update(
        self,
        dt: float,
        player_x: float,
        player_y: float,
        freeze_enemies: bool = False,
        screen_width: int = 1600,
        screen_height: int = 900,
        attraction_mult: float = 1.0,
    ) -> None:
        enemy_dt = 0.0 if freeze_enemies else dt
        new_alien_bullets: List[AlienBullet] = []
        new_eye_lasers: List[EyeLaser] = []

        # Cache de inimigos
        self._cached_formation_enemies = []
        self._cached_all_enemies = list(self.enemies)
        for f in self.formations:
            fe = f.get_enemies()
            self._cached_formation_enemies.extend(fe)
            self._cached_all_enemies.extend(fe)
        if self.boss:
            self._cached_all_enemies.append(self.boss)

        # Atualizar efeitos visuais
        for w in self.emp_waves[:]:
            w.update(dt)
            if w.dead:
                self.emp_waves.remove(w)
        for e in self.explosive_effects[:]:
            e.update(dt)
            if e.dead:
                self.explosive_effects.remove(e)
        for zone in self.ice_poison_zones[:]:
            zone.update(dt)
            if zone.dead:
                self.ice_poison_zones.remove(zone)
        for zone in self.fire_zones[:]:
            zone.update(dt)
            if zone.dead:
                self.fire_zones.remove(zone)

        # Helper para lentidão (EMP)
        slow_active = getattr(self, "emp_active", False)
        slow_factor = getattr(self, "emp_slow_factor", 1.0) if slow_active else 1.0
        emp_waves = self.emp_waves

        def emp_mul_for(entity: Any) -> float:
            linger = getattr(entity, "emp_linger_timer", 0.0)
            if not slow_active:
                return float(slow_factor) if linger > 0.0 else 1.0
            rect = getattr(entity, "rect", None)
            ex, ey = (
                (rect.centerx, rect.centery)
                if rect
                else (getattr(entity, "x", 0.0), getattr(entity, "y", 0.0))
            )
            for w in emp_waves:
                if w.is_affecting_position(float(ex), float(ey), dt):
                    setattr(entity, "emp_linger_timer", float(EMP_LINGER_DURATION))
                    return float(slow_factor)
            return float(slow_factor) if linger > 0.0 else 1.0

        def update_linger(entity: Any, dt: float) -> None:
            linger_t = getattr(entity, "emp_linger_timer", 0.0)
            if linger_t > 0.0:
                setattr(entity, "emp_linger_timer", max(0.0, linger_t - dt))

        def ice_mul_for(entity: Any) -> float:
            ice_t = getattr(entity, "_ice_slow_timer", 0.0)
            return IcePoisonZone.SLOW_FACTOR if ice_t > 0.0 else 1.0

        def update_ice_linger(entity: Any, dt: float) -> None:
            ice_t = getattr(entity, "_ice_slow_timer", 0.0)
            if ice_t > 0.0:
                setattr(entity, "_ice_slow_timer", max(0.0, ice_t - dt))

        # Atualizar formações e naves aliadas
        for f in self.formations[:]:
            update_linger(f, dt)
            update_ice_linger(f, dt)
            mul = emp_mul_for(f) * ice_mul_for(f)
            shot = f.update(enemy_dt * mul)
            if shot:
                new_alien_bullets.extend(shot)

        for b in self.bullets:
            b.update(dt, self._cached_all_enemies if b.homing else None)

        for b in self.homing_bullets:
            b.update(dt, self._cached_all_enemies)

        for b in self.mini_ship_bullets:
            b.update(dt)

        for b in self.player_lasers:
            if b.target_entity and getattr(b.target_entity, "dead", False):
                b.target_entity = None
            b.update(dt)
        for b in self.cacador_lasers:
            b.update(dt)

        # Atualizar projéteis inimigos
        for b in self.alien_bullets:
            b.update(enemy_dt)
        for b in self.serpent_bullets:
            b.update(enemy_dt)
        for b in self.boss_lasers:
            b.update(enemy_dt)
        for b in self.eye_lasers:
            b.update(enemy_dt)

        self.explosion_pool.update(dt)
        for me in self.mine_explosions:
            me.update(dt)
        
        # Coletáveis com suporte a atração (Magneto)
        player_pos = (player_x, player_y)
        for p in self.powerups:
            p.update(dt, attraction_pos=player_pos, attraction_mult=attraction_mult)
        for s in self.stars:
            s.update(dt, screen_width, screen_height, attraction_pos=player_pos, attraction_mult=attraction_mult)
            
        for fs in self.floating_scores:
            fs.update(dt)
        for ms in self.mini_ships:
            ms.update(dt, self._cached_all_enemies, self.mini_ship_bullets)

        # Atualizar Spikes
        ac = sum(1 for s in self.spikes if s.state in ("trembling", "flying"))
        for s in self.spikes:
            update_linger(s, dt)
            update_ice_linger(s, dt)
            mul = emp_mul_for(s) * ice_mul_for(s)
            s.update(enemy_dt * mul, player_x, player_y, ac)

        # Atualizar Boss
        if self.boss:
            if isinstance(self.boss, SpikeBoss):
                ss, bls = self.boss.update(enemy_dt, player_x, player_y, self.spikes)
                if ss:
                    self.spikes.extend(ss)
                if bls:
                    self.boss_lasers.extend(bls)
            elif isinstance(self.boss, SlimeBoss):
                self.boss.update(enemy_dt, player_x, player_y, self)
            elif isinstance(self.boss, GiantMeteorBoss):
                self.boss.update(enemy_dt, self)
            elif isinstance(self.boss, StoneGolemBoss):
                nb, ns, orks = self.boss.update(enemy_dt, player_x, player_y, self)
                if nb:
                    self.boulders.extend(nb)
                if ns:
                    self.attack_debris.extend(ns)
                self.orbital_debris = orks
            elif isinstance(self.boss, MountainSerpentBoss):
                bb, fragments = self.boss.update(enemy_dt, player_x, player_y)
                if bb:
                    self.serpent_bullets.extend(bb)
                for f in fragments:
                    if isinstance(f, SerpentRockBullet):
                        self.serpent_bullets.append(f)
                    else:
                        self.enemies.append(f)
            elif isinstance(self.boss, CloudArchmageBoss):
                spawned = self.boss.update(enemy_dt, (player_x, player_y))
                if spawned:
                    for s in spawned:
                        if isinstance(s, RockGlider):
                            self.rock_glider_pool.pool.append(s)
                            self.rock_glider_pool.active.append(s)
                            self.enemies.append(s)  # type: ignore[arg-type]
                        elif isinstance(s, MountainPropeller):
                            self.mountain_propellers.append(s)
                        else:
                            self.enemies.append(s)
            else:
                ls, sqs = self.boss.update(enemy_dt, player_x, player_y)
                if ls:
                    self.boss_lasers.extend(ls)
                if sqs:
                    self.boss_squares.extend(sqs)
                for q in self.boss.floating_squares:
                    if q not in self.boss_squares:
                        self.boss_squares.append(q)

        # Atualizar Inimigos Comuns
        for en in self.enemies:
            update_ice_linger(en, dt)
            mul = emp_mul_for(en) * ice_mul_for(en)
            sdt = enemy_dt * mul
            if isinstance(en, Alien):
                s = en.update(sdt)
                if s:
                    new_alien_bullets.extend(s)
            elif isinstance(en, EyeEnemy):
                s = en.update(sdt, player_x, player_y)
                if s:
                    new_eye_lasers.extend(s)
            elif isinstance(en, GuidedMeteor):
                en.update(sdt, self.is_side_scroll, player_x, player_y)
            elif isinstance(en, SquareMinionBoss):
                en.update(sdt, screen_width, screen_height)
            elif isinstance(en, ElementalRobot):
                no = en.update(dt, sdt, player_x, player_y)
                if no:
                    self.energy_orbs.extend(no)
            elif isinstance(en, StoneSentry):
                s = en.update(sdt, (player_x, player_y), self.enemies)
                if s:
                    new_alien_bullets.extend(s)
            elif isinstance(en, MountainMage):
                nst = en.update(sdt, (player_x, player_y))
                if nst:
                    self.enemies.extend(nst)
            elif isinstance(en, Meteor):
                en.update(sdt, self.is_side_scroll)
            else:
                en.update(sdt)

        for prop in self.mountain_propellers:
            prop.update(dt)
        self.mountain_propellers = [p for p in self.mountain_propellers if not p.dead]

        # Atualizar projéteis adicionais e colisões
        for o in self.energy_orbs:
            o.update(dt)
        self._check_alien_collisions()
        self.alien_bullets.extend(new_alien_bullets)
        self.eye_lasers.extend(new_eye_lasers)

        # Atualizar elementos dinâmicos da tela
        screen = pygame.display.get_surface()
        sw, sh = screen.get_size() if screen else (1600, 900)

        for q in self.boss_squares[:]:
            q.update(enemy_dt, sw, sh)
            if q.dead:
                self.boss_squares.remove(q)

        for m in self.boulders:
            es = m.update(dt)
            if es:
                self.attack_debris.extend(es)

        for s in self.attack_debris:
            s.update(dt)

        for b in self.air_strike_bombs[:]:
            b.update(enemy_dt)
            if b.dead:
                self.air_strike_bombs.remove(b)

        for t in self.cannon_towers[:]:
            t.update(enemy_dt)
            if t.dead:
                self.cannon_towers.remove(t)

        for m in self.cannon_mines[:]:
            m.update(enemy_dt)
            if m.dead:
                self.cannon_mines.remove(m)

        for b in self.black_holes:
            b.update(dt)
        for b in self.black_holes:
            b.process_all_enemies(
                self._cached_all_enemies, enemy_dt, self.spawn_explosion
            )

        self.cleanup()
        self.rebuild_all_grids()

    def update_for_game_over_slow_motion(
        self, dt: float, player_x: float, player_y: float
    ) -> None:
        # Atualizar todas as listas de perigos e projéteis
        groups: List[List[Any]] = [
            self.enemies,
            self.bullets,
            self.alien_bullets,
            self.serpent_bullets,
            self.boss_lasers,
            self.powerups,
            self.floating_scores,
            self.mini_ships,
            self.spikes,
            self.boss_squares,
            self.eye_lasers,
            self.mini_ship_bullets,
            self.cannon_towers,
            self.cannon_mines,
            self.energy_orbs,
            self.boulders,
            self.attack_debris,
        ]
        for g in groups:
            for e in g:
                if isinstance(e, (EyeEnemy, GuidedMeteor, ElementalRobot)):
                    if isinstance(e, GuidedMeteor):
                        e.update(dt, self.is_side_scroll, player_x, player_y)
                    elif isinstance(e, ElementalRobot):
                        e.update(dt, dt, player_x, player_y)
                    else:
                        e.update(dt, player_x, player_y)
                elif isinstance(e, MiniShip):
                    e.update(dt, [], [])
                elif isinstance(e, Meteor):
                    e.update(dt, self.is_side_scroll)
                else:
                    e.update(dt)

        for f in self.formations:
            f.update(dt)
        self.explosion_pool.update(dt)

        if self.boss:
            if isinstance(self.boss, SpikeBoss):
                ss, bls = self.boss.update(dt, player_x, player_y, self.spikes)
                if ss:
                    self.spikes.extend(ss)
                if bls:
                    self.boss_lasers.extend(bls)
            elif isinstance(self.boss, SlimeBoss):
                self.boss.update(dt, player_x, player_y, self)
            elif isinstance(self.boss, GiantMeteorBoss):
                self.boss.update(dt, self)
            elif isinstance(self.boss, StoneGolemBoss):
                nb, ns, orks = self.boss.update(dt, player_x, player_y, self)
                if nb:
                    self.boulders.extend(nb)
                if ns:
                    self.attack_debris.extend(ns)
                self.orbital_debris = orks
            elif isinstance(self.boss, MountainSerpentBoss):
                bb, fragments = self.boss.update(dt, player_x, player_y)
                if bb:
                    self.serpent_bullets.extend(bb)
                for f in fragments:
                    if isinstance(f, SerpentRockBullet):
                        self.serpent_bullets.append(f)
                    else:
                        self.enemies.append(f)
            elif isinstance(self.boss, CloudArchmageBoss):
                spawned = self.boss.update(dt, (player_x, player_y))
                if spawned:
                    for s in spawned:
                        if isinstance(s, RockGlider):
                            self.rock_glider_pool.pool.append(s)
                            self.rock_glider_pool.active.append(s)
                            self.enemies.append(s)  # type: ignore[arg-type]
                        elif isinstance(s, MountainPropeller):
                            self.mountain_propellers.append(s)
                        else:
                            self.enemies.append(s)
            else:
                # Many boss subclasses return (lasers, squares). Use a cast
                # to give the type-checker a concrete signature here.
                result = self.boss.update(dt, player_x, player_y)
                ls, sqs = result
                if ls:
                    self.boss_lasers.extend(ls)
                if sqs:
                    self.boss_squares.extend(sqs)
        self.cleanup()

    def draw(
        self,
        surface: pygame.Surface,
        player_x: float,
        player_y: float,
        enemy_visible: bool = True,
        fps: float = 60.0,
        draw_boss: bool = True,
    ) -> None:
        sr = surface.get_rect()

        def is_v(e: Any) -> bool:
            # Verifica visibilidade de forma robusta
            r = getattr(e, "rect", None)
            if r is not None and isinstance(r, pygame.Rect):
                return r.colliderect(sr)
            x = getattr(e, "x", None)
            y = getattr(e, "y", None)
            w = getattr(e, "w", None)
            h = getattr(e, "h", None)
            if x is not None and y is not None and w is not None and h is not None:
                return pygame.Rect(int(x), int(y), int(w), int(h)).colliderect(sr)
            return True  # Assume visível se não tiver geometria clara

        # MountainMage em APPEARING é desenhado independente de enemy_visible e is_v:
        # as partículas se espalham além do rect, e o efeito não deve piscar durante
        # o blink de limpeza de fase nem ser cortado pelo culling de visibilidade.
        for e in self.enemies:
            if isinstance(e, MountainMage) and not e.dead and e.is_appearing:
                e.draw(surface)

        if enemy_visible:
            # Note: meteor_pool.draw removed from here to avoid duplicate and move to higher layer
            for e in self.enemies:
                if isinstance(e, Meteor):
                    continue  # Will be drawn later via meteor_pool
                # MountainMage em APPEARING já foi desenhado acima — skip para evitar duplo draw
                if isinstance(e, MountainMage) and not e.dead and e.is_appearing:
                    continue
                # MountainStalagmite/Stalactite: sempre desenha (com ou sem fragmentos) — o rect
                # pode ser zero no início de RISING antes da máscara ser calculada.
                if (
                    isinstance(e, (MountainStalagmite, MountainStalactite))
                    and not e.dead
                ):
                    e.draw(surface)
                    continue
                if isinstance(e, (MountainStalagmite, MountainStalactite)) and getattr(
                    e, "_fragments", None
                ):
                    e.draw(surface)
                    continue
                if is_v(e):
                    if isinstance(e, EyeEnemy):
                        e.draw(surface, player_x, player_y)
                    else:
                        e.draw(surface)
            for f in self.formations:
                if is_v(f):
                    f.draw(surface)
            for prop in self.mountain_propellers:
                prop.draw(surface)

        # 2. Desenhar projéteis que ficam por BAIXO do boss (como o ataque da serpente)
        for b in self.serpent_bullets:
            if is_v(b):
                b.draw(surface)

        # 3. Desenhar o Boss (agora por cima das rochas da serpente)
        if draw_boss and self.boss:
            if isinstance(self.boss, SlimeBoss):
                self.boss.draw(surface, fps)
            else:
                self.boss.draw(surface)

        # 3.5 Desenhar Meteoros (agora sobre o boss para efeito de "breaking off")
        if enemy_visible:
            self.meteor_pool.draw(surface)
            self.rock_glider_pool.draw(surface)

        for laser in self.boss_lasers:
            laser.draw(surface)
        for laser in self.cacador_lasers:
            # Laser em linha pode ter rect com altura/largura zero;
            # não usar culling por rect para não sumir no draw.
            laser.draw(surface)
        for b in self.black_holes:
            b.draw(surface)
        for w in self.emp_waves:
            w.draw(surface)
        for zone in self.ice_poison_zones:
            zone.draw(surface)
        for zone in self.fire_zones:
            zone.draw(surface)

        # 4. Desenhar projéteis e efeitos de impacto (devem ficar SOBRE os inimigos)
        lists: List[List[Any]] = [
            self.bullets,
            self.homing_bullets,
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
            self.attack_debris,
        ]
        for lst in lists:
            for e in lst:
                if is_v(e):
                    e.draw(surface)

        self.explosion_pool.draw_all(surface)
        for e in self.explosive_effects:
            e.draw(surface)

    def spawn_elemental_robot(
        self,
        x: float | None = None,
        y: float | None = None,
        difficulty_multiplier: float = 1.0,
        start_visible: bool = False,
    ) -> ElementalRobot:
        screen = pygame.display.get_surface()
        sw, sh = screen.get_size() if screen else (1600, 900)
        robot = ElementalRobot(
            x if x is not None else sw / 2 - 72,
            y if y is not None else sh * 0.15,
            difficulty_multiplier=difficulty_multiplier,
            start_visible=start_visible,
        )
        self.enemies.append(robot)
        return robot

    def spawn_stone_sentry(
        self,
        x: float | None = None,
        y: float | None = None,
    ) -> StoneSentry:
        sentry = StoneSentry()
        if x is not None:
            sentry.x = x
        if y is not None:
            sentry.target_y = y
        self.enemies.append(sentry)
        return sentry

    def spawn_mountain_serpent_boss(
        self,
        x: float | None = None,
        y: float | None = None,
        health: int | None = None,
        block_health_multiplier: float = 1.0,
    ) -> MountainSerpentBoss:
        boss = MountainSerpentBoss(x=x, y=y, health=health)
        self.boss = boss
        self.enemies.extend(boss.create_blocks(block_health_multiplier))
        return boss

    def spawn_mountain_propeller(self, y: float | None = None) -> MountainPropeller:
        prop = MountainPropeller(y=y)
        self.mountain_propellers.append(prop)
        return prop

    def spawn_giant_meteor_boss(
        self, x: float = 0.0, y: float = 0.0
    ) -> GiantMeteorBoss:
        boss = GiantMeteorBoss(x, y)
        boss.is_side_scroll = self.is_side_scroll
        self.boss = boss
        return boss

    def spawn_meteor(
        self,
        size: int | None = None,
        x: float | None = None,
        y: float | None = None,
        vx: float | None = None,
        vy: float | None = None,
        behind: bool = False,
    ) -> Meteor:
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
        damage: int = Config.BULLET_BASE_DAMAGE,
        piercing: bool = False,
        homing: bool = False,
        explosive: bool = False,
        low_ammo: bool = False,
        direction: Optional[tuple[float, float]] = None,
        ship_id: str = "padrao",
    ) -> Bullet:
        bullet = self.bullet_pool.get(
            x=x,
            y=y,
            damage=damage,
            piercing=piercing,
            homing=homing,
            explosive=explosive,
            low_ammo=low_ammo,
            is_side_scroll=self.is_side_scroll,
            direction=direction,
            ship_id=ship_id,
        )
        if homing:
            target = self._assign_homing_target(bullet)
            if target:
                bullet.assign_target(target)
        self.bullets.append(bullet)
        return bullet

    def _assign_homing_target(self, bullet: Bullet) -> Any:
        all_e: List[Any] = list(self.enemies)
        for f in self.formations:
            if not getattr(f, "dead", True):
                all_e.extend(f.get_enemies())
        if self.boss and not getattr(self.boss, "dead", True):
            all_e.append(self.boss)

        alive = [e for e in all_e if not getattr(e, "dead", True)]
        if not alive:
            return None

        counts: Dict[int, int] = {}
        for b in self.bullets:
            if getattr(b, "homing", False) and b.assigned_target_id is not None:
                counts[b.assigned_target_id] = counts.get(b.assigned_target_id, 0) + 1

        best = None
        min_c = 999999
        min_d = float("inf")
        for e in alive:
            eid = id(e)
            c = counts.get(eid, 0)
            ex, ey = e.x + getattr(e, "w", 0) / 2, e.y + getattr(e, "h", 0) / 2
            d = ((ex - bullet.x) ** 2 + (ey - bullet.y) ** 2) ** 0.5
            if c < min_c or (c == min_c and d < min_d):
                min_c = c
                min_d = d
                best = e
        return best

    def _is_enemy_off_screen(self, enemy: Any) -> bool:
        ew = getattr(enemy, "w", getattr(getattr(enemy, "rect", None), "width", 50))
        eh = getattr(enemy, "h", getattr(getattr(enemy, "rect", None), "height", 50))
        s = pygame.display.get_surface()
        sw, sh = s.get_size() if s else (1600, 900)

        if self.is_side_scroll:
            return enemy.x < -(ew + sw * 0.2) or enemy.y < -eh or enemy.y > sh

        # Para a Serpente, permitimos que os blocos existam abaixo do limite inferior (spawn)
        if isinstance(enemy, SerpentBlock):
            return enemy.y < -eh or enemy.x < -ew or enemy.x > sw

        return enemy.y > sh or enemy.x < -ew or enemy.x > sw

    @staticmethod
    def _filter_dead_inplace(
        lst: list[Any], is_dead_fn: Callable[[Any], bool] | None = None
    ) -> None:
        """Filter dead entities in-place using swap-and-pop to reduce GC pressure.

        Args:
            lst: List to filter
            is_dead_fn: Optional callable that returns True if entity is dead.
                       If None, checks lst[i].dead attribute.
        """

        def default_is_dead(x: Any) -> bool:
            return getattr(x, "dead", False)

        if is_dead_fn is None:
            is_dead_fn = default_is_dead

        i = 0
        while i < len(lst):
            if is_dead_fn(lst[i]):
                lst[i] = lst[-1]
                lst.pop()
            else:
                i += 1

    def cleanup(self) -> None:
        for b in self.bullets:
            if b.dead:
                self.bullet_pool.release(b)
        self._filter_dead_inplace(self.bullets)

        # Marcar como mortos inimigos que saíram da tela (exceto os controlados por boss)
        for e in self.enemies:
            if (
                not e.dead
                and not isinstance(e, SerpentBlock)
                # Stalagmites/stalactites spawn off-screen intentionally (rise from below
                # or fall from above) — let their own state machine handle removal.
                and not isinstance(e, (MountainStalagmite, MountainStalactite))
                and self._is_enemy_off_screen(e)
            ):
                e.dead = True

        self._filter_dead_inplace(self.alien_bullets)
        self._filter_dead_inplace(self.serpent_bullets)
        self._filter_dead_inplace(self.energy_orbs)
        self._filter_dead_inplace(self.boss_lasers)
        self._filter_dead_inplace(self.player_lasers)
        self._filter_dead_inplace(self.cacador_lasers)
        self._filter_dead_inplace(self.homing_bullets)
        self._filter_dead_inplace(self.boss_squares)
        self._filter_dead_inplace(self.slime_drips)
        self._filter_dead_inplace(self.eye_lasers)
        self._filter_dead_inplace(self.mini_ship_bullets)

        # Processar remoção de inimigos via protocolos should_remove/on_remove
        to_remove: list[Any] = []
        for e in self.enemies:
            should: bool = e.should_remove() if isinstance(e, Removable) else e.dead
            if should:
                # Chama callback de limpeza (ex: devolver ao pool)
                if hasattr(e, "on_remove"):
                    getattr(e, "on_remove")(self)
                to_remove.append(e)

        if to_remove:
            remove_ids = {id(e) for e in to_remove}
            self._filter_dead_inplace(self.enemies, lambda e: id(e) in remove_ids)

        self._filter_dead_inplace(self.mine_explosions, lambda m: m.finished())
        self._filter_dead_inplace(self.ice_poison_zones)
        self._filter_dead_inplace(self.powerups)
        self._filter_dead_inplace(self.stars)
        self._filter_dead_inplace(self.floating_scores, lambda f: f.is_dead())
        self._filter_dead_inplace(self.formations)
        self._filter_dead_inplace(self.spikes)
        self._filter_dead_inplace(self.air_strike_bombs)
        self._filter_dead_inplace(self.cannon_towers)
        self._filter_dead_inplace(self.cannon_mines)
        self._filter_dead_inplace(self.boulders)
        self._filter_dead_inplace(self.attack_debris)
        self._filter_dead_inplace(self.orbital_debris)
        self._grid_needs_rebuild = True

    def clear_all(self) -> None:
        self.bullets.clear()
        self.homing_bullets.clear()
        self.alien_bullets.clear()
        self.serpent_bullets.clear()
        self.energy_orbs.clear()
        self.boss_lasers.clear()
        self.cacador_lasers.clear()
        self.boss_squares.clear()
        self.slime_drips.clear()
        self.eye_lasers.clear()
        self.powerups.clear()
        self.stars.clear()
        self.floating_scores.clear()
        # Limpeza especial para blocos da serpente
        if isinstance(self.boss, MountainSerpentBoss):
            self.boss._all_blocks.clear()  # type: ignore[attr-defined]
        self.enemies.clear()
        self.boulders.clear()
        self.attack_debris.clear()
        self.orbital_debris.clear()
        self.mine_explosions.clear()
        self.ice_poison_zones.clear()
        self.fire_zones.clear()
        self.mountain_propellers.clear()
        self.explosive_effects.clear()
        self.air_strike_bombs.clear()
        self.cannon_towers.clear()
        self.cannon_mines.clear()
        self.black_holes.clear()
        self.emp_waves.clear()
        self.boss = None
        self.mini_ships.clear()
        self.mini_ship_bullets.clear()
        self.formations.clear()
        self.spikes.clear()
        self.meteor_pool.clear_active()
        self.rock_glider_pool.clear_active()
        self.bullet_pool.clear_active()
        self.explosion_pool.clear_active()
        self.enemy_spatial_grid.clear()
        self.spike_spatial_grid.clear()
        self._grid_needs_rebuild = True

    def clear_for_level_transition(self) -> None:
        self.alien_bullets.clear()
        self.homing_bullets.clear()
        self.serpent_bullets.clear()
        self.energy_orbs.clear()
        self.cacador_lasers.clear()
        self.boss_squares.clear()
        self.eye_lasers.clear()
        self.floating_scores.clear()
        self.enemies.clear()
        self.mine_explosions.clear()
        self.ice_poison_zones.clear()
        self.fire_zones.clear()
        self.mountain_propellers.clear()
        self.boss = None
        # Mini-naves são limpas completamente; a cena reconstrói o estado
        # correto após o clear (permanentes vs par temporário do powerup ativo).
        self.mini_ships.clear()
        self.mini_ship_bullets.clear()
        self.formations.clear()
        self.meteor_pool.clear_active()
        self.rock_glider_pool.clear_active()
        self.explosion_pool.clear_active()
        self.spikes.clear()
        self.boulders.clear()
        self.attack_debris.clear()
        self.orbital_debris.clear()
        # Entidades spawnadas por upgrades do jogador são preservadas —
        # o slot do upgrade mantém duration_left/active, então limpar a
        # entidade em tela "rouba" o efeito que o jogador acabou de pagar
        # em cooldown. Air strikes em queda, black holes ativos, torres
        # de canhão com mines, ondas EMP e resíduos de tiro explosivo
        # continuam até expirarem naturalmente.
        # Powerups e estrelas em tela também são preservados — não é
        # justo perder um pickup pendente por timing de transição.

        self.enemy_spatial_grid.clear()
        self.spike_spatial_grid.clear()
        self._grid_needs_rebuild = True

    def get_stats(self) -> Dict[str, Any]:
        return {
            "bullets": len(self.bullets),
            "enemies": len(self.enemies),
            "formations": len(self.formations),
            "explosions_active": self.explosion_pool.get_stats()["active"],
            "grid_stats": self.enemy_spatial_grid.get_statistics(),
        }
