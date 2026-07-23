from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Sequence, cast

import pygame

from ..entities.bullet import Bullet
from ..entities.explosion import ExplosionType
from ..entities.floating_score import FloatingScore
from ..entities.impact_styles import ImpactStyle
from ..entities.mini_ship_bullet import MiniShipBullet
from ..events import game_events as events
from . import enemy_shield, hit_sounds
from .collision_protocols import Enemy
from .hit_result import NO_HIT, HitResult

# Feedback imutável reusado quando o escudo bloqueia o hit inteiro (sem dano ao
# HP). Só centelha ciano — o som é escolhido/ tocado inline (quebra vs. clink);
# `sound=None` evita replay pelo fluxo padrão. Zero alocação por hit (§7).
_SHIELD_BLOCK: HitResult = HitResult(
    explosion_size=8,
    explosion_type=ExplosionType.CYBER,
)

if TYPE_CHECKING:
    from ..core.events import EventBus
    from ..core.spatial_grid import SpatialGrid
    from .entity_manager import EntityManager


_DEFAULT_SPATIAL_QUERY_PADDING = 10

# Cache compartilhada de máscaras retangulares por (w, h). Reuso entre todos
# os call sites: projétil, bala, laser. Tamanhos são poucos e estáveis.
_RECT_MASK_CACHE: dict[tuple[int, int], pygame.mask.Mask] = {}


def get_rect_mask(width: int, height: int) -> pygame.mask.Mask:
    """Retorna (e cacheia) uma máscara retangular cheia do tamanho pedido."""
    key = (width, height)
    mask = _RECT_MASK_CACHE.get(key)
    if mask is None:
        mask = pygame.mask.Mask((width, height), fill=True)
        _RECT_MASK_CACHE[key] = mask
    return mask


def get_enemy_collision_mask_data(
    enemy: Any,
) -> tuple[pygame.mask.Mask, tuple[int, int]] | None:
    """Resolve a máscara do inimigo via `get_collision_mask_data` ou `.mask`/`.rect`."""
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

    # Fallback: padrão pygame.sprite (.mask + .rect).
    if hasattr(enemy, "mask"):
        mask = getattr(enemy, "mask")
        if mask is not None:
            if hasattr(enemy, "rect"):
                rect = getattr(enemy, "rect")
                if rect is not None:
                    return cast(pygame.mask.Mask, mask), (rect.x, rect.y)

    return None


class CollisionPhysics:
    """Helpers de física desacoplados do dispatcher `Collisions`.

    `Collisions` continua orquestrando os pares X-vs-Y; esta classe centraliza
    a aplicação efetiva do dano (`apply_hit`, `apply_ship_contact`,
    `apply_area_damage`) e as primitivas geométricas (`check_mask_collision`,
    `batch_query_for_projectiles`). Testável isoladamente — só depende de
    `EventBus` opcional.
    """

    def __init__(self, event_bus: "EventBus | None" = None) -> None:
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Geometria
    # ------------------------------------------------------------------

    def check_mask_collision(
        self,
        entity_rect: pygame.Rect,
        entity_mask: pygame.mask.Mask | None,
        target_with_mask: Any,
        _entity_x: float,
        _entity_y: float,
    ) -> bool:
        """Colisão pixel-perfect entre `entity_rect` e `target_with_mask`.

        Prioridade:
          1. `get_collision_mask_data()` — máscara com offset correto (float,
             jitter, etc).
          2. Atributo `.mask` + `.rect` — padrão pygame.sprite.
          3. AABB puro via `.rect`.
        """
        mask_data = get_enemy_collision_mask_data(target_with_mask)
        if mask_data is not None:
            target_mask, (tx, ty) = mask_data
            target_mask_rect = pygame.Rect(tx, ty, *target_mask.get_size())
            if not entity_rect.colliderect(target_mask_rect):
                return False
            if entity_mask is None:
                entity_mask = get_rect_mask(entity_rect.width, entity_rect.height)
            return (
                entity_mask.overlap(
                    target_mask, (tx - entity_rect.x, ty - entity_rect.y)
                )
                is not None
            )

        sprite_mask = getattr(target_with_mask, "mask", None)
        if sprite_mask is not None:
            target_rect: pygame.Rect | None = getattr(target_with_mask, "rect", None)
            if target_rect is None:
                target_rect = pygame.Rect(
                    target_with_mask.x,
                    target_with_mask.y,
                    target_with_mask.w,
                    target_with_mask.h,
                )
            if not entity_rect.colliderect(target_rect):
                return False
            if entity_mask is None:
                entity_mask = get_rect_mask(entity_rect.width, entity_rect.height)
            offset = (target_rect.x - entity_rect.x, target_rect.y - entity_rect.y)
            return (
                cast("pygame.mask.Mask", sprite_mask).overlap(entity_mask, offset)
                is not None
            )

        fallback_rect: pygame.Rect | None = getattr(target_with_mask, "rect", None)
        if fallback_rect is None:
            fallback_rect = pygame.Rect(
                target_with_mask.x,
                target_with_mask.y,
                target_with_mask.w,
                target_with_mask.h,
            )
        return entity_rect.colliderect(fallback_rect)

    @staticmethod
    def batch_query_for_projectiles(
        projectiles: Sequence[Bullet | MiniShipBullet],
        grid: "SpatialGrid[Any]",
        padding: int = _DEFAULT_SPATIAL_QUERY_PADDING,
    ) -> dict[int, list[Enemy]]:
        """Query por projétil em vez de área única — evita AABB gigante quando
        as balas estão dispersas. Retorna `{id(p): [candidates]}`.
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

    # ------------------------------------------------------------------
    # Aplicação de dano
    # ------------------------------------------------------------------

    def apply_hit(
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
        """Roteador único: chama `target.on_hit` e materializa o HitResult.

        `impact` é o estilo da nave que disparou (ver `entities.impact_styles`)
        e só pinta hits NÃO-letais. A explosão de MORTE fica intacta — é a que o
        inimigo pede (ALIEN verde, SLIME roxo...), no burst de sempre. É o que
        preserva a identidade de tema dos hostis, inclusive a de quem morre no
        primeiro tiro. None = efeito genérico de sempre.

        `impact_scale` (> 1.0 sob Giant Shot) engorda o burst do impacto da nave
        junto com o tiro aumentado. Só afeta o efeito estético NÃO-letal — a
        explosão de morte do hostil segue no tamanho que ele pede.
        """
        # Escudo temporário (enemy_shield): absorve antes do HP. Som de quebra
        # quando o escudo é esgotado; clink quando aguenta. Se engole o hit
        # inteiro, a entidade não recebe `on_hit` — feedback de centelha.
        if damage > 0 and getattr(target, "shield_hp", 0.0) > 0.0:
            damage = enemy_shield.absorb(target, damage)
            shield_broke = getattr(target, "shield_hp", 0.0) <= 0.0
            if damage <= 0:
                entity_manager.spawn_explosion(
                    hit_x,
                    hit_y,
                    size=_SHIELD_BLOCK.explosion_size,
                    explosion_type=_SHIELD_BLOCK.explosion_type,
                )
                (hit_sounds.SHIELD_BREAK if shield_broke else hit_sounds.BOSS_DAMAGE)()
                return _SHIELD_BLOCK
            # Escudo esgotado mas com dano sobrando: quebra e o resto vai ao HP.
            if shield_broke:
                hit_sounds.SHIELD_BREAK()

        result: HitResult = target.on_hit(damage, hit_x, hit_y)

        if result.explosion_size > 0:
            if impact is not None and not result.killed:
                scaled_size = (
                    result.explosion_size
                    if impact_scale == 1.0
                    else max(1, round(result.explosion_size * impact_scale))
                )
                entity_manager.spawn_explosion(
                    hit_x,
                    hit_y,
                    size=scaled_size,
                    explosion_type=impact.palette,
                    pattern=impact.pattern,
                )
            else:
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

        if result.killed and result.points > 0:
            if floating_scores is not None:
                if self._event_bus is not None:
                    self._event_bus.emit(
                        events.SpawnFloatingScore(
                            x=hit_x,
                            y=hit_y,
                            score=result.points,
                            color=(255, 255, 0),
                        )
                    )
                else:
                    floating_scores.append(FloatingScore(hit_x, hit_y, result.points))

        if (
            result.killed
            and self._event_bus is not None
            and not getattr(target, "is_boss", False)
        ):
            self._event_bus.emit(
                events.EnemyDestroyed(
                    enemy_type=type(target).__name__,
                    position=(hit_x, hit_y),
                    points=result.points,
                )
            )

        if result.triggers_special_death:
            entity_manager.trigger_death_sequence(target)

        return result

    @staticmethod
    def apply_ship_contact(
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

    def apply_area_damage(
        self,
        source_x: float,
        source_y: float,
        damage_radius: float,
        hit_tracking_set: set[int],
        enemies: Sequence[Enemy],
        entity_manager: "EntityManager",
        damage: int = 1,
    ) -> tuple[int, int, list[tuple[float, float, int]]]:
        """Aplica dano em área (explosive effects, air strikes, explosive bullets)."""
        score_gain = 0
        destroyed_count = 0
        score_events: list[tuple[float, float, int]] = []

        for enemy in enemies:
            if enemy.dead:
                continue

            enemy_id = id(enemy)
            if enemy_id in hit_tracking_set:
                continue

            cx, cy, radius = enemy.collision_circle()
            dist_sq = (cx - source_x) ** 2 + (cy - source_y) ** 2

            if dist_sq < (damage_radius + radius) ** 2:
                hit_tracking_set.add(enemy_id)

                hit_damage = (
                    enemy.health
                    if getattr(enemy, "is_explosive_mine", False)
                    else damage
                )
                result = self.apply_hit(
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
