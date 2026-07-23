from typing import TYPE_CHECKING, Any, Callable, Sequence, TypeAlias, cast

import pygame

from ..core.config import config as config_instance
from ..core.sound import sound_manager
from ..core.spatial_grid import SpatialGrid
from ..core.upgrades_config import EXPLOSIVE_BULLET_DAMAGE
from ..core.upgrades_config import EXPLOSIVE_BULLET_RADIUS as _EXPLOSIVE_BULLET_RADIUS
from ..entities.air_strike_bomb import AirStrikeBomb
from ..entities.boss_laser import BossLaser
from ..entities.boss_square import BossSquare
from ..entities.bot_elemental_attacks import EnergyOrb
from ..entities.bullet import Bullet
from ..entities.cannon_mine import CannonMine, MineState
from ..entities.chain_lightning import ChainLightning
from ..entities.explosion import ExplosionType
from ..entities.explosive_effect import ExplosiveEffect
from ..entities.eye_laser import EyeLaser
from ..entities.fire_zone import FireZone
from ..entities.floating_score import FloatingScore
from ..entities.homing_bullet import HomingBullet
from ..entities.impact_styles import (
    ImpactStyle,
    impact_for_projectile,
    impact_scale_for_projectile,
)
from ..entities.Inimigos_Tema_Cidade.neon_bolt import NeonBolt
from ..entities.electric_field_zone import ElectricFieldZone
from ..entities.ice_poison_zone import IcePoisonZone
from ..entities.orbital_energy_orb import OrbitalEnergyOrb
from ..entities.mine_explosion import MineExplosion
from ..entities.mini_ship_bullet import MiniShipBullet
from ..entities.player_laser import PlayerLaser
from ..entities.powerup import PowerUp
from ..entities.ship import Ship
from ..entities.slime_drip import SlimeDrip
from ..entities.spike import Spike
from ..entities.spike_boss_laser import SpikeBossLaser
from ..entities.star import Star
from .collision_physics import (
    CollisionPhysics,
    get_enemy_collision_mask_data,
    get_rect_mask,
)
from .collision_protocols import Damageable, Enemy
from .hit_result import HitResult

if TYPE_CHECKING:
    from ..core.events import EventBus
    from .entity_manager import EntityManager


Projectile: TypeAlias = Bullet | MiniShipBullet


def _point_segment_dist_sq(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    """Distância² do ponto (px,py) ao segmento A-B. Quadrado para evitar sqrt
    no hot path — o chamador compara contra raio²."""
    abx, aby = bx - ax, by - ay
    seg_sq = abx * abx + aby * aby
    if seg_sq < 1e-6:
        dx, dy = px - ax, py - ay
        return dx * dx + dy * dy
    t = ((px - ax) * abx + (py - ay) * aby) / seg_sq
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    dx = px - (ax + abx * t)
    dy = py - (ay + aby * t)
    return dx * dx + dy * dy


# Constantes de colisão
class CollisionConstants:
    SPATIAL_QUERY_PADDING = 10
    DEFAULT_EXPLOSION_SIZE = 20
    AREA_EXPLOSION_SIZE = 30
    BOSS_EXPLOSION_SIZE = 100
    SPIKE_EXPLOSION_SIZE = 15
    MINE_DAMAGE_DEFAULT = 2
    MINE_DAMAGE_AIRSTRIKE = 5
    EXPLOSIVE_BULLET_RADIUS = _EXPLOSIVE_BULLET_RADIUS
    ICE_SLOW_DURATION = 0.15


class Collisions:
    def __init__(self, event_bus: "EventBus | None" = None) -> None:
        self._event_bus = event_bus
        # Helpers de física extraídos. Os métodos `_apply_*` / `_check_*` /
        # `_batch_*` abaixo viraram thin wrappers para preservar os ~28 call
        # sites internos sem mudanças.
        self.physics = CollisionPhysics(event_bus)

    @staticmethod
    def _get_points_value(enemy: Any) -> int:
        """Retorna pontos de forma segura para entidades que suportam score."""
        getter = getattr(enemy, "get_points_value", None)
        if callable(getter):
            return int(cast(Callable[[], int], getter)())
        return 0

    @staticmethod
    def _get_ship_contact_hitboxes(enemy: Any) -> tuple[pygame.Rect, ...]:
        """Retorna hitboxes de contato com a nave, com fallback para enemy.rect."""
        getter = getattr(enemy, "get_ship_contact_hitboxes", None)
        if callable(getter):
            raw_hitboxes = cast(Callable[[], Sequence[pygame.Rect]], getter)()
            hitboxes = tuple(
                rect for rect in raw_hitboxes if rect.width > 0 and rect.height > 0
            )
            if hitboxes:
                return hitboxes

        enemy_rect: pygame.Rect = (
            enemy.rect
            if hasattr(enemy, "rect")
            else cast(
                pygame.Rect,
                getattr(enemy, "get_rect", lambda: pygame.Rect(0, 0, 0, 0))(),
            )
        )
        if enemy_rect.width <= 0 or enemy_rect.height <= 0:
            return ()
        return (enemy_rect,)

    # Wrappers thin para as primitivas migradas a `collision_physics.py`.
    # Mantidos como staticmethods para preservar chamadas `cls._get_*(...)`.
    @staticmethod
    def _get_enemy_collision_mask_data(
        enemy: Any,
    ) -> tuple[pygame.mask.Mask, tuple[int, int]] | None:
        return get_enemy_collision_mask_data(enemy)

    @staticmethod
    def _get_rect_mask(width: int, height: int) -> pygame.mask.Mask:
        return get_rect_mask(width, height)

    @staticmethod
    def _credit_kill(projectile: Any) -> None:
        """Notifica a nave que disparou o projétil sobre o kill.

        Usa duck typing: tenta `owner_ship` (Bullet, MiniShipBullet, BossLaser),
        `source_ship` (HomingBullet) e `ship` (PlayerLaser) nessa ordem. Sem
        owner_ship rastreável (ex.: AoE de mina), kill não é atribuído — combo
        do Reverberador não conta para "spray and pray".
        """
        owner = (
            getattr(projectile, "owner_ship", None)
            or getattr(projectile, "source_ship", None)
            or getattr(projectile, "ship", None)
        )
        if owner is not None and hasattr(owner, "register_kill"):
            owner.register_kill()

    @staticmethod
    def _circles_collide(
        c1_x: float,
        c1_y: float,
        c1_r: float,
        c2_x: float,
        c2_y: float,
        c2_r: float,
    ) -> bool:
        """Verifica colisão entre dois círculos (distância < r1 + r2).

        Otimizado: compara distância ao quadrado para evitar sqrt.
        """
        dx = c2_x - c1_x
        dy = c2_y - c1_y
        sum_radii = c1_r + c2_r
        return (dx * dx + dy * dy) < (sum_radii * sum_radii)

    @classmethod
    def _rect_collides_with_enemy(cls, rect: pygame.Rect, enemy: Any) -> bool:
        """Colisão híbrida: AABB (rápido) → Círculo (preciso) quando disponível.

        Para objetos redondos (SerpentBlock, etc), usa collision_circle() como
        validação secundária após AABB pass. Evita falsos positivos nas diagonais.
        """
        # Tentativa 1: Colisão por máscara (mask-based, pixel-perfect)
        mask_data = cls._get_enemy_collision_mask_data(enemy)
        if mask_data is not None:
            enemy_mask, (enemy_x, enemy_y) = mask_data
            enemy_mask_rect = pygame.Rect(
                enemy_x,
                enemy_y,
                enemy_mask.get_size()[0],
                enemy_mask.get_size()[1],
            )
            if not rect.colliderect(enemy_mask_rect):
                return False

            rect_mask = cls._get_rect_mask(rect.width, rect.height)
            overlap = rect_mask.overlap(
                enemy_mask, (enemy_x - rect.x, enemy_y - rect.y)
            )
            return overlap is not None

        # Tentativa 2: Colisão por hitbox retangular
        hitboxes = cls._get_ship_contact_hitboxes(enemy)
        if hitboxes:
            for hitbox in hitboxes:
                if rect.colliderect(hitbox):
                    # Validação secundária: se o inimigo oferece collision_circles() ou collision_circle(),
                    # valida com círculos para ser mais preciso (evita falsos positivos)
                    proj_cx, proj_cy = float(rect.centerx), float(rect.centery)
                    proj_r = float(max(rect.width, rect.height) / 2.0)

                    # Tenta múltiplos círculos primeiro
                    circles_getter = getattr(enemy, "collision_circles", None)
                    if callable(circles_getter):
                        try:
                            circles = cast(
                                "Sequence[tuple[float, float, float]]", circles_getter()
                            )
                            for cx, cy, r in circles:
                                if cls._circles_collide(proj_cx, proj_cy, proj_r, cx, cy, r):
                                    return True
                            return False # Estava no rect mas fora de todos os círculos específicos
                        except (TypeError, ValueError):
                            pass

                    # Fallback para círculo único
                    if hasattr(enemy, "collision_circle") and callable(
                        enemy.collision_circle
                    ):
                        try:
                            circle_data: tuple[float, float, float] = cast(
                                tuple[float, float, float], enemy.collision_circle()
                            )
                            enemy_cx, enemy_cy, enemy_r = circle_data
                            return cls._circles_collide(
                                proj_cx, proj_cy, proj_r, enemy_cx, enemy_cy, enemy_r
                            )
                        except (TypeError, ValueError):
                            # Fallback caso collision_circle() não retorne formato esperado
                            return True
                    return True
            return False

        return False

    @classmethod
    def _ship_collides_with_enemy(cls, ship_rect: pygame.Rect, enemy: Any) -> bool:
        """Verifica colisao da nave usando hitbox custom quando disponivel."""
        return cls._rect_collides_with_enemy(ship_rect, enemy)

    @classmethod
    def _projectile_collides_with_enemy(
        cls, projectile_rect: pygame.Rect, enemy: Any
    ) -> bool:
        """Verifica colisao de projeteis com suporte a hitboxes customizadas."""
        return cls._rect_collides_with_enemy(projectile_rect, enemy)

    def _process_projectile_hit(
        self,
        projectile: Projectile,
        hit_x: float,
        hit_y: float,
        entity_manager: "EntityManager",
        create_explosion: bool = True,
        explosion_size: int = 15,
    ) -> bool:
        """
        Processa hit de projétil (explosão visual, destruição).

        Args:
            create_explosion: Se True, cria explosão visual

        Returns:
            True se projétil foi destruído, False se é piercing
        """
        is_piercing = getattr(projectile, "piercing", False)

        if create_explosion and explosion_size > 0:
            # Impacto contra obstáculo (não é `apply_hit`, que só trata dano a
            # entidades): usa o estilo da nave direto, já que não existe um
            # HitResult com paleta de tema para respeitar aqui.
            impact = impact_for_projectile(projectile)
            if impact is not None:
                entity_manager.spawn_explosion(
                    hit_x,
                    hit_y,
                    size=explosion_size,
                    explosion_type=impact.palette,
                    pattern=impact.pattern,
                )
            else:
                entity_manager.spawn_explosion(hit_x, hit_y, size=explosion_size)

        if not is_piercing:
            projectile.dead = True

        return not is_piercing

    def _check_mask_collision(
        self,
        entity_rect: pygame.Rect,
        entity_mask: pygame.mask.Mask | None,
        target_with_mask: Any,
        entity_x: float,
        entity_y: float,
    ) -> bool:
        return self.physics.check_mask_collision(
            entity_rect, entity_mask, target_with_mask, entity_x, entity_y
        )

    def _batch_query_for_projectiles(
        self,
        projectiles: Sequence[Projectile],
        grid: SpatialGrid[Any],
        padding: int = CollisionConstants.SPATIAL_QUERY_PADDING,
    ) -> dict[int, list[Enemy]]:
        return self.physics.batch_query_for_projectiles(projectiles, grid, padding)

    def _apply_hit(
        self,
        target: Any,
        damage: int,
        hit_x: float,
        hit_y: float,
        entity_manager: "EntityManager",
        floating_scores: list[FloatingScore] | None = None,
        impact: ImpactStyle | None = None,
        impact_scale: float = 1.0,
    ) -> HitResult:
        return self.physics.apply_hit(
            target,
            damage,
            hit_x,
            hit_y,
            entity_manager,
            floating_scores,
            impact,
            impact_scale,
        )

    def _apply_ship_contact(
        self,
        target: Any,
        contact_x: float,
        contact_y: float,
        entity_manager: "EntityManager",
    ) -> HitResult:
        return self.physics.apply_ship_contact(
            target, contact_x, contact_y, entity_manager
        )

    def _apply_area_damage(
        self,
        source_x: float,
        source_y: float,
        damage_radius: float,
        hit_tracking_set: set[int],
        enemies: Sequence[Enemy],
        entity_manager: "EntityManager",
        damage: int = 1,
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        return self.physics.apply_area_damage(
            source_x,
            source_y,
            damage_radius,
            hit_tracking_set,
            enemies,
            entity_manager,
            damage,
        )

    def _aoe_into_boss(
        self,
        boss: Any,
        source_x: float,
        source_y: float,
        damage_radius: float,
        damage: int,
        hit_set: set[int],
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Aplica dano em área a um boss via boss.on_hit, evitando dupla-contagem."""
        if not boss or boss.dead or damage_radius <= 0:
            return 0
        boss_id = id(boss)
        if boss_id in hit_set:
            return 0

        # Usar o novo protocol para geometria
        cx, cy, _ = boss.collision_circle()
        dx = source_x - cx
        dy = source_y - cy
        if dx * dx + dy * dy > damage_radius * damage_radius:
            return 0

        scaled = int(damage * config_instance.BOSS_UPGRADE_DAMAGE_MULTIPLIER)
        result = self._apply_hit(boss, scaled, cx, cy, entity_manager, floating_scores)
        hit_set.add(boss_id)
        return result.points

    def _project_into_boss(
        self,
        projectiles: Sequence[Any],
        boss: Any,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
        is_piercing_allowed: bool = False,
    ) -> int:
        """Helper para dano unificado ao boss via boss.on_hit."""
        score_gain = 0
        if not projectiles or not boss or boss.dead:
            return 0

        for proj in projectiles[:]:
            if proj.dead or not self._check_mask_collision(
                proj.rect, None, boss, proj.x, proj.y
            ):
                continue

            if not (is_piercing_allowed and getattr(proj, "piercing", False)):
                proj.dead = True

            # Nerf global de upgrade + nerf por-projétil (Wingman tem o seu;
            # demais projéteis usam 1.0 via getattr → sem mudança).
            damage = int(
                proj.damage
                * config_instance.BOSS_UPGRADE_DAMAGE_MULTIPLIER
                * getattr(proj, "boss_damage_mult", 1.0)
            )
            result = self._apply_hit(
                boss,
                damage,
                proj.x,
                proj.y,
                entity_manager,
                floating_scores,
                impact=impact_for_projectile(proj),
                impact_scale=impact_scale_for_projectile(proj),
            )
            score_gain += result.points

        return score_gain

    def check_mine_explosions(
        self,
        enemies: Sequence[Enemy],
        mine_explosions: list[MineExplosion],
        ships: Sequence[Ship],
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]], set[int]]:
        """
        Processa explosões de minas.

        Fluxo:
        1) Quando uma mina está explodindo E seu timer acabou, cria MineExplosion visual.
        2) Processa explosões ativas usando raio máximo para causar dano.

        IMPORTANTE: Verificamos is_exploding + pre_explosion_timer <= 0 porque
        a mina só fica dead=True quando o timer acaba internamente.

        Retorna set de `id(ship)` para cada nave atingida pela explosão.
        """
        if not enemies:
            return 0, 0, [], set()

        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []
        ship_hits: set[int] = set()

        # 1) Criar explosões para minas cujo timer de explosão acabou
        for enemy in enemies:
            if getattr(enemy, "is_explosive_mine", False):
                mine: Any = enemy
                should_explode = mine.is_exploding and (
                    (mine.pre_explosion_timer <= 0 and not mine.dead) or mine.dead
                )
                if should_explode:
                    cx, cy = (mine.x, mine.y)
                    explosion_radius = mine.explosion_radius

                    mine_explosions.append(MineExplosion(cx, cy, size=explosion_radius))

                    # Checar todas as naves vivas e limpar formações
                    ship_hits.update(
                        self.handle_mine_explosion(
                            cx, cy, explosion_radius, ships, entity_manager
                        )
                    )

                    sound_manager.play_explosion_boss()

                    # Marcar como dead DEPOIS de criar explosão
                    mine.dead = True
                    if getattr(mine, "spawns_ice_zone", False):
                        entity_manager.spawn_ice_poison_zone(cx, cy, explosion_radius)
                    # Resíduos energéticos da Neon City: explosões secundárias
                    # menores, em cadeia, DENTRO do raio principal (a própria mina
                    # calcula as posições/atrasos; aqui só orquestramos o spawn).
                    if getattr(mine, "spawns_neon_residue", False):
                        for spec in mine.residue_bursts(cx, cy, explosion_radius):
                            entity_manager.spawn_explosive_effect(**spec)

                    pts = self._get_points_value(mine)
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

            for enemy in enemies:
                if enemy.dead:
                    continue

                enemy_id = id(enemy)
                if enemy_id in explosion.hit_ids:
                    continue

                enemy_cx, enemy_cy, enemy_r = enemy.collision_circle()

                dist_sq = (enemy_cx - explosion_x) ** 2 + (enemy_cy - explosion_y) ** 2

                if dist_sq < (explosion_radius + enemy_r) ** 2:
                    explosion.hit_ids.add(enemy_id)
                    # Mine explosion mata outras minas com dano = HP delas;
                    # demais inimigos recebem dano nominal e on_hit resolve.
                    hit_damage = (
                        enemy.health
                        if getattr(enemy, "is_explosive_mine", False)
                        else 50  # Dano fixo de explosão de mina inimiga
                    )
                    result = self._apply_hit(
                        enemy,
                        hit_damage,
                        enemy_cx,
                        enemy_cy,
                        entity_manager,
                    )
                    score_gain += result.points
                    if result.killed:
                        destroyed_count += 1
                        if result.points > 0:
                            score_events.append((enemy_cx, enemy_cy, result.points))

        return score_gain, destroyed_count, score_events, ship_hits

    def ice_poison_zones_vs_entities(
        self,
        zones: list[IcePoisonZone],
        enemies: Sequence[Any],
        ships: Sequence[Ship],
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        for zone in zones:
            if zone.dead:
                continue

            for ship in ships:
                if zone.in_zone(ship.x, ship.y):
                    ship.speed_modifier_timer = max(ship.speed_modifier_timer, 0.15)

            for enemy in enemies:
                if enemy.dead:
                    continue
                cx, cy, r = enemy.collision_circle()
                if not zone.in_zone(cx, cy, r):
                    continue

                setattr(enemy, "_ice_slow_timer", CollisionConstants.ICE_SLOW_DURATION)

                eid = id(enemy)
                if zone.can_damage(eid):
                    zone.register_hit(eid)
                    result = self._apply_hit(enemy, 1, cx, cy, entity_manager)
                    score_gain += result.points
                    if result.killed:
                        destroyed_count += 1
                        if result.points > 0:
                            score_events.append((cx, cy, result.points))

        return score_gain, destroyed_count, score_events

    def fire_zones_vs_entities(
        self,
        zones: list[FireZone],
        enemies: Sequence[Any],
        ships: Sequence[Ship],
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]], set[int]]:
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []
        ship_hits: set[int] = set()

        for zone in zones:
            if zone.dead:
                continue

            for ship in ships:
                if ship.invuln > 0:
                    continue
                ship_cx = ship.x + ship.w / 2
                ship_cy = ship.y + ship.h / 2
                if zone.in_zone(ship_cx, ship_cy):
                    ship_eid = id(ship)
                    if zone.can_damage(ship_eid):
                        zone.register_hit(ship_eid)
                        ship_hits.add(ship_eid)

            for enemy in enemies:
                if enemy.dead:
                    continue
                cx, cy, r = enemy.collision_circle()
                if not zone.in_zone(cx, cy, r):
                    continue

                eid = id(enemy)
                if zone.can_damage(eid):
                    zone.register_hit(eid)
                    result = self._apply_hit(enemy, 1, cx, cy, entity_manager)
                    score_gain += result.points
                    if result.killed:
                        destroyed_count += 1
                        if result.points > 0:
                            score_events.append((cx, cy, result.points))

        return score_gain, destroyed_count, score_events, ship_hits

    def handle_mine_explosion(
        self,
        explosion_x: float,
        explosion_y: float,
        explosion_radius: int,
        ships: Sequence[Ship],
        entity_manager: "EntityManager",
    ) -> set[int]:
        """
        Checa colisão da explosão de mina com cada nave e limpa formações.

        Retorna set de `id(ship)` para cada nave atingida pela explosão.
        """
        ship_hits: set[int] = set()

        # Limpar inimigos mortos das formações (para marcar formação como dead).
        # Delegado ao próprio Formation — Collisions não conhece a representação
        # interna da lista de inimigos.
        for formation in entity_manager.formations:
            formation.remove_dead_enemies()

        for ship in ships:
            if ship.invuln > 0:
                continue
            ship_cx = ship.x + ship.w / 2
            ship_cy = ship.y + ship.h / 2
            ship_r = ship.w / 2

            dist_sq = (ship_cx - explosion_x) ** 2 + (ship_cy - explosion_y) ** 2
            if dist_sq < (explosion_radius + ship_r) ** 2:
                entity_manager.spawn_explosion(
                    ship.x + ship.w / 2,
                    ship.y + ship.h / 2,
                    size=CollisionConstants.AREA_EXPLOSION_SIZE,
                )
                ship_hits.add(id(ship))
        return ship_hits

    def explosive_effects_vs_enemies(
        self,
        explosive_effects: list[ExplosiveEffect],
        enemies: Sequence[Enemy],
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Verifica colisão contínua entre efeitos explosivos ativos e inimigos."""
        if not explosive_effects:
            return 0, 0, []

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
            gain, destroyed, hit_events = self._apply_area_damage(
                effect.x,
                effect.y,
                damage_radius,
                effect.hit_enemies,
                enemies,
                entity_manager,
                damage=effect.damage,
            )
            score_gain += gain
            destroyed_count += destroyed
            score_events.extend(hit_events)

        return score_gain, destroyed_count, score_events

    def explosive_effects_vs_boss(
        self,
        explosive_effects: list[ExplosiveEffect],
        boss: Any,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Verifica colisão entre efeitos explosivos e boss."""
        if not explosive_effects or not boss or boss.dead:
            return 0
        score_gain = 0
        for effect in explosive_effects:
            if not effect.damage_active:
                continue
            score_gain += self._aoe_into_boss(
                boss,
                effect.x,
                effect.y,
                effect.current_damage_radius,
                effect.damage,
                effect.hit_enemies,
                floating_scores,
                entity_manager,
            )
        return score_gain

    def air_strike_bombs_vs_enemies(
        self,
        air_strike_bombs: list[AirStrikeBomb],
        enemies: Sequence[Enemy],
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Verifica colisão entre explosões de bombas e inimigos."""
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
            gain, destroyed, hit_events = self._apply_area_damage(
                bomb.x,
                bomb.target_y,
                damage_radius,
                bomb.hit_enemies,
                enemies,
                entity_manager,
                damage=bomb.damage,
            )
            score_gain += gain
            destroyed_count += destroyed
            score_events.extend(hit_events)

        return score_gain, destroyed_count, score_events

    def cannon_mines_vs_enemies(
        self,
        cannon_mines: list[CannonMine],
        enemies: Sequence[Enemy],
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Verifica colisão entre minas de torres e inimigos."""
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        for mine in cannon_mines[:]:
            # Processar qualquer mina que tenha dano ativo
            damage_info = mine.damage_info
            if damage_info.radius > 0:
                # Aplicar dano em área contínuo
                gain, destroyed, hit_events = self._apply_area_damage(
                    damage_info.x,
                    damage_info.y,
                    damage_info.radius,
                    mine.hit_tracking_set,
                    enemies,
                    entity_manager,
                    damage=damage_info.damage,
                )
                score_gain += gain
                destroyed_count += destroyed
                score_events.extend(hit_events)

            # Verificar colisão para ativação de minas armadas
            if not mine.dead and mine.state == MineState.ARMED:
                for enemy in enemies:
                    if enemy.dead:
                        continue

                    if mine.check_enemy_collision(enemy):  # type: ignore[arg-type]
                        break  # Mina explodiu, sair do loop de inimigos

        return score_gain, destroyed_count, score_events

    def cannon_mines_vs_boss(
        self,
        cannon_mines: list[CannonMine],
        boss: Any,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Verifica colisão entre minas de torres e boss."""
        if not cannon_mines or not boss or boss.dead:
            return 0

        score_gain = 0
        for mine in cannon_mines:
            if mine.dead:
                continue

            damage_info = mine.damage_info
            score_gain += self._aoe_into_boss(
                boss,
                damage_info.x,
                damage_info.y,
                damage_info.radius,
                damage_info.damage,
                mine.hit_tracking_set,
                floating_scores,
                entity_manager,
            )

        return score_gain

    def air_strike_bombs_vs_boss(
        self,
        air_strike_bombs: list[AirStrikeBomb],
        boss: Any,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Verifica colisão entre explosões de bombas e boss."""
        if not air_strike_bombs or not boss or boss.dead:
            return 0
        score_gain = 0
        for bomb in air_strike_bombs:
            if not bomb.exploding or not bomb.damage_active:
                continue
            score_gain += self._aoe_into_boss(
                boss,
                bomb.x,
                bomb.target_y,
                bomb.explosion_radius,
                bomb.damage,
                bomb.hit_enemies,
                floating_scores,
                entity_manager,
            )
        return score_gain

    def projectiles_vs_enemies(
        self,
        projectiles: list[Projectile],
        enemy_grid: SpatialGrid[Any],
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Projéteis do jogador (Bullet e MiniShipBullet) vs. inimigos normais.

        Chain Shot é avaliado por bala via `owner_ship`: em coop, cada nave
        encadeia conforme o seu próprio `has_chain_shot` (P2 coletar o powerup
        ativa o efeito nas balas do P2, independente do estado do P1).
        Explosive e chain shot são ativados via duck typing — MiniShipBullet não os
        possui, então os caminhos especiais são automaticamente ignorados.
        """
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        if not projectiles:
            return 0, 0, []

        projectile_targets = self._batch_query_for_projectiles(
            projectiles,
            enemy_grid,
            padding=CollisionConstants.SPATIAL_QUERY_PADDING,
        )

        for b in projectiles[:]:
            if getattr(b, "dead", False):
                continue  # ex.: bloqueada pelo feixe do Tesla Twin neste frame
            potential_enemies = projectile_targets.get(id(b), [])
            if not potential_enemies:
                continue

            owner = getattr(b, "owner_ship", None)
            bullet_chain_active = owner is not None and getattr(
                owner, "has_chain_shot", False
            )
            # Uma vez por bala, não por inimigo atingido: o estilo não muda
            # entre os alvos da mesma bala (piercing acerta vários).
            impact = impact_for_projectile(b)
            impact_scale = impact_scale_for_projectile(b)

            for enemy in potential_enemies:
                if enemy.dead:
                    continue
                if self._projectile_collides_with_enemy(b.rect, enemy):
                    result = self._apply_hit(
                        enemy,
                        getattr(b, "damage", 1),
                        b.x,
                        b.y,
                        entity_manager,
                        impact=impact,
                        impact_scale=impact_scale,
                    )
                    score_gain += result.points
                    if result.killed:
                        destroyed_count += 1
                        self._credit_kill(b)
                        if result.points > 0:
                            score_events.append((b.x, b.y, result.points))

                    if bullet_chain_active:
                        already_hit: set[int] = set()
                        # Combos com a família de modificadores de tiro:
                        # Giant → +1 salto (arco mais longo); Explosive → cada
                        # salto detona uma mini-explosão (teia de estilhaços).
                        is_giant_bullet = getattr(b, "size_multiplier", 1.0) > 1.0
                        extra_jumps = 1 if is_giant_bullet else 0
                        eg, ed, ee = self._trigger_chain_shot(
                            hit_x=b.x,
                            hit_y=b.y,
                            source_enemy=enemy,
                            bullet_damage=getattr(b, "damage", 1),
                            jumps_left=config_instance.CHAIN_SHOT_MAX_JUMPS
                            + extra_jumps,
                            already_hit=already_hit,
                            enemy_grid=enemy_grid,
                            entity_manager=entity_manager,
                            owner_ship=owner,
                            explosive=getattr(b, "explosive", False),
                        )
                        score_gain += eg
                        destroyed_count += ed
                        score_events.extend(ee)

                    if getattr(b, "explosive", False) and not b.dead:
                        eg, ed, ee = self._handle_explosive_bullet(
                            cast(Bullet, b), enemy_grid, entity_manager
                        )
                        score_gain += eg
                        destroyed_count += ed
                        score_events.extend(ee)

                    if self._process_projectile_hit(
                        b, b.x, b.y, entity_manager, create_explosion=False
                    ):
                        break
        return score_gain, destroyed_count, score_events

    def projectiles_vs_blocker_fields(
        self,
        projectiles: Sequence[Projectile],
        enemies: Sequence[Any],
    ) -> None:
        """Campos de inimigos que bloqueiam (destroem) projéteis da nave.

        Detecção por duck typing (§5): qualquer inimigo que exponha
        `projectile_fields()` participa, sem `isinstance`. Cada campo é uma tupla
        com a forma na primeira posição:
          - `("seg", ax, ay, bx, by, raio)`  — parede do Tesla Twin
          - `("circle", cx, cy, raio)`       — campo estático do Jammer Node
        Bloqueia inclusive balas perfurantes (são paredes/campos sem brecha).
        Deve rodar antes de `projectiles_vs_enemies` para a bala não atingir
        inimigos atrás do campo.
        """
        if not projectiles:
            return

        fields: list[tuple[Any, ...]] = []
        for e in enemies:
            getter = getattr(e, "projectile_fields", None)
            if getter is None:
                continue
            fs = getter()
            if fs:
                fields.extend(fs)
        if not fields:
            return

        for b in projectiles:
            if getattr(b, "dead", False):
                continue
            br = b.rect
            bx, by = br.centerx, br.centery
            for field in fields:
                kind = field[0]
                if kind == "seg":
                    _, ax, ay, sx, sy, radius = field
                    if _point_segment_dist_sq(bx, by, ax, ay, sx, sy) <= radius * radius:
                        b.dead = True
                        break
                elif kind == "circle":
                    _, cx, cy, radius = field
                    dx, dy = bx - cx, by - cy
                    if dx * dx + dy * dy <= radius * radius:
                        b.dead = True
                        break

    def projectiles_vs_reflectors(
        self,
        projectiles: Sequence[Projectile],
        enemies: Sequence[Any],
        entity_manager: "EntityManager",
    ) -> None:
        """Face espelhada do Mirror Pylon **reflete** os tiros da nave: destrói o
        projétil e devolve um `NeonBolt` inimigo na direção do jogador.

        Duck-typed (§5): inimigos com `reflect_field()` participam, sem
        `isinstance`. O bolt refletido espalha conforme onde o tiro acertou a face
        (mais believable que reflexão perfeita). Roda antes de
        `projectiles_vs_enemies` para o tiro refletido não atingir o corpo atrás.
        """
        if not projectiles:
            return

        mirrors: list[tuple[Any, tuple[Any, ...]]] = []
        for e in enemies:
            getter = getattr(e, "reflect_field", None)
            if getter is None:
                continue
            for field in getter():
                mirrors.append((e, field))
        if not mirrors:
            return

        for b in projectiles:
            if getattr(b, "dead", False):
                continue
            br = b.rect
            bx, by = br.centerx, br.centery
            for owner, field in mirrors:
                _, ax, ay, sx, sy, radius, speed = field
                if _point_segment_dist_sq(bx, by, ax, ay, sx, sy) <= radius * radius:
                    self._spawn_reflected_bolt(
                        bx, by, ay, sy, owner, float(speed), entity_manager
                    )
                    b.dead = True
                    break

    @staticmethod
    def _spawn_reflected_bolt(
        bx: float,
        by: float,
        seg_ay: float,
        seg_by: float,
        owner: Any,
        speed: float,
        entity_manager: "EntityManager",
    ) -> None:
        """Cria o bolt refletido voltando para o lado do jogador. O espalhamento
        deriva de onde o tiro acertou a face (off em -1..1)."""
        if getattr(owner, "side_scroll", True):
            mid = (seg_ay + seg_by) / 2.0
            half = max(1.0, abs(seg_by - seg_ay) / 2.0)
            off = max(-1.0, min(1.0, (by - mid) / half))
            vx = -speed * 0.92          # de volta p/ a esquerda (jogador)
            vy = off * speed * 0.45
        else:
            mid = (seg_ay + seg_by) / 2.0  # no vertical, ay/sy carregam x
            half = max(1.0, abs(seg_by - seg_ay) / 2.0)
            off = max(-1.0, min(1.0, (bx - mid) / half))
            vx = off * speed * 0.45
            vy = -speed * 0.92          # de volta p/ cima
        entity_manager.neon_bolts.append(
            NeonBolt(bx, by, vx, vy, core=(255, 255, 255), glow=(200, 240, 255))
        )
        notify = getattr(owner, "notify_reflected", None)
        if notify is not None:
            notify()

    def _handle_explosive_bullet(
        self,
        bullet: Bullet,
        enemy_grid: SpatialGrid[Any],
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Materializa o efeito AoE de uma bala explosiva ao primeiro impacto."""
        cx = bullet.x + bullet.w / 2
        cy = bullet.y + bullet.h / 2
        radius = CollisionConstants.EXPLOSIVE_BULLET_RADIUS

        entity_manager.spawn_explosive_effect(cx, cy, radius=radius)
        entity_manager.spawn_explosion(cx, cy, size=radius // 2)
        sound_manager.play_explosion_asteroid()

        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        for nearby in enemy_grid.query(
            cx - radius, cy - radius, radius * 2, radius * 2
        ):
            if nearby.dead:
                continue
            ncx, ncy, _ = nearby.collision_circle()
            if (ncx - cx) ** 2 + (ncy - cy) ** 2 >= radius**2:
                continue
            hit_damage = EXPLOSIVE_BULLET_DAMAGE
            r = self._apply_hit(nearby, hit_damage, ncx, ncy, entity_manager)
            score_gain += r.points
            if r.killed:
                destroyed_count += 1
                self._credit_kill(bullet)
                if r.points > 0:
                    score_events.append((ncx, ncy, r.points))

        return score_gain, destroyed_count, score_events

    def homing_bullets_vs_enemies(
        self,
        homing_bullets: list[HomingBullet],
        enemy_grid: SpatialGrid[Any],
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Colisão de tiros teleguiados consumíveis com inimigos.
        Consome vida do projétil baseada no HP do inimigo.
        """
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        if not homing_bullets:
            return 0, 0, []

        for b in homing_bullets[:]:
            if b.dead or b.life <= 0:
                continue

            r = b.rect
            potential_enemies = enemy_grid.query(
                r.x - 10, r.y - 10, r.width + 20, r.height + 20
            )
            impact = impact_for_projectile(b)

            for enemy in potential_enemies:
                if enemy.dead:
                    continue

                # Evitar múltiplos hits no mesmo inimigo no mesmo frame
                if id(enemy) in b.hit_this_frame:
                    continue

                if self._projectile_collides_with_enemy(r, enemy):
                    b.hit_this_frame.add(id(enemy))

                    # HP do inimigo antes do hit para saber quanto consumir
                    enemy_hp = getattr(enemy, "health", 1)

                    # Aplicar hit
                    result = self._apply_hit(
                        enemy, b.damage, b.x, b.y, entity_manager, impact=impact
                    )

                    # Consumir vida do projétil: se matou, consome o HP total do inimigo.
                    # Se não matou, consome o dano que a bala causou (b.damage).
                    amount_to_consume = enemy_hp if result.killed else b.damage
                    b.consume_life(amount_to_consume)

                    score_gain += result.points
                    if result.killed:
                        destroyed_count += 1
                        self._credit_kill(b)
                        if result.points > 0:
                            score_events.append((b.x, b.y, result.points))

                    # Se a bala morreu por falta de vida, para de processar inimigos para ela
                    if b.life <= 0:
                        b.dead = True
                        break

        return score_gain, destroyed_count, score_events

    def _apply_continuous_beam_hits(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
        damage: int,
        enemy_grid: SpatialGrid[Any],
        entity_manager: "EntityManager",
        extra_padding: int = 0,
        owner_ship: Any | None = None,
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Aplica dano de um feixe (linha p1→p2) aos inimigos na grid."""
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        pad = CollisionConstants.SPATIAL_QUERY_PADDING + extra_padding
        min_x = min(p1[0], p2[0]) - pad
        min_y = min(p1[1], p2[1]) - pad
        w = abs(p2[0] - p1[0]) + pad * 2
        h = abs(p2[1] - p1[1]) + pad * 2
        candidates = enemy_grid.query(int(min_x), int(min_y), int(w), int(h))

        for enemy in candidates:
            if enemy.dead:
                continue
            for hitbox in self._get_ship_contact_hitboxes(enemy):
                if hitbox.clipline(p1, p2):
                    hx, hy = hitbox.centerx, hitbox.centery
                    result = self._apply_hit(enemy, damage, hx, hy, entity_manager)
                    score_gain += result.points
                    if result.killed:
                        destroyed_count += 1
                        if owner_ship is not None and hasattr(owner_ship, "register_kill"):
                            owner_ship.register_kill()
                        if result.points > 0:
                            score_events.append((hx, hy, result.points))
                    break

        return score_gain, destroyed_count, score_events

    def orbital_shields_vs_enemies(
        self,
        orbital_shields: list[Any],
        enemy_grid: SpatialGrid[Any],
        dt: float,
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Dano contínuo dos escudos orbitais a inimigos em contato."""
        if not orbital_shields or dt <= 0.0:
            return 0, 0, []

        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        for shield in orbital_shields:
            if getattr(shield, "dead", False):
                continue
            sr: pygame.Rect = shield.rect
            damage = max(1, int(shield.damage * dt))
            pad = CollisionConstants.SPATIAL_QUERY_PADDING
            owner = getattr(shield, "ship", None)

            candidates = enemy_grid.query(
                sr.x - pad, sr.y - pad, sr.width + pad * 2, sr.height + pad * 2
            )
            for enemy in candidates:
                if enemy.dead:
                    continue
                if not self._rect_collides_with_enemy(sr, enemy):
                    continue
                hx, hy = sr.centerx, sr.centery
                result = self._apply_hit(enemy, damage, hx, hy, entity_manager)
                score_gain += result.points
                if result.killed:
                    destroyed_count += 1
                    if owner is not None and hasattr(owner, "register_kill"):
                        owner.register_kill()
                    if result.points > 0:
                        score_events.append((hx, hy, result.points))

        return score_gain, destroyed_count, score_events

    def plasma_beams_vs_enemies(
        self,
        plasma_beams: list[Any],
        enemy_grid: SpatialGrid[Any],
        dt: float,
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Dano contínuo do feixe de plasma a inimigos na linha."""
        if not plasma_beams or dt <= 0.0:
            return 0, 0, []

        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        for beam in plasma_beams:
            if getattr(beam, "dead", False):
                continue
            p1, p2 = beam.get_line()
            damage = max(1, int(beam.damage * dt))
            extra_pad = int(getattr(beam, "current_width", 0))
            g, d, ev = self._apply_continuous_beam_hits(
                p1, p2, damage, enemy_grid, entity_manager,
                extra_padding=extra_pad,
                owner_ship=getattr(beam, "ship", None),
            )
            score_gain += g
            destroyed_count += d
            score_events.extend(ev)

        return score_gain, destroyed_count, score_events

    def coop_links_vs_enemies(
        self,
        coop_links: list[Any],
        enemy_grid: SpatialGrid[Any],
        dt: float,
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Dano contínuo do CoopLink (linha entre dois jogadores) a inimigos."""
        if not coop_links or dt <= 0.0:
            return 0, 0, []

        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        for link in coop_links:
            if getattr(link, "dead", False):
                continue
            p1, p2 = link.get_collision_line()
            damage = max(1, int(link.damage * dt))
            # Coop kill: ambos os jogadores recebem combo (mecânica do CoopLink
            # é cooperativa por design — o feixe só existe se os 2 estão ativos).
            g, d, ev = self._apply_continuous_beam_hits(
                p1, p2, damage, enemy_grid, entity_manager,
                owner_ship=getattr(link, "ship1", None),
            )
            score_gain += g
            destroyed_count += d
            score_events.extend(ev)
            # Atribuir também ao ship2 — sem dupla contagem porque o
            # `_apply_continuous_beam_hits` interno só credita o owner_ship.
            ship2 = getattr(link, "ship2", None)
            if ship2 is not None and hasattr(ship2, "register_kill"):
                for _ in range(d):
                    ship2.register_kill()

        return score_gain, destroyed_count, score_events

    def homing_bullets_vs_boss(
        self,
        homing_bullets: list[HomingBullet],
        boss: Any,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão de tiros teleguiados consumíveis com boss."""
        if not homing_bullets or not boss or boss.dead:
            return 0
        # Boss invulnerável (INTRO/TELEPORT/ENTERING): pular para não
        # desperdiçar cargas — o dano seria descartado por can_take_damage.
        can_damage_fn = getattr(boss, "can_take_damage", None)
        if callable(can_damage_fn) and not can_damage_fn():
            return 0

        score_gain = 0
        for b in homing_bullets[:]:
            if b.dead or b.life <= 0:
                continue

            # Evitar multi-hit no boss no mesmo frame
            if id(boss) in b.hit_this_frame:
                continue

            if self._check_mask_collision(b.rect, None, boss, b.x, b.y):
                b.hit_this_frame.add(id(boss))

                damage = int(b.damage * config_instance.BOSS_UPGRADE_DAMAGE_MULTIPLIER)

                # Boss tem muito HP, geralmente a bala vai consumir toda sua vida restante
                # ou o máximo de dano que ela pode causar.
                amount_to_consume = (
                    b.life
                )  # Simplificação: boss sempre consome o que resta da bala se hitar
                b.consume_life(amount_to_consume)

                result = self._apply_hit(
                    boss,
                    damage,
                    b.x,
                    b.y,
                    entity_manager,
                    floating_scores,
                    impact=impact_for_projectile(b),
                )
                score_gain += result.points

                if b.life <= 0:
                    b.dead = True

        return score_gain

    def _trigger_chain_shot(
        self,
        hit_x: float,
        hit_y: float,
        source_enemy: Any,
        bullet_damage: int,
        jumps_left: int,
        already_hit: set[int],
        enemy_grid: "SpatialGrid[Any]",
        entity_manager: "EntityManager",
        owner_ship: Any | None = None,
        explosive: bool = False,
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Executa os saltos do Chain Shot iterativamente.

        Cada salto busca o inimigo vivo mais próximo dentro de CHAIN_SHOT_RADIUS
        que ainda não foi atingido nesta cadeia, aplica dano escalado e cria o
        efeito visual ChainLightning. Kills propagados são creditados ao
        `owner_ship` (mesma nave que disparou a bala original).

        Combo Chain + Explosive: quando ``explosive`` é True (a bala original é
        explosiva), cada salto também solta uma mini-explosão AoE no inimigo
        encadeado — o raio elétrico vira uma teia de estilhaços. Usa o mesmo
        ``ExplosiveEffect`` do tiro explosivo, com raio/dano reduzidos, então o
        dano em área é resolvido pelo passe ``explosive_effects_vs_enemies``.
        """
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        radius = config_instance.CHAIN_SHOT_RADIUS
        damage_factor = config_instance.CHAIN_SHOT_DAMAGE_FACTOR

        current_x = hit_x
        current_y = hit_y
        current_damage = int(bullet_damage * damage_factor)
        already_hit.add(id(source_enemy))

        for _ in range(jumps_left):
            if current_damage < 1:
                break

            candidates = enemy_grid.query(
                current_x - radius,
                current_y - radius,
                radius * 2,
                radius * 2,
            )

            best: Any = None
            best_dist_sq = radius * radius

            for cand in candidates:
                if cand.dead or id(cand) in already_hit:
                    continue
                cx, cy, _ = cand.collision_circle()
                dx = cx - current_x
                dy = cy - current_y
                dist_sq = dx * dx + dy * dy
                if dist_sq < best_dist_sq:
                    best_dist_sq = dist_sq
                    best = cand

            if best is None:
                break

            best_cx, best_cy, _ = best.collision_circle()
            already_hit.add(id(best))

            entity_manager.chain_lightnings.append(
                ChainLightning(
                    start_pos=(current_x, current_y),
                    end_pos=(best_cx, best_cy),
                )
            )

            result = self._apply_hit(
                best, current_damage, best_cx, best_cy, entity_manager
            )
            score_gain += result.points
            if result.killed:
                destroyed_count += 1
                if owner_ship is not None and hasattr(owner_ship, "register_kill"):
                    owner_ship.register_kill()
                if result.points > 0:
                    score_events.append((best_cx, best_cy, result.points))

            # Combo Chain + Explosive: cada salto detona uma mini-explosão. Raio e
            # dano reduzidos (~60%/50% do tiro explosivo) para o combo ser um
            # bônus de dispersão, não um apagão de tela. O AoE em si é resolvido
            # no passe explosive_effects_vs_enemies.
            if explosive:
                mini_radius = CollisionConstants.EXPLOSIVE_BULLET_RADIUS * 0.6
                entity_manager.spawn_explosive_effect(
                    best_cx,
                    best_cy,
                    radius=mini_radius,
                    damage=EXPLOSIVE_BULLET_DAMAGE // 2,
                    color=(255, 140, 40),
                )
                entity_manager.spawn_explosion(best_cx, best_cy, size=int(mini_radius // 2))

            current_x = best_cx
            current_y = best_cy
            current_damage = int(current_damage * damage_factor)

        return score_gain, destroyed_count, score_events

    def projectiles_vs_boss(
        self,
        projectiles: Sequence[Any],
        boss: Any,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Projéteis do jogador (Bullet, MiniShipBullet) vs. boss — dano com multiplicador."""
        return self._project_into_boss(
            projectiles, boss, floating_scores, entity_manager, is_piercing_allowed=True
        )

    def projectiles_vs_boss_barrier(
        self,
        projectiles: Sequence[Any],
        boss: Any,
        entity_manager: "EntityManager",
    ) -> None:
        """Barreira FÍSICA do corpo do boss (blindagem sólida) vs. tiros do jogador.

        Conceito SEPARADO do dano: interrompe/destrói o projétil ao tocar o corpo, mas
        NÃO passa pelo roteador de dano (`apply_hit`/`on_hit`) — o corpo não toma dano
        (esse vem só das partes vulneráveis). Pequeno feedback de impacto via
        `boss.spawn_barrier_impact`. Só age em bosses que exponham `barrier_circle()`
        ATIVA (Metropolis Overlord nas Fases 1/2); demais bosses → no-op.

        Respeita `piercing` (atravessa, como `_project_into_boss`) — não nerfa o upgrade
        e o corpo não toma dano de qualquer modo.
        """
        if not projectiles or not boss or boss.dead:
            return
        get_barrier = getattr(boss, "barrier_circle", None)
        if not callable(get_barrier):
            return
        circle: Any = get_barrier()
        if circle is None:
            return
        bcx, bcy, br = circle
        br2 = br * br
        for proj in projectiles:
            if proj.dead or getattr(proj, "piercing", False):
                continue
            r = proj.rect
            px, py = float(r.centerx), float(r.centery)
            if (px - bcx) ** 2 + (py - bcy) ** 2 <= br2:
                proj.dead = True  # tiro interrompido pela blindagem (sem dano ao corpo)
                boss.spawn_barrier_impact(px, py)

    def ship_vs_boss(
        self,
        ship: Ship,
        boss: Any,
        entity_manager: "EntityManager",
    ) -> bool:
        if not boss or boss.dead or ship.invuln > 0:
            return False

        ship_mask = (
            pygame.mask.from_surface(ship.ship_image)
            if hasattr(ship, "ship_image") and ship.ship_image is not None
            else pygame.mask.Mask((ship.w, ship.h), fill=True)
        )

        if self._check_mask_collision(ship.rect, ship_mask, boss, ship.x, ship.y):
            # Iniciar morte da nave (trigger_death_sequence ou similar se existir)
            # Para boss, contato costuma ser letal instantâneo.
            entity_manager.spawn_explosion(
                ship.x + ship.w / 2,
                ship.y + ship.h / 2,
                size=CollisionConstants.AREA_EXPLOSION_SIZE,
            )
            return True
        return False

    def ship_vs_enemies(
        self,
        ship: Ship,
        enemy_grid: SpatialGrid[Any],
        entity_manager: "EntityManager",
    ) -> bool:
        """Verifica colisão da nave com inimigos comuns."""
        if ship.invuln > 0:
            return False

        ship_rect = ship.rect
        candidates = enemy_grid.query(
            ship_rect.x - 10,
            ship_rect.y - 10,
            ship_rect.width + 20,
            ship_rect.height + 20,
        )
        cx, cy = float(ship_rect.centerx), float(ship_rect.centery)

        for enemy in candidates:
            if enemy.dead or not getattr(enemy, "causes_damage", True):
                continue
            if not self._ship_collides_with_enemy(ship_rect, enemy):
                continue

            self._apply_ship_contact(enemy, cx, cy, entity_manager)
            entity_manager.spawn_explosion(
                cx, cy, size=CollisionConstants.AREA_EXPLOSION_SIZE
            )
            return True
        return False

    def enemy_projectiles_vs_ship(
        self,
        ship: Ship,
        projectiles: list[Any],
        grid: "SpatialGrid[Any] | None" = None,
    ) -> bool:
        """Projéteis de inimigos (qualquer tipo) vs. nave do jogador.

        Quando `grid` é passada, filtra candidatos por proximidade espacial e
        verifica pertencimento à `projectiles` via id-set (a grid mistura
        tipos diferentes de projétil de inimigo). Sem grid, itera a lista
        diretamente — assinatura espelha `energy_orbs_vs_ship`.
        """
        if ship.invuln > 0:
            return False
        ship_rect = ship.rect

        if grid is not None and projectiles:
            pad = CollisionConstants.SPATIAL_QUERY_PADDING
            projectile_ids = {id(p) for p in projectiles}
            for p in grid.query(
                ship_rect.x - pad,
                ship_rect.y - pad,
                ship_rect.width + pad * 2,
                ship_rect.height + pad * 2,
            ):
                if (
                    id(p) in projectile_ids
                    and not getattr(p, "dead", False)
                    and ship_rect.colliderect(p.rect)
                ):
                    p.dead = True
                    return True
            return False

        for p in projectiles:
            if not getattr(p, "dead", False) and ship_rect.colliderect(p.rect):
                p.dead = True
                return True
        return False

    def energy_orbs_vs_ship(
        self,
        ship: Ship,
        energy_orbs: list[EnergyOrb],
        grid: "SpatialGrid[Any] | None" = None,
    ) -> EnergyOrb | None:
        """Verifica colisão entre EnergyOrbs (ElementalRobot) e a nave.

        Retorna o orbe que colidiu para que PlayingScene possa aplicar os debuffs.
        """
        if ship.invuln > 0:
            return None
        ship_rect = ship.rect
        if grid is not None:
            pad = CollisionConstants.SPATIAL_QUERY_PADDING
            for orb in grid.query(
                ship_rect.x - pad,
                ship_rect.y - pad,
                ship_rect.width + pad * 2,
                ship_rect.height + pad * 2,
            ):
                if (
                    isinstance(orb, EnergyOrb)
                    and not orb.dead
                    and ship_rect.colliderect(orb.rect)
                ):
                    orb.dead = True
                    return orb
            return None
        for orb in energy_orbs[:]:
            if not orb.dead and ship_rect.colliderect(orb.rect):
                orb.dead = True
                return orb
        return None

    def player_shots_vs_orbital_orbs(
        self,
        orbs: list[OrbitalEnergyOrb],
        projectiles: Sequence[Any],
        player_lasers: Sequence[PlayerLaser],
        entity_manager: "EntityManager",
    ) -> int:
        """Tiros da nave destroem os orbes da Torreta Orbital antes que cheguem.

        Orbes são poucos (≤ ~6 em tela) → scan linear é mais barato que a grid
        aqui (§8). Balas/mini-balas testam por rect; lasers por distância
        ponto-segmento contra a linha do feixe. Retorna nº de orbes destruídos.
        """
        if not orbs:
            return 0
        destroyed = 0
        for orb in orbs:
            if orb.dead:
                continue
            orb_rect = orb.rect
            for b in projectiles:
                if getattr(b, "dead", False):
                    continue
                if orb_rect.colliderect(b.rect):
                    orb.take_damage(getattr(b, "damage", 1))
                    entity_manager.spawn_explosion(
                        orb.x, orb.y, size=10, explosion_type=ExplosionType.CYBER
                    )
                    if not getattr(b, "piercing", False):
                        b.dead = True
                    if orb.dead:
                        break
            if orb.dead:
                destroyed += 1
                continue

            ocx, ocy, orr = orb.collision_circle()
            for laser in player_lasers:
                if laser.dead or laser.state != "alive" or laser.w <= 0:
                    continue
                (ax, ay), (bx, by) = laser.get_collision_line()
                reach = laser.w / 2 + orr
                if _point_segment_dist_sq(ocx, ocy, ax, ay, bx, by) <= reach * reach:
                    orb.take_damage(laser.damage)
                    if orb.dead:
                        break
            if orb.dead:
                destroyed += 1
        return destroyed

    def orbital_orbs_vs_ship(
        self,
        ship: Ship,
        orbs: list[OrbitalEnergyOrb],
        entity_manager: "EntityManager",
        grid: "SpatialGrid[Any] | None" = None,
    ) -> bool:
        """Contato de um orbe com a nave: dano à nave e o orbe morre SEM virar
        campo (`landed=False`). Espelha `energy_orbs_vs_ship`, mas também solta um
        estouro de energia no ponto de impacto (feedback visual), como acontece
        quando o orbe é destruído por tiro."""
        if ship.invuln > 0:
            return False
        ship_rect = ship.rect
        if grid is not None:
            pad = CollisionConstants.SPATIAL_QUERY_PADDING
            for orb in grid.query(
                ship_rect.x - pad,
                ship_rect.y - pad,
                ship_rect.width + pad * 2,
                ship_rect.height + pad * 2,
            ):
                if (
                    isinstance(orb, OrbitalEnergyOrb)
                    and not orb.dead
                    and ship_rect.colliderect(orb.rect)
                ):
                    self._burst_orbital_orb(orb, entity_manager)
                    return True
            return False
        for orb in orbs:
            if not orb.dead and ship_rect.colliderect(orb.rect):
                self._burst_orbital_orb(orb, entity_manager)
                return True
        return False

    @staticmethod
    def _burst_orbital_orb(
        orb: OrbitalEnergyOrb, entity_manager: "EntityManager"
    ) -> None:
        """Mata o orbe no contato (sem virar campo) e solta o estouro de energia."""
        orb.dead = True
        orb.landed = False
        entity_manager.spawn_explosion(
            orb.x, orb.y, size=22, explosion_type=ExplosionType.CYBER
        )

    def electric_fields_vs_ships(
        self,
        fields: list[ElectricFieldZone],
        ships: Sequence[Ship],
        _entity_manager: "EntityManager",
    ) -> set[int]:
        """Campos elétricos vs. naves: dano contínuo + debuff de paralisia.

        Só a fase ativa (`damaging`) fere — `expand` é telegrama e `dissipate` é
        eco. O debuff é aplicado a quem encosta (mesmo em i-frames); o dano
        respeita invuln e a cadência da zona. Retorna `id(ship)` atingidos.
        """
        ship_hits: set[int] = set()
        for zone in fields:
            if zone.dead or not zone.damaging:
                continue
            for ship in ships:
                scx = ship.x + ship.w / 2
                scy = ship.y + ship.h / 2
                if not zone.in_zone(scx, scy):
                    continue
                ship.apply_electric_debuff()
                if ship.invuln > 0:
                    continue
                ship_eid = id(ship)
                if zone.can_damage(ship_eid):
                    zone.register_hit(ship_eid)
                    ship_hits.add(ship_eid)
        return ship_hits

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

    def fence_vs_ship(self, ship: Ship, beams: list[BossLaser]) -> bool:
        """Cerca elétrica (Fase 3) vs. nave: aplica o MESMO debuff elétrico/paralisia
        da Torreta Orbital (`Ship.apply_electric_debuff`) a quem ENCOSTA — inclusive
        em i-frames, igual a `electric_fields_vs_ships` — e retorna True se deve ferir
        (contato com a barreira ATIVA, `w > 0`, e sem invuln). NÃO cria status novo:
        a cerca é só uma nova ORIGEM do efeito elétrico já existente no jogo.
        """
        damaging = False
        for beam in beams:
            if beam.w <= 0:  # entrada/saída (telegrafo/colapso) não machucam nem paralisam
                continue
            if ship.rect.clipline(beam.get_collision_line()):
                ship.apply_electric_debuff()  # reuso direto: duração/chance/visual existentes
                if ship.invuln <= 0:
                    damaging = True
        return damaging

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

    def projectiles_vs_spikes(
        self,
        projectiles: list[Projectile],
        spike_grid: SpatialGrid[Spike],
        entity_manager: "EntityManager",
    ) -> int:
        """Projéteis do jogador (Bullet, MiniShipBullet) vs. Spikes voando.

        Só colide com spikes em estado "flying". Retorna score ganho.
        """
        score_gain = 0

        for b in projectiles[:]:
            b_rect = b.rect
            pad = CollisionConstants.SPATIAL_QUERY_PADDING
            potential_spikes = spike_grid.query(
                b_rect.x - pad,
                b_rect.y - pad,
                b_rect.width + pad * 2,
                b_rect.height + pad * 2,
            )
            for spike in potential_spikes:
                if spike.state == "flying" and b_rect.colliderect(spike.rect):
                    self._process_projectile_hit(
                        b,
                        spike.center_x,
                        spike.center_y,
                        entity_manager,
                        create_explosion=True,
                        explosion_size=CollisionConstants.SPIKE_EXPLOSION_SIZE,
                    )
                    spike.dead = True
                    sound_manager.play_explosion_alien()
                    score_gain += spike.get_points_value()
                    break
        return score_gain

    def ship_vs_powerups(
        self,
        ship: Ship,
        powerups: list[PowerUp],
    ) -> list[str]:
        # Magneto: `pickup_rect` é inflado por `profile.pickup_radius_mult`.
        pickup_box = ship.pickup_rect
        collected_kinds: list[str] = []
        for p in powerups[:]:
            if p.dead:
                continue
            if pickup_box.colliderect(p.rect):
                p.dead = True
                collected_kinds.append(p.kind)
        return collected_kinds

    def ship_vs_stars(
        self,
        ship: Ship,
        stars: list[Star],
    ) -> int:
        """Verifica colisão entre nave e estrelas. Retorna quantidade coletada."""
        pickup_box = ship.pickup_rect
        collected = 0
        for star in stars[:]:
            if pickup_box.colliderect(star.get_rect()):
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
                entity_manager.spawn_explosion(
                    spike.center_x,
                    spike.center_y,
                    size=CollisionConstants.SPIKE_EXPLOSION_SIZE,
                )
                return True
        return False

    def ship_vs_spike_boss(
        self, ship: Ship, boss: Any, entity_manager: "EntityManager"
    ) -> bool:
        """Colisão entre nave e SpikeBoss."""
        if not boss or boss.dead:
            return False
        if ship.invuln > 0:
            return False

        # Colisão com o corpo do boss
        if ship.rect.colliderect(pygame.Rect(boss.x, boss.y, boss.w, boss.h)):
            entity_manager.spawn_explosion(
                ship.x + ship.w / 2,
                ship.y + ship.h / 2,
                size=CollisionConstants.AREA_EXPLOSION_SIZE,
            )
            return True

        # Colisão com onda de proximidade
        proximity_data = getattr(boss, "get_proximity_attack_data", lambda: None)()
        if proximity_data:
            _, boss_center_x, boss_center_y, wave_radius = proximity_data
            # Calcular distância do centro da nave ao centro do boss
            ship_center_x = ship.x + ship.w / 2
            ship_center_y = ship.y + ship.h / 2
            dx = ship_center_x - boss_center_x
            dy = ship_center_y - boss_center_y
            if dx * dx + dy * dy <= wave_radius * wave_radius:
                entity_manager.spawn_explosion(
                    ship.x + ship.w / 2,
                    ship.y + ship.h / 2,
                    size=CollisionConstants.DEFAULT_EXPLOSION_SIZE,
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
                    entity_manager.spawn_explosion(
                        bullet.x,
                        bullet.y,
                        size=CollisionConstants.DEFAULT_EXPLOSION_SIZE,
                    )

                    # Destruir apenas a bala se não for piercing
                    if not bullet.piercing:
                        bullet.dead = True
                    hit_count += 1

                    # Som de impacto (mesmo som de dano ao boss)
                    sound_manager.play_boss_damage()
                    break

        return hit_count

    def bullets_vs_slime_drips(
        self,
        bullets: list[Bullet],
        slime_drips: list[SlimeDrip],
        entity_manager: "EntityManager",
    ) -> int:
        """
        Colisão entre balas do jogador e gotas de slime.
        As gotas NÃO são destruídas, apenas geram explosão visual.
        Retorna número de acertos para feedback visual/sonoro.
        """
        hit_count = 0

        for bullet in bullets[:]:
            if bullet.dead:
                continue

            bullet_rect = bullet.rect

            for drip in slime_drips:
                if drip.dead:
                    continue

                drip_rect = drip.get_rect()
                if bullet_rect.colliderect(drip_rect):
                    # Aplicar slow (lentidão) à gota quando atingida por uma bala
                    # Cada bala causa 0.5s de slow, acumulável até no máximo 2s
                    drip.apply_slow(slow_duration=0.5, max_slow_duration=2.0)

                    # Criar explosão no ponto de impacto
                    entity_manager.spawn_explosion(
                        bullet.x,
                        bullet.y,
                        size=CollisionConstants.DEFAULT_EXPLOSION_SIZE,
                        explosion_type=ExplosionType.SLIME,
                    )

                    # Destruir apenas a bala se não for piercing
                    if not bullet.piercing:
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
        enemies: Sequence[Enemy],
        _floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
        enemy_grid: "SpatialGrid[Any] | None" = None,
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Colisão dos lasers do jogador com inimigos (atravessa múltiplos alvos)."""
        score_gain: int = 0
        destroyed_count: int = 0
        score_events: list[tuple[float, float, int]] = []

        for laser in player_lasers:
            if laser.w <= 0:  # Laser ainda não expandiu ou já retraiu
                continue

            line = laser.get_collision_line()

            # Usa spatial grid para narrow candidates quando disponível
            if enemy_grid is not None:
                # Calcular bounding box do laser (linha entre x,y e target_x,target_y)
                min_x = min(laser.x, laser.target_x) - laser.w
                max_x = max(laser.x, laser.target_x) + laser.w
                min_y = min(laser.y, laser.target_y) - laser.w
                max_y = max(laser.y, laser.target_y) + laser.w

                lx = int(min_x)
                ly = int(min_y)
                lw = int(max_x - min_x)
                lh = int(max_y - min_y)
                candidates: Sequence[Enemy] = enemy_grid.query(lx, ly, lw, lh)
            else:
                candidates = enemies

            for enemy in candidates:
                if enemy.dead:
                    continue

                # Verificar se já atingiu este inimigo
                enemy_id = id(enemy)
                if enemy_id in laser.hit_enemies:
                    continue

                # Garantir que enemy_rect é pygame.Rect
                enemy_rect: pygame.Rect = (
                    enemy.rect
                    if hasattr(enemy, "rect")
                    else cast(
                        pygame.Rect,
                        getattr(enemy, "get_rect", lambda: pygame.Rect(0, 0, 0, 0))(),
                    )
                )
                if enemy_rect.clipline(line):
                    laser.hit_enemies.add(enemy_id)
                    cx, cy, _ = enemy.collision_circle()
                    result = self._apply_hit(
                        enemy,
                        laser.damage,
                        cx,
                        cy,
                        entity_manager,
                    )
                    score_gain += result.points
                    if result.killed:
                        destroyed_count += 1
                        self._credit_kill(laser)
                        if result.points > 0:
                            score_events.append((cx, cy, result.points))
        return score_gain, destroyed_count, score_events

    def player_lasers_vs_boss(
        self,
        player_lasers: list[PlayerLaser],
        boss: Damageable,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão dos lasers do jogador com o boss.

        Usa pixel-perfect collision se o boss possuir uma máscara definida.
        """
        if not player_lasers:
            return 0
        if not boss or boss.dead:
            return 0
        # Boss em INTRO/TELEPORT/ENTERING: pular para não registrar boss em
        # laser.hit_enemies prematuramente — caso contrário o laser nunca
        # acertaria de novo quando o boss ficasse vulnerável.
        can_damage_fn = getattr(boss, "can_take_damage", None)
        if callable(can_damage_fn) and not can_damage_fn():
            return 0
        score_gain: int = 0

        mask_data = self._get_enemy_collision_mask_data(boss)

        for laser in player_lasers:
            if laser.w <= 0:
                continue

            line = laser.get_collision_line()
            boss_rect: pygame.Rect = boss.rect

            collision_detected = False

            if mask_data is not None:
                mask, (bx, by) = mask_data
                # Fast proximity check first (optimization)
                bw, bh = mask.get_size()
                boss_center_x = bx + bw / 2
                boss_center_y = by + bh / 2

                # Calculate distance from boss center to laser line
                start_pos, end_pos = line
                dx = end_pos[0] - start_pos[0]
                dy = end_pos[1] - start_pos[1]
                length_squared = dx * dx + dy * dy

                if length_squared > 0:
                    vx = boss_center_x - start_pos[0]
                    vy = boss_center_y - start_pos[1]
                    t = max(0, min(1, (vx * dx + vy * dy) / length_squared))
                    proj_x = start_pos[0] + t * dx
                    proj_y = start_pos[1] + t * dy

                    dist_dx = boss_center_x - proj_x
                    dist_dy = boss_center_y - proj_y
                    distance_squared = dist_dx * dist_dx + dist_dy * dist_dy

                    # Buffer for laser width
                    proximity_threshold = (bw / 2 + 50) ** 2

                    if distance_squared <= proximity_threshold:
                        if boss_rect.clipline(line):
                            # Sampling points along the laser line for mask check
                            steps = 10
                            for i in range(steps + 1):
                                t_step = i / steps
                                cx = start_pos[0] + t_step * (end_pos[0] - start_pos[0])
                                cy = start_pos[1] + t_step * (end_pos[1] - start_pos[1])

                                rel_x = int(cx - bx)
                                rel_y = int(cy - by)

                                if 0 <= rel_x < bw and 0 <= rel_y < bh:
                                    if mask.get_at((rel_x, rel_y)):
                                        collision_detected = True
                                        break
            else:
                collision_detected = boss_rect.clipline(line)

            if collision_detected:
                boss_id = id(boss)
                if boss_id in laser.hit_enemies:
                    continue

                laser.hit_enemies.add(boss_id)
                damage = int(
                    laser.damage * config_instance.BOSS_UPGRADE_DAMAGE_MULTIPLIER
                )
                cx_hit: float = float(boss.rect.centerx)
                cy_hit: float = float(boss.rect.centery)
                result = self._apply_hit(
                    boss, damage, cx_hit, cy_hit, entity_manager, floating_scores
                )
                score_gain += result.points

        return score_gain

    def cacador_lasers_vs_enemies(
        self,
        lasers: list[BossLaser],
        enemies: Sequence[Enemy],
        _floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
        enemy_grid: "SpatialGrid[Any] | None" = None,
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Colisão dos lasers especiais do Caçador (BossLaser) com inimigos."""
        score_gain: int = 0
        destroyed_count: int = 0
        score_events: list[tuple[float, float, int]] = []

        for laser in lasers:
            if laser.w <= 0:
                continue

            line = laser.get_collision_line()

            if enemy_grid is not None:
                # Bounding box do segmento do laser com padding lateral. Para
                # lasers verticais (target_x ≈ laser.x), abs(target_x - x) é 0
                # e candidatos a meio caminho ficariam fora do query — usar
                # min/max com `+ laser.w` evita esse caso.
                min_x = min(laser.x, laser.target_x) - laser.w
                max_x = max(laser.x, laser.target_x) + laser.w
                min_y = min(laser.y, laser.target_y) - laser.w
                max_y = max(laser.y, laser.target_y) + laser.w
                lx = int(min_x)
                ly = int(min_y)
                lw = int(max_x - min_x)
                lh = int(max_y - min_y)
                candidates: Sequence[Enemy] = enemy_grid.query(lx, ly, lw, lh)
            else:
                candidates = enemies

            for enemy in candidates:
                if enemy.dead:
                    continue

                enemy_id = id(enemy)
                if enemy_id in laser.hit_enemies:
                    continue

                enemy_rect: pygame.Rect = (
                    enemy.rect
                    if hasattr(enemy, "rect")
                    else cast(
                        pygame.Rect,
                        getattr(enemy, "get_rect", lambda: pygame.Rect(0, 0, 0, 0))(),
                    )
                )
                if enemy_rect.clipline(line):
                    laser.hit_enemies.add(enemy_id)
                    cx, cy, _ = enemy.collision_circle()
                    result = self._apply_hit(
                        enemy,
                        laser.damage,
                        cx,
                        cy,
                        entity_manager,
                    )
                    score_gain += result.points
                    if result.killed:
                        destroyed_count += 1
                        self._credit_kill(laser)
                        if result.points > 0:
                            score_events.append((cx, cy, result.points))
        return score_gain, destroyed_count, score_events

    def cacador_lasers_vs_boss(
        self,
        lasers: list[BossLaser],
        boss: Damageable,
        _floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão dos lasers especiais do Caçador (BossLaser) com o boss."""
        if not lasers:
            return 0
        if not boss or boss.dead:
            return 0
        # Boss em INTRO/TELEPORT/ENTERING: pular (ver `player_lasers_vs_boss`).
        can_damage_fn = getattr(boss, "can_take_damage", None)
        if callable(can_damage_fn) and not can_damage_fn():
            return 0

        score_gain: int = 0
        mask_data = self._get_enemy_collision_mask_data(boss)

        for laser in lasers:
            if laser.w <= 0:
                continue

            line = laser.get_collision_line()
            boss_rect: pygame.Rect = boss.rect
            collision_detected = False

            if mask_data is not None:
                mask, (bx, by) = mask_data
                bw, bh = mask.get_size()
                boss_center_x = bx + bw / 2
                boss_center_y = by + bh / 2

                start_pos, end_pos = line
                dx = end_pos[0] - start_pos[0]
                dy = end_pos[1] - start_pos[1]
                length_squared = dx * dx + dy * dy

                if length_squared > 0:
                    vx = boss_center_x - start_pos[0]
                    vy = boss_center_y - start_pos[1]
                    t = max(0, min(1, (vx * dx + vy * dy) / length_squared))
                    proj_x = start_pos[0] + t * dx
                    proj_y = start_pos[1] + t * dy

                    dist_dx = boss_center_x - proj_x
                    dist_dy = boss_center_y - proj_y
                    distance_squared = dist_dx * dist_dx + dist_dy * dist_dy
                    proximity_threshold = (bw / 2 + 50) ** 2

                    if distance_squared <= proximity_threshold and boss_rect.clipline(
                        line
                    ):
                        steps = 10
                        for i in range(steps + 1):
                            t_step = i / steps
                            cx = start_pos[0] + t_step * (end_pos[0] - start_pos[0])
                            cy = start_pos[1] + t_step * (end_pos[1] - start_pos[1])
                            rel_x = int(cx - bx)
                            rel_y = int(cy - by)
                            if (
                                0 <= rel_x < bw
                                and 0 <= rel_y < bh
                                and mask.get_at((rel_x, rel_y))
                            ):
                                collision_detected = True
                                break
            else:
                collision_detected = boss_rect.clipline(line)

            if not collision_detected:
                continue

            boss_id = id(boss)
            if boss_id in laser.hit_enemies:
                continue

            laser.hit_enemies.add(boss_id)
            damage = int(laser.damage * config_instance.BOSS_UPGRADE_DAMAGE_MULTIPLIER)
            cx_hit: float = float(boss.rect.centerx)
            cy_hit: float = float(boss.rect.centery)
            result = self._apply_hit(
                boss, damage, cx_hit, cy_hit, entity_manager, _floating_scores
            )
            score_gain += result.points

        return score_gain
