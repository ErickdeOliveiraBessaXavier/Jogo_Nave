import random
from typing import TYPE_CHECKING, Any, Callable, Optional, Sequence, Union

import pygame

from ..core.config import config as Config
from ..core.spatial_grid import SpatialGrid
from ..core.upgrades_config import EMP_LINGER_DURATION, EMP_SLOW_FACTOR
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
from ..entities.chain_lightning import ChainLightning
from ..entities.cloud_archmage_boss import CloudArchmageBoss
from ..entities.emp_wave import EMPWave
from ..entities.explosion import Explosion, ExplosionType
from ..entities.explosion_pool import ExplosionPool
from ..entities.explosive_effect import ExplosiveEffect
from ..entities.explosive_mine import ExplosiveMine
from ..entities.eye_enemy import EyeEnemy
from ..entities.eye_laser import EyeLaser
from ..entities.Inimigos_Tema_Cidade.captor_emp import CaptorEMP
from ..entities.Inimigos_Tema_Cidade.core_implosion import CoreImplosion
from ..entities.Inimigos_Tema_Cidade.cyber_captor import CyberCaptor
from ..entities.Inimigos_Tema_Cidade.cyber_tank import CyberTank
from ..entities.Inimigos_Tema_Cidade.jammer_node import JammerNode
from ..entities.Inimigos_Tema_Cidade.neon_bolt import NeonBolt
from ..entities.Inimigos_Tema_Cidade.splitter_debris import SplitterDebris
from ..entities.Inimigos_Tema_Cidade.carrier_debris import CarrierDebris
from ..entities.Inimigos_Tema_Cidade.cargo_carrier import CargoCarrier
from ..entities.Inimigos_Tema_Cidade.splitter_tank import SplitterTank
from ..entities.Inimigos_Tema_Cidade.neon_sniper import NeonSniper
from ..entities.Inimigos_Tema_Cidade.police_crash import PoliceCrash
from ..entities.Inimigos_Tema_Cidade.police_interceptor import PoliceInterceptor
from ..entities.Inimigos_Tema_Cidade.tank_meltdown import TankMeltdown
from ..entities.fire_zone import FireZone
from ..entities.floating_score import FloatingScore
from ..entities.formation import Formation
from ..entities.giant_meteor_boss import GiantMeteorBoss
from ..entities.homing_bullet import HomingBullet
from ..entities.ice_poison_zone import IcePoisonZone
from ..entities.meteor import Meteor
from ..entities.meteor_pool import MeteorPool
from ..entities.mine_explosion import MineExplosion
from ..entities.mini_ship import MiniShip
from ..entities.mini_ship_bullet import MiniShipBullet
from ..entities.mountain_mage import (
    MountainMage,
    MountainStalactite,
    MountainStalagmite,
)
from ..entities.mountain_propeller import MountainPropeller
from ..entities.mountain_serpent_boss import (
    MountainSerpentBoss,
    SerpentBlock,
    SerpentRockBullet,
)
from ..entities.player_laser import PlayerLaser
from ..entities.powerup import PowerUp
from ..entities.rock_glider_pool import RockGliderPool
from ..entities.slime_boss import SlimeBoss
from ..entities.slime_drip import SlimeDrip
from ..entities.spike import Spike
from ..entities.spike_boss import SpikeBoss
from ..entities.orbital_shield import OrbitalShield
from ..entities.plasma_beam import PlasmaBeam
from ..entities.spike_boss_laser import SpikeBossLaser
from ..entities.square_minion_boss import SquareMinionBoss
from ..entities.star import Star
from ..entities.stone_golem_boss import (
    AttackDebris,
    EmergeDebris,
    GolemMine,
    OrbitalDebris,
    StoneGolemBoss,
)
from ..entities.stone_sentry import StoneSentry
from ..entities.wingman import Wingman
from ..entities.coop_link import CoopLink
from . import enemy_shield
from .boss_context import BossUpdateContext, BossUpdateResult
from .collision_protocols import Removable
from .entity_context import EnemyUpdateContext
from .hit_result import MeteorSpec

if TYPE_CHECKING:
    from ..entities.ship import Ship


class EntityManager:
    """Gerencia todas as entidades do jogo, coordenando update, draw e cleanup."""

    def __init__(
        self,
        sound_manager: Any | None = None,
        is_side_scroll: bool = False,
        aggressiveness_multiplier: float = 1.0,
    ) -> None:
        self.sound_manager = sound_manager
        self.is_side_scroll = is_side_scroll
        self.aggressiveness_multiplier = aggressiveness_multiplier

        # Listas de projéteis e efeitos
        self.bullets: list[Bullet] = []
        self.homing_bullets: list[HomingBullet] = []
        self.emp_waves: list[EMPWave] = []
        self.energy_orbs: list[EnergyOrb] = []
        self.explosive_effects: list[ExplosiveEffect] = []
        self.alien_bullets: list[AlienBullet] = []
        self.serpent_bullets: list[SerpentRockBullet] = []
        self.boss_lasers: list[Union[BossLaser, SpikeBossLaser]] = []
        self.player_lasers: list[PlayerLaser] = []
        self.cacador_lasers: list[BossLaser] = []
        self.boss_squares: list[BossSquare] = []
        self.slime_drips: list[SlimeDrip] = []
        self.eye_lasers: list[EyeLaser] = []
        self.neon_bolts: list[NeonBolt] = []
        self.core_implosions: list[CoreImplosion] = []
        self.police_crashes: list[PoliceCrash] = []
        self.tank_meltdowns: list[TankMeltdown] = []
        self.splitter_debris: list[SplitterDebris] = []
        self.carrier_debris: list[CarrierDebris] = []
        self.captor_emps: list[CaptorEMP] = []
        # Blasts de área one-shot (cx, cy, raio) emitidos por efeitos/inimigos neste
        # frame; consumidos pela cena (handle_mine_explosion) p/ aplicar dano à nave.
        self.area_blasts: list[tuple[float, float, float]] = []
        self.mine_explosions: list[MineExplosion] = []
        self.ice_poison_zones: list[IcePoisonZone] = []
        self.fire_zones: list[FireZone] = []
        self.mini_ship_bullets: list[MiniShipBullet] = []
        self.chain_lightnings: list[ChainLightning] = []
        self.orbital_shields: list[OrbitalShield] = []
        self.plasma_beams: list[PlasmaBeam] = []

        # Listas de entidades e coletáveis
        self.enemies: list[Any] = []
        self.powerups: list[PowerUp] = []
        self.stars: list[Star] = []
        self.floating_scores: list[FloatingScore] = []

        self.boss: Union[
            Boss,
            SpikeBoss,
            SlimeBoss,
            GiantMeteorBoss,
            StoneGolemBoss,
            MountainSerpentBoss,
            CloudArchmageBoss,
            None,
        ] = None

        self.mini_ships: list[MiniShip] = []
        self.wingmen: list[Wingman] = []
        self.coop_links: list[CoopLink] = []
        self.formations: list[Formation] = []
        self.mountain_propellers: list[MountainPropeller] = []
        self.spikes: list[Spike] = []
        self.boulders: list[GolemMine] = []
        self.attack_debris: list[AttackDebris] = []
        self.orbital_debris: list[OrbitalDebris] = []
        self.air_strike_bombs: list[AirStrikeBomb] = []
        self.cannon_towers: list[CannonTower] = []
        self.cannon_mines: list[CannonMine] = []
        self.black_holes: list[BlackHole] = []

        # Pools de performance
        self.meteor_pool = MeteorPool(
            initial_size=100,
            is_side_scroll=is_side_scroll,
            aggressiveness_multiplier=aggressiveness_multiplier,
        )
        self.rock_glider_pool = RockGliderPool(
            initial_size=24,
            is_side_scroll=is_side_scroll,
            aggressiveness_multiplier=aggressiveness_multiplier,
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
        self.enemy_projectile_grid: SpatialGrid[Any] = SpatialGrid()

        # Estado interno
        self._grid_needs_rebuild = True
        self._cached_formation_enemies: list[Any] = []
        self._cached_all_enemies: list[Any] = []

        # Cache do tamanho da tela — evita pygame.display.get_surface() por inimigo/frame.
        self._screen_size: tuple[int, int] = (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)

    def set_side_scroll(self, value: bool) -> None:
        """Atualiza o modo de jogo (top-down vs side-scroll) e propaga aos pools.

        Crítico na transição entre mundos: o modo é definido no `__init__`, mas
        ao cruzar de um mundo side-scroll (ex.: Cordilheira) para um top-down
        (ex.: Espaço Sideral) o `EntityManager` precisa trocar as regras de
        culling off-screen e de movimento dos meteoros. Sem isso, entidades que
        saem pela lateral direita em top-down não eram removidas (a regra
        side-scroll só removia pela esquerda), ficando contadas como hostis
        ativos e travando o fim de fase.
        """
        self.is_side_scroll = value
        self.meteor_pool.is_side_scroll = value
        self.rock_glider_pool.is_side_scroll = value

    def _dispatch_boss_sound_events(self, sound_events: Sequence[str]) -> None:
        """Executa eventos de som emitidos por Boss.update()."""
        if not sound_events or not self.sound_manager:
            return
        dispatch = {
            "play_charging": self.sound_manager.play_boss_laser_charging,
            "stop_charging": self.sound_manager.stop_boss_laser_charging,
            "play_fire": self.sound_manager.play_boss_laser_fire,
            "stop_fire": self.sound_manager.stop_boss_laser_fire,
        }
        for ev in sound_events:
            fn = dispatch.get(ev)
            if fn:
                fn()

    def _emp_multiplier(
        self,
        entity: Any,
        slow_active: bool,
        slow_factor: float,
        dt: float,
    ) -> float:
        """Retorna o multiplicador de velocidade por EMP para uma entidade."""
        linger = getattr(entity, "emp_linger_timer", 0.0)
        if not slow_active:
            return float(slow_factor) if linger > 0.0 else 1.0
        rect = getattr(entity, "rect", None)
        ex, ey = (
            (rect.centerx, rect.centery)
            if rect
            else (getattr(entity, "x", 0.0), getattr(entity, "y", 0.0))
        )
        for w in self.emp_waves:
            if w.is_affecting_position(float(ex), float(ey), dt):
                setattr(entity, "emp_linger_timer", float(EMP_LINGER_DURATION))
                return float(slow_factor)
        return float(slow_factor) if linger > 0.0 else 1.0

    @staticmethod
    def _update_emp_linger(entity: Any, dt: float) -> None:
        """Decrementa o timer de linger EMP da entidade."""
        linger_t = getattr(entity, "emp_linger_timer", 0.0)
        if linger_t > 0.0:
            setattr(entity, "emp_linger_timer", max(0.0, linger_t - dt))

    @staticmethod
    def _ice_multiplier(entity: Any) -> float:
        """Retorna o multiplicador de velocidade por zona de gelo para uma entidade."""
        ice_t = getattr(entity, "_ice_slow_timer", 0.0)
        return IcePoisonZone.SLOW_FACTOR if ice_t > 0.0 else 1.0

    @staticmethod
    def _update_ice_linger(entity: Any, dt: float) -> None:
        """Decrementa o timer de slow de gelo da entidade."""
        ice_t = getattr(entity, "_ice_slow_timer", 0.0)
        if ice_t > 0.0:
            setattr(entity, "_ice_slow_timer", max(0.0, ice_t - dt))

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
        return self.explosion_pool.get(x, y, size, explosion_type)

    def absorb_fragments(self, fragments: tuple[Any, ...]) -> None:
        """Materializa fragments oriundos de HitResult.

        MeteorSpec → meteor_pool.get; entidades já alocadas → enemies.append.
        Mantém o pool isolado das entidades (estas só geram specs).
        """
        if not fragments:
            return

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
        elif isinstance(target, NeonSniper):
            cx = target.x + target.w / 2
            cy = target.y + target.h / 2
            self.core_implosions.append(CoreImplosion(cx, cy))
        elif isinstance(target, PoliceInterceptor):
            cx = target.x + target.w / 2
            cy = target.y + target.h / 2
            self.police_crashes.append(
                PoliceCrash(cx, cy, target.cell, target.vx, target.vy)
            )
        elif isinstance(target, CyberTank):
            cx = target.x + target.w / 2
            cy = target.y + target.h / 2
            self.tank_meltdowns.append(TankMeltdown(cx, cy, target.cell))
        elif isinstance(target, (CyberCaptor, JammerNode)):
            cx = target.x + target.w / 2
            cy = target.y + target.h / 2
            self._trigger_captor_emp(cx, cy, float(target.EMP_RADIUS))
        elif isinstance(target, SplitterTank):
            cx = target.x + target.w / 2
            cy = target.y + target.h / 2
            # tier 0: explosão menor (o "split" é o espetáculo); tier 1: explosão
            # cheia de morte. Ambos espalham destroços do chassi.
            size = 28 if target.tier == 0 else 30
            self.spawn_explosion(cx, cy, size=size, explosion_type=ExplosionType.CYBER)
            self.splitter_debris.append(SplitterDebris(cx, cy, target.tier))
            self.enemies.extend(target.make_children())
        elif isinstance(target, CargoCarrier):
            cx = target.x + target.w / 2
            cy = target.y + target.h / 2
            # Nave grande e pesada: explosão central + chassi estilhaçado em cacos.
            self.spawn_explosion(cx, cy, size=44, explosion_type=ExplosionType.CYBER)
            self.carrier_debris.append(CarrierDebris(cx, cy))

    def _trigger_captor_emp(self, cx: float, cy: float, radius: float) -> None:
        """EMP Discharge: onda amarela + neutraliza (limpa) os projéteis inimigos
        no raio — a "desativação" temporária da proposta."""
        self.captor_emps.append(CaptorEMP(cx, cy, radius))
        r2 = radius * radius
        for lst in (self.alien_bullets, self.serpent_bullets, self.energy_orbs, self.neon_bolts):
            for proj in lst:
                px = getattr(proj, "x", None)
                py = getattr(proj, "y", None)
                if px is None or py is None:
                    continue
                if (px - cx) ** 2 + (py - cy) ** 2 <= r2:
                    proj.dead = True

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

    def spawn_explosive_effect(
        self,
        x: float,
        y: float,
        radius: float = 60.0,
        damage: int = 50,
        delay: float = 0.0,
        color: tuple[int, int, int] = (255, 255, 255),
        lifetime: float = 0.4,
    ) -> None:
        self.explosive_effects.append(
            ExplosiveEffect(
                x, y, radius=radius, damage=damage, lifetime=lifetime,
                delay=delay, color=color,
            )
        )

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

    def spawn_black_hole(
        self, x: float, y: float, duration: float, is_vortex: bool = False
    ) -> None:
        self.black_holes.append(
            BlackHole(x, y, duration, self.is_side_scroll, is_vortex)
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
        target_entity: Any | None = None,
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
        owner_ship: Any | None = None,
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
            owner_ship=owner_ship,
        )
        self.cacador_lasers.append(laser)
        return laser

    def spawn_homing_bullet(
        self,
        x: float,
        y: float,
        damage: int,
        direction: tuple[float, float] | None = None,
        locked_target: Any | None = None,
        source_ship: Any | None = None,
    ) -> HomingBullet:
        """Spawna um tiro teleguiado consumível (Caçador).

        locked_target: inimigo que este projétil perseguirá exclusivamente enquanto
        estiver vivo. Permite distribuir alvos entre múltiplos projéteis simultâneos.
        source_ship: nave que originou o tiro (P1 vs P2). Necessário em coop
        para o gate "1 burst de homing por Caçador na tela".
        """
        homing = HomingBullet(
            x=x,
            y=y,
            damage=damage,
            is_side_scroll=self.is_side_scroll,
            direction=direction,
            locked_target=locked_target,
            source_ship=source_ship,
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

        self.enemy_projectile_grid.clear()
        for b in self.alien_bullets:
            if not b.dead:
                self.enemy_projectile_grid.insert_from_rect(b)
        for b in self.serpent_bullets:
            if not b.dead:
                self.enemy_projectile_grid.insert_from_rect(b)
        for o in self.energy_orbs:
            if not o.dead:
                self.enemy_projectile_grid.insert_from_rect(o)
        for b in self.neon_bolts:
            if not b.dead:
                self.enemy_projectile_grid.insert_from_rect(b)

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
        self._screen_size = (screen_width, screen_height)
        self._rebuild_enemy_caches()

        self._update_visual_effects(dt)

        new_alien_bullets: list[AlienBullet] = self._update_formations(dt, enemy_dt)
        self._update_player_projectiles(dt)
        self._update_enemy_projectiles(enemy_dt)
        self._update_misc_effects(dt)

        self._update_collectibles(
            dt, (player_x, player_y), attraction_mult, screen_width, screen_height
        )
        self._update_floating_scores_and_mini_ships(dt)

        self._update_spikes(dt, enemy_dt, player_x, player_y)
        self._update_boss(enemy_dt, player_x, player_y)

        ctx_emissions = self._update_enemies(
            dt, enemy_dt, player_x, player_y, screen_width, screen_height
        )
        new_alien_bullets.extend(ctx_emissions.new_alien_bullets)
        new_eye_lasers: list[EyeLaser] = list(ctx_emissions.new_eye_lasers)
        self.energy_orbs.extend(ctx_emissions.new_energy_orbs)
        self.neon_bolts.extend(ctx_emissions.new_neon_bolts)
        self.enemies.extend(ctx_emissions.new_enemies)
        # Inimigos "atrás": inseridos no início p/ desenhar antes (sob) os demais.
        if ctx_emissions.new_enemies_behind:
            self.enemies[:0] = ctx_emissions.new_enemies_behind
        self.area_blasts.extend(ctx_emissions.new_area_blasts)
        for _ex in ctx_emissions.new_explosions:
            self.spawn_explosion(*_ex)
        for _z in ctx_emissions.new_ice_zones:
            self.spawn_ice_poison_zone(*_z)

        self._update_mountain_propellers(dt)
        self._update_energy_orbs(dt)
        self._check_alien_collisions()
        self.alien_bullets.extend(new_alien_bullets)
        self.eye_lasers.extend(new_eye_lasers)

        self._update_environment(dt, enemy_dt)

        self.cleanup()
        self.rebuild_all_grids()

    # ------------------------------------------------------------------
    # Sub-passos de update() — extraídos para isolar fronteiras de domínio.
    # ------------------------------------------------------------------

    def _rebuild_enemy_caches(self) -> None:
        """Atualiza caches de inimigos consumidos por bullets homing / mini-ships."""
        self._cached_formation_enemies = []
        self._cached_all_enemies = list(self.enemies)
        
        # Incluir Rock Gliders ativos do pool
        self._cached_all_enemies.extend(self.rock_glider_pool.active)
        
        for f in self.formations:
            fe = f.get_enemies()
            self._cached_formation_enemies.extend(fe)
            self._cached_all_enemies.extend(fe)
        if self.boss:
            self._cached_all_enemies.append(self.boss)

    def _emp_state(self) -> tuple[bool, float]:
        slow_active = getattr(self, "emp_active", False)
        # O fator vale tanto durante o EMP global quanto no linger por inimigo
        # (que persiste depois da onda passar / do EMP acabar). Por isso NÃO
        # zera quando inativo — o "quando aplicar" é decidido em
        # _emp_multiplier (global + linger). Default = constante de config.
        slow_factor = getattr(self, "emp_slow_factor", EMP_SLOW_FACTOR)
        return slow_active, slow_factor

    def _update_visual_effects(self, dt: float) -> None:
        """Efeitos visuais com auto-cleanup: EMP, explosivos, zonas elementais, chain."""
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
        for cl in self.chain_lightnings[:]:
            cl.update(dt)
            if cl.dead:
                self.chain_lightnings.remove(cl)

    def _update_formations(self, dt: float, enemy_dt: float) -> list[AlienBullet]:
        """Tick das formações com EMP/ice; retorna alien_bullets emitidas."""
        new_alien_bullets: list[AlienBullet] = []
        slow_active, slow_factor = self._emp_state()
        for f in self.formations[:]:
            self._update_emp_linger(f, dt)
            self._update_ice_linger(f, dt)
            mul = self._emp_multiplier(
                f, slow_active, slow_factor, dt
            ) * self._ice_multiplier(f)
            shot = f.update(enemy_dt * mul)
            if shot:
                new_alien_bullets.extend(shot)
        return new_alien_bullets

    def _update_player_projectiles(self, dt: float) -> None:
        """Projéteis do jogador: bullets (com homing), homing dedicado, mini-ships, lasers."""
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
        for w in self.wingmen:
            w.update(dt, self._cached_all_enemies, self.mini_ship_bullets)
        for link in self.coop_links:
            link.update(dt)
        for s in self.orbital_shields:
            s.update(dt)
        for beam in self.plasma_beams:
            beam.update(dt)

    def _update_enemy_projectiles(self, enemy_dt: float) -> None:
        """Projéteis inimigos: alien/serpent/boss/eye (todos respeitam freeze)."""
        for b in self.alien_bullets:
            b.update(enemy_dt)
        for b in self.serpent_bullets:
            b.update(enemy_dt)
        for b in self.boss_lasers:
            b.update(enemy_dt)
        for b in self.eye_lasers:
            b.update(enemy_dt)
        for b in self.neon_bolts:
            b.update(enemy_dt)

    def _update_misc_effects(self, dt: float) -> None:
        """Pool de explosões e mine_explosions."""
        self.explosion_pool.update(dt)
        for me in self.mine_explosions:
            me.update(dt)
        for ci in self.core_implosions:
            ci.update(dt)
        for pc in self.police_crashes:
            pc.update(dt)
        for tm in self.tank_meltdowns:
            tm.update(dt)
            blast = tm.pop_blast()
            if blast is not None:
                self.area_blasts.append(blast)
        for sd in self.splitter_debris:
            sd.update(dt)
        for cd in self.carrier_debris:
            cd.update(dt)
        for ce in self.captor_emps:
            ce.update(dt)

    def _update_collectibles(
        self,
        dt: float,
        player_pos: tuple[float, float],
        attraction_mult: float,
        screen_width: int,
        screen_height: int,
    ) -> None:
        """Powerups e estrelas — suportam atração do Magneto."""
        for p in self.powerups:
            p.update(dt, attraction_pos=player_pos, attraction_mult=attraction_mult)
        for s in self.stars:
            s.update(
                dt,
                screen_width,
                screen_height,
                attraction_pos=player_pos,
                attraction_mult=attraction_mult,
            )

    def _update_floating_scores_and_mini_ships(self, dt: float) -> None:
        for fs in self.floating_scores:
            fs.update(dt)
        for ms in self.mini_ships:
            ms.update(dt, self, self.mini_ship_bullets)

    def _update_spikes(
        self, dt: float, enemy_dt: float, player_x: float, player_y: float
    ) -> None:
        ac = sum(1 for s in self.spikes if s.state in ("trembling", "flying"))
        slow_active, slow_factor = self._emp_state()
        for s in self.spikes:
            self._update_emp_linger(s, dt)
            self._update_ice_linger(s, dt)
            mul = self._emp_multiplier(
                s, slow_active, slow_factor, dt
            ) * self._ice_multiplier(s)
            s.update(enemy_dt * mul, player_x, player_y, ac)

    def _update_boss(self, enemy_dt: float, player_x: float, player_y: float) -> None:
        """Dispatch polimórfico via boss.update_boss(dt, ctx)."""
        if not self.boss:
            return
        ctx = BossUpdateContext(
            dt=enemy_dt,
            player_x=player_x,
            player_y=player_y,
            entity_manager=self,
        )
        result = self.boss.update_boss(enemy_dt, ctx)
        self._consume_boss_result(result)

    def _consume_boss_result(self, result: "BossUpdateResult") -> None:
        """Aplica as emissões de um BossUpdateResult aos grupos do EntityManager."""
        if result.new_lasers:
            self.boss_lasers.extend(result.new_lasers)
        if result.new_squares:
            self.boss_squares.extend(result.new_squares)
        if result.new_spikes:
            self.spikes.extend(result.new_spikes)
        if result.new_serpent_bullets:
            self.serpent_bullets.extend(result.new_serpent_bullets)
        if result.new_mines:
            self.boulders.extend(result.new_mines)
        if result.new_shards:
            self.attack_debris.extend(result.new_shards)
        if result.spawned_enemies:
            self.enemies.extend(result.spawned_enemies)
        if result.sound_events:
            self._dispatch_boss_sound_events(result.sound_events)

    def _update_enemies(
        self,
        dt: float,
        enemy_dt: float,
        player_x: float,
        player_y: float,
        screen_width: int,
        screen_height: int,
    ) -> EnemyUpdateContext:
        """Loop polimórfico via update_in_context — retorna ctx com emissões."""
        ctx = EnemyUpdateContext(
            dt=dt,
            sdt=0.0,
            player_x=player_x,
            player_y=player_y,
            is_side_scroll=self.is_side_scroll,
            screen_width=screen_width,
            screen_height=screen_height,
            other_enemies=self.enemies,
        )
        slow_active, slow_factor = self._emp_state()
        for en in self.enemies:
            self._update_emp_linger(en, dt)
            self._update_ice_linger(en, dt)
            mul = self._emp_multiplier(
                en, slow_active, slow_factor, dt
            ) * self._ice_multiplier(en)
            ctx.sdt = enemy_dt * mul
            update_in_ctx = getattr(en, "update_in_context", None)
            if update_in_ctx is not None:
                update_in_ctx(ctx)
            else:
                en.update(ctx.sdt)
        return ctx

    def _update_mountain_propellers(self, dt: float) -> None:
        for prop in self.mountain_propellers:
            prop.update(dt)
        self.mountain_propellers = [p for p in self.mountain_propellers if not p.dead]

    def _update_energy_orbs(self, dt: float) -> None:
        for o in self.energy_orbs:
            o.update(dt)

    def _update_environment(self, dt: float, enemy_dt: float) -> None:
        """Elementos dinâmicos: boss_squares, boulders/debris, bombs, towers, mines, black holes."""
        sw, sh = self._screen_size

        for q in self.boss_squares:
            q.update(enemy_dt, sw, sh)
        self._filter_dead_inplace(self.boss_squares)

        for m in self.boulders:
            es = m.update(dt)
            if es:
                self.attack_debris.extend(es)

        for s in self.attack_debris:
            s.update(dt)

        for b in self.air_strike_bombs:
            b.update(enemy_dt)
        self._filter_dead_inplace(self.air_strike_bombs)

        for t in self.cannon_towers:
            t.update(enemy_dt)
        self._filter_dead_inplace(self.cannon_towers)

        for m in self.cannon_mines:
            m.update(enemy_dt)
        self._filter_dead_inplace(self.cannon_mines)

        for b in self.black_holes:
            b.update(dt)
        for b in self.black_holes:
            b.process_all_enemies(
                self._cached_all_enemies, enemy_dt, self.spawn_explosion
            )

    def update_for_game_over_slow_motion(
        self, dt: float, player_x: float, player_y: float
    ) -> None:
        # Inimigos: dispatch polimórfico via update_in_context. sdt == dt
        # (sem EMP/ice em slow-motion). Cada inimigo traduz o ctx em sua
        # assinatura específica — sem cascata de isinstance aqui.
        sw, sh = self._screen_size
        ctx = EnemyUpdateContext(
            dt=dt,
            sdt=dt,
            player_x=player_x,
            player_y=player_y,
            is_side_scroll=self.is_side_scroll,
            screen_width=sw,
            screen_height=sh,
            other_enemies=self.enemies,
        )
        for en in self.enemies:
            update_in_ctx = getattr(en, "update_in_context", None)
            if update_in_ctx is not None:
                update_in_ctx(ctx)
            else:
                en.update(dt)

        # MiniShip exige listas explícitas de alvos/balas — em slow-motion
        # passamos vazias para evitar disparos durante a death sequence.
        for ms in self.mini_ships:
            ms.update(dt, self, [])

        # Demais grupos têm assinatura uniforme update(dt).
        uniform_groups: list[list[Any]] = [
            self.bullets,
            self.alien_bullets,
            self.serpent_bullets,
            self.boss_lasers,
            self.powerups,
            self.floating_scores,
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
        for g in uniform_groups:
            for e in g:
                e.update(dt)

        for f in self.formations:
            f.update(dt)
        self.explosion_pool.update(dt)

        if self.boss:
            ctx = BossUpdateContext(
                dt=dt,
                player_x=player_x,
                player_y=player_y,
                entity_manager=self,
            )
            self._consume_boss_result(self.boss.update_boss(dt, ctx))
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
                if getattr(e, "DRAWN_BY_POOL", False):
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
                # `draws_offscreen`: entidade quer desenhar mesmo fora da tela
                # (ex.: telegraph do CyberTank, cujo corpo ainda está fora da borda).
                if is_v(e) or getattr(e, "draws_offscreen", False):
                    if isinstance(e, EyeEnemy):
                        e.draw(surface, player_x, player_y)
                    else:
                        e.draw(surface)
            # Passe central de escudos (enemy_shield): sobre os corpos, abaixo
            # de projéteis/boss. Guard barato por getattr para a esmagadora
            # maioria sem escudo.
            for e in self.enemies:
                if getattr(e, "shield_hp", 0.0) > 0.0 and is_v(e):
                    enemy_shield.draw_shield(surface, e, getattr(e, "pulse", 0.0))
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
        for link in self.coop_links:
            link.draw(surface)
        for s in self.orbital_shields:
            s.draw(surface)
        for beam in self.plasma_beams:
            beam.draw(surface)
        for w in self.wingmen:
            w.draw(surface)
        for b in self.black_holes:
            b.draw(surface)
        for w in self.emp_waves:
            w.draw(surface)
        for zone in self.ice_poison_zones:
            zone.draw(surface)
        for zone in self.fire_zones:
            zone.draw(surface)

        # 4. Desenhar projéteis e efeitos de impacto (devem ficar SOBRE os inimigos)
        lists: list[list[Any]] = [
            self.bullets,
            self.homing_bullets,
            self.alien_bullets,
            self.energy_orbs,
            self.player_lasers,
            self.mini_ship_bullets,
            self.eye_lasers,
            self.neon_bolts,
            self.core_implosions,
            self.police_crashes,
            self.tank_meltdowns,
            self.splitter_debris,
            self.carrier_debris,
            self.captor_emps,
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

        # 5. Batch draw Chain Lightnings (Otimização de Performance)
        if self.chain_lightnings:
            sw, sh = surface.get_size()
            overlay = ChainLightning.get_shared_overlay(sw, sh)
            overlay.fill((0, 0, 0, 0))

            for cl in self.chain_lightnings:
                cl.draw_to_surface(overlay)

            surface.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

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

    def spawn_wingman(self, player: Any, duration: float) -> Wingman:
        wingman = Wingman(player, duration)
        self.wingmen.append(wingman)
        return wingman

    def spawn_coop_link(self, ship1: Any, ship2: Any, duration: float) -> CoopLink:
        link = CoopLink(ship1, ship2, duration)
        self.coop_links.append(link)
        return link

    def spawn_orbital_shield(self, ship: Any, duration: float) -> list[OrbitalShield]:
        shields: list[OrbitalShield] = []
        for i in range(3): # Agora são três escudos
            s: OrbitalShield = OrbitalShield(ship, duration, index=i, total=3)
            self.orbital_shields.append(s)
            shields.append(s)
        return shields

    def spawn_plasma_beam(self, ship: Any, duration: float) -> PlasmaBeam:
        beam = PlasmaBeam(ship, duration)
        self.plasma_beams.append(beam)
        return beam

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
        direction: tuple[float, float] | None = None,
        ship_id: str = "padrao",
        owner_ship: Any | None = None,
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
            owner_ship=owner_ship,
        )
        if homing:
            target = self._assign_homing_target(bullet)
            if target:
                bullet.assign_target(target)
        self.bullets.append(bullet)
        return bullet

    def _assign_homing_target(self, bullet: Bullet) -> Any:
        all_e: list[Any] = list(self.enemies)
        for f in self.formations:
            if not getattr(f, "dead", True):
                all_e.extend(f.get_enemies())
        if self.boss and not getattr(self.boss, "dead", True):
            all_e.append(self.boss)

        alive = [e for e in all_e if not getattr(e, "dead", True)]
        if not alive:
            return None

        counts: dict[int, int] = {}
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
        sw, sh = self._screen_size

        if self.is_side_scroll:
            return enemy.x < -(ew + sw * 0.2) or enemy.y < -eh or enemy.y > sh

        # Para a Serpente, permitimos que os blocos existam abaixo do limite inferior (spawn)
        if isinstance(enemy, SerpentBlock):
            return enemy.y < -eh or enemy.x < -ew or enemy.x > sw

        # Entidades de spawn invertido (re-entry/entering: sobem de baixo pra
        # cima) nascem ABAIXO do rodapé e saem pelo topo. Sem isto, eram mortas
        # no spawn (y > sh) — por isso satélites/destroços sumiam no re-entry.
        if getattr(enemy, "inverted_vertical", False):
            return enemy.y < -eh or enemy.x < -ew or enemy.x > sw

        return enemy.y > sh or enemy.x < -ew or enemy.x > sw

    def is_on_screen(self, entity: Any) -> bool:
        """True se o rect da entidade intersecta a área visível (teste estrito).

        Difere de ``_is_enemy_off_screen``, que — por regra de gameplay — mantém
        "vivos" inimigos ACIMA do topo prestes a entrar. Aqui o teste é estrito:
        usado pela progressão de fase ("há hostil VISÍVEL?"). Assim, formações
        ainda paradas acima do topo (``y = -100`` durante a entrada), ou qualquer
        hostil já fora da área por qualquer borda, NÃO seguram o avanço quando a
        tela está visualmente vazia.
        """
        sw, sh = self._screen_size
        ew = getattr(entity, "w", getattr(getattr(entity, "rect", None), "width", 50))
        eh = getattr(entity, "h", getattr(getattr(entity, "rect", None), "height", 50))
        x = getattr(entity, "x", 0.0)
        y = getattr(entity, "y", 0.0)
        return x + ew > 0 and x < sw and y + eh > 0 and y < sh

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
        self._filter_dead_inplace(self.neon_bolts)
        self._filter_dead_inplace(self.core_implosions)
        self._filter_dead_inplace(self.police_crashes)
        self._filter_dead_inplace(self.tank_meltdowns)
        self._filter_dead_inplace(self.splitter_debris)
        self._filter_dead_inplace(self.carrier_debris)
        self._filter_dead_inplace(self.captor_emps)
        self._filter_dead_inplace(self.mini_ship_bullets)
        self._filter_dead_inplace(self.wingmen)
        self._filter_dead_inplace(self.coop_links)
        self._filter_dead_inplace(self.orbital_shields)
        
        # PlasmaBeam: disparar explosão final antes de remover
        for beam in self.plasma_beams:
            if beam.dead and hasattr(beam, "trigger_final_explosion"):
                beam.trigger_final_explosion(self)
                
        self._filter_dead_inplace(self.plasma_beams)
        self._filter_dead_inplace(self.chain_lightnings)

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
        self._filter_dead_inplace(self.black_holes)
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
        self.neon_bolts.clear()
        self.core_implosions.clear()
        self.police_crashes.clear()
        self.tank_meltdowns.clear()
        self.splitter_debris.clear()
        self.carrier_debris.clear()
        self.captor_emps.clear()
        self.area_blasts.clear()
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
        self.chain_lightnings.clear()
        self.formations.clear()
        self.spikes.clear()
        self.meteor_pool.clear_active()
        self.rock_glider_pool.clear_active()
        self.bullet_pool.clear_active()
        self.explosion_pool.clear_active()
        self.enemy_spatial_grid.clear()
        self.spike_spatial_grid.clear()
        self.enemy_projectile_grid.clear()
        self._grid_needs_rebuild = True

    def clear_for_level_transition(self) -> None:
        self.alien_bullets.clear()
        self.serpent_bullets.clear()
        self.energy_orbs.clear()
        self.boss_squares.clear()
        self.eye_lasers.clear()
        self.neon_bolts.clear()
        self.core_implosions.clear()
        self.police_crashes.clear()
        self.tank_meltdowns.clear()
        self.splitter_debris.clear()
        self.carrier_debris.clear()
        self.captor_emps.clear()
        self.area_blasts.clear()
        # homing_bullets e cacador_lasers são projéteis do jogador — preservados
        # pela mesma razão que air_strike_bombs e black_holes (ver comentário abaixo).
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
        self.enemy_projectile_grid.clear()
        self._grid_needs_rebuild = True

    def get_stats(self) -> dict[str, Any]:
        return {
            "bullets": len(self.bullets),
            "enemies": len(self.enemies),
            "formations": len(self.formations),
            "explosions_active": self.explosion_pool.get_stats()["active"],
            "grid_stats": self.enemy_spatial_grid.get_statistics(),
        }
