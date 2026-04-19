import math
import random
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Protocol,
    Sequence,
    TypeAlias,
    cast,
    runtime_checkable,
)

import pygame

from ..core.config import Config
from ..core.config import config as config_instance
from ..core.sound import sound_manager
from ..core.spatial_grid import SpatialGrid
from ..entities.air_strike_bomb import AirStrikeBomb
from ..entities.alien import Alien
from ..entities.alien_bullet import AlienBullet
from ..entities.boss import Boss
from ..entities.boss_laser import BossLaser
from ..entities.boss_square import BossSquare
from ..entities.bot_elemental import ElementalRobot, EnergyOrb
from ..entities.bullet import Bullet
from ..entities.cannon_mine import CannonMine, MineState
from ..entities.explosion import ExplosionType
from ..entities.explosive_effect import ExplosiveEffect
from ..entities.explosive_mine import ExplosiveMine
from ..entities.eye_enemy import EyeEnemy
from ..entities.eye_laser import EyeLaser
from ..entities.floating_score import FloatingScore
from ..entities.giant_meteor_boss import GiantMeteorBoss
from ..entities.meteor import Meteor
from ..entities.mine_explosion import MineExplosion
from ..entities.mini_ship_bullet import MiniShipBullet
from ..entities.mountain_mage import MountainStalagmite
from ..entities.player_laser import PlayerLaser
from ..entities.powerup import PowerUp
from ..entities.rock_glider import RockGlider
from ..entities.ship import Ship
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
    from .entity_manager import EntityManager


# Protocol define um contrato estrutural (duck typing com type checking)
# Qualquer classe que implemente get_points_value() satisfaz este contrato
@runtime_checkable
class Scoreable(Protocol):
    """Contrato para entidades que geram pontos ao serem destruídas."""

    def get_points_value(self) -> int:
        """Retorna quantidade de pontos que a entidade gera."""
        ...


@runtime_checkable
class Enemy(Protocol):
    """Protocol para qualquer inimigo comum do jogo."""

    @property
    def x(self) -> float: ...

    @property
    def y(self) -> float: ...

    @property
    def rect(self) -> pygame.Rect: ...

    dead: bool
    health: int

    def get_points_value(self) -> int: ...
    def update(self, dt: float, *args: Any, **kwargs: Any) -> Any: ...


BossEnemy: TypeAlias = Boss | SpikeBoss | SlimeBoss | GiantMeteorBoss | StoneGolemBoss
Projectile: TypeAlias = Bullet | MiniShipBullet


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
                rect
                for rect in raw_hitboxes
                if rect.width > 0 and rect.height > 0
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
        if not callable(getter):
            return None

        raw_data = cast(
            tuple[pygame.mask.Mask, tuple[int, int]] | None,
            getter(),
        )
        if raw_data is None:
            return None

        mask, offset = raw_data
        if mask.get_size()[0] <= 0 or mask.get_size()[1] <= 0:
            return None
        return mask, offset

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

            rect_mask = pygame.mask.Mask((rect.width, rect.height), fill=True)
            overlap = rect_mask.overlap(enemy_mask, (enemy_x - rect.x, enemy_y - rect.y))
            return overlap is not None

        return any(rect.colliderect(hitbox) for hitbox in cls._get_ship_contact_hitboxes(enemy))

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

    @staticmethod
    def get_collision_info(
        enemy: Enemy,
    ) -> tuple[float, float, float]:
        """OPT #6: Helper para calcular center_x, center_y, radius de qualquer inimigo.

        Retorna (center_x, center_y, radius) consolidando lógica de type checking.
        """
        if isinstance(enemy, ExplosiveMine):
            return enemy.x, enemy.y, enemy.radius
        if isinstance(enemy, Boulder):
            return enemy.x, enemy.y, enemy.RADIUS
        if isinstance(enemy, RockShard):
            return enemy.x, enemy.y, enemy.size
        if isinstance(enemy, EntryDebris):
            return enemy.x, enemy.y, enemy.S * enemy.rock_size
        return (
            enemy.rect.centerx,
            enemy.rect.centery,
            max(enemy.rect.width, enemy.rect.height) / 2,
        )

    def _is_invulnerable_to_damage(self, entity: Enemy) -> bool:
        """Verifica se entidade é imune a dano comum (tiros/explosões)."""
        return isinstance(entity, SquareMinionBoss)

    def _handle_invulnerable_hit(
        self, projectile_x: float, projectile_y: float, entity_manager: "EntityManager"
    ) -> None:
        """Cria feedback visual ao atingir entidade invulnerável."""
        entity_manager.spawn_explosion(projectile_x, projectile_y, size=20)
        sound_manager.play_boss_damage()

    def _calculate_default_explosion_size(self, enemy: Enemy) -> int:
        """Calcula tamanho padrão de explosão baseado no inimigo."""
        if isinstance(enemy, Meteor):
            return max(12, int(enemy.w // 2))
        if isinstance(enemy, Alien):
            return 40
        if isinstance(enemy, ExplosiveMine):
            return 25
        if isinstance(enemy, ElementalRobot):
            return 55
        if isinstance(enemy, StoneSentry):
            return 45
            if isinstance(enemy, MountainStalagmite):
                return 38
        return CollisionConstants.DEFAULT_EXPLOSION_SIZE

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
        target_with_mask: BossEnemy,
        entity_x: float,
        entity_y: float,
    ) -> bool:
        """
        Verifica colisão pixel-perfect entre entidade e alvo com máscara.
        Fallback para rect collision se máscara não disponível.
        """
        if not isinstance(target_with_mask, SlimeBoss):
            return entity_rect.colliderect(
                pygame.Rect(
                    target_with_mask.x,
                    target_with_mask.y,
                    target_with_mask.w,
                    target_with_mask.h,
                )
            )

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
            entity_mask = pygame.mask.Mask(
                (entity_rect.width, entity_rect.height), fill=True
            )

        offset = (
            int(entity_x - target_with_mask.x),
            int(entity_y - target_with_mask.y),
        )
        return target_with_mask.mask.overlap(entity_mask, offset) is not None

    def _batch_query_for_projectiles(
        self,
        projectiles: Sequence[Projectile],
        grid: SpatialGrid[Any],
        padding: int = CollisionConstants.SPATIAL_QUERY_PADDING,
    ) -> dict[int, list[Enemy]]:
        """
        Faz query única expandida para todos os projéteis.
        Retorna dicionário mapeando projectile_id -> potential_targets.
        """
        if not projectiles:
            return {}

        # Calcular bounds de todos os projéteis
        rects = [p.rect for p in projectiles]
        min_x = min(r.x for r in rects) - padding
        min_y = min(r.y for r in rects) - padding
        max_x = max(r.x + r.width for r in rects) + padding
        max_y = max(r.y + r.height for r in rects) + padding

        # Query única
        all_potential = grid.query(min_x, min_y, max_x - min_x, max_y - min_y)

        # Mapear para cada projétil
        result: dict[int, list[Enemy]] = {}
        for p in projectiles:
            result[id(p)] = [
                target for target in all_potential if p.rect.colliderect(target.rect)
            ]

        return result

    def _destroy_enemy(
        self,
        enemy: Enemy,
        _enemies: Sequence[Enemy],
        entity_manager: "EntityManager",
        explosion_size: int | None = None,
        hit_x: float | None = None,
        hit_y: float | None = None,
    ) -> tuple[int, tuple[float, float, int] | None, bool]:
        """Helper para destruição de inimigos com explosão, som e fragmentos.

        Centraliza lógica repetida em 8+ lugares.
        Retorna (pontos, (cx, cy, pontos) | None, foi_morto).

        Args:
            enemy: Inimigo a ser destruído
            enemies: Sequência de inimigos (será convertida em lista para mutação)
            entity_manager: Gerenciador de entidades
            explosion_size: Tamanho da explosão. Se None, usa tamanho padrão.
            hit_x, hit_y: Ponto exato do impacto (opcional).

        Returns:
            Tupla com (pontos_ganhos, evento_pontos, foi_destruído)
        """
        # Fragmentos do Golem não são destrutíveis por ataques do jogador.
        # A esfera vermelha (Boulder/GolemMine) continua seguindo o fluxo normal.
        if isinstance(enemy, (RockShard, OrbitalRock, EntryDebris)):
            return 0, None, False

        # Converter para lista mutável apenas internamente - melhor prática
        # (mantido para compatibilidade com outros usos futuros do método)
        # Calcular centro
        cx, cy, _ = self.get_collision_info(enemy)

        # Ponto de explosão de impacto: hit_x/y se disponível, senão centro
        hx = hit_x if hit_x is not None else cx
        hy = hit_y if hit_y is not None else cy

        # RockGlider possui dano por partes (pedra e bot) com mortes independentes.
        if isinstance(enemy, RockGlider):
            (
                pts,
                part_destroyed,
                _fully_destroyed,
                part_center,
                part_name,
            ) = enemy.take_part_damage(hx, hy, amount=1)

            if not part_destroyed:
                entity_manager.spawn_explosion(hx, hy, size=10)
                sound_manager.play_boss_damage()
                return 0, None, False

            part_explosion_size = 35 if part_name == "rock" else 25
            entity_manager.spawn_explosion(
                part_center[0],
                part_center[1],
                size=part_explosion_size,
            )

            if part_name == "rock":
                sound_manager.play_explosion_asteroid()
            else:
                sound_manager.play_explosion_alien()

            score_event = (part_center[0], part_center[1], pts) if pts > 0 else None

            return pts, score_event, part_destroyed

        # ElementalRobot, Boulder e StoneSentry têm sistema de HP próprio — delegar ao take_damage
        if isinstance(enemy, (ElementalRobot, Boulder, StoneSentry)):
            enemy.take_damage(1)
            # ElementalRobot sinaliza morte via flag just_died no estado DYING.
            if hasattr(enemy, "fsm_state") and hasattr(enemy, "just_died"):
                elemental_enemy = cast(ElementalRobot, enemy)
                just_died = (
                    elemental_enemy.fsm_state == "DYING" and elemental_enemy.just_died
                )
                if just_died:
                    elemental_enemy.just_died = False  # consome a flag
            else:
                # Boulder e StoneSentry marcam morte diretamente em .dead
                just_died = enemy.dead

            if not just_died:
                # Ainda vivo: só explosão pequena de hit, sem score
                entity_manager.spawn_explosion(hx, hy, size=10)
                sound_manager.play_boss_damage()
                return 0, None, False
            # Morreu neste hit: continua para dar pontos e explosão grande
        else:
            # Marcar como morto
            if isinstance(enemy, EyeEnemy):
                enemy.destroy()
            enemy.dead = True

        # Definir tipo de explosão baseado no inimigo
        if isinstance(enemy, Alien):
            explosion_type = ExplosionType.ALIEN
        elif isinstance(enemy, ElementalRobot):
            explosion_type = enemy.get_explosion_type()
        else:
            explosion_type = None

        # Garantir que explosion_size não seja None
        if explosion_size is None:
            explosion_size = self._calculate_default_explosion_size(enemy)

        # Explosão fatal sempre ocorre no centro do inimigo
        entity_manager.spawn_explosion(
            cx, cy, size=explosion_size, explosion_type=explosion_type
        )

        # Som apropriado
        if isinstance(enemy, Meteor):
            sound_manager.play_explosion_asteroid()
        else:
            sound_manager.play_explosion_alien()

        pts = self._get_points_value(enemy)

        # Fragmentos (apenas meteoros)
        if isinstance(enemy, Meteor) and hasattr(enemy, "spawn_fragments"):
            fragments = enemy.spawn_fragments(
                is_side_scroll=self.is_side_scroll,
                meteor_factory=entity_manager.meteor_pool.get,
            )
            for frag in fragments:
                entity_manager.enemies.append(frag)

        return pts, (cx, cy, pts), True

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

            # Calcular distância
            cx, cy, radius = self.get_collision_info(enemy)
            dist_sq = (cx - source_x) ** 2 + (cy - source_y) ** 2

            # Verificar colisão
            if dist_sq < (damage_radius + radius) ** 2:
                hit_tracking_set.add(enemy_id)

                if isinstance(enemy, ExplosiveMine):
                    enemy.take_damage(damage_to_mine)
                elif self._is_invulnerable_to_damage(enemy):
                    self._handle_invulnerable_hit(source_x, source_y, entity_manager)
                else:
                    pts, score_event, killed = self._destroy_enemy(
                        enemy,
                        enemies,
                        entity_manager,
                        explosion_size=None,  # Usar tamanho padrão do inimigo
                    )
                    score_gain += pts
                    if killed:
                        destroyed_count += 1
                    if score_event is not None:
                        score_events.append(score_event)

        return score_gain, destroyed_count, score_events

    def _apply_boss_damage(
        self,
        projectiles: list[Bullet] | list[MiniShipBullet],
        boss: Boss | SpikeBoss | SlimeBoss | GiantMeteorBoss,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
        is_piercing_allowed: bool = False,
    ) -> int:
        """Helper para dano unificado ao boss (normal, spike ou slime).

        Centraliza lógica de 4 métodos idênticos.
        Usa pixel-perfect collision para SlimeBoss quando disponível.
        Retorna score_gain.
        """
        score_gain = 0

        for proj in projectiles[:]:
            proj_rect = proj.rect

            # Check for collision
            collision_detected = self._check_mask_collision(
                proj_rect, None, boss, proj.x, proj.y
            )

            if collision_detected:
                # Destruir projétil se não for piercing
                if not (is_piercing_allowed and getattr(proj, "piercing", False)):
                    proj.dead = True

                # Aplicar dano com multiplicador
                damage = int(
                    proj.damage * config_instance.BOSS_UPGRADE_DAMAGE_MULTIPLIER
                )
                boss.take_damage(damage)
                sound_manager.play_boss_damage()
                entity_manager.spawn_explosion(proj.x, proj.y, size=15)

                # Recompensa e efeitos ao derrotar
                if boss.dead:
                    cx, cy = boss.x + boss.w / 2, boss.y + boss.h / 2

                    if isinstance(boss, SlimeBoss):
                        if not getattr(boss, "death_sequence_started", False):
                            boss.death_sequence_started = True
                            entity_manager.trigger_slime_boss_death(boss)
                            floating_scores.append(
                                FloatingScore(cx, cy, config_instance.BOSS_DEFEAT_SCORE)
                            )
                            score_gain += config_instance.BOSS_DEFEAT_SCORE
                    else:
                        floating_scores.append(
                            FloatingScore(cx, cy, config_instance.BOSS_DEFEAT_SCORE)
                        )
                        score_gain += config_instance.BOSS_DEFEAT_SCORE
                        entity_manager.spawn_explosion(cx, cy, size=100)

        return score_gain

    def bullets_vs_giant_meteor_boss(
        self,
        bullets: list[Bullet],
        boss: GiantMeteorBoss,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão de balas com GiantMeteorBoss.

        - Aplica dano com multiplicador de boss.
        - Em cada hit, chance de soltar pequenos fragmentos (meteoros) pelo pool.
        - Ao morrer, gera explosão e vários fragmentos.
        """
        score_gain = 0
        boss_rect = boss.rect

        for b in bullets[:]:
            if b.rect.colliderect(boss_rect):
                # Destruir bala se não for piercing
                if not getattr(b, "piercing", False):
                    b.dead = True

                # Dano com multiplicador
                damage = int(b.damage * Config.BOSS_UPGRADE_DAMAGE_MULTIPLIER)
                boss.take_damage(damage, entity_manager)
                sound_manager.play_boss_damage()
                entity_manager.spawn_explosion(b.x, b.y, size=18)

                # Chance de soltar fragmentos por hit
                if random.random() < Config.GIANT_METEOR_HIT_FRAGMENT_CHANCE:
                    count = random.randint(*Config.GIANT_METEOR_HIT_FRAGMENT_COUNT)
                    cx = boss.x + boss.w / 2
                    cy = boss.y + boss.h / 2
                    for _ in range(count):
                        size = random.randint(
                            Config.GIANT_METEOR_FRAGMENT_MIN_SIZE,
                            Config.GIANT_METEOR_FRAGMENT_MAX_SIZE,
                        )
                        ang = random.uniform(0, 2 * math.pi)
                        speed = random.uniform(90.0, 180.0)
                        vx = math.cos(ang) * speed
                        vy = math.sin(ang) * speed
                        entity_manager.spawn_meteor(
                            size=size, x=cx, y=cy, vx=vx, vy=abs(vy)
                        )

                # Checar morte
                if boss.dead:
                    cx, cy = boss.x + boss.w / 2, boss.y + boss.h / 2
                    floating_scores.append(
                        FloatingScore(cx, cy, Config.BOSS_DEFEAT_SCORE)
                    )
                    score_gain += Config.BOSS_DEFEAT_SCORE
                    entity_manager.spawn_explosion(cx, cy, size=120)

                    # Muitos fragmentos ao morrer
                    death_count = random.randint(
                        *Config.GIANT_METEOR_DEATH_FRAGMENT_COUNT
                    )
                    for _ in range(death_count):
                        size = random.randint(
                            Config.GIANT_METEOR_FRAGMENT_MIN_SIZE,
                            Config.GIANT_METEOR_FRAGMENT_MAX_SIZE,
                        )
                        ang = random.uniform(0, 2 * math.pi)
                        speed = random.uniform(120.0, 240.0)
                        vx = math.cos(ang) * speed
                        vy = math.sin(ang) * speed
                        entity_manager.spawn_meteor(
                            size=size, x=cx, y=cy, vx=vx, vy=abs(vy)
                        )
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
            if isinstance(enemy, ExplosiveMine):
                # Verificar se está explodindo E timer acabou (mas ainda não marcada dead)
                # OU já está dead (timer acabou no update anterior)
                should_explode = (
                    enemy.is_exploding
                    and enemy.pre_explosion_timer <= 0
                    and not enemy.dead
                ) or enemy.dead
                if should_explode:
                    cx, cy = (enemy.x, enemy.y)
                    explosion_radius = enemy.explosion_radius

                    mine_explosions.append(MineExplosion(cx, cy, size=explosion_radius))

                    # Checar nave e limpar formações
                    if self.handle_mine_explosion(
                        cx, cy, explosion_radius, ship, entity_manager
                    ):
                        ship_hit = True

                    sound_manager.play_explosion_boss()

                    # Marcar como dead DEPOIS de criar explosão
                    enemy.dead = True

                    pts = self._get_points_value(enemy)
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

                enemy_cx, enemy_cy, enemy_r = self.get_collision_info(enemy)

                dist_sq = (enemy_cx - explosion_x) ** 2 + (enemy_cy - explosion_y) ** 2

                if dist_sq < (explosion_radius + enemy_r) ** 2:
                    if isinstance(enemy, ExplosiveMine):
                        enemy.take_damage(enemy.health)
                    elif self._is_invulnerable_to_damage(enemy):
                        self._handle_invulnerable_hit(
                            explosion_x, explosion_y, entity_manager
                        )
                    else:
                        pts, score_event, killed = self._destroy_enemy(
                            enemy, enemies, entity_manager, explosion_size=None
                        )
                        score_gain += pts
                        if killed:
                            destroyed_count += 1
                        if score_event is not None:
                            score_events.append(score_event)

        return score_gain, destroyed_count, score_events, ship_hit

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
        enemies: Sequence[Enemy],
        entity_manager: "EntityManager",
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Verifica colisão contínua entre efeitos explosivos ativos e inimigos.

        Isso permite que fragmentos de meteoros e novos inimigos que entrem
        na área de explosão sofram dano enquanto o efeito estiver ativo.
        """
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
        boss: Boss | SpikeBoss | SlimeBoss | GiantMeteorBoss | StoneGolemBoss | None,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Verifica colisão entre efeitos explosivos e boss."""
        if not explosive_effects:
            return 0
        if not boss or boss.dead:
            return 0

        score_gain = 0

        for effect in explosive_effects:
            if not effect.damage_active:
                continue

            damage_radius = effect.current_damage_radius
            if damage_radius <= 0:
                continue

            # Calcular distância entre efeito explosivo e boss
            boss_center_x = boss.x + boss.w / 2
            boss_center_y = boss.y + boss.h / 2
            dx = effect.x - boss_center_x
            dy = effect.y - boss_center_y
            distance = (dx * dx + dy * dy) ** 0.5

            if distance <= damage_radius:
                # Boss atingido - aplicar dano
                damage = int(
                    effect.damage * config_instance.BOSS_UPGRADE_DAMAGE_MULTIPLIER
                )
                boss.take_damage(damage)
                sound_manager.play_boss_damage()
                entity_manager.spawn_explosion(boss_center_x, boss_center_y, size=30)

                # Verificar se boss morreu
                if boss.dead:
                    score_gain += config_instance.BOSS_DEFEAT_SCORE
                    floating_scores.append(
                        FloatingScore(
                            boss_center_x,
                            boss_center_y,
                            config_instance.BOSS_DEFEAT_SCORE,
                        )
                    )
                    entity_manager.spawn_explosion(
                        boss_center_x, boss_center_y, size=100
                    )

                # Marcar efeito como já atingiu este boss
                effect.hit_enemies.add(id(boss))

        return score_gain

    def air_strike_bombs_vs_enemies(
        self,
        air_strike_bombs: list[AirStrikeBomb],
        enemies: Sequence[Enemy],
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
        boss: Boss | SpikeBoss | SlimeBoss | GiantMeteorBoss | StoneGolemBoss | None,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Verifica colisão entre minas de torres e boss."""
        if not cannon_mines:
            return 0
        if not boss or boss.dead:
            return 0

        score_gain = 0

        for mine in cannon_mines:
            if mine.dead:
                continue

            damage_info = mine.damage_info
            if damage_info.radius <= 0:
                continue

            # Verificar se boss está dentro do raio de explosão
            boss_id = id(boss)
            hit_set = mine.hit_tracking_set
            if boss_id in hit_set:
                continue  # Já atingiu este boss

            # Calcular distância entre explosão da mina e boss
            boss_center_x = boss.x + boss.w / 2
            boss_center_y = boss.y + boss.h / 2
            dx = damage_info.x - boss_center_x
            dy = damage_info.y - boss_center_y
            distance = (dx * dx + dy * dy) ** 0.5

            if distance <= damage_info.radius:
                # Boss atingido - aplicar dano
                damage = int(
                    damage_info.damage * config_instance.BOSS_UPGRADE_DAMAGE_MULTIPLIER
                )
                boss.take_damage(damage)
                sound_manager.play_boss_damage()
                entity_manager.spawn_explosion(boss_center_x, boss_center_y, size=50)

                # Verificar se boss morreu
                if boss.dead:
                    score_gain += config_instance.BOSS_DEFEAT_SCORE
                    floating_scores.append(
                        FloatingScore(
                            boss_center_x,
                            boss_center_y,
                            config_instance.BOSS_DEFEAT_SCORE,
                        )
                    )
                    entity_manager.spawn_explosion(
                        boss_center_x, boss_center_y, size=100
                    )

                # Marcar mina como já atingiu este boss
                hit_set.add(boss_id)

        return score_gain

    def air_strike_bombs_vs_boss(
        self,
        air_strike_bombs: list[AirStrikeBomb],
        boss: Boss | SpikeBoss | SlimeBoss | GiantMeteorBoss | StoneGolemBoss | None,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Verifica colisão entre explosões de bombas e boss."""
        if not air_strike_bombs:
            return 0
        if not boss or boss.dead:
            return 0

        score_gain = 0

        for bomb in air_strike_bombs:
            if not bomb.exploding or not bomb.damage_active:
                continue

            damage_radius = bomb.explosion_radius
            if damage_radius <= 0:
                continue

            # Calcular distância entre bomba e boss
            boss_center_x = boss.x + boss.w / 2
            boss_center_y = boss.y + boss.h / 2
            dx = bomb.x - boss_center_x
            dy = bomb.target_y - boss_center_y
            distance = (dx * dx + dy * dy) ** 0.5

            if distance <= damage_radius:
                # Boss atingido - aplicar dano
                damage = int(
                    bomb.damage * config_instance.BOSS_UPGRADE_DAMAGE_MULTIPLIER
                )
                boss.take_damage(damage)
                sound_manager.play_boss_damage()
                entity_manager.spawn_explosion(boss_center_x, boss_center_y, size=50)

                # Verificar se boss morreu
                if boss.dead:
                    score_gain += config_instance.BOSS_DEFEAT_SCORE
                    floating_scores.append(
                        FloatingScore(
                            boss_center_x,
                            boss_center_y,
                            config_instance.BOSS_DEFEAT_SCORE,
                        )
                    )
                    entity_manager.spawn_explosion(
                        boss_center_x, boss_center_y, size=100
                    )

                # Marcar bomba como já atingiu este boss
                bomb.hit_enemies.add(id(boss))

        return score_gain

    def mini_ship_bullets_vs_enemies(
        self,
        mini_ship_bullets: list[MiniShipBullet],
        enemy_grid: SpatialGrid[Any],
        enemies: Sequence[Enemy],  # Para adicionar fragments
        entity_manager: "EntityManager",  # <-- ADICIONAR
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        # Early return se lista vazia
        if not mini_ship_bullets:
            return 0, 0, []

        # Usar batch query para otimização
        projectile_targets = self._batch_query_for_projectiles(
            mini_ship_bullets,
            enemy_grid,
            padding=CollisionConstants.SPATIAL_QUERY_PADDING,
        )

        for b in mini_ship_bullets[:]:
            potential_enemies = projectile_targets.get(id(b), [])

            # Early return se query vazia
            if not potential_enemies:
                continue

            for enemy in potential_enemies:
                if self._projectile_collides_with_enemy(b.rect, enemy):
                    if isinstance(enemy, ExplosiveMine):
                        enemy.take_damage(1)
                    elif self._is_invulnerable_to_damage(enemy):
                        self._handle_invulnerable_hit(b.x, b.y, entity_manager)
                    else:
                        pts, score_event, killed = self._destroy_enemy(
                            enemy,
                            enemies,
                            entity_manager,
                            explosion_size=None,
                            hit_x=b.x,
                            hit_y=b.y,
                        )
                        score_gain += pts
                        if killed:
                            destroyed_count += 1
                        if score_event is not None:
                            score_events.append(score_event)

                    if self._process_projectile_hit(
                        b, b.x, b.y, entity_manager, create_explosion=False
                    ):
                        break  # Bullet is gone, check next bullet
        return score_gain, destroyed_count, score_events

    def bullets_vs_enemies(
        self,
        bullets: list[Bullet],
        mine_explosions: list[MineExplosion],  # noqa: ARG002
        ship: Ship,  # noqa: ARG002
        enemy_grid: SpatialGrid[Any],
        enemies: Sequence[Enemy],  # Para adicionar fragments
        entity_manager: "EntityManager",  # <-- NOVO
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        _ = mine_explosions, ship  # Unused; kept for API compatibility
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        # Early return se lista vazia
        if not bullets:
            return 0, 0, []

        # Usar batch query para otimização
        projectile_targets = self._batch_query_for_projectiles(
            bullets, enemy_grid, padding=CollisionConstants.SPATIAL_QUERY_PADDING
        )

        for b in bullets[:]:
            potential_enemies = projectile_targets.get(id(b), [])

            # Early return se query vazia
            if not potential_enemies:
                continue

            for enemy in potential_enemies:
                if self._projectile_collides_with_enemy(b.rect, enemy):  # Usa cache
                    if isinstance(enemy, ExplosiveMine):
                        enemy.take_damage(1)
                    elif self._is_invulnerable_to_damage(enemy):
                        self._handle_invulnerable_hit(b.x, b.y, entity_manager)
                    else:
                        # Usar helper consolidado
                        pts, score_event, killed = self._destroy_enemy(
                            enemy,
                            enemies,
                            entity_manager,
                            explosion_size=None,
                            hit_x=b.x,
                            hit_y=b.y,
                        )
                        score_gain += pts
                        if killed:
                            destroyed_count += 1
                        if score_event is not None:
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
                                    pts, score_event, killed = self._destroy_enemy(
                                        nearby_enemy,
                                        enemies,
                                        entity_manager,
                                        explosion_size=None,  # Usar tamanho padrão do inimigo
                                    )
                                    score_gain += pts
                                    if killed:
                                        destroyed_count += 1
                                    if score_event is not None:
                                        score_events.append(score_event)

                    if self._process_projectile_hit(
                        b, b.x, b.y, entity_manager, create_explosion=False
                    ):
                        break  # Bullet is gone, check next bullet
        return score_gain, destroyed_count, score_events

    def bullets_vs_boss(
        self,
        bullets: list[Bullet],
        boss: Boss | GiantMeteorBoss,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        if not bullets:
            return 0
        if not boss or boss.dead:
            return 0
        return self._apply_boss_damage(
            bullets, boss, floating_scores, entity_manager, is_piercing_allowed=True
        )

    def ship_vs_boss(
        self,
        ship: Ship,
        boss: Boss | SlimeBoss | GiantMeteorBoss,
        entity_manager: "EntityManager",
    ) -> bool:
        if not boss or boss.dead:
            return False
        if ship.invuln > 0:
            return False

        ship_mask = (
            pygame.mask.from_surface(ship.ship_image)
            if hasattr(ship, "ship_image") and ship.ship_image is not None
            else pygame.mask.Mask((ship.w, ship.h), fill=True)
        )

        if self._check_mask_collision(ship.rect, ship_mask, boss, ship.x, ship.y):
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
        # Durante invulnerabilidade, a nave fica intangível para colisão com inimigos.
        if ship.invuln > 0:
            return False

        # Usar grid existente

        ship_rect = ship.rect

        # Query potential collisions with ship's rect (expand by 10 pixels)
        query_x = ship_rect.x - 10
        query_y = ship_rect.y - 10
        query_w = ship_rect.width + 20
        query_h = ship_rect.height + 20
        potential_enemies = enemy_grid.query(query_x, query_y, query_w, query_h)
        for enemy in potential_enemies:
            if not enemy or getattr(enemy, "dead", False):
                continue

            if enemy and self._ship_collides_with_enemy(ship_rect, enemy):
                if not getattr(enemy, "causes_damage", True):
                    continue

                if isinstance(enemy, RockGlider):
                    ship_cx = ship.x + ship.w / 2
                    ship_cy = ship.y + ship.h / 2
                    (
                        _pts,
                        part_destroyed,
                        _fully_destroyed,
                        _part_center,
                        part_name,
                    ) = enemy.take_part_damage(
                        ship_cx,
                        ship_cy,
                        amount=max(enemy.ROCK_MAX_HP, enemy.BOT_MAX_HP),
                    )

                    if part_destroyed:
                        if part_name == "rock":
                            sound_manager.play_explosion_asteroid()
                        else:
                            sound_manager.play_explosion_alien()
                    else:
                        sound_manager.play_boss_damage()
                elif isinstance(enemy, ExplosiveMine):
                    enemy.dead = True  # Explode immediately
                    sound_manager.play_explosion_alien()
                elif isinstance(enemy, (Boulder, RockShard, EntryDebris, OrbitalRock)):
                    enemy.dead = True
                    sound_manager.play_explosion_asteroid()
                else:
                    if isinstance(enemy, EyeEnemy):
                        enemy.destroy()
                    enemy.dead = True
                    # Tocar som de colisão apropriado baseado no tipo de inimigo
                    if isinstance(enemy, Meteor):
                        sound_manager.play_explosion_asteroid()
                    elif isinstance(enemy, (Alien, SquareMinionBoss)):
                        sound_manager.play_explosion_alien()
                    else:
                        # EyeEnemy e outros
                        sound_manager.play_explosion_alien()

                entity_manager.spawn_explosion(
                    ship.x + ship.w / 2, ship.y + ship.h / 2, size=30
                )
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
        boss: Boss | GiantMeteorBoss,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão de balas das mini ships com Boss normal."""
        if not mini_ship_bullets:
            return 0
        if not boss or boss.dead:
            return 0
        return self._apply_boss_damage(
            mini_ship_bullets,
            boss,
            floating_scores,
            entity_manager,
            is_piercing_allowed=True,  # Allow piercing if bullets have piercing=True
        )

    def mini_ship_bullets_vs_spike_boss(
        self,
        mini_ship_bullets: list[MiniShipBullet],
        boss: SpikeBoss,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão de balas das mini ships com SpikeBoss."""
        if not mini_ship_bullets:
            return 0
        if not boss or boss.dead:
            return 0
        return self._apply_boss_damage(
            mini_ship_bullets,
            boss,
            floating_scores,
            entity_manager,
            is_piercing_allowed=True,  # Allow piercing if bullets have piercing=True
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

    def bullets_vs_spike_boss(
        self,
        bullets: list[Bullet],
        boss: SpikeBoss,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão de balas com SpikeBoss."""
        if not bullets:
            return 0
        if not boss or boss.dead:
            return 0
        return self._apply_boss_damage(
            bullets, boss, floating_scores, entity_manager, is_piercing_allowed=True
        )

    def bullets_vs_slime_boss(
        self,
        bullets: list[Bullet],
        boss: "SlimeBoss",
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão de balas com SlimeBoss."""
        if not bullets:
            return 0
        if not boss or boss.dead:
            return 0
        return self._apply_boss_damage(
            bullets, boss, floating_scores, entity_manager, is_piercing_allowed=True
        )

    def mini_ship_bullets_vs_slime_boss(
        self,
        mini_ship_bullets: list[MiniShipBullet],
        boss: "SlimeBoss",
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão de balas das mini ships com SlimeBoss."""
        if not mini_ship_bullets:
            return 0
        if not boss or boss.dead:
            return 0
        return self._apply_boss_damage(
            mini_ship_bullets,
            boss,
            floating_scores,
            entity_manager,
            is_piercing_allowed=True,  # Allow piercing if bullets have piercing=True
        )

    def ship_vs_spike_boss(
        self, ship: Ship, boss: SpikeBoss, entity_manager: "EntityManager"
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
                    # Marcar inimigo como já atingido por este laser
                    laser.hit_enemies.add(enemy_id)

                    # Aplicar dano de acordo com o tipo de inimigo
                    if isinstance(enemy, ExplosiveMine):
                        # Minas explosivas apenas sofrem dano, não são destruídas
                        enemy.take_damage(laser.damage)
                    elif isinstance(enemy, SquareMinionBoss):
                        # SquareMinionBoss não pode ser destruído por lasers
                        pass  # Não faz nada - imune a lasers
                    else:
                        # Para todos os outros inimigos (Meteoros, Aliens, EyeEnemies)
                        # Usar helper com explosion_size customizado
                        pts, score_event, killed = self._destroy_enemy(
                            enemy,
                            enemies,
                            entity_manager,
                            explosion_size=None,
                        )
                        score_gain += pts
                        if killed:
                            destroyed_count += 1
                        if score_event is not None:
                            score_events.append(score_event)
                            floating_scores.append(FloatingScore(*score_event))
        return score_gain, destroyed_count, score_events

    def player_lasers_vs_boss(
        self,
        player_lasers: list[PlayerLaser],
        boss: Boss | SpikeBoss | SlimeBoss | GiantMeteorBoss,
        floating_scores: list[FloatingScore],
        entity_manager: "EntityManager",
    ) -> int:
        """Colisão dos lasers do jogador com o boss.

        Usa pixel-perfect collision para SlimeBoss quando disponível.
        """
        if not player_lasers:
            return 0
        if not boss or boss.dead:
            return 0
        score_gain: int = 0

        for laser in player_lasers:
            if laser.w <= 0:
                continue

            line = laser.get_collision_line()
            boss_rect = pygame.Rect(boss.x, boss.y, boss.w, boss.h)

            collision_detected = False

            # Pixel-perfect collision for SlimeBoss
            if isinstance(boss, SlimeBoss) and hasattr(boss, "mask"):
                # Fast proximity check first (optimization)
                boss_center_x = boss.x + boss.w / 2
                boss_center_y = boss.y + boss.h / 2

                # Calculate distance from boss center to laser line
                start_pos, end_pos = line
                # Simple distance from point to line segment (approximation)
                dx = end_pos[0] - start_pos[0]
                dy = end_pos[1] - start_pos[1]
                length_squared = dx * dx + dy * dy

                if length_squared > 0:
                    # Vector from start to boss center
                    vx = boss_center_x - start_pos[0]
                    vy = boss_center_y - start_pos[1]

                    # Project point onto line
                    t = max(0, min(1, (vx * dx + vy * dy) / length_squared))
                    proj_x = start_pos[0] + t * dx
                    proj_y = start_pos[1] + t * dy

                    # Distance from boss center to projected point
                    dist_dx = boss_center_x - proj_x
                    dist_dy = boss_center_y - proj_y
                    distance_squared = dist_dx * dist_dx + dist_dy * dist_dy

                    # Only do expensive mask check if laser is reasonably close
                    proximity_threshold = (
                        boss.w / 2 + 50
                    ) ** 2  # 50 pixel buffer for laser width

                    if distance_squared <= proximity_threshold:
                        # Check rect collision first (additional optimization)
                        if boss_rect.clipline(line):
                            # For pixel-perfect, we need to check if the laser line intersects non-transparent pixels
                            # This is more complex - for now, we'll use a simplified approach
                            # Check multiple points along the laser line
                            steps = 10  # Check 10 points along the line
                            for i in range(steps + 1):
                                t = i / steps
                                check_x = start_pos[0] + t * (end_pos[0] - start_pos[0])
                                check_y = start_pos[1] + t * (end_pos[1] - start_pos[1])

                                # Convert to boss-relative coordinates
                                relative_x = int(check_x - boss.x)
                                relative_y = int(check_y - boss.y)

                                # Check if point is within boss bounds and mask
                                if (
                                    0 <= relative_x < boss.w
                                    and 0 <= relative_y < boss.h
                                ):
                                    if boss.mask.get_at((relative_x, relative_y)):
                                        collision_detected = True
                                        break
            else:
                # Rectangular collision for other bosses
                collision_detected = boss_rect.clipline(line)

            if collision_detected:
                # Verificar se já atingiu o boss
                boss_id = id(boss)
                if boss_id in laser.hit_enemies:
                    continue

                laser.hit_enemies.add(boss_id)
                # Apply damage modifier for laser upgrade against boss
                damage = int(
                    laser.damage * config_instance.BOSS_UPGRADE_DAMAGE_MULTIPLIER
                )
                boss.take_damage(damage)
                sound_manager.play_boss_damage()

                # Explosão no ponto de impacto
                cx: float = boss.x + boss.w / 2
                cy: float = boss.y + boss.h / 2
                entity_manager.spawn_explosion(cx, cy, size=30)

                if boss.dead:
                    # Boss sempre dá pontos fixos ao morrer
                    pts: int = config_instance.BOSS_DEFEAT_SCORE
                    score_gain += pts
                    floating_scores.append(FloatingScore(cx, cy, pts))
                    entity_manager.spawn_explosion(cx, cy, size=100)

        return score_gain
