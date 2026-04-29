from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Sequence,
    TypeAlias,
    cast,
)

import pygame

from ..core.config import Config
from ..core.config import config as config_instance
from ..core.sound import sound_manager
from ..core.spatial_grid import SpatialGrid
from ..entities.air_strike_bomb import AirStrikeBomb
from ..entities.alien_bullet import AlienBullet
from ..entities.boss_laser import BossLaser
from ..entities.boss_square import BossSquare
from ..entities.bot_elemental import EnergyOrb
from ..entities.bullet import Bullet
from ..entities.cannon_mine import CannonMine, MineState
from ..entities.explosion import ExplosionType
from ..entities.explosive_effect import ExplosiveEffect
from ..entities.eye_laser import EyeLaser
from ..entities.floating_score import FloatingScore
from ..entities.ice_poison_zone import IcePoisonZone
from ..entities.mine_explosion import MineExplosion
from ..entities.mini_ship_bullet import MiniShipBullet
from ..entities.mountain_serpent_boss import SerpentRockBullet
from ..entities.player_laser import PlayerLaser
from ..entities.powerup import PowerUp
from ..entities.ship import Ship
from ..entities.slime_drip import SlimeDrip
from ..entities.spike import Spike
from ..entities.spike_boss_laser import SpikeBossLaser
from ..entities.star import Star
from .collision_protocols import Damageable, Enemy
from .hit_result import NO_HIT, HitResult

if TYPE_CHECKING:
    from .entity_manager import EntityManager


Projectile: TypeAlias = Bullet | MiniShipBullet

_RECT_MASK_CACHE: dict[tuple[int, int], pygame.mask.Mask] = {}


# Constantes de colisão
class CollisionConstants:
    SPATIAL_QUERY_PADDING = 10
    DEFAULT_EXPLOSION_SIZE = 20
    AREA_EXPLOSION_SIZE = 30
    BOSS_EXPLOSION_SIZE = 100
    SPIKE_EXPLOSION_SIZE = 15
    MINE_DAMAGE_DEFAULT = 2
    MINE_DAMAGE_AIRSTRIKE = 5


class Collisions:

    def __init__(self, is_side_scroll: bool = False) -> None:
        """Inicializa o sistema de colisões com suporte ao modo de jogo.

        Args:
            is_side_scroll: True se em modo side-scroll, False se em modo top-down
        """
        self.is_side_scroll = is_side_scroll

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

    @staticmethod
    def _get_enemy_collision_mask_data(
        enemy: Any,
    ) -> tuple[pygame.mask.Mask, tuple[int, int]] | None:
        getter = getattr(enemy, "get_collision_mask_data", None)
        if callable(getter):
            raw_data = cast(
                tuple[pygame.mask.Mask, tuple[int, int]] | None,
                getter(),
            )
            if raw_data is not None:
                mask, offset = raw_data
                if mask.get_size()[0] > 0 and mask.get_size()[1] > 0:
                    return mask, offset

        # Fallback: suporte a padrão do pygame com atributos .mask e .rect
        if hasattr(enemy, "mask"):
            mask = getattr(enemy, "mask")
            if mask is not None:
                if hasattr(enemy, "rect"):
                    rect = getattr(enemy, "rect")
                    if rect is not None:
                        return cast(pygame.mask.Mask, mask), (rect.x, rect.y)

        return None

    @staticmethod
    def _get_rect_mask(width: int, height: int) -> pygame.mask.Mask:
        key = (width, height)
        mask = _RECT_MASK_CACHE.get(key)
        if mask is None:
            mask = pygame.mask.Mask((width, height), fill=True)
            _RECT_MASK_CACHE[key] = mask
        return mask

    @classmethod
    def _rect_collides_with_enemy(cls, rect: pygame.Rect, enemy: Any) -> bool:
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

        return any(
            rect.colliderect(hitbox) for hitbox in cls._get_ship_contact_hitboxes(enemy)
        )

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
        """
        Verifica colisão pixel-perfect entre entidade e alvo com máscara.
        Fallback para rect collision se máscara não disponível.
        """
        # Se não possui mask explícita, usa fallback de rect
        mask = getattr(target_with_mask, "mask", None)  # type: ignore[attr-defined]
        if mask is None:
            target_rect: pygame.Rect = getattr(
                target_with_mask, "rect", None
            ) or pygame.Rect(
                target_with_mask.x,
                target_with_mask.y,
                target_with_mask.w,
                target_with_mask.h,
            )
            return entity_rect.colliderect(target_rect)

        # Fast distance check first
        target_center_x = target_with_mask.x + target_with_mask.w / 2
        target_center_y = target_with_mask.y + target_with_mask.h / 2
        entity_center_x = entity_x + entity_rect.width / 2
        entity_center_y = entity_y + entity_rect.height / 2

        dx = entity_center_x - target_center_x
        dy = entity_center_y - target_center_y
        distance_squared = dx * dx + dy * dy

        proximity_threshold = (
            target_with_mask.w / 2 + max(entity_rect.width, entity_rect.height)
        ) ** 2

        if distance_squared > proximity_threshold:
            return False

        # Rect collision check
        target_rect = pygame.Rect(
            target_with_mask.x,
            target_with_mask.y,
            target_with_mask.w,
            target_with_mask.h,
        )
        if not entity_rect.colliderect(target_rect):
            return False

        # Mask overlap check
        if entity_mask is None:
            entity_mask = self._get_rect_mask(entity_rect.width, entity_rect.height)

        offset = (
            int(entity_x - target_with_mask.x),
            int(entity_y - target_with_mask.y),
        )
        # mask is type: ignore for Pylance, since we checked above
        return cast("pygame.mask.Mask", mask).overlap(entity_mask, offset) is not None  # type: ignore[attr-defined]

    def _batch_query_for_projectiles(
        self,
        projectiles: Sequence[Projectile],
        grid: SpatialGrid[Any],
        padding: int = CollisionConstants.SPATIAL_QUERY_PADDING,
    ) -> dict[int, list[Enemy]]:
        """
        Faz uma query por projétil em vez de uma área única abrangente.
        Isso evita que um conjunto disperso de balas crie uma área de consulta gigantesca.

        Retorna dicionário mapeando projectile_id -> potential_targets.
        """
        if not projectiles:
            return {}

        result: dict[int, list[Enemy]] = {}
        for p in projectiles:
            r = p.rect
            potential_enemies = grid.query(
                r.x - padding,
                r.y - padding,
                r.width + padding * 2,
                r.height + padding * 2,
            )
            result[id(p)] = [
                target for target in potential_enemies if r.colliderect(target.rect)
            ]

        return result

    def _apply_hit(
        self,
        target: Any,
        damage: int,
        hit_x: float,
        hit_y: float,
        entity_manager: "EntityManager",
        floating_scores: list[FloatingScore] | None = None,
    ) -> HitResult:
        """Roteador único: chama target.on_hit e materializa o HitResult.

        Substitui _destroy_enemy. A entidade decide o que acontece; este
        método apenas executa explosão, som, fragmentos e death-sequence.
        """
        result: HitResult = target.on_hit(damage, hit_x, hit_y)

        if result.explosion_size > 0:
            entity_manager.spawn_explosion(
                hit_x,
                hit_y,
                size=result.explosion_size,
                explosion_type=result.explosion_type,
            )

        if result.sound is not None:
            result.sound()

        if result.fragments:
            entity_manager.absorb_fragments(result.fragments)

        if result.killed and result.points > 0 and floating_scores is not None:
            floating_scores.append(FloatingScore(hit_x, hit_y, result.points))

        if result.triggers_special_death:
            entity_manager.trigger_death_sequence(target)

        return result

    def _apply_ship_contact(
        self,
        target: Any,
        contact_x: float,
        contact_y: float,
        entity_manager: "EntityManager",
    ) -> HitResult:
        """Roteador para morte por contato com a nave."""
        contact = getattr(target, "on_ship_contact", None)
        if not callable(contact):
            return NO_HIT
        result: HitResult = cast(Callable[[float, float], HitResult], contact)(
            contact_x, contact_y
        )
        if result.explosion_size > 0:
            entity_manager.spawn_explosion(
                contact_x, contact_y, size=result.explosion_size
            )
        if result.sound is not None:
            result.sound()
        return result

    def _apply_area_damage(
        self,
        source_x: float,
        source_y: float,
        damage_radius: float,
        hit_tracking_set: set[int],
        enemies: Sequence[Enemy],
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

            # Calcular distância usando o protocol CollisionGeometry
            cx, cy, radius = enemy.collision_circle()
            dist_sq = (cx - source_x) ** 2 + (cy - source_y) ** 2

            # Verificar colisão
            if dist_sq < (damage_radius + radius) ** 2:
                hit_tracking_set.add(enemy_id)

                # Mines absorvem damage_to_mine; outros recebem dano nominal
                # (1 = padrão da explosão). on_hit decide o resto.
                hit_damage = (
                    damage_to_mine if getattr(enemy, "is_explosive_mine", False) else 1
                )
                result = self._apply_hit(
                    enemy,
                    hit_damage,
                    cx,
                    cy,
                    entity_manager,
                )
                score_gain += result.points
                if result.killed:
                    destroyed_count += 1
                    if result.points > 0:
                        score_events.append((cx, cy, result.points))

        return score_gain, destroyed_count, score_events

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

            damage = int(proj.damage * config_instance.BOSS_UPGRADE_DAMAGE_MULTIPLIER)
            result = self._apply_hit(
                boss, damage, proj.x, proj.y, entity_manager, floating_scores
            )
            score_gain += result.points

        return score_gain

    def check_mine_explosions(
        self,
        enemies: Sequence[Enemy],
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
        if not enemies:
            return 0, 0, [], False

        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []
        ship_hit = False

        # 1) Criar explosões para minas cujo timer de explosão acabou
        for enemy in enemies[:]:
            if getattr(enemy, "is_explosive_mine", False):
                mine: Any = enemy
                # Verificar se está explodindo E timer acabou (mas ainda não marcada dead)
                # OU já está dead (timer acabou no update anterior)
                should_explode = (
                    mine.is_exploding
                    and mine.pre_explosion_timer <= 0
                    and not mine.dead
                ) or mine.dead
                if should_explode:
                    cx, cy = (mine.x, mine.y)
                    explosion_radius = mine.explosion_radius

                    mine_explosions.append(MineExplosion(cx, cy, size=explosion_radius))

                    # Checar nave e limpar formações
                    if self.handle_mine_explosion(
                        cx, cy, explosion_radius, ship, entity_manager
                    ):
                        ship_hit = True

                    sound_manager.play_explosion_boss()

                    # Marcar como dead DEPOIS de criar explosão
                    mine.dead = True
                    if getattr(mine, "spawns_ice_zone", False):
                        entity_manager.spawn_ice_poison_zone(cx, cy, explosion_radius)

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

            for enemy in enemies[:]:
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
                        else 1
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

        return score_gain, destroyed_count, score_events, ship_hit

    def ice_poison_zones_vs_entities(
        self,
        zones: list[IcePoisonZone],
        enemies: Sequence[Any],
        ship: Ship,
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        for zone in zones:
            if zone.dead:
                continue

            if zone.in_zone(ship.x, ship.y):
                ship.speed_modifier_timer = max(ship.speed_modifier_timer, 0.15)

            for enemy in enemies:
                if enemy.dead:
                    continue
                cx, cy, r = enemy.collision_circle()
                if not zone.in_zone(cx, cy, r):
                    continue

                setattr(enemy, "_ice_slow_timer", 0.15)

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

    def handle_mine_explosion(
        self,
        explosion_x: float,
        explosion_y: float,
        explosion_radius: int,
        ship: Ship,
        entity_manager: "EntityManager",
    ) -> bool:
        """
        Checa colisão da explosão de mina com a nave e limpa formações.

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
                gain, destroyed, events = self._apply_area_damage(
                    damage_info.x,
                    damage_info.y,
                    damage_info.radius,
                    mine.hit_tracking_set,
                    enemies,
                    entity_manager,
                    damage_to_mine=damage_info.damage,
                )
                score_gain += gain
                destroyed_count += destroyed
                score_events.extend(events)

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

    def mini_ship_bullets_vs_enemies(
        self,
        mini_ship_bullets: list[MiniShipBullet],
        enemy_grid: SpatialGrid[Any],
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        if not mini_ship_bullets:
            return 0, 0, []

        projectile_targets = self._batch_query_for_projectiles(
            mini_ship_bullets,
            enemy_grid,
            padding=CollisionConstants.SPATIAL_QUERY_PADDING,
        )

        for b in mini_ship_bullets[:]:
            potential_enemies = projectile_targets.get(id(b), [])
            if not potential_enemies:
                continue

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
                    )
                    score_gain += result.points
                    if result.killed:
                        destroyed_count += 1
                        if result.points > 0:
                            score_events.append((b.x, b.y, result.points))

                    if self._process_projectile_hit(
                        b, b.x, b.y, entity_manager, create_explosion=False
                    ):
                        break
        return score_gain, destroyed_count, score_events

    def _handle_explosive_bullet(
        self,
        bullet: Bullet,
        enemy_grid: SpatialGrid[Any],
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Materializa o efeito AoE de uma bala explosiva ao primeiro impacto."""
        cx = bullet.x + bullet.w / 2
        cy = bullet.y + bullet.h / 2
        radius = 60

        entity_manager.spawn_explosive_effect(cx, cy, radius=radius)
        entity_manager.spawn_explosion(cx, cy, size=radius // 2)
        sound_manager.play_explosion_asteroid()

        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        for nearby in enemy_grid.query(cx - radius, cy - radius, radius * 2, radius * 2):
            if nearby.dead:
                continue
            ncx, ncy, _ = nearby.collision_circle()
            if (ncx - cx) ** 2 + (ncy - cy) ** 2 >= radius ** 2:
                continue
            hit_damage = 2 if getattr(nearby, "is_explosive_mine", False) else 1
            r = self._apply_hit(nearby, hit_damage, ncx, ncy, entity_manager)
            score_gain += r.points
            if r.killed:
                destroyed_count += 1
                if r.points > 0:
                    score_events.append((ncx, ncy, r.points))

        return score_gain, destroyed_count, score_events

    def bullets_vs_enemies(
        self,
        bullets: list[Bullet],
        enemy_grid: SpatialGrid[Any],
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        if not bullets:
            return 0, 0, []

        projectile_targets = self._batch_query_for_projectiles(
            bullets, enemy_grid, padding=CollisionConstants.SPATIAL_QUERY_PADDING
        )

        for b in bullets[:]:
            potential_enemies = projectile_targets.get(id(b), [])
            if not potential_enemies:
                continue

            for enemy in potential_enemies:
                if enemy.dead:
                    continue
                if self._projectile_collides_with_enemy(b.rect, enemy):
                    result = self._apply_hit(
                        enemy, getattr(b, "damage", 1), b.x, b.y, entity_manager
                    )
                    score_gain += result.points
                    if result.killed:
                        destroyed_count += 1
                        if result.points > 0:
                            score_events.append((b.x, b.y, result.points))

                    if b.explosive and not b.dead:
                        eg, ed, ee = self._handle_explosive_bullet(
                            b, enemy_grid, entity_manager
                        )
                        score_gain += eg
                        destroyed_count += ed
                        score_events.extend(ee)

                    if self._process_projectile_hit(
                        b, b.x, b.y, entity_manager, create_explosion=False
                    ):
                        break
        return score_gain, destroyed_count, score_events

    def bullets_vs_boss(
        self,
        bullets: list[Bullet],
        boss: Any,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        return self._project_into_boss(
            bullets, boss, floating_scores, entity_manager, is_piercing_allowed=True
        )

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
                ship.x + ship.w / 2, ship.y + ship.h / 2, size=30
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
            entity_manager.spawn_explosion(cx, cy, size=30)
            return True
        return False

    def serpent_bullets_vs_ship(
        self, ship: Ship, serpent_bullets: list[SerpentRockBullet]
    ) -> bool:
        """Verifica colisão entre as bolas de rocha da serpente e a nave."""
        if ship.invuln > 0:
            return False
        for bullet in serpent_bullets[:]:
            if ship.rect.colliderect(bullet.rect):
                bullet.dead = True
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

    def energy_orbs_vs_ship(
        self, ship: Ship, energy_orbs: list[EnergyOrb]
    ) -> EnergyOrb | None:
        """Verifica colisão entre EnergyOrbs (ElementalRobot) e a nave.

        Retorna o orbe que colidiu para que PlayingScene possa aplicar os debuffs.
        """
        if ship.invuln > 0:
            return None

        for orb in energy_orbs[:]:
            if not orb.dead and ship.rect.colliderect(orb.rect):
                orb.dead = True
                return orb
        return None

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
        boss: Damageable,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão de balas das mini ships com Boss normal."""
        return self._project_into_boss(
            mini_ship_bullets,
            boss,
            floating_scores,
            entity_manager,
            is_piercing_allowed=True,
        )


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
                if spike.state == "flying" and b_rect.colliderect(
                    spike.rect
                ):  # Usa cache
                    # Destruir projétil se não for piercing
                    self._process_projectile_hit(
                        b,
                        spike.center_x,
                        spike.center_y,
                        entity_manager,
                        create_explosion=True,
                        explosion_size=15,
                    )
                    spike.dead = True
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
                    self._process_projectile_hit(
                        b,
                        spike.center_x,
                        spike.center_y,
                        entity_manager,
                        create_explosion=True,
                        explosion_size=15,
                    )
                    # Destruir espinho
                    spike.dead = True
                    # Som
                    sound_manager.play_explosion_asteroid()
                    # Pontos
                    score_gain += spike.get_points_value()
                    break  # Próxima bala
        return score_gain

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
                ship.x + ship.w / 2, ship.y + ship.h / 2, size=30
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
                        bullet.x, bullet.y, size=20, explosion_type=ExplosionType.SLIME
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
        floating_scores: list[FloatingScore],
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
                lx = int(laser.x)
                ly = int(laser.y - laser.w / 2)
                lw = int(laser.w)
                lh = int(laser.w)
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
                        if result.points > 0:
                            score_events.append((cx, cy, result.points))
                            floating_scores.append(FloatingScore(cx, cy, result.points))
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
